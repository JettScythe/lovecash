// Mock-network proof for the web refund builder: pot shrinks exactly by the
// receipt amount, the viewer nets amount - 200 (800-sat receipt dust folded
// into the payout, 1000-sat fee), and the receipt NFT is burned.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Contract, MockNetworkProvider, SignatureTemplate } from 'cashscript';
import { generatePrivateKey, secp256k1, hash160, binToHex, hexToBin, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildRefundTx, parseReceiptCommitment } from './refund_tx.mjs';
import artifact from '../goal_show.json' with { type: 'json' };

const GOAL_SATS = 100_000n;
const DEADLINE = 800_000;
const CATEGORY = '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f';

const p2pkhLock = (pkh) => Uint8Array.from([0x76, 0xa9, 0x14, ...pkh, 0x88, 0xac]);
const mockAddr = (pkh) => {
  const r = encodeCashAddress({ prefix: 'bchtest', type: CashAddressType.p2pkh, payload: pkh });
  return typeof r === 'string' ? r : r.address;
};
const le64 = (n) => { const b = new Uint8Array(8); let v = BigInt(n); for (let i = 0; i < 8; i++) { b[i] = Number(v & 0xffn); v >>= 8n; } return b; };
const commitmentOf = (pkh, amount) => binToHex(Uint8Array.from([...pkh, ...le64(amount)]));

let n = 0;
const nextTxid = () => (++n).toString(16).padStart(64, '0');

function makeKey() {
  const priv = generatePrivateKey();
  const pub = secp256k1.derivePublicKeyCompressed(priv);
  return { priv, pub, pkh: hash160(pub), sig: new SignatureTemplate(priv) };
}

const mintingNft = { category: CATEGORY, amount: 0n, nft: { capability: 'minting', commitment: '' } };
const apiShape = (u) => ({
  tx_hash: u.txid,
  tx_pos: u.vout,
  value: Number(u.satoshis),
  token: u.token ? { category: u.token.category, amount: Number(u.token.amount), nft: u.token.nft } : null,
});

function setup(potValue = 60_000n) {
  const provider = new MockNetworkProvider();
  const performer = makeKey();
  const contract = new Contract(artifact, [performer.pkh, GOAL_SATS, BigInt(DEADLINE), hexToBin(CATEGORY).reverse()], { provider });
  const pot = provider.addUtxo(contract.tokenAddress, { txid: nextTxid(), vout: 0, satoshis: potValue, token: mintingNft });
  const viewer = makeKey();
  const params = { performerPkh: binToHex(performer.pkh), goalSats: GOAL_SATS, deadline: DEADLINE, categoryDisplayHex: CATEGORY };
  const addReceipt = (amount, pkh = viewer.pkh, capability = 'none', category = CATEGORY) =>
    provider.addUtxo(binToHex(p2pkhLock(viewer.pkh)), {
      txid: nextTxid(), vout: 0, satoshis: 800n,
      token: { category, amount: 0n, nft: { capability, commitment: commitmentOf(pkh, amount) } },
    });
  return { provider, contract, pot, viewer, params, addReceipt };
}

test('parseReceiptCommitment decodes pkh ++ le64', () => {
  const k = makeKey();
  const { pkhHex, amount } = parseReceiptCommitment(commitmentOf(k.pkh, 12_345n));
  assert.equal(pkhHex, binToHex(k.pkh));
  assert.equal(amount, 12_345n);
  assert.throws(() => parseReceiptCommitment('aabb'), /28 bytes/);
});

test('refund: pot shrinks exactly by amount, viewer nets amount - 200, receipt burned', async () => {
  const { provider, contract, pot, viewer, params, addReceipt } = setup(60_000n);
  const receipt = addReceipt(10_000n);
  const { builder, payoutSats, request } = await buildRefundTx({
    artifact,
    contractParams: params,
    potUtxo: apiShape(pot),
    receiptUtxo: apiShape(receipt),
    funderAddress: mockAddr(viewer.pkh),
    deadline: DEADLINE,
    provider,
    funderUnlocker: viewer.sig.unlockP2PKH(),
    refundArgs: { sig: viewer.sig, pubkey: viewer.pub },
  });

  assert.equal(payoutSats, 10_000n + 800n - 1000n); // viewer nets amount - 200
  assert.deepEqual(request.inputPaths, [[0, 'receive', 0], [1, 'receive', 0]]);
  // conservation: (pot + dust) = (pot - amount) + payout + fee, fee == 1000
  builder.debug(); // full VM evaluation
  await builder.send();

  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots.length, 1);
  assert.equal(pots[0].satoshis, 50_000n); // exactly pot - amount
  assert.equal(pots[0].token.nft.capability, 'minting');

  const viewerUtxos = await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(viewer.pkh)));
  assert.equal(viewerUtxos.length, 1);
  assert.equal(viewerUtxos[0].satoshis, 9_800n);
  assert.equal(viewerUtxos[0].token, undefined); // receipt burned
});

test('refund near-dust edge: 600-sat receipt pays out exactly 546 (fee shrinks to fit)', async () => {
  const { provider, contract, pot, viewer, params, addReceipt } = setup(60_000n);
  const receipt = addReceipt(600n);
  const { builder, payoutSats, feeSats } = await buildRefundTx({
    artifact,
    contractParams: params,
    potUtxo: apiShape(pot),
    receiptUtxo: apiShape(receipt),
    funderAddress: mockAddr(viewer.pkh),
    deadline: DEADLINE,
    provider,
    funderUnlocker: viewer.sig.unlockP2PKH(),
    refundArgs: { sig: viewer.sig, pubkey: viewer.pub },
  });
  assert.equal(payoutSats, 546n);
  assert.equal(feeSats, 854n); // 600 + 800 - 546
  builder.debug();
  await builder.send();
  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots[0].satoshis, 60_000n - 600n);
});

test('refund of a 546-sat receipt cannot cover its own fee (documented floor)', async () => {
  const { provider, pot, viewer, params, addReceipt } = setup(60_000n);
  // Fee headroom = amount + dust - 546 = 800 sats < ~825 sats the ~825-byte
  // tx needs at 1 sat/byte. The covenant pins inputs.length == 2, so no
  // top-up input can rescue it: 546..~570-sat receipts are fee-stuck.
  await assert.rejects(() => buildRefundTx({
    artifact, contractParams: params, potUtxo: apiShape(pot), receiptUtxo: apiShape(addReceipt(546n)),
    funderAddress: mockAddr(viewer.pkh), deadline: DEADLINE, provider,
    funderUnlocker: viewer.sig.unlockP2PKH(), refundArgs: { sig: viewer.sig, pubkey: viewer.pub },
  }), /fee per byte/);
});

test('refund builder rejects foreign receipts and sign-bit encodings before building', async () => {
  const { provider, pot, viewer, params, addReceipt } = setup(60_000n);
  const other = makeKey();
  await assert.rejects(() => buildRefundTx({
    artifact, contractParams: params, potUtxo: apiShape(pot), receiptUtxo: apiShape(addReceipt(10_000n, other.pkh)),
    funderAddress: mockAddr(viewer.pkh), deadline: DEADLINE, provider,
  }), /different address/);

  await assert.rejects(() => buildRefundTx({
    artifact, contractParams: params, potUtxo: apiShape(pot),
    receiptUtxo: apiShape(addReceipt(10_000n, viewer.pkh, 'mutable')),
    funderAddress: mockAddr(viewer.pkh), deadline: DEADLINE, provider,
  }), /not an immutable NFT/);
});

test('refund placeholder path: relay-safe request, both inputs flagged for signing', async () => {
  const { provider, pot, viewer, params, addReceipt } = setup(60_000n);
  const { request } = await buildRefundTx({
    artifact,
    contractParams: params,
    potUtxo: apiShape(pot),
    receiptUtxo: apiShape(addReceipt(10_000n)),
    funderAddress: mockAddr(viewer.pkh),
    deadline: DEADLINE,
    provider,
  });
  assert.doesNotThrow(() => JSON.stringify(request));
  assert.equal(typeof request.transaction.transaction, 'string');
  const [potSo, receiptSo] = request.transaction.sourceOutputs;
  // covenant input carries placeholder sig+pubkey pushes (non-empty)...
  assert.notEqual(potSo.unlockingBytecode, '');
  assert.ok(potSo.unlockingBytecode.includes('00'.repeat(65))); // placeholderSignature
  assert.ok(potSo.unlockingBytecode.includes('00'.repeat(33))); // placeholderPublicKey
  // ...receipt input stays empty for the wallet to fill
  assert.equal(receiptSo.unlockingBytecode, '');
  assert.equal(receiptSo.token.nft.commitment.length / 2, 28);
});
