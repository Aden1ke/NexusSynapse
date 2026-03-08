/*
   NexusSynapse — Control Room  |  dashboard.js
    */

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

// Normalise any agent name string → chip element id suffix
// HTML ids: chip-manager, chip-coder, chip-senior, chip-deployer
function chipId(name) {
    const n = (name || "").toLowerCase();
    if (n.includes("senior")) return "senior";
    if (n.includes("deploy")) return "deployer";
    if (n.includes("coder")) return "coder";
    return "manager";
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

// SSE — real pipeline events
function connectSSE(runId) {
    if (sseSource) {
        sseSource.close();
        sseSource = null;
    }
    sseSource = new EventSource("/stream");

    sseSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.heartbeat) return;

        const { level, agent, message, timestamp } = data;
        const time = timestamp || tss();
        const chip = chipId(agent);
        const status = levelToStatus(level);

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

        // Update agent chip
        storeAgent(runId, chip, status);

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

        // Render bubble
        pushMsg(runId, {
            type: "agent",
            html: levelToBubble(level, message),
            agent,
            time,
        });

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
        if (
            level === "warning" &&
            message.toLowerCase().includes("rejected at hitl")
        ) {
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

        if (isRunning) addTyping();
    };

    sseSource.onerror = () => {
        removeTyping();
    };
}

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

// HISTORY SIDEBAR — with delete buttons
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
    if (isRunning) return;
    activeId = null;
    liveId = null;
    isTT = false;
    document.getElementById("ttBar").classList.remove("on");
    document.getElementById("taskInput").value = "";
    setBtns(false);
    clearChat();
    renderHistory();
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
    isRunning = true;
    setBtns(true);
    setStatus("running");
    clearChat();
    document.getElementById("hitlCard").classList.remove("on");
    document.getElementById("safetyCard").classList.remove("on");
    mem.total++;
    updateMem();
    renderHistory();

    pushMsg(id, { type: "user", text: task });
    addTyping();
    connectSSE(id);

    try {
        const res = await fetch(unsafe ? "/api/unsafe" : "/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(unsafe ? {} : { task }),
        });
        if (!res.ok) {
            const err = await res
                .json()
                .catch(() => ({ error: "Unknown error" }));
            removeTyping();
            pushMsg(id, {
                type: "agent",
                html: `<div class="abub abub-rejected">&#9888; ${err.error}</div>`,
                agent: "Dashboard",
                time: tss(),
            });
            run.status = "rejected";
            isRunning = false;
            setBtns(false);
            saveRuns();
            renderHistory();
        }
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

// INIT — with refresh recovery
async function recoverOnRefresh() {
    const state = await fetchState();

    // Fix any run stuck as 'running' from a previous session
    runs.forEach((r) => {
        if (r.status === "running") {
            if (!state || state.status === "idle") {
                // Backend restarted or finished — mark rejected so it doesn't hang
                r.status = "rejected";
            } else if (
                state.status === "running" ||
                state.status === "hitl_pending"
            ) {
                // Backend is still live — reconnect SSE to resume streaming
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
    if (runs.length) viewRun(runs[0].id);
}

recoverOnRefresh();
