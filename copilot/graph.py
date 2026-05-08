"""LangGraph supervisor + 2 workers for Clinical Co-Pilot v2.

Nodes:
  supervisor        — routes on first pass; assembles final answer on second pass
  intake_extractor  — calls attach_and_extract() for uploaded clinical documents
  evidence_retriever — calls GuidelineRetriever for cited guideline snippets

Routing:
  file_path present → supervisor → intake_extractor → evidence_retriever → supervisor (assemble)
  guideline-only    → supervisor → evidence_retriever → supervisor (assemble)

All handoffs are logged as structured dicts per CONTEXT.md spec:
  {timestamp, from_node, to_node, reason, input_summary}
"""
from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

import anthropic
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from ingest import attach_and_extract
from observability import log_graph_handoff
from retriever import search_guidelines


# ── State ──────────────────────────────────────────────────────────────────────

class GraphState(TypedDict):
    query: str
    patient_id: int
    file_path: Optional[str]
    doc_type: Optional[str]           # "lab_pdf" | "intake_form"
    intake_result: Optional[dict]     # serialized output of attach_and_extract
    evidence_chunks: Optional[list[dict]]  # serialized RetrievedChunks
    final_answer: str
    handoffs: Annotated[list[dict], operator.add]  # append-only reducer
    phase: Literal["route", "assemble"]


# ── Handoff helper ─────────────────────────────────────────────────────────────

def _handoff(from_node: str, to_node: str, reason: str, input_summary: str) -> dict:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "from_node": from_node,
        "to_node": to_node,
        "reason": reason,
        "input_summary": input_summary,
    }
    log_graph_handoff(record)
    return record


# ── Nodes ──────────────────────────────────────────────────────────────────────

def supervisor(state: GraphState) -> dict:
    if state["phase"] == "route":
        return {}  # no state changes; routing handled by conditional edge

    # Assemble phase: combine worker outputs into a final answer via Claude
    context_parts: list[str] = []

    if state.get("intake_result"):
        context_parts.append(
            "=== Extracted Document Data ===\n"
            + json.dumps(state["intake_result"], indent=2, default=str)
        )

    if state.get("evidence_chunks"):
        chunks_text = "\n\n".join(
            f"[{c['citation']['source_id']} / {c['citation']['page_or_section']}]\n{c['text']}"
            for c in state["evidence_chunks"]
        )
        context_parts.append("=== Guideline Evidence ===\n" + chunks_text)

    if not context_parts:
        return {"final_answer": "No relevant information could be retrieved for this query."}

    context = "\n\n".join(context_parts)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Clinical query: {state['query']}\n\n"
                    f"{context}\n\n"
                    "Using only the information above, provide a concise clinical summary. "
                    "Every clinical fact must cite its source. "
                    "Do not add information not present in the context above."
                ),
            }
        ],
    )
    return {"final_answer": msg.content[0].text}


def _supervisor_router(state: GraphState) -> str:
    if state["phase"] == "assemble":
        return "end"
    if state.get("file_path"):
        return "intake_extractor"
    return "evidence_retriever"


def intake_extractor(state: GraphState) -> dict:
    h_out = _handoff(
        "supervisor", "intake_extractor",
        "document upload detected",
        f"file={state['file_path']}, doc_type={state['doc_type']}",
    )
    extraction = attach_and_extract(
        patient_id=state["patient_id"],
        file_path=state["file_path"],
        doc_type=state["doc_type"],
    )
    serialized = extraction.data_as_dicts()
    if isinstance(serialized, list):
        summary = f"extracted {len(serialized)} lab result(s) (doc_id={extraction.doc_id})"
    else:
        summary = f"extracted intake form (doc_id={extraction.doc_id})"

    h_back = _handoff(
        "intake_extractor", "evidence_retriever",
        "extraction complete, forwarding to evidence retriever",
        summary,
    )
    return {"intake_result": serialized, "handoffs": [h_out, h_back]}


def evidence_retriever(state: GraphState) -> dict:
    from_node = "intake_extractor" if state.get("intake_result") is not None else "supervisor"
    h_out = _handoff(
        from_node, "evidence_retriever",
        "retrieving guideline evidence",
        f"query_preview={state['query'][:100]}",
    )
    chunks = search_guidelines(state["query"])
    serialized = [
        {
            "text": c.text,
            "relevance_score": c.score,
            "citation": c.citation.model_dump(),
        }
        for c in chunks
    ]
    h_back = _handoff(
        "evidence_retriever", "supervisor",
        "retrieval complete, returning to supervisor for assembly",
        f"retrieved {len(serialized)} chunk(s)",
    )
    return {
        "evidence_chunks": serialized,
        "phase": "assemble",
        "handoffs": [h_out, h_back],
    }


# ── Graph assembly ─────────────────────────────────────────────────────────────

def _build_graph():
    g = StateGraph(GraphState)

    g.add_node("supervisor", supervisor)
    g.add_node("intake_extractor", intake_extractor)
    g.add_node("evidence_retriever", evidence_retriever)

    g.set_entry_point("supervisor")

    g.add_conditional_edges(
        "supervisor",
        _supervisor_router,
        {
            "intake_extractor": "intake_extractor",
            "evidence_retriever": "evidence_retriever",
            "end": END,
        },
    )
    # intake_extractor always flows directly to evidence_retriever
    g.add_edge("intake_extractor", "evidence_retriever")
    # evidence_retriever returns to supervisor for final assembly
    g.add_edge("evidence_retriever", "supervisor")

    return g.compile()


_graph = _build_graph()


def run_graph(
    patient_id: int,
    query: str,
    file_path: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> dict:
    """Invoke the supervisor graph and return the assembled result.

    Returns a dict with: final_answer, handoffs, intake_result, evidence_chunks_count.
    """
    initial_state: GraphState = {
        "query": query,
        "patient_id": patient_id,
        "file_path": file_path,
        "doc_type": doc_type,
        "intake_result": None,
        "evidence_chunks": None,
        "final_answer": "",
        "handoffs": [],
        "phase": "route",
    }
    final_state = _graph.invoke(initial_state)
    return {
        "final_answer": final_state.get("final_answer", ""),
        "handoffs": final_state.get("handoffs", []),
        "intake_result": final_state.get("intake_result"),
        "evidence_chunks_count": len(final_state.get("evidence_chunks") or []),
    }
