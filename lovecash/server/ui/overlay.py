"""Stream overlay page (the thing viewers see in OBS).

render_overlay(alerts) injects the performer's AlertConfig as JSON so
display policy (amounts, memos, sound, goal bar, accent color) is decided
performer-side, not hardcoded.

Zero-build: one self-contained HTML document, no external assets.
"""

import json

from lovecash.config import AlertConfig

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>lovecash overlay</title>
<style>
  :root { color-scheme: dark; --accent: __ACCENT__; }
  body {
    margin: 0; font-family: system-ui, sans-serif; background: transparent;
    overflow: hidden;
  }
  #qr-card {
    position: fixed; bottom: 24px; right: 24px; padding: 16px;
    background: rgba(20, 20, 24, 0.82); border-radius: 16px;
    text-align: center; color: #fff; backdrop-filter: blur(4px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  #qr-card img { width: 200px; height: 200px; border-radius: 8px;
    background: #fff; padding: 8px; display: block; }
  #qr-card .label { margin-top: 10px; font-size: 14px; opacity: 0.85; }
  #status { margin-top: 6px; font-size: 12px; }
  .ok { color: #5cff9d; } .down { color: #ff6b6b; }

  /* --- tip alerts --- */
  #alerts {
    position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
    display: flex; flex-direction: column; gap: 10px; align-items: center;
    z-index: 20;
  }
  .alert {
    color: #fff; font-weight: 600; padding: 14px 22px; border-radius: 999px;
    background: linear-gradient(135deg, var(--accent), #ff9a5c);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.45);
    animation: pop 0.4s ease, fade 0.5s ease 5s forwards;
    text-align: center; line-height: 1.35;
  }
  .alert .memo { display: block; font-weight: 400; font-size: 13px;
    opacity: 0.92; max-width: 60ch; overflow-wrap: anywhere; }
  .alert.medium { font-size: 20px; padding: 16px 28px; }
  .alert.whale {
    font-size: 28px; padding: 20px 36px; border-radius: 24px;
    animation: pop 0.4s ease, glow 1s ease-in-out 3 alternate,
      fade 0.5s ease 7s forwards;
  }
  @keyframes pop { from { transform: scale(0.7); opacity: 0; } }
  @keyframes fade { to { opacity: 0; transform: translateY(-12px); } }
  @keyframes glow {
    from { box-shadow: 0 0 24px var(--accent); }
    to { box-shadow: 0 0 64px var(--accent); }
  }
  .confetti {
    position: fixed; width: 10px; height: 10px; border-radius: 2px;
    top: 60px; z-index: 10; pointer-events: none;
    animation: fall 1.8s ease-in forwards;
  }
  @keyframes fall {
    to { transform: translateY(110vh) rotate(720deg); opacity: 0.6; }
  }

  /* --- goal bar --- */
  #goal {
    position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
    width: 420px; max-width: 60vw; display: none; color: #fff;
    background: rgba(20, 20, 24, 0.82); border-radius: 14px;
    padding: 10px 16px; backdrop-filter: blur(4px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.35);
  }
  #goal .bar {
    height: 10px; border-radius: 999px; background: rgba(255,255,255,0.12);
    overflow: hidden; margin-top: 6px;
  }
  #goal .fill {
    height: 100%; width: 0%; border-radius: 999px;
    background: linear-gradient(90deg, var(--accent), #ff9a5c);
    transition: width 0.6s ease;
  }
  #goal .text { font-size: 13px; display: flex;
    justify-content: space-between; }

  /* --- playback queue --- */
  #queue {
    position: fixed; bottom: 24px; left: 24px;
    display: flex; flex-direction: column; gap: 8px; width: 280px;
  }
  .tip-row {
    padding: 10px 14px; border-radius: 12px; color: #fff; font-size: 14px;
    background: rgba(20, 20, 24, 0.82); backdrop-filter: blur(4px);
    box-shadow: 0 4px 16px rgba(0,0,0,0.35);
    display: flex; justify-content: space-between; align-items: center;
    animation: slidein 0.25s ease;
  }
  @keyframes slidein { from { transform: translateX(-20px); opacity: 0; } }
  .tip-row.confirming { border-left: 4px solid #ffd35c; }
  .tip-row.queued { border-left: 4px solid #5ca8ff; }
  .tip-row.active { border-left: 4px solid #5cff9d;
    background: rgba(40, 60, 40, 0.85); }
  .tip-row .eta { font-size: 12px; opacity: 0.7; }
  .dot {
    width: 8px; height: 8px; border-radius: 50%; background: #ffd35c;
    display: inline-block; margin-right: 8px;
    animation: pulse 1s ease-in-out infinite;
  }
  @keyframes pulse { 50% { opacity: 0.3; } }
</style>
</head>
<body>
  <div id="alerts"></div>
  <div id="queue"></div>
  <div id="goal">
    <div class="text"><span id="goal-label">Tip goal</span>
      <span id="goal-nums"></span></div>
    <div class="bar"><div class="fill" id="goal-fill"></div></div>
  </div>
  <div id="qr-card">
    <img src="/qr.png" alt="Tip with Bitcoin Cash" />
    <div class="label">Tip with Bitcoin Cash</div>
    <div id="status" class="down">connecting...</div>
  </div>
<script>
  const ALERTS = __ALERTS_JSON__;

  const statusEl = document.getElementById("status");
  const alertsEl = document.getElementById("alerts");
  const queueEl = document.getElementById("queue");
  const goalEl = document.getElementById("goal");
  const tips = new Map();

  function fmtSats(sats) {
    const bch = (sats / 1e8).toFixed(8).replace(/0+$/, "").replace(/\\.$/, "");
    return bch + " BCH";
  }

  function tier(sats) {
    if (sats >= 50000) return "whale";
    if (sats >= 10000) return "medium";
    return "small";
  }

  // --- sound: WebAudio chimes, no assets. Bigger tier, bigger chime. ---
  let audioCtx = null;
  function chime(t) {
    if (!ALERTS.sound) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext ||
        window.webkitAudioContext)();
      const notes = {small: [660], medium: [523, 784],
        whale: [523, 659, 784, 1047]}[t];
      notes.forEach((freq, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        const at = audioCtx.currentTime + i * 0.12;
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.25, at + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.5);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(at);
        osc.stop(at + 0.55);
      });
    } catch (e) { /* audio blocked until user gesture — fine */ }
  }

  function confettiBurst() {
    const colors = ["--accent", "#ff9a5c", "#5cff9d", "#5ca8ff", "#ffd35c"];
    const accent = getComputedStyle(document.documentElement)
      .getPropertyValue("--accent").trim() || "#ff5c8a";
    for (let i = 0; i < 40; i++) {
      const p = document.createElement("div");
      p.className = "confetti";
      p.style.left = (35 + Math.random() * 30) + "vw";
      p.style.background = i % 5 === 0 ? accent :
        colors[1 + (i % (colors.length - 1))];
      p.style.animationDelay = (Math.random() * 0.4) + "s";
      document.body.appendChild(p);
      setTimeout(() => p.remove(), 2400);
    }
  }

  function showAlert(d) {
    const hasTokens = d.tokens && d.tokens.length > 0;
    if (d.amount_sats < ALERTS.min_sats && !hasTokens) return;
    const t = tier(d.amount_sats);
    const el = document.createElement("div");
    el.className = "alert " + t;
    const parts = [];
    if (ALERTS.show_amount) {
      parts.push("New tip: " + fmtSats(d.amount_sats) +
        (d.usd != null ? " (~$" + d.usd.toFixed(2) + ")" : ""));
    } else {
      parts.push("New tip!");
    }
    el.textContent = parts.join("");
    if (hasTokens) {
      // Token receipts: amount + short category prefix (full hex is in
      // the dashboard). Category hex, not a ticker, is the identity.
      const tk = document.createElement("span");
      tk.className = "memo";
      tk.textContent = d.tokens.map((r) =>
        "+" + fmtSats(r.amount) + " tokens (" + String(r.category).slice(0, 8) + "…)"
      ).join(" ");
      el.appendChild(tk);
    }
    if (ALERTS.show_memo && d.memo) {
      const m = document.createElement("span");
      m.className = "memo";
      m.textContent = d.memo;  // on-chain text: textContent only, never HTML
      el.appendChild(m);
    }
    alertsEl.appendChild(el);
    chime(t);
    if (t === "whale") confettiBurst();
    setTimeout(() => el.remove(), t === "whale" ? 8000 : 6000);
  }

  let lastStats = { total_sats: 0, goal_sats: ALERTS.goal_sats };
  let potMode = false;  // goal_show covenant: bar tracks the pot, not tips

  function updateGoal(d) {
    if (potMode) {
      // handled by onPotBalance — stats messages must not clobber it
    } else if (d && typeof d.total_sats === "number") {
      lastStats.total_sats = d.total_sats;
      if (d.goal_sats !== undefined) lastStats.goal_sats = d.goal_sats;
    }
    const goal = lastStats.goal_sats;
    if (!ALERTS.show_goal || goal == null || goal <= 0) {
      goalEl.style.display = "none";
      return;
    }
    goalEl.style.display = "block";
    const pct = Math.min(100, (lastStats.total_sats / goal) * 100);
    document.getElementById("goal-fill").style.width = pct + "%";
    document.getElementById("goal-nums").textContent =
      lastStats.total_sats.toLocaleString() + " / " +
      goal.toLocaleString() + " sats (" + Math.floor(pct) + "%)";
  }

  function onPotBalance(d) {
    if (!d || typeof d.balance_sats !== "number") return;
    potMode = true;
    if (d.active === false) {
      // Show settled (pot claimed) — drop the bar entirely.
      goalEl.style.display = "none";
      return;
    }
    lastStats.total_sats = d.balance_sats;
    if (typeof d.goal_sats === "number") lastStats.goal_sats = d.goal_sats;
    updateGoal();
  }

  function renderQueue() {
    queueEl.textContent = "";
    const order = { confirming: 0, queued: 1, active: 2 };
    const rows = [...tips.values()].sort((a, b) => {
      const oa = order[a.status] ?? 9, ob = order[b.status] ?? 9;
      if (oa !== ob) return oa - ob;
      return (a.position ?? 0) - (b.position ?? 0);
    });
    for (const t of rows) {
      const row = document.createElement("div");
      row.className = "tip-row " + t.status;
      const left = document.createElement("span");
      const right = document.createElement("span");
      right.className = "eta";
      if (t.status === "confirming") {
        const dot = document.createElement("span");
        dot.className = "dot";
        left.appendChild(dot);
        left.appendChild(document.createTextNode("confirming..."));
      } else if (t.status === "queued") {
        left.textContent = "queued #" + t.position;
        if (t.eta_seconds != null)
          right.textContent = "~" + Math.ceil(t.eta_seconds) + "s";
      } else if (t.status === "active") {
        left.textContent = "▶ playing now";
      }
      row.appendChild(left);
      row.appendChild(right);
      queueEl.appendChild(row);
    }
  }

  function onTipStatus(d) {
    if (d.status === "done") {
      tips.delete(d.id);
    } else {
      tips.set(d.id, d);
    }
    renderQueue();
  }

  // Seed the goal bar on load — a persisted goal shows immediately,
  // not after the first tip of the session.
  fetch("/api/status").then((r) => r.ok ? r.json() : null).then((data) => {
    if (!data) return;
    if (data.alerts) Object.assign(ALERTS, data.alerts);
    if (data.stats && typeof data.stats.total_sats === "number")
      lastStats.total_sats = data.stats.total_sats;
    lastStats.goal_sats = ALERTS.goal_sats;
    updateGoal();
  }).catch(() => { /* offline: bar waits for the first stats push */ });

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(proto + "://" + location.host + "/overlay-ws");
    ws.onopen = () => { statusEl.textContent = "live";
      statusEl.className = "ok"; };
    ws.onclose = () => { statusEl.textContent = "tips paused - reconnecting";
      statusEl.className = "down"; setTimeout(connect, 2000); };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "tip") showAlert(msg.data);
      else if (msg.type === "stats") updateGoal(msg.data);
      else if (msg.type === "goal_pot") onPotBalance(msg.data);
      else if (msg.type === "alerts") {
        Object.assign(ALERTS, msg.data);
        if (ALERTS.accent)
          document.documentElement.style.setProperty("--accent", ALERTS.accent);
        updateGoal(); // show_goal / goal_sats may have just changed
      }
      else if (msg.type === "tip_status") onTipStatus(msg.data);
      else if (msg.type === "status") {
        const live = msg.data.connection === "connected";
        statusEl.textContent = live ? "live" : "tips paused - reconnecting";
        statusEl.className = live ? "ok" : "down";
      }
      else if (msg.type === "address") {
        document.querySelector("#qr-card img").src = "/qr.png?ts=" + Date.now();
      }
    };
  }
  connect();
</script>
</body>
</html>
"""


def render_overlay(alerts: AlertConfig) -> str:
    """Overlay HTML with the performer's alert preferences baked in."""
    cfg = json.dumps(alerts.model_dump()).replace("</", "<\\/")
    accent = alerts.accent if alerts.accent.startswith("#") else "#ff5c8a"
    return _TEMPLATE.replace("__ALERTS_JSON__", cfg).replace("__ACCENT__", accent)
