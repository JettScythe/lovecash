#!/usr/bin/env node
// Chipnet proof for the WEB deploy builder (contracts/web/deploy_tx.mjs):
// build a one-tx genesis+seed with a real key, broadcast it, and print the
// JSON the relay's POST /api/goal_show expects. This is the scripted half
// of the dashboard-deploy gate; the Cashonize pairing half is manual.
import { readFileSync } from 'node:fs';
import { ElectrumNetworkProvider, SignatureTemplate } from 'cashscript';
import { decodePrivateKeyWif, secp256k1, hash160, binToHex, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildDeployTx } from './web/deploy_tx.mjs';
import artifact from './goal_show.json' with { type: 'json' };

const wif = readFileSync(new URL('./.chipnet-wif', import.meta.url), 'utf8').trim();
const decoded = decodePrivateKeyWif(wif);
if (typeof decoded === 'string') throw new Error(decoded);
const priv = decoded.privateKey;
const pub = secp256k1.derivePublicKeyCompressed(priv);
if (typeof pub === 'string') throw new Error(pub);
const pkh = hash160(pub);
const sig = new SignatureTemplate(priv);
const addr = encodeCashAddress({ prefix: 'bchtest', type: CashAddressType.p2pkh, payload: pkh }).address;

const goalSats = Number(process.env.GOAL_SATS ?? 100_000);
const provider = new ElectrumNetworkProvider('chipnet', { hostname: 'chipnet.imaginary.cash' });
const height = await provider.getBlockHeight();
const deadline = height + 1000;

const utxos = (await provider.getUtxos(addr)).map((u) => ({
  tx_hash: u.txid, tx_pos: u.vout, value: Number(u.satoshis),
  token: u.token ? { category: u.token.category, amount: Number(u.token.amount), nft: u.token.nft } : null,
}));

const { builder, category, potTokenAddress, seedSats, feeSats } = await buildDeployTx({
  artifact, goalSats, deadline,
  funderUtxos: utxos, funderAddress: addr,
  provider, funderUnlocker: sig.unlockP2PKH(),
});
const { txid } = await builder.send();
console.log(JSON.stringify({
  genesis_txid: txid, goal_sats: goalSats, deadline,
  performer_pkh: binToHex(pkh), address: potTokenAddress,
  category, seedSats: Number(seedSats), feeSats: Number(feeSats), height,
}, null, 2));
