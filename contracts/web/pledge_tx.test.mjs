// Mock-network proof for the web pledge builder: the tx the browser builds
// (via placeholder unlockers for WalletConnect) is VM-valid when a real key
// signs it — the same shape that ran on chipnet in round 2/3.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Contract, MockNetworkProvider, SignatureTemplate } from 'cashscript';
import { generatePrivateKey, secp256k1, hash160, binToHex, hexToBin, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildPledgeTx, toTokenAddress } from './pledge_tx.mjs';
import artifact from '../goal_show.json' with { type: 'json' };

const GOAL_SATS = 100_000n;
const DEADLINE = 800_000;
const CATEGORY = '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f'; // display hex

const p2pkhLock = (pkh) => Uint8Array.from([0x76, 0xa9, 0x14, ...pkh, 0x88, 0xac]);
const mockAddr = (pkh, tokens = false) => {
  const r = encodeCashAddress({ prefix: 'bchtest', type: tokens ? CashAddressType.p2pkhWithTokens : CashAddressType.p2pkh, payload: pkh });
  return typeof r === 'string' ? r : r.address;
};
const le64 = (n) => { const b = Buffer.alloc(8); b.writeBigUInt64LE(n); return new Uint8Array(b); };

let n = 0;
const nextTxid = () => (++n).toString(16).padStart(64, '0');

function makeKey() {
  const priv = generatePrivateKey();
  const pub = secp256k1.derivePublicKeyCompressed(priv);
  return { priv, pub, pkh: hash160(pub), sig: new SignatureTemplate(priv) };
}

const mintingNft = { category: CATEGORY, amount: 0n, nft: { capability: 'minting', commitment: '' } };

// cashscript Utxo -> API wire shape (what /api/goal_pot and /api/utxos return)
const apiShape = (u) => ({
  tx_hash: u.txid,
  tx_pos: u.vout,
  value: Number(u.satoshis),
  token: u.token ? { category: u.token.category, amount: Number(u.token.amount), nft: u.token.nft } : null,
});

function setup() {
  const provider = new MockNetworkProvider();
  const performer = makeKey();
  const contract = new Contract(artifact, [performer.pkh, GOAL_SATS, BigInt(DEADLINE), hexToBin(CATEGORY).reverse()], { provider });
  const pot = provider.addUtxo(contract.tokenAddress, { txid: nextTxid(), vout: 0, satoshis: 50_000n, token: mintingNft });
  const funder = makeKey();
  const funding = provider.addUtxo(binToHex(p2pkhLock(funder.pkh)), { txid: nextTxid(), vout: 0, satoshis: 20_000n });
  const params = { performerPkh: binToHex(performer.pkh), goalSats: GOAL_SATS, deadline: DEADLINE, categoryDisplayHex: CATEGORY };
  return { provider, performer, contract, pot, funder, funding, params };
}

test('web builder: pledge tx is VM-valid and lands pot + receipt correctly', async () => {
  const { provider, contract, pot, funder, funding, params } = setup();
  const { builder, changeSats, wcTransactionObject } = await buildPledgeTx({
    artifact,
    contractParams: params,
    potUtxo: apiShape(pot),
    funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh),
    amountSats: 10_000n,
    provider,
    funderUnlocker: funder.sig.unlockP2PKH(),
  });

  assert.equal(changeSats, 20_000n - 10_000n - 800n - 1000n);
  builder.debug(); // full VM evaluation — the whole point
  await builder.send();

  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots.length, 1);
  assert.equal(pots[0].satoshis, 60_000n);
  assert.equal(pots[0].token.nft.capability, 'minting');

  const receipts = await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(funder.pkh)));
  const receipt = receipts.find((u) => u.token);
  assert.equal(receipt.token.nft.capability, 'none');
  assert.equal(receipt.token.nft.commitment, binToHex(Uint8Array.from([...funder.pkh, ...le64(10_000n)])));
  assert.equal(receipt.satoshis, 800n);
});

test('web builder: placeholder path produces a well-formed WC object', async () => {
  const { provider, pot, funder, funding, params } = setup();
  const { wcTransactionObject } = await buildPledgeTx({
    artifact,
    contractParams: params,
    potUtxo: apiShape(pot),
    funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh),
    amountSats: 10_000n,
    provider, // placeholder unlocker: no debug/send, object shape only
  });
  assert.ok(wcTransactionObject.transaction);
  assert.ok(Array.isArray(wcTransactionObject.sourceOutputs));
  assert.equal(wcTransactionObject.transaction.inputs.length, 2);
  assert.equal(wcTransactionObject.transaction.outputs.length, 3);
  assert.equal(wcTransactionObject.broadcast, true);
});

test('web builder: rejects below-dust pledge', async () => {
  const { provider, pot, funder, funding, params } = setup();
  await assert.rejects(() => buildPledgeTx({
    artifact, contractParams: params, potUtxo: apiShape(pot), funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh), amountSats: 100n, provider,
  }), /below dust/);
});

test('web builder: rejects when no single UTXO covers the pledge', async () => {
  const { provider, pot, funder, funding, params } = setup();
  await assert.rejects(() => buildPledgeTx({
    artifact, contractParams: params, potUtxo: apiShape(pot), funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh), amountSats: 19_000n, provider,
  }), /no single UTXO/);
});

test('web builder: rejects a pot without the minting NFT or with wrong category', async () => {
  const { provider, contract, funder, funding, params } = setup();
  const barePot = provider.addUtxo(contract.tokenAddress, { txid: nextTxid(), vout: 0, satoshis: 50_000n });
  await assert.rejects(() => buildPledgeTx({
    artifact, contractParams: params, potUtxo: apiShape(barePot), funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh), amountSats: 10_000n, provider,
  }), /no minting NFT/);

  const wrongPot = provider.addUtxo(contract.tokenAddress, {
    txid: nextTxid(), vout: 0, satoshis: 50_000n,
    token: { category: 'ff'.repeat(32), amount: 0n, nft: { capability: 'minting', commitment: '' } },
  });
  await assert.rejects(() => buildPledgeTx({
    artifact, contractParams: params, potUtxo: apiShape(wrongPot), funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh), amountSats: 10_000n, provider,
  }), /category mismatch/);
});

test('web builder: token-aware funder address derives correct receipt target', async () => {
  const { provider, contract, pot, funder, funding, params } = setup();
  const { builder } = await buildPledgeTx({
    artifact,
    contractParams: params,
    potUtxo: apiShape(pot),
    funderUtxos: [apiShape(funding)],
    funderAddress: mockAddr(funder.pkh, true), // viewer gave a z... address
    amountSats: 10_000n,
    provider,
    funderUnlocker: funder.sig.unlockP2PKH(),
  });
  builder.debug();
  await builder.send();
  const receipts = (await provider.getUtxosForLockingBytecode(binToHex(p2pkhLock(funder.pkh)))).filter((u) => u.token);
  assert.equal(receipts.length, 1);
  assert.equal(toTokenAddress(mockAddr(funder.pkh)), mockAddr(funder.pkh, true));
});
