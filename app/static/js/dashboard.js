// Today dashboard — nested todos, nutrition deficit/week, upper/lower/zone2

function localISODate(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

let mealListExpanded = false;
let appSettings = { morning_until: "12:00", evening_from: "18:00" };
let currentTodoBucket = "today";

document.addEventListener("DOMContentLoaded", async () => {
    const today = new Date();
    document.getElementById("today-date").textContent =
        today.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

    applyBucketFormMode();
    await Promise.all([
        loadAppSettings(),
        loadTodos(),
        loadGoals(),
        loadNutrition(),
        loadSteps(),
        loadWorkouts(),
        loadRoutines(),
    ]);
    applyRoutineAutoExpand();
    await loadMorningBrief();
    updateShutdownButton();
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

async function loadAppSettings() {
    try {
        appSettings = await api.get("/design/api/settings");
    } catch (e) {
        appSettings = { morning_until: "12:00", evening_from: "18:00" };
    }
}

function parseHHMM(s) {
    const [h, m] = (s || "0:0").split(":").map(Number);
    return (h || 0) * 60 + (m || 0);
}

function applyRoutineAutoExpand() {
    const now = new Date();
    const mins = now.getHours() * 60 + now.getMinutes();
    const morningUntil = parseHHMM(appSettings.morning_until || "12:00");
    const eveningFrom = parseHHMM(appSettings.evening_from || "18:00");
    const openMorning = mins < morningUntil;
    const openEvening = mins >= eveningFrom;
    setRoutineCollapse("morning", openMorning);
    setRoutineCollapse("evening", openEvening);
    // Midday: both collapsed unless empty
    if (!openMorning && !openEvening) {
        setRoutineCollapse("morning", false);
        setRoutineCollapse("evening", false);
    }
}

function formatPlanHours(minutes, availableHours) {
    const h = Math.floor((minutes || 0) / 60);
    const m = (minutes || 0) % 60;
    const planned = h && m ? `${h}h ${m}m` : h ? `${h}h` : m ? `${m}m` : "0m";
    const avail = availableHours == null ? "—" : `${availableHours}h`;
    return { planned, avail };
}

async function loadMorningBrief() {
    const banner = document.getElementById("morning-brief");
    const textEl = document.getElementById("morning-brief-text");
    if (!banner || !textEl) return;
    try {
        const brief = await api.get("/review/api/morning-brief");
        window._morningBrief = brief;
        updateShutdownButton(brief);

        if (!brief.show_banner) {
            banner.classList.add("hidden");
            return;
        }

        const names = (brief.priorities || []).map(p => p.title).filter(Boolean);
        const pri = names.length
            ? `Your ${names.length} priorit${names.length === 1 ? "y" : "ies"} today: ${names.join(" · ")}`
            : "No priorities set yet — add them above or plan tonight.";
        const { planned, avail } = formatPlanHours(brief.planned_minutes, brief.available_hours);
        const workout = brief.workout_suggestion || "—";
        textEl.textContent = `${pri} · Planned ${planned} / ${avail} free · Workout: ${workout}`;
        banner.classList.remove("hidden");
        // First visit: keep morning routine expanded
        setRoutineCollapse("morning", true);
    } catch (e) {
        banner.classList.add("hidden");
        console.error(e);
    }
}

async function dismissMorningBrief() {
    try {
        await api.post("/review/api/morning-brief/dismiss", {});
        document.getElementById("morning-brief")?.classList.add("hidden");
    } catch (e) {
        showToast(e.message, "error");
    }
}

function updateShutdownButton(brief) {
    const btn = document.getElementById("btn-start-shutdown");
    const badge = document.getElementById("day-complete-badge");
    if (!btn) return;
    const data = brief || window._morningBrief || {};
    const eveningFrom = parseHHMM(data.evening_from || appSettings.evening_from || "18:00");
    const now = new Date();
    const mins = now.getHours() * 60 + now.getMinutes();
    const afterEvening = mins >= eveningFrom;

    if (data.is_complete) {
        btn.classList.add("hidden");
        badge?.classList.remove("hidden");
        return;
    }
    badge?.classList.add("hidden");
    btn.classList.toggle("hidden", !afterEvening);
}

function setRoutineCollapse(routine, open) {
    const el = document.getElementById(`${routine}-routine-card`);
    if (!el || el.classList.contains("hidden")) return;
    el.classList.toggle("open", !!open);
}

function toggleRoutineCollapse(routine) {
    const el = document.getElementById(`${routine}-routine-card`);
    if (!el) return;
    el.classList.toggle("open");
}

function toggleMealList() {
    mealListExpanded = !mealListExpanded;
    const list = document.getElementById("food-list");
    const chev = document.getElementById("meal-collapse-chevron");
    list?.classList.toggle("meal-list-collapsed", !mealListExpanded);
    if (chev) chev.textContent = mealListExpanded ? "▾" : "▸";
}

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
    const more = document.getElementById("planning-more");
    if (more) more.open = true;
    document.querySelectorAll("#main-planning-tabs .tab-btn").forEach(b => b.classList.remove("active"));
    if (btn) btn.classList.add("active");
    document.getElementById("main-tab-todo")?.classList.toggle("active", tab === "todo");
    document.getElementById("main-tab-goals")?.classList.toggle("active", tab === "goals");
    document.getElementById("main-tab-history")?.classList.toggle("active", tab === "history");
    if (tab === "todo") loadTodos();
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
        const tracked = day.tracked || {};
        const deficitClass = day.deficit == null
            ? ""
            : day.deficit > 0 ? "hist-deficit" : day.deficit < 0 ? "hist-surplus" : "hist-even";
        // No calorie deficit pill unless calories were tracked that day
        const deficitText = !tracked.calories || day.deficit == null
            ? `<span class="hist-pill muted">Calories not tracked</span>`
            : `<span class="hist-pill ${deficitClass}">${formatDeficitShort(day.deficit)} kcal</span>`;
        const proteinText = tracked.protein
            ? `${day.protein}g pro${day.protein_hit ? " ✓" : ""}`
            : "Protein —";
        const stepsText = tracked.steps
            ? `${(day.steps || 0).toLocaleString()} steps${day.steps_hit ? " ✓" : ""}`
            : "Steps —";
        const workoutText = tracked.workouts
            ? `${day.workouts_count} workout${day.workouts_count === 1 ? "" : "s"}`
            : "Workouts —";
        const todosText = tracked.todos
            ? `${day.todos_completed} done`
            : "Todos —";
        const selected = historySelectedDate === day.date ? " selected" : "";
        return `
        <li class="history-row${selected}${day.has_activity ? "" : " empty-day"}" onclick="openHistoryDay('${day.date}')">
            <div class="history-row-main">
                <div class="history-row-date">${formatDayLabel(day.date)}</div>
                <div class="history-row-iso text-muted">${escHtml(day.date)}</div>
            </div>
            <div class="history-row-metrics">
                ${deficitText}
                <span class="hist-stat" title="Protein">${proteinText}</span>
                <span class="hist-stat" title="Steps">${stepsText}</span>
                <span class="hist-stat" title="Workouts">${workoutText}</span>
                <span class="hist-stat" title="Todos completed">${todosText}</span>
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
    const tracked = o.tracked || {};
    const deficitLabel = !tracked.calories || o.deficit == null
        ? "Calories not tracked — no deficit"
        : formatDeficit(o.deficit);
    document.getElementById("history-detail-stats").innerHTML = `
        <div class="history-stat-card ${!tracked.calories || o.deficit == null ? "" : o.deficit > 0 ? "is-deficit" : o.deficit < 0 ? "is-surplus" : ""}">
            <div class="week-stat-label">Calorie balance</div>
            <div class="week-stat-value">${!tracked.calories || o.deficit == null ? "—" : formatDeficitShort(o.deficit)}</div>
            <div class="week-stat-meta">${deficitLabel}</div>
        </div>
        <div class="history-stat-card">
            <div class="week-stat-label">TDEE</div>
            <div class="week-stat-value">${o.tdee.tdee}</div>
            <div class="week-stat-meta">${o.tdee.baseline} + ${o.tdee.from_steps} steps + ${o.tdee.from_workouts} workouts</div>
        </div>
        <div class="history-stat-card">
            <div class="week-stat-label">Intake / protein</div>
            <div class="week-stat-value">${tracked.calories ? o.intake_calories : "—"}</div>
            <div class="week-stat-meta">${tracked.protein ? `${o.protein} / ${o.protein_goal} g${o.protein_hit ? " · on target" : ""}` : "Protein not tracked"}</div>
        </div>
        <div class="history-stat-card">
            <div class="week-stat-label">Activity</div>
            <div class="week-stat-value">${tracked.steps ? (o.steps || 0).toLocaleString() : "—"}</div>
            <div class="week-stat-meta">${tracked.workouts ? `${o.workouts_count} workouts` : "Workouts —"} · ${tracked.todos ? `${o.todos_completed} todos done` : "Todos —"}</div>
        </div>
    `;

    document.getElementById("hist-steps").value = tracked.steps ? (o.steps || 0) : "";

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

let todoMeta = {};
let matrixView = false;
let lastTodos = [];

const LEVEL_LABEL = { 1: "Low", 2: "Med", 3: "High" };
const ESTIMATE_LABEL = { 15: "15m", 30: "30m", 60: "1h", 120: "2h", 240: "½ day" };

function setSeg(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.dataset.value = String(value);
    el.querySelectorAll("button").forEach(b => {
        b.classList.toggle("active", Number(b.dataset.v) === value);
    });
}

function formatMinutes(m) {
    m = Math.max(0, Math.round(m || 0));
    const h = Math.floor(m / 60);
    const mins = m % 60;
    if (h && mins) return `${h}h ${mins}m`;
    if (h) return `${h}h`;
    return `${mins}m`;
}

function applyBucketFormMode() {
    const copy = BUCKET_COPY[currentTodoBucket];
    document.getElementById("todo-bucket-title").textContent = copy.title;
    document.getElementById("bucket-hint").textContent = copy.hint;
    document.getElementById("todo-title").placeholder = copy.placeholder;
    document.getElementById("todo-add-btn").textContent = copy.addLabel;

    const isIdea = currentTodoBucket === "idea";
    const isToday = currentTodoBucket === "today";
    document.getElementById("todo-step-field").classList.toggle("hidden", isIdea);
    document.getElementById("todo-notes-field").classList.toggle("hidden", !isIdea);
    document.getElementById("todo-metrics-fields").classList.toggle("hidden", isIdea);
    document.getElementById("todo-estimate-field")?.classList.toggle("hidden", isIdea);
    document.getElementById("todo-due-field").classList.toggle("hidden", isIdea);
    document.getElementById("todo-goal-field")?.classList.toggle("hidden", isIdea);
    document.getElementById("todo-title-label").textContent = isIdea ? "Idea" : "Task";
    document.getElementById("plan-time-bar")?.classList.toggle("hidden", !isToday);
    document.getElementById("matrix-toggle")?.classList.toggle("hidden", currentTodoBucket !== "overall");
    if (currentTodoBucket !== "overall") {
        matrixView = false;
        document.getElementById("todo-matrix")?.classList.add("hidden");
        document.getElementById("todo-list")?.classList.remove("hidden");
    }
}

async function populateGoalSelect(selectEl, selectedId) {
    if (!selectEl) return;
    try {
        if (!window._activeGoals) {
            window._activeGoals = await api.get("/today/api/goals?status=active");
        }
        const goals = window._activeGoals || [];
        selectEl.innerHTML = `<option value="">—</option>` + goals.map(g =>
            `<option value="${g.id}" ${String(selectedId || "") === String(g.id) ? "selected" : ""}>${escHtml(g.title)}</option>`
        ).join("");
    } catch (e) {
        selectEl.innerHTML = `<option value="">—</option>`;
    }
}

function toggleTodoForm(show) {
    const form = document.getElementById("todo-form");
    const open = show === undefined ? form.classList.contains("hidden") : show;
    form.classList.toggle("hidden", !open);
    if (open) {
        applyBucketFormMode();
        setSeg("todo-importance-seg", 2);
        setSeg("todo-effort-seg", 2);
        populateGoalSelect(document.getElementById("todo-goal"), null);
        document.getElementById("todo-title").focus();
    }
}

function toggleMatrixView() {
    matrixView = !matrixView;
    const btn = document.getElementById("matrix-toggle");
    if (btn) btn.textContent = matrixView ? "List" : "Matrix";
    renderTodoViews(lastTodos);
}

function updatePlanTimeBar(meta) {
    const label = document.getElementById("plan-time-label");
    const warn = document.getElementById("plan-time-warn");
    const input = document.getElementById("available-hours-input");
    if (!label || !meta) return;
    const planned = meta.planned_minutes || 0;
    const availH = meta.available_hours ?? 4;
    const availM = Math.round(availH * 60);
    label.textContent = `Planned: ${formatMinutes(planned)} / Available: ${formatMinutes(availM)}`;
    warn?.classList.toggle("hidden", planned <= availM);
    if (input) input.value = availH;
}

async function saveAvailableHours() {
    const raw = document.getElementById("available-hours-input").value;
    try {
        await api.put("/today/api/day-plan", {
            date: localISODate(),
            available_hours: raw === "" ? null : Number(raw),
        });
        await loadTodos();
        showToast("Available hours saved", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function loadTodos() {
    let url = `/today/api/todos?bucket=${currentTodoBucket}`;
    if (currentTodoBucket === "today") {
        url += `&date=${localISODate()}`;
    }
    const data = await api.get(url);
    // Back-compat if API ever returns a bare array
    const todos = Array.isArray(data) ? data : (data.todos || []);
    todoMeta = Array.isArray(data) ? {} : (data.meta || {});
    lastTodos = todos;
    if (todoMeta.rolled_forward) {
        showToast(`Rolled ${todoMeta.rolled_forward} unfinished task${todoMeta.rolled_forward === 1 ? "" : "s"} to today`, "success");
    }
    updatePlanTimeBar(todoMeta);
    await renderTodoViews(todos);
}

async function renderTodoViews(todos) {
    const list = document.getElementById("todo-list");
    const empty = document.getElementById("todo-empty");
    const matrix = document.getElementById("todo-matrix");
    if (!todos.length) {
        list.innerHTML = "";
        if (matrix) { matrix.innerHTML = ""; matrix.classList.add("hidden"); }
        list.classList.remove("hidden");
        empty.classList.remove("hidden");
        empty.textContent = currentTodoBucket === "idea"
            ? "No ideas yet — capture one above."
            : currentTodoBucket === "today"
                ? "No tasks for today — add one above."
                : "No overall todos — add one above.";
        return;
    }
    empty.classList.add("hidden");
    if (matrixView && currentTodoBucket === "overall") {
        list.classList.add("hidden");
        matrix.classList.remove("hidden");
        matrix.innerHTML = matrixHtml(todos);
        await fillTodoGoalSelects(matrix);
    } else {
        matrix?.classList.add("hidden");
        list.classList.remove("hidden");
        list.innerHTML = todos.map(todoItemHtml).join("");
        enableTodoDrag(list);
        await fillTodoGoalSelects(list);
    }
}

async function fillTodoGoalSelects(root) {
    const selects = (root || document).querySelectorAll("select[data-todo-goal]");
    if (!selects.length) return;
    try {
        window._activeGoals = await api.get("/today/api/goals?status=active");
    } catch (e) {
        return;
    }
    const goals = window._activeGoals || [];
    selects.forEach(sel => {
        const selected = sel.dataset.selected || "";
        sel.innerHTML = `<option value="">—</option>` + goals.map(g =>
            `<option value="${g.id}" ${String(selected) === String(g.id) ? "selected" : ""}>${escHtml(g.title)}</option>`
        ).join("");
    });
}

function matrixQuadrant(imp, eff) {
    const highImp = imp >= 3;
    const lowEff = eff <= 1;
    if (highImp && lowEff) return "quick";
    if (highImp && !lowEff) return "bets";
    if (!highImp && lowEff) return "fill";
    return "reconsider";
}

function matrixHtml(todos) {
    const buckets = {
        quick: { title: "Quick wins", hint: "High imp · Low effort", items: [] },
        bets: { title: "Big bets", hint: "High imp · High effort", items: [] },
        fill: { title: "Fill-ins", hint: "Low imp · Low effort", items: [] },
        reconsider: { title: "Reconsider", hint: "Low imp · High effort", items: [] },
    };
    for (const t of todos) {
        buckets[matrixQuadrant(t.importance, t.effort)].items.push(t);
    }
    return Object.values(buckets).map(b => `
        <div class="matrix-cell">
            <div class="matrix-cell-title">${b.title}</div>
            <div class="matrix-cell-hint text-muted">${b.hint}</div>
            <ul class="todo-tree">${b.items.map(todoItemHtml).join("") || `<li class="text-muted">—</li>`}</ul>
        </div>`).join("");
}

function kindLabel(kind) {
    return ({ zone2: "Zone 2", full: "Full", upper: "Upper", lower: "Lower" })[kind] || kind;
}

function segInlineHtml(todoId, field, value) {
    return `<div class="seg-control seg-sm" data-todo="${todoId}" data-field="${field}">
        ${[1, 2, 3].map(v => `
            <button type="button" class="${v === value ? "active" : ""}"
                onclick="updateTodoField(${todoId},'${field}',${v})">${LEVEL_LABEL[v]}</button>`).join("")}
    </div>`;
}

function estimateSelectHtml(todoId, value) {
    const opts = ["", 15, 30, 60, 120, 240].map(v => {
        const label = v === "" ? "—" : ESTIMATE_LABEL[v];
        const sel = String(value || "") === String(v) ? "selected" : "";
        return `<option value="${v}" ${sel}>${label}</option>`;
    }).join("");
    return `<select class="estimate-select" onchange="updateTodoField(${todoId},'estimate_minutes',this.value===''?null:Number(this.value))">${opts}</select>`;
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

function rolloverPromptHtml(t) {
    if ((t.rollover_count || 0) < 3 || t.bucket !== "today") return "";
    return `<div class="rollover-prompt">
        Rolled ${t.rollover_count}× —
        <button class="btn btn-ghost btn-sm" type="button" onclick="focusBreakDown(${t.id})">Break it down</button>
        <button class="btn btn-ghost btn-sm" type="button" onclick="moveTodo(${t.id},'overall')">Move to Overall</button>
        <button class="btn btn-ghost btn-sm" type="button" onclick="moveTodo(${t.id},'idea')">Move to Ideas</button>
        <button class="btn btn-danger btn-sm" type="button" onclick="deleteTodo(${t.id})">Delete</button>
    </div>`;
}

function focusBreakDown(todoId) {
    const input = document.getElementById(`step-input-${todoId}`);
    input?.focus();
    input?.scrollIntoView({ behavior: "smooth", block: "center" });
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

    const rollBadge = (t.rollover_count || 0) > 0
        ? `<span class="rollover-badge" title="Rolled over ${t.rollover_count} time(s)">↻${t.rollover_count}</span>`
        : "";
    const goalTag = t.goal_title
        ? `<span class="goal-tag" title="Linked goal">${escHtml(t.goal_title)}</span>`
        : "";

    const metrics = isIdea
        ? (t.notes ? `<div class="check-meta">${escHtml(t.notes)}</div>` : "")
        : `<div class="todo-metrics">
                <span class="metric" title="Importance"><span class="metric-label">Imp</span>${segInlineHtml(t.id, "importance", t.importance)}</span>
                <span class="metric" title="Effort"><span class="metric-label">Eff</span>${segInlineHtml(t.id, "effort", t.effort)}</span>
                <span class="metric" title="Estimate">${estimateSelectHtml(t.id, t.estimate_minutes)}</span>
                ${stepProgress}
                ${t.due_date ? `<span class="check-meta">Due ${escHtml(t.due_date)}</span>` : ""}
           </div>
           <div class="todo-goal-row">
                <label class="text-muted">Goal
                    <select class="goal-link-select" onchange="updateTodoField(${t.id},'goal_id',this.value===''?null:Number(this.value))"
                        data-todo-goal="${t.id}" data-selected="${t.goal_id || ""}">
                        <option value="">—</option>
                    </select>
                </label>
           </div>`;

    const addStep = isIdea ? "" : `
        <ul class="todo-steps">${stepsHtml}</ul>
        <div class="todo-add-step">
            <input type="text" id="step-input-${t.id}" placeholder="Add a step…" onkeydown="if(event.key==='Enter'){event.preventDefault();addTodoStep(${t.id})}">
            <button class="btn btn-secondary btn-sm" type="button" onclick="addTodoStep(${t.id})">+ Step</button>
        </div>`;

    return `
    <li class="todo-block ${t.done ? "done" : ""}" id="todo-${t.id}" draggable="${!isIdea}" data-id="${t.id}">
        <div class="todo-row">
            <div class="check-box ${t.done ? "checked" : ""}" onclick="toggleTodo(${t.id})">${t.done ? "✓" : ""}</div>
            <div class="todo-body">
                <div class="check-label">${escHtml(t.title)} ${rollBadge} ${goalTag}</div>
                ${metrics}
                ${rolloverPromptHtml(t)}
                ${moveButtonsHtml(t)}
            </div>
            <button class="btn btn-danger btn-sm" type="button" onclick="deleteTodo(${t.id})" title="Delete">✕</button>
        </div>
        ${addStep}
    </li>`;
}

function enableTodoDrag(list) {
    let dragId = null;
    list.querySelectorAll(".todo-block[draggable=true]").forEach(el => {
        el.addEventListener("dragstart", () => { dragId = el.dataset.id; el.classList.add("dragging"); });
        el.addEventListener("dragend", () => { el.classList.remove("dragging"); dragId = null; });
        el.addEventListener("dragover", e => { e.preventDefault(); el.classList.add("drag-over"); });
        el.addEventListener("dragleave", () => el.classList.remove("drag-over"));
        el.addEventListener("drop", async e => {
            e.preventDefault();
            el.classList.remove("drag-over");
            if (!dragId || dragId === el.dataset.id) return;
            const ids = [...list.querySelectorAll(".todo-block")].map(n => Number(n.dataset.id));
            const from = ids.indexOf(Number(dragId));
            const to = ids.indexOf(Number(el.dataset.id));
            if (from < 0 || to < 0) return;
            ids.splice(to, 0, ids.splice(from, 1)[0]);
            try {
                await api.post("/today/api/todos/reorder", {
                    bucket: currentTodoBucket,
                    date: localISODate(),
                    ordered_ids: ids,
                });
                await loadTodos();
            } catch (err) {
                showToast(err.message, "error");
            }
        });
    });
}

async function updateTodoField(id, field, value) {
    try {
        await api.put(`/today/api/todos/${id}`, { [field]: value });
        await loadTodos();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function addTodo(extra = {}) {
    const title = document.getElementById("todo-title").value.trim();
    if (!title) return showToast(currentTodoBucket === "idea" ? "Enter an idea" : "Enter a task", "error");

    const payload = { title, bucket: currentTodoBucket, ...extra };
    if (currentTodoBucket === "idea") {
        const notes = document.getElementById("todo-notes").value.trim();
        if (notes) payload.notes = notes;
    } else {
        const firstStep = document.getElementById("todo-first-step").value.trim();
        payload.importance = Number(document.getElementById("todo-importance-seg").dataset.value || 2);
        payload.effort = Number(document.getElementById("todo-effort-seg").dataset.value || 2);
        const est = document.getElementById("todo-estimate").value;
        if (est) payload.estimate_minutes = Number(est);
        payload.due_date = document.getElementById("todo-due").value || null;
        const goalId = document.getElementById("todo-goal")?.value;
        if (goalId) payload.goal_id = Number(goalId);
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
        document.getElementById("todo-estimate").value = "";
        const goalSel = document.getElementById("todo-goal");
        if (goalSel) goalSel.value = "";
        setSeg("todo-importance-seg", 2);
        setSeg("todo-effort-seg", 2);
        toggleTodoForm(false);
        await loadTodos();
        showToast(currentTodoBucket === "idea" ? "Idea saved" : "Todo added", "success");
    } catch (e) {
        if (e.data?.code === "cap_exceeded") {
            await handleCapExceeded(payload, e.data);
            return;
        }
        showToast(e.message, "error");
    }
}

async function handleCapExceeded(payload, data) {
    const open = data.open_todos || [];
    const names = open.map(t => `• ${t.title}`).join("\n");
    const choice = window.prompt(
        `Today is capped at ${data.todo_cap} tasks.\n\nOpen tasks:\n${names}\n\nType a task number (1–${open.length}) to swap it out to Overall,\nor type OVERALL to add this new task to Overall instead.`,
    );
    if (choice == null) return;
    const trimmed = choice.trim().toLowerCase();
    if (trimmed === "overall") {
        payload.bucket = "overall";
        delete payload.for_date;
        payload.force = true;
        try {
            await api.post("/today/api/todos", payload);
            toggleTodoForm(false);
            currentTodoBucket = "overall";
            applyBucketFormMode();
            await loadTodos();
            showToast("Added to Overall", "success");
        } catch (err) {
            showToast(err.message, "error");
        }
        return;
    }
    const idx = Number(choice) - 1;
    if (!Number.isInteger(idx) || idx < 0 || idx >= open.length) {
        showToast("Cancelled — invalid choice", "error");
        return;
    }
    payload.swap_out_id = open[idx].id;
    try {
        await api.post("/today/api/todos", payload);
        toggleTodoForm(false);
        await loadTodos();
        showToast(`Swapped out “${open[idx].title}” → Overall`, "success");
    } catch (err) {
        showToast(err.message, "error");
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
        if (e.data?.code === "cap_exceeded") {
            showToast(`Today is full (cap ${e.data.todo_cap}). Free a slot first.`, "error");
            return;
        }
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
    if (open) {
        setGoalType("project");
        document.getElementById("goal-title").focus();
    }
}

function setGoalType(type) {
    const seg = document.getElementById("goal-type-seg");
    if (seg) {
        seg.dataset.value = type;
        seg.querySelectorAll("button").forEach(b => {
            b.classList.toggle("active", b.dataset.v === type);
        });
    }
    document.getElementById("goal-metric-fields")?.classList.toggle("hidden", type !== "metric");
}

function activityLabel(days) {
    if (days == null || days >= 999) return "No activity yet";
    if (days === 0) return "Last activity today";
    if (days === 1) return "Last activity 1 day ago";
    return `Last activity ${days} days ago`;
}

function goalCardHtml(g) {
    const typeBadge = g.goal_type === "metric"
        ? `<span class="badge">Metric</span>`
        : `<span class="badge">Project</span>`;
    const stalled = g.stalled ? `<span class="goal-stalled">Stalled</span>` : "";
    const why = g.why ? `<div class="check-meta">${escHtml(g.why)}</div>` : "";
    const target = g.target_date ? `<div class="check-meta">Target ${escHtml(g.target_date)}</div>` : "";
    let metricLine = "";
    if (g.goal_type === "metric" && g.metric) {
        const cur = g.metric.current == null ? "—" : g.metric.current;
        const note = g.metric.note ? ` · ${escHtml(g.metric.note)}` : "";
        metricLine = `<div class="check-meta">${escHtml(g.metric.label || "")}: ${cur} / ${g.metric_target ?? "—"}${note}</div>`;
    }
    const commitments = (g.commitments || []).map(c => `
        <li class="goal-commitment ${c.done ? "done" : ""}">
            <div class="check-box ${c.done ? "checked" : ""}" onclick="toggleCommitment(${c.id}, ${!c.done})">${c.done ? "✓" : ""}</div>
            <span class="goal-commitment-text">${escHtml(c.text)}</span>
            <button class="btn btn-danger btn-sm" type="button" onclick="deleteCommitment(${c.id})" title="Remove">✕</button>
        </li>`).join("");

    return `
    <li class="goal-item ${g.stalled ? "is-stalled" : ""}" id="goal-${g.id}">
        <div class="goal-card-top">
            <div class="goal-main">
                <div class="goal-title">${escHtml(g.title)} ${typeBadge} ${stalled}</div>
                ${why}${target}${metricLine}
                <div class="goal-progress-wrap">
                    <div class="progress-wrap"><div class="progress-bar" style="width:${g.progress_pct || 0}%"></div></div>
                    <span class="check-meta">${g.progress_pct || 0}%</span>
                </div>
                <div class="check-meta">${activityLabel(g.last_activity_days)}
                    ${g.linked_todos ? ` · ${g.linked_done}/${g.linked_todos} linked tasks done` : ""}</div>
            </div>
            <div class="goal-actions">
                <button class="btn btn-secondary btn-sm" type="button" onclick="completeGoal(${g.id})">Done</button>
                <button class="btn btn-danger btn-sm" type="button" onclick="deleteGoal(${g.id})">✕</button>
            </div>
        </div>
        <div class="goal-commitments">
            <div class="goal-commitments-head">This week’s commitments</div>
            <ul class="goal-commitment-list">${commitments || `<li class="text-muted">None yet</li>`}</ul>
            <div class="todo-add-step">
                <input type="text" id="commit-input-${g.id}" placeholder="Add a weekly commitment…"
                    onkeydown="if(event.key==='Enter'){event.preventDefault();addCommitment(${g.id})}">
                <button class="btn btn-secondary btn-sm" type="button" onclick="addCommitment(${g.id})">+ Commit</button>
            </div>
        </div>
    </li>`;
}

async function loadGoals() {
    try {
        const goals = await api.get("/today/api/goals?status=active");
        window._activeGoals = goals;
        const list = document.getElementById("goal-list");
        const empty = document.getElementById("goal-empty");
        if (!goals.length) {
            list.innerHTML = "";
            empty.classList.remove("hidden");
            return;
        }
        empty.classList.add("hidden");
        list.innerHTML = goals.map(goalCardHtml).join("");
    } catch (e) {
        showToast(e.message, "error");
        document.getElementById("goal-empty")?.classList.remove("hidden");
    }
}

async function addGoal() {
    const title = document.getElementById("goal-title").value.trim();
    if (!title) return showToast("Enter a goal", "error");
    const why = document.getElementById("goal-why").value.trim() || null;
    const target_date = document.getElementById("goal-target").value || null;
    const goal_type = document.getElementById("goal-type-seg")?.dataset.value || "project";
    const payload = { title, why, target_date, goal_type };
    if (goal_type === "metric") {
        payload.metric_key = document.getElementById("goal-metric-key").value;
        const raw = document.getElementById("goal-metric-target").value;
        if (!raw) return showToast("Enter a metric target", "error");
        payload.metric_target = Number(raw);
    }
    try {
        await api.post("/today/api/goals", payload);
        document.getElementById("goal-title").value = "";
        document.getElementById("goal-why").value = "";
        document.getElementById("goal-target").value = "";
        document.getElementById("goal-metric-target").value = "";
        toggleGoalForm(false);
        window._activeGoals = null;
        await loadGoals();
        showToast("Goal added", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function addCommitment(goalId) {
    const input = document.getElementById(`commit-input-${goalId}`);
    const text = input?.value.trim();
    if (!text) return showToast("Enter a commitment", "error");
    try {
        await api.post(`/today/api/goals/${goalId}/commitments`, { text });
        if (input) input.value = "";
        await loadGoals();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function toggleCommitment(id, done) {
    try {
        await api.put(`/today/api/commitments/${id}`, { done });
        await loadGoals();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteCommitment(id) {
    try {
        await api.delete(`/today/api/commitments/${id}`);
        await loadGoals();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function completeGoal(id) {
    try {
        await api.put(`/today/api/goals/${id}`, { status: "done" });
        window._activeGoals = null;
        await loadGoals();
        showToast("Goal completed", "success");
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function deleteGoal(id) {
    try {
        await api.delete(`/today/api/goals/${id}`);
        window._activeGoals = null;
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

function setGoalLink(el, text) {
    el.innerHTML = `<a class="goal-unset-link" href="/design/#panel-nutrition">${escHtml(text)}</a>`;
}

async function loadNutrition() {
    const [today, week] = await Promise.all([
        api.get("/today/api/nutrition/today"),
        api.get("/today/api/nutrition/week"),
    ]);
    const { targets, totals, deficit, entries, tdee, food_logged } = today;
    const proteinGoal = targets.protein_goal;
    const proteinSet = proteinGoal != null && proteinGoal > 0;
    const proPct = proteinSet
        ? Math.min(100, Math.round(totals.protein / proteinGoal * 100))
        : 0;

    document.getElementById("cal-label").textContent = food_logged
        ? `${totals.calories} kcal in`
        : "Not tracked";
    const remainingEl = document.getElementById("cal-remaining");
    if (remainingEl) {
        if (food_logged) {
            const rem = tdee.tdee - totals.calories;
            remainingEl.textContent = rem >= 0 ? `${rem}` : `${rem}`;
        } else {
            remainingEl.textContent = String(tdee.tdee);
        }
    }
    if (food_logged && deficit != null) {
        document.getElementById("deficit-line").textContent =
            `${formatDeficit(deficit)} · TDEE ${tdee.tdee}`;
        document.getElementById("deficit-line").className =
            `deficit-line ${deficit > 0 ? "is-deficit" : deficit < 0 ? "is-surplus" : ""}`;
    } else {
        document.getElementById("deficit-line").textContent =
            food_logged ? `TDEE ${tdee.tdee}` : "Log food to track remaining";
        document.getElementById("deficit-line").className = "deficit-line";
    }
    document.getElementById("tdee-breakdown").textContent =
        `TDEE ${tdee.tdee} = ${tdee.baseline} + ${tdee.from_steps} steps + ${tdee.from_workouts} workouts`;

    const proLabel = document.getElementById("pro-label");
    if (!proteinSet) {
        setGoalLink(proLabel, "Set goal →");
        document.getElementById("pro-bar").style.width = "0%";
    } else {
        proLabel.textContent = food_logged
            ? `${totals.protein} / ${proteinGoal} g`
            : `— / ${proteinGoal} g`;
        document.getElementById("pro-bar").style.width = food_logged ? `${proPct}%` : "0%";
    }

    const completeDays = week.days_complete ?? week.days_logged ?? 0;
    if (completeDays) {
        document.getElementById("week-deficit").textContent =
            formatDeficit(week.total_deficit).replace(" kcal", "");
        document.getElementById("week-deficit-meta").textContent =
            `${completeDays} complete day${completeDays === 1 ? "" : "s"} · avg ${formatDeficit(week.avg_deficit)}`;
    } else {
        document.getElementById("week-deficit").textContent = "—";
        document.getElementById("week-deficit-meta").textContent =
            "No complete days yet this week";
    }
    document.getElementById("week-protein-hits").textContent =
        `${week.protein_hit_days}/${completeDays || 0}`;

    const todayLine = document.getElementById("week-today-nutrition");
    if (todayLine && week.today) {
        const t = week.today;
        if (t.logged && t.deficit != null) {
            todayLine.textContent = `Today (in progress): ${formatDeficit(t.deficit)} · ${t.protein}g protein`;
        } else if (t.logged) {
            todayLine.textContent = `Today (in progress): ${t.calories} kcal logged`;
        } else {
            todayLine.textContent = "Today (in progress): not logged yet";
        }
    }

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
    list.classList.toggle("meal-list-collapsed", !mealListExpanded);
    const mealLabel = document.getElementById("meal-collapse-label");
    if (mealLabel) {
        const n = entries.length;
        mealLabel.textContent = `${n} entr${n === 1 ? "y" : "ies"} · ${totals.calories} kcal`;
    }
    const chev = document.getElementById("meal-collapse-chevron");
    if (chev) chev.textContent = mealListExpanded ? "▾" : "▸";
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
    const stepsLabel = document.getElementById("steps-label");
    const goalSet = today.goal_set && today.steps_goal != null;
    if (!goalSet) {
        setGoalLink(stepsLabel, "Set goal →");
        document.getElementById("steps-bar").style.width = "0%";
    } else {
        stepsLabel.textContent =
            `${today.count.toLocaleString()} / ${today.steps_goal.toLocaleString()}`;
        document.getElementById("steps-bar").style.width = `${today.pct}%`;
    }
    document.getElementById("steps-count").value = today.logged ? today.count : "";

    document.getElementById("week-steps-total").textContent = week.total.toLocaleString();
    document.getElementById("week-steps-meta").textContent =
        week.days_logged
            ? `avg ${week.avg.toLocaleString()} · ${week.days_logged} complete logged day${week.days_logged === 1 ? "" : "s"}`
            : "No complete logged days";
    // Only logged days in the denominator (never unlogged misses)
    document.getElementById("week-steps-hits").textContent =
        week.days_logged
            ? `${week.goal_hit_days}/${week.days_logged}`
            : "—";

    const todayLine = document.getElementById("week-today-steps");
    if (todayLine && week.today) {
        todayLine.textContent = week.today.logged
            ? `Today (in progress): ${week.today.count.toLocaleString()} steps`
            : "Today (in progress): not logged yet";
    }
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

function workoutRowHtml(w, { showDate = false } = {}) {
    return `
    <li class="entry-list-item food-row">
        <div>
            <div class="entry-list-snippet">
                <span class="kind-badge kind-${w.kind}">${kindLabel(w.kind)}</span>
                ${escHtml(w.title || "Session")}
            </div>
            <div class="entry-list-date">${showDate ? `${escHtml(w.log_date)} · ` : ""}${w.duration_minutes ? `${w.duration_minutes} min` : ""}${w.calories_burned ? ` · ${w.calories_burned} kcal` : ""}</div>
        </div>
        <button class="btn btn-danger btn-sm" type="button" onclick="deleteWorkout(${w.id})">✕</button>
    </li>`;
}

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

    const weekList = data.week_workouts || data.workouts || [];
    const todayList = data.today_workouts || [];

    document.getElementById("workout-week-list").innerHTML = weekList.length
        ? weekList.map(w => workoutRowHtml(w, { showDate: true })).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No workouts logged this week.</li>`;

    document.getElementById("workout-today-list").innerHTML = todayList.length
        ? todayList.map(w => workoutRowHtml(w)).join("")
        : `<li class="text-muted" style="padding:var(--space-sm) 0">No workout logged today — add one above.</li>`;
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

// ── ROUTINES (merged from Tracker) ────────────────────────────────────────────

const ROUTINES = ["morning", "evening", "daily"];

async function loadRoutines() {
    try {
        const data = await api.post("/tracker/api/today/init", {});
        renderRoutineCompletions(data.completions || []);
    } catch (e) {
        showToast(e.message || "Couldn’t load routines", "error");
    }
}

function renderRoutineCompletions(completions) {
    for (const routine of ROUTINES) {
        const items = completions.filter(c => c.routine === routine);
        if (routine === "daily") {
            const dailyCard = document.getElementById("daily-routine-card");
            if (dailyCard) {
                if (items.length === 0) {
                    dailyCard.classList.add("hidden");
                    continue;
                }
                dailyCard.classList.remove("hidden");
            }
        }
        renderRoutineChecklist(routine, items);
        updateRoutineProgress(routine, items);
    }
}

function renderRoutineChecklist(routine, completions) {
    const list = document.getElementById(`${routine}-checklist`);
    if (!list) return;
    if (completions.length === 0) {
        list.innerHTML = `<li class="text-muted" style="padding:var(--space-sm) 0">No steps — add some in <a href="/design/">Design</a>.</li>`;
        return;
    }
    list.innerHTML = completions.map(c => routineItemHtml(c)).join("");
}

function routineItemHtml(c) {
    const done = c.completed;
    const durText = c.step_duration ? `<div class="check-meta">${c.step_duration} min</div>` : "";
    const descText = c.step_description ? `<div class="check-meta">${escHtml(c.step_description)}</div>` : "";
    return `
    <li class="check-item ${done ? "done" : ""}" id="item-${c.id}">
        <div class="check-box ${done ? "checked" : ""}" onclick="toggleRoutineItem(${c.id})">
            ${done ? "✓" : ""}
        </div>
        <div>
            <div class="check-label">${escHtml(c.step_title)}</div>
            ${descText}${durText}
        </div>
    </li>`;
}

function updateRoutineProgress(routine, completions) {
    const total = completions.length;
    const done = completions.filter(c => c.completed).length;
    const pct = total > 0 ? Math.round(done / total * 100) : 0;
    const text = document.getElementById(`${routine}-progress-text`);
    const bar = document.getElementById(`${routine}-progress-bar`);
    if (text) text.textContent = `${done} / ${total}`;
    if (bar) bar.style.width = `${pct}%`;
}

async function toggleRoutineItem(completionId) {
    try {
        const updated = await api.post(`/tracker/api/completion/${completionId}/toggle`, {});
        const li = document.getElementById(`item-${completionId}`);
        if (li) li.outerHTML = routineItemHtml(updated);
        const data = await api.get("/tracker/api/today");
        for (const routine of ROUTINES) {
            updateRoutineProgress(
                routine,
                (data.completions || []).filter(c => c.routine === routine),
            );
        }
    } catch (e) {
        showToast(e.message, "error");
    }
}
