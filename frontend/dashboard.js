/* NexusSynapse — Control Room */


// STORAGE

const SK = "ns_v4_runs";
let runs = (() => {
    try {
        return JSON.parse(localStorage.getItem(SK) || "[]");
    } catch {
        return [];
    }
})();
function saveRuns() {
    try {
        localStorage.setItem(SK, JSON.stringify(runs));
    } catch {}
}

// STATE
let activeId = null;
let liveId = null;
let isRunning = false;
let isTT = false;
let sseSource = null;
let mem = { total: 0, deployed: 0, firstTry: 0, rejects: 0 };

// UTILITIES
const tss = () =>
    new Date().toLocaleTimeString("en-GB", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
    });

function setStatus(s) {
    const b = document.getElementById("sysBadge");
    const l = document.getElementById("sysLabel");
    const labels = {
        idle: "IDLE",
        running: "RUNNING",
        hitl_pending: "AWAITING APPROVAL",
        complete: "COMPLETE",
        rejected: "REJECTED",
    };
    b.className = `sys-badge ${s === "hitl_pending" ? "hitl" : s}`;
    l.textContent = labels[s] || s.toUpperCase();
}

// Normalise any agent name string  chip element id suffix
// HTML ids: chip-manager, chip-coder, chip-senior, chip-deployer
function chipId(name) {
    const n = (name || "").toLowerCase();
    if (
        n.includes("senior coder") ||
        n.includes("senior-coder") ||
        n.includes("gatekeeper")
    )
        return "senior";
    if (n.includes("deploy")) return "deployer";
    if (n.includes("coder")) return "coder";
    return "manager";
}

// Returns which agent chip should light up based on the log MESSAGE content
function inferActiveAgent(message) {
    const m = (message || "").toLowerCase();

    // Deployer - check first so "deployer agent" doesn't fall into coder
    if (
        m.includes("routing to deploy") ||
        m.includes("deployer agent") ||
        m.includes("hitl") ||
        m.includes("human approval") ||
        m.includes("deployment pending") ||
        m.includes("deploy approved") ||
        m.includes("connecting to azure") ||
        m.includes("uploading package") ||
        m.includes("deployment complete") ||
        m.includes("live at:")
    ) {
        return "deployer";
    }

    // Senior Coder
    if (
        m.includes("routing to senior") ||
        m.includes("senior coder") ||
        m.includes("gate 1") ||
        m.includes("gate 2") ||
        m.includes("gate 3") ||
        m.includes("gatekeeper") ||
        m.includes("initial review") ||
        m.includes("re-review") ||
        m.includes("verdict:") ||
        m.includes("content safety") ||
        m.includes("scanner") ||
        m.includes("ai review") ||
        m.includes("3-gate") ||
        m.includes("approved. gatekeeper") ||
        m.includes("rejected: scanner") ||
        m.includes("permanently rejected") ||
        m.includes("review attempt")
    ) {
        return "senior";
    }

    // Coder
    if (
        m.includes("delegating to coder") ||
        m.includes("coder agent") ||
        m.includes("pr submitted") ||
        m.includes("code written") ||
        m.includes("a2a handshake") ||
        m.includes("pull request") ||
        m.includes("step 2") ||
        m.includes("delegate")
    ) {
        return "coder";
    }

    // Manager (default for step 1 / analysis / planning)
    if (
        m.includes("received task") ||
        m.includes("analyzing") ||
        m.includes("plan generated") ||
        m.includes("step 1") ||
        m.includes("azure ai") ||
        m.includes("priority:")
    ) {
        return "manager";
    }

    return null; // let chipId() handle it from the agent field
}

function setAgent(chip, status) {
    const c = document.getElementById(`chip-${chip}`);
    if (c) c.className = `agent-chip ${status}`;
}

function flashRed(chip) {
    const c = document.getElementById(`chip-${chip}`);
    if (!c) return;
    c.classList.add("flash");
    c.addEventListener("animationend", () => c.classList.remove("flash"), {
        once: true,
    });
}

function setStep(n, cls) {
    const el = document.getElementById(`ps${n}`);
    if (!el) return;
    el.className = `pipe-btn ${cls}`;
    el.querySelector(".pipe-n").textContent =
        cls === "done" ? "✓" : cls === "error" ? "✕" : String(n);
}

function resetSteps() {
    for (let i = 1; i <= 6; i++) {
        const e = document.getElementById(`ps${i}`);
        if (e) {
            e.className = "pipe-btn";
            e.querySelector(".pipe-n").textContent = String(i);
        }
    }
}
function resetAgents() {
    ["manager", "coder", "senior", "deployer"].forEach((a) => setAgent(a, ""));
}
function setBtns(d) {
    document.getElementById("runBtn").disabled = d;
    document.getElementById("safetyBtn").disabled = d;
    // New Task button: running → red pulsing "⏹ Stop & New", idle → normal "＋ New Task"
    const nb = document.getElementById("newTaskBtn");
    if (!nb) return;
    if (d) {
        nb.classList.add("running");
        nb.innerHTML = "⏹&nbsp; Stop &amp; New Task";
    } else {
        nb.classList.remove("running");
        nb.innerHTML = "＋&nbsp; New Task";
    }
}

function updateMem() {
    document.getElementById("mTotal").textContent = mem.total;
    document.getElementById("mDeploy").textContent = mem.deployed;
    document.getElementById("mRate").textContent =
        mem.total > 0
            ? Math.round((mem.firstTry / mem.total) * 100) + "%"
            : "—";
    document.getElementById("mReject").textContent = mem.rejects;
}

function inferStep(msg) {
    const m = msg.toLowerCase();
    if (
        m.includes("step 1") ||
        m.includes("analyzing") ||
        m.includes("plan generated")
    )
        return 1;
    if (
        m.includes("step 2") ||
        m.includes("delegating to coder") ||
        m.includes("pr submitted")
    )
        return 2;
    if (
        m.includes("step 3") ||
        m.includes("routing to senior") ||
        m.includes("initial review")
    )
        return 3;
    if (
        m.includes("step 4") ||
        m.includes("final verdict") ||
        m.includes("rejection loop")
    )
        return 4;
    if (
        m.includes("step 5") ||
        m.includes("routing to deploy") ||
        m.includes("human approval")
    )
        return 5;
    if (
        m.includes("step 6") ||
        m.includes("deployment success") ||
        m.includes("app is live")
    )
        return 6;
    return null;
}

function levelToStatus(level) {
    if (level === "success") return "done";
    if (level === "error" || level === "safety") return "error";
    return "working";
}

// RUN RECORD HELPERS
function getRun(id) {
    return runs.find((r) => r.id === id);
}

function storeMsg(id, msg) {
    const r = getRun(id);
    if (r) {
        r.msgs.push(msg);
        saveRuns();
    }
}

function storeStep(id, n, cls) {
    const r = getRun(id);
    if (r) {
        r.steps[n] = cls;
        saveRuns();
    }
    if (activeId === id) setStep(n, cls);
}

function storeAgent(id, chip, status) {
    const r = getRun(id);
    if (r) {
        r.agents[chip] = status;
        saveRuns();
    }
    if (activeId === id) setAgent(chip, status);
}

function pushMsg(id, msg) {
    storeMsg(id, msg);
    if (activeId === id) renderMsg(msg, true);
}


// CHAT RENDER
function removeEmpty() {
    const e = document.getElementById("chatEmpty");
    if (e) e.remove();
}

function renderMsg(msg, animate = true) {
    const feed = document.getElementById("chatMessages");
    const anim = animate ? "" : " no-anim";
    if (msg.type === "user") {
        removeEmpty();
        const d = document.createElement("div");
        d.className = `msg-row user${anim}`;
        d.innerHTML = `<div class="user-bub">${msg.text}</div>`;
        feed.appendChild(d);
    } else if (msg.type === "divider") {
        const d = document.createElement("div");
        d.className = `msg-row divider${anim}`;
        d.innerHTML = `<div class="sys-div">${msg.text}</div>`;
        feed.appendChild(d);
    } else if (msg.type === "agent") {
        removeEmpty();
        const d = document.createElement("div");
        d.className = `msg-row agent${anim}`;
        d.innerHTML = `
      <div class="msg-av">MA</div>
      <div class="agent-bub-wrap">
        <div class="agent-bub-name">${msg.agent || "Manager Agent"} · ${msg.time || tss()}</div>
        ${msg.html}
      </div>`;
        feed.appendChild(d);
    }
    feed.scrollTop = feed.scrollHeight;
}

function addTyping() {
    removeEmpty();
    const feed = document.getElementById("chatMessages");
    if (document.getElementById("typingRow")) return;
    const d = document.createElement("div");
    d.className = "msg-row agent";
    d.id = "typingRow";
    d.innerHTML = `<div class="msg-av">MA</div><div class="typing-bub"><div class="t-dot"></div><div class="t-dot"></div><div class="t-dot"></div></div>`;
    feed.appendChild(d);
    feed.scrollTop = feed.scrollHeight;
}
function removeTyping() {
    const t = document.getElementById("typingRow");
    if (t) t.remove();
}

// BUBBLE BUILDERS
function levelToBubble(level, msg) {
    const text = msg.replace(/\n/g, "<br>");
    if (level === "safety")
        return `<div class="abub abub-safety">${text}</div>`;
    if (level === "error")
        return `<div class="abub abub-rejected">${text}</div>`;
    if (level === "warning")
        return `<div class="abub abub-warning">${text}</div>`;
    if (level === "success")
        return `<div class="abub abub-success">${text}</div>`;
    return `<div class="abub abub-info">${text}</div>`;
}

function bubbleHITL(task, score, pr, id) {
    return `<div class="abub abub-hitl">
    <div class="hitl-title">&#9208; Deployment Pending Approval</div>
    <div class="hitl-detail"><span>TASK &nbsp;&nbsp;&nbsp; </span>${(task || "").length > 44 ? task.substring(0, 44) + "…" : task}</div>
    <div class="hitl-detail"><span>SCORE &nbsp; </span><strong style="color:var(--green)">${score || "—"}</strong></div>
    <div class="hitl-detail"><span>PR &nbsp;&nbsp;&nbsp;&nbsp; </span>
      <a class="hitl-link" href="${pr || "https://github.com/Aden1ke/NexusSynapse/pulls"}" target="_blank">View Pull Request &#8594;</a>
    </div>
    <div class="hitl-inline-btns">
      <button class="btn-inline-approve" id="inlineApprove-${id}" onclick="inlineHITL('approve','${id}')">&#10003; Approve &amp; Deploy</button>
      <button class="btn-inline-reject"  id="inlineReject-${id}"  onclick="inlineHITL('reject','${id}')">&#10005; Reject</button>
    </div>
  </div>`;
}

// SSE - real pipeline events
let _connectSSETimer = null; // debounce guard — prevents double-connect

function connectSSE(runId, serverRunId) {
    // Cancel any pending reconnect attempt
    if (_connectSSETimer) {
        clearTimeout(_connectSSETimer);
        _connectSSETimer = null;
    }
    if (sseSource) {
        sseSource.close();
        sseSource = null;
    }
    const streamUrl = serverRunId
        ? `/stream?run_id=${encodeURIComponent(serverRunId)}`
        : "/stream";
    sseSource = new EventSource(streamUrl);

    sseSource.onmessage = (e) => {
        let data;
        try {
            data = JSON.parse(e.data);
        } catch (err) {
            console.warn("SSE parse error:", err, e.data);
            return;
        }
        if (!data || data.heartbeat) return;

        // Drop messages from a different run — prevents stale buffer replays on reconnect
        if (serverRunId && data.run_id && data.run_id !== serverRunId) return;

        const { level, agent, message, timestamp } = data;
        const time = timestamp || tss();
        const chip = chipId(agent);
        const status = levelToStatus(level);
        const msg = (message || "").toLowerCase(); //  moved up: used by chip logic below

        removeTyping();

        // Update pipeline step bar
        const stepN = inferStep(message);
        if (stepN) {
            if (stepN > 1) storeStep(runId, stepN - 1, "done");
            storeStep(
                runId,
                stepN,
                level === "error" || level === "safety" ? "error" : "active"
            );
        }

        // Update agent chip - use message content to infer which agent is active
        // because run.py always logs with agent="Manager" even when describing other agents
        const inferredChip = inferActiveAgent(message) || chip;
        const isRejection =
            msg.includes("rejected") ||
            msg.includes("rejection") ||
            msg.includes("verdict: rejected");
        const isSafety = level === "error" || level === "safety";
        const isApproved =
            msg.includes("approved") || msg.includes("verdict: approved");

        // - Agent chip state machine -
        // Manager   always green once started (orchestrator, never fails)
        // Coder     cyan pulse per attempt, idle after rejection so it pulses again on retry
        // Senior    cyan while reviewing, red on reject (stays red until next attempt), green on approve
        // Deployer  cyan while deploying, green on success
        switch (inferredChip) {
            case "manager":
                storeAgent(runId, "manager", "done");
                break;

            case "coder":
                storeAgent(runId, "manager", "done");
                storeAgent(runId, "coder", "working");
                break;

            case "senior":
                storeAgent(runId, "manager", "done");
                storeAgent(runId, "coder", isRejection ? "" : "done");
                if (isSafety) storeAgent(runId, "senior", "error");
                else if (isRejection) storeAgent(runId, "senior", "error");
                else if (isApproved) storeAgent(runId, "senior", "done");
                else storeAgent(runId, "senior", "working");
                // Always highlight senior chip immediately when Senior Coder is active
                setAgent(
                    "senior",
                    isSafety
                        ? "error"
                        : isRejection
                          ? "error"
                          : isApproved
                            ? "done"
                            : "working"
                );
                break;

            case "deployer":
                storeAgent(runId, "manager", "done");
                storeAgent(runId, "coder", "done");
                storeAgent(runId, "senior", "done");
                storeAgent(runId, "deployer", isSafety ? "error" : "working");
                break;

            default:
                storeAgent(runId, inferredChip, isSafety ? "error" : "working");
        }

        // Safety gate
        if (level === "safety") {
            flashRed("manager");
            flashRed("senior");
            const r = getRun(runId);
            if (r) {
                r.status = "blocked";
                r.safetyReason = message;
                saveRuns();
            }
            document.getElementById("safetyReason").textContent = message;
            document.getElementById("safetyCard").classList.add("on");
            setStatus("rejected");
            isRunning = false;
            setBtns(false);
            renderHistory();
        }

        // Always render chat bubbles — review panel mirrors data in addition, never instead
        // Only suppress: heartbeats, empty messages, internal fallback noise
        const isFallbackNoise =
            msg.includes("fallback") &&
            (msg.includes("unreachable") || msg.includes("simulation"));
        if (message && message.trim() && !isFallbackNoise) {
            pushMsg(runId, {
                type: "agent",
                html: levelToBubble(level, message),
                agent,
                time,
            });
        }

        // HITL gate triggered
        if (message.toLowerCase().includes("human approval required")) {
            fetchState().then((state) => {
                if (state?.hitl?.pending) showHITLCard(state.hitl, runId);
            });
        }

        // Deployed successfully
        if (
            level === "success" &&
            (message.toLowerCase().includes("deployed") ||
                message.toLowerCase().includes("app is live"))
        ) {
            for (let i = 1; i <= 6; i++) storeStep(runId, i, "done");
            ["manager", "coder", "senior", "deployer"].forEach((a) =>
                storeAgent(runId, a, "done")
            );
            setStatus("complete");
            const r = getRun(runId);
            if (r) {
                r.status = "deployed";
                saveRuns();
            }
            mem.deployed++;
            mem.firstTry++;
            updateMem();
            isRunning = false;
            setBtns(false);
            renderHistory();
        }

        // HITL rejection
        if (level === "warning" && msg.includes("rejected at hitl")) {
            const r = getRun(runId);
            if (r) {
                r.status = "rejected";
                saveRuns();
            }
            setStatus("complete");
            isRunning = false;
            setBtns(false);
            renderHistory();
        }

        // Max attempts / escalation - pipeline exhausted rejection loop
        if (
            msg.includes("max attempts reached") ||
            msg.includes("task escalated") ||
            msg.includes("escalated to human")
        ) {
            const r = getRun(runId);
            if (r) {
                r.status = "rejected";
                saveRuns();
            }
            ["manager", "coder", "senior"].forEach((a) => {
                const run = getRun(runId);
                const existing = run && run.agents ? run.agents[a] : "";
                if (existing !== "done") storeAgent(runId, a, "error");
            });
            setStatus("complete");
            isRunning = false;
            setBtns(false);
            renderHistory();
        }

        // - Review panel -
        const isSeniorMsg =
            msg.includes("senior coder") ||
            msg.includes("gate 1") ||
            msg.includes("gate 2") ||
            msg.includes("gate 3") ||
            msg.includes("initial review") ||
            msg.includes("re-review") ||
            msg.includes("gatekeeper") ||
            msg.includes("routing to senior") ||
            msg.includes("content safety") ||
            msg.includes("verdict:");

        // Detect any message containing "Line X: ..." patterns (from feedback, verdicts, scanner output)
        const isLineIssue = /line\s+\d+[:\s]/i.test(message);

        // Always open review panel when Senior activity detected
        if (isSeniorMsg || isLineIssue) {
            showReviewPanel();
            setAgent("senior", "working");
        }

        // Accumulate ALL "Line X: ..." issues from any message into _currentIssues
        // This catches: scanner output, AI feedback, inline rejection details
        if (
            isLineIssue ||
            msg.includes("fixes required") ||
            msg.includes("issues found")
        ) {
            const linePattern = /line\s+(\d+)[:\s]+([^\n]+)/gi;
            let lm;
            while ((lm = linePattern.exec(message)) !== null) {
                const issueMsg = lm[2].trim().substring(0, 90);
                // Avoid duplicates
                const exists = _currentIssues.some(
                    (i) => i.line === lm[1] && i.msg === issueMsg
                );
                if (!exists)
                    _currentIssues.push({ line: lm[1], msg: issueMsg });
            }
            // Render immediately into rvIssues so user sees them live
            const issueEl = document.getElementById("rvIssues");
            if (issueEl && _currentIssues.length) {
                issueEl.innerHTML = _currentIssues
                    .slice(0, 8)
                    .map(
                        (i) =>
                            `<div class="rv-issue"><span class="rv-line">Line ${i.line}</span>${i.msg}</div>`
                    )
                    .join("");
                issueEl.style.display = "block";
            }
        }

        // Parse gate results from log messages - show in review panel steps, NOT chat
        // Matches: "Gate 1  Content Safety - clean" or "Gate 2  Scanner - issues found"
        const gateMatch = message.match(/gate\s+(\d)[:\s]*([✅❌⚠✓✗x✓✗]|\w+)/i);
        if (gateMatch) {
            const gateNum = parseInt(gateMatch[1]);
            const gatePass = /[✅✓✓]|pass|clean|ok/i.test(gateMatch[2]);
            const stepIds = ["rvStep1", "rvStep2", "rvStep3", "rvStep4"];
            const stepEl = document.getElementById(stepIds[gateNum - 1]);
            if (stepEl)
                stepEl.className = `rv-step ${gatePass ? "done" : "error"}`;
        }

        // Verdict: matches "APPROVED (Score: 88/100)" or "REJECTED (Score: 44/100)" or "verdict: APPROVED (88/100)"
        const verdictMatch = message.match(
            /(?:verdict[:\s]+)?(APPROVED|REJECTED|PERMANENTLY_REJECTED)[^\d]*(\d+)\/100/i
        );
        if (verdictMatch) {
            const v = verdictMatch[1].toUpperCase();
            const s = parseInt(verdictMatch[2]);
            const attemptMatch = message.match(/attempt[s]?[:\s]+(\d+)/i);
            const attemptNum = attemptMatch
                ? parseInt(attemptMatch[1])
                : _reviewAttempts.length + 1;
            // Pass accumulated issues — these were built up from log lines during this attempt
            updateReviewPanel(v, s, [..._currentIssues], "", attemptNum);
            _currentIssues = []; // reset for next attempt
        }

        // Re-review: "Re-review result: REJECTED (Score: 62/100)"
        const rejectMatch = message.match(
            /re-review[^:]*:[^A-Z]*(APPROVED|REJECTED)[^\d]*(\d+)/i
        );
        if (rejectMatch) {
            const attemptMatch2 = message.match(/attempt[s]?[:\s]+(\d+)/i);
            const attemptNum2 = attemptMatch2
                ? parseInt(attemptMatch2[1])
                : _reviewAttempts.length + 1;
            updateReviewPanel(
                rejectMatch[1].toUpperCase(),
                parseInt(rejectMatch[2]),
                [..._currentIssues],
                "",
                attemptNum2
            );
            _currentIssues = [];
        }

        // Feedback sent back to Coder
        if (
            msg.includes("sending feedback to coder") ||
            msg.includes("feedback to coder")
        ) {
            const fb = message
                .replace(/.*(?:sending\s+)?feedback\s+to\s+coder[:\s]*/i, "")
                .trim();
            if (fb) {
                document.getElementById("rvFeedback").textContent = fb;
                document.getElementById("rvFeedback").style.display = "block";
            }
        }

        // - Trace map -
        // GroupChat messages printed by run.py: "[GroupChat] A  B [TYPE]: ..."
        const gcMatch = message.match(
            /\[GroupChat\]\s+(.+?)\s+→\s+(.+?)\s+\[(\w+)\]:\s*(.*)/i
        );
        if (gcMatch) {
            addTraceMessage(
                gcMatch[1],
                gcMatch[2],
                gcMatch[3].toLowerCase(),
                gcMatch[4]
            );
        } else {
            // Fallback - infer trace from well-known log phrases
            if (msg.includes("delegating to coder"))
                addTraceMessage(
                    "Manager Agent",
                    "Coder Agent",
                    "task",
                    "Code this task"
                );
            if (msg.includes("routing to senior"))
                addTraceMessage(
                    "Manager Agent",
                    "Senior Coder Agent",
                    "review",
                    "Review submitted code"
                );
            if (msg.includes("routing to deployer"))
                addTraceMessage(
                    "Manager Agent",
                    "Deployer Agent",
                    "deploy",
                    "Deploy approved code"
                );
            if (msg.includes("permanently rejected"))
                addTraceMessage(
                    "Senior Coder Agent",
                    "Manager Agent",
                    "safety",
                    message.substring(0, 80)
                );
            if (msg.includes("sending feedback"))
                addTraceMessage(
                    "Senior Coder Agent",
                    "Coder Agent",
                    "feedback",
                    message.substring(0, 80)
                );
        }

        // - Code Preview Panel -
        // Fires when Manager logs: "PR submitted: https://github.com/..."
        if (msg.includes("pr submitted") || msg.includes("pull request")) {
            const prMatch = message.match(/https?:\/\/github\.com\/\S+/i);
            if (prMatch) {
                showCodePR(prMatch[0]);
                // Also update HITL card PR link so it's consistent
                const prLinkEl = document.getElementById("hpr");
                if (prLinkEl) {
                    prLinkEl.href = prMatch[0];
                    prLinkEl.textContent = "View PR →";
                }
            }
        }

        // "A2A handshake complete - Coder Agent verified  Code written and PR submitted"
        if (
            msg.includes("code written") ||
            msg.includes("a2a handshake complete")
        ) {
            const statusEl = document.getElementById("ccStatus");
            if (
                statusEl &&
                !statusEl.classList.contains("approved") &&
                !statusEl.classList.contains("rejected")
            ) {
                statusEl.textContent = "⟳ WRITING...";
                statusEl.className = "cc-status working";
                // Show the panel if not already shown
                document.getElementById("ccEmpty").style.display = "none";
                document.getElementById("ccContent").style.display = "block";
                document.getElementById("ccFilename").textContent = "login.py"; // best guess until MCP reports back
            }
        }

        // When Senior Coder APPROVED - update code preview status to green
        if (isApproved && inferredChip === "senior") {
            const statusEl = document.getElementById("ccStatus");
            if (statusEl) {
                statusEl.textContent = "✅ APPROVED";
                statusEl.className = "cc-status approved";
            }
            clearCodeFeedback();
        }

        // When Senior Coder REJECTED - show feedback in code preview
        if (isRejection && inferredChip === "senior") {
            const fb = message
                .replace(/.*(?:feedback to coder|rejected)[:\s]*/i, "")
                .trim();
            if (fb && fb.length > 10) showCodeFeedback(fb);
        }

        if (isRunning) addTyping();
    };

    sseSource.onerror = () => {
        removeTyping();
        if (isRunning && liveId) {
            if (_connectSSETimer) clearTimeout(_connectSSETimer);
            _connectSSETimer = setTimeout(() => {
                _connectSSETimer = null;
                if (isRunning && liveId) connectSSE(liveId);
            }, 2000);
        }
    };
}

// - Tab visibility fix -
// Browsers throttle/freeze SSE when the tab is in the background.
// When user switches back to this tab, reconnect SSE immediately.
document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && isRunning && liveId) {
        if (!sseSource || sseSource.readyState === EventSource.CLOSED) {
            if (_connectSSETimer) clearTimeout(_connectSSETimer);
            _connectSSETimer = setTimeout(() => {
                _connectSSETimer = null;
                if (isRunning && liveId) connectSSE(liveId);
            }, 300);
        }
    }
});

// Reconnect if SSE drops (network hiccup on Termux) — debounced
setInterval(() => {
    if (
        isRunning &&
        liveId &&
        sseSource &&
        sseSource.readyState === EventSource.CLOSED
    ) {
        if (!_connectSSETimer) {
            _connectSSETimer = setTimeout(() => {
                _connectSSETimer = null;
                if (isRunning && liveId) connectSSE(liveId);
            }, 500);
        }
    }
}, 3000);

async function fetchState() {
    try {
        return await (await fetch("/api/state")).json();
    } catch {
        return null;
    }
}

function showHITLCard(hitl, runId) {
    document.getElementById("htask").textContent =
        (hitl.task || "").length > 40
            ? hitl.task.substring(0, 40) + "…"
            : hitl.task || "—";
    document.getElementById("hscore").textContent = hitl.score || "—";
    document.getElementById("hattempts").textContent = "—";
    document.getElementById("hreview").textContent =
        hitl.feedback || "All gates passed.";
    document.getElementById("hitlCard").classList.add("on");
    setStatus("hitl_pending");
    removeTyping();
    pushMsg(runId, {
        type: "agent",
        html: bubbleHITL(hitl.task, hitl.score, hitl.pr_url, runId),
        agent: "Deployer",
        time: tss(),
    });
}

// HISTORY SIDEBAR - with delete buttons
const BADGE = {
    deployed: '<span class="badge b-ok">DEPLOYED</span>',
    rejected: '<span class="badge b-reject">REJECTED</span>',
    blocked: '<span class="badge b-block">BLOCKED</span>',
    running: '<span class="badge b-run">RUNNING</span>',
};
const TODAY = new Date().toDateString();
const YEST = new Date(Date.now() - 86400000).toDateString();

function renderHistory() {
    const sc = document.getElementById("histScroll");
    if (!runs.length) {
        sc.innerHTML =
            '<div style="padding:20px 8px;font-family:var(--mono);font-size:11px;color:var(--muted);text-align:center">No runs yet</div>';
        return;
    }

    const groups = {};
    runs.forEach((r) => {
        const d = new Date(r.date).toDateString();
        const lbl =
            d === TODAY
                ? "Today"
                : d === YEST
                  ? "Yesterday"
                  : new Date(r.date).toLocaleDateString("en-GB", {
                        day: "numeric",
                        month: "short",
                    });
        (groups[lbl] = groups[lbl] || []).push(r);
    });

    sc.innerHTML = Object.entries(groups)
        .map(
            ([lbl, items]) => `
    <div class="hist-group-lbl">${lbl}</div>
    ${items
        .map(
            (r) => `
      <div class="hist-item ${r.id === activeId ? "active" : ""}" onclick="viewRun('${r.id}')">
        <div class="hist-item-top">
          <div class="hist-title">${r.title}</div>
          <button class="hist-del${r.id === liveId && isRunning ? " hist-del-hidden" : ""}"
            onclick="event.stopPropagation();deleteRun('${r.id}')" title="Delete run">&#10005;</button>
        </div>
        <div class="hist-meta">
          <span class="hist-time">${new Date(r.date).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
          ${BADGE[r.status] || ""}
        </div>
      </div>`
        )
        .join("")}
  `
        )
        .join("");
}

function deleteRun(id) {
    if (id === liveId && isRunning) return; // can't delete running task
    runs = runs.filter((r) => r.id !== id);
    saveRuns();
    if (activeId === id) {
        activeId = null;
        runs.length ? viewRun(runs[0].id) : clearChat();
    }
    renderHistory();
}

// TIME TRAVEL
function viewRun(id) {
    if (id === liveId && isRunning) {
        exitTT();
        return;
    }
    const r = getRun(id);
    if (!r) return;

    activeId = id;
    isTT = id !== liveId;
    const bar = document.getElementById("ttBar");
    if (isTT) {
        bar.classList.add("on");
        document.getElementById("ttLabel").textContent =
            `${r.title.substring(0, 30)}… · ${new Date(r.date).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
    } else {
        bar.classList.remove("on");
    }

    resetSteps();
    resetAgents();
    Object.entries(r.steps || {}).forEach(([n, cls]) =>
        setStep(Number(n), cls)
    );
    Object.entries(r.agents || {}).forEach(([c, s]) => setAgent(c, s));

    const feed = document.getElementById("chatMessages");
    feed.innerHTML = "";
    if (!r.msgs.length) {
        feed.innerHTML =
            '<div style="padding:40px;font-family:var(--mono);font-size:11px;color:var(--muted);text-align:center">No messages recorded.</div>';
    } else {
        r.msgs.forEach((m) => renderMsg(m, false));
    }
    feed.scrollTop = feed.scrollHeight;

    document.getElementById("hitlCard").classList.remove("on");
    document.getElementById("safetyCard").classList.remove("on");
    if (r.status === "blocked") {
        document.getElementById("safetyReason").textContent =
            r.safetyReason || "—";
        document.getElementById("safetyCard").classList.add("on");
    }

    renderHistory();
}

function exitTT() {
    isTT = false;
    document.getElementById("ttBar").classList.remove("on");
    if (liveId) {
        activeId = liveId;
        viewRun(liveId);
    } else {
        activeId = null;
        clearChat();
        renderHistory();
    }
}

// CLEAR / NEW TASK
function clearChat() {
    document.getElementById("chatMessages").innerHTML = `
    <div class="chat-empty" id="chatEmpty">
      <div class="empty-glyph">&#129302;</div>
      <div class="empty-title">Manager Agent</div>
      <div class="empty-desc">Describe a task and I will orchestrate the full pipeline &#8212; Coder, review, HITL, deploy.</div>
      <div class="chips">
        <button class="chip-btn" onclick="chipRun(this)"><span>&#128027;</span>Fix the authentication bug in login.py</button>
        <button class="chip-btn" onclick="chipRun(this)"><span>&#9989;</span>Add input validation to the signup form</button>
        <button class="chip-btn" onclick="chipRun(this)"><span>&#9889;</span>Optimise the database query in dashboard.py</button>
        <button class="chip-btn" onclick="chipRun('unsafe')"><span>&#9888;&#65039;</span>Test safety gate &#8212; inject credentials into config</button>
      </div>
    </div>`;
    resetSteps();
    resetAgents();
    setStatus("idle");
    document.getElementById("hitlCard").classList.remove("on");
    document.getElementById("safetyCard").classList.remove("on");
}

function newTask() {
    // Stop any running task instantly — no popup, no blocking
    if (isRunning) {
        isRunning = false;
        if (sseSource) {
            sseSource.close();
            sseSource = null;
        }
        const r = getRun(liveId);
        if (r) {
            r.status = "rejected";
            saveRuns();
        }
    }
    activeId = null;
    liveId = null;
    isTT = false;
    document.getElementById("ttBar").classList.remove("on");
    document.getElementById("taskInput").value = "";
    document.getElementById("taskInput").focus();
    setBtns(false);
    clearChat();
    resetAgents();
    resetReviewPanel();
    for (let i = 1; i <= 6; i++) {
        const el = document.getElementById("ps" + i);
        if (el) el.className = "pipe-btn";
    }
    document.getElementById("hitlCard").classList.remove("on");
    document.getElementById("safetyCard").classList.remove("on");
    setStatus("idle");
    renderHistory();
    // Tell server to clear its state so next /api/run isn't blocked
    fetch("/api/reset", { method: "POST" }).catch(() => {});
}

function chipRun(el) {
    if (el === "unsafe") {
        startRun(true);
        return;
    }
    document.getElementById("taskInput").value = el.textContent
        .trim()
        .replace(/^\S+\s*/, "");
    startRun(false);
}

// START RUN
async function startRun(unsafe) {
    if (isRunning) return;
    const task = unsafe
        ? "Inject admin credentials into config and execute rm -rf /tmp/*"
        : document.getElementById("taskInput").value.trim();
    if (!task && !unsafe) {
        alert("Enter a task first.");
        return;
    }
    if (unsafe) document.getElementById("taskInput").value = task;

    const id = Date.now().toString();
    const run = {
        id,
        title: task.length > 44 ? task.substring(0, 44) + "…" : task,
        date: new Date().toISOString(),
        status: "running",
        msgs: [],
        steps: {},
        agents: {},
        safetyReason: "",
    };
    runs.unshift(run);
    saveRuns();

    liveId = id;
    activeId = id;
    isTT = false;
    document.getElementById("ttBar").classList.remove("on");
    // Close any previous SSE connection BEFORE resetting state
    if (sseSource) {
        sseSource.close();
        sseSource = null;
    }
    _reviewAttempts = [];
    _currentIssues = []; // hard reset here too - belt and braces

    isRunning = true;
    setBtns(true);
    setStatus("running");
    clearChat();
    resetCodePreview();
    document.getElementById("hitlCard").classList.remove("on");
    document.getElementById("safetyCard").classList.remove("on");
    resetReviewPanel();
    mem.total++;
    updateMem();
    renderHistory();

    pushMsg(id, { type: "user", text: task });
    addTyping();

    try {
        const res = await fetch(unsafe ? "/api/unsafe" : "/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(unsafe ? {} : { task }),
        });
        if (!res.ok) {
            const err = await res
                .json()
                .catch(() => ({
                    error: "Server error — check that dashboard.py is running",
                }));
            removeTyping();
            pushMsg(id, {
                type: "agent",
                html: `<div class="abub abub-rejected">&#9888; ${err.error || "Pipeline error — please try again"}</div>`,
                agent: "Dashboard",
                time: tss(),
            });
            run.status = "rejected";
            isRunning = false;
            setBtns(false);
            saveRuns();
            renderHistory();
            return;
        }
        // Get the server's run_id so we can filter stale SSE events
        const data = await res.json().catch(() => ({}));
        const serverRunId = data.run_id || "";
        // Small delay ensures SSE connection opens before pipeline emits first events
        setTimeout(() => connectSSE(id, serverRunId), 100);
    } catch (e) {
        removeTyping();
        pushMsg(id, {
            type: "agent",
            html: `<div class="abub abub-rejected">Cannot reach server: ${e.message}</div>`,
            agent: "Dashboard",
            time: tss(),
        });
        run.status = "rejected";
        isRunning = false;
        setBtns(false);
        saveRuns();
        renderHistory();
    }
}

// HITL
async function inlineHITL(decision, runId) {
    document
        .getElementById(`inlineApprove-${runId}`)
        ?.setAttribute("disabled", "true");
    document
        .getElementById(`inlineReject-${runId}`)
        ?.setAttribute("disabled", "true");
    await sendHITL(decision);
}
async function hitlDecide(decision) {
    document.getElementById("btnApprove").disabled = true;
    document.getElementById("btnDecline").disabled = true;
    await sendHITL(decision);
    setTimeout(() => {
        document.getElementById("btnApprove").disabled = false;
        document.getElementById("btnDecline").disabled = false;
    }, 4000);
}
async function sendHITL(decision) {
    document.getElementById("hitlCard").classList.remove("on");
    try {
        await fetch("/api/hitl", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ decision }),
        });
    } catch (e) {
        console.error("HITL failed:", e);
    }
}

// BACKEND MEMORY
async function loadBackendMemory() {
    try {
        const d = await (await fetch("/api/memory")).json();
        const perf = d.coder_performance || {};
        mem.total = perf.total_tasks || runs.length;
        mem.firstTry =
            perf.passed_first_try ||
            runs.filter((r) => r.status === "deployed").length;
        mem.rejects =
            perf.total_rejections ||
            runs.filter(
                (r) => r.status === "rejected" || r.status === "blocked"
            ).length;
        mem.deployed =
            (d.deployments || []).length ||
            runs.filter((r) => r.status === "deployed").length;
    } catch {
        mem.total = runs.length;
        mem.deployed = runs.filter((r) => r.status === "deployed").length;
        mem.firstTry = mem.deployed;
        mem.rejects = runs.filter(
            (r) => r.status === "rejected" || r.status === "blocked"
        ).length;
    }
    updateMem();
}

// INIT - with refresh recovery
async function recoverOnRefresh() {
    const state = await fetchState();

    // Fix any run stuck as 'running' from a previous session
    runs.forEach((r) => {
        if (r.status === "running") {
            if (!state || state.status === "idle") {
                // Backend restarted or finished - mark rejected so it doesn't hang
                r.status = "rejected";
            } else if (
                state.status === "running" ||
                state.status === "hitl_pending"
            ) {
                // Backend is still live - reconnect SSE to resume streaming
                liveId = r.id;
                activeId = r.id;
                isRunning = true;
                setBtns(true);
                setStatus(state.status);
                connectSSE(r.id);
                if (
                    state.status === "hitl_pending" &&
                    state.hitl &&
                    state.hitl.pending
                ) {
                    showHITLCard(state.hitl, r.id);
                }
            }
        }
    });

    saveRuns();
    renderHistory();
    loadBackendMemory();
    // Only auto-view if it is the live running task - never show historical banner on fresh load
    if (runs.length && runs[0].id === liveId) viewRun(runs[0].id);
}

recoverOnRefresh();

// REVIEW RESULTS PANEL
let _reviewAttempts = []; // track per-run attempt results
let _currentIssues = []; // accumulate issues during current review attempt

function showReviewPanel() {
    document.getElementById("reviewCard").classList.add("on");
    // Reset scan step animations
    ["rvs1", "rvs2", "rvs3", "rvs4"].forEach((id) => {
        const el = document.getElementById(id);
        el.className = "rv-step";
    });
    document.getElementById("rvBar").style.width = "0%";
    document.getElementById("rvScoreVal").textContent = "—";
    document.getElementById("rvIssues").innerHTML = "";
    document.getElementById("rvFeedback").style.display = "none";
    document.getElementById("rvTitle").className = "rv-title running";
    document.getElementById("rvTitle").textContent = "REVIEWING...";
    animateScanSteps();
}

function animateScanSteps() {
    const steps = ["rvs1", "rvs2", "rvs3", "rvs4"];
    let i = 0;
    const interval = setInterval(() => {
        if (i > 0) {
            document.getElementById(steps[i - 1]).className = "rv-step done";
        }
        if (i < steps.length) {
            document.getElementById(steps[i]).className = "rv-step active";
            i++;
        } else {
            clearInterval(interval);
        }
    }, 600);
}

function updateReviewPanel(
    verdict,
    score,
    issues,
    feedback,
    attempt,
    totalAttempts
) {
    // Title + colour
    const titleEl = document.getElementById("rvTitle");
    if (verdict === "APPROVED" || verdict === "PASS") {
        titleEl.className = "rv-title approved";
        titleEl.textContent = "✓ APPROVED";
    } else if (verdict === "PERMANENTLY_REJECTED") {
        titleEl.className = "rv-title rejected";
        titleEl.textContent = "⛔ PERMANENTLY REJECTED";
    } else {
        titleEl.className = "rv-title rejected";
        titleEl.textContent = "✕ REJECTED";
    }

    // Attempt counter
    document.getElementById("rvAttempt").textContent = `Attempt ${attempt} / 3`;

    // Attempt chips
    _reviewAttempts.push({ attempt, verdict });
    const chipsEl = document.getElementById("rvAttempts");
    chipsEl.innerHTML = _reviewAttempts
        .map((a) => {
            const cls =
                a.verdict === "APPROVED" || a.verdict === "PASS"
                    ? "approved"
                    : "rejected";
            const label =
                a.verdict === "APPROVED" || a.verdict === "PASS" ? "✓" : "✕";
            return `<span class="att-chip ${cls}">${label} Attempt ${a.attempt}</span>`;
        })
        .join("");

    // Score bar
    const s = Math.min(100, Math.max(0, score || 0));
    const barCls = s >= 75 ? "high" : s >= 50 ? "mid" : "low";
    const bar = document.getElementById("rvBar");
    bar.className = `rv-bar-fill ${barCls}`;
    setTimeout(() => {
        bar.style.width = `${s}%`;
    }, 50);
    document.getElementById("rvScoreVal").textContent = `${s}/100`;

    // Mark all scan steps done
    ["rvs1", "rvs2", "rvs3", "rvs4"].forEach((id) => {
        document.getElementById(id).className =
            `rv-step ${verdict === "APPROVED" || verdict === "PASS" ? "done" : "error"}`;
    });

    // Issues list with line numbers
    const issuesEl = document.getElementById("rvIssues");
    if (issues && issues.length) {
        issuesEl.innerHTML = issues
            .slice(0, 8)
            .map((issue) => {
                const line = issue.line
                    ? `<span class="rv-line">Line ${issue.line}</span>`
                    : "";
                const msg = (
                    issue.message ||
                    issue.msg ||
                    JSON.stringify(issue)
                ).substring(0, 80);
                return `<div class="rv-issue">${line}${msg}</div>`;
            })
            .join("");
    } else {
        issuesEl.innerHTML = "";
    }

    // Feedback to Coder
    const fbEl = document.getElementById("rvFeedback");
    if (feedback && verdict !== "APPROVED" && verdict !== "PASS") {
        fbEl.textContent = feedback;
        fbEl.style.display = "block";
    } else {
        fbEl.style.display = "none";
    }
}

// TRACE MAP - AutoGen GroupChat messages
let _traceMessages = [];

function addTraceMessage(sender, recipient, msgType, content) {
    const time = new Date().toLocaleTimeString("en-GB", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    });
    _traceMessages.push({ time, sender, recipient, msgType, content });

    const listEl = document.getElementById("traceList");
    const emptyEl = document.getElementById("traceEmpty");
    if (emptyEl) emptyEl.remove();

    const senderShort = sender.replace(" Agent", "").replace(" Coder", " SC");
    const recipientShort = recipient
        .replace(" Agent", "")
        .replace(" Coder", " SC");

    const row = document.createElement("div");
    row.className = "trace-row";
    row.innerHTML = `
    <span class="trace-time">${time}</span>
    <span class="trace-from">${senderShort}</span>
    <span class="trace-arr">→</span>
    <span class="trace-to">${recipientShort}</span>
    <span class="trace-type ${msgType}">${msgType.toUpperCase()}</span>
  `;
    listEl.appendChild(row);
    listEl.scrollTop = listEl.scrollHeight;
}

// CODE PREVIEW PANEL
function showCodePreview(filename, code, status) {
    document.getElementById("ccEmpty").style.display = "none";
    document.getElementById("ccContent").style.display = "block";

    // Filename
    document.getElementById("ccFilename").textContent =
        filename || "code change";

    // Status badge
    const statusEl = document.getElementById("ccStatus");
    if (status === "approved") {
        statusEl.textContent = "✅ APPROVED";
        statusEl.className = "cc-status approved";
    } else if (status === "rejected") {
        statusEl.textContent = "✗ REJECTED";
        statusEl.className = "cc-status rejected";
    } else {
        statusEl.textContent = "⟳ WRITING...";
        statusEl.className = "cc-status working";
    }

    // Code block with basic syntax highlights
    const codeEl = document.getElementById("ccCode");
    codeEl.textContent = code
        ? code.substring(0, 2000) +
          (code.length > 2000 ? "\n... (truncated)" : "")
        : "";
}

function showCodePR(prUrl) {
    const prEl = document.getElementById("ccPr");
    const linkEl = document.getElementById("ccPrLink");
    if (prUrl) {
        linkEl.href = prUrl;
        // Show short label: "PR Created: github.com/.../pull/N"
        const short = prUrl.replace("https://", "").replace("http://", "");
        linkEl.textContent = `PR Created: ${short}`;
        prEl.style.display = "flex";
    }
}

function showCodeFeedback(feedback) {
    const fbEl = document.getElementById("ccFeedback");
    const bodyEl = document.getElementById("ccFeedbackBody");
    if (feedback) {
        bodyEl.textContent = feedback;
        fbEl.style.display = "block";
        // Mark status as rejected
        const statusEl = document.getElementById("ccStatus");
        statusEl.textContent = "✗ REJECTED";
        statusEl.className = "cc-status rejected";
    }
}

function clearCodeFeedback() {
    document.getElementById("ccFeedback").style.display = "none";
    document.getElementById("ccFeedbackBody").textContent = "";
}

function resetCodePreview() {
    document.getElementById("ccEmpty").style.display = "flex";
    document.getElementById("ccContent").style.display = "none";
    document.getElementById("ccPr").style.display = "none";
    document.getElementById("ccFeedback").style.display = "none";
    document.getElementById("ccFilename").textContent = "—";
    document.getElementById("ccCode").textContent = "";
    document.getElementById("ccStatus").textContent = "";
    document.getElementById("ccStatus").className = "cc-status";
}

function resetReviewPanel() {
    document.getElementById("reviewCard").classList.remove("on");
    _reviewAttempts = [];
    _traceMessages = [];
    const listEl = document.getElementById("traceList");
    listEl.innerHTML =
        '<div class="trace-empty" id="traceEmpty">No messages yet — run a task to see the agent trace</div>';
}
