import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Contract, MockNetworkProvider, TransactionBuilder, SignatureTemplate } from 'cashscript';
import { generatePrivateKey, secp256k1, hash160, binToHex, hexToBin } from '@bitauth/libauth';
import artifact from './goal_show.json' with { type: 'json' };

const GOAL_SATS = 100_000n;
const DEADLINE = 800_000; // block height
// Deliberately non-palindromic: catches any byte-order bug in category handling.
// CATEGORY is the display-order hex (as shown by wallets/explorers); the
// covenant compares against the raw serialized byte order, which is reversed.
const CATEGORY = '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f';
const CATEGORY_RAW = hexToBin(CATEGORY).reverse();
const FEE = 1000n;
const RECEIPT_DUST = 800n; // token outputs need more than the 546 bare dust
const POT_DUST = 678n; // dust floor of the token-bearing pot continuation

const p2pkhLock = (pkh) => Uint8Array.from([0x76, 0xa9, 0x14, ...pkh, 0x88, 0xac]);
const le64 = (n) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(n); return new Uint8Array(b); };
const receiptCommitment = (pkh, amount) => binToHex(Uint8Array.from([...pkh, ...le64(amount)]));

let txCounter = 0;
const nextTxid = () => (++txCounter).toString(16).padStart(64, '0');

function makeKey() {
  const priv = generatePrivateKey();
  const pub = secp256k1.derivePublicKeyCompressed(priv);
  return { priv, pub, pkh: hash160(pub), sig: new SignatureTemplate(priv) };
}

const mintingNft = (category = CATEGORY) => ({ category, amount: 0n, nft: { capability: 'minting', commitment: '' } });
const receiptNft = (pkh, amount, capability = 'none') => ({ category: CATEGORY, amount: 0n, nft: { capability, commitment: receiptCommitment(pkh, amount) } });

// Fresh provider + contract + performer key; seedPot(value, token) adds the pot UTXO.
function setup() {
  const provider = new MockNetworkProvider();
  const performer = makeKey();
  const contract = new Contract(artifact, [performer.pkh, GOAL_SATS, BigInt(DEADLINE), CATEGORY_RAW], { provider });
  const seedPot = (satoshis, token = mintingNft()) => provider.addUtxo(contract.tokenAddress, {
    txid: nextTxid(), vout: 0, satoshis, token,
  });
  const addFunder = (key, satoshis) => provider.addUtxo(binToHex(p2pkhLock(key.pkh)), {
    txid: nextTxid(), vout: 0, satoshis,
  });
  return { provider, performer, contract, seedPot, addFunder };
}

// Builds (and VM-evaluates) a pledge tx: pot + funding -> pot+amount, receipt, change.
function pledgeTx({ provider, contract, pot, pledger, amount, locktime = DEADLINE - 1, funder = makeKey(), forgeReceipt = false, potFirst = true }) {
  const funding = provider.addUtxo(binToHex(p2pkhLock(funder.pkh)), {
    txid: nextTxid(), vout: 0, satoshis: amount + RECEIPT_DUST + FEE + 1000n,
  });
  const builder = new TransactionBuilder({ provider });
  const inputs = [
    [pot, contract.unlock.pledge(pledger.pkh)],
    [funding, funder.sig.unlockP2PKH()],
  ];
  if (!potFirst) inputs.reverse();
  return builder
    .addInput(...inputs[0])
    .addInput(...inputs[1])
    .addOutput({ to: contract.tokenAddress, amount: pot.satoshis + amount, token: mintingNft() })
    .addOutput({ to: p2pkhLock(pledger.pkh), amount: RECEIPT_DUST, token: receiptNft(pledger.pkh, amount) })
    .addOutput({ to: p2pkhLock(funder.pkh), amount: 1000n, token: forgeReceipt ? receiptNft(funder.pkh, amount) : undefined })
    .setLocktime(locktime);
}

// Builds a refund tx: pot + receipt -> pot-amount, payout to pledger.
// refund() takes no args: the receipt's own P2PKH input proves ownership.
function refundTx({ provider, contract, pot, pledger, amount, locktime = DEADLINE, receiptPkh = null, receiptCapability = 'none', commitmentHex = null, continuation = null, payout = null, extraFunding = null, potFirst = true }) {
  const receipt = provider.addUtxo(binToHex(p2pkhLock(pledger.pkh)), {
    txid: nextTxid(), vout: 0, satoshis: RECEIPT_DUST,
    token: { category: CATEGORY, amount: 0n, nft: { capability: receiptCapability, commitment: commitmentHex ?? receiptCommitment(receiptPkh ?? pledger.pkh, amount) } },
  });
  const builder = new TransactionBuilder({ provider });
  const inputs = [
    [pot, contract.unlock.refund()],
    [receipt, pledger.sig.unlockP2PKH()],
  ];
  if (!potFirst) inputs.reverse();
  builder.addInput(...inputs[0]).addInput(...inputs[1]);
  if (extraFunding) builder.addInput(extraFunding.utxo, extraFunding.key.sig.unlockP2PKH());
  return { receipt, builder: builder
    .addOutput({ to: contract.tokenAddress, amount: continuation ?? (pot.satoshis - amount), token: mintingNft() })
    .addOutput({ to: p2pkhLock(pledger.pkh), amount: payout ?? (amount + RECEIPT_DUST - FEE) })
    .setLocktime(locktime) };
}

test('pledge grows the pot and mints a receipt with byte-exact commitment', async () => {
  const { provider, contract, seedPot } = setup();
  const pledger = makeKey();
  const pot = seedPot(50_000n);

  const builder = pledgeTx({ provider, contract, pot, pledger, amount: 10_000n });
  builder.debug(); // full VM evaluation — throws if any require fails
  await builder.send();

  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots.length, 1);
  assert.equal(pots[0].satoshis, 60_000n);
  assert.equal(pots[0].token.nft.capability, 'minting');

  const receipts = await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(pledger.pkh)));
  assert.equal(receipts.length, 1);
  assert.equal(receipts[0].token.nft.capability, 'none');
  assert.equal(receipts[0].token.nft.commitment, receiptCommitment(pledger.pkh, 10_000n));
  assert.equal(receipts[0].token.nft.commitment.length / 2, 28);
});

test('pledge is refused once locktime reaches the deadline', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(50_000n);
  const builder = pledgeTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, locktime: DEADLINE });
  assert.throws(() => builder.debug(), /past deadline/);
});

test('pledge below the 5000-sat minimum is refused (dust-DoS + refund-fee floor)', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(50_000n);
  const builder = pledgeTx({ provider, contract, pot, pledger: makeKey(), amount: 4_999n });
  assert.throws(() => builder.debug(), /below minimum/);
});

test('pledge cannot smuggle a forged receipt into the change output', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(50_000n);
  const builder = pledgeTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, forgeReceipt: true });
  assert.throws(() => builder.debug(), /tokenless/);
});

test('pledge is rejected when the pot is not input 0', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(50_000n);
  const builder = pledgeTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, potFirst: false });
  assert.throws(() => builder.debug(), /pot must be input 0/);
});

test('pledge is rejected when the pot NFT has the wrong category', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(50_000n, mintingNft('ff'.repeat(32)));
  const builder = pledgeTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n });
  assert.throws(() => builder.debug(), /wrong category/);
});

test('claim fails below the goal', () => {
  const { provider, performer, contract, seedPot } = setup();
  const pot = seedPot(GOAL_SATS - 1n);
  const builder = new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: pot.satoshis - FEE });
  assert.throws(() => builder.debug(), /goal not met/);
});

test('claim at the goal pays the whole pot to the performer', async () => {
  const { provider, performer, contract, seedPot } = setup();
  const pot = seedPot(GOAL_SATS);
  const builder = new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: pot.satoshis - FEE });
  builder.debug();
  await builder.send();

  assert.equal((await provider.getUtxos(contract.tokenAddress)).length, 0); // pot does not continue
  const payouts = await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(performer.pkh)));
  assert.equal(payouts.length, 1);
  assert.equal(payouts[0].satoshis, GOAL_SATS - FEE);
  assert.equal(payouts[0].token, undefined); // minting NFT burned
});

test('claim is rejected when the pot is not input 0', () => {
  const { provider, performer, contract, seedPot, addFunder } = setup();
  const decoy = makeKey();
  const pot = seedPot(GOAL_SATS);
  const builder = new TransactionBuilder({ provider })
    .addInput(addFunder(decoy, 10_000n), decoy.sig.unlockP2PKH())
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: pot.satoshis + 10_000n - FEE });
  assert.throws(() => builder.debug(), /pot must be input 0|spends the pot only/);
});

test('claim is rejected with a tokenless pot', () => {
  const { provider, performer, contract } = setup();
  const pot = provider.addUtxo(contract.tokenAddress, { txid: nextTxid(), vout: 0, satoshis: GOAL_SATS }); // no token at all
  const builder = new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: pot.satoshis - FEE });
  assert.throws(() => builder.debug(), /pot must carry an NFT/);
});

test('claim is rejected with a non-minting pot NFT', () => {
  const { provider, performer, contract, seedPot } = setup();
  const pot = seedPot(GOAL_SATS, { category: CATEGORY, amount: 0n, nft: { capability: 'none', commitment: '' } });
  const builder = new TransactionBuilder({ provider })
    .addInput(pot, contract.unlock.claim())
    .addOutput({ to: p2pkhLock(performer.pkh), amount: pot.satoshis - FEE });
  assert.throws(() => builder.debug(), /pot must carry an NFT/);
});

test('refund fails before the deadline', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, locktime: DEADLINE - 1 });
  assert.throws(() => builder.debug(), /before deadline/);
});

test('refund fails when the goal was met', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(GOAL_SATS);
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n });
  assert.throws(() => builder.debug(), /goal was met/);
});

test('refund after deadline, under goal: pot shrinks, pledger is paid, receipt burned', async () => {
  const { provider, contract, seedPot } = setup();
  const pledger = makeKey();
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger, amount: 10_000n });
  builder.debug();
  await builder.send();

  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots.length, 1);
  assert.equal(pots[0].satoshis, 50_000n);

  const pledgerUtxos = await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(pledger.pkh)));
  assert.equal(pledgerUtxos.length, 1);
  assert.equal(pledgerUtxos[0].satoshis, 10_000n + RECEIPT_DUST - FEE);
  assert.equal(pledgerUtxos[0].token, undefined); // receipt NFT burned, not returned
});

test('refund cannot be redirected: payout must go to the committed pkh', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(60_000n);
  const other = makeKey();
  // Receipt committed to `other`, but the tx pays `pledger` — the
  // covenant locks the payout to the commitment.
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, receiptPkh: other.pkh });
  assert.throws(() => builder.debug(), /refund not to pledger/);
});

test('refund is rejected when the pot is not input 0', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, potFirst: false });
  assert.throws(() => builder.debug(), /pot must be input 0/);
});

test('refund is rejected with more than 2 inputs', () => {
  const { provider, contract, seedPot, addFunder } = setup();
  const extra = makeKey();
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, extraFunding: { utxo: addFunder(extra, 10_000n), key: extra } });
  assert.throws(() => builder.debug(), /pot \+ one receipt input/);
});

test('refund rejects a receipt whose amount bytes have the sign bit set', () => {
  const { provider, contract, seedPot } = setup();
  const pledger = makeKey();
  const evilAmount = le64(10_000n);
  evilAmount[7] |= 0x80; // sign-magnitude negative
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger, amount: 10_000n, commitmentHex: binToHex(Uint8Array.from([...pledger.pkh, ...evilAmount])) });
  assert.throws(() => builder.debug(), /sign bit/);
});

test('refund rejects a payment output below dust', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(60_000n);
  // 400 sats is rejected by the builder's dust check before the covenant even runs;
  // the covenant's own >= 546 floor is belt-and-braces behind it.
  assert.throws(() => refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, payout: 400n }), /minimum|below dust/);
});

test('refund rejects a mutable NFT in the receipt slot', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, receiptCapability: 'mutable' });
  assert.throws(() => builder.debug(), /immutable NFT/);
});

test('refund rejects a minting NFT in the receipt slot', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(60_000n);
  const { builder } = refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, receiptCapability: 'minting' });
  assert.throws(() => builder.debug(), /immutable NFT/);
});

test('last refund: exact remainder below dust folds receipt dust into the pot and succeeds', async () => {
  const { provider, contract, seedPot } = setup();
  const pledger = makeKey();
  const pot = seedPot(10_400n); // 10_400 - 10_000 = 400 < 678 token dust floor
  const continuation = POT_DUST; // fold 278 of the receipt's 800 dust sats into the pot
  const payout = 10_400n + RECEIPT_DUST - continuation - FEE;
  const { builder } = refundTx({ provider, contract, pot, pledger, amount: 10_000n, continuation, payout });
  builder.debug();
  await builder.send();

  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots.length, 1);
  assert.equal(pots[0].satoshis, POT_DUST);
});

test('a refund cannot leave the pot below the token dust floor', () => {
  const { provider, contract, seedPot } = setup();
  const pot = seedPot(10_400n);
  assert.throws(() => refundTx({ provider, contract, pot, pledger: makeKey(), amount: 10_000n, continuation: 400n }), /minimum/); // builder dust validation
});

test('pledge crossing the goal succeeds; refund against a met goal stays rejected', async () => {
  const { provider, contract, seedPot } = setup();
  const pledger = makeKey();
  const pot = seedPot(95_000n);
  const pledge = pledgeTx({ provider, contract, pot, pledger, amount: 10_000n }); // crosses to 105_000
  pledge.debug();
  await pledge.send();

  const newPot = (await provider.getUtxos(contract.tokenAddress))[0];
  assert.equal(newPot.satoshis, 105_000n);

  const { builder } = refundTx({ provider, contract, pot: newPot, pledger, amount: 10_000n });
  assert.throws(() => builder.debug(), /goal was met/);
});

test('a receipt cannot be refunded twice', async () => {
  const { provider, contract, seedPot } = setup();
  const pledger = makeKey();
  const pot = seedPot(60_000n);

  const first = refundTx({ provider, contract, pot, pledger, amount: 10_000n });
  await first.builder.send();
  const receipt = first.receipt;

  // receipt UTXO is consumed by the first refund
  const remaining = await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(pledger.pkh)));
  assert.equal(remaining.filter((u) => u.token).length, 0);

  // spending the same receipt against the new pot must fail
  const newPot = (await provider.getUtxos(contract.tokenAddress))[0];
  const second = new TransactionBuilder({ provider })
    .addInput(newPot, contract.unlock.refund())
    .addInput(receipt, pledger.sig.unlockP2PKH())
    .addOutput({ to: contract.tokenAddress, amount: newPot.satoshis - 10_000n, token: mintingNft() })
    .addOutput({ to: p2pkhLock(pledger.pkh), amount: 10_000n + RECEIPT_DUST - FEE })
    .setLocktime(DEADLINE);
  await assert.rejects(() => second.send(), /UTXO not found/);
});
