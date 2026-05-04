<?php
/**
 * Clinical Co-Pilot — Bootstrap
 *
 * Listens to OpenEMR's Main\Tabs render event and injects the
 * Co-Pilot sidebar panel HTML + JavaScript into the main frame.
 */

namespace OpenEMR\Modules\CopilotModule;

use OpenEMR\Events\Main\Tabs\RenderEvent;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class Bootstrap
{
    public function __construct(
        private EventDispatcherInterface $eventDispatcher
    ) {}

    public function subscribeToEvents(): void
    {
        $this->eventDispatcher->addListener(
            RenderEvent::EVENT_BODY_RENDER_POST,
            $this->renderCopilotPanel(...)
        );
    }

    public function renderCopilotPanel(RenderEvent $event): void
    {
        // The Co-Pilot service secret — must match COPILOT_SECRET env var
        $secret = getenv('COPILOT_SECRET') ?: 'dev-secret-change-in-production';
        $copilotBase = '/copilot'; // Proxied by Apache to the copilot-service container
        ?>
        <!-- Clinical Co-Pilot Panel -->
        <div id="copilot-panel" style="
            position: fixed;
            right: 0; top: 60px;
            width: 380px; height: calc(100vh - 60px);
            background: #fff;
            border-left: 1px solid #dee2e6;
            box-shadow: -2px 0 8px rgba(0,0,0,0.1);
            display: flex; flex-direction: column;
            z-index: 9999;
            transform: translateX(380px);
            transition: transform 0.25s ease;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            font-size: 13px;
        ">
            <!-- Header -->
            <div style="
                padding: 10px 14px;
                background: #1a6e8e;
                color: white;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-shrink: 0;
            ">
                <div style="font-weight: 600; font-size: 14px;">
                    🩺 Clinical Co-Pilot
                    <?php if (getenv('COPILOT_DEMO_MODE') !== 'false'): ?>
                        <span style="font-size:10px; background:rgba(255,255,255,0.2);
                            padding:1px 6px; border-radius:10px; margin-left:6px;">DEMO</span>
                    <?php endif; ?>
                </div>
                <div style="display:flex; gap:8px; align-items:center;">
                    <span id="copilot-patient-name" style="font-size:11px; opacity:0.85;"></span>
                    <button onclick="copilotClear()" title="Clear conversation"
                        style="background:none; border:none; color:white; cursor:pointer;
                               font-size:16px; padding:0 4px; opacity:0.7;">↺</button>
                    <button onclick="copilotToggle()" title="Close"
                        style="background:none; border:none; color:white; cursor:pointer;
                               font-size:18px; padding:0 4px;">×</button>
                </div>
            </div>

            <!-- Messages area -->
            <div id="copilot-messages" style="
                flex: 1; overflow-y: auto;
                padding: 12px;
                display: flex; flex-direction: column; gap: 10px;
            ">
                <div style="color:#6c757d; font-size:12px; text-align:center; padding:20px 0;">
                    Open a patient chart to begin.
                </div>
            </div>

            <!-- Input area -->
            <div style="
                padding: 10px;
                border-top: 1px solid #dee2e6;
                flex-shrink: 0;
                background: #f8f9fa;
            ">
                <div style="display:flex; gap:6px; margin-bottom:6px;">
                    <button onclick="copilotBriefing()"
                        style="flex:1; padding:7px; background:#1a6e8e; color:white;
                               border:none; border-radius:4px; cursor:pointer; font-size:12px;
                               font-weight:500;">
                        ⚡ Pre-Visit Briefing
                    </button>
                    <button onclick="copilotGaps()"
                        style="flex:1; padding:7px; background:#fff; color:#1a6e8e;
                               border:1px solid #1a6e8e; border-radius:4px; cursor:pointer;
                               font-size:12px;">
                        🔍 Chart Gaps
                    </button>
                </div>
                <div style="display:flex; gap:6px;">
                    <textarea id="copilot-input"
                        placeholder="Ask about this patient…"
                        onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();copilotSend();}"
                        style="flex:1; padding:7px; border:1px solid #ced4da;
                               border-radius:4px; resize:none; font-size:12px;
                               font-family:inherit; height:52px;"></textarea>
                    <button onclick="copilotSend()"
                        style="padding:7px 12px; background:#1a6e8e; color:white;
                               border:none; border-radius:4px; cursor:pointer;">
                        ↑
                    </button>
                </div>
                <div style="font-size:10px; color:#adb5bd; margin-top:4px; text-align:center;">
                    AI-generated. Verify all clinical information in the chart.
                </div>
            </div>
        </div>

        <!-- Toggle button (always visible) -->
        <button id="copilot-toggle-btn" onclick="copilotToggle()" style="
            position: fixed;
            right: 0; top: 50%;
            transform: translateY(-50%);
            background: #1a6e8e;
            color: white;
            border: none;
            border-radius: 6px 0 0 6px;
            padding: 12px 8px;
            cursor: pointer;
            z-index: 10000;
            font-size: 18px;
            box-shadow: -2px 0 6px rgba(0,0,0,0.2);
            writing-mode: vertical-rl;
            letter-spacing: 1px;
            font-size: 11px;
            font-weight: 600;
        ">Co-Pilot</button>

        <script>
        (function() {
            const BASE = <?= json_encode($copilotBase) ?>;
            const SECRET = <?= json_encode($secret) ?>;
            let currentPid = null;
            let sessionId = 'sess_' + Math.random().toString(36).substr(2, 12);
            let panelOpen = false;

            // Detect current patient by polling the session PID endpoint
            function pollPatient() {
                fetch('/interface/modules/custom_modules/oe-module-copilot/pid.php', {credentials: 'include'})
                    .then(r => r.json())
                    .then(data => {
                        if (data.pid && data.pid !== currentPid) {
                            currentPid = data.pid;
                            document.getElementById('copilot-patient-name').textContent =
                                data.name || ('Patient #' + data.pid);
                            // New patient — reset session
                            sessionId = 'sess_' + Math.random().toString(36).substr(2, 12);
                            resetMessages('Patient loaded: ' + (data.name || '#' + data.pid) +
                                         '. Click ⚡ Pre-Visit Briefing or ask a question.');
                        } else if (!data.pid) {
                            currentPid = null;
                            document.getElementById('copilot-patient-name').textContent = '';
                            resetMessages('Open a patient chart to begin.');
                        }
                    })
                    .catch(() => {});
            }

            function resetMessages(msg) {
                const el = document.getElementById('copilot-messages');
                el.innerHTML = '<div style="color:#6c757d;font-size:12px;text-align:center;padding:20px 0;">'
                    + escapeHtml(msg) + '</div>';
            }

            window.copilotToggle = function() {
                panelOpen = !panelOpen;
                document.getElementById('copilot-panel').style.transform =
                    panelOpen ? 'translateX(0)' : 'translateX(380px)';
                document.getElementById('copilot-toggle-btn').style.right =
                    panelOpen ? '380px' : '0';
            };

            window.copilotBriefing = function() {
                if (!currentPid) { alert('Please open a patient chart first.'); return; }
                sendMessage('Give me a pre-visit briefing for today\'s appointment. ' +
                    'Include active medications, recent encounter summary, latest vitals, ' +
                    'any pending items from the last visit, and chart gaps.');
            };

            window.copilotGaps = function() {
                if (!currentPid) { alert('Please open a patient chart first.'); return; }
                sendMessage('What is missing or incomplete in this patient\'s chart?');
            };

            window.copilotSend = function() {
                const input = document.getElementById('copilot-input');
                const q = input.value.trim();
                if (!q) return;
                if (!currentPid) { alert('Please open a patient chart first.'); return; }
                input.value = '';
                sendMessage(q);
            };

            window.copilotClear = function() {
                if (!currentPid) return;
                fetch(BASE + '/clear', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json', 'X-Copilot-Secret': SECRET},
                    body: JSON.stringify({session_id: sessionId})
                });
                sessionId = 'sess_' + Math.random().toString(36).substr(2, 12);
                resetMessages('Conversation cleared. Ask a new question.');
            };

            function sendMessage(question) {
                if (!panelOpen) copilotToggle();

                // Add physician message bubble
                addBubble('physician', question);
                const responseBubble = addBubble('copilot', '');
                const statusEl = document.createElement('div');
                statusEl.style.cssText = 'color:#6c757d;font-size:11px;font-style:italic;margin-top:4px;';
                responseBubble.appendChild(statusEl);
                const textEl = document.createElement('div');
                responseBubble.appendChild(textEl);

                fetch(BASE + '/chat', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json', 'X-Copilot-Secret': SECRET},
                    body: JSON.stringify({session_id: sessionId, pid: currentPid, question: question})
                }).then(res => {
                    const reader = res.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    function read() {
                        reader.read().then(({done, value}) => {
                            if (done) return;
                            buffer += decoder.decode(value, {stream: true});
                            const lines = buffer.split('\n');
                            buffer = lines.pop();

                            lines.forEach(line => {
                                if (!line.startsWith('data: ')) return;
                                const data = line.slice(6);
                                if (data.startsWith('status:')) {
                                    statusEl.textContent = data.slice(7);
                                } else if (data.startsWith('token:')) {
                                    statusEl.textContent = '';
                                    textEl.textContent += data.slice(6);
                                    // Auto-scroll
                                    document.getElementById('copilot-messages')
                                        .scrollTop = 99999;
                                } else if (data === 'done') {
                                    statusEl.remove();
                                    // Render markdown-ish formatting
                                    renderMarkdown(textEl);
                                } else if (data.startsWith('error:')) {
                                    statusEl.remove();
                                    textEl.style.color = '#dc3545';
                                    textEl.textContent = 'Error: ' + data.slice(6);
                                }
                            });
                            read();
                        });
                    }
                    read();
                }).catch(err => {
                    statusEl.remove();
                    textEl.style.color = '#dc3545';
                    textEl.textContent = 'Connection error. Is the Co-Pilot service running?';
                });
            }

            function addBubble(role, text) {
                const msgs = document.getElementById('copilot-messages');
                // Clear the "open a patient" placeholder on first message
                if (msgs.children.length === 1 && msgs.children[0].style.textAlign === 'center') {
                    msgs.innerHTML = '';
                }
                const bubble = document.createElement('div');
                bubble.style.cssText = role === 'physician'
                    ? 'background:#e3f2fd;padding:8px 10px;border-radius:8px;align-self:flex-end;max-width:90%;'
                    : 'background:#f1f3f5;padding:8px 10px;border-radius:8px;align-self:flex-start;max-width:100%;';
                if (text) bubble.textContent = text;
                msgs.appendChild(bubble);
                msgs.scrollTop = 99999;
                return bubble;
            }

            function renderMarkdown(el) {
                // Basic markdown: **bold**, bullet points, line breaks
                let html = escapeHtml(el.textContent);
                html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
                html = html.replace(/\n- /g, '\n• ');
                html = html.replace(/\n/g, '<br>');
                el.innerHTML = html;
            }

            function escapeHtml(s) {
                return String(s)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
            }

            // Poll for current patient every 3 seconds
            pollPatient();
            setInterval(pollPatient, 3000);
        })();
        </script>
        <?php
    }
}
