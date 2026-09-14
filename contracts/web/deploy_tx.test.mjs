// Mock-network proof for the performer-side genesis builder: the tx the
// dashboard builds (via a placeholder unlocker for WizardConnect) is
// VM-valid when a real key signs it, lands the minting NFT directly in
// the covenant, and the category is the input-0 parent's txid — the
// single-tx genesis+seed the server-side verifier expects.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Contract, MockNetworkProvider, SignatureTemplate } from 'cashscript';
import { generatePrivateKey, secp256k1, hash160, binToHex, hexToBin, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildDeployTx, POT_SEED } from './deploy_tx.mjs';
import artifact from '../goal_show.json' with { type: 'json' };

const GOAL_SATS = 100_000n;
const DEADLINE = 800_000;

const p2pkhLock = (pkh) => Uint8Array.from([0x76, 0xa9, 0x14, ...pkh, 0x88, 0xac]);
const mockAddr = (pkh, tokens = false) => {
  const r = encodeCashAddress({ prefix: 'bchtest', type: tokens ? CashAddressType.p2pkhWithTokens : CashAddressType.p2pkh, payload: pkh });
  return typeof r === 'string' ? r : r.address;
};

let n = 0;
const nextTxid = () => (++n).toString(16).padStart(64, '0');

function makeKey() {
  const priv = generatePrivateKey();
  const pub = secp256k1.derivePublicKeyCompressed(priv);
  return { priv, pub, pkh: hash160(pub), sig: new SignatureTemplate(priv) };
}

// cashscript Utxo -> API wire shape (what /api/utxos returns)
const apiShape = (u) => ({
  tx_hash: u.txid,
  tx_pos: u.vout,
  value: Number(u.satoshis),
  token: u.token ? { category: u.token.category, amount: Number(u.token.amount), nft: u.token.nft } : null,
});

function setup() {
  const provider = new MockNetworkProvider();
  const performer = makeKey();
  const parent = provider.addUtxo(binToHex(p2pkhLock(performer.pkh)), { txid: nextTxid(), vout: 0, satoshis: 20_000n });
  return { provider, performer, parent };
}

test('deploy builder: genesis+seed lands the minting NFT in the covenant', async () => {
  const { provider, performer, parent } = setup();
  const { builder, category, potTokenAddress, changeSats, feeSats } = await buildDeployTx({
    artifact,
    goalSats: GOAL_SATS,
    deadline: DEADLINE,
    funderUtxos: [apiShape(parent)],
    funderAddress: mockAddr(performer.pkh),
    provider,
    funderUnlocker: performer.sig.unlockP2PKH(),
  });

  assert.equal(category, parent.txid); // category = input-0 parent's txid
  assert.ok(feeSats < 1000n, `real fee ${feeSats} should be well under the old hardcoded 1000`);
  assert.equal(changeSats, 20_000n - POT_SEED - feeSats);
  await builder.send();

  // The pot exists at the INDEPENDENTLY derived covenant address.
  const contract = new Contract(
    artifact,
    [performer.pkh, GOAL_SATS, BigInt(DEADLINE), hexToBin(parent.txid).reverse()],
    { provider },
  );
  assert.equal(potTokenAddress, contract.tokenAddress);
  const pots = await provider.getUtxos(contract.tokenAddress);
  assert.equal(pots.length, 1);
  assert.equal(pots[0].satoshis, POT_SEED);
  assert.equal(pots[0].token.nft.capability, 'minting');
  assert.equal(pots[0].token.nft.commitment, '');
  assert.equal(pots[0].token.category, parent.txid);
});

test('deploy builder: placeholder path produces a relay-safe WizardConnect request', async () => {
  const { provider, performer, parent } = setup();
  const { request } = await buildDeployTx({
    artifact,
    goalSats: GOAL_SATS,
    deadline: DEADLINE,
    funderUtxos: [apiShape(parent)],
    funderAddress: mockAddr(performer.pkh),
    provider, // placeholder unlocker: no send, object shape only
  });
  const { transaction, inputPaths } = request;
  assert.match(transaction.transaction, /^[0-9a-f]+$/);
  assert.equal(transaction.broadcast, false); // the RELAY broadcasts (deploy flow)
  assert.deepEqual(inputPaths, [[0, 'receive', 0]]); // parent MUST be input 0
  assert.equal(transaction.sourceOutputs.length, 1);
  assert.equal(transaction.sourceOutputs[0].unlockingBytecode, ''); // wallet fills this
  assert.doesNotThrow(() => JSON.stringify(request)); // bare relay stringify
});

test('deploy builder: rejects a goal below the server minimum', async () => {
  const { provider, performer, parent } = setup();
  await assert.rejects(() => buildDeployTx({
    artifact, goalSats: 50_000n, deadline: DEADLINE,
    funderUtxos: [apiShape(parent)], funderAddress: mockAddr(performer.pkh), provider,
  }), /goal below the minimum/);
});

test('deploy builder: rejects when no tokenless UTXO covers seed+fee+dust', async () => {
  const { provider, performer } = setup();
  const dusty = provider.addUtxo(binToHex(p2pkhLock(performer.pkh)), { txid: nextTxid(), vout: 0, satoshis: 2_000n });
  await assert.rejects(() => buildDeployTx({
    artifact, goalSats: GOAL_SATS, deadline: DEADLINE,
    funderUtxos: [apiShape(dusty)], funderAddress: mockAddr(performer.pkh), provider,
  }), /output index 0/);

  const tokenUtxo = provider.addUtxo(binToHex(p2pkhLock(performer.pkh)), {
    txid: nextTxid(), vout: 0, satoshis: 20_000n,
    token: { category: 'ff'.repeat(32), amount: 1n },
  });
  await assert.rejects(() => buildDeployTx({
    artifact, goalSats: GOAL_SATS, deadline: DEADLINE,
    funderUtxos: [apiShape(tokenUtxo)], funderAddress: mockAddr(performer.pkh), provider,
  }), /output index 0/);
});

test('deploy builder: rejects a parent not at output index 0 (genesis rule)', async () => {
  const { provider, performer } = setup();
  // Ample sats but at vout 2 — CHIP-2022-02: only outpoint index 0 can
  // create a token category (bad-txns-token-invalid-category otherwise).
  const vout2 = provider.addUtxo(binToHex(p2pkhLock(performer.pkh)), { txid: nextTxid(), vout: 2, satoshis: 20_000n });
  await assert.rejects(() => buildDeployTx({
    artifact, goalSats: GOAL_SATS, deadline: DEADLINE,
    funderUtxos: [apiShape(vout2)], funderAddress: mockAddr(performer.pkh), provider,
  }), /output index 0/);
});

test('deploy builder: token-aware performer address works (z... form)', async () => {
  const { provider, performer, parent } = setup();
  const { builder, potTokenAddress } = await buildDeployTx({
    artifact,
    goalSats: GOAL_SATS,
    deadline: DEADLINE,
    funderUtxos: [apiShape(parent)],
    funderAddress: mockAddr(performer.pkh, true), // token-aware form
    provider,
    funderUnlocker: performer.sig.unlockP2PKH(),
  });
  await builder.send();
  const contract = new Contract(
    artifact,
    [performer.pkh, GOAL_SATS, BigInt(DEADLINE), hexToBin(parent.txid).reverse()],
    { provider },
  );
  assert.equal(potTokenAddress, contract.tokenAddress);
});
