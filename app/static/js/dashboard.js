// Today dashboard — nested todos, nutrition deficit/week, upper/lower/zone2

function localISODate(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

document.addEventListener("DOMContentLoaded", async () => {
    const today = new Date();
    document.getElementById("today-date").textContent =
        today.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

    applyBucketFormMode();
    await Promise.all([loadTodos(), loadGoals(), loadNutrition(), loadSteps(), loadWorkouts()]);
    initPushButton();

    ["food-label", "food-cal", "food-pro"].forEach(id => {
        document.getElementById(id)?.addEventListener("keydown", e => {
            if (e.key === "Enter") { e.preventDefault(); addFood(); }
        });
    });
    document.getElementById("todo-title")?.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); addTodo(); }
    });
    document.getElementById("steps-count")?.addEventListener("keydown", e => {
        if (e.key === "Enter") { e.preventDefault(); saveSteps(); }
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

// ── PLANNING TABS + TODO BUCKETS ──────────────────────────────────────────────

let currentTodoBucket = "today";

const BUCKET_COPY = {
    today: {
        title: "Today’s to-dos",
        hint: "Tasks for today only — tick them off as you go.",
        placeholder: "What needs doing today?",
        addLabel: "Add today’s task",
    },
    overall: {
        title: "Overall to-dos",
        hint: "Longer-running tasks that aren’t just for today.",
        placeholder: "e.g. Tax return",
        addLabel: "Add overall todo",
    },
    idea: {
        title: "Idea collection",
        hint: "Capture ideas here. Move one to Today or Overall when you’re ready.",
        placeholder: "Capture an idea…",
        addLabel: "Add idea",
    },
};

function switchMainTab(tab, btn) {
    document.querySelectorAll("#main-planning-tabs .tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("main-tab-todo").classList.toggle("active", tab === "todo");
    document.getElementById("main-tab-goals").classList.toggle("active", tab === "goals");
    document.getElementById("main-tab-history").classList.toggle("active", tab === "history");
    if (tab === "goals") loadGoals();
    if (tab === "history") loadHistoryList();
}

// ── HISTORY ───────────────────────────────────────────────────────────────────

let historySelectedDate = null;

function formatDeficitShort(n) {
    if (n == null) return "—";
    if (n > 0) return `−${n}`;
    if (n < 0) return `+${Math.abs(n)}`;
    return "0";
}

function formatDayLabel(iso) {
    const d = new Date(iso + "T00:00:00");
    const today = localISODate();
    const yday = localISODate(new Date(Date.now() - 86400000));
    if (iso === today) return "Today";
    if (iso === yday) return "Yesterday";
    return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

async function loadHistoryList() {
    const active = document.getElementById("history-active-only")?.checked ? "&active=1" : "";
    const data = await api.get(`/today/api/history?days=28${active}`);
    const list = document.getElementById("history-list");
    if (!data.days_list.length) {
        list.innerHTML = `<li class="text-muted" style="padding:var(--space-sm) 0">No days to show.</li>`;
        return;
    }
    list.innerHTML = data.days_list.map(day => {
        const deficitClass = day.deficit == null
            ? ""
            : day.deficit > 0 ? "hist-deficit" : day.deficit < 0 ? "hist-surplus" : "hist-even";
        const deficitText = day.deficit == null
            ? `<span class="hist-pill muted">No food log</span>`
            : `<span class="hist-pill ${deficitClass}">${formatDeficitShort(day.deficit)} kcal</span>`;
        const selected = historySelectedDate === day.date ? " selected" : "";
        return `
        <li class="history-row${selected}${day.has_activity ? "" : " empty-day"}" onclick="openHistoryDay('${day.date}')">
            <div class="history-row-main">
                <div class="history-row-date">${formatDayLabel(day.date)}</div>
                <div class="history-row-iso text-muted">${escHtml(day.date)}</div>
            </div>
            <div class="history-row-metrics">
                ${deficitText}
                <span class="hist-stat" title="Protein">${day.protein}g pro${day.protein_hit ? " ✓" : ""}</span>
                <span class="hist-stat" title="Steps">${(day.steps || 0).toLocaleString()} steps${day.steps_hit ? " ✓" : ""}</span>
                <span class="hist-stat" title="Workouts">${day.workouts_count} workout${day.workouts_count === 1 ? "" : "s"}</span>
                <span class="hist-stat" title="Todos completed">${day.todos_completed} done</span>
            </div>
        </li>`;
    }).join("");
}

async function openHistoryDay(dateStr) {
    historySelectedDate = dateStr;
    document.querySelectorAll(".history-row").forEach(el => {
        el.classList.toggle("selected", el.getAttribute("onclick")?.includes(dateStr));
    });
    const detail = document.getElementById("history-detail");
    detail.classList.remove("hidden");
    document.getElementById("history-detail-title").textContent = formatDayLabel(dateStr);

    const data = await api.get(`/today/api/history/${dateStr}`);
    const o = data.overview;
    const deficitLabel = o.deficit == null
        ? "No food logged"
        : formatDeficit(o.deficit);
    document.getElementById("history-detail-stats").innerHTML = `
        <div class="history-stat-card ${o.deficit == null ? "" : o.deficit > 0 ? "is-deficit" : o.deficit < 0 ? "is-surplus" : ""}">
            <div class="week-stat-label">Calorie balance</div>
            <div class="week-stat-value">${o.deficit == null ? "—" : formatDeficitShort(o.deficit)}</div>
            <div class="week-stat-meta">${deficitLabel}</div>
        </div>
        <div class="history-stat-card">
            <div class="week-stat-label">TDEE</div>
            <div class="week-stat-value">${o.tdee.tdee}</div>
            <div class="week-stat-meta">${o.tdee.baseline} + ${o.tdee.from_steps} steps + ${o.tdee.from_workouts} workouts</div>
        </div>
        <div class="history-stat-card">
            <div class="week-stat-label">Intake / protein</div>
            <div class="week-stat-value">${o.intake_calories}</div>
            <div class="week-stat-meta">${o.protein} / ${o.protein_goal} g${o.protein_hit ? " · on target" : ""}</div>
        </div>
        <div class="history-stat-card">
            <div class="week-stat-label">Activity</div>
            <div class="week-stat-value">${(o.steps || 0).toLocaleString()}</div>
            <div class="week-stat-meta">${o.workouts_count} workouts · ${o.todos_completed} todos done</div>
        </div>
    `;

    document.getElementById("hist-steps").value = o.steps || "";

    const foodList = document.getElementById("hist-food-list");
    foodList.innerHTML = data.entries.length
        ? data.entries.map(e => `
            <li class="entry-list-item food-row">
                <div>
                    <div class="entry-list-snippet">${escHtml(e.label)}</div>
                    <div class="entry-list-date">${e.calories} kcal · ${e.protein} g</div>
                </div>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteHistoryFood(${e.id})">✕</button>
            </li>`).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No food logged.</li>`;

    const workoutList = document.getElementById("hist-workout-list");
    workoutList.innerHTML = data.workouts.length
        ? data.workouts.map(w => `
            <li class="entry-list-item food-row">
                <div>
                    <div class="entry-list-snippet">
                        <span class="kind-badge kind-${w.kind}">${kindLabel(w.kind)}</span>
                        ${escHtml(w.title || "Session")}
                    </div>
                    <div class="entry-list-date">${w.duration_minutes ? `${w.duration_minutes} min` : ""}${w.calories_burned ? ` · ${w.calories_burned} kcal` : ""}</div>
                </div>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteHistoryWorkout(${w.id})">✕</button>
            </li>`).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No workouts.</li>`;

    const todosList = document.getElementById("hist-todos-list");
    const completed = data.completed_todos || [];
    todosList.innerHTML = completed.length
        ? completed.map(t => `
            <li class="entry-list-item">
                <div class="entry-list-snippet">${escHtml(t.title)}</div>
                <div class="entry-list-date">${escHtml(t.bucket)}${t.completed_at ? ` · ${escHtml(t.completed_at.slice(0, 16).replace("T", " "))}` : ""}</div>
            </li>`).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No completions logged.</li>`;

    detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeHistoryDetail() {
    historySelectedDate = null;
    document.getElementById("history-detail").classList.add("hidden");
    document.querySelectorAll(".history-row").forEach(el => el.classList.remove("selected"));
}

async function saveHistorySteps() {
    if (!historySelectedDate) return;
    const raw = document.getElementById("hist-steps").value;
    if (raw === "") return showToast("Enter steps", "error");
    try {
        await api.put("/today/api/steps/today", {
            log_date: historySelectedDate,
            count: Math.round(Number(raw)),
        });
        showToast("Steps saved", "success");
        await refreshHistoryAfterEdit();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function addHistoryFood() {
    if (!historySelectedDate) return;
    const label = document.getElementById("hist-food-label").value.trim();
    const calories = Number(document.getElementById("hist-food-cal").value || 0);
    const protein = Number(document.getElementById("hist-food-pro").value || 0);
    if (!label) return showToast("Enter a meal name", "error");
    try {
        await api.post("/today/api/nutrition/entries", {
            label, calories, protein, log_date: historySelectedDate,
        });
        document.getElementById("hist-food-label").value = "";
        document.getElementById("hist-food-cal").value = "";
        document.getElementById("hist-food-pro").value = "";
        await refreshHistoryAfterEdit();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteHistoryFood(id) {
    try {
        await api.delete(`/today/api/nutrition/entries/${id}`);
        await refreshHistoryAfterEdit();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function addHistoryWorkout() {
    if (!historySelectedDate) return;
    const kind = document.getElementById("hist-workout-kind").value;
    const title = document.getElementById("hist-workout-title").value.trim();
    const mins = document.getElementById("hist-workout-mins").value;
    const kcal = document.getElementById("hist-workout-kcal").value;
    try {
        await api.post("/today/api/workouts", {
            kind,
            title: title || null,
            duration_minutes: mins ? Number(mins) : null,
            calories_burned: kcal !== "" ? Number(kcal) : null,
            log_date: historySelectedDate,
        });
        document.getElementById("hist-workout-title").value = "";
        document.getElementById("hist-workout-mins").value = "";
        document.getElementById("hist-workout-kcal").value = "";
        showToast("Workout logged", "success");
        await refreshHistoryAfterEdit();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteHistoryWorkout(id) {
    try {
        await api.delete(`/today/api/workouts/${id}`);
        await refreshHistoryAfterEdit();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function refreshHistoryAfterEdit() {
    const date = historySelectedDate;
    await loadHistoryList();
    if (date) await openHistoryDay(date);
    // Keep Today panels in sync if editing today
    if (date === localISODate()) {
        await Promise.all([loadNutrition(), loadSteps(), loadWorkouts()]);
    }
}

function switchTodoBucket(bucket, btn) {
    currentTodoBucket = bucket;
    document.querySelectorAll("#todo-bucket-chips .chip").forEach(c => c.classList.remove("active"));
    btn.classList.add("active");
    applyBucketFormMode();
    toggleTodoForm(false);
    loadTodos();
}

function applyBucketFormMode() {
    const copy = BUCKET_COPY[currentTodoBucket];
    document.getElementById("todo-bucket-title").textContent = copy.title;
    document.getElementById("bucket-hint").textContent = copy.hint;
    document.getElementById("todo-title").placeholder = copy.placeholder;
    document.getElementById("todo-add-btn").textContent = copy.addLabel;

    const isIdea = currentTodoBucket === "idea";
    document.getElementById("todo-step-field").classList.toggle("hidden", isIdea);
    document.getElementById("todo-notes-field").classList.toggle("hidden", !isIdea);
    document.getElementById("todo-metrics-fields").classList.toggle("hidden", isIdea);
    document.getElementById("todo-due-field").classList.toggle("hidden", isIdea);
    document.getElementById("todo-title-label").textContent = isIdea ? "Idea" : "Task";
}

function toggleTodoForm(show) {
    const form = document.getElementById("todo-form");
    const open = show === undefined ? form.classList.contains("hidden") : show;
    form.classList.toggle("hidden", !open);
    if (open) {
        applyBucketFormMode();
        document.getElementById("todo-title").focus();
    }
}

async function loadTodos() {
    let url = `/today/api/todos?bucket=${currentTodoBucket}`;
    if (currentTodoBucket === "today") {
        url += `&date=${localISODate()}`;
    }
    const todos = await api.get(url);
    const list = document.getElementById("todo-list");
    const empty = document.getElementById("todo-empty");
    if (!todos.length) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
        empty.textContent = currentTodoBucket === "idea"
            ? "No ideas yet — capture one above."
            : currentTodoBucket === "today"
                ? "No tasks for today — add one above."
                : "No overall todos — add one above.";
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

function kindLabel(kind) {
    return ({ zone2: "Zone 2", full: "Full", upper: "Upper", lower: "Lower" })[kind] || kind;
}

function moveButtonsHtml(t) {
    const moves = [];
    if (t.bucket !== "today") {
        moves.push(`<button class="btn btn-ghost btn-sm" type="button" onclick="moveTodo(${t.id},'today')">→ Today</button>`);
    }
    if (t.bucket !== "overall") {
        moves.push(`<button class="btn btn-ghost btn-sm" type="button" onclick="moveTodo(${t.id},'overall')">→ Overall</button>`);
    }
    if (t.bucket !== "idea") {
        moves.push(`<button class="btn btn-ghost btn-sm" type="button" onclick="moveTodo(${t.id},'idea')">→ Ideas</button>`);
    }
    return moves.length ? `<div class="todo-move-actions">${moves.join("")}</div>` : "";
}

function todoItemHtml(t) {
    const isIdea = t.bucket === "idea";
    const steps = t.steps || [];
    const stepProgress = !isIdea && steps.length
        ? `<span class="check-meta">${t.steps_done}/${t.steps_total} steps</span>`
        : "";
    const stepsHtml = isIdea ? "" : steps.map(s => `
        <li class="todo-step ${s.done ? "done" : ""}">
            <div class="check-box ${s.done ? "checked" : ""}" onclick="toggleTodoStep(${s.id})">${s.done ? "✓" : ""}</div>
            <span class="todo-step-title">${escHtml(s.title)}</span>
            <button class="btn btn-danger btn-sm" type="button" onclick="deleteTodoStep(${s.id})" title="Remove step">✕</button>
        </li>
    `).join("");

    const metrics = isIdea
        ? (t.notes ? `<div class="check-meta">${escHtml(t.notes)}</div>` : "")
        : `<div class="todo-metrics">
                <span class="metric" title="Importance">
                    <span class="metric-label">Imp</span>${dots(t.importance, 5, "dot-imp")}
                </span>
                <span class="metric" title="Effort">
                    <span class="metric-label">Eff</span>${dots(t.effort, 5, "dot-eff")}
                </span>
                ${stepProgress}
                ${t.due_date ? `<span class="check-meta">Due ${escHtml(t.due_date)}</span>` : ""}
           </div>`;

    const addStep = isIdea ? "" : `
        <ul class="todo-steps">${stepsHtml}</ul>
        <div class="todo-add-step">
            <input type="text" id="step-input-${t.id}" placeholder="Add a step…" onkeydown="if(event.key==='Enter'){event.preventDefault();addTodoStep(${t.id})}">
            <button class="btn btn-secondary btn-sm" type="button" onclick="addTodoStep(${t.id})">+ Step</button>
        </div>`;

    return `
    <li class="todo-block ${t.done ? "done" : ""}" id="todo-${t.id}">
        <div class="todo-row">
            <div class="check-box ${t.done ? "checked" : ""}" onclick="toggleTodo(${t.id})">${t.done ? "✓" : ""}</div>
            <div class="todo-body">
                <div class="check-label">${escHtml(t.title)}</div>
                ${metrics}
                ${moveButtonsHtml(t)}
            </div>
            <button class="btn btn-danger btn-sm" type="button" onclick="deleteTodo(${t.id})" title="Delete">✕</button>
        </div>
        ${addStep}
    </li>`;
}

async function addTodo() {
    const title = document.getElementById("todo-title").value.trim();
    if (!title) return showToast(currentTodoBucket === "idea" ? "Enter an idea" : "Enter a task", "error");

    const payload = { title, bucket: currentTodoBucket };
    if (currentTodoBucket === "idea") {
        const notes = document.getElementById("todo-notes").value.trim();
        if (notes) payload.notes = notes;
    } else {
        const firstStep = document.getElementById("todo-first-step").value.trim();
        payload.importance = Number(document.getElementById("todo-importance").value);
        payload.effort = Number(document.getElementById("todo-effort").value);
        payload.due_date = document.getElementById("todo-due").value || null;
        if (firstStep) payload.steps = [firstStep];
        if (currentTodoBucket === "today") {
            payload.for_date = localISODate();
        }
    }

    try {
        await api.post("/today/api/todos", payload);
        document.getElementById("todo-title").value = "";
        document.getElementById("todo-first-step").value = "";
        document.getElementById("todo-notes").value = "";
        document.getElementById("todo-due").value = "";
        document.getElementById("todo-importance").value = 3;
        document.getElementById("todo-effort").value = 3;
        document.getElementById("todo-imp-val").textContent = "3";
        document.getElementById("todo-eff-val").textContent = "3";
        toggleTodoForm(false);
        await loadTodos();
        showToast(currentTodoBucket === "idea" ? "Idea saved" : "Todo added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function moveTodo(id, bucket) {
    const body = { bucket };
    if (bucket === "today") body.for_date = localISODate();
    try {
        await api.put(`/today/api/todos/${id}`, body);
        await loadTodos();
        showToast(`Moved to ${bucket === "idea" ? "Ideas" : bucket === "today" ? "Today" : "Overall"}`, "success");
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

async function addTodoStep(todoId) {
    const input = document.getElementById(`step-input-${todoId}`);
    const title = (input?.value || "").trim();
    if (!title) return showToast("Enter a step", "error");
    try {
        await api.post(`/today/api/todos/${todoId}/steps`, { title });
        await loadTodos();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function toggleTodoStep(stepId) {
    try {
        await api.post(`/today/api/todo-steps/${stepId}/toggle`, {});
        await loadTodos();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteTodoStep(stepId) {
    try {
        await api.delete(`/today/api/todo-steps/${stepId}`);
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

function formatDeficit(n) {
    if (n > 0) return `${n} kcal deficit`;
    if (n < 0) return `${Math.abs(n)} kcal surplus`;
    return "At maintenance";
}

async function loadNutrition() {
    const [today, week] = await Promise.all([
        api.get("/today/api/nutrition/today"),
        api.get("/today/api/nutrition/week"),
    ]);
    const { targets, totals, deficit, entries, tdee } = today;
    const proPct = targets.protein_goal
        ? Math.min(100, Math.round(totals.protein / targets.protein_goal * 100))
        : 0;

    document.getElementById("cal-label").textContent = `${totals.calories} kcal`;
    document.getElementById("deficit-line").textContent =
        `${formatDeficit(deficit)} · TDEE ${tdee.tdee}`;
    document.getElementById("deficit-line").className =
        `deficit-line ${deficit > 0 ? "is-deficit" : deficit < 0 ? "is-surplus" : ""}`;
    document.getElementById("tdee-breakdown").textContent =
        `TDEE ${tdee.tdee} = ${tdee.baseline} baseline + ${tdee.from_steps} from steps (${tdee.steps.toLocaleString()}) + ${tdee.from_workouts} from workouts`;

    document.getElementById("pro-label").textContent = `${totals.protein} / ${targets.protein_goal} g`;
    document.getElementById("pro-bar").style.width = `${proPct}%`;

    document.getElementById("week-deficit").textContent = formatDeficit(week.total_deficit).replace(" kcal", "");
    document.getElementById("week-deficit-meta").textContent =
        week.days_logged
            ? `${week.days_logged} logged day${week.days_logged === 1 ? "" : "s"} · avg ${formatDeficit(week.avg_deficit)}`
            : "No food logged this week";
    document.getElementById("week-protein-hits").textContent =
        `${week.protein_hit_days}/${week.days_logged || 0}`;

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

// ── STEPS ─────────────────────────────────────────────────────────────────────

async function loadSteps() {
    const [today, week] = await Promise.all([
        api.get("/today/api/steps/today"),
        api.get("/today/api/steps/week"),
    ]);
    document.getElementById("steps-label").textContent =
        `${today.count.toLocaleString()} / ${today.steps_goal.toLocaleString()}`;
    document.getElementById("steps-bar").style.width = `${today.pct}%`;
    document.getElementById("steps-count").value = today.logged ? today.count : "";

    document.getElementById("week-steps-total").textContent = week.total.toLocaleString();
    document.getElementById("week-steps-meta").textContent =
        week.days_logged
            ? `avg ${week.avg.toLocaleString()} · ${week.days_logged} day${week.days_logged === 1 ? "" : "s"}`
            : "No days logged";
    document.getElementById("week-steps-hits").textContent =
        `${week.goal_hit_days}/${week.days_logged || 0}`;
}

async function saveSteps() {
    const raw = document.getElementById("steps-count").value;
    if (raw === "") return showToast("Enter today’s steps", "error");
    const count = Number(raw);
    if (!Number.isFinite(count) || count < 0) return showToast("Invalid step count", "error");
    try {
        await api.put("/today/api/steps/today", { count: Math.round(count) });
        await Promise.all([loadSteps(), loadNutrition()]);
        showToast("Steps saved", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── WORKOUTS ──────────────────────────────────────────────────────────────────

async function loadWorkouts() {
    const data = await api.get("/today/api/workouts/overview");
    document.getElementById("upper-stat").textContent = data.upper.count;
    document.getElementById("upper-meta").textContent =
        `incl. full${data.upper.today ? " · today ✓" : ""}`;
    document.getElementById("lower-stat").textContent = data.lower.count;
    document.getElementById("lower-meta").textContent =
        `incl. full${data.lower.today ? " · today ✓" : ""}`;
    document.getElementById("zone2-stat").textContent = data.zone2.count;
    document.getElementById("zone2-meta").textContent =
        `${data.zone2.minutes} min${data.zone2.today ? " · today ✓" : ""}`;

    const list = document.getElementById("workout-list");
    list.innerHTML = data.workouts.length
        ? data.workouts.map(w => `
            <li class="entry-list-item food-row">
                <div>
                    <div class="entry-list-snippet">
                        <span class="kind-badge kind-${w.kind}">${kindLabel(w.kind)}</span>
                        ${escHtml(w.title || "Session")}
                    </div>
                    <div class="entry-list-date">${escHtml(w.log_date)}${w.duration_minutes ? ` · ${w.duration_minutes} min` : ""}${w.calories_burned ? ` · ${w.calories_burned} kcal` : ""}</div>
                </div>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteWorkout(${w.id})">✕</button>
            </li>`).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No workouts logged this week.</li>`;
}

async function addWorkout() {
    const kind = document.getElementById("workout-kind").value;
    const title = document.getElementById("workout-title").value.trim();
    const mins = document.getElementById("workout-mins").value;
    const kcal = document.getElementById("workout-kcal").value;
    try {
        await api.post("/today/api/workouts", {
            kind,
            title: title || null,
            duration_minutes: mins ? Number(mins) : null,
            calories_burned: kcal !== "" ? Number(kcal) : null,
        });
        document.getElementById("workout-title").value = "";
        document.getElementById("workout-mins").value = "";
        document.getElementById("workout-kcal").value = "";
        await Promise.all([loadWorkouts(), loadNutrition()]);
        showToast("Workout logged", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteWorkout(id) {
    try {
        await api.delete(`/today/api/workouts/${id}`);
        await Promise.all([loadWorkouts(), loadNutrition()]);
    } catch (e) {
        showToast(e.message, "error");
    }
}
