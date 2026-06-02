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
</style>
</head>
<body>
  <div id="alerts"></div>
  <div id="qr-card">
    <img src="/qr.png" alt="Tip with Bitcoin Cash" />
    <div class="label">Tip with Bitcoin Cash</div>
    <div id="status" class="down">connecting...</div>
  </div>
<script>
  const statusEl = document.getElementById("status");
  const alertsEl = document.getElementById("alerts");

  function showTip(tip) {
    const el = document.createElement("div");
    el.className = "alert";
    const bch = (tip.amount_sats / 1e8).toFixed(8).replace(/0+$/, "");
    el.textContent = "New tip: " + bch + " BCH";
    alertsEl.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(proto + "://" + location.host + "/overlay-ws");
    ws.onopen = () => { statusEl.textContent = "live";
      statusEl.className = "ok"; };
    ws.onclose = () => { statusEl.textContent = "reconnecting...";
      statusEl.className = "down"; setTimeout(connect, 2000); };
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "tip") showTip(msg.data);
    };
  }
  connect();
</script>
</body>
</html>
"""
