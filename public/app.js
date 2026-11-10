/* Mandate — front-end. No framework, no build step. */

const $ = (id) => document.getElementById(id);

const TRACE_EMPTY = `
  <div class="trace-empty">
    <div class="trace-empty-icon">⌁</div>
    <p>No activity yet.</p>
    <span>Run the agent and every decision appears here — planning, policy checks, and the payment itself.</span>
  </div>`;

const ICONS = {
  verify: "⌁",
  plan: "◈",
  search: "⌕",
  policy: "§",
  approval: "!",
  payment: "$",
  order: "$",
  capture: "✓",
  done: "✓",
  block: "⊘",
  error: "!",
  deny: "✕",
  issue: "+",
  revoke: "⊘",
  topup: "+",
  webhook: "⌁",
};

const ACTS = {
  1: "Find me running shoes for under $100.",
  2: "Get me the cheapest Aero Tempo 4 you can find.",
  3: "Buy the Trail Blaze 2.",
};

let DATA = null;
let busy = false;

/* ---------------------------------------------------------------- helpers */
const money = (v) =>
  "$" + Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function fmtDuration(seconds) {
  seconds = Math.max(0, Math.floor(seconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m`;
  return `${seconds}s`;
}

function timeAgo(ts) {
  const diff = Date.now() / 1000 - Number(ts || 0);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({ error: "invalid server response" }));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function toast(message, kind = "info") {
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  $("toasts").appendChild(node);
  setTimeout(() => {
    node.style.opacity = "0";
    node.style.transform = "translateY(6px)";
    node.style.transition = "opacity .25s ease, transform .25s ease";
    setTimeout(() => node.remove(), 260);
  }, 4200);
}

/* ----------------------------------------------------------------- render */
function render() {
  if (!DATA || !DATA.mandate) return;
  const m = DATA.mandate;

  $("ai-badge").textContent = `AI · ${DATA.ai.label}`;
  const paypalBadge = $("paypal-badge");
  paypalBadge.textContent = `PayPal · ${DATA.paypal.mode === "mock" ? "mock" : DATA.paypal.env}`;
  paypalBadge.classList.toggle("mock", DATA.paypal.mode === "mock");
  $("footer-mode").textContent = `${DATA.paypal.mode === "mock" ? "mock payments" : "PayPal " + DATA.paypal.env} · signed tokens · policy engine`;

  $("m-agent").textContent = m.agent;
  $("m-agent-avatar").textContent = (m.agent || "A").slice(0, 1).toUpperCase();
  $("m-id").textContent = m.id;

  const statusPill = $("m-status");
  statusPill.textContent = m.status;
  statusPill.className = "pill " + (m.status === "active" ? "ok" : "bad");

  const agentState = $("agent-state");
  agentState.textContent = busy ? "running" : m.status === "active" ? "idle" : "revoked";
  agentState.className = "pill " + (busy ? "running" : m.status === "active" ? "idle" : "bad");

  $("m-spent").textContent = money(m.spent);
  $("m-budget").textContent = money(m.budget);
  $("m-cap").textContent = money(m.per_txn_cap);
  $("m-threshold").textContent = money(m.approval_threshold);
  $("m-velocity").textContent = `${m.purchases_last_hour} / ${m.max_purchases_per_hour}`;
  updateExpiry();

  const circumference = 339.292;
  const fraction = m.budget > 0 ? Math.min(1, m.spent / m.budget) : 0;
  $("donut-fill").style.strokeDashoffset = String(circumference * (1 - fraction));

  $("m-merchants").innerHTML = (m.merchants.length ? m.merchants : ["any merchant"])
    .map((value) => `<span class="chip">${esc(value)}</span>`)
    .join("");
  $("m-categories").innerHTML = (m.categories.length ? m.categories : ["any category"])
    .map((value) => `<span class="chip">${esc(value)}</span>`)
    .join("");

  const token = $("m-token");
  token.textContent = m.token_preview;
  token.dataset.full = m.token;
  token.title = "Click to copy the full signed token";

  $("revoke-btn").disabled = m.status !== "active";

  renderStats();
  renderApprovals();
  renderLedger();
}

function updateExpiry() {
  if (!DATA || !DATA.mandate) return;
  const elapsed = (Date.now() - (DATA._loadedAt || Date.now())) / 1000;
  $("m-expiry").textContent = fmtDuration(DATA.mandate.expires_in - elapsed);
}

function renderStats() {
  const stats = DATA.stats;
  const tiles = [
    ["Captured", money(stats.captured), `${stats.payments} payment${stats.payments === 1 ? "" : "s"} settled`, "green"],
    ["Policy blocks", String(stats.blocked), "agent attempts stopped", "red"],
    ["Awaiting approval", String(stats.pending), "human in the loop", "amber"],
    ["Agent runs", String(stats.runs), "audited end-to-end", ""],
  ];
  $("statbar").innerHTML = tiles
    .map(
      ([label, value, note, tone]) => `
      <div class="stat ${tone}">
        <span class="stat-label">${esc(label)}</span>
        <span class="stat-value">${esc(value)}</span>
        <span class="stat-note ${tone}">${esc(note)}</span>
      </div>`
    )
    .join("");
}

function renderApprovals() {
  const approvals = [...(DATA.approvals || [])];
  const pending = approvals.filter((a) => a.status === "pending");
  const done = approvals.filter((a) => a.status !== "pending");

  const count = $("approval-count");
  count.textContent = `${pending.length} pending`;
  count.className = "pill " + (pending.length ? "warn" : "idle");

  const cards = [];

  for (const approval of pending) {
    const offer = approval.offer;
    cards.push(`
      <div class="approval-card">
        <div class="approval-top">
          <span class="pill warn">Awaiting you</span>
          <strong class="approval-amount">${money(approval.amount)}</strong>
        </div>
        <div class="approval-item">${esc(offer.name)} <span>· ${esc(offer.merchant_name || offer.merchant)}</span></div>
        <p class="approval-reason">${esc(approval.reason)}</p>
        <div class="approval-actions">
          <button class="btn primary" data-action="approve" data-id="${approval.id}">Approve &amp; pay</button>
          <button class="btn ghost" data-action="deny" data-id="${approval.id}">Deny</button>
        </div>
      </div>`);
  }

  for (const approval of done.slice(0, 4)) {
    const offer = approval.offer;
    const label = { approved: "Paid", denied: "Denied", void: "Voided", expired: "Void", failed: "Failed" }[approval.status] || approval.status;
    const tone = approval.status === "approved" ? "ok" : approval.status === "denied" ? "bad" : "idle";
    cards.push(`
      <div class="approval-card ${approval.status}">
        <div class="approval-top">
          <span class="pill ${tone}">${esc(label)}</span>
          <strong class="approval-amount">${money(approval.amount)}</strong>
        </div>
        <div class="approval-item">${esc(offer.name)} <span>· ${esc(offer.merchant)}</span></div>
        <p class="approval-reason">${esc(approval.note || timeAgo(approval.resolved_at))}</p>
      </div>`);
  }

  $("approvals").innerHTML = cards.length
    ? cards.join("")
    : `<div class="empty">No approvals waiting. Anything under ${money(DATA.mandate.approval_threshold)} is paid automatically.</div>`;
}

function renderLedger() {
  const transactions = DATA.transactions || [];
  $("ledger-total").textContent = `${money(DATA.stats.captured)} captured`;

  if (!transactions.length) {
    $("ledger").innerHTML = `<div class="empty">No payments yet. The ledger fills as the agent spends.</div>`;
    return;
  }

  $("ledger").innerHTML = transactions
    .map((txn) => {
      const ok = txn.status === "completed";
      return `
        <div class="ledger-row">
          <div class="ledger-main">
            <span class="ledger-name">${esc(txn.item_name)}</span>
            <span class="ledger-meta">${esc(txn.merchant)} · ${esc(txn.paypal_order_id || txn.id)}</span>
          </div>
          <div class="ledger-right">
            <span class="ledger-amount ${ok ? "" : "failed"}">${money(txn.amount)}</span>
            <span class="ledger-status ${ok ? "" : "failed"}">${esc(ok ? txn.mode || "paid" : "failed")}</span>
          </div>
        </div>`;
    })
    .join("");
}

/* ------------------------------------------------------------------ steps */
function renderStep(step) {
  const node = document.createElement("div");
  node.className = `step kind-${step.kind}`;

  const data = step.data || {};
  const verdict = data.verdict
    ? `<span class="verdict ${esc(data.verdict)}">${esc(String(data.verdict).toUpperCase())}</span>`
    : "";

  let checks = "";
  if (Array.isArray(data.checks) && data.checks.length) {
    checks =
      `<div class="checks">` +
      data.checks
        .map(
          (check) => `
            <div class="check">
              <span class="check-dot ${esc(check.status)}"></span>
              <span class="check-label">${esc(check.label)}</span>
              <span class="check-detail">${esc(check.detail)}</span>
            </div>`
        )
        .join("") +
      `</div>`;
  }

  node.innerHTML = `
    <div class="step-icon">${ICONS[step.kind] || "·"}</div>
    <div class="step-body">
      <div class="step-title"><span>${esc(step.title)}</span>${verdict}</div>
      <div class="step-detail">${esc(step.detail)}</div>
      ${checks}
    </div>
    <div class="step-time">${new Date((step.ts || Date.now() / 1000) * 1000).toLocaleTimeString([], { hour12: false })}</div>`;

  return node;
}

async function animate(steps) {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  for (const step of steps) {
    $("trace").appendChild(renderStep(step));
    $("trace").scrollTop = $("trace").scrollHeight;
    if (!reduce) await sleep(step.kind === "policy" ? 520 : 360);
  }
}

function renderLastRun() {
  const actions = (DATA.actions || []).filter((action) => action.run_id && action.run_id !== "system");
  if (!actions.length) return;
  const lastRun = actions[actions.length - 1].run_id;
  const steps = actions.filter((action) => action.run_id === lastRun);
  if (!steps.length) return;
  $("trace").innerHTML = "";
  for (const step of steps) $("trace").appendChild(renderStep(step));
  $("trace").scrollTop = $("trace").scrollHeight;
}

/* ----------------------------------------------------------------- actions */
function setBusy(value) {
  busy = value;
  document.body.classList.toggle("is-running", value);
  const runBtn = $("run-btn");
  runBtn.disabled = value;
  runBtn.querySelector("span").textContent = value ? "Working…" : "Run agent";
  document.querySelectorAll(".scenario").forEach((button) => (button.disabled = value));
  if (DATA && DATA.mandate) {
    const agentState = $("agent-state");
    agentState.textContent = value ? "running" : DATA.mandate.status === "active" ? "idle" : "revoked";
    agentState.className = "pill " + (value ? "running" : DATA.mandate.status === "active" ? "idle" : "bad");
  }
}

function toastResult(result) {
  if (!result) return;
  if (result.verdict === "paid" && result.transaction) {
    toast(`Paid ${money(result.transaction.amount)} · ${result.transaction.item_name}`, "success");
  } else if (result.verdict === "approval") {
    toast(`Approval required · ${money(result.approval.amount)} ${result.approval.offer.name}`, "warn");
  } else if (result.verdict === "block") {
    toast(`Blocked · ${result.reason}`, "error");
  } else if (result.verdict === "denied") {
    toast("Purchase denied. Nothing was charged.", "warn");
  } else if (result.verdict === "error") {
    toast(`Error · ${result.reason}`, "error");
  }
}

async function runAgent(goal, { tokenOverride } = {}) {
  if (busy) return;
  if (!goal.trim()) return;

  setBusy(true);
  $("trace").innerHTML = "";
  const placeholder = renderStep({
    kind: "plan",
    title: "Dispatching goal",
    detail: goal,
    ts: Date.now() / 1000,
  });
  $("trace").appendChild(placeholder);

  try {
    const body = { goal, mandate_id: DATA.mandate.id };
    if (tokenOverride) body.token_override = tokenOverride;
    const response = await api("/api/agent/run", { method: "POST", body });
    $("trace").innerHTML = "";
    await animate(response.steps);
    DATA = response.state;
    DATA._loadedAt = Date.now();
    render();
    toastResult(response.result);

    if (response.result?.verdict === "approval" && window.innerWidth <= 1140) {
      document.querySelector(".side-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  } catch (error) {
    $("trace").innerHTML = "";
    $("trace").appendChild(
      renderStep({ kind: "error", title: "Request failed", detail: error.message, ts: Date.now() / 1000 })
    );
    toast(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function resolveApproval(id, action) {
  if (busy) return;
  setBusy(true);
  try {
    const response = await api(`/api/approvals/${id}/${action}`, { method: "POST", body: {} });
    $("trace").innerHTML = "";
    await animate(response.steps);
    DATA = response.state;
    DATA._loadedAt = Date.now();
    render();
    toastResult(response.result);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function tamperToken(token) {
  try {
    const [body, signature] = token.split(".");
    const normalized = body.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const payload = JSON.parse(atob(padded));
    payload.budget = 99999;
    const forged = btoa(JSON.stringify(payload))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    return `${forged}.${signature}`;
  } catch {
    return token.slice(0, -2) + "xx";
  }
}

function setTokenResult(ok, message) {
  const node = $("token-result");
  node.textContent = message;
  node.className = "token-result " + (ok ? "ok" : "bad");
}

/* -------------------------------------------------------------------- wire */
$("run-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runAgent($("goal").value);
});

$("goal").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    event.preventDefault();
    runAgent($("goal").value);
  }
});

document.querySelectorAll(".scenario").forEach((button) => {
  button.addEventListener("click", async () => {
    const act = Number(button.dataset.act);
    if (busy) return;

    if (act === 3 && DATA.mandate.status === "active") {
      try {
        const response = await api(`/api/mandates/${DATA.mandate.id}/revoke`, { method: "POST", body: {} });
        DATA = response.state;
        DATA._loadedAt = Date.now();
        render();
        toast("Mandate revoked — Scout is cut off.", "warn");
        await sleep(600);
      } catch (error) {
        toast(error.message, "error");
        return;
      }
    }

    $("goal").value = ACTS[act];
    runAgent(ACTS[act]);
  });
});

$("approvals").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  resolveApproval(button.dataset.id, button.dataset.action);
});

$("revoke-btn").addEventListener("click", async () => {
  if (!DATA || DATA.mandate.status !== "active") return;
  try {
    const response = await api(`/api/mandates/${DATA.mandate.id}/revoke`, { method: "POST", body: {} });
    DATA = response.state;
    DATA._loadedAt = Date.now();
    render();
    toast("Mandate revoked. The agent can no longer spend.", "warn");
  } catch (error) {
    toast(error.message, "error");
  }
});

$("topup-btn").addEventListener("click", async () => {
  try {
    const response = await api(`/api/mandates/${DATA.mandate.id}/topup`, { method: "POST", body: { amount: 75 } });
    DATA = response.state;
    DATA._loadedAt = Date.now();
    render();
    toast("Budget raised. A fresh signed token was issued.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
});

$("verify-btn").addEventListener("click", async () => {
  try {
    const response = await api("/api/verify", { method: "POST", body: { token: DATA.mandate.token } });
    if (response.valid) {
      const payload = response.payload || {};
      setTokenResult(true, `Signature valid — budget ${money(payload.budget)}, cap ${money(payload.per_txn_cap)}. Limits are intact.`);
    } else {
      setTokenResult(false, `Rejected — ${response.error}.`);
    }
  } catch (error) {
    setTokenResult(false, error.message);
  }
});

$("tamper-btn").addEventListener("click", async () => {
  try {
    const forged = tamperToken(DATA.mandate.token);
    const response = await api("/api/verify", { method: "POST", body: { token: forged } });
    setTokenResult(
      false,
      `Tampered token rejected — ${response.error || "signature mismatch"}. The agent cannot edit its own limits.`
    );
  } catch (error) {
    setTokenResult(false, error.message);
  }
});

$("m-token").addEventListener("click", async () => {
  const token = $("m-token").dataset.full;
  if (!token) return;
  try {
    await navigator.clipboard.writeText(token);
    toast("Full signed token copied.", "success");
  } catch {
    toast("Copy failed — select the token manually.", "error");
  }
});

$("reset-btn").addEventListener("click", async () => {
  try {
    const response = await api("/api/reset", { method: "POST", body: {} });
    DATA = response.state;
    DATA._loadedAt = Date.now();
    $("trace").innerHTML = TRACE_EMPTY;
    $("token-result").textContent = "";
    $("token-result").className = "token-result";
    render();
    toast("Demo reset.", "success");
  } catch (error) {
    toast(error.message, "error");
  }
});

/* -------------------------------------------------------------------- boot */
(async function boot() {
  try {
    DATA = await api("/api/state");
    DATA._loadedAt = Date.now();
    render();
    renderLastRun();
    setInterval(updateExpiry, 1000);
  } catch (error) {
    toast(`Could not load state: ${error.message}`, "error");
  }
})();
