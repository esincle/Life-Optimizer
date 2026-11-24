// Tracker page logic — morning, evening, and daily checklists

document.addEventListener("DOMContentLoaded", async () => {
    const today = new Date();
    document.getElementById("tracker-date").textContent =
        today.toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

    await loadToday();
    loadStreaks();
    loadHistory();
});

const ROUTINES = ["morning", "evening", "daily"];

function badgeClass(routine) {
    if (routine === "morning") return "badge-morning";
    if (routine === "evening") return "badge-evening";
    return "badge-daily";
}

// ── TODAY'S CHECKLISTS ────────────────────────────────────────────────────────

async function loadToday() {
    const data = await api.post("/tracker/api/today/init", {});
    renderCompletions(data.completions);
}

function renderCompletions(completions) {
    for (const routine of ROUTINES) {
        const items = completions.filter(c => c.routine === routine);
        renderChecklist(routine, items);
        updateProgress(routine, items);
    }
}

function renderChecklist(routine, completions) {
    const list = document.getElementById(`${routine}-checklist`);
    if (completions.length === 0) {
        list.innerHTML = `<li class="text-muted" style="padding:var(--space-sm) 0">No steps — go to Design to add some.</li>`;
        return;
    }
    list.innerHTML = completions.map(c => checkItemHtml(c)).join("");
}

function checkItemHtml(c) {
    const done = c.completed;
    const durText = c.step_duration ? `<div class="check-meta">${c.step_duration} min</div>` : "";
    const descText = c.step_description ? `<div class="check-meta">${escHtml(c.step_description)}</div>` : "";
    return `
    <li class="check-item ${done ? "done" : ""}" id="item-${c.id}">
        <div class="check-box ${done ? "checked" : ""}" onclick="toggleItem(${c.id})">
            ${done ? "✓" : ""}
        </div>
        <div>
            <div class="check-label">${escHtml(c.step_title)}</div>
            ${descText}${durText}
        </div>
    </li>`;
}

function updateProgress(routine, completions) {
    const total = completions.length;
    const done = completions.filter(c => c.completed).length;
    const pct = total > 0 ? Math.round(done / total * 100) : 0;
    document.getElementById(`${routine}-progress-text`).textContent = `${done} / ${total} done`;
    document.getElementById(`${routine}-progress-bar`).style.width = `${pct}%`;
}

async function toggleItem(completionId) {
    try {
        const updated = await api.post(`/tracker/api/completion/${completionId}/toggle`, {});
        const li = document.getElementById(`item-${completionId}`);
        li.outerHTML = checkItemHtml(updated);
        const data = await api.get("/tracker/api/today");
        for (const routine of ROUTINES) {
            updateProgress(routine, data.completions.filter(c => c.routine === routine));
        }
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── STREAKS ───────────────────────────────────────────────────────────────────

async function loadStreaks() {
    try {
        const streaks = await api.get("/tracker/api/streaks");
        const grid = document.getElementById("streak-grid");
        if (streaks.length === 0) {
            grid.innerHTML = `<p class="text-muted">Add routine steps in Design to start tracking streaks.</p>`;
            return;
        }
        grid.innerHTML = streaks.map(s => `
            <div class="streak-card">
                <div class="streak-number">${s.streak}</div>
                <div class="streak-label">${escHtml(s.title)}</div>
                <div class="badge ${badgeClass(s.routine)}" style="margin-top:4px">${s.routine}</div>
            </div>`).join("");
    } catch (e) {
        console.error("Streaks:", e);
    }
}

// ── HISTORY CALENDAR ──────────────────────────────────────────────────────────

async function loadHistory() {
    try {
        const history = await api.get("/tracker/api/history?days=35");
        renderCalendar(history);
    } catch (e) {
        console.error("History:", e);
    }
}

function pctBucket(morning, evening, daily) {
    const parts = [morning, evening, daily].filter(p => p !== undefined);
    const avg = parts.reduce((a, b) => a + b, 0) / (parts.length || 1);
    if (avg === 0)   return "0";
    if (avg < 30)    return "low";
    if (avg < 70)    return "mid";
    if (avg < 100)   return "high";
    return "full";
}

function renderCalendar(history) {
    const grid = document.getElementById("calendar-grid");
    const days = [...history].reverse();
    if (days.length === 0) { grid.innerHTML = ""; return; }

    const firstDate = new Date(days[0].date + "T00:00:00");
    const startDow = firstDate.getDay();
    let cells = "";
    for (let i = 0; i < startDow; i++) {
        cells += `<div class="calendar-day empty"></div>`;
    }

    for (const d of days) {
        const bucket = pctBucket(d.morning_pct, d.evening_pct, d.daily_pct || 0);
        const journalClass = d.has_journal ? " has-journal" : "";
        const dateObj = new Date(d.date + "T00:00:00");
        const label = dateObj.getDate();
        cells += `<div class="calendar-day${journalClass}" data-pct="${bucket}"
            title="${d.date} — morning ${d.morning_pct}% · daily ${d.daily_pct || 0}% · evening ${d.evening_pct}%"
            onclick="showDayDetail('${d.date}')"
            style="display:flex;align-items:center;justify-content:center;font-size:0.65rem;color:rgba(0,0,0,0.4);font-weight:600">
            ${label}
        </div>`;
    }

    grid.innerHTML = cells;
}

// ── DAY POPOVER ───────────────────────────────────────────────────────────────

async function showDayDetail(dateStr) {
    document.getElementById("day-popover-overlay").classList.remove("hidden");
    document.getElementById("popover-date").textContent = new Date(dateStr + "T00:00:00")
        .toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
    document.getElementById("popover-content").innerHTML = "<p class='text-muted'>Loading…</p>";

    try {
        const data = await api.get(`/tracker/api/history/${dateStr}`);
        if (data.completions.length === 0) {
            document.getElementById("popover-content").innerHTML = "<p class='text-muted'>No data for this day.</p>";
            return;
        }
        const morning = data.completions.filter(c => c.routine === "morning");
        const daily = data.completions.filter(c => c.routine === "daily");
        const evening = data.completions.filter(c => c.routine === "evening");

        const renderSection = (label, items) => {
            if (items.length === 0) return "";
            return `<div style="margin-bottom:var(--space-md)">
                <div style="font-weight:600;margin-bottom:var(--space-sm)">${label}</div>
                ${items.map(c => `
                <div style="display:flex;gap:var(--space-sm);align-items:center;margin-bottom:4px">
                    <span style="color:${c.completed ? "var(--color-success)" : "var(--color-border)"};font-size:14px">${c.completed ? "✓" : "○"}</span>
                    <span style="font-size:var(--font-size-sm);${c.completed ? "" : "color:var(--color-text-muted)"}">${escHtml(c.step_title)}</span>
                </div>`).join("")}
            </div>`;
        };

        document.getElementById("popover-content").innerHTML =
            renderSection("☀️ Morning", morning) +
            renderSection("◎ Daily", daily) +
            renderSection("🌙 Evening", evening);
    } catch (e) {
        document.getElementById("popover-content").innerHTML = `<p class='text-muted'>${escHtml(e.message)}</p>`;
    }
}

function closeDayPopover() {
    document.getElementById("day-popover-overlay").classList.add("hidden");
}
