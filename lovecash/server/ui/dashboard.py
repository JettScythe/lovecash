"""Self-contained performer dashboard page (served at /dashboard).

Zero-build: inline CSS + vanilla JS, no external resources except /qr.png.
Consumes the API contract of lovecash.server.app (/api/status, /api/toys,
/panic, /resume) and follows the overlay conventions in templates.py.
Safety rules: memos are attacker-controlled on-chain text, so they are only
ever rendered via textContent; control POSTs prompt for the relay token once
on a 401 and reuse it from localStorage afterwards.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>lovecash — performer dashboard</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #0b0b0e; color: #f2f2f5; min-height: 100vh;
    font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 20;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 12px 20px;
    background: rgba(11, 11, 14, 0.92); backdrop-filter: blur(8px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  }
  .brand {
    font-size: 22px; font-weight: 800; color: #ff5c8a;
    margin-right: auto; white-space: nowrap;
  }
  .brand .sub {
    color: rgba(255, 255, 255, 0.55); font-weight: 600;
    font-size: 14px; margin-left: 10px;
  }
  .uptime {
    font-variant-numeric: tabular-nums;
    color: rgba(255, 255, 255, 0.75); font-size: 15px;
  }
  .badge { padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 14px; }
  .badge.ok { background: rgba(92, 255, 157, 0.14); color: #5cff9d; }
  .badge.warn { background: rgba(255, 211, 92, 0.14); color: #ffd35c; }
  .badge.down { background: rgba(255, 107, 107, 0.14); color: #ff6b6b; }
  #panic {
    font-size: 20px; font-weight: 800; letter-spacing: 0.5px;
    color: #fff; background: linear-gradient(135deg, #ff3b5c, #c81e3a);
    border: none; border-radius: 12px; padding: 16px 30px; cursor: pointer;
    box-shadow: 0 6px 24px rgba(255, 59, 92, 0.45);
  }
  #panic:active { transform: scale(0.97); }
  #panic.resume {
    background: linear-gradient(135deg, #ffd35c, #ff9a3c); color: #201400;
    box-shadow: 0 6px 24px rgba(255, 211, 92, 0.4);
  }
  main {
    max-width: 1100px; margin: 0 auto; padding: 20px;
    display: flex; flex-direction: column; gap: 16px;
  }
  .banner {
    padding: 14px 18px; border-radius: 12px;
    font-weight: 700; text-align: center; font-size: 16px;
  }
  #stopped-banner {
    background: rgba(255, 211, 92, 0.12); color: #ffd35c;
    border: 1px solid rgba(255, 211, 92, 0.4);
  }
  #relay-banner {
    background: rgba(255, 107, 107, 0.12); color: #ff6b6b;
    border: 1px solid rgba(255, 107, 107, 0.4);
  }
  .hidden { display: none !important; }
  .card {
    background: rgba(20, 20, 24, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px; padding: 18px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  }
  .card h2 {
    margin: 0 0 14px; font-size: 13px; text-transform: uppercase;
    letter-spacing: 1.2px; color: rgba(255, 255, 255, 0.5);
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 14px;
  }
  .stat-label {
    font-size: 13px; text-transform: uppercase;
    letter-spacing: 1.2px; color: rgba(255, 255, 255, 0.5);
  }
  .stat-value {
    font-size: 30px; font-weight: 800; margin-top: 8px;
    font-variant-numeric: tabular-nums;
  }
  .stat-sub {
    font-size: 14px; color: rgba(255, 255, 255, 0.55);
    margin-top: 4px; min-height: 18px;
  }
  .columns {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(330px, 1fr));
    gap: 14px; align-items: start;
  }
  .address {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    word-break: break-all; background: rgba(255, 255, 255, 0.05);
    padding: 12px 14px; border-radius: 8px; font-size: 14px; margin-bottom: 14px;
  }
  #address-card { text-align: center; }
  #address-card .address { text-align: left; }
  #qr {
    width: 220px; height: 220px; background: #fff;
    padding: 10px; border-radius: 10px;
  }
  .qr-caption { margin-top: 10px; font-size: 13px; color: rgba(255, 255, 255, 0.55); }
  .toy {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 14px; border-radius: 10px;
    background: rgba(255, 255, 255, 0.04); margin-bottom: 8px;
  }
  .toy-dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .toy-dot.on { background: #5cff9d; box-shadow: 0 0 8px rgba(92, 255, 157, 0.7); }
  .toy-dot.off { background: rgba(255, 255, 255, 0.25); }
  .toy-name { font-weight: 600; }
  .toy-batt {
    margin-left: auto; color: rgba(255, 255, 255, 0.65);
    font-variant-numeric: tabular-nums;
  }
  table { width: 100%; border-collapse: collapse; }
  th {
    text-align: left; font-size: 12px; text-transform: uppercase;
    letter-spacing: 1px; color: rgba(255, 255, 255, 0.45);
    padding: 8px 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  td {
    padding: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    font-size: 15px;
  }
  .num { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .memo { max-width: 380px; overflow-wrap: anywhere; color: rgba(255, 255, 255, 0.85); }
  .status {
    padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 700;
    background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.6);
  }
  .status.st-confirming { background: rgba(255, 211, 92, 0.15); color: #ffd35c; }
  .status.st-queued { background: rgba(92, 168, 255, 0.15); color: #5ca8ff; }
  .status.st-active { background: rgba(92, 255, 157, 0.15); color: #5cff9d; }
  .status.st-done { background: rgba(255, 255, 255, 0.07); color: rgba(255, 255, 255, 0.5); }
  .muted { color: rgba(255, 255, 255, 0.5); font-size: 14px; }

  /* settings editor */
  .set-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 18px; }
  .set-field label { display: block; font-size: 12px; opacity: 0.6; margin-bottom: 4px; }
  .set-field .val { color: #ff9a5c; font-weight: 700; }
  .set-field input[type="range"] { width: 100%; accent-color: #ff5c8a; }
  .set-field input[type="number"], .set-field input[type="text"], .set-field select, .set-field textarea {
    width: 100%; padding: 8px 10px; font: inherit; font-size: 14px;
    color: #f2f2f5; background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 8px;
  }
  .set-field textarea {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; min-height: 150px; resize: vertical;
  }
  .set-field input[type="color"] { width: 48px; height: 32px; padding: 0; border: 0; background: none; }
  .set-check { display: flex; align-items: center; gap: 8px; font-size: 14px; margin-top: 20px; }
  .set-check input { accent-color: #ff5c8a; }
  #settings-save {
    margin-top: 14px; padding: 11px; width: 100%; cursor: pointer;
    font: inherit; font-weight: 700; color: #fff;
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    border: 0; border-radius: 10px;
  }
  #settings-msg { margin-top: 8px; font-size: 13px; min-height: 1.2em; }
  #settings-msg.ok { color: #5cff9d; }
  #settings-msg.err { color: #ff6b6b; }
  @media (max-width: 700px) { .set-grid { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div class="brand">lovecash<span class="sub">performer dashboard</span></div>
  <span id="conn-badge" class="badge down">connecting</span>
  <span id="uptime" class="uptime">--:--:--</span>
  <button id="panic" type="button">PANIC STOP</button>
</header>
<main>
  <div id="stopped-banner" class="banner hidden">PANIC STOP ACTIVE — toy halted, all further commands blocked</div>
  <div id="relay-banner" class="banner hidden">Relay unreachable — is lovecash running? Controls will not respond until it is back.</div>

  <section class="stats-grid">
    <div class="card">
      <div class="stat-label">Session total</div>
      <div id="stat-total" class="stat-value">—</div>
      <div id="stat-total-usd" class="stat-sub"></div>
    </div>
    <div class="card">
      <div class="stat-label">Tips</div>
      <div id="stat-count" class="stat-value">—</div>
      <div class="stat-sub"></div>
    </div>
    <div class="card">
      <div class="stat-label">Top tip</div>
      <div id="stat-top" class="stat-value">—</div>
      <div id="stat-top-usd" class="stat-sub"></div>
    </div>
    <div class="card">
      <div class="stat-label">BCH / USD</div>
      <div id="stat-price" class="stat-value">—</div>
      <div class="stat-sub"></div>
    </div>
  </section>

  <div class="columns">
    <section class="card" id="address-card">
      <h2>Receive address</h2>
      <div id="address" class="address">waiting for address…</div>
      <img id="qr" src="/qr.png" alt="QR code of the current receive address" />
      <div class="qr-caption">viewers scan this to tip in Bitcoin Cash</div>
    </section>
    <section class="card">
      <h2>Toys</h2>
      <div id="toys"><div class="muted">loading…</div></div>
    </section>
  </div>

  <section class="card">
    <h2>Recent tips</h2>
    <table>
      <thead><tr><th>Time</th><th>Amount</th><th>Memo</th><th>Status</th></tr></thead>
      <tbody id="tips-body"></tbody>
    </table>
    <div id="tips-empty" class="muted">no tips yet this session</div>
  </section>

  <section class="card">
    <h2>Settings — live, no restart</h2>
    <div class="muted" style="margin-bottom:14px">Applies to the next tip and saves to config.yaml. Wallet key, servers and toy wiring stay in config.yaml (need a restart).</div>
    <div class="set-grid">
      <div class="set-field">
        <label>Max strength <span class="val" id="set-strength-val">—</span> / 20</label>
        <input type="range" id="set-strength" min="1" max="20" />
      </div>
      <div class="set-field">
        <label>Max duration per tip <span class="val" id="set-duration-val">—</span>s</label>
        <input type="range" id="set-duration" min="1" max="120" />
      </div>
      <div class="set-field">
        <label>Playback mode</label>
        <select id="set-playback">
          <option value="queue">queue — tips play in turn</option>
          <option value="override">override — newest tip fires now</option>
        </select>
      </div>
      <div class="set-field">
        <label>When the queue is full</label>
        <select id="set-trim">
          <option value="drop_oldest">drop oldest</option>
          <option value="drop_newest">reject new tip</option>
          <option value="compress">compress durations</option>
        </select>
      </div>
      <div class="set-field">
        <label>Alert below this many sats — off</label>
        <input type="number" id="set-alert-min" min="0" step="1" />
      </div>
      <div class="set-field">
        <label>Session goal (sats, empty = off)</label>
        <input type="number" id="set-goal" min="0" step="1" placeholder="off" />
      </div>
      <div class="set-field set-check">
        <input type="checkbox" id="set-show-goal" />
        <label for="set-show-goal" style="margin:0">show goal bar in overlay</label>
      </div>
      <div class="set-field">
        <label>Overlay accent</label>
        <input type="color" id="set-accent" />
      </div>
      <div class="set-field set-check">
        <input type="checkbox" id="set-sound" />
        <label for="set-sound" style="margin:0">alert sound</label>
      </div>
    </div>
    <div class="set-field" style="margin-top:14px">
      <label>Tip rules (JSON — validated on save)</label>
      <textarea id="set-rules" spellcheck="false"></textarea>
    </div>
    <button id="settings-save" type="button">Save settings</button>
    <div id="settings-msg"></div>
  </section>
</main>
<script>
  const connBadge = document.getElementById('conn-badge');
  const uptimeEl = document.getElementById('uptime');
  const panicBtn = document.getElementById('panic');
  const stoppedBanner = document.getElementById('stopped-banner');
  const relayBanner = document.getElementById('relay-banner');
  const statTotal = document.getElementById('stat-total');
  const statTotalUsd = document.getElementById('stat-total-usd');
  const statCount = document.getElementById('stat-count');
  const statTop = document.getElementById('stat-top');
  const statTopUsd = document.getElementById('stat-top-usd');
  const statPrice = document.getElementById('stat-price');
  const addrEl = document.getElementById('address');
  const qrEl = document.getElementById('qr');
  const toysEl = document.getElementById('toys');
  const tipsBody = document.getElementById('tips-body');
  const tipsEmpty = document.getElementById('tips-empty');

  const TOKEN_KEY = 'lovecash_relay_token';
  let isStopped = false;
  let lastStartedAt = null;
  let lastAddress = null;

  function fmtSats(n) {
    return Number(n || 0).toLocaleString('en-US') + ' sats';
  }
  function usdOf(sats, price) {
    return '$' + (Number(sats || 0) / 1e8 * price).toFixed(2);
  }
  function fmtTime(epoch) {
    return new Date(epoch * 1000).toTimeString().slice(0, 8);
  }
  function fmtDuration(secs) {
    const pad = (x) => String(x).padStart(2, '0');
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    return pad(h) + ':' + pad(m) + ':' + pad(s);
  }

  function setConnection(state) {
    let cls = 'down';
    if (state === 'connected') cls = 'ok';
    else if (state === 'reconnecting') cls = 'warn';
    connBadge.className = 'badge ' + cls;
    connBadge.textContent = state || 'down';
  }

  function setRelayReachable(ok) {
    relayBanner.classList.toggle('hidden', ok);
    if (!ok) {
      connBadge.className = 'badge down';
      connBadge.textContent = 'relay unreachable';
    }
  }

  function setStopped(stopped) {
    isStopped = stopped;
    panicBtn.textContent = stopped ? 'RESUME' : 'PANIC STOP';
    panicBtn.classList.toggle('resume', stopped);
    stoppedBanner.classList.toggle('hidden', !stopped);
  }

  function tokenHeaders() {
    const t = localStorage.getItem(TOKEN_KEY);
    return t ? { 'X-Relay-Token': t } : {};
  }

  async function postControl(path) {
    return fetch(path, { method: 'POST', headers: tokenHeaders() });
  }

  async function control(path) {
    let resp;
    try {
      resp = await postControl(path);
    } catch (e) {
      setRelayReachable(false);
      return;
    }
    if (resp.status === 401) {
      const t = prompt('This relay requires a control token. Enter the relay token from your lovecash config:');
      if (t === null || t === '') return;
      localStorage.setItem(TOKEN_KEY, t);
      try {
        resp = await postControl(path);
      } catch (e) {
        setRelayReachable(false);
        return;
      }
      if (resp.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        alert('The relay rejected that token; it was cleared. Check your config and try again.');
        return;
      }
    }
    if (!resp.ok) {
      alert('Control request failed (HTTP ' + resp.status + ').');
      return;
    }
    const data = await resp.json();
    setStopped(!!data.stopped);
    pollStatus();
  }

  panicBtn.addEventListener('click', () => {
    if (isStopped) {
      if (confirm('Clear the panic stop and allow toy commands again?')) control('/resume');
    } else {
      if (confirm('PANIC STOP: halt all toy activity now and block every further command?')) control('/panic');
    }
  });

  function renderStats(data) {
    const stats = data.stats || {};
    const price = data.price_usd;
    const total = stats.total_sats || 0;
    const top = stats.top_sats || 0;
    statTotal.textContent = fmtSats(total);
    statTotalUsd.textContent = price != null ? '≈ ' + usdOf(total, price) : '';
    statCount.textContent = String(stats.count || 0);
    statTop.textContent = fmtSats(top);
    statTopUsd.textContent = price != null && top > 0 ? '≈ ' + usdOf(top, price) : '';
    statPrice.textContent = price != null ? '$' + Number(price).toFixed(2) : '—';
    lastStartedAt = stats.started_at || null;
  }

  function renderAddress(addr) {
    if (!addr || addr === lastAddress) return;
    lastAddress = addr;
    addrEl.textContent = addr;
    qrEl.src = '/qr.png?ts=' + Date.now();
  }

  function renderTips(recent) {
    tipsBody.replaceChildren();
    tipsEmpty.classList.toggle('hidden', recent.length > 0);
    for (const tip of recent) {
      const tr = document.createElement('tr');

      const tdTime = document.createElement('td');
      tdTime.className = 'num';
      tdTime.textContent = fmtTime(tip.at);

      const tdAmt = document.createElement('td');
      tdAmt.className = 'num';
      tdAmt.textContent = fmtSats(tip.amount_sats)
        + (tip.usd != null ? ' ($' + Number(tip.usd).toFixed(2) + ')' : '');

      const tdMemo = document.createElement('td');
      tdMemo.className = 'memo';
      tdMemo.textContent = tip.memo || '';

      const tdStatus = document.createElement('td');
      const badge = document.createElement('span');
      badge.className = 'status st-' + (tip.status || 'done');
      badge.textContent = tip.status || 'unknown';
      tdStatus.appendChild(badge);

      tr.appendChild(tdTime);
      tr.appendChild(tdAmt);
      tr.appendChild(tdMemo);
      tr.appendChild(tdStatus);
      tipsBody.appendChild(tr);
    }
  }

  function toyNote(text) {
    const note = document.createElement('div');
    note.className = 'muted';
    note.textContent = text;
    toysEl.appendChild(note);
  }

  function renderToys(data) {
    toysEl.replaceChildren();
    if (!data.ok) {
      toyNote('Lovense Connect app not reachable');
      return;
    }
    if (!data.toys || data.toys.length === 0) {
      toyNote('no toys reported by Lovense Connect');
      return;
    }
    for (const toy of data.toys) {
      const row = document.createElement('div');
      row.className = 'toy';

      const dot = document.createElement('span');
      dot.className = 'toy-dot ' + (toy.online ? 'on' : 'off');

      const name = document.createElement('span');
      name.className = 'toy-name';
      name.textContent = toy.name || 'Unknown toy';

      const state = document.createElement('span');
      state.className = 'muted';
      state.textContent = toy.online ? 'online' : 'offline';

      const batt = document.createElement('span');
      batt.className = 'toy-batt';
      if (toy.battery != null) batt.textContent = toy.battery + '%';

      row.appendChild(dot);
      row.appendChild(name);
      row.appendChild(state);
      row.appendChild(batt);
      toysEl.appendChild(row);
    }
  }

  async function pollStatus() {
    let data;
    try {
      const resp = await fetch('/api/status');
      if (!resp.ok) throw new Error('http ' + resp.status);
      data = await resp.json();
    } catch (e) {
      setRelayReachable(false);
      return;
    }
    setRelayReachable(true);
    setConnection(data.connection);
    setStopped(!!data.stopped);
    renderStats(data);
    renderAddress(data.address);
    renderTips((data.stats && data.stats.recent) || []);
  }

  async function pollToys() {
    let data;
    try {
      const resp = await fetch('/api/toys');
      if (!resp.ok) throw new Error('http ' + resp.status);
      data = await resp.json();
    } catch (e) {
      toysEl.replaceChildren();
      toyNote('relay unreachable — cannot fetch toys');
      return;
    }
    renderToys(data);
  }

  function tickUptime() {
    if (!lastStartedAt) {
      uptimeEl.textContent = '--:--:--';
      return;
    }
    const elapsed = Math.max(0, Date.now() / 1000 - lastStartedAt);
    uptimeEl.textContent = 'up ' + fmtDuration(elapsed);
  }

  // ---- live settings editor ----
  const setStrength = document.getElementById('set-strength');
  const setDuration = document.getElementById('set-duration');
  const setPlayback = document.getElementById('set-playback');
  const setTrim = document.getElementById('set-trim');
  const setAlertMin = document.getElementById('set-alert-min');
  const setGoal = document.getElementById('set-goal');
  const setShowGoal = document.getElementById('set-show-goal');
  const setAccent = document.getElementById('set-accent');
  const setSound = document.getElementById('set-sound');
  const setRules = document.getElementById('set-rules');
  const settingsMsg = document.getElementById('settings-msg');
  let settingsLoaded = false;
  let rawLimits = null; // full objects from GET — save merges over these
  let rawAlerts = null; // so untouched fields (queue seconds etc.) aren't defaulted

  setStrength.addEventListener('input', () => {
    document.getElementById('set-strength-val').textContent = setStrength.value;
  });
  setDuration.addEventListener('input', () => {
    document.getElementById('set-duration-val').textContent = setDuration.value;
  });

  async function loadSettings() {
    let resp;
    try {
      resp = await fetch('/api/settings', { headers: tokenHeaders() });
    } catch (e) { return; } // relay down: pollStatus already shows the banner
    if (resp.status === 401) return; // token prompt happens on first save
    if (!resp.ok) return;
    const data = await resp.json();
    setStrength.value = data.limits.max_strength;
    document.getElementById('set-strength-val').textContent = data.limits.max_strength;
    setDuration.value = data.limits.max_duration_s;
    document.getElementById('set-duration-val').textContent = data.limits.max_duration_s;
    setPlayback.value = data.limits.playback;
    setTrim.value = data.limits.trim_strategy;
    setAlertMin.value = data.alerts.min_sats;
    setGoal.value = data.alerts.goal_sats == null ? '' : data.alerts.goal_sats;
    setShowGoal.checked = data.alerts.show_goal !== false;
    setAccent.value = data.alerts.accent;
    setSound.checked = !!data.alerts.sound;
    setRules.value = JSON.stringify(data.rules, null, 2);
    rawLimits = data.limits;
    rawAlerts = data.alerts;
    settingsLoaded = true;
  }

  function settingsBody() {
    let rules;
    try {
      rules = JSON.parse(setRules.value);
    } catch (e) {
      throw new Error('rules are not valid JSON: ' + e.message);
    }
    if (!Array.isArray(rules)) throw new Error('rules must be a JSON array');
    const limits = Object.assign({}, rawLimits, {
      max_strength: parseInt(setStrength.value, 10),
      max_duration_s: parseFloat(setDuration.value),
      playback: setPlayback.value,
      trim_strategy: setTrim.value,
    });
    const alerts = Object.assign({}, rawAlerts, {
      min_sats: parseInt(setAlertMin.value, 10) || 0,
      goal_sats: setGoal.value === '' ? null : parseInt(setGoal.value, 10),
      show_goal: setShowGoal.checked,
      accent: setAccent.value,
      sound: setSound.checked,
    });
    return { limits, alerts, rules };
  }

  document.getElementById('settings-save').addEventListener('click', async () => {
    settingsMsg.className = '';
    settingsMsg.textContent = '';
    let body;
    try {
      body = settingsBody();
    } catch (e) {
      settingsMsg.className = 'err';
      settingsMsg.textContent = e.message;
      return;
    }
    const resp = await fetch('/api/settings', {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, tokenHeaders()),
      body: JSON.stringify(body),
    });
    if (resp.status === 401) {
      const t = prompt('This relay requires a control token. Enter the relay token from your lovecash config:');
      if (!t) return;
      localStorage.setItem(TOKEN_KEY, t);
      const retry = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Relay-Token': t },
        body: JSON.stringify(body),
      });
      if (retry.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        settingsMsg.className = 'err';
        settingsMsg.textContent = 'token rejected — check your config';
        return;
      }
      if (!retry.ok) { settingsMsg.className = 'err'; settingsMsg.textContent = 'save failed (HTTP ' + retry.status + ')'; return; }
      settingsMsg.className = 'ok';
      settingsMsg.textContent = 'saved — live now, persisted to config.yaml';
      return;
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      settingsMsg.className = 'err';
      settingsMsg.textContent = 'save failed: ' + (err.detail ? JSON.stringify(err.detail) : 'HTTP ' + resp.status);
      return;
    }
    const data = await resp.json();
    settingsMsg.className = 'ok';
    settingsMsg.textContent = data.persisted
      ? 'saved — live now, persisted to config.yaml'
      : 'saved — live now (no config file path known; not persisted)';
  });

  loadSettings();
  pollStatus();
  pollToys();
  setInterval(pollStatus, 2000);
  setInterval(pollToys, 2000);
  setInterval(tickUptime, 1000);
  tickUptime();
</script>
</body>
</html>
"""
