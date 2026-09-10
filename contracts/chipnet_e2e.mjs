#!/usr/bin/env node
// Chipnet end-to-end proof for the GoalShow covenant (pre-mainnet gate).
//
//   node chipnet_e2e.mjs --address   print funding address + balance, exit
//   node chipnet_e2e.mjs             run the full flow (requires balance)
//
// Key source: $CHIPNET_WIF, else ./.chipnet-wif (generated once, gitignored).
// Every transaction is built with cashscript's TransactionBuilder against a
// real ElectrumNetworkProvider('chipnet') — the mock suite proved the VM
// logic; this file only proves real-consensus acceptance, so checks here are
// on-chain state checks (getUtxos), not debug() calls.
import { readFileSync, writeFileSync } from 'node:fs';
import { Contract, ElectrumNetworkProvider, TransactionBuilder, SignatureTemplate } from 'cashscript';
import { generatePrivateKey, secp256k1, hash160, binToHex, hexToBin, encodePrivateKeyWif, decodePrivateKeyWif, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import artifact from './goal_show.json' with { type: 'json' };

const FEE = 1000n;
const NFT_DUST = 800n;
const POT_SEED = 5_000n;
const EXPLORER = 'https://chipnet.imaginary.cash/tx/';
const WIF_PATH = new URL('./.chipnet-wif', import.meta.url);

const p2pkhLock = (pkh) => Uint8Array.from([0x76, 0xa9, 0x14, ...pkh, 0x88, 0xac]);
const le64 = (n) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(n); return new Uint8Array(b); };
const bchtest = (pkh, tokens = false) => {
  const r = encodeCashAddress({ prefix: 'bchtest', type: tokens ? CashAddressType.p2pkhWithTokens : CashAddressType.p2pkh, payload: pkh });
  return typeof r === 'string' ? r : r.address;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const txids = { A: {}, B: {} };
const logTx = (inst, step) => (res) => { const txid = res?.txid ?? res; txids[inst][step] = txid; console.log(`[${inst}] ${step}: ${EXPLORER}${txid}`); return txid; };

function loadPerformer() {
  let wif = process.env.CHIPNET_WIF;
  if (!wif) {
    try { wif = readFileSync(WIF_PATH, 'utf8').trim(); } catch { /* first run */ }
  }
  if (!wif) {
    wif = encodePrivateKeyWif(generatePrivateKey(), 'testnet');
    writeFileSync(WIF_PATH, wif + '\n', { mode: 0o600 });
    console.log('generated new throwaway key ->', WIF_PATH.pathname);
  }
  const decoded = decodePrivateKeyWif(wif);
  const priv = decoded instanceof Uint8Array ? decoded : decoded.privateKey;
  const pub = secp256k1.derivePublicKeyCompressed(priv);
  return { priv, pub, pkh: hash160(pub), sig: new SignatureTemplate(priv) };
}

async function balanceOf(provider, address) {
  return (await provider.getUtxos(address)).reduce((s, u) => s + u.satoshis, 0n);
}

async function waitForUtxo(provider, address, predicate, label) {
  let last = [];
  for (let i = 0; i < 90; i++) {
    last = await provider.getUtxos(address);
    const found = last.find(predicate);
    if (found) return found;
    if (i % 5 === 4) console.log(`  ... waiting for ${label} (${last.length} utxos visible)`);
    await sleep(2000);
  }
  throw new Error(`timed out waiting for ${label}; last seen: ${last.map((u) => `${u.txid.slice(0, 8)}:${u.vout}${u.token ? 'T' : ''}`).join(' ')}`);
}

const performer = loadPerformer();
// cashscript's default chipnet server (chipnet.bch.ninja) currently refuses
// connections; chipnet.imaginary.cash:50004 is the working community server.
const provider = new ElectrumNetworkProvider('chipnet', { hostname: 'chipnet.imaginary.cash' });
const address = bchtest(performer.pkh);

if (process.argv.includes('--address')) {
  console.log('address:', address);
  try { console.log('balance:', (await balanceOf(provider, address)).toString(), 'sats'); }
  catch (e) { console.log('balance: unknown (', String(e?.message ?? e ?? 'electrum error'), ')'); }
  process.exit(0);
}

const exit = (msg) => { console.log(msg); process.exit(1); };
const balance = await balanceOf(provider, address);
if (balance < 25_000n) exit(`fund ${address} with at least 25000 chipnet sats, then rerun (balance: ${balance})`);
console.log('performer:', address, 'balance:', balance.toString());

const pledger = { ...(() => { const priv = generatePrivateKey(); const pub = secp256k1.derivePublicKeyCompressed(priv); return { priv, pub, pkh: hash160(pub) }; })(), sig: null };
pledger.sig = new SignatureTemplate(pledger.priv);
console.log('pledger:  ', bchtest(pledger.pkh));

// genesis spends a vout-0 utxo at input index 0; its parent txid becomes the
// category (display-order hex; constructor param wants raw = reversed).
async function genesis(changeFrom, inst) {
  const log = (step) => logTx(inst, step);
  let parent = changeFrom ?? (await provider.getUtxos(address))
    .filter((u) => u.vout === 0 && !u.token && u.satoshis >= 50_000n)
    .sort((a, b) => Number(b.satoshis - a.satoshis))[0];
  if (!parent) {
    console.log('no usable vout-0 utxo; self-sending to create one');
    const any = (await provider.getUtxos(address)).filter((u) => !u.token).sort((a, b) => Number(b.satoshis - a.satoshis))[0];
    const txid = await new TransactionBuilder({ provider })
      .addInput(any, performer.sig.unlockP2PKH())
      .addOutput({ to: p2pkhLock(performer.pkh), amount: 50_000n })
      .addOutput({ to: p2pkhLock(performer.pkh), amount: any.satoshis - 50_000n - FEE })
      .send().then(log('selfsend'));
    parent = await waitForUtxo(provider, address, (u) => u.txid === txid && u.vout === 0, 'self-send vout 0');
  }
  const category = parent.txid;
  const txid = await new TransactionBuilder({ provider })
    .addInput(parent, performer.sig.unlockP2PKH())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: parent.satoshis - NFT_DUST - FEE }) // vout 0: change, keeps a vout-0 spare
    .addOutput({ to: p2pkhLock(performer.pkh), amount: NFT_DUST, token: { category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
    .send().then(log('genesis'));
  const mintNft = await waitForUtxo(provider, bchtest(performer.pkh, true), (u) => u.txid === txid && u.token?.nft?.capability === 'minting', 'minting NFT');
  return { category, mintNft, change: { txid, vout: 0, satoshis: parent.satoshis - NFT_DUST - FEE } };
}

const newContract = (goalSats, deadline, categoryHex) =>
  new Contract(artifact, [performer.pkh, goalSats, BigInt(deadline), hexToBin(categoryHex).reverse()], { provider });

// ---------- Instance A: goal met -> claim ----------
console.log('\n--- instance A (goal 8000, deadline 8000000) ---');
const genA = await genesis(null, 'A');
console.log('category A:', genA.category);
const contractA = newContract(8_000n, 8_000_000, genA.category);

const seedAtxid = await new TransactionBuilder({ provider })
  .addInput(genA.mintNft, performer.sig.unlockP2PKH())
  .addInput(genA.change, performer.sig.unlockP2PKH())
  .addOutput({ to: p2pkhLock(performer.pkh), amount: genA.change.satoshis + NFT_DUST - POT_SEED - 12_000n - FEE }) // vout 0: spare for genesis B
  .addOutput({ to: contractA.tokenAddress, amount: POT_SEED, token: { category: genA.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
  .addOutput({ to: p2pkhLock(pledger.pkh), amount: 12_000n })
  .send().then(logTx('A', 'seed'));
const potA = await waitForUtxo(provider, contractA.tokenAddress, (u) => u.txid === seedAtxid, 'pot A');
const pledgerFunds = await waitForUtxo(provider, bchtest(pledger.pkh), (u) => u.txid === seedAtxid, 'pledger funding');

const pledgeA = 5_000n;
const pledgeAtxid = await new TransactionBuilder({ provider })
  .addInput(potA, contractA.unlock.pledge(pledger.pub))
  .addInput(pledgerFunds, pledger.sig.unlockP2PKH())
  .addOutput({ to: contractA.tokenAddress, amount: potA.satoshis + pledgeA, token: { category: genA.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
  .addOutput({ to: p2pkhLock(pledger.pkh), amount: NFT_DUST, token: { category: genA.category, amount: 0n, nft: { capability: 'none', commitment: binToHex(Uint8Array.from([...pledger.pkh, ...le64(pledgeA)])) } } })
  .addOutput({ to: p2pkhLock(pledger.pkh), amount: pledgerFunds.satoshis - pledgeA - NFT_DUST - FEE })
  .setLocktime(0)
  .send().then(logTx('A', 'pledge'));
const potA2 = await waitForUtxo(provider, contractA.tokenAddress, (u) => u.txid === pledgeAtxid, 'grown pot A');
if (potA2.satoshis !== POT_SEED + pledgeA) exit(`pot A did not grow: ${potA2.satoshis}`);
const receiptA = await waitForUtxo(provider, bchtest(pledger.pkh, true), (u) => u.txid === pledgeAtxid && u.token?.nft, 'receipt NFT');
const wantCommitment = binToHex(Uint8Array.from([...pledger.pkh, ...le64(pledgeA)]));
if (receiptA.token.nft.commitment !== wantCommitment) exit(`receipt commitment mismatch on-chain: ${receiptA.token.nft.commitment} != ${wantCommitment}`);
console.log('on-chain receipt commitment verified:', receiptA.token.nft.commitment);

await new TransactionBuilder({ provider })
  .addInput(potA2, contractA.unlock.claim())
  .addOutput({ to: p2pkhLock(performer.pkh), amount: potA2.satoshis - FEE })
  .send().then(logTx('A', 'claim'));
await sleep(2000);
const potsLeft = await provider.getUtxos(contractA.tokenAddress);
if (potsLeft.length !== 0) exit('claim failed: pot A still exists');
console.log('instance A settled: pot claimed by performer');

// ---------- Instance B: goal missed -> refund, then failed claim ----------
console.log('\n--- instance B (goal 100000, deadline 1) ---');
const spareVout0 = await waitForUtxo(provider, address, (u) => u.txid === seedAtxid && u.vout === 0, 'vout-0 spare');
const genB = await genesis(spareVout0, 'B');
console.log('category B:', genB.category);
const contractB = newContract(100_000n, 1, genB.category);

const seedBtxid = await new TransactionBuilder({ provider })
  .addInput(genB.mintNft, performer.sig.unlockP2PKH())
  .addInput(genB.change, performer.sig.unlockP2PKH())
  .addOutput({ to: contractB.tokenAddress, amount: POT_SEED, token: { category: genB.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
  .addOutput({ to: p2pkhLock(performer.pkh), amount: genB.change.satoshis + NFT_DUST - POT_SEED - FEE })
  .send().then(logTx('B', 'seed'));
const potB = await waitForUtxo(provider, contractB.tokenAddress, (u) => u.txid === seedBtxid, 'pot B');

const pledgerChangeA = await waitForUtxo(provider, bchtest(pledger.pkh), (u) => u.txid === pledgeAtxid && !u.token, 'pledger change');
const pledgeB = 2_000n;
const pledgeBtxid = await new TransactionBuilder({ provider })
  .addInput(potB, contractB.unlock.pledge(pledger.pub))
  .addInput(pledgerChangeA, pledger.sig.unlockP2PKH())
  .addOutput({ to: contractB.tokenAddress, amount: potB.satoshis + pledgeB, token: { category: genB.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
  .addOutput({ to: p2pkhLock(pledger.pkh), amount: NFT_DUST, token: { category: genB.category, amount: 0n, nft: { capability: 'none', commitment: binToHex(Uint8Array.from([...pledger.pkh, ...le64(pledgeB)])) } } })
  .addOutput({ to: p2pkhLock(pledger.pkh), amount: pledgerChangeA.satoshis - pledgeB - NFT_DUST - FEE })
  .setLocktime(0) // 0 < deadline(1): the declared-bound pledge path
  .send().then(logTx('B', 'pledge'));
const potB2 = await waitForUtxo(provider, contractB.tokenAddress, (u) => u.txid === pledgeBtxid, 'grown pot B');
const receiptB = await waitForUtxo(provider, bchtest(pledger.pkh, true), (u) => u.txid === pledgeBtxid && u.token?.nft, 'receipt NFT B');

const refundBtxid = await new TransactionBuilder({ provider })
  .addInput(potB2, contractB.unlock.refund(pledger.sig, pledger.pub))
  .addInput(receiptB, pledger.sig.unlockP2PKH())
  .addOutput({ to: contractB.tokenAddress, amount: potB2.satoshis - pledgeB, token: { category: genB.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
  .addOutput({ to: p2pkhLock(pledger.pkh), amount: pledgeB + NFT_DUST - FEE })
  .setLocktime(1) // tx.time >= deadline(1): CLTV lower bound
  .send().then(logTx('B', 'refund'));
const potB3 = await waitForUtxo(provider, contractB.tokenAddress, (u) => u.txid === refundBtxid, 'reduced pot B');
if (potB3.satoshis !== POT_SEED) exit(`pot B did not shrink back: ${potB3.satoshis}`);
const payoutB = await waitForUtxo(provider, bchtest(pledger.pkh), (u) => u.txid === refundBtxid && !u.token, 'refund payout');
console.log('refund paid out:', payoutB.satoshis.toString(), 'sats; pot continues at', potB3.satoshis.toString());

console.log('\n--- negative: claim below goal on instance B (expect NODE rejection) ---');
try {
  // NB: builder.send() evaluates the VM locally before broadcasting (that is
  // not a consensus proof). build() does not evaluate, so push the raw hex
  // to the node ourselves and let the NODE reject it.
  const hex = new TransactionBuilder({ provider })
    .addInput(potB3, contractB.unlock.claim())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: potB3.satoshis - FEE })
    .build();
  const txid = await provider.sendRawTransaction(hex);
  exit(`UNEXPECTED: below-goal claim broadcast succeeded: ${EXPLORER}${txid}`);
} catch (e) {
  txids.B.failedClaim = String(e?.error ?? e?.message ?? e).slice(0, 300);
  console.log('rejected by node as expected:', txids.B.failedClaim);
}

console.log('\n===== summary =====');
for (const inst of ['A', 'B']) {
  for (const [step, txid] of Object.entries(txids[inst])) {
    console.log(`${inst}.${step.padEnd(12)} ${step === 'failedClaim' ? txid : EXPLORER + txid}`);
  }
}
process.exit(0);
