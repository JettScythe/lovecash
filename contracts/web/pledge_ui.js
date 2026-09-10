// Browser entry for the viewer-facing covenant pledge flow.
// Bundled by esbuild (npm run build-web) into lovecash/server/ui/static/
// pledge.bundle.js — the compiled covenant artifact is INLINED into the
// bundle at build time, so rebuild after every cashc recompile.
//
// Wallet transport: BCH WalletConnect (wc2-bch-bcr) via @walletconnect/
// sign-client; the wallet signs with placeholderP2PKHUnlocker inputs (no
// covenant pubkey placeholders anywhere in the pledge path).
//
// NOT e2e-tested without a real wallet + WalletConnect project id: the
// pairing/namespace/method flow follows the wc2-bch-bcr spec as implemented
// by Cashonize — verify against a real wallet before shipping to viewers.
import SignClient from '@walletconnect/sign-client';
import { stringify } from '@bitauth/libauth';
import { buildPledgeTx } from './pledge_tx.mjs';
import artifact from '../goal_show.json';

const CHAIN = 'bch:bitcoincash';
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

window.LovecashPledge = {
  async init(panelEl) {
    let info;
    try {
      info = await fetchJson('/api/goal_pot');
    } catch {
      return; // relay trouble: leave the read-only bar alone
    }
    if (!info.configured || !info.wc_project_id) return; // read-only panel
    const mount = panelEl.querySelector('#pot-pledge-mount');
    if (!mount) return;

    const hint = panelEl.querySelector('#pot-hint');
    if (hint) {
      hint.textContent = 'Pledges go into a smart-contract pot, not the performer\u2019s wallet. ' +
        'If the goal isn\u2019t reached by the deadline, your receipt NFT is your on-chain refund ticket.';
    }

    const status = el('p', 'hint', '');
    status.style.textAlign = 'left';
    const amountInput = el('input');
    amountInput.type = 'number';
    amountInput.min = '546';
    amountInput.step = '1';
    amountInput.inputMode = 'numeric';
    amountInput.placeholder = 'Pledge amount in sats (min 546)';
    amountInput.setAttribute('aria-label', 'Pledge amount in sats');
    const connectBtn = el('button', 'btn-primary', 'Connect Cashonize');
    connectBtn.type = 'button';
    const pledgeBtn = el('button', 'btn-primary', 'Pledge with Cashonize');
    pledgeBtn.type = 'button';
    const qrWrap = el('div', 'qr-wrap hidden');
    const qrImg = el('img');
    qrImg.alt = 'WalletConnect pairing QR code';
    qrImg.width = 272;
    qrImg.height = 272;
    qrWrap.appendChild(qrImg);
    const copyBtn = el('button', 'btn-primary hidden', 'Copy pairing link');
    copyBtn.type = 'button';
    const result = el('p', 'hint', '');
    result.style.textAlign = 'left';
    result.style.wordBreak = 'break-all';

    mount.appendChild(amountInput);
    mount.appendChild(connectBtn);
    mount.appendChild(qrWrap);
    mount.appendChild(copyBtn);
    mount.appendChild(pledgeBtn);
    mount.appendChild(status);
    mount.appendChild(result);

    let client = null;
    let session = null; // in-memory only: a page reload = reconnect (no stored topics)
    let viewerAddress = null;
    pledgeBtn.classList.add('hidden');

    const say = (msg) => { status.textContent = msg; };
    const sayResult = (msg) => { result.textContent = msg; };

    connectBtn.addEventListener('click', async () => {
      connectBtn.disabled = true;
      say('starting WalletConnect pairing\u2026');
      try {
        client = await SignClient.init({ projectId: info.wc_project_id });
        const { uri, approval } = await client.connect({
          requiredNamespaces: { bch: { chains: [CHAIN], methods: ['bch_signTransaction'], events: [] } },
        });
        if (uri) {
          qrImg.src = '/qr-data.png?data=' + encodeURIComponent(uri);
          qrWrap.classList.remove('hidden');
          copyBtn.classList.remove('hidden');
          copyBtn.onclick = () => {
            if (navigator.clipboard) navigator.clipboard.writeText(uri).then(() => { copyBtn.textContent = 'Copied!'; }, () => {});
          };
          say('scan the QR with Cashonize (or copy the pairing link)');
        }
        session = await approval();
        const accounts = (session.namespaces.bch && session.namespaces.bch.accounts) || [];
        if (!accounts.length) throw new Error('wallet approved no bch accounts');
        viewerAddress = accounts[0].split(':').slice(2).join(':'); // bch:bitcoincash:<addr>
        qrWrap.classList.add('hidden');
        copyBtn.classList.add('hidden');
        pledgeBtn.classList.remove('hidden');
        say('connected: ' + viewerAddress);
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
        if (!utxoInfo.ok) throw new Error('could not fetch your wallet UTXOs');
        const { wcTransactionObject } = await buildPledgeTx({
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
        // wc2-bch-bcr: with broadcast:true the wallet broadcasts and returns the txid.
        if (!client || !session) throw new Error('session lost — reconnect the wallet');
        const wcResult = await client.request({ topic: session.topic, chainId: CHAIN, request: { method: 'bch_signTransaction', params: JSON.parse(stringify(wcTransactionObject)) } });
        const txid = typeof wcResult === 'string' ? wcResult : (wcResult && wcResult.txid) || JSON.stringify(wcResult);
        result.textContent = '';
        const link = el('a', null, 'pledge broadcast: ' + txid);
        link.href = EXPLORER + txid;
        link.target = '_blank';
        link.rel = 'noopener';
        link.style.color = '#ff9a5c';
        result.appendChild(el('span', null, '\u2705 '));
        result.appendChild(link);
      } catch (e) {
        // Verbatim wallet/node error + the one hint that matters for a
        // serialized pot: someone else may have moved it — retry fresh.
        sayResult('pledge failed: ' + (e && e.message ? e.message : String(e)) + ' — if the pot moved (another pledge landed), retry with a fresh build.');
      } finally {
        pledgeBtn.disabled = false;
      }
    });
  },
};
