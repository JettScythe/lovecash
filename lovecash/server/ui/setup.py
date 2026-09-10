SETUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<meta name="theme-color" content="#0b0b10" />
<title>lovecash setup</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #0b0b10;
    color: #f2f2f5;
    min-height: 100vh;
  }
  .wrap { max-width: 460px; margin: 0 auto; padding: 28px 16px 56px; }

  header { text-align: center; margin-bottom: 20px; }
  h1 {
    margin: 10px 0 6px; font-size: 26px;
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
  }
  .sub { margin: 0; font-size: 14px; line-height: 1.55; opacity: 0.72; }

  /* wizard progress */
  .wiz-steps { display: flex; gap: 6px; justify-content: center; margin-bottom: 18px; }
  .wiz-steps .pip {
    width: 26px; height: 6px; border-radius: 3px;
    background: rgba(255, 255, 255, 0.12);
    transition: background 0.2s ease;
  }
  .wiz-steps .pip.now { background: #ff5c8a; }
  .wiz-steps .pip.done { background: #5cff9d; }

  .card {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 14px;
    padding: 20px 16px;
    margin-bottom: 14px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  }
  h2 { margin: 0 0 10px; font-size: 18px; }
  p.explain { margin: 0 0 14px; font-size: 13.5px; line-height: 1.6; opacity: 0.8; }

  .flow {
    margin: 0 0 14px; padding: 12px; border-radius: 10px;
    background: rgba(255, 255, 255, 0.04);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px; line-height: 1.75; text-align: center;
    white-space: pre-wrap; word-break: break-word;
  }
  .flow .ok { color: #5cff9d; }
  .flow .no { color: #ff6b6b; }

  input[type="text"], input[type="number"], select {
    -webkit-appearance: none; appearance: none;
    width: 100%; padding: 13px; margin-top: 8px;
    font: inherit; font-size: 15px; color: #f2f2f5;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 12px;
  }
  input:focus, select:focus { outline: 2px solid #ff5c8a; outline-offset: 1px; }

  input[type="range"] { width: 100%; margin-top: 10px; accent-color: #ff5c8a; }
  .slider-row { margin-bottom: 6px; }
  .slider-row .val { float: right; font-weight: 700; color: #ff9a5c; }
  .slider-row label { font-size: 13px; opacity: 0.8; }

  .check-row {
    display: flex; align-items: flex-start; gap: 9px;
    margin-top: 12px; font-size: 13px; line-height: 1.5;
  }
  .check-row input { margin-top: 3px; accent-color: #ff5c8a; }

  .btn {
    -webkit-appearance: none; appearance: none;
    width: 100%; padding: 14px; margin-top: 14px; cursor: pointer;
    font: inherit; font-size: 15px; font-weight: 700; color: #fff;
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    border: 0; border-radius: 12px;
    box-shadow: 0 6px 22px rgba(255, 92, 138, 0.35);
    transition: transform 0.08s ease;
  }
  .btn:active { transform: scale(0.97); }
  .btn.secondary {
    background: rgba(255, 255, 255, 0.08);
    box-shadow: none; font-weight: 600;
  }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .msg { margin-top: 10px; font-size: 13px; min-height: 1.3em; }
  .msg.err { color: #ff6b6b; }
  .msg.ok { color: #5cff9d; }

  .addr-chain {
    margin-top: 12px; padding: 10px 12px; border-radius: 10px;
    background: rgba(255, 255, 255, 0.04);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px; line-height: 1.8; word-break: break-all;
  }
  .addr-chain .first { color: #5cff9d; }
  .addr-chain .dim { opacity: 0.45; }

  .toy-row {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 4px; border-bottom: 1px solid rgba(255, 255, 255, 0.07);
    font-size: 14px;
  }
  .toy-row:last-child { border-bottom: 0; }
  .toy-row .toy-name { flex: 1; }
  .toy-row .badge {
    font-size: 11px; padding: 3px 9px; border-radius: 999px;
    background: rgba(92, 255, 157, 0.15); color: #5cff9d;
  }
  .toy-row select { width: auto; margin-top: 0; padding: 7px 10px; font-size: 13px; }

  .hidden { display: none !important; }
  footer { text-align: center; font-size: 12px; opacity: 0.45; margin-top: 18px; }
</style>
</head>
<body>
  <main class="wrap">
    <header>
      <h1>lovecash setup</h1>
      <p class="sub">Four steps. No account, no signup, no custody.</p>
      <div class="wiz-steps" id="wiz">
        <div class="pip now"></div><div class="pip"></div><div class="pip"></div><div class="pip"></div>
      </div>
    </header>

    <!-- 0 · how it works -->
    <section class="card" id="step-0">
      <h2>How lovecash works</h2>
      <div class="flow">tipper&rsquo;s wallet
   │
   ▼  <span class="ok">direct, on-chain</span>
YOUR wallet (BCH)
   │
   ▼  watch-only
lovecash <span class="no">✗ no keys</span> <span class="ok">✓ only watches</span>
   │
   ▼
your toy reacts</div>
      <p class="explain">Tips go <strong>straight to your own Bitcoin Cash wallet</strong>. lovecash only
      <em>watches</em> the chain with a public key and fires your toy when a payment lands.
      It can never move your funds.</p>
      <button class="btn" id="next-0">Get started</button>
    </section>

    <!-- 1 · toy -->
    <section class="card hidden" id="step-1">
      <h2>1 · Connect your toy</h2>
      <p class="explain">Open the <strong>Lovense Connect</strong> app (not Remote) and connect your
      toy, then scan. lovecash auto-detects what each toy does.</p>
      <div id="toy-list"></div>
      <div id="toy-manual" class="hidden">
        <p class="explain">No toy found yet. You can pick an action manually and re-run setup later,
        or connect your toy and scan again.</p>
        <select id="manual-action" aria-label="Toy action">
          <option>Vibrate</option><option>Thrusting</option>
          <option>Rotate</option><option>Pump</option><option>Depth</option>
        </select>
      </div>
      <div class="msg" id="toy-msg"></div>
      <button class="btn secondary" id="scan-toys">Scan for toys</button>
      <button class="btn" id="next-1" disabled>Next: your wallet</button>
    </section>

    <!-- 2 · xpub -->
    <section class="card hidden" id="step-2">
      <h2>2 · Your wallet&rsquo;s public key</h2>
      <p class="explain">In Electron Cash: <strong>Wallet &rarr; Information &rarr; Master Public Key</strong>
      (starts with <code>xpub</code>). This lets lovecash <em>watch</em> your wallet.
      <strong>Never</strong> paste a private key (<code>xprv</code>) or seed words.</p>
      <input type="text" id="xpub" placeholder="xpub…" aria-label="Your xpub" spellcheck="false" />
      <div class="msg" id="xpub-msg"></div>
      <div class="addr-chain hidden" id="addr-chain"></div>
      <label class="check-row hidden" id="addr-confirm-row">
        <input type="checkbox" id="addr-confirm" />
        <span>Address <strong>#0</strong> above matches the first receive address in my wallet.</span>
      </label>
      <button class="btn secondary" id="check-xpub">Check key</button>
      <button class="btn" id="next-2" disabled>Next: limits</button>
    </section>

    <!-- 3 · limits -->
    <section class="card hidden" id="step-3">
      <h2>3 · Safety limits</h2>
      <p class="explain">Hard ceilings &mdash; no tip can ever exceed these. You can change them anytime
      in <code>config.yaml</code>.</p>
      <div class="slider-row">
        <label>Max strength <span class="val" id="strength-val">12</span> / 20</label>
        <input type="range" id="max-strength" min="1" max="20" value="12" />
      </div>
      <div class="slider-row">
        <label>Max duration per tip <span class="val" id="duration-val">30</span>s</label>
        <input type="range" id="max-duration" min="1" max="120" value="30" />
      </div>
      <label class="check-row">
        <input type="checkbox" id="relay-enabled" checked />
        <span>Enable the OBS overlay + tipping page (<code>/overlay</code>, <code>/tip</code>)</span>
      </label>
      <button class="btn" id="finish">Write my config</button>
      <div class="msg" id="finish-msg"></div>
    </section>

    <!-- done -->
    <section class="card hidden" id="step-done">
      <h2>You&rsquo;re set</h2>
      <p class="explain" id="done-detail"></p>
      <div class="flow">lovecash doctor   <span class="dim"># sanity-check everything</span>
lovecash serve     <span class="dim"># go live</span></div>
      <p class="explain">Restart <code>lovecash serve</code> and this address becomes your live relay.
      Add <code>/overlay</code> as an OBS Browser Source; share <code>/tip</code> with viewers.</p>
    </section>

    <footer>lovecash setup &middot; runs only on this machine</footer>
  </main>

<script>
(function () {
  "use strict";

  var state = {
    toys: [],          // [{id, name, action, known}]
    manualAction: null,
    xpubOk: false
  };

  function el(id) { return document.getElementById(id); }

  var steps = ["step-0", "step-1", "step-2", "step-3", "step-done"];
  function gotoStep(n) {
    var i;
    for (i = 0; i < steps.length; i += 1) el(steps[i]).classList.add("hidden");
    el(steps[n]).classList.remove("hidden");
    var pips = document.querySelectorAll("#wiz .pip");
    for (i = 0; i < pips.length; i += 1) {
      pips[i].classList.remove("now", "done");
      if (i < n) pips[i].classList.add("done");
      else if (i === n) pips[i].classList.add("now");
    }
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.detail || ("http " + r.status));
        return data;
      });
    });
  }

  // ---- step 1: toys ----
  function renderToys() {
    var list = el("toy-list");
    list.textContent = "";
    var manual = el("toy-manual");
    if (!state.toys.length) {
      manual.classList.remove("hidden");
      el("next-1").disabled = false; // manual action selected by default
      return;
    }
    manual.classList.add("hidden");
    state.toys.forEach(function (toy, i) {
      var row = document.createElement("div");
      row.className = "toy-row";
      var name = document.createElement("span");
      name.className = "toy-name";
      name.textContent = toy.name;
      row.appendChild(name);
      if (toy.known) {
        var badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = toy.action;
        row.appendChild(badge);
      } else {
        var sel = document.createElement("select");
        ["Vibrate", "Thrusting", "Rotate", "Pump", "Depth"].forEach(function (a) {
          var opt = document.createElement("option");
          opt.textContent = a;
          sel.appendChild(opt);
        });
        sel.value = toy.action;
        sel.addEventListener("change", function () { state.toys[i].action = sel.value; });
        row.appendChild(sel);
      }
      list.appendChild(row);
    });
    el("next-1").disabled = false;
  }

  el("scan-toys").addEventListener("click", function () {
    el("toy-msg").textContent = "scanning…";
    fetch("/api/setup/toys").then(function (r) { return r.json(); }).then(function (data) {
      state.toys = data.toys || [];
      el("toy-msg").textContent = state.toys.length
        ? state.toys.length + " toy(s) found"
        : "none found — is Lovense Connect running?";
      el("toy-msg").className = "msg " + (state.toys.length ? "ok" : "err");
      renderToys();
    }).catch(function () {
      el("toy-msg").textContent = "scan failed — Lovense Connect not reachable";
      el("toy-msg").className = "msg err";
      renderToys();
    });
  });

  // ---- step 2: xpub ----
  el("check-xpub").addEventListener("click", function () {
    var xpub = el("xpub").value.trim();
    el("xpub-msg").textContent = "checking…";
    el("xpub-msg").className = "msg";
    post("/api/setup/check-xpub", { xpub: xpub }).then(function (data) {
      var chain = el("addr-chain");
      chain.textContent = "";
      var head = document.createElement("div");
      head.textContent = "your xpub derives a fresh address per tip:";
      head.className = "dim";
      chain.appendChild(head);
      data.addresses.forEach(function (addr, i) {
        var row = document.createElement("div");
        row.textContent = "#" + i + "  " + addr;
        row.className = i === 0 ? "first" : "dim";
        chain.appendChild(row);
      });
      chain.classList.remove("hidden");
      el("addr-confirm-row").classList.remove("hidden");
      el("xpub-msg").textContent = "valid public key ✓ — confirm address #0 below";
      el("xpub-msg").className = "msg ok";
      state.xpubOk = false;
      el("next-2").disabled = true;
    }).catch(function (err) {
      el("addr-chain").classList.add("hidden");
      el("addr-confirm-row").classList.add("hidden");
      el("xpub-msg").textContent = err.message;
      el("xpub-msg").className = "msg err";
    });
  });

  el("addr-confirm").addEventListener("change", function () {
    state.xpubOk = el("addr-confirm").checked;
    el("next-2").disabled = !state.xpubOk;
  });

  // ---- step 3: limits ----
  el("max-strength").addEventListener("input", function () {
    el("strength-val").textContent = el("max-strength").value;
  });
  el("max-duration").addEventListener("input", function () {
    el("duration-val").textContent = el("max-duration").value;
  });

  el("finish").addEventListener("click", function () {
    el("finish").disabled = true;
    el("finish-msg").textContent = "writing config…";
    el("finish-msg").className = "msg";
    post("/api/setup/config", {
      xpub: el("xpub").value.trim(),
      max_strength: parseInt(el("max-strength").value, 10),
      max_duration_s: parseFloat(el("max-duration").value),
      relay_enabled: el("relay-enabled").checked,
      manual_action: state.toys.length ? null : el("manual-action").value,
      toys: state.toys.map(function (t) {
        return { toy_id: t.id, name: t.name, action: t.known ? null : t.action };
      })
    }).then(function (data) {
      el("done-detail").textContent = "Config written to " + data.path +
        " (owner-only permissions).";
      gotoStep(4);
    }).catch(function (err) {
      el("finish-msg").textContent = err.message;
      el("finish-msg").className = "msg err";
      el("finish").disabled = false;
    });
  });

  // ---- nav ----
  el("next-0").addEventListener("click", function () { gotoStep(1); el("scan-toys").click(); });
  el("next-1").addEventListener("click", function () { gotoStep(2); });
  el("next-2").addEventListener("click", function () { gotoStep(3); });
})();
</script>
</body>
</html>
"""
