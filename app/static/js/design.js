// Design page logic

document.addEventListener("DOMContentLoaded", () => {
    loadNutritionGoals();
    loadReminders();
    loadRoutine("morning");
    loadRoutine("evening");
    loadRoutine("daily");
    loadTechniques();
    loadPrompts("gratitude");
    loadPrompts("evening");
    if (location.hash === "#panel-nutrition") {
        document.getElementById("panel-nutrition")?.classList.add("open");
    }
});

// ── NUTRITION ─────────────────────────────────────────────────────────────────

async function loadNutritionGoals() {
    try {
        const t = await api.get("/today/api/nutrition/targets");
        document.getElementById("design-maintenance").value = t.maintenance_calories;
        document.getElementById("design-pro-goal").value = t.protein_goal;
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function saveNutritionGoals() {
    const maintenance_calories = Number(document.getElementById("design-maintenance").value);
    const protein_goal = Number(document.getElementById("design-pro-goal").value);
    try {
        await api.put("/today/api/nutrition/targets", { maintenance_calories, protein_goal });
        showToast("Nutrition settings saved", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── REMINDERS ─────────────────────────────────────────────────────────────────

async function loadReminders() {
    try {
        let list = await api.get("/today/api/reminders");
        if (!list.length) {
            list = await api.post("/today/api/reminders/seed", {});
        }
        renderReminders(list);
        window.LifeReminders?.refreshReminders?.();
    } catch (e) {
        showToast(e.message, "error");
    }
}

function renderReminders(list) {
    const el = document.getElementById("reminder-list");
    if (!list.length) {
        el.innerHTML = `<li class="text-muted" style="padding:var(--space-sm)">No reminders yet.</li>`;
        return;
    }
    el.innerHTML = list.map(r => `
        <li class="routine-item" data-id="${r.id}">
            <div class="routine-item-content">
                <div class="routine-item-title">${escHtml(r.label)}
                    <span class="badge">${escHtml(r.time_of_day)}</span>
                    <span class="badge">${escHtml(r.kind)}</span>
                    ${r.enabled ? "" : '<span class="badge">off</span>'}
                </div>
            </div>
            <div class="routine-item-actions" style="opacity:1">
                <button class="btn btn-ghost btn-sm" type="button" onclick="toggleReminder(${r.id}, ${r.enabled ? "false" : "true"})">${r.enabled ? "Disable" : "Enable"}</button>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteReminder(${r.id})">🗑</button>
            </div>
        </li>
    `).join("");
}

function showAddReminder() {
    document.getElementById("add-form-reminder").classList.remove("hidden");
    document.getElementById("reminder-label").focus();
}

function hideAddReminder() {
    document.getElementById("add-form-reminder").classList.add("hidden");
}

async function addReminder() {
    const label = document.getElementById("reminder-label").value.trim();
    const time_of_day = document.getElementById("reminder-time").value;
    const kind = document.getElementById("reminder-kind").value;
    if (!label || !time_of_day) return showToast("Label and time required", "error");
    try {
        await api.post("/today/api/reminders", { label, time_of_day, kind, enabled: true });
        document.getElementById("reminder-label").value = "";
        document.getElementById("reminder-time").value = "";
        hideAddReminder();
        await loadReminders();
        showToast("Reminder added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function toggleReminder(id, enabled) {
    try {
        await api.put(`/today/api/reminders/${id}`, { enabled });
        await loadReminders();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteReminder(id) {
    try {
        await api.delete(`/today/api/reminders/${id}`);
        await loadReminders();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── PANELS ────────────────────────────────────────────────────────────────────

function togglePanel(id) {
    document.getElementById(id).classList.toggle("open");
}

// ── ROUTINE STEPS ─────────────────────────────────────────────────────────────

async function loadRoutine(routine) {
    const steps = await api.get(`/design/api/routine/${routine}`);
    renderSteps(routine, steps);
}

function renderSteps(routine, steps) {
    const list = document.getElementById(`${routine}-list`);
    list.innerHTML = steps.map(s => stepHtml(s)).join("") ||
        `<li class="text-muted" style="padding:var(--space-sm)">No steps yet — add one below.</li>`;
    initDragDrop(list, routine);
}

function stepHtml(s) {
    const dur = s.duration_minutes ? `<span class="badge">${s.duration_minutes} min</span>` : "";
    const desc = s.description ? `<div class="routine-item-desc">${escHtml(s.description)}</div>` : "";
    return `
    <li class="routine-item" draggable="true" data-id="${s.id}">
        <span class="drag-handle">⋮⋮</span>
        <div class="routine-item-content">
            <div class="routine-item-title">${escHtml(s.title)} ${dur}</div>
            ${desc}
        </div>
        <div class="routine-item-actions">
            <button class="btn btn-ghost btn-sm" onclick="startEditStep(${s.id}, '${escHtml(s.title)}', '${escHtml(s.description || '')}', ${s.duration_minutes || ''})">✏️</button>
            <button class="btn btn-danger btn-sm" onclick="deleteStep(${s.id}, '${s.routine}')">🗑</button>
        </div>
    </li>`;
}

function showAddStep(routine) {
    document.getElementById(`add-form-${routine}`).classList.remove("hidden");
    document.getElementById(`${routine}-title`).focus();
}

function hideAddStep(routine) {
    document.getElementById(`add-form-${routine}`).classList.add("hidden");
    document.getElementById(`${routine}-title`).value = "";
    document.getElementById(`${routine}-desc`).value = "";
    document.getElementById(`${routine}-duration`).value = "";
}

async function addStep(routine) {
    const title = document.getElementById(`${routine}-title`).value.trim();
    if (!title) { showToast("Please enter a title", "error"); return; }
    const desc = document.getElementById(`${routine}-desc`).value.trim();
    const dur = parseInt(document.getElementById(`${routine}-duration`).value) || null;
    try {
        await api.post(`/design/api/routine/${routine}/step`, { title, description: desc, duration_minutes: dur });
        hideAddStep(routine);
        loadRoutine(routine);
        showToast("Step added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function startEditStep(id, title, desc, dur) {
    const li = document.querySelector(`.routine-item[data-id="${id}"]`);
    li.innerHTML = `
        <div class="edit-form" style="width:100%">
            <div class="field">
                <input type="text" id="edit-title-${id}" value="${escHtml(title)}">
            </div>
            <div class="add-form-row">
                <input type="text" id="edit-desc-${id}" placeholder="Description" value="${escHtml(desc)}">
                <input type="number" id="edit-dur-${id}" placeholder="Min" value="${dur || ''}" style="max-width:70px">
                <button class="btn btn-primary btn-sm" onclick="saveEditStep(${id})">Save</button>
                <button class="btn btn-ghost btn-sm" onclick="loadRoutine(document.querySelector('[data-id=\\'${id}\\']') ? '${findRoutineForStep(id)}' : 'morning')">Cancel</button>
            </div>
        </div>`;
    document.getElementById(`edit-title-${id}`).focus();
}

// Helper: find routine type from the list element's data attribute
function findRoutineForStep(stepId) {
    const lists = ["morning", "evening", "daily"];
    for (const r of lists) {
        const list = document.getElementById(`${r}-list`);
        if (list && list.querySelector(`[data-id="${stepId}"]`)) return r;
    }
    return "morning";
}

async function saveEditStep(id) {
    const title = document.getElementById(`edit-title-${id}`).value.trim();
    if (!title) { showToast("Title required", "error"); return; }
    const desc = document.getElementById(`edit-desc-${id}`).value.trim();
    const dur = parseInt(document.getElementById(`edit-dur-${id}`).value) || null;
    try {
        await api.put(`/design/api/routine/step/${id}`, { title, description: desc, duration_minutes: dur });
        loadRoutine("morning");
        loadRoutine("evening");
        loadRoutine("daily");
        showToast("Saved", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteStep(id, routine) {
    if (!confirm("Delete this step?")) return;
    try {
        await api.delete(`/design/api/routine/step/${id}`);
        loadRoutine(routine);
        showToast("Deleted", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── DRAG-AND-DROP REORDER ─────────────────────────────────────────────────────

function initDragDrop(list, routine) {
    let dragSrc = null;

    list.querySelectorAll(".routine-item[draggable]").forEach(item => {
        item.addEventListener("dragstart", e => {
            dragSrc = item;
            item.classList.add("dragging");
            e.dataTransfer.effectAllowed = "move";
        });
        item.addEventListener("dragend", () => {
            item.classList.remove("dragging");
            list.querySelectorAll(".routine-item").forEach(i => i.classList.remove("drag-over"));
        });
        item.addEventListener("dragover", e => {
            e.preventDefault();
            if (dragSrc && dragSrc !== item) {
                list.querySelectorAll(".routine-item").forEach(i => i.classList.remove("drag-over"));
                item.classList.add("drag-over");
            }
        });
        item.addEventListener("drop", async e => {
            e.preventDefault();
            if (dragSrc && dragSrc !== item) {
                const items = [...list.querySelectorAll(".routine-item[data-id]")];
                const srcIdx = items.indexOf(dragSrc);
                const dstIdx = items.indexOf(item);
                if (srcIdx < dstIdx) {
                    item.after(dragSrc);
                } else {
                    item.before(dragSrc);
                }
                const order = [...list.querySelectorAll(".routine-item[data-id]")].map(i => +i.dataset.id);
                await api.post(`/design/api/routine/${routine}/reorder`, { order });
            }
        });
    });
}

// ── TECHNIQUES ────────────────────────────────────────────────────────────────

async function loadTechniques() {
    const techs = await api.get("/design/api/techniques");
    renderTechniques(techs);
}

function renderTechniques(techs) {
    const grid = document.getElementById("technique-grid");
    grid.innerHTML = techs.map(t => techniqueHtml(t)).join("") || "";
}

function techniqueHtml(t) {
    const cat = t.category ? `<span class="badge" style="margin-bottom:var(--space-sm)">${escHtml(t.category)}</span>` : "";
    return `
    <div class="technique-card" id="tech-${t.id}">
        <div class="technique-card-actions">
            <button class="btn btn-ghost btn-sm" onclick="startEditTech(${t.id})">✏️</button>
            <button class="btn btn-danger btn-sm" onclick="deleteTech(${t.id})">🗑</button>
        </div>
        ${cat}
        <div class="technique-card-name">${escHtml(t.name)}</div>
        <div class="technique-card-desc">${escHtml(t.description)}</div>
    </div>`;
}

function showAddTechnique() {
    document.getElementById("add-form-technique").classList.remove("hidden");
    document.getElementById("tech-name").focus();
}

function hideAddTechnique() {
    document.getElementById("add-form-technique").classList.add("hidden");
    ["tech-name", "tech-category", "tech-desc"].forEach(id => {
        document.getElementById(id).value = "";
    });
}

async function addTechnique() {
    const name = document.getElementById("tech-name").value.trim();
    const desc = document.getElementById("tech-desc").value.trim();
    if (!name || !desc) { showToast("Name and description required", "error"); return; }
    const category = document.getElementById("tech-category").value.trim() || null;
    try {
        await api.post("/design/api/techniques", { name, description: desc, category });
        hideAddTechnique();
        loadTechniques();
        showToast("Technique added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function startEditTech(id) {
    const card = document.getElementById(`tech-${id}`);
    const name = card.querySelector(".technique-card-name").textContent;
    const desc = card.querySelector(".technique-card-desc").textContent;
    const badge = card.querySelector(".badge");
    const cat = badge ? badge.textContent : "";
    card.innerHTML = `
        <div class="edit-form">
            <div class="field"><label>Name</label><input id="etname-${id}" value="${escHtml(name)}"></div>
            <div class="field"><label>Category</label><input id="etcat-${id}" value="${escHtml(cat)}"></div>
            <div class="field"><label>Description</label><textarea id="etdesc-${id}">${escHtml(desc)}</textarea></div>
            <div class="flex gap-sm">
                <button class="btn btn-primary btn-sm" onclick="saveEditTech(${id})">Save</button>
                <button class="btn btn-ghost btn-sm" onclick="loadTechniques()">Cancel</button>
            </div>
        </div>`;
    document.getElementById(`etname-${id}`).focus();
}

async function saveEditTech(id) {
    const name = document.getElementById(`etname-${id}`).value.trim();
    const desc = document.getElementById(`etdesc-${id}`).value.trim();
    const category = document.getElementById(`etcat-${id}`).value.trim() || null;
    try {
        await api.put(`/design/api/techniques/${id}`, { name, description: desc, category });
        loadTechniques();
        showToast("Saved", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteTech(id) {
    if (!confirm("Delete this technique?")) return;
    try {
        await api.delete(`/design/api/techniques/${id}`);
        loadTechniques();
        showToast("Deleted", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── JOURNAL PROMPTS ────────────────────────────────────────────────────────────

let activePromptTab = "gratitude";

function switchPromptTab(type, btn) {
    activePromptTab = type;
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    document.getElementById(`prompts-${type}`).classList.add("active");
}

async function loadPrompts(type) {
    const prompts = await api.get(`/design/api/prompts/${type}`);
    renderPrompts(type, prompts);
}

function renderPrompts(type, prompts) {
    const list = document.getElementById(`prompt-list-${type}`);
    list.innerHTML = prompts.map(p => promptHtml(p)).join("") ||
        `<li class="text-muted" style="padding:var(--space-sm)">No prompts yet.</li>`;
    initPromptDragDrop(list, type);
}

function promptHtml(p) {
    const inactive = !p.is_active ? ' style="opacity:0.45"' : "";
    return `
    <li class="routine-item" draggable="true" data-id="${p.id}"${inactive}>
        <span class="drag-handle">⋮⋮</span>
        <div class="routine-item-content">
            <div class="routine-item-title">${escHtml(p.text)}</div>
        </div>
        <div class="routine-item-actions">
            <button class="btn btn-ghost btn-sm" title="${p.is_active ? 'Disable' : 'Enable'}"
                onclick="togglePrompt(${p.id}, ${!p.is_active}, '${p.prompt_type}')">${p.is_active ? "✓" : "○"}</button>
            <button class="btn btn-ghost btn-sm" onclick="startEditPrompt(${p.id}, '${escHtml(p.text)}', '${p.prompt_type}')">✏️</button>
            <button class="btn btn-danger btn-sm" onclick="deletePrompt(${p.id}, '${p.prompt_type}')">🗑</button>
        </div>
    </li>`;
}

function showAddPrompt(type) {
    document.getElementById(`add-form-prompt-${type}`).classList.remove("hidden");
    document.getElementById(`prompt-text-${type}`).focus();
}

function hideAddPrompt(type) {
    document.getElementById(`add-form-prompt-${type}`).classList.add("hidden");
    document.getElementById(`prompt-text-${type}`).value = "";
}

async function addPrompt(type) {
    const text = document.getElementById(`prompt-text-${type}`).value.trim();
    if (!text) { showToast("Please enter a prompt", "error"); return; }
    try {
        await api.post(`/design/api/prompts/${type}`, { text });
        hideAddPrompt(type);
        loadPrompts(type);
        showToast("Prompt added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function togglePrompt(id, active, type) {
    try {
        await api.put(`/design/api/prompts/${id}`, { is_active: active });
        loadPrompts(type);
    } catch (e) {
        showToast(e.message, "error");
    }
}

function startEditPrompt(id, text, type) {
    const li = document.querySelector(`#prompt-list-${type} [data-id="${id}"]`);
    li.innerHTML = `
        <div class="edit-form" style="width:100%">
            <div class="add-form-row">
                <input type="text" id="ep-${id}" value="${escHtml(text)}">
                <button class="btn btn-primary btn-sm" onclick="saveEditPrompt(${id}, '${type}')">Save</button>
                <button class="btn btn-ghost btn-sm" onclick="loadPrompts('${type}')">Cancel</button>
            </div>
        </div>`;
    document.getElementById(`ep-${id}`).focus();
}

async function saveEditPrompt(id, type) {
    const text = document.getElementById(`ep-${id}`).value.trim();
    if (!text) return;
    try {
        await api.put(`/design/api/prompts/${id}`, { text });
        loadPrompts(type);
        showToast("Saved", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deletePrompt(id, type) {
    if (!confirm("Delete this prompt?")) return;
    try {
        await api.delete(`/design/api/prompts/${id}`);
        loadPrompts(type);
        showToast("Deleted", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function initPromptDragDrop(list, type) {
    let dragSrc = null;
    list.querySelectorAll(".routine-item[draggable]").forEach(item => {
        item.addEventListener("dragstart", e => {
            dragSrc = item;
            item.classList.add("dragging");
            e.dataTransfer.effectAllowed = "move";
        });
        item.addEventListener("dragend", () => {
            item.classList.remove("dragging");
            list.querySelectorAll(".routine-item").forEach(i => i.classList.remove("drag-over"));
        });
        item.addEventListener("dragover", e => {
            e.preventDefault();
            if (dragSrc && dragSrc !== item) {
                list.querySelectorAll(".routine-item").forEach(i => i.classList.remove("drag-over"));
                item.classList.add("drag-over");
            }
        });
        item.addEventListener("drop", async e => {
            e.preventDefault();
            if (dragSrc && dragSrc !== item) {
                const items = [...list.querySelectorAll(".routine-item[data-id]")];
                const srcIdx = items.indexOf(dragSrc);
                const dstIdx = items.indexOf(item);
                if (srcIdx < dstIdx) item.after(dragSrc);
                else item.before(dragSrc);
                const order = [...list.querySelectorAll(".routine-item[data-id]")].map(i => +i.dataset.id);
                await api.post(`/design/api/prompts/${type}/reorder`, { order });
            }
        });
    });
}
