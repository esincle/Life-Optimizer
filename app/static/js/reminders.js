// Browser / computer push reminders using Notification API
// Polls reminder schedule while any Life Optimizer page is open.

(function () {
    const FIRED_KEY = "life_optimizer_reminder_fired";
    let timer = null;
    let cache = [];

    function firedMap() {
        try {
            return JSON.parse(localStorage.getItem(FIRED_KEY) || "{}");
        } catch {
            return {};
        }
    }

    function markFired(id, dayKey) {
        const map = firedMap();
        map[`${id}:${dayKey}`] = true;
        // prune old keys
        const keep = {};
        Object.keys(map).forEach(k => {
            if (k.endsWith(`:${dayKey}`) || k.includes(dayKey)) keep[k] = true;
        });
        // also keep yesterday briefly is unnecessary — just rewrite today's
        const todayPrefix = `:${dayKey}`;
        Object.keys(map).forEach(k => {
            if (k.endsWith(todayPrefix)) keep[k] = true;
        });
        localStorage.setItem(FIRED_KEY, JSON.stringify(keep));
    }

    function alreadyFired(id, dayKey) {
        return !!firedMap()[`${id}:${dayKey}`];
    }

    function localDayKey(d = new Date()) {
        return d.toISOString().slice(0, 10);
    }

    function hhmm(d = new Date()) {
        return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    }

    async function refreshReminders() {
        try {
            if (typeof api === "undefined") return;
            let list = await api.get("/today/api/reminders");
            if (!list.length) {
                list = await api.post("/today/api/reminders/seed", {});
            }
            cache = list.filter(r => r.enabled);
        } catch {
            // silent — reminders are best-effort
        }
    }

    function maybeFire() {
        if (!("Notification" in window) || Notification.permission !== "granted") return;
        const now = hhmm();
        const day = localDayKey();
        for (const r of cache) {
            if (r.time_of_day !== now) continue;
            if (alreadyFired(r.id, day)) continue;
            try {
                const n = new Notification("Life Optimizer", {
                    body: r.label,
                    tag: `life-reminder-${r.id}`,
                    renotify: true,
                });
                n.onclick = () => {
                    window.focus();
                    window.location.href = "/today/";
                };
            } catch {
                // ignore
            }
            markFired(r.id, day);
        }
    }

    async function enable() {
        if (!("Notification" in window)) return false;
        let perm = Notification.permission;
        if (perm === "default") {
            perm = await Notification.requestPermission();
        }
        if (perm !== "granted") return false;
        await refreshReminders();
        maybeFire();
        return true;
    }

    function start() {
        if (timer) return;
        refreshReminders();
        maybeFire();
        timer = setInterval(() => {
            maybeFire();
        }, 20000);
        // refresh schedule every 5 minutes
        setInterval(refreshReminders, 5 * 60 * 1000);
    }

    window.LifeReminders = { enable, start, refreshReminders };

    document.addEventListener("DOMContentLoaded", () => {
        if ("Notification" in window && Notification.permission === "granted") {
            start();
        } else {
            // still load schedule; firing waits for permission
            refreshReminders();
            start();
        }
    });
})();
