#!/usr/bin/env node
// Chipnet proof: pledge over the goal so the relay's auto-claim fires.
// Uses the web pledge builder (buildPledgeTx) against the LIVE pot from
// the running relay, signed by the throwaway chipnet key.
import { readFileSync } from 'node:fs';
import { ElectrumNetworkProvider, SignatureTemplate } from 'cashscript';
import { decodePrivateKeyWif, secp256k1, hash160, encodeCashAddress, CashAddressType } from '@bitauth/libauth';
import { buildPledgeTx } from './web/pledge_tx.mjs';
import artifact from './goal_show.json' with { type: 'json' };

const RELAY = process.env.RELAY ?? 'http://host.docker.internal:8080'; // docker: host loopback
const AMOUNT = BigInt(process.env.PLEDGE_SATS ?? 96_000);

const wif = readFileSync(new URL('./.chipnet-wif', import.meta.url), 'utf8').trim();
const decoded = decodePrivateKeyWif(wif);
if (typeof decoded === 'string') throw new Error(decoded);
const priv = decoded.privateKey;
const pub = secp256k1.derivePublicKeyCompressed(priv);
if (typeof pub === 'string') throw new Error(pub);
const pkh = hash160(pub);
const sig = new SignatureTemplate(priv);
const addr = encodeCashAddress({ prefix: 'bchtest', type: CashAddressType.p2pkh, payload: pkh }).address;

const potInfo = await (await fetch(`${RELAY}/api/goal_pot`)).json();
if (!potInfo.configured || !potInfo.utxo) throw new Error('relay has no live pot — deploy first');
console.log('pot:', potInfo.balance_sats, '/', potInfo.goal_sats, 'sats; pledging', AMOUNT.toString());

const provider = new ElectrumNetworkProvider('chipnet', { hostname: 'chipnet.imaginary.cash' });
const utxos = (await provider.getUtxos(addr)).map((u) => ({
  tx_hash: u.txid, tx_pos: u.vout, value: Number(u.satoshis),
  token: u.token ? { category: u.token.category, amount: Number(u.token.amount), nft: u.token.nft } : null,
}));

const { builder } = await buildPledgeTx({
  artifact,
  contractParams: {
    performerPkh: potInfo.performer_pkh,
    goalSats: potInfo.goal_sats,
    deadline: potInfo.deadline,
    categoryDisplayHex: potInfo.utxo.token.category,
  },
  potUtxo: potInfo.utxo,
  funderUtxos: utxos,
  funderAddress: addr,
  amountSats: AMOUNT,
  provider,
  funderUnlocker: sig.unlockP2PKH(),
});
const { txid } = await builder.send();
console.log('pledge broadcast:', txid);
