// Send chipnet sats from the throwaway key to a target address.
// node send_chipnet.mjs <bchtest:addr> <sats>
import { ElectrumNetworkProvider } from "cashscript";
import { TransactionBuilder } from "cashscript";
import { decodePrivateKeyWif, secp256k1, hash160, encodeCashAddress, CashAddressNetworkPrefix, CashAddressType } from "@bitauth/libauth";
import { readFileSync } from "fs";

const [to, satsStr] = process.argv.slice(2);
const sats = BigInt(satsStr);
const wif = readFileSync(".chipnet-wif", "utf8").trim();
const decoded = decodePrivateKeyWif(wif);
if (typeof decoded === "string") throw new Error(decoded);
const pub = secp256k1.derivePublicKeyCompressed(decoded.privateKey);
const pkh = hash160(pub);
const from = encodeCashAddress({ prefix: CashAddressNetworkPrefix.testnet, type: CashAddressType.p2pkh, payload: pkh }).address;

const provider = new ElectrumNetworkProvider("chipnet", { hostname: "chipnet.imaginary.cash" });
const utxos = (await provider.getUtxos(from)).filter(u => !u.token);
const total = utxos.reduce((a, u) => a + u.satoshis, 0n);
console.log("balance:", total.toString(), "sats across", utxos.length, "utxos");

const FEE = 3000n;
const builder = new TransactionBuilder({ provider });
const { SignatureTemplate } = await import("cashscript");
const sig = new SignatureTemplate(decoded.privateKey);
builder.addInputs(utxos, sig.unlockP2PKH());
builder.addOutput({ to: to, amount: sats });
const change = total - sats - FEE;
if (change > 546n) builder.addOutput({ to: from, amount: change });
const txid = await builder.send();
console.log("sent:", typeof txid === "string" ? txid : txid.txid);
console.log("https://chipnet.imaginary.cash/tx/" + (typeof txid === "string" ? txid : txid.txid));
