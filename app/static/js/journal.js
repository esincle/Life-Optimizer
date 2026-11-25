// Journal page logic

let currentTab = "gratitude";
let entryData = { gratitude: null, evening: null };
let entriesPage = 1;
let searchDebounce = null;

document.addEventListener("DOMContentLoaded", () => {
    loadJournalEntry("gratitude");
    loadJournalEntry("evening");
    loadEntryList(1, false);
});

// ── TABS ──────────────────────────────────────────────────────────────────────

function switchJournalTab(type, btn) {
    currentTab = type;
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    document.getElementById(`journal-${type}`).classList.add("active");
}

// ── JOURNAL COMPOSER ──────────────────────────────────────────────────────────

async function loadJournalEntry(type) {
    const container = document.getElementById(`${type}-prompts`);
    try {
        const data = await api.get(`/journal/api/today/${type}`);
        entryData[type] = data;
        renderPrompts(type, data.prompts || []);
    } catch (e) {
        if (container) {
            container.innerHTML = `<p class="text-muted">Couldn’t load prompts. ${escHtml(e.message || "Try refreshing.")}</p>`;
        }
    }
}

function renderPrompts(type, prompts) {
    const container = document.getElementById(`${type}-prompts`);
    if (prompts.length === 0) {
        container.innerHTML = `<p class="text-muted">No prompts configured. Go to <a href="/design/">Design</a> to add ${type} journal prompts.</p>`;
        return;
    }
    container.innerHTML = prompts.map(p => `
        <div class="journal-prompt">
            <div class="journal-prompt-text">${escHtml(p.text)}</div>
            <textarea class="journal-textarea" id="response-${p.id}" data-prompt-id="${p.id}"
                placeholder="Write your thoughts…">${escHtml(p.response || "")}</textarea>
        </div>`).join("");
}

async function saveEntry(type) {
    const prompts = entryData[type]?.prompts || [];
    if (prompts.length === 0) { showToast("No prompts to save", "error"); return; }

    const responses = {};
    for (const p of prompts) {
        const el = document.getElementById(`response-${p.id}`);
        if (el) responses[p.id] = el.value;
    }

    try {
        await api.post(`/journal/api/today/${type}/save`, { responses });
        const msg = document.getElementById(`${type}-saved-msg`);
        msg.textContent = `Saved at ${new Date().toLocaleTimeString()}`;
        setTimeout(() => { msg.textContent = ""; }, 4000);
        showToast("Entry saved", "success");
        loadEntryList(1, false);
    } catch (e) {
        showToast(e.message, "error");
    }
}

// ── ENTRY LIST (sidebar) ──────────────────────────────────────────────────────

async function loadEntryList(page, append) {
    const container = document.getElementById("entry-list-container");
    const moreBtn = document.getElementById("load-more-btn");
    try {
        const data = await api.get(`/journal/api/entries?page=${page}&per_page=20`);
        entriesPage = page;
        renderEntryList(data.entries || [], append);
        if (moreBtn) moreBtn.style.display = data.has_more ? "block" : "none";
    } catch (e) {
        if (!append && container) {
            container.innerHTML = `<p class="text-muted text-sm" style="padding:var(--space-sm) 0">Couldn’t load entries. ${escHtml(e.message || "Try refreshing.")}</p>`;
        }
        if (moreBtn) moreBtn.style.display = "none";
    }
}

function renderEntryList(entries, append) {
    const container = document.getElementById("entry-list-container");
    if (!container) return;
    if (!append) container.innerHTML = "";

    if (!entries || (entries.length === 0 && !append)) {
        container.innerHTML = `<p class="text-muted text-sm" style="padding:var(--space-sm) 0">No entries yet. Write your first entry above!</p>`;
        return;
    }

    const ul = append
        ? (container.querySelector("ul") || (() => { const u = document.createElement("ul"); u.className = "entry-list"; container.appendChild(u); return u; })())
        : (() => { const u = document.createElement("ul"); u.className = "entry-list"; container.appendChild(u); return u; })();

    for (const e of entries) {
        const li = document.createElement("li");
        li.className = "entry-list-item";
        const icon = e.entry_type === "gratitude" ? "🙏" : "🌙";
        const dateLabel = new Date(e.date + "T00:00:00").toLocaleDateString("en-US", {
            month: "short", day: "numeric", year: "numeric"
        });
        li.innerHTML = `
            <div class="entry-list-date">${icon} ${dateLabel}</div>
            <div class="entry-list-snippet">${escHtml(e.snippet || "—")}</div>`;
        li.addEventListener("click", () => openEntryDetail(e.date, e.entry_type, dateLabel, icon));
        ul.appendChild(li);
    }
}

function loadMoreEntries() {
    loadEntryList(entriesPage + 1, true);
}

// ── SEARCH ────────────────────────────────────────────────────────────────────

function onSearch(value) {
    clearTimeout(searchDebounce);
    const q = value.trim();
    if (!q) {
        loadEntryList(1, false);
        document.getElementById("load-more-btn").style.display = "";
        return;
    }
    searchDebounce = setTimeout(async () => {
        try {
            const data = await api.get(`/journal/api/search?q=${encodeURIComponent(q)}`);
            renderEntryList(data.entries, false);
            document.getElementById("load-more-btn").style.display = "none";
        } catch (e) {
            const container = document.getElementById("entry-list-container");
            if (container) {
                container.innerHTML = `<p class="text-muted text-sm" style="padding:var(--space-sm) 0">Search failed. ${escHtml(e.message || "")}</p>`;
            }
        }
    }, 300);
}

// ── ENTRY DETAIL ──────────────────────────────────────────────────────────────

async function openEntryDetail(date, type, dateLabel, icon) {
    document.getElementById("entry-detail-overlay").classList.remove("hidden");
    document.getElementById("entry-detail-title").textContent = `${icon} ${dateLabel}`;
    document.getElementById("entry-detail-body").innerHTML = `<p class="text-muted">Loading…</p>`;

    try {
        const data = await api.get(`/journal/api/entries/${date}/${type}`);
        if (data.responses.length === 0) {
            document.getElementById("entry-detail-body").innerHTML = `<p class="text-muted">No responses recorded.</p>`;
            return;
        }
        document.getElementById("entry-detail-body").innerHTML = data.responses.map(r => `
            <div style="margin-bottom:var(--space-lg)">
                <div style="font-weight:600;color:var(--color-text-muted);font-size:var(--font-size-sm);margin-bottom:var(--space-xs)">${escHtml(r.prompt_text)}</div>
                <div style="white-space:pre-wrap;line-height:1.7">${escHtml(r.body || "—")}</div>
            </div>`).join("");
    } catch (e) {
        document.getElementById("entry-detail-body").innerHTML = `<p class="text-muted">${escHtml(e.message)}</p>`;
    }
}

function closeEntryDetail() {
    document.getElementById("entry-detail-overlay").classList.add("hidden");
}
