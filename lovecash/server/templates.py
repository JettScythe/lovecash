OVERLAY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>lovecash overlay</title>
<style>
  :root { color-scheme: dark; }
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
  #alerts {
    position: fixed; top: 24px; left: 50%; transform: translateX(-50%);
    display: flex; flex-direction: column; gap: 10px; align-items: center;
  }
  .alert {
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    color: #fff; font-weight: 600; padding: 14px 22px; border-radius: 999px;
    box-shadow: 0 6px 24px rgba(255, 92, 138, 0.5);
    animation: pop 0.4s ease, fade 0.5s ease 5s forwards;
  }
  @keyframes pop { from { transform: scale(0.7); opacity: 0; } }
  @keyframes fade { to { opacity: 0; transform: translateY(-12px); } }
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
  <div id="qr-card">
    <img src="/qr.png" alt="Tip with Bitcoin Cash" />
    <div class="label">Tip with Bitcoin Cash</div>
    <div id="status" class="down">connecting...</div>
  </div>
<script>
  const statusEl = document.getElementById("status");
  const alertsEl = document.getElementById("alerts");
  const queueEl = document.getElementById("queue");
  const tips = new Map();

  function showAlert(sats) {
    const el = document.createElement("div");
    el.className = "alert";
    const bch = (sats / 1e8).toFixed(8).replace(/0+$/, "").replace(/\\.$/, "");
    el.textContent = "New tip: " + bch + " BCH";
    alertsEl.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  function renderQueue() {
    queueEl.innerHTML = "";
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
        left.innerHTML = '<span class="dot"></span>confirming...';
      } else if (t.status === "queued") {
        left.textContent = "queued #" + t.position;
        if (t.eta_seconds != null)
          right.textContent = "~" + Math.ceil(t.eta_seconds) + "s";
      } else if (t.status === "active") {
        left.textContent = "\u25b6 playing now";
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

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(proto + "://" + location.host + "/overlay-ws");
    ws.onopen = () => { statusEl.textContent = "live";
      statusEl.className = "ok"; };
    ws.onclose = () => { statusEl.textContent = "tips paused - reconnecting";
      statusEl.className = "down"; setTimeout(connect, 2000); };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "tip") showAlert(msg.data.amount_sats);
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
