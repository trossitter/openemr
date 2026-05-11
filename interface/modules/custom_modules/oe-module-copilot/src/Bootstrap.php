<?php

/**
 * Clinical Co-Pilot — Bootstrap
 *
 * Listens to OpenEMR's Main\Tabs render event and injects the
 * Co-Pilot sidebar panel HTML + JavaScript into the main frame.
 *
 * Also injects a full UI theme override using a calming biophilic palette
 * derived from color theory research:
 *   - Deep navy navigation for trust/authority (WCAG AA contrast)
 *   - Surface mist background for reduced eye strain
 *   - Teal accents for primary actions (naturally calming)
 *   - Indigo for the AI Co-Pilot panel (distinct from clinical chrome)
 */

declare(strict_types=1);

namespace OpenEMR\Modules\CopilotModule;

use OpenEMR\Events\Main\Tabs\RenderEvent;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class Bootstrap
{
    public function __construct(
        private readonly EventDispatcherInterface $eventDispatcher
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

        <!-- ============================================================
             CLINICAL CO-PILOT — THEME OVERRIDES
             Clinical palette: soft blues, slate grays, clean whites
             Palette:
               --cp-nav:      #EBF4FB  Ice Blue        (navbar bg — light, clinical)
               --cp-nav-text: #1A3A52  Dark Slate      (navbar text on light bg)
               --cp-panel:    #FFFFFF  Clean White     (dropdowns/sidebar bg)
               --cp-surface:  #F5F9FC  Surface Mist    (main content bg)
               --cp-teal:     #0A7B7B  Teal Action     (primary buttons/links)
               --cp-mint:     #22A86E  Mint Confirm    (success/active states)
               --cp-text:     #1A2733  Body Text       (primary)
               --cp-muted:    #4A5E6D  Secondary Text  (labels/metadata)
               --cp-amber:    #B45309  Amber Alert     (warnings)
               --cp-indigo:   #2E6B9E  Clinical Blue   (Co-Pilot panel header)
               --cp-indigo-lt:#E8F4FD  Sky Tint        (physician bubble bg)
        ============================================================ -->
        <style id="copilot-theme">
        /* ── Root tokens ─────────────────────────────────────────── */
        :root {
            --cp-nav:       #EBF4FB;
            --cp-nav-text:  #1A3A52;
            --cp-nav-border:#C8DFF0;
            --cp-panel:     #FFFFFF;
            --cp-surface:   #F5F9FC;
            --cp-teal:      #0A7B7B;
            --cp-teal-dk:   #086363;
            --cp-mint:      #22A86E;
            --cp-text:      #1A2733;
            --cp-muted:     #4A5E6D;
            --cp-amber:     #B45309;
            --cp-indigo:    #2E6B9E;
            --cp-indigo-dk: #245680;
            --cp-indigo-lt: #E8F4FD;
            --cp-border:    #C9D5E0;
        }

        /* ── Body / main frame ───────────────────────────────────── */
        body {
            background-color: var(--cp-surface) !important;
            color: var(--cp-text) !important;
        }

        /* ── Navbar ──────────────────────────────────────────────── */
        .navbar.bg-light,
        #mainMenu .navbar,
        nav.navbar {
            background-color: var(--cp-nav) !important;
            border-bottom: 1px solid var(--cp-nav-border) !important;
        }

        /* Navbar brand / text links */
        .navbar .navbar-brand,
        .navbar .nav-link,
        .navbar .navbar-text,
        #mainMenu .nav-link,
        #mainMenu .navbar-brand {
            color: var(--cp-nav-text) !important;
        }

        .navbar .nav-link:hover,
        #mainMenu .nav-link:hover {
            color: #0F2A44 !important;
            background-color: rgba(0,0,0,0.06) !important;
            border-radius: 4px;
        }

        /* ── Dropdown menus ──────────────────────────────────────── */
        .dropdown-menu,
        .oe-dropdown-toggle + .dropdown-menu,
        .menuEntries {
            background-color: var(--cp-panel) !important;
            border: 1px solid var(--cp-border) !important;
            border-radius: 6px !important;
            box-shadow: 0 6px 20px rgba(0,0,0,0.12) !important;
            z-index: 99999 !important;
        }

        .dropdown-item,
        .dropdown-menu a,
        .menuEntries a,
        .menuEntries li a {
            color: #1A2733 !important;
            font-size: 13px !important;
            padding: 7px 16px !important;
        }

        .dropdown-item:hover,
        .dropdown-menu a:hover,
        .menuEntries a:hover {
            background-color: rgba(0,0,0,0.05) !important;
            color: #0F2A44 !important;
        }

        .dropdown-divider,
        .menuEntries hr {
            border-color: #E5EBF0 !important;
        }

        .dropdown-header {
            color: #4E6E82 !important;
            font-size: 10px !important;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }

        /* ── Patient search area (header search bar) ─────────────── */
        #anySearchBox,
        #anySearchBox input {
            border: 1px solid var(--cp-border) !important;
            border-radius: 20px !important;
            background: #FFFFFF !important;
            color: var(--cp-text) !important;
            padding: 4px 12px !important;
            font-size: 12px;
        }

        #anySearchBox input::placeholder {
            color: #547690 !important;
        }

        #anySearchBox input:focus {
            background: #FFFFFF !important;
            outline: none;
            border-color: var(--cp-teal) !important;
            box-shadow: 0 0 0 2px rgba(10,123,123,0.25) !important;
        }

        /* Search button in nav */
        #search_globals,
        button#search_globals {
            background: var(--cp-teal) !important;
            border-color: var(--cp-teal) !important;
            color: white !important;
            border-radius: 0 20px 20px 0 !important;
        }

        /* ── Page cards / panels ─────────────────────────────────── */
        .card,
        .panel,
        .tab-content,
        .container-fluid > .row,
        #main-container {
            background-color: #fff !important;
        }

        /* ── Primary buttons ─────────────────────────────────────── */
        .btn-primary,
        .btn-success:not(.btn-sm) {
            background-color: var(--cp-teal) !important;
            border-color: var(--cp-teal-dk) !important;
            color: white !important;
        }

        .btn-primary:hover,
        .btn-primary:focus {
            background-color: var(--cp-teal-dk) !important;
        }

        /* ── Links ───────────────────────────────────────────────── */
        a:not(.nav-link):not(.dropdown-item):not(.btn):not([class*="copilot"]) {
            color: var(--cp-teal) !important;
        }

        a:not(.nav-link):not(.dropdown-item):not(.btn):not([class*="copilot"]):hover {
            color: var(--cp-teal-dk) !important;
        }

        /* ── iframe content area ─────────────────────────────────── */
        #mainBox,
        .mainBox,
        iframe#iframe-content {
            background: var(--cp-surface) !important;
        }

        /* ── Tab headers ─────────────────────────────────────────── */
        .nav-tabs .nav-link.active,
        .nav-tabs .nav-item.show .nav-link {
            color: var(--cp-teal) !important;
            border-bottom-color: var(--cp-teal) !important;
        }

        /* ── Alerts ──────────────────────────────────────────────── */
        .alert-warning {
            background-color: #FFF3CD !important;
            border-color: var(--cp-amber) !important;
            color: var(--cp-amber) !important;
        }

        /* ── Scrollbar ───────────────────────────────────────────── */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb {
            background: var(--cp-border);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover { background: var(--cp-muted); }
        </style>

        <!-- ============================================================
             CLINICAL CO-PILOT — PANEL UI
        ============================================================ -->

        <!-- Co-Pilot Panel -->
        <div id="copilot-panel" style="
            position: fixed;
            right: 0; top: 60px;
            width: 380px; height: calc(100vh - 60px);
            background: #fff;
            border-left: 1px solid var(--cp-border, #C9D5E0);
            box-shadow: -3px 0 16px rgba(0,0,0,0.18);
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
                background: #2E6B9E;
                background: linear-gradient(135deg, #2E6B9E 0%, #245680 100%);
                color: white;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-shrink: 0;
            ">
                <div style="font-weight: 600; font-size: 14px; letter-spacing: 0.2px;">
                    🩺 Clinical Co-Pilot
                    <?php if (getenv('COPILOT_DEMO_MODE') !== 'false'): ?>
                        <span style="font-size:10px; background:rgba(0,0,0,0.18);
                            padding:1px 6px; border-radius:10px; margin-left:6px;
                            letter-spacing:0.5px;">DEMO</span>
                    <?php endif; ?>
                </div>
                <div style="display:flex; gap:8px; align-items:center;">
                    <span id="copilot-patient-name" style="font-size:11px; opacity:0.85;
                        max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"></span>
                    <button onclick="copilotClear()" title="Clear conversation"
                        style="background:rgba(0,0,0,0.18); border:none; color:white;
                               cursor:pointer; font-size:14px; padding:2px 6px; border-radius:4px;
                               transition:background 0.15s;">↺</button>
                    <button onclick="copilotToggle()" title="Close"
                        style="background:rgba(0,0,0,0.18); border:none; color:white;
                               cursor:pointer; font-size:16px; padding:2px 6px; border-radius:4px;
                               transition:background 0.15s;">×</button>
                </div>
            </div>

            <!-- Subheader: patient context strip -->
            <div id="copilot-context-strip" style="
                display:none;
                padding: 5px 14px;
                background: #E8F4FD;
                border-bottom: 1px solid #C9D5E0;
                font-size: 11px;
                color: #2E6B9E;
                font-weight: 500;
            "></div>

            <!-- Messages area -->
            <div id="copilot-messages" style="
                flex: 1; overflow-y: auto;
                padding: 12px;
                display: flex; flex-direction: column; gap: 10px;
                background: #F9FAFB;
            ">
                <div class="cp-placeholder" style="
                    color: #4A5E6D; font-size: 12px; text-align: center;
                    padding: 28px 12px;
                    background: #fff;
                    border-radius: 8px;
                    border: 1px dashed #C9D5E0;
                    margin-top: 8px;
                ">
                    <div style="font-size:28px; margin-bottom:10px;">🩺</div>
                    <strong style="color:#1A2733;">Clinical Co-Pilot</strong><br>
                    <span style="color:#4A5E6D;">Open a patient chart to begin.</span>
                </div>
            </div>

            <!-- Input area -->
            <div style="
                padding: 10px;
                border-top: 1px solid #C9D5E0;
                flex-shrink: 0;
                background: #fff;
            ">
                <!-- Quick action buttons -->
                <div style="display:flex; gap:6px; margin-bottom:8px;">
                    <button onclick="copilotBriefing()"
                        style="flex:1; padding:8px 6px;
                               background: linear-gradient(135deg, #0E8A8A 0%, #0B6E6E 100%);
                               color:white; border:none; border-radius:6px; cursor:pointer;
                               font-size:12px; font-weight:600; letter-spacing:0.2px;
                               transition: opacity 0.15s; box-shadow: 0 1px 4px rgba(14,138,138,0.3);">
                        ⚡ Pre-Visit Briefing
                    </button>
                    <button onclick="copilotGaps()"
                        style="flex:1; padding:8px 6px;
                               background:#fff; color:#0E8A8A;
                               border:1.5px solid #0E8A8A; border-radius:6px; cursor:pointer;
                               font-size:12px; font-weight:500;
                               transition: background 0.15s;">
                        🔍 Chart Gaps
                    </button>
                </div>
                <!-- Text input row -->
                <div style="display:flex; gap:6px;">
                    <textarea id="copilot-input"
                        placeholder="Ask about this patient…"
                        onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault();copilotSend();}"
                        style="flex:1; padding:8px 10px;
                               border:1.5px solid #C9D5E0;
                               border-radius:6px; resize:none; font-size:12px;
                               font-family:inherit; height:52px;
                               background: #F9FAFB; color: #1A2733;
                               transition: border-color 0.15s;
                               outline: none;"
                        onfocus="this.style.borderColor='#0E8A8A'"
                        onblur="this.style.borderColor='#C9D5E0'"></textarea>
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <button onclick="copilotSend()"
                            style="padding:8px 13px;
                                   background: linear-gradient(135deg, #3B4FBF 0%, #2E3E99 100%);
                                   color:white; border:none; border-radius:6px; cursor:pointer;
                                   font-size:16px; font-weight:600; flex:1;
                                   box-shadow: 0 1px 4px rgba(59,79,191,0.3);">↑</button>
                        <button onclick="document.getElementById('copilot-file-input').click()"
                            title="Upload lab PDF or intake form"
                            style="padding:5px 13px;
                                   background:#fff; color:#0E8A8A;
                                   border:1.5px solid #0E8A8A; border-radius:6px; cursor:pointer;
                                   font-size:13px;">📎</button>
                    </div>
                </div>
                <!-- Hidden file input for PDF upload -->
                <input type="file" id="copilot-file-input" accept=".pdf,.png,.jpg,.jpeg"
                    style="display:none"
                    onchange="copilotIngestFile(this)">
                <div style="font-size:10px; color:#4A5E6D; margin-top:6px; text-align:center;
                    border-top: 1px solid #F0F4F8; padding-top:6px;">
                    AI-generated · Verify all clinical information in the chart
                </div>
            </div>
        </div>

        <!-- Toggle button (always visible) -->
        <button id="copilot-toggle-btn" onclick="copilotToggle()" style="
            position: fixed;
            right: 0; top: 50%;
            transform: translateY(-50%);
            background: linear-gradient(180deg, #3B4FBF 0%, #2E3E99 100%);
            color: white;
            border: none;
            border-radius: 6px 0 0 6px;
            padding: 14px 9px;
            cursor: pointer;
            z-index: 10000;
            box-shadow: -2px 0 8px rgba(59,79,191,0.4);
            writing-mode: vertical-rl;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.2px;
            transition: background 0.15s;
        ">Co-Pilot</button>

        <script>
        (function() {
            const BASE    = <?= json_encode($copilotBase) ?>;
            const SECRET  = <?= json_encode($secret) ?>;
            let currentPid  = null;
            let sessionId   = 'sess_' + Math.random().toString(36).substr(2, 12);
            let panelOpen   = false;

            /* ──────────────────────────────────────────────────────
               DOM TWEAKS — run after the page has fully rendered
            ────────────────────────────────────────────────────── */
            function applyDomTweaks() {
                // 1. Rename "Finder" → "Patients" in the nav
                //    OpenEMR renders menu labels via Knockout.js data-bind="text:label"
                //    and also in plain anchor text — catch both.
                document.querySelectorAll(
                    '#mainMenu .nav-link, #mainMenu .dropdown-toggle, ' +
                    '#mainMenu a, .navbar a'
                ).forEach(function(el) {
                    if (el.textContent.trim() === 'Finder') {
                        // Preserve child elements (icons etc); only swap text nodes
                        el.childNodes.forEach(function(node) {
                            if (node.nodeType === Node.TEXT_NODE &&
                                node.textContent.trim() === 'Finder') {
                                node.textContent = node.textContent.replace('Finder', 'Patients');
                            }
                        });
                    }
                });

                // 2. Dropdown z-index fix — iframes sit above Bootstrap dropdowns.
                //    Temporarily lower iframe pointer-events when any dropdown opens.
                document.addEventListener('show.bs.dropdown', function() {
                    document.querySelectorAll('iframe').forEach(function(f) {
                        f._prevPE = f.style.pointerEvents;
                        f.style.pointerEvents = 'none';
                    });
                });
                document.addEventListener('hide.bs.dropdown', function() {
                    document.querySelectorAll('iframe').forEach(function(f) {
                        f.style.pointerEvents = f._prevPE || '';
                    });
                });

                // 3. Improve patient search UX — label the search input placeholder
                var searchBox = document.getElementById('anySearchBox');
                if (searchBox) {
                    var inp = searchBox.querySelector('input[type="text"]');
                    if (inp && !inp.placeholder) {
                        inp.placeholder = 'Search patients…';
                    }
                }

                // 4. Add subtle separator between nav sections
                var navbarNav = document.querySelector('#mainMenu .navbar-nav');
                if (navbarNav) {
                    navbarNav.style.gap = '2px';
                }
            }

            // Run tweaks once DOM is ready, and again after a short delay
            // to catch Knockout.js-rendered elements
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', function() {
                    applyDomTweaks();
                    setTimeout(applyDomTweaks, 800);
                    setTimeout(applyDomTweaks, 2000);
                });
            } else {
                applyDomTweaks();
                setTimeout(applyDomTweaks, 800);
                setTimeout(applyDomTweaks, 2000);
            }

            /* ──────────────────────────────────────────────────────
               PATIENT DETECTION
            ────────────────────────────────────────────────────── */
            function pollPatient() {
                var pid = null;
                var name = null;
                try {
                    /* Read directly from OpenEMR's Knockout view model — works in
                       both the tabbed frame (app_view_model in scope) and any
                       child frame (window.top.app_view_model). */
                    var vm = (typeof app_view_model !== 'undefined')
                        ? app_view_model
                        : (window.top && window.top.app_view_model ? window.top.app_view_model : null);
                    if (vm && vm.application_data.patient()) {
                        var pt = vm.application_data.patient();
                        pid  = parseInt(pt.pid(), 10) || null;
                        name = pt.pname ? pt.pname() : null;
                    }
                } catch (e) {}

                if (pid && pid !== currentPid) {
                    currentPid = pid;
                    name = name || ('Patient #' + pid);
                    document.getElementById('copilot-patient-name').textContent = name;

                    var strip = document.getElementById('copilot-context-strip');
                    strip.textContent = '📋 ' + name;
                    strip.style.display = 'block';

                    sessionId = 'sess_' + Math.random().toString(36).substr(2, 12);
                    resetMessages(
                        '<div style="font-size:28px;margin-bottom:10px;">✅</div>' +
                        '<strong style="color:#1A2733;">' + escapeHtml(name) + '</strong><br>' +
                        '<span style="color:#4A5E6D;font-size:12px;">' +
                        'Chart loaded. Click <strong>⚡ Pre-Visit Briefing</strong> or ask a question.</span>'
                    );
                } else if (!pid && currentPid !== null) {
                    currentPid = null;
                    document.getElementById('copilot-patient-name').textContent = '';
                    document.getElementById('copilot-context-strip').style.display = 'none';
                    resetMessages(
                        '<div style="font-size:28px;margin-bottom:10px;">🩺</div>' +
                        '<strong style="color:#1A2733;">Clinical Co-Pilot</strong><br>' +
                        '<span style="color:#4A5E6D;">Open a patient chart to begin.</span>'
                    );
                }
            }

            function resetMessages(innerHtml) {
                var el = document.getElementById('copilot-messages');
                el.innerHTML = '<div class="cp-placeholder" style="' +
                    'color:#4A5E6D;font-size:12px;text-align:center;' +
                    'padding:28px 12px;background:#fff;border-radius:8px;' +
                    'border:1px dashed #C9D5E0;margin-top:8px;">' +
                    innerHtml + '</div>';
            }

            /* ──────────────────────────────────────────────────────
               PANEL CONTROLS
            ────────────────────────────────────────────────────── */
            window.copilotToggle = function() {
                panelOpen = !panelOpen;
                document.getElementById('copilot-panel').style.transform =
                    panelOpen ? 'translateX(0)' : 'translateX(380px)';
                document.getElementById('copilot-toggle-btn').style.right =
                    panelOpen ? '380px' : '0';
            };

            window.copilotBriefing = function() {
                if (!currentPid) { alert('Please open a patient chart first.'); return; }
                sendMessage(
                    'Give me a pre-visit briefing for today\'s appointment. ' +
                    'Include active medications, recent encounter summary, latest vitals, ' +
                    'any pending items from the last visit, and chart gaps.'
                );
            };

            window.copilotGaps = function() {
                if (!currentPid) { alert('Please open a patient chart first.'); return; }
                sendMessage('What is missing or incomplete in this patient\'s chart?');
            };

            window.copilotSend = function() {
                var input = document.getElementById('copilot-input');
                var q = input.value.trim();
                if (!q) return;
                if (!currentPid) { alert('Please open a patient chart first.'); return; }
                input.value = '';
                sendMessage(q);
            };

            window.copilotIngestFile = function(input) {
                var file = input.files[0];
                if (!file) return;
                if (!currentPid) { alert('Please open a patient chart first.'); input.value = ''; return; }
                if (!panelOpen) copilotToggle();

                // Ask user for doc type
                var docType = null;
                var name = file.name.toLowerCase();
                if (name.includes('lab') || name.includes('result')) {
                    docType = 'lab_pdf';
                } else if (name.includes('intake') || name.includes('form')) {
                    docType = 'intake_form';
                } else {
                    var choice = confirm(
                        'Is this a lab result PDF?\n\nOK = Lab Result\nCancel = Intake Form'
                    );
                    docType = choice ? 'lab_pdf' : 'intake_form';
                }

                addBubble('physician', '📎 Uploaded: ' + file.name + ' (' + docType.replace('_', ' ') + ')');
                var responseBubble = addBubble('copilot', '');
                var statusEl = document.createElement('div');
                statusEl.style.cssText = 'color:#4A5E6D;font-size:11px;font-style:italic;margin-bottom:4px;';
                statusEl.textContent = '⋯ Extracting data from document…';
                responseBubble.appendChild(statusEl);
                var textEl = document.createElement('div');
                textEl.style.lineHeight = '1.55';
                responseBubble.appendChild(textEl);

                var formData = new FormData();
                formData.append('file', file);
                formData.append('doc_type', docType);
                formData.append('pid', currentPid);

                fetch(BASE + '/v2/ingest', {
                    method: 'POST',
                    headers: {'X-Copilot-Secret': SECRET},
                    body: formData,
                }).then(function(res) {
                    if (res.status === 401) {
                        statusEl.remove();
                        textEl.style.color = '#B45309';
                        textEl.textContent =
                            '⚠ Authentication failed — COPILOT_SECRET mismatch. ' +
                            'Ensure the secret in copilot/.env matches the OpenEMR module config.';
                        throw new Error('handled');
                    }
                    return res.json();
                }).then(function(data) {
                    statusEl.remove();
                    if (data.detail) {
                        textEl.style.color = '#B45309';
                        textEl.textContent = '⚠ ' + data.detail;
                        return;
                    }
                    var extracted = data.extracted || {};
                    var lines = [];
                    if (docType === 'lab_pdf') {
                        lines.push('<strong>Lab Result Extracted</strong>');
                        if (extracted.test_name) lines.push('Test: ' + escapeHtml(extracted.test_name));
                        if (extracted.value) lines.push('Value: ' + escapeHtml(extracted.value) + (extracted.unit ? ' ' + escapeHtml(extracted.unit) : ''));
                        if (extracted.reference_range) lines.push('Reference: ' + escapeHtml(extracted.reference_range));
                        if (extracted.collection_date) lines.push('Collected: ' + escapeHtml(extracted.collection_date));
                        if (extracted.abnormal_flag) lines.push('<span style="color:#B45309;">⚠ Abnormal</span>');
                        if (extracted.source_citation) {
                            var cit = extracted.source_citation;
                            lines.push('<span style="font-size:10px;color:#4A5E6D;font-style:italic;">' +
                                '(source: ' + escapeHtml(cit.source_type) + ' / ' + escapeHtml(cit.source_id) + ', ' + escapeHtml(cit.page_or_section) + ')</span>');
                        }
                    } else {
                        lines.push('<strong>Intake Form Extracted</strong>');
                        if (extracted.chief_concern) lines.push('Chief concern: ' + escapeHtml(extracted.chief_concern));
                        if (extracted.demographics && extracted.demographics.name) lines.push('Patient: ' + escapeHtml(extracted.demographics.name));
                        if (extracted.medications && extracted.medications.length) lines.push('Medications: ' + extracted.medications.map(escapeHtml).join(', '));
                        if (extracted.allergies && extracted.allergies.length) lines.push('Allergies: ' + extracted.allergies.map(escapeHtml).join(', '));
                        if (extracted.source_citation) {
                            var cit = extracted.source_citation;
                            lines.push('<span style="font-size:10px;color:#4A5E6D;font-style:italic;">' +
                                '(source: ' + escapeHtml(cit.source_type) + ' / ' + escapeHtml(cit.source_id) + ', ' + escapeHtml(cit.page_or_section) + ')</span>');
                        }
                    }
                    lines.push('<span style="font-size:10px;color:#22A86E;">✓ Data imported to chart</span>');
                    textEl.innerHTML = lines.join('<br>');

                    // Overlay button — fetch annotated PNG from /v2/overlay when clicked
                    var docId = data.doc_id;
                    if (docId) {
                        var overlayBtn = document.createElement('button');
                        overlayBtn.textContent = '🔍 View bounding-box overlay';
                        overlayBtn.style.cssText =
                            'margin-top:8px;font-size:10px;background:#EBF4FB;border:1px solid #A8C8E8;' +
                            'color:#2E6B9E;padding:3px 8px;border-radius:4px;cursor:pointer;' +
                            'display:block;width:100%;text-align:left;';
                        var overlayWrap = document.createElement('div');
                        overlayWrap.style.cssText = 'margin-top:6px;display:none;';
                        var overlayImg = document.createElement('img');
                        overlayImg.style.cssText =
                            'width:100%;border-radius:4px;border:1px solid #C9D5E0;display:block;';
                        overlayImg.alt = 'Bounding-box overlay — extracted fields highlighted';
                        overlayWrap.appendChild(overlayImg);
                        responseBubble.appendChild(overlayBtn);
                        responseBubble.appendChild(overlayWrap);

                        overlayBtn.onclick = function() {
                            if (overlayWrap.style.display === 'none') {
                                if (!overlayImg.dataset.loaded) {
                                    overlayBtn.textContent = '⋯ Loading overlay…';
                                    fetch(BASE + '/v2/overlay/' + encodeURIComponent(docId) + '/0', {
                                        headers: {'X-Copilot-Secret': SECRET}
                                    }).then(function(res) {
                                        if (!res.ok) throw new Error('HTTP ' + res.status);
                                        return res.blob();
                                    }).then(function(blob) {
                                        overlayImg.src = URL.createObjectURL(blob);
                                        overlayImg.dataset.loaded = '1';
                                        overlayWrap.style.display = 'block';
                                        overlayBtn.textContent = '🔍 Hide overlay';
                                        document.getElementById('copilot-messages').scrollTop = 99999;
                                    }).catch(function() {
                                        overlayBtn.textContent = '⚠ Overlay unavailable';
                                    });
                                } else {
                                    overlayWrap.style.display = 'block';
                                    overlayBtn.textContent = '🔍 Hide overlay';
                                }
                            } else {
                                overlayWrap.style.display = 'none';
                                overlayBtn.textContent = '🔍 View bounding-box overlay';
                            }
                        };
                    }

                    document.getElementById('copilot-messages').scrollTop = 99999;
                }).catch(function(err) {
                    if (err && err.message === 'handled') return;
                    statusEl.remove();
                    textEl.style.color = '#B45309';
                    diagnoseCopilotError(textEl);
                });
                input.value = '';
            };

            window.copilotClear = function() {
                if (!currentPid) return;
                fetch(BASE + '/clear', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json', 'X-Copilot-Secret': SECRET},
                    body: JSON.stringify({session_id: sessionId})
                });
                sessionId = 'sess_' + Math.random().toString(36).substr(2, 12);
                var name = document.getElementById('copilot-patient-name').textContent;
                resetMessages(
                    '<span style="color:#22A86E;font-size:18px;">✓</span> ' +
                    'Conversation cleared.<br>' +
                    '<span style="color:#4A5E6D;font-size:12px;">Ask a new question about ' +
                    escapeHtml(name) + '.</span>'
                );
            };

            /* ──────────────────────────────────────────────────────
               MESSAGING
            ────────────────────────────────────────────────────── */
            function sendMessage(question) {
                if (!panelOpen) copilotToggle();

                addBubble('physician', question);
                var responseBubble = addBubble('copilot', '');
                var statusEl = document.createElement('div');
                statusEl.style.cssText =
                    'color:#4A5E6D;font-size:11px;font-style:italic;margin-bottom:4px;' +
                    'display:flex;align-items:center;gap:6px;';
                statusEl.innerHTML = '<span class="cp-spinner">⋯</span><span class="cp-status-text"></span>';
                responseBubble.insertBefore(statusEl, responseBubble.firstChild);
                var statusText = statusEl.querySelector('.cp-status-text');
                var textEl = document.createElement('div');
                textEl.style.lineHeight = '1.55';
                responseBubble.appendChild(textEl);

                fetch(BASE + '/chat', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json', 'X-Copilot-Secret': SECRET},
                    body: JSON.stringify({
                        session_id: sessionId,
                        pid: currentPid,
                        question: question
                    })
                }).then(function(res) {
                    if (!res.ok) {
                        statusEl.remove();
                        textEl.style.color = '#B45309';
                        if (res.status === 401) {
                            textEl.textContent =
                                '⚠ Authentication failed — COPILOT_SECRET mismatch. ' +
                                'Ensure the secret in copilot/.env matches the OpenEMR module config.';
                        } else {
                            textEl.textContent =
                                '⚠ Service error (HTTP ' + res.status + '). ' +
                                'Run docker logs copilot-service for details.';
                        }
                        return;
                    }
                    var reader  = res.body.getReader();
                    var decoder = new TextDecoder();
                    var buffer  = '';

                    function read() {
                        reader.read().then(function(chunk) {
                            if (chunk.done) return;
                            buffer += decoder.decode(chunk.value, {stream: true});
                            var lines = buffer.split('\n');
                            buffer = lines.pop();

                            lines.forEach(function(line) {
                                if (!line.startsWith('data: ')) return;
                                var data = line.slice(6);
                                if (data.startsWith('status:')) {
                                    statusText.textContent = data.slice(7);
                                } else if (data.startsWith('token:')) {
                                    statusEl.style.display = 'none';
                                    textEl.textContent += data.slice(6);
                                    document.getElementById('copilot-messages').scrollTop = 99999;
                                } else if (data === 'done') {
                                    statusEl.remove();
                                    renderMarkdown(textEl);
                                } else if (data.startsWith('error:')) {
                                    statusEl.remove();
                                    textEl.style.color = '#B45309';
                                    textEl.textContent = '⚠ ' + data.slice(6);
                                }
                            });
                            read();
                        });
                    }
                    read();
                }).catch(function() {
                    statusEl.remove();
                    textEl.style.color = '#B45309';
                    diagnoseCopilotError(textEl);
                });
            }

            function addBubble(role, text) {
                var msgs = document.getElementById('copilot-messages');
                // Clear placeholder on first real message
                var ph = msgs.querySelector('.cp-placeholder');
                if (ph) ph.remove();

                var bubble = document.createElement('div');
                if (role === 'physician') {
                    bubble.style.cssText =
                        'background:#EEF0FB;padding:9px 12px;border-radius:10px 10px 2px 10px;' +
                        'align-self:flex-end;max-width:88%;font-size:12.5px;' +
                        'border:1px solid #D0D6F5;color:#1A2733;';
                } else {
                    bubble.style.cssText =
                        'background:#fff;padding:10px 12px;border-radius:10px 10px 10px 2px;' +
                        'align-self:flex-start;max-width:100%;font-size:12.5px;' +
                        'border:1px solid #C9D5E0;color:#1A2733;' +
                        'box-shadow:0 1px 3px rgba(0,0,0,0.06);';
                }
                if (text) bubble.textContent = text;
                msgs.appendChild(bubble);
                msgs.scrollTop = 99999;
                return bubble;
            }

            function renderMarkdown(el) {
                var html = escapeHtml(el.textContent);
                // Bold
                html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
                // Source citations — style with subdued colour
                html = html.replace(/\(source:([^)]+)\)/g,
                    '<span style="font-size:10px;color:#4A5E6D;font-style:italic;">' +
                    '(source:$1)</span>');
                // Bullet points
                html = html.replace(/\n[-•] /g, '\n<span style="color:#0E8A8A;">•</span> ');
                // Line breaks
                html = html.replace(/\n/g, '<br>');
                el.innerHTML = html;
            }

            function escapeHtml(s) {
                return String(s)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;');
            }

            /* ──────────────────────────────────────────────────────
               ERROR DIAGNOSIS
               Calls /health (no auth) to determine the specific
               cause of a connection or service failure.
            ────────────────────────────────────────────────────── */
            function diagnoseCopilotError(textEl) {
                fetch(BASE + '/health')
                    .then(function(r) { return r.json(); })
                    .then(function(h) {
                        if (h.checks && !h.checks.anthropic_key_set) {
                            textEl.innerHTML =
                                '⚠ <strong>ANTHROPIC_API_KEY</strong> is not set.<br>' +
                                '<span style="font-size:11px;">Add it to <code>copilot/.env</code> ' +
                                'and run <code>docker compose restart copilot-service</code>.</span>';
                        } else if (h.checks && !h.checks.cohere_key_set) {
                            textEl.innerHTML =
                                '⚠ <strong>COHERE_API_KEY</strong> is not set.<br>' +
                                '<span style="font-size:11px;">Add it to <code>copilot/.env</code> ' +
                                'and run <code>docker compose restart copilot-service</code>.</span>';
                        } else {
                            textEl.innerHTML =
                                '⚠ Service error. Run ' +
                                '<code>docker logs copilot-service</code> to investigate.';
                        }
                    })
                    .catch(function() {
                        textEl.innerHTML =
                            '⚠ Co-Pilot service is unreachable.<br>' +
                            '<span style="font-size:11px;">Start it with ' +
                            '<code>docker compose up</code> in ' +
                            '<code>docker/development-easy/</code>.</span>';
                    });
            }

            // Poll for current patient every 3 seconds
            pollPatient();
            setInterval(pollPatient, 3000);
        })();
        </script>
        <?php
    }
}
