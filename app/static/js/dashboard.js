// Today dashboard — todos, goals, nutrition, workouts

document.addEventListener("DOMContentLoaded", async () => {
    const today = new Date();
    document.getElementById("today-date").textContent =
        today.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

    await Promise.all([loadTodos(), loadGoals(), loadNutrition(), loadWorkouts()]);
    initPushButton();

    // Enter-to-submit on quick-add fields
    ["food-label", "food-cal", "food-pro"].forEach(id => {
        document.getElementById(id)?.addEventListener("keydown", e => {
            if (e.key === "Enter") { e.preventDefault(); addFood(); }
        });
    });
    document.getElementById("todo-title")?.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); addTodo(); }
    });
});

function initPushButton() {
    const btn = document.getElementById("btn-enable-push");
    const status = document.getElementById("push-status");
    if (!("Notification" in window)) {
        btn.disabled = true;
        status.textContent = "Notifications not supported in this browser";
        return;
    }
    if (Notification.permission === "granted") {
        status.textContent = "Reminders on";
        btn.textContent = "Reminders enabled";
    } else if (Notification.permission === "denied") {
        status.textContent = "Blocked — allow notifications in browser settings";
        btn.disabled = true;
    }
    btn.addEventListener("click", async () => {
        const ok = await window.LifeReminders?.enable();
        if (ok) {
            status.textContent = "Reminders on";
            btn.textContent = "Reminders enabled";
            showToast("Computer reminders enabled", "success");
        } else {
            status.textContent = "Permission needed for push reminders";
            showToast("Notification permission denied", "error");
        }
    });
}

// ── TODOS ─────────────────────────────────────────────────────────────────────

function toggleTodoForm(show) {
    const form = document.getElementById("todo-form");
    const open = show === undefined ? form.classList.contains("hidden") : show;
    form.classList.toggle("hidden", !open);
    if (open) document.getElementById("todo-title").focus();
}

async function loadTodos() {
    const todos = await api.get("/today/api/todos");
    const list = document.getElementById("todo-list");
    const empty = document.getElementById("todo-empty");
    if (!todos.length) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
        return;
    }
    empty.classList.add("hidden");
    list.innerHTML = todos.map(todoItemHtml).join("");
}

function dots(n, max = 5, filledClass = "dot-on") {
    let html = "";
    for (let i = 1; i <= max; i++) {
        html += `<span class="metric-dot ${i <= n ? filledClass : ""}"></span>`;
    }
    return html;
}

function todoItemHtml(t) {
    return `
    <li class="check-item todo-item ${t.done ? "done" : ""}" id="todo-${t.id}">
        <div class="check-box ${t.done ? "checked" : ""}" onclick="toggleTodo(${t.id})">${t.done ? "✓" : ""}</div>
        <div class="todo-body">
            <div class="check-label">${escHtml(t.title)}</div>
            <div class="todo-metrics">
                <span class="metric" title="Importance">
                    <span class="metric-label">Imp</span>${dots(t.importance, 5, "dot-imp")}
                </span>
                <span class="metric" title="Effort">
                    <span class="metric-label">Eff</span>${dots(t.effort, 5, "dot-eff")}
                </span>
                ${t.due_date ? `<span class="check-meta">Due ${escHtml(t.due_date)}</span>` : ""}
            </div>
        </div>
        <button class="btn btn-danger btn-sm" type="button" onclick="deleteTodo(${t.id})" title="Delete">✕</button>
    </li>`;
}

async function addTodo() {
    const title = document.getElementById("todo-title").value.trim();
    if (!title) return showToast("Enter a task", "error");
    const importance = Number(document.getElementById("todo-importance").value);
    const effort = Number(document.getElementById("todo-effort").value);
    const due_date = document.getElementById("todo-due").value || null;
    try {
        await api.post("/today/api/todos", { title, importance, effort, due_date });
        document.getElementById("todo-title").value = "";
        document.getElementById("todo-due").value = "";
        document.getElementById("todo-importance").value = 3;
        document.getElementById("todo-effort").value = 3;
        document.getElementById("todo-imp-val").textContent = "3";
        document.getElementById("todo-eff-val").textContent = "3";
        toggleTodoForm(false);
        await loadTodos();
        showToast("Todo added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function toggleTodo(id) {
    try {
        await api.post(`/today/api/todos/${id}/toggle`, {});
        await loadTodos();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteTodo(id) {
    try {
        await api.delete(`/today/api/todos/${id}`);
        await loadTodos();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── GOALS ─────────────────────────────────────────────────────────────────────

function toggleGoalForm(show) {
    const form = document.getElementById("goal-form");
    const open = show === undefined ? form.classList.contains("hidden") : show;
    form.classList.toggle("hidden", !open);
    if (open) document.getElementById("goal-title").focus();
}

async function loadGoals() {
    const goals = await api.get("/today/api/goals?status=active");
    const list = document.getElementById("goal-list");
    const empty = document.getElementById("goal-empty");
    if (!goals.length) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
        return;
    }
    empty.classList.add("hidden");
    list.innerHTML = goals.map(g => `
        <li class="goal-item" id="goal-${g.id}">
            <div class="goal-main">
                <div class="goal-title">${escHtml(g.title)}</div>
                ${g.description ? `<div class="check-meta">${escHtml(g.description)}</div>` : ""}
                ${g.target_date ? `<div class="check-meta">Target ${escHtml(g.target_date)}</div>` : ""}
            </div>
            <div class="goal-actions">
                <button class="btn btn-secondary btn-sm" type="button" onclick="completeGoal(${g.id})">Done</button>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteGoal(${g.id})">✕</button>
            </div>
        </li>
    `).join("");
}

async function addGoal() {
    const title = document.getElementById("goal-title").value.trim();
    if (!title) return showToast("Enter a goal", "error");
    const description = document.getElementById("goal-desc").value.trim() || null;
    const target_date = document.getElementById("goal-target").value || null;
    try {
        await api.post("/today/api/goals", { title, description, target_date });
        document.getElementById("goal-title").value = "";
        document.getElementById("goal-desc").value = "";
        document.getElementById("goal-target").value = "";
        toggleGoalForm(false);
        await loadGoals();
        showToast("Goal added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function completeGoal(id) {
    try {
        await api.put(`/today/api/goals/${id}`, { status: "done" });
        await loadGoals();
        showToast("Goal completed", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteGoal(id) {
    try {
        await api.delete(`/today/api/goals/${id}`);
        await loadGoals();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── NUTRITION ─────────────────────────────────────────────────────────────────

async function loadNutrition() {
    const data = await api.get("/today/api/nutrition/today");
    const { targets, totals, entries } = data;
    const calPct = targets.calorie_goal ? Math.min(100, Math.round(totals.calories / targets.calorie_goal * 100)) : 0;
    const proPct = targets.protein_goal ? Math.min(100, Math.round(totals.protein / targets.protein_goal * 100)) : 0;
    document.getElementById("cal-label").textContent = `${totals.calories} / ${targets.calorie_goal}`;
    document.getElementById("pro-label").textContent = `${totals.protein} / ${targets.protein_goal} g`;
    document.getElementById("cal-bar").style.width = `${calPct}%`;
    document.getElementById("pro-bar").style.width = `${proPct}%`;

    const list = document.getElementById("food-list");
    list.innerHTML = entries.length
        ? entries.map(e => `
            <li class="entry-list-item food-row">
                <div>
                    <div class="entry-list-snippet">${escHtml(e.label)}</div>
                    <div class="entry-list-date">${e.calories} kcal · ${e.protein} g protein</div>
                </div>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteFood(${e.id})">✕</button>
            </li>`).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No food logged today.</li>`;
}

async function addFood() {
    const label = document.getElementById("food-label").value.trim();
    const calories = Number(document.getElementById("food-cal").value || 0);
    const protein = Number(document.getElementById("food-pro").value || 0);
    if (!label) return showToast("Enter a meal name", "error");
    try {
        await api.post("/today/api/nutrition/entries", { label, calories, protein });
        document.getElementById("food-label").value = "";
        document.getElementById("food-cal").value = "";
        document.getElementById("food-pro").value = "";
        await loadNutrition();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteFood(id) {
    try {
        await api.delete(`/today/api/nutrition/entries/${id}`);
        await loadNutrition();
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── WORKOUTS ──────────────────────────────────────────────────────────────────

async function loadWorkouts() {
    const data = await api.get("/today/api/workouts/overview");
    document.getElementById("zone2-stat").textContent = data.zone2.count;
    document.getElementById("zone2-meta").textContent =
        `${data.zone2.minutes} min${data.zone2.today ? " · today ✓" : ""}`;
    document.getElementById("lifting-stat").textContent = data.lifting.count;
    document.getElementById("lifting-meta").textContent =
        `${data.lifting.minutes} min${data.lifting.today ? " · today ✓" : ""}`;

    const list = document.getElementById("workout-list");
    list.innerHTML = data.workouts.length
        ? data.workouts.map(w => `
            <li class="entry-list-item food-row">
                <div>
                    <div class="entry-list-snippet">
                        <span class="kind-badge kind-${w.kind}">${w.kind === "zone2" ? "Zone 2" : "Lifting"}</span>
                        ${escHtml(w.title || "Session")}
                    </div>
                    <div class="entry-list-date">${escHtml(w.log_date)}${w.duration_minutes ? ` · ${w.duration_minutes} min` : ""}</div>
                </div>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteWorkout(${w.id})">✕</button>
            </li>`).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No workouts logged this week.</li>`;
}

async function addWorkout() {
    const kind = document.getElementById("workout-kind").value;
    const title = document.getElementById("workout-title").value.trim();
    const mins = document.getElementById("workout-mins").value;
    try {
        await api.post("/today/api/workouts", {
            kind,
            title: title || null,
            duration_minutes: mins ? Number(mins) : null,
        });
        document.getElementById("workout-title").value = "";
        document.getElementById("workout-mins").value = "";
        await loadWorkouts();
        showToast("Workout logged", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteWorkout(id) {
    try {
        await api.delete(`/today/api/workouts/${id}`);
        await loadWorkouts();
    } catch (e) {
        showToast(e.message, "error");
    }
}
