// Evening shutdown guided flow

let shutdownState = null;
let currentStep = 1;
let planView = "list";
let selectedTomorrow = new Set();

const LEVEL = { 1: "L", 2: "M", 3: "H" };

document.addEventListener("DOMContentLoaded", async () => {
    await loadShutdown();
});

async function loadShutdown() {
    try {
        shutdownState = await api.get("/review/api/shutdown");
        document.getElementById("shutdown-date").textContent =
            `Closing ${shutdownState.date}. Each step is skippable.`;
        document.getElementById("plan-cap").textContent = shutdownState.todo_cap;
        document.getElementById("tomorrow-hours").value =
            shutdownState.tomorrow_available_hours ?? shutdownState.default_available_hours ?? 4;

        if (shutdownState.is_complete) {
            showPane("done");
            return;
        }
        renderTasks();
        renderEveningRoutine();
        renderReflection();
        renderPlanCandidates();
        renderShutCheckin();
        selectedTomorrow = new Set((shutdownState.tomorrow_todos || []).map(t => t.id));
        updateSelectedCount();

        const start = shutdownState.shutdown_step
            ? Math.min(4, Math.max(1, shutdownState.shutdown_step + 1))
            : 1;
        goStep(start);
    } catch (e) {
        showToast(e.message, "error");
    }
}

function showPane(name) {
    document.querySelectorAll(".shutdown-pane").forEach(p => {
        p.classList.toggle("active", p.dataset.pane === String(name));
    });
}

function goStep(n) {
    currentStep = n;
    showPane(n);
    document.querySelectorAll(".shutdown-step-dot").forEach(btn => {
        const s = Number(btn.dataset.step);
        btn.classList.toggle("active", s === n);
        btn.classList.toggle("done", s < n);
    });
    api.post("/review/api/shutdown/step", { shutdown_step: n - 1 }).catch(() => {});
}

document.getElementById("shutdown-progress")?.addEventListener("click", e => {
    const btn = e.target.closest(".shutdown-step-dot");
    if (!btn) return;
    goStep(Number(btn.dataset.step));
});

function renderTasks() {
    const list = document.getElementById("shutdown-tasks");
    const empty = document.getElementById("shutdown-tasks-empty");
    const todos = shutdownState.open_todos || [];
    if (!todos.length) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
        return;
    }
    empty.classList.add("hidden");
    list.innerHTML = todos.map(t => `
        <li class="shutdown-task" data-id="${t.id}">
            <div class="shutdown-task-title">${escHtml(t.title)}</div>
            <div class="shutdown-task-actions">
                <label><input type="radio" name="disp-${t.id}" value="done"> Done</label>
                <label><input type="radio" name="disp-${t.id}" value="roll" checked> Roll</label>
                <label><input type="radio" name="disp-${t.id}" value="overall"> Overall</label>
                <label><input type="radio" name="disp-${t.id}" value="delete"> Delete</label>
            </div>
        </li>`).join("");
}

function renderEveningRoutine() {
    const items = shutdownState.evening_completions || [];
    const list = document.getElementById("evening-checklist");
    const done = items.filter(c => c.completed).length;
    document.getElementById("evening-progress-text").textContent = `${done} / ${items.length}`;
    document.getElementById("evening-progress-bar").style.width =
        `${items.length ? Math.round(done / items.length * 100) : 0}%`;
    if (!items.length) {
        list.innerHTML = `<li class="text-muted">No evening steps — configure in Design.</li>`;
        return;
    }
    list.innerHTML = items.map(c => `
        <li class="check-item ${c.completed ? "done" : ""}" id="shut-item-${c.id}">
            <div class="check-box ${c.completed ? "checked" : ""}" onclick="toggleEveningItem(${c.id})">
                ${c.completed ? "✓" : ""}
            </div>
            <div class="check-label">${escHtml(c.step_title)}</div>
        </li>`).join("");
}

async function toggleEveningItem(id) {
    try {
        const updated = await api.post(`/tracker/api/completion/${id}/toggle`, {});
        const row = shutdownState.evening_completions.find(c => c.id === id);
        if (row) Object.assign(row, updated);
        renderEveningRoutine();
    } catch (e) {
        showToast(e.message, "error");
    }
}

function renderReflection() {
    const prompts = shutdownState.reflection?.prompts || [];
    const el = document.getElementById("shutdown-prompts");
    if (!prompts.length) {
        el.innerHTML = `<p class="text-muted">No evening prompts yet — add them in <a href="/design/">Design</a>.</p>`;
        return;
    }
    el.innerHTML = prompts.map(p => `
        <div class="journal-prompt">
            <div class="journal-prompt-text">${escHtml(p.text)}</div>
            <textarea class="journal-textarea" id="shut-resp-${p.id}" data-prompt-id="${p.id}"
                placeholder="Write…">${escHtml(p.response || "")}</textarea>
        </div>`).join("");
}

function matrixQuadrant(imp, eff) {
    const highImp = imp >= 3;
    const lowEff = eff <= 1;
    if (highImp && lowEff) return "quick";
    if (highImp) return "bets";
    if (lowEff) return "fill";
    return "reconsider";
}

function candidateRow(t) {
    const checked = selectedTomorrow.has(t.id) ? "checked" : "";
    return `<label class="plan-candidate">
        <input type="checkbox" value="${t.id}" ${checked} onchange="togglePlanSelect(${t.id}, this.checked)">
        <span>${escHtml(t.title)}</span>
        <span class="text-muted">Imp ${LEVEL[t.importance] || "?"} · Eff ${LEVEL[t.effort] || "?"}</span>
    </label>`;
}

function renderPlanCandidates() {
    const rolled = shutdownState.tomorrow_todos || [];
    const overall = shutdownState.overall_todos || [];
    // Merge unique by id — prefer rolled first
    const map = new Map();
    for (const t of [...rolled, ...overall]) map.set(t.id, t);
    const all = [...map.values()];
    const el = document.getElementById("plan-candidates");

    if (planView === "matrix") {
        const buckets = { quick: [], bets: [], fill: [], reconsider: [] };
        const titles = {
            quick: "Quick wins", bets: "Big bets",
            fill: "Fill-ins", reconsider: "Reconsider",
        };
        for (const t of all) buckets[matrixQuadrant(t.importance, t.effort)].push(t);
        el.innerHTML = `<div class="todo-matrix">${Object.keys(buckets).map(k => `
            <div class="matrix-cell">
                <div class="matrix-cell-title">${titles[k]}</div>
                ${buckets[k].map(candidateRow).join("") || `<p class="text-muted">—</p>`}
            </div>`).join("")}</div>`;
    } else {
        el.innerHTML = all.length
            ? `<div class="plan-list">${all.map(candidateRow).join("")}</div>`
            : `<p class="text-muted">No candidates — Overall is empty and nothing rolled.</p>`;
    }
    document.getElementById("plan-view-list").classList.toggle("active", planView === "list");
    document.getElementById("plan-view-matrix").classList.toggle("active", planView === "matrix");
}

function setPlanView(v) {
    planView = v;
    renderPlanCandidates();
}

function togglePlanSelect(id, on) {
    const cap = shutdownState.todo_cap || 3;
    if (on) {
        if (selectedTomorrow.size >= cap) {
            showToast(`Cap is ${cap} — deselect one first`, "error");
            renderPlanCandidates();
            return;
        }
        selectedTomorrow.add(id);
    } else {
        selectedTomorrow.delete(id);
    }
    updateSelectedCount();
}

function updateSelectedCount() {
    const el = document.getElementById("plan-selected-count");
    if (el) {
        el.textContent = `${selectedTomorrow.size} / ${shutdownState?.todo_cap || 3} selected`;
    }
}

async function shutdownSaveTasks() {
    const dispositions = {};
    document.querySelectorAll(".shutdown-task").forEach(li => {
        const id = li.dataset.id;
        const checked = li.querySelector(`input[name="disp-${id}"]:checked`);
        dispositions[id] = checked ? checked.value : "roll";
    });
    try {
        await api.post("/review/api/shutdown/tasks", { dispositions });
        await loadShutdown();
        goStep(2);
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function shutdownSaveReflection() {
    const responses = {};
    document.querySelectorAll("#shutdown-prompts textarea").forEach(ta => {
        responses[ta.dataset.promptId] = ta.value;
    });
    try {
        if (Object.keys(responses).length) {
            await api.post("/review/api/shutdown/reflection", { responses });
        } else {
            await api.post("/review/api/shutdown/step", { shutdown_step: 3 });
        }
        goStep(4);
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function shutdownNext(from) {
    try {
        await api.post("/review/api/shutdown/step", { shutdown_step: from });
        goStep(from + 1);
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function shutdownSkip(from) {
    if (from >= 4) {
        await shutdownFinish(true);
        return;
    }
    await shutdownNext(from);
}

function setShutCheckin(field, value) {
    const seg = document.getElementById(`shut-${field}-seg`);
    if (!seg) return;
    seg.dataset.value = String(value);
    seg.querySelectorAll("button").forEach(b => {
        b.classList.toggle("active", Number(b.dataset.v) === value);
    });
}

function renderShutCheckin() {
    const c = shutdownState.checkin || {};
    if (c.mood) setShutCheckin("mood", c.mood);
    if (c.energy) setShutCheckin("energy", c.energy);
    const note = document.getElementById("shut-checkin-note");
    if (note) note.value = c.note || "";
}

async function saveShutCheckinIfAny() {
    const mood = document.getElementById("shut-mood-seg")?.dataset.value;
    const energy = document.getElementById("shut-energy-seg")?.dataset.value;
    const note = document.getElementById("shut-checkin-note")?.value.trim() || "";
    if (!mood && !energy && !note) return;
    const payload = {};
    if (mood) payload.mood = Number(mood);
    if (energy) payload.energy = Number(energy);
    if (note) payload.note = note;
    await api.put("/today/api/checkin", payload);
}

async function shutdownFinish(skippedPlan = false) {
    try {
        if (!skippedPlan) {
            await api.post("/review/api/shutdown/plan", {
                todo_ids: [...selectedTomorrow],
                available_hours: Number(document.getElementById("tomorrow-hours").value),
            });
        }
        await saveShutCheckinIfAny();
        await api.post("/review/api/shutdown/complete", {});
        showPane("done");
        showToast("Day marked complete", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}
