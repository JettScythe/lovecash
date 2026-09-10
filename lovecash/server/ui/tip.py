TIP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<meta name="theme-color" content="#0b0b10" />
<title>Tip with Bitcoin Cash</title>
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
  .wrap { max-width: 420px; margin: 0 auto; padding: 28px 16px 56px; }

  header { text-align: center; margin-bottom: 22px; }
  h1 {
    margin: 12px 0 8px; font-size: 27px; line-height: 1.2;
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
  }
  .sub { margin: 0; font-size: 14px; line-height: 1.55; opacity: 0.72; }

  .conn {
    display: inline-flex; align-items: center; gap: 7px;
    font-size: 12px; letter-spacing: 0.02em;
    padding: 5px 12px; border-radius: 999px;
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.75);
  }
  .conn .dot { width: 8px; height: 8px; border-radius: 50%; background: #ffd35c; }
  .conn.live .dot { background: #5cff9d; }
  .conn.reconnecting .dot { background: #ffd35c; animation: pulse 1.1s ease-in-out infinite; }
  .conn.down .dot { background: #ff6b6b; }
  @keyframes pulse { 50% { opacity: 0.25; } }

  .card {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 14px;
    padding: 20px 16px;
    margin-bottom: 16px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  }
  .section-label {
    font-size: 12px; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; opacity: 0.55; margin: 18px 2px 10px;
  }
  .section-label:first-child { margin-top: 0; }

  .presets { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .preset {
    -webkit-appearance: none; appearance: none; cursor: pointer;
    padding: 13px 6px; border-radius: 14px;
    font: inherit; font-size: 16px; font-weight: 600;
    color: #f2f2f5;
    background: rgba(255, 255, 255, 0.06);
    border: 2px solid rgba(255, 255, 255, 0.10);
    transition: transform 0.08s ease, border-color 0.15s ease, background 0.15s ease;
  }
  .preset small {
    display: block; font-size: 12px; font-weight: 400;
    opacity: 0.6; margin-top: 3px; min-height: 1em;
  }
  .preset.active {
    border-color: #ff5c8a;
    background: linear-gradient(135deg, rgba(255, 92, 138, 0.25), rgba(255, 154, 92, 0.25));
  }
  .preset:active { transform: scale(0.96); }

  input[type="number"], input[type="text"] {
    -webkit-appearance: none; appearance: none;
    width: 100%; margin-top: 10px; padding: 14px;
    font: inherit; font-size: 16px; color: #f2f2f5;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 14px;
  }
  input:focus { outline: 2px solid #ff5c8a; outline-offset: 1px; }
  input::placeholder { color: rgba(255, 255, 255, 0.35); }

  .usd-hint { margin: 10px 2px 0; font-size: 13px; opacity: 0.7; min-height: 1.2em; }

  .qr-wrap {
    margin: 18px 0 14px; padding: 12px;
    background: #ffffff; border-radius: 14px;
    display: flex; justify-content: center;
  }
  .qr-wrap img { width: 100%; max-width: 272px; height: auto; display: block; }

  .uri-link {
    display: block; margin: 0 0 14px;
    font-size: 12px; line-height: 1.5; word-break: break-all;
    max-height: 4.5em; overflow: hidden;
    color: #ff9a5c; text-decoration: none;
  }
  .uri-link:active { opacity: 0.7; }

  .btn-primary {
    -webkit-appearance: none; appearance: none;
    width: 100%; padding: 15px; cursor: pointer;
    font: inherit; font-size: 16px; font-weight: 700; color: #ffffff;
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    border: 0; border-radius: 14px;
    box-shadow: 0 6px 22px rgba(255, 92, 138, 0.38);
    transition: transform 0.08s ease;
  }
  .btn-primary:active { transform: scale(0.97); }

  .hint { margin: 12px 2px 0; font-size: 12px; text-align: center; opacity: 0.55; }

  .token-row {
    margin-bottom: 12px; padding: 12px; border-radius: 10px;
    background: rgba(255, 255, 255, 0.04); font-size: 13px;
  }
  .token-row .tk-min { font-weight: 700; }
  .token-row .tk-cat {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 10.5px; word-break: break-all; opacity: 0.6; margin-top: 4px;
  }
  .token-row .tk-links { margin-top: 8px; display: flex; gap: 12px; }
  .token-row .tk-links a, .token-row .tk-links button {
    font-size: 12px; color: #ff9a5c; background: none; border: 0;
    padding: 0; cursor: pointer; text-decoration: none; font-family: inherit;
  }

  #thanks { text-align: center; padding: 34px 16px; }
  #thanks .burst {
    width: 74px; height: 74px; margin: 0 auto 14px;
    animation: pop 0.45s ease, bob 2.2s ease-in-out 0.5s infinite;
  }
  #thanks .burst svg {
    width: 100%; height: 100%; display: block;
    filter: drop-shadow(0 6px 18px rgba(255, 92, 138, 0.55));
  }
  #thanks h2 {
    margin: 0 0 8px; font-size: 23px;
    background: linear-gradient(135deg, #ff5c8a, #ff9a5c);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
  }
  #thanks p { margin: 4px 0; font-size: 15px; }
  #thanks .thanks-memo { opacity: 0.75; font-style: italic; word-break: break-word; }
  @keyframes pop { from { transform: scale(0.4); opacity: 0; } }
  @keyframes bob { 50% { transform: translateY(-7px); } }

  #unreachable { text-align: center; }
  #unreachable .big { margin: 4px 0 16px; font-size: 17px; font-weight: 600; }

  /* live lifecycle stepper */
  #track { padding: 16px; }
  #track .section-label { margin-top: 0; }
  .steps { display: flex; align-items: center; gap: 4px; margin: 6px 0 10px; }
  .step { flex: 1; text-align: center; }
  .step .pip {
    width: 12px; height: 12px; margin: 0 auto 5px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.14);
    transition: background 0.2s ease;
  }
  .step .lbl { font-size: 10px; letter-spacing: 0.04em; opacity: 0.45; }
  .step.passed .pip { background: #5cff9d; }
  .step.passed .lbl { opacity: 0.75; }
  .step.now .pip {
    background: #ff5c8a;
    box-shadow: 0 0 10px rgba(255, 92, 138, 0.8);
    animation: pulse 1.1s ease-in-out infinite;
  }
  .step.now .lbl { opacity: 1; font-weight: 700; }
  #track-detail { margin: 0; font-size: 13px; text-align: center; opacity: 0.8; min-height: 1.3em; }
  #track-txid {
    display: block; margin-top: 8px; font-size: 11px; text-align: center;
    color: #ff9a5c; text-decoration: none; word-break: break-all; opacity: 0.9;
  }

  /* trust explainer */
  details.proof { font-size: 13px; }
  details.proof summary {
    cursor: pointer; text-align: center; opacity: 0.65;
    font-size: 12px; letter-spacing: 0.04em; list-style: none;
  }
  details.proof summary::-webkit-details-marker { display: none; }
  details.proof summary::after { content: " ▾"; }
  details.proof[open] summary::after { content: " ▴"; }
  .proof-flow {
    margin: 12px 0; padding: 12px; border-radius: 10px;
    background: rgba(255, 255, 255, 0.04);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11.5px; line-height: 1.7; text-align: center;
    white-space: pre-wrap; word-break: break-word;
  }
  .proof-flow .ok { color: #5cff9d; }
  .proof-flow .no { color: #ff6b6b; }
  details.proof ul { margin: 8px 0 2px; padding-left: 18px; line-height: 1.6; opacity: 0.85; }
  details.proof li { margin-bottom: 6px; }

  footer { text-align: center; font-size: 12px; opacity: 0.45; }
  .hidden { display: none !important; }
</style>
</head>
<body>
  <main class="wrap">
    <header>
      <span id="conn" class="conn reconnecting" aria-live="polite"><span class="dot"></span><span id="conn-label">connecting</span></span>
      <h1>Tip with Bitcoin Cash</h1>
      <p class="sub">Tips go directly to the performer&rsquo;s wallet &mdash; the relay never holds funds. Non-custodial, with sub-cent network fees.</p>
    </header>

    <noscript><p style="text-align:center">This page needs JavaScript to build your tip QR.</p></noscript>

    <section id="picker" class="card hidden">
      <div class="section-label">1 &middot; Choose an amount</div>
      <div class="presets" id="presets">
        <button type="button" class="preset" data-sats="1000">1,000 sats<small data-usd-for="1000"></small></button>
        <button type="button" class="preset active" data-sats="5000">5,000 sats<small data-usd-for="5000"></small></button>
        <button type="button" class="preset" data-sats="25000">25,000 sats<small data-usd-for="25000"></small></button>
        <button type="button" class="preset" data-sats="100000">100,000 sats<small data-usd-for="100000"></small></button>
      </div>
      <input id="custom" type="number" min="1" step="1" inputmode="numeric"
        placeholder="Custom amount in sats" aria-label="Custom amount in sats" />
      <div id="usd-hint" class="usd-hint" aria-live="polite"></div>

      <div class="section-label">2 &middot; Add a memo</div>
      <input id="memo" type="text" maxlength="200"
        placeholder="Say something (optional, public on-chain)" aria-label="Memo" />

      <div class="section-label">3 &middot; Scan or tap</div>
      <div class="qr-wrap"><img id="qr" alt="Bitcoin Cash payment QR code" width="272" height="272" /></div>
      <a id="uri-link" class="uri-link" href="#"></a>
      <button id="copy" type="button" class="btn-primary">Copy payment URI</button>
      <p class="hint">Scan with any Bitcoin Cash wallet, or tap the link to open one.</p>
    </section>

    <section id="goalpot" class="card hidden">
      <div class="section-label">Goal show — all or nothing</div>
      <div id="pot-progress" style="margin: 4px 0 8px; font-size: 15px; font-weight: 600;"></div>
      <div style="height: 10px; border-radius: 999px; background: rgba(255,255,255,0.08); overflow: hidden;">
        <div id="pot-fill" style="height: 100%; width: 0%; background: linear-gradient(135deg, #ff5c8a, #ff9a5c); transition: width 0.4s ease;"></div>
      </div>
      <p class="hint" id="pot-hint" style="text-align: left;">Pledges go into a smart-contract
        pot, not the performer&rsquo;s wallet. If the goal isn&rsquo;t reached
        by the deadline, every pledger can claim an on-chain refund.
        Direct-wallet pledging lands in a future release &mdash; for now this
        bar tracks the pot live.</p>
      <div id="pot-pledge-mount"></div>
      <div class="tk-cat" id="pot-addr" style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10.5px; word-break: break-all; opacity: 0.6;"></div>
    </section>

    <section id="tokens" class="card hidden">
      <div class="section-label">Tip with fan tokens</div>
      <div id="token-list"></div>
      <p class="hint">Send the token to the same address above from a
        CashToken wallet (Electron Cash, Paytaca, Cashonize, Zapit). The
        toy reacts once the transaction confirms.</p>
    </section>

    <section id="thanks" class="card hidden" aria-live="polite">
      <div class="burst">
        <svg viewBox="0 0 24 24" role="img" aria-label="heart">
          <defs>
            <linearGradient id="hg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="#ff5c8a" />
              <stop offset="1" stop-color="#ff9a5c" />
            </linearGradient>
          </defs>
          <path fill="url(#hg)" d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
        </svg>
      </div>
      <h2>Tip received &mdash; thank you!</h2>
      <p id="thanks-detail"></p>
      <p id="thanks-memo" class="thanks-memo"></p>
    </section>

    <section id="track" class="card hidden" aria-live="polite">
      <div class="section-label">Your tip, live on-chain</div>
      <div class="steps" id="steps">
        <div class="step" data-step="received"><div class="pip"></div><div class="lbl">received</div></div>
        <div class="step" data-step="checking"><div class="pip"></div><div class="lbl">checking</div></div>
        <div class="step" data-step="queued"><div class="pip"></div><div class="lbl">queued</div></div>
        <div class="step" data-step="active"><div class="pip"></div><div class="lbl">playing</div></div>
        <div class="step" data-step="done"><div class="pip"></div><div class="lbl">done</div></div>
      </div>
      <p id="track-detail"></p>
      <a id="track-txid" class="hidden" href="#" target="_blank" rel="noopener"></a>
    </section>

    <details class="proof card">
      <summary>How this page protects your tip</summary>
      <div class="proof-flow">your wallet
   │
   ▼  <span class="ok">direct, on-chain</span>
performer&rsquo;s wallet
   │
   ▼  watch-only eyes
this relay <span class="no">✗ no keys</span> <span class="ok">✓ can only see</span></div>
      <ul>
        <li><strong>Direct to the performer.</strong> The QR/URI is built in <em>your browser</em> and pays the performer&rsquo;s own address. The relay never holds funds and cannot intercept them.</li>
        <li><strong>The relay has no keys.</strong> It only knows a <em>watch-only</em> public key (xpub) &mdash; enough to see payments arrive, mathematically unable to spend them.</li>
        <li><strong>Fresh address every tip.</strong> The address rotates after each payment, so your tip can&rsquo;t be linked to other tippers.</li>
        <li><strong>Double-spend checked.</strong> Payments are screened with BCH DSProof fraud proofs before the toy reacts; larger tips wait for a block confirmation.</li>
        <li><strong>Verify it yourself.</strong> After you pay, your transaction id appears above &mdash; check it on any block explorer.</li>
      </ul>
    </details>

    <section id="unreachable" class="card hidden">
      <p class="big">relay unreachable &mdash; try again later</p>
      <button id="retry" type="button" class="btn-primary">Retry</button>
    </section>

    <footer>lovecash &middot; your tip goes straight to the performer</footer>
  </main>

<script>
(function () {
  "use strict";

  var state = {
    address: null,      // current receive address (rotates after each tip)
    addrIndex: 0,       // bumps on every rotation so the QR img never serves a stale cache entry
    priceUsd: null,     // null hides every USD hint
    sats: 5000,         // effective selection (preset or custom)
    presetSats: 5000,   // last chosen preset, restored when the custom box is cleared
    customActive: false,
    memo: "",
    myTxid: null        // txid we claimed via the amount heuristic; statuses tracked against it
  };

  var connEl = document.getElementById("conn");
  var connLabelEl = document.getElementById("conn-label");
  var pickerEl = document.getElementById("picker");
  var presetsEl = document.getElementById("presets");
  var customEl = document.getElementById("custom");
  var memoEl = document.getElementById("memo");
  var usdHintEl = document.getElementById("usd-hint");
  var qrEl = document.getElementById("qr");
  var linkEl = document.getElementById("uri-link");
  var copyBtn = document.getElementById("copy");
  var thanksEl = document.getElementById("thanks");
  var thanksDetailEl = document.getElementById("thanks-detail");
  var thanksMemoEl = document.getElementById("thanks-memo");
  var unreachableEl = document.getElementById("unreachable");
  var retryBtn = document.getElementById("retry");
  var trackEl = document.getElementById("track");
  var stepsEl = document.getElementById("steps");
  var trackDetailEl = document.getElementById("track-detail");
  var trackTxidEl = document.getElementById("track-txid");
  var tokensEl = document.getElementById("tokens");
  var tokenListEl = document.getElementById("token-list");
  var goalPotEl = document.getElementById("goalpot");
  var potProgressEl = document.getElementById("pot-progress");
  var potFillEl = document.getElementById("pot-fill");

  function renderGoalPot(pot) {
    if (!pot) return;
    var bal = typeof pot.balance_sats === "number" ? pot.balance_sats : 0;
    var goal = pot.goal_sats || 0;
    var pct = goal > 0 ? Math.min(100, (bal / goal) * 100) : 0;
    potProgressEl.textContent = fmtSats(bal) + " / " + fmtSats(goal) + " sats (" + Math.floor(pct) + "%)";
    potFillEl.style.width = pct + "%";
    if (pot.address) document.getElementById("pot-addr").textContent = "pot: " + pot.address;
    goalPotEl.classList.remove("hidden");
  }

  function renderTokenMenu(menu) {
    if (!menu || !menu.length) return;
    for (var i = 0; i < menu.length; i++) {
      var t = menu[i];
      var row = document.createElement("div");
      row.className = "token-row";
      var min = document.createElement("div");
      min.className = "tk-min";
      min.textContent = "≥ " + fmtSats(t.min_amount) + " token units";
      var cat = document.createElement("div");
      cat.className = "tk-cat";
      cat.textContent = t.category;
      var links = document.createElement("div");
      links.className = "tk-links";
      var swap = document.createElement("a");
      swap.href = "https://cauldron.quest";
      swap.target = "_blank";
      swap.rel = "noopener";
      swap.textContent = "Get tokens on Cauldron";
      var copy = document.createElement("button");
      copy.type = "button";
      copy.textContent = "Copy category ID";
      (function (hex, btn) {
        btn.addEventListener("click", function () {
          function done() { btn.textContent = "Copied!"; setTimeout(function () { btn.textContent = "Copy category ID"; }, 1500); }
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(hex).then(done, done);
          } else { done(); }
        });
      })(t.category, copy);
      links.appendChild(swap);
      links.appendChild(copy);
      row.appendChild(min);
      row.appendChild(cat);
      row.appendChild(links);
      tokenListEl.appendChild(row);
    }
    tokensEl.classList.remove("hidden");
  }

  var statusOk = false;

  function fmtSats(n) {
    return Number(n).toLocaleString("en-US");
  }

  function bchFromSats(sats) {
    var s = (sats / 1e8).toFixed(8);
    s = s.replace(/0+$/, "");
    if (s.charAt(s.length - 1) === ".") s = s.slice(0, -1);
    return s;
  }

  function usdFor(sats) {
    if (typeof state.priceUsd !== "number") return null;
    return (sats / 1e8) * state.priceUsd;
  }

  function fmtUsd(v) {
    if (v >= 0.01) return "$" + v.toFixed(2);
    return "$" + v.toFixed(4); // sub-cent tips still get a meaningful hint
  }

  function normalizedAddress() {
    var a = state.address || "";
    if (a && a.indexOf(":") < 0) a = "bitcoincash:" + a;
    return a;
  }

  function paymentParams() {
    var params = [];
    if (state.sats > 0) params.push("amount=" + bchFromSats(state.sats));
    if (state.memo) params.push("message=" + encodeURIComponent(state.memo));
    return params;
  }

  function buildUri() {
    // Client-side BIP21 URI — the tap link carries amount + memo no matter
    // what the server-side QR renderer happens to support.
    var params = paymentParams();
    var uri = normalizedAddress();
    if (params.length) uri += "?" + params.join("&");
    return uri;
  }

  function qrUrl() {
    // Older relays render /qr.png without the message param — harmless, they
    // just ignore it. The "r" param cache-busts the img when the address
    // rotates but amount/memo (and therefore the URL) would be unchanged.
    var params = paymentParams();
    params.push("r=" + state.addrIndex);
    return "/qr.png?" + params.join("&");
  }

  function renderUsd() {
    var spans = presetsEl.querySelectorAll("[data-usd-for]");
    var i;
    for (i = 0; i < spans.length; i += 1) {
      var usd = usdFor(parseInt(spans[i].getAttribute("data-usd-for"), 10));
      spans[i].textContent = usd === null ? "" : "≈ " + fmtUsd(usd);
    }
    var line = fmtSats(state.sats) + " sats = " + bchFromSats(state.sats) + " BCH";
    var cur = usdFor(state.sats);
    if (cur !== null) line += " · ≈ " + fmtUsd(cur);
    usdHintEl.textContent = line;
  }

  function renderPayment() {
    if (!state.address) return;
    var uri = buildUri();
    qrEl.src = qrUrl();
    linkEl.textContent = uri; // textContent only — memo text is attacker-controlled on-chain
    linkEl.setAttribute("href", uri);
    renderUsd();
  }

  function markActivePreset() {
    var btns = presetsEl.querySelectorAll(".preset");
    var i;
    for (i = 0; i < btns.length; i += 1) {
      var match = !state.customActive &&
        parseInt(btns[i].getAttribute("data-sats"), 10) === state.sats;
      btns[i].classList.toggle("active", match);
    }
  }

  presetsEl.addEventListener("click", function (ev) {
    var btn = ev.target;
    while (btn && btn !== presetsEl && !(btn.getAttribute && btn.getAttribute("data-sats"))) {
      btn = btn.parentNode;
    }
    if (!btn || btn === presetsEl) return;
    var sats = parseInt(btn.getAttribute("data-sats"), 10);
    if (isNaN(sats)) return;
    state.sats = sats;
    state.presetSats = sats;
    state.customActive = false;
    customEl.value = "";
    markActivePreset();
    renderPayment();
  });

  customEl.addEventListener("input", function () {
    var v = parseInt(customEl.value, 10);
    if (!isNaN(v) && v > 0) {
      state.sats = v;
      state.customActive = true;
    } else if (customEl.value === "") {
      state.sats = state.presetSats;
      state.customActive = false;
    } else {
      return;
    }
    markActivePreset();
    renderPayment();
  });

  var memoTimer = null;
  memoEl.addEventListener("input", function () {
    // Debounce so /qr.png is not re-rendered on every keystroke.
    if (memoTimer) clearTimeout(memoTimer);
    memoTimer = setTimeout(function () {
      state.memo = memoEl.value.slice(0, 200);
      renderPayment();
    }, 350);
  });

  var copyTimer = null;
  function flashCopied() {
    copyBtn.textContent = "Copied!";
    if (copyTimer) clearTimeout(copyTimer);
    copyTimer = setTimeout(function () {
      copyBtn.textContent = "Copy payment URI";
    }, 1500);
  }

  function copyUri() {
    var uri = buildUri();
    function fallback() {
      // clipboard API needs a secure context; plain-http LAN relays hit this path
      var ta = document.createElement("textarea");
      ta.value = uri;
      ta.setAttribute("readonly", "readonly");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) { /* ancient browser: user copies manually */ }
      document.body.removeChild(ta);
      flashCopied();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(uri).then(flashCopied, fallback);
    } else {
      fallback();
    }
  }
  copyBtn.addEventListener("click", copyUri);

  function setConn(mode, label) {
    connEl.classList.remove("live", "reconnecting", "down");
    connEl.classList.add(mode);
    connLabelEl.textContent = label;
  }

  var STEP_ORDER = ["received", "checking", "queued", "active", "done"];

  function setStep(status, detail) {
    // Map wire status onto a fixed 5-stop stepper; confirming and
    // verifying both light the "checking" stop.
    var stop = status === "confirming" || status === "verifying" ? "checking" : status;
    var rank = STEP_ORDER.indexOf(stop);
    if (rank < 0) return;
    var nodes = stepsEl.querySelectorAll(".step");
    var i;
    for (i = 0; i < nodes.length; i += 1) {
      nodes[i].classList.remove("passed", "now");
      if (i < rank) nodes[i].classList.add("passed");
      else if (i === rank) nodes[i].classList.add(status === "done" ? "passed" : "now");
    }
    if (status === "done") nodes[nodes.length - 1].classList.add("passed");
    trackDetailEl.textContent = detail || "";
  }

  function statusDetail(status, d) {
    if (status === "confirming")
      return d && d.reason === "high_value"
        ? "larger tip — waiting for one block confirmation"
        : "waiting for the next block to confirm";
    if (status === "verifying")
      return "double-spend fraud-proof check (~" + (d && d.window_seconds || 5) + "s)";
    if (status === "queued")
      return "position " + (d && d.position || 1) + " in the play queue";
    if (status === "active") return "toy is reacting right now";
    if (status === "done") return d && d.played === false ? "finished (skipped by safety gate)" : "all done — thanks again!";
    return "";
  }

  function showTrack() {
    trackEl.classList.remove("hidden");
  }

  function onTipStatus(data) {
    if (!data || typeof data.status !== "string") return;
    // Same amount heuristic as onTip: claim a status stream as ours when
    // the txid matches a tip we already claimed, or (before the tip msg
    // lands) when the amount matches what this page is paying.
    if (state.myTxid && data.id !== state.myTxid) return;
    if (!state.myTxid) {
      if (typeof data.amount_sats !== "number" || data.amount_sats !== state.sats) return;
      state.myTxid = data.id;
    }
    showTrack();
    setStep(data.status, statusDetail(data.status, data));
  }

  var thanksTimer = null;
  function showThanks(data) {
    var detail = fmtSats(data.amount_sats) + " sats received";
    var usd = typeof data.usd === "number" ? data.usd : usdFor(data.amount_sats);
    if (usd !== null) detail += " · ≈ " + fmtUsd(usd);
    thanksDetailEl.textContent = detail;
    // Memo is attacker-controlled on-chain text: textContent, never innerHTML.
    thanksMemoEl.textContent = data.memo ? "“" + data.memo + "”" : "";
    if (typeof data.txid === "string" && data.txid) {
      state.myTxid = data.txid;
      trackTxidEl.textContent = "tx: " + data.txid;
      trackTxidEl.setAttribute("href", "https://blockchair.com/bitcoin-cash/transaction/" + data.txid);
      trackTxidEl.classList.remove("hidden");
      showTrack();
      setStep("received", "payment seen on the network");
    }
    pickerEl.classList.add("hidden");
    thanksEl.classList.remove("hidden");
    if (thanksTimer) clearTimeout(thanksTimer);
    thanksTimer = setTimeout(function () {
      thanksEl.classList.add("hidden");
      if (statusOk) pickerEl.classList.remove("hidden");
    }, 8000);
  }

  function onTip(data) {
    if (!data || typeof data.amount_sats !== "number") return;
    // HEURISTIC: an exact-amount match cannot prove this payment scanned this
    // page's QR — another viewer may tip the same amount in the same window,
    // and the address rotates after every tip. Fine for a thank-you moment;
    // never used for crediting anything.
    if (data.amount_sats !== state.sats) return;
    showThanks(data);
  }

  function onAddress(data) {
    if (!data || !data.address) return;
    state.address = data.address;
    state.addrIndex = typeof data.index === "number" ? data.index : state.addrIndex + 1;
    renderPayment(); // rebuild QR + URI for the fresh address
  }

  var ws = null;

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    return proto + location.host + "/overlay-ws";
  }

  function connect() {
    try {
      ws = new WebSocket(wsUrl());
    } catch (e) {
      setConn("reconnecting", "reconnecting");
      setTimeout(connect, 2000);
      return;
    }
    ws.onopen = function () { setConn("live", "live"); };
    ws.onmessage = function (ev) {
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (!msg || typeof msg.type !== "string") return;
      if (msg.type === "tip") onTip(msg.data);
      else if (msg.type === "tip_status") onTipStatus(msg.data);
      else if (msg.type === "goal_pot") renderGoalPot(msg.data);
      else if (msg.type === "address") onAddress(msg.data);
      else if (msg.type === "status") {
        var c = msg.data && msg.data.connection;
        if (c === "connected") setConn("live", "live");
        else if (c === "down") setConn("down", "relay down");
        else setConn("reconnecting", "reconnecting");
      }
    };
    ws.onclose = function () {
      setConn("reconnecting", "reconnecting");
      setTimeout(connect, 2000); // fixed 2s backoff
    };
    ws.onerror = function () {
      try { ws.close(); } catch (e) { /* already closed */ }
    };
  }

  function loadStatus() {
    fetch("/api/status").then(function (resp) {
      if (!resp.ok) throw new Error("http " + resp.status);
      return resp.json();
    }).then(function (data) {
      if (!data || !data.address) throw new Error("no address");
      state.address = data.address;
      state.priceUsd = typeof data.price_usd === "number" ? data.price_usd : null;
      renderTokenMenu(data.token_menu);
      renderGoalPot(data.goal_pot);
      statusOk = true;
      unreachableEl.classList.add("hidden");
      if (thanksEl.classList.contains("hidden")) pickerEl.classList.remove("hidden");
      markActivePreset();
      renderPayment();
    }).catch(function () {
      statusOk = false;
      pickerEl.classList.add("hidden");
      unreachableEl.classList.remove("hidden");
    });
  }
  retryBtn.addEventListener("click", loadStatus);

  loadStatus();
  connect();
})();
</script>
<script type="module">
  // Covenant pledge flow (goal show). The bundle self-checks /api/goal_pot
  // and stays hidden unless a WalletConnect project id is configured, so the
  // read-only bar above is unchanged for unconfigured relays.
  import("/static/pledge.bundle.js").then(function () {
    if (window.LovecashPledge) {
      window.LovecashPledge.init(document.getElementById("goalpot"));
    }
  }).catch(function () { /* bundle absent (not built): read-only panel */ });
</script>
</body>
</html>
"""
