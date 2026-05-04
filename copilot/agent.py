"""
Core agent loop for the Clinical Co-Pilot.

Architecture:
  - Multi-turn conversations are stored in memory keyed by session_id.
  - Each turn uses Claude's tool_use to retrieve patient data on demand.
  - Tool calls are dispatched to tools.py, which queries OpenEMR's MariaDB.
  - After the final response is assembled, it passes through verification.py.
  - All steps are traced through observability.py.

The agent uses a two-phase prompt:
  1. SYSTEM prompt: fixed role definition, constraints, and refusal policy.
     Never modified by user input or tool results.
  2. HUMAN messages: physician questions + tool results (as tool_result blocks).

Multi-turn context is maintained by appending to the messages list.
Conversations expire after CONVERSATION_TTL seconds of inactivity.
"""
import json
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CONVERSATION_TTL, DEMO_MODE
from observability import (
    log_llm_call, log_request_start, log_request_complete,
    new_trace, timer
)
from tools import TOOL_DEFINITIONS, dispatch_tool
from verification import verify

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# In-memory conversation store: {session_id: {"messages": [...], "last_active": float, "pid": int}}
_conversations: dict[str, dict] = {}

SYSTEM_PROMPT = """You are the Clinical Co-Pilot, an AI assistant embedded in OpenEMR, \
an electronic health record system. You assist primary care physicians by surfacing \
relevant patient context from their chart at the point of care.

YOUR ROLE:
- Retrieve and summarize what is documented in this patient's chart.
- Surface what is relevant to the current visit based on the physician's question.
- Identify and explicitly flag gaps in the chart data.
- Cite the source of every clinical fact (e.g., "per SOAP note dated 2026-04-10").

ABSOLUTE CONSTRAINTS — NEVER VIOLATE THESE:
1. Only state facts that are explicitly present in the tool results you retrieve.
   If something is not in the chart, say "not documented" — never infer or extrapolate.
2. Never suggest, recommend, or imply a diagnosis, treatment plan, medication change,
   or clinical decision of any kind. You surface information. The physician decides.
3. Never use directive language: "you should", "I recommend", "consider changing", etc.
4. If asked for medical advice, a diagnosis, or a prescription recommendation,
   decline clearly and redirect: "I can surface what's in the chart — clinical
   decisions are yours."
5. If asked about a patient not present in your tools' scope, decline.
6. Always cite your source for clinical facts. Format: "(source: [table/date])"

RESPONSE FORMAT:
- Use brief, scannable bullet points for briefings.
- Use concise prose for conversational follow-up questions.
- Lead with what is most clinically relevant to the visit reason.
- Always end a briefing with a "Chart gaps:" section listing any missing data.

DEMO MODE NOTE: """ + ("ACTIVE — operating on synthetic demo data only. No real PHI." if DEMO_MODE else "INACTIVE — operating on real patient data under BAA.") + """
"""


def _get_or_create_conversation(session_id: str, pid: int) -> dict:
    now = time.time()
    conv = _conversations.get(session_id)

    if conv is None or (now - conv["last_active"]) > CONVERSATION_TTL:
        # New or expired conversation
        _conversations[session_id] = {
            "messages": [],
            "pid": pid,
            "last_active": now,
            "turn": 0,
        }
    else:
        _conversations[session_id]["last_active"] = now

    return _conversations[session_id]


def clear_conversation(session_id: str):
    _conversations.pop(session_id, None)


def get_conversation_length(session_id: str) -> int:
    conv = _conversations.get(session_id)
    return len(conv["messages"]) // 2 if conv else 0


async def chat(
    session_id: str,
    pid: int,
    question: str,
) -> AsyncGenerator[str, None]:
    """
    Main agent entry point. Yields SSE-formatted strings:
      - "data: status:<message>\n\n"   — progress updates during tool calls
      - "data: token:<text>\n\n"       — response text tokens
      - "data: done\n\n"              — end of stream
      - "data: error:<message>\n\n"   — error condition
    """
    trace_id = new_trace()
    t_start = time.perf_counter()
    conv = _get_or_create_conversation(session_id, pid)
    conv["turn"] += 1
    turn = conv["turn"]

    log_request_start(trace_id, pid, question, turn)

    # Append the physician's question to the conversation
    conv["messages"].append({"role": "user", "content": question})

    tool_results_this_turn: list[dict] = []

    try:
        # --- Agentic tool-use loop ---
        while True:
            with timer() as llm_t:
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=TOOL_DEFINITIONS,
                    messages=conv["messages"],
                )

            log_llm_call(
                trace_id, CLAUDE_MODEL,
                response.usage.input_tokens,
                response.usage.output_tokens,
                llm_t.get("ms", 0),
            )

            # Append assistant response to conversation history
            conv["messages"].append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # No more tool calls — extract final text response
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text += block.text
                break

            if response.stop_reason == "tool_use":
                # Execute all tool calls in this response
                tool_result_blocks = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_name = block.name
                    tool_input = block.input

                    # Emit status to the client so the physician sees progress
                    status_labels = {
                        "get_patient_demographics": "Looking up patient demographics…",
                        "get_active_medications": "Retrieving active medications…",
                        "get_recent_encounters": "Loading recent encounters…",
                        "get_vitals": "Fetching latest vitals…",
                        "get_data_gaps": "Checking chart completeness…",
                    }
                    label = status_labels.get(tool_name, f"Running {tool_name}…")
                    yield f"data: status:{label}\n\n"

                    try:
                        result = dispatch_tool(tool_name, tool_input, pid, trace_id)
                        tool_results_this_turn.append(result)
                        tool_result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        })
                    except Exception as e:
                        tool_result_blocks.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps({"error": str(e)}),
                            "is_error": True,
                        })

                # Append tool results to conversation and loop
                conv["messages"].append({
                    "role": "user",
                    "content": tool_result_blocks,
                })
                continue

            # Unexpected stop reason
            final_text = "I encountered an unexpected response from the AI service."
            break

        # --- Verification ---
        yield "data: status:Verifying response…\n\n"
        result = verify(final_text, tool_results_this_turn, trace_id)

        # --- Stream the verified response ---
        # Split into words for smooth streaming effect
        words = result.annotated_response.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: token:{chunk}\n\n"

        total_ms = (time.perf_counter() - t_start) * 1000
        log_request_complete(trace_id, total_ms, "success")
        yield "data: done\n\n"

    except Exception as e:
        total_ms = (time.perf_counter() - t_start) * 1000
        log_request_complete(trace_id, total_ms, f"error: {e}")
        yield f"data: error:{str(e)}\n\n"
        yield "data: done\n\n"
