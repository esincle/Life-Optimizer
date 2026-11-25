// Centralized API helpers

async function apiFetch(url, options = {}) {
    const defaults = {
        headers: { "Content-Type": "application/json" },
    };
    const merged = { ...defaults, ...options };
    if (merged.body && typeof merged.body === "object") {
        merged.body = JSON.stringify(merged.body);
    }
    const res = await fetch(url, merged);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        const e = new Error(err.error || "Request failed");
        e.status = res.status;
        e.data = err;
        throw e;
    }
    // 204 / empty
    if (res.status === 204) return null;
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text);
}

const api = {
    get:    (url)          => apiFetch(url),
    post:   (url, body)    => apiFetch(url, { method: "POST", body }),
    put:    (url, body)    => apiFetch(url, { method: "PUT", body }),
    delete: (url)          => apiFetch(url, { method: "DELETE" }),
};

// Toast notifications
function showToast(message, type = "") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// Escape HTML to prevent XSS when setting innerHTML
function escHtml(str) {
    const d = document.createElement("div");
    d.appendChild(document.createTextNode(str || ""));
    return d.innerHTML;
}
