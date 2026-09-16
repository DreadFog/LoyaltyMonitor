/* ─────────────────────────────────────────────────────────────
   LoyaltyMonitor — shared client-side utilities
   Page-specific logic lives in inline <script> blocks inside
   each template.
───────────────────────────────────────────────────────────── */

"use strict";

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value;
  return element.innerHTML;
}

// ── CSRF ──────────────────────────────────────────────────────
function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content ?? "";
}

// ── Generic JSON POST (CSRF-aware) ────────────────────────────
function postJSON(url, data) {
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(data),
  }).then((resp) => resp.json());
}

// ── Transient alert injected into #alert-container ────────────
function showAlert(message, type = "info") {
  const container = document.getElementById("alert-container");
  if (!container) return;

  const div = document.createElement("div");
  div.className = `alert alert-${type} alert-dismissible fade show`;
  div.setAttribute("role", "alert");
  div.innerHTML =
    message +
    `<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
  container.appendChild(div);

  // Auto-dismiss after 4 s
  setTimeout(() => {
    div.classList.remove("show");
    setTimeout(() => div.remove(), 200);
  }, 4000);
}

// ── Navbar display-mode toggle ────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  const toggleBtn = document.getElementById("toggleDisplayMode");
  if (!toggleBtn) return;

  // Skip if the settings page has overridden this listener
  if (toggleBtn.dataset.listenerAttached) return;
  toggleBtn.dataset.listenerAttached = "1";

  toggleBtn.addEventListener("click", function () {
    postJSON("/admin/toggle-display", {}).then((data) => {
      if (data.display_mode) {
        window.location.reload();
      }
    });
  });
});
