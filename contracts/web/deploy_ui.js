// Browser entry for the performer-side goal-show deploy flow (dashboard).
// Bundled with pledge_ui.js by esbuild (npm run build-web) into
// lovecash/server/ui/static/pledge.bundle.js.
//
// The performer connects Cashonize via WizardConnect (same transport as the
// viewer pledge flow); the wallet signs ONLY the genesis parent P2PKH input
// — lovecash never sees a key. After the wallet broadcasts, the relay
// re-verifies the genesis tx itself (POST /api/goal_show) before watching
// the pot: client-provided parameters are claims, not proof.
import { initiateDappRelay } from '@wizardconnect/core';
import { DappConnectionManager, loadSession } from '@wizardconnect/dapp';
import { hash160, hexToBin, binToHex, hash256, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildDeployTx, POT_SEED } from './deploy_tx.mjs';
import artifact from '../goal_show.json';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text; // never innerHTML
  return node;
}

async function fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`http ${resp.status}`);
  return resp.json();
}

const unwrapAddr = (r) => (typeof r === 'string' ? r : r.address);
const txidOfHex = (hex) => binToHex(hash256(hexToBin(hex)).reverse());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

window.LovecashDeploy = {
  async init(mountEl) {
    let status;
    try {
      status = await fetchJson('/api/status');
    } catch {
      return; // relay trouble: the dashboard's own banner covers it
    }
    if (!mountEl) return;
    if (status.goal_pot) {
      mountEl.appendChild(el('p', 'hint', 'A goal show is already configured. One show at a time — remove goal_show from config.yaml and restart to replace it.'));
      return;
    }
    // The relay tells us its chain (server.features genesis hash) — the tip
    // address is always mainnet-prefixed and must NOT be used for this.
    const netPrefix = status.network === 'mainnet' ? 'bitcoincash' : 'bchtest';

    let currentHeight = 0;
    try {
      currentHeight = (await fetchJson('/api/height')).height;
    } catch { /* hint stays generic */ }

    mountEl.appendChild(el('div', 'section-label', 'Create a covenant goal show'));
    mountEl.appendChild(el('p', 'hint',
      'All-or-nothing tip goals, enforced by a smart contract: viewers pledge into a pot you can ' +
      'claim only if the goal is met by the deadline — otherwise every pledger refunds themselves. ' +
      'Your wallet (Cashonize) signs the creation transaction; lovecash never touches your keys.'));

    const goalInput = el('input');
    goalInput.type = 'number';
    goalInput.min = '100000';
    goalInput.step = '1000';
    goalInput.inputMode = 'numeric';
    goalInput.placeholder = 'Goal in sats (min 100000)';
    goalInput.setAttribute('aria-label', 'Goal in sats');

    const deadlineInput = el('input');
    deadlineInput.type = 'number';
    deadlineInput.min = String(currentHeight + 1);
    deadlineInput.step = '1';
    deadlineInput.inputMode = 'numeric';
    deadlineInput.placeholder = currentHeight
      ? `Deadline block (now ${currentHeight}; +144 ≈ a day)`
      : 'Deadline block height';
    deadlineInput.setAttribute('aria-label', 'Deadline block height');

    const connectBtn = el('button', 'btn-primary', 'Connect wallet (Cashonize)');
    connectBtn.type = 'button';
    const createBtn = el('button', 'btn-primary hidden', `Create goal show (${POT_SEED} sat seed)`);
    createBtn.type = 'button';
    const forgetBtn = el('button', 'btn-primary hidden', 'Forget this wallet');
    forgetBtn.type = 'button';
    forgetBtn.style.background = 'none';
    forgetBtn.style.boxShadow = 'none';
    forgetBtn.style.opacity = '0.6';
    forgetBtn.style.fontSize = '13px';
    const qrWrap = el('div', 'qr-wrap hidden');
    const qrImg = el('img');
    qrImg.alt = 'WizardConnect pairing QR code';
    qrImg.width = 272;
    qrImg.height = 272;
    qrWrap.appendChild(qrImg);
    const uriLink = el('a', 'uri-link hidden', '');
    uriLink.href = '#';
    const copyBtn = el('button', 'btn-primary hidden', 'Copy pairing link');
    copyBtn.type = 'button';
    const statusLine = el('p', 'hint', '');
    statusLine.style.textAlign = 'left';
    const result = el('p', 'hint', '');
    result.style.textAlign = 'left';
    result.style.wordBreak = 'break-all';

    for (const node of [goalInput, deadlineInput, connectBtn, qrWrap, uriLink, copyBtn, createBtn, forgetBtn, statusLine, result]) {
      mountEl.appendChild(node);
    }

    const say = (msg) => { statusLine.textContent = msg; };
    const sayResult = (msg) => { result.textContent = msg; };

    let dappMgr = null;
    let performerAddress = null;

    function onWalletReady() {
      try {
        const pub = dappMgr.getPubkey(0, 0n);
        if (!pub) throw new Error('wallet sent no receive-path xpub');
        performerAddress = unwrapAddr(encodeCashAddress({ prefix: netPrefix, type: CashAddressType.p2pkh, payload: hash160(pub) }));
        qrWrap.classList.add('hidden');
        uriLink.classList.add('hidden');
        copyBtn.classList.add('hidden');
        connectBtn.classList.add('hidden');
        createBtn.classList.remove('hidden');
        forgetBtn.classList.remove('hidden');
        say('connected: ' + performerAddress);
      } catch (e) {
        say('wallet handshake failed: ' + (e && e.message ? e.message : String(e)));
      }
    }

    connectBtn.addEventListener('click', async () => {
      connectBtn.disabled = true;
      say('starting wallet pairing…');
      try {
        dappMgr = new DappConnectionManager('lovecash');
        const relay = initiateDappRelay((payload) => dappMgr.updateConnection(payload.client, payload.status));
        dappMgr.attachRelay(relay);
        qrImg.src = '/qr-data.png?data=' + encodeURIComponent(relay.qrUri || relay.uri);
        qrWrap.classList.remove('hidden');
        uriLink.textContent = relay.uri; // raw wiz:// form: Cashonize web needs paste, not scan
        uriLink.classList.remove('hidden');
        copyBtn.classList.remove('hidden');
        copyBtn.onclick = () => {
          if (navigator.clipboard) navigator.clipboard.writeText(relay.uri).then(() => { copyBtn.textContent = 'Copied!'; }, () => {});
        };
        say('scan the QR with Cashonize, or paste the link into it');
        dappMgr.on('walletready', onWalletReady);
        dappMgr.on('disconnect', (reason, msg) => {
          say('wallet disconnected' + (msg ? ': ' + msg : ''));
          createBtn.classList.add('hidden');
          forgetBtn.classList.add('hidden');
        });
      } catch (e) {
        say('pairing failed: ' + (e && e.message ? e.message : String(e)));
      } finally {
        connectBtn.disabled = false;
      }
    });

    createBtn.addEventListener('click', async () => {
      const goal = parseInt(goalInput.value, 10);
      const deadline = parseInt(deadlineInput.value, 10);
      if (!Number.isFinite(goal) || goal < 100000) {
        sayResult('goal must be at least 100000 sats');
        return;
      }
      if (!Number.isFinite(deadline) || deadline < 1) {
        sayResult('deadline must be a future block height');
        return;
      }
      createBtn.disabled = true;
      try {
        sayResult('fetching wallet UTXOs…');
        const utxoInfo = await fetchJson('/api/utxos?address=' + encodeURIComponent(performerAddress));
        if (!utxoInfo.ok) throw new Error('could not fetch wallet UTXOs from the relay');
        sayResult('building genesis transaction…');
        const { request, category, potTokenAddress } = await buildDeployTx({
          artifact,
          goalSats: goal,
          deadline,
          funderUtxos: utxoInfo.utxos,
          funderAddress: performerAddress,
          userPrompt: `Create goal show: ${goal} sats by block ${deadline}`,
        });
        sayResult('check your wallet to approve…');
        console.log('[lovecash deploy] unsigned tx hex:', request.transaction.transaction);
        const response = await dappMgr.signTransaction(request);
        console.log('[lovecash deploy] wallet response:', JSON.stringify(response));
        if (response.error) throw new Error(response.error);
        const signedHex = response.signedTransaction;
        if (!signedHex) throw new Error('wallet returned no signed transaction');
        const txid = txidOfHex(signedHex);

        // The RELAY broadcasts: it sanity-checks the token category first
        // (a wallet-side re-serialization bug gets a precise error here,
        // bytes logged server-side — not an opaque node rejection).
        const token = localStorage.getItem('lovecash_relay_token') || '';
        const headers = { 'Content-Type': 'application/json', ...(token && { 'X-Relay-Token': token }) };
        sayResult('broadcasting via the relay…');
        const bc = await fetch('/api/broadcast', { method: 'POST', headers, body: JSON.stringify({ tx_hex: signedHex }) });
        const bcBody = await bc.json();
        if (!bc.ok) throw new Error(bcBody.detail || 'broadcast failed');
        console.log('[lovecash deploy] broadcast txid:', bcBody.txid);

        // The relay's Electrum may lag a beat before it sees the genesis.
        const payload = {
          genesis_txid: txid,
          goal_sats: goal,
          deadline,
          performer_pkh: binToHex(hash160(dappMgr.getPubkey(0, 0n))),
          address: potTokenAddress,
        };
        let reg = null;
        for (let attempt = 0; attempt < 6; attempt++) {
          sayResult('verifying genesis on-chain… (attempt ' + (attempt + 1) + ')');
          const resp = await fetch('/api/goal_show', { method: 'POST', headers, body: JSON.stringify(payload) });
          if (resp.status === 404) { await sleep(2500); continue; }
          if (resp.status === 401) {
            const t = prompt('Relay token required to save the show (from your lovecash config):');
            if (!t) throw new Error('relay token required');
            localStorage.setItem('lovecash_relay_token', t);
            headers['X-Relay-Token'] = t;
            continue;
          }
          reg = await resp.json();
          if (!resp.ok) throw new Error(reg.detail || 'relay rejected the genesis');
          break;
        }
        if (!reg) throw new Error('relay never saw the genesis tx — check the relay log, then re-register');
        sayResult('');
        result.appendChild(el('span', null, '✅ goal show live — category ' + category.slice(0, 12) + '…, pot ' + reg.seed_sats.toLocaleString() + ' sats, watching: ' + (reg.watching ? 'yes' : 'after restart')));
        createBtn.classList.add('hidden');
      } catch (e) {
        sayResult('deploy failed: ' + (e && e.message ? e.message : String(e)));
        createBtn.disabled = false;
      }
    });

    // Forget: clear the stored session so the next visit re-pairs.
    forgetBtn.addEventListener('click', async () => {
      try {
        if (dappMgr) {
          dappMgr.clearStoredSession();
          await dappMgr.sendDisconnect('performer left');
        }
      } catch { /* wallet already gone */ }
      dappMgr = null;
      performerAddress = null;
      createBtn.classList.add('hidden');
      forgetBtn.classList.add('hidden');
      connectBtn.classList.remove('hidden');
      say('wallet forgotten — connect again to deploy');
    });

    // Silent reconnect (same stored session as the viewer pledge flow).
    const stored = loadSession();
    if (stored && stored.walletPublicKey) {
      connectBtn.classList.add('hidden');
      say('reconnecting to your wallet…');
      try {
        dappMgr = new DappConnectionManager('lovecash');
        const relay = initiateDappRelay(
          (payload) => dappMgr.updateConnection(payload.client, payload.status),
          { existingCredentials: stored },
        );
        dappMgr.attachRelay(relay);
        dappMgr.on('walletready', onWalletReady);
        onWalletReady();
      } catch (e) {
        dappMgr = null;
        connectBtn.classList.remove('hidden');
        say('stored session failed — pair again');
      }
    }
  },
};
