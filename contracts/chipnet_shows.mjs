#!/usr/bin/env node
// Multi-show chipnet exerciser for the GoalShow covenant (PR #11 follow-up).
// All covenant pots pay out to a FIXED external performer address (TARGET)
// so settlement is verifiable watch-only. Funding/pledging uses the repo
// throwaway key (./.chipnet-wif).
//
//   node chipnet_shows.mjs deploy            deploy all 3 shows, write state
//   node chipnet_shows.mjs config1           print lovecash goal_show YAML for show 1
//   node chipnet_shows.mjs pledge <n> <sats> pledge into show n
//   node chipnet_shows.mjs claim <n>         manual permissionless claim (show 2)
//   node chipnet_shows.mjs refund <n>        refund one receipt (show 3)
//   node chipnet_shows.mjs negclaim <n>      below-goal claim, expect NODE rejection
//   node chipnet_shows.mjs status            pot balances + TARGET balance
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { Contract, ElectrumNetworkProvider, TransactionBuilder, SignatureTemplate } from 'cashscript';
import { secp256k1, hash160, binToHex, hexToBin, decodePrivateKeyWif, encodeCashAddress, decodeCashAddress, CashAddressType } from '@bitauth/libauth';
import artifact from './goal_show.json' with { type: 'json' };

const FEE = 1000n;
const NFT_DUST = 800n;
const POT_SEED = 5_000n;
const TARGET = 'bchtest:qreytkxgddp4kvtc2rwqd36yux999rza7u7z05c6du';
const EXPLORER = 'https://chipnet.imaginary.cash/tx/';
const STATE = new URL('./.chipnet-shows.json', import.meta.url);

// Show 1: goal >= lovecash MIN_GOAL_SATS, far deadline — auto-claim by the
//         running lovecash watcher (the headline PR feature).
// Show 2: small goal, far deadline — manual claim via this script.
// Show 3: unreachable goal, deadline in the PAST — refund + negative claim.
const SHOW_SPECS = {
  1: { goal: 100_000n, deadline: 'future' },
  2: { goal: 8_000n, deadline: 'future' },
  3: { goal: 500_000n, deadline: 'past' },
};

const p2pkhLock = (pkh) => Uint8Array.from([0x76, 0xa9, 0x14, ...pkh, 0x88, 0xac]);
const le64 = (n) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(n); return new Uint8Array(b); };
const bchtest = (pkh, tokens = false) => {
  const r = encodeCashAddress({ prefix: 'bchtest', type: tokens ? CashAddressType.p2pkhWithTokens : CashAddressType.p2pkh, payload: pkh });
  return typeof r === 'string' ? r : r.address;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const decodedTarget = decodeCashAddress(TARGET);
if (typeof decodedTarget === 'string') throw new Error(`bad TARGET address: ${decodedTarget}`);
const targetPkh = decodedTarget.payload;

const wif = readFileSync(new URL('./.chipnet-wif', import.meta.url), 'utf8').trim();
const d = decodePrivateKeyWif(wif);
const priv = d instanceof Uint8Array ? d : d.privateKey;
const pub = secp256k1.derivePublicKeyCompressed(priv);
const pkh = hash160(pub);
const sig = new SignatureTemplate(priv);
const address = bchtest(pkh);

const provider = new ElectrumNetworkProvider('chipnet', { hostname: 'chipnet.imaginary.cash' });

const loadState = () => (existsSync(STATE) ? JSON.parse(readFileSync(STATE, 'utf8')) : {});
const saveState = (s) => writeFileSync(STATE, JSON.stringify(s, null, 2));

async function waitForUtxo(addr, predicate, label) {
  let last = [];
  for (let i = 0; i < 90; i++) {
    last = await provider.getUtxos(addr);
    const found = last.find(predicate);
    if (found) return found;
    if (i % 5 === 4) console.log(`  ... waiting for ${label} (${last.length} utxos visible)`);
    await sleep(2000);
  }
  throw new Error(`timed out waiting for ${label}`);
}

const newContract = (goalSats, deadline, categoryHex) =>
  new Contract(artifact, [targetPkh, goalSats, BigInt(deadline), hexToBin(categoryHex).reverse()], { provider });

// genesis IS the seed: one tx creates the minting NFT directly into the
// covenant (category = spent vout-0 parent's txid). See chipnet_e2e.mjs.
async function genesisSeed(goalSats, deadline, inst, changeFrom = null) {
  let parent = changeFrom
    ? { ...changeFrom, satoshis: BigInt(changeFrom.satoshis) }
    : (await provider.getUtxos(address))
    .filter((u) => u.vout === 0 && !u.token && u.satoshis >= 50_000n)
    .sort((a, b) => Number(b.satoshis - a.satoshis))[0];
  if (!parent) {
    console.log(`[${inst}] no usable vout-0 utxo; self-sending to create one`);
    const any = (await provider.getUtxos(address)).filter((u) => !u.token).sort((a, b) => Number(b.satoshis - a.satoshis))[0];
    const txid = await new TransactionBuilder({ provider })
      .addInput(any, sig.unlockP2PKH())
      .addOutput({ to: p2pkhLock(pkh), amount: 50_000n })
      .addOutput({ to: p2pkhLock(pkh), amount: any.satoshis - 50_000n - FEE })
      .send().then((r) => r.txid);
    console.log(`[${inst}] selfsend: ${EXPLORER}${txid}`);
    parent = await waitForUtxo(address, (u) => u.txid === txid && u.vout === 0, 'self-send vout 0');
  }
  const category = parent.txid;
  const contract = newContract(goalSats, deadline, category);
  const txid = await new TransactionBuilder({ provider })
    .addInput(parent, sig.unlockP2PKH())
    .addOutput({ to: p2pkhLock(pkh), amount: parent.satoshis - POT_SEED - FEE }) // vout 0: change, next parent
    .addOutput({ to: contract.tokenAddress, amount: POT_SEED, token: { category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
    .send().then((r) => r.txid);
  console.log(`[${inst}] genesis+seed: ${EXPLORER}${txid}`);
  const pot = await waitForUtxo(contract.tokenAddress, (u) => u.txid === txid, 'pot');
  if (pot.token?.nft?.capability !== 'minting') throw new Error('deployed pot is missing its minting NFT');
  return { category: parent.txid, goalSats: Number(goalSats), deadline: Number(deadline), potTokenAddress: contract.tokenAddress, potAddress: contract.address, seedTxid: txid, change: { txid, vout: 0, satoshis: Number(parent.satoshis - POT_SEED - FEE) } };
}

const [cmd, ...args] = process.argv.slice(2);

if (cmd === 'deploy') {
  const height = await provider.getBlockHeight();
  const state = { height, target: TARGET, targetPkh: binToHex(targetPkh), shows: {} };
  let change = null;
  for (const [n, spec] of Object.entries(SHOW_SPECS)) {
    const deadline = spec.deadline === 'past' ? height - 1000 : height + 100_000;
    const gen = await genesisSeed(spec.goal, deadline, n, change);
    state.shows[n] = { ...gen, change: undefined };
    change = gen.change;
  }
  saveState(state);
  console.log('\nstate written to', STATE.pathname);
  console.log('performer payout address (TARGET):', TARGET, 'pkh:', binToHex(targetPkh));
  process.exit(0);
}

if (cmd === 'config1') {
  const s = loadState().shows['1'];
  console.log(`goal_show:\n  address: "${s.potTokenAddress}"\n  goal_sats: ${s.goalSats}\n  deadline: ${s.deadline}\n  performer_pkh: "${binToHex(targetPkh)}"`);
  process.exit(0);
}

const state = loadState();
const show = state.shows?.[args[0]];
const needShow = () => { if (!show) { console.error('unknown show; run deploy first'); process.exit(1); } };
const contractOf = (s) => newContract(BigInt(s.goalSats), s.deadline, s.category);
const potOf = async (s) => {
  const utxos = await provider.getUtxos(s.potTokenAddress);
  if (utxos.length !== 1) throw new Error(`expected exactly 1 pot utxo, saw ${utxos.length}`);
  return utxos[0];
};
const largestPlain = () => provider.getUtxos(address)
  .then((us) => us.filter((u) => !u.token).sort((a, b) => Number(b.satoshis - a.satoshis))[0]);

if (cmd === 'pledge') {
  needShow();
  const amount = BigInt(args[1]);
  const contract = contractOf(show);
  const [pot, funds] = [await potOf(show), await largestPlain()];
  const txid = await new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.pledge(pkh))
    .addInput(funds, sig.unlockP2PKH())
    .addOutput({ to: contract.tokenAddress, amount: pot.satoshis + amount, token: { category: show.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
    .addOutput({ to: p2pkhLock(pkh), amount: NFT_DUST, token: { category: show.category, amount: 0n, nft: { capability: 'none', commitment: binToHex(Uint8Array.from([...pkh, ...le64(amount)])) } } })
    .addOutput({ to: p2pkhLock(pkh), amount: funds.satoshis - amount - NFT_DUST - FEE })
    .setLocktime(0)
    .send().then((r) => r.txid);
  console.log(`[${args[0]}] pledge ${amount}: ${EXPLORER}${txid}`);
  const grown = await waitForUtxo(show.potTokenAddress, (u) => u.txid === txid, 'grown pot');
  console.log(`[${args[0]}] pot now ${grown.satoshis} sats (goal ${show.goalSats})`);
  process.exit(0);
}

if (cmd === 'claim') {
  needShow();
  const contract = contractOf(show);
  const pot = await potOf(show);
  const txid = await new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(targetPkh), amount: pot.satoshis - FEE })
    .send().then((r) => r.txid);
  console.log(`[${args[0]}] claim: ${EXPLORER}${txid}`);
  console.log(`[${args[0]}] paid ${pot.satoshis - FEE} sats to ${TARGET}`);
  process.exit(0);
}

if (cmd === 'refund') {
  needShow();
  const contract = contractOf(show);
  const pot = await potOf(show);
  const receipt = (await provider.getUtxos(bchtest(pkh, true)))
    .filter((u) => u.token?.nft && u.token.category === show.category)
    .sort((a, b) => Number(b.satoshis - a.satoshis))[0];
  if (!receipt) throw new Error('no receipt NFT found for this category');
  const refund = BigInt('0x' + binToHex(hexToBin(receipt.token.nft.commitment).slice(20)).match(/../g).reverse().join('')); // 8-byte LE amount
  console.log(`[${args[0]}] receipt ${receipt.txid}:${receipt.vout} commitment=${receipt.token.nft.commitment} amount=${refund} pot=${pot.satoshis}`);
  const txid = await new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.refund())
    .addInput(receipt, sig.unlockP2PKH())
    .addOutput({ to: contract.tokenAddress, amount: pot.satoshis - refund, token: { category: show.category, amount: 0n, nft: { capability: 'minting', commitment: '' } } })
    .addOutput({ to: p2pkhLock(pkh), amount: refund + NFT_DUST - FEE })
    .setLocktime(show.deadline)
    .send().then((r) => r.txid);
  console.log(`[${args[0]}] refund ${refund}: ${EXPLORER}${txid}`);
  const shrunk = await waitForUtxo(show.potTokenAddress, (u) => u.txid === txid, 'shrunk pot');
  console.log(`[${args[0]}] pot now ${shrunk.satoshis} sats`);
  process.exit(0);
}

if (cmd === 'negclaim') {
  needShow();
  const contract = contractOf(show);
  const pot = await potOf(show);
  // build() does NOT evaluate the VM locally; push raw to the node so the
  // rejection is a real consensus verdict.
  const hex = new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(targetPkh), amount: pot.satoshis - FEE })
    .build();
  try {
    const txid = await provider.sendRawTransaction(hex);
    console.error(`UNEXPECTED: below-goal claim accepted: ${EXPLORER}${txid}`);
    process.exit(1);
  } catch (e) {
    console.log(`[${args[0]}] below-goal claim rejected by node as expected:`, String(e?.error ?? e?.message ?? e).slice(0, 300));
  }
  process.exit(0);
}

if (cmd === 'status') {
  for (const [n, s] of Object.entries(state.shows ?? {})) {
    const utxos = await provider.getUtxos(s.potTokenAddress);
    console.log(`show ${n}: pot ${utxos.length === 0 ? 'EMPTY (settled)' : utxos.map((u) => u.satoshis).join('+')} / goal ${s.goalSats}, deadline ${s.deadline}`);
  }
  const t = await provider.getUtxos(TARGET);
  const total = t.reduce((s2, u) => s2 + u.satoshis, 0n);
  console.log(`TARGET ${TARGET}: ${total} sats in ${t.length} utxo(s)`);
  for (const u of t) console.log(`  ${u.txid}:${u.vout} ${u.satoshis} sats`);
  process.exit(0);
}

console.error('usage: deploy | config1 | pledge <n> <sats> | claim <n> | refund <n> | negclaim <n> | status');
process.exit(1);
