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
import { DappConnectionManager, loadSession } from '@wizardconnect/dapp';
import { hash160, hexToBin, binToHex, hash256, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildPledgeTx, decodeAnyAddr, toTokenAddress } from './pledge_tx.mjs';
import { buildRefundTx, parseReceiptCommitment } from './refund_tx.mjs';
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
    if (!info.utxo) {
      // Pot UTXO gone => claimed (refunds keep the pot running). Nothing
      // left to pledge or refund — say so and stop.
      mount.appendChild(el('p', 'hint', 'This goal show is over — the pot was claimed.'));
      return;
    }
    // The covenant address tells us which network this show lives on.
    const netPrefix = decodeAnyAddr(info.address).prefix;

    const hint = panelEl.querySelector('#pot-hint');
    if (hint) {
      hint.textContent = 'Pledges go into a smart-contract pot, not the performer\u2019s wallet. ' +
        'Goal met: the pot pays the performer automatically. Goal missed at the deadline: ' +
        'your receipt NFT is your refund ticket — refund promptly when the window opens.';
    }

    const amountInput = el('input');
    amountInput.type = 'number';
    amountInput.min = '5000';
    amountInput.step = '1';
    amountInput.inputMode = 'numeric';
    amountInput.placeholder = 'Pledge amount in sats (min 5000)';
    amountInput.setAttribute('aria-label', 'Pledge amount in sats');
    const pledgeHint = el('p', 'hint',
      'Minimum pledge 5000 sats — the covenant requires it so every receipt can always cover its own refund fee.');
    pledgeHint.style.textAlign = 'left';
    amountInput.insertAdjacentElement('afterend', pledgeHint);
    const connectBtn = el('button', 'btn-primary', 'Connect wallet (Cashonize)');
    connectBtn.type = 'button';
    const pledgeBtn = el('button', 'btn-primary hidden', 'Pledge with Cashonize');
    pledgeBtn.type = 'button';
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
    mount.appendChild(forgetBtn);
    mount.appendChild(status);
    mount.appendChild(result);

    // Refund section: the viewer's receipt NFTs of this show's category.
    const receiptsLabel = el('div', 'section-label hidden', 'Your pledge receipts (refunds)');
    const receiptsList = el('div');
    const receiptsWhy = el('p', 'hint hidden', '');
    receiptsWhy.style.textAlign = 'left';
    mount.appendChild(receiptsLabel);
    mount.appendChild(receiptsList);
    mount.appendChild(receiptsWhy);

    const say = (msg) => { status.textContent = msg; };
    const sayResult = (msg) => { result.textContent = msg; };

    let dappMgr = null;
    let viewerAddress = null;

    function onWalletReady() {
      try {
        // hdwalletv1: child 0 = receive path, index 0 = first receive address.
        // The pledge's inputPaths [[1,'receive',0]] must match this address.
        const pub = dappMgr.getPubkey(0, 0n);
        if (!pub) throw new Error('wallet sent no receive-path xpub');
        viewerAddress = unwrapAddr(encodeCashAddress({ prefix: netPrefix, type: CashAddressType.p2pkh, payload: hash160(pub) }));
        qrWrap.classList.add('hidden');
        uriLink.classList.add('hidden');
        copyBtn.classList.add('hidden');
        connectBtn.classList.add('hidden');
        forgetBtn.classList.remove('hidden');
        pledgeBtn.classList.remove('hidden');
        say('connected: ' + viewerAddress);
        renderReceipts().catch(() => {});
      } catch (e) {
        say('wallet handshake failed: ' + (e && e.message ? e.message : String(e)));
      }
    }

    function wireManagerEvents() {
      dappMgr.on('walletready', onWalletReady);
      dappMgr.on('disconnect', (reason, msg) => {
        say('wallet disconnected' + (msg ? ': ' + msg : ''));
        pledgeBtn.classList.add('hidden');
      });
    }

    function receiptAmount(u) {
      try { return parseReceiptCommitment(u.token.nft.commitment).amount; } catch { return null; }
    }

    async function renderReceipts() {
      receiptsList.textContent = '';
      receiptsLabel.classList.add('hidden');
      receiptsWhy.classList.add('hidden');
      if (!viewerAddress) return;
      const [potInfo, utxoInfo] = await Promise.all([
        fetchJson('/api/goal_pot'),
        fetchJson('/api/utxos?address=' + encodeURIComponent(toTokenAddress(viewerAddress))),
      ]);
      if (!potInfo.configured || !potInfo.utxo || !utxoInfo.ok) return;
      const category = potInfo.utxo.token.category;
      const receipts = utxoInfo.utxos.filter((u) =>
        u.token && u.token.nft && u.token.nft.capability === 'none' &&
        u.token.category === category && receiptAmount(u) !== null);
      if (!receipts.length) return;
      receiptsLabel.classList.remove('hidden');

      const open = potInfo.current_height >= potInfo.deadline && potInfo.balance_sats < potInfo.goal_sats;
      receiptsWhy.textContent = open
        ? 'Refunds are open — the deadline passed below goal. Each refund is its own transaction.'
        : 'Refunds open after the deadline if the goal is missed. Until then your receipt is just a ticket.';
      receiptsWhy.classList.remove('hidden');

      for (const receipt of receipts) {
        const amount = receiptAmount(receipt);
        const row = el('div', 'token-row');
        row.appendChild(el('div', 'tk-min', amount.toLocaleString() + ' sats pledged'));
        // The 5000-sat min pledge guarantees every receipt covers its own
        // refund fee (payout = amount + receipt dust - fee, fee <= 1000).
        const label = open
          ? 'Refund ' + amount.toLocaleString() + ' sats'
          : 'Refund (not open yet)';
        const btn = el('button', 'btn-primary', label);
        btn.type = 'button';
        btn.disabled = !open;
        btn.addEventListener('click', async () => {
          btn.disabled = true;
          sayResult('building refund transaction\u2026');
          try {
            // The pot is serialized: ALWAYS rebuild against the freshest pot UTXO.
            const fresh = await fetchJson('/api/goal_pot');
            if (!fresh.utxo) throw new Error('pot UTXO not found — show over or pot moved; reload and retry');
            if (!(fresh.current_height >= fresh.deadline && fresh.balance_sats < fresh.goal_sats)) {
              throw new Error('refund window closed (goal met or deadline not reached)');
            }
            const { request } = await buildRefundTx({
              artifact,
              contractParams: {
                performerPkh: fresh.performer_pkh,
                goalSats: fresh.goal_sats,
                deadline: fresh.deadline,
                categoryDisplayHex: fresh.utxo.token.category,
              },
              potUtxo: fresh.utxo,
              receiptUtxo: receipt,
              funderAddress: viewerAddress,
              deadline: fresh.deadline,
              userPrompt: `Refund ${amount} sats from the goal show`,
            });
            sayResult('check your wallet to approve\u2026');
            const response = await dappMgr.signTransaction(request);
            if (response.error) throw new Error(response.error);
            const txid = txidOfHex(response.signedTransaction);
            result.textContent = '';
            const link = el('a', null, 'refund broadcast: ' + txid);
            link.href = EXPLORER + txid;
            link.target = '_blank';
            link.rel = 'noopener';
            link.style.color = '#ff9a5c';
            result.appendChild(el('span', null, '\u2705 '));
            result.appendChild(link);
            renderReceipts().catch(() => {});
          } catch (e) {
            sayResult('refund failed: ' + (e && e.message ? e.message : String(e)) + ' — if the pot moved (another refund landed), retry with a fresh build.');
            btn.disabled = false;
          }
        });
        row.appendChild(btn);
        receiptsList.appendChild(row);
      }
    }

    connectBtn.addEventListener('click', async () => {
      connectBtn.disabled = true;
      say('starting wallet pairing…');
      try {
        // Default session config: persists to localStorage, so a refresh
        // (or next visit) reconnects silently — see the init path below.
        dappMgr = new DappConnectionManager('lovecash');
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

        wireManagerEvents();
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

    // Forget: clear the stored session so the next visit re-pairs.
    forgetBtn.addEventListener('click', async () => {
      try {
        if (dappMgr) {
          dappMgr.clearStoredSession();
          await dappMgr.sendDisconnect('viewer left');
        }
      } catch { /* wallet already gone */ }
      dappMgr = null;
      viewerAddress = null;
      pledgeBtn.classList.add('hidden');
      forgetBtn.classList.add('hidden');
      receiptsLabel.classList.add('hidden');
      receiptsList.textContent = '';
      receiptsWhy.classList.add('hidden');
      connectBtn.classList.remove('hidden');
      say('wallet forgotten — connect again to pledge');
    });

    // Silent reconnect: a stored session restores the wallet's xpubs (the
    // address derives locally, no round-trip) and re-pairs over the relay
    // without a QR. Sign requests queue until the wallet app reopens.
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
        wireManagerEvents();
        onWalletReady(); // xpubs were restored from storage at construction
      } catch (e) {
        dappMgr = null;
        connectBtn.classList.remove('hidden');
        say('stored session failed (' + (e && e.message ? e.message : String(e)) + ') — pair again');
      }
    }
  },
};
