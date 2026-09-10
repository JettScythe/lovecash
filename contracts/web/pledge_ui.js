// Browser entry for the viewer-facing covenant pledge flow.
// Bundled by esbuild (npm run build-web) into lovecash/server/ui/static/
// pledge.bundle.js — the compiled covenant artifact is INLINED into the
// bundle at build time, so rebuild after every cashc recompile.
//
// Wallet transport: WizardConnect (Nostr NIP-17 relay, no cloud project id)
// as implemented by Cashonize v0.9.0+. The wallet signs the funder P2PKH
// inputs (placeholder unlockers leave them empty; the wallet fills them per
// inputPaths); the covenant pot input ships complete.
//
// NOT e2e-tested without a real wallet: relay reachability, the wallet's
// 'receive'-path index-0 address alignment, and broadcast:true semantics
// all follow the wc2-bch-bcr / hdwalletv1 specs — verify with real
// Cashonize before shipping to viewers.
import { initiateDappRelay } from '@wizardconnect/core';
import { DappConnectionManager } from '@wizardconnect/dapp';
import { hash160, hexToBin, binToHex, hash256, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildPledgeTx, decodeAnyAddr } from './pledge_tx.mjs';
import artifact from '../goal_show.json';

const EXPLORER = 'https://blockchair.com/bitcoin-cash/transaction/';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text; // never innerHTML: on-chain/session data is attacker-adjacent
  return node;
}

async function fetchJson(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`http ${resp.status}`);
  return resp.json();
}

const unwrapAddr = (r) => (typeof r === 'string' ? r : r.address);
const txidOfHex = (hex) => binToHex(hash256(hexToBin(hex)).reverse());

window.LovecashPledge = {
  async init(panelEl) {
    let info;
    try {
      info = await fetchJson('/api/goal_pot');
    } catch {
      return; // relay trouble: leave the read-only bar alone
    }
    if (!info.configured) return; // read-only panel (no wallet transport gate anymore)
    const mount = panelEl.querySelector('#pot-pledge-mount');
    if (!mount) return;
    // The covenant address tells us which network this show lives on.
    const netPrefix = decodeAnyAddr(info.address).prefix;

    const hint = panelEl.querySelector('#pot-hint');
    if (hint) {
      hint.textContent = 'Pledges go into a smart-contract pot, not the performer\u2019s wallet. ' +
        'If the goal isn\u2019t reached by the deadline, your receipt NFT is your on-chain refund ticket.';
    }

    const amountInput = el('input');
    amountInput.type = 'number';
    amountInput.min = '546';
    amountInput.step = '1';
    amountInput.inputMode = 'numeric';
    amountInput.placeholder = 'Pledge amount in sats (min 546)';
    amountInput.setAttribute('aria-label', 'Pledge amount in sats');
    const connectBtn = el('button', 'btn-primary', 'Connect wallet (Cashonize)');
    connectBtn.type = 'button';
    const pledgeBtn = el('button', 'btn-primary hidden', 'Pledge with Cashonize');
    pledgeBtn.type = 'button';
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
    const status = el('p', 'hint', '');
    status.style.textAlign = 'left';
    const result = el('p', 'hint', '');
    result.style.textAlign = 'left';
    result.style.wordBreak = 'break-all';

    mount.appendChild(amountInput);
    mount.appendChild(connectBtn);
    mount.appendChild(qrWrap);
    mount.appendChild(uriLink);
    mount.appendChild(copyBtn);
    mount.appendChild(pledgeBtn);
    mount.appendChild(status);
    mount.appendChild(result);

    const say = (msg) => { status.textContent = msg; };
    const sayResult = (msg) => { result.textContent = msg; };

    let dappMgr = null;
    let viewerAddress = null;

    connectBtn.addEventListener('click', async () => {
      connectBtn.disabled = true;
      say('starting wallet pairing\u2026');
      try {
        // session:false — a tip page is a one-shot visit; no localStorage
        // residue. Cost: the pairing QR is fresh on every page load.
        dappMgr = new DappConnectionManager('lovecash', undefined, { session: false });
        const relay = initiateDappRelay((payload) => dappMgr.updateConnection(payload.client, payload.status));
        dappMgr.attachRelay(relay);

        const qrUri = relay.qrUri || relay.uri; // uppercase/encoded: QR alphanumeric mode
        const uri = relay.uri;                  // raw wiz:// form: paste/copy
        qrImg.src = '/qr-data.png?data=' + encodeURIComponent(qrUri);
        qrWrap.classList.remove('hidden');
        uriLink.textContent = uri; // phone viewers can't scan their own screen
        uriLink.classList.remove('hidden');
        copyBtn.classList.remove('hidden');
        copyBtn.onclick = () => {
          if (navigator.clipboard) navigator.clipboard.writeText(uri).then(() => { copyBtn.textContent = 'Copied!'; }, () => {});
        };
        say('scan the QR with Cashonize, or paste the link into it');

        dappMgr.on('walletready', () => {
          try {
            // hdwalletv1: child 0 = receive path, index 0 = first receive address.
            // The pledge's inputPaths [[1,'receive',0]] must match this address.
            const pub = dappMgr.getPubkey(0, 0n);
            if (!pub) throw new Error('wallet sent no receive-path xpub');
            viewerAddress = unwrapAddr(encodeCashAddress({ prefix: netPrefix, type: CashAddressType.p2pkh, payload: hash160(pub) }));
            qrWrap.classList.add('hidden');
            uriLink.classList.add('hidden');
            copyBtn.classList.add('hidden');
            pledgeBtn.classList.remove('hidden');
            say('connected: ' + viewerAddress);
          } catch (e) {
            say('wallet handshake failed: ' + (e && e.message ? e.message : String(e)));
          }
        });
        dappMgr.on('disconnect', (reason, msg) => {
          say('wallet disconnected' + (msg ? ': ' + msg : ''));
          pledgeBtn.classList.add('hidden');
        });
      } catch (e) {
        say('pairing failed: ' + (e && e.message ? e.message : String(e)));
      } finally {
        connectBtn.disabled = false;
      }
    });

    pledgeBtn.addEventListener('click', async () => {
      const amount = parseInt(amountInput.value, 10);
      if (!Number.isFinite(amount) || amount < 546) {
        sayResult('enter at least 546 sats');
        return;
      }
      pledgeBtn.disabled = true;
      sayResult('building pledge transaction\u2026');
      try {
        // The pot is serialized: ALWAYS rebuild against the freshest pot UTXO.
        const [potInfo, utxoInfo] = await Promise.all([
          fetchJson('/api/goal_pot'),
          fetchJson('/api/utxos?address=' + encodeURIComponent(viewerAddress)),
        ]);
        if (!potInfo.utxo) throw new Error('pot UTXO not found — show over or pot moved; reload and retry');
        if (!utxoInfo.ok) throw new Error('could not fetch wallet UTXOs from the relay');
        const { request } = await buildPledgeTx({
          artifact,
          contractParams: {
            performerPkh: potInfo.performer_pkh,
            goalSats: potInfo.goal_sats,
            deadline: potInfo.deadline,
            categoryDisplayHex: potInfo.utxo.token.category,
          },
          potUtxo: potInfo.utxo,
          funderUtxos: utxoInfo.utxos,
          funderAddress: viewerAddress,
          amountSats: BigInt(amount),
          userPrompt: `Pledge ${amount} sats to the goal show`,
        });
        sayResult('check your wallet to approve\u2026');
        // hdwalletv1: broadcast:true asks the WALLET to broadcast; the
        // response carries the signed tx hex. txid derived locally.
        const response = await dappMgr.signTransaction(request);
        if (response.error) throw new Error(response.error);
        const txid = txidOfHex(response.signedTransaction);
        result.textContent = '';
        const link = el('a', null, 'pledge broadcast: ' + txid);
        link.href = EXPLORER + txid;
        link.target = '_blank';
        link.rel = 'noopener';
        link.style.color = '#ff9a5c';
        result.appendChild(el('span', null, '\u2705 '));
        result.appendChild(link);
      } catch (e) {
        // Verbatim wallet/relay error + the one hint that matters for a
        // serialized pot: someone else may have moved it — retry fresh.
        sayResult('pledge failed: ' + (e && e.message ? e.message : String(e)) + ' — if the pot moved (another pledge landed), retry with a fresh build.');
      } finally {
        pledgeBtn.disabled = false;
      }
    });
  },
};
