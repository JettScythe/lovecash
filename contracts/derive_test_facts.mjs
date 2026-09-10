import { decodePrivateKeyWif, secp256k1, hash160, encodeCashAddress, CashAddressNetworkPrefix, CashAddressType, hexToBin, binToHex } from "@bitauth/libauth";
import { readFileSync } from "fs";
import { Contract, MockNetworkProvider } from "cashscript";
import artifact from "./goal_show.json" with { type: "json" };

const wif = readFileSync(".chipnet-wif", "utf8").trim();
const decoded = decodePrivateKeyWif(wif);
if (typeof decoded === "string") throw new Error(decoded);
const priv = decoded.privateKey;
const pub = secp256k1.derivePublicKeyCompressed(priv);
if (typeof pub === "string") throw new Error(pub);
const pkh = hash160(pub);
console.log("performer_pkh:", binToHex(pkh));
console.log("addr:", encodeCashAddress({ prefix: CashAddressNetworkPrefix.testnet, type: CashAddressType.p2pkh, payload: pkh }).address);
console.log("token addr:", encodeCashAddress({ prefix: CashAddressNetworkPrefix.testnet, type: CashAddressType.p2pkhWithTokens, payload: pkh }).address);

// Instance B pot: goal 100000, deadline 1, category = A's seed txid (display)
const catDisplay = "db2dfbfdffbfb7cb6f50fbc7d4335157cd77291b78adc26ea2de37e9877082b8";
const catRaw = binToHex(hexToBin(catDisplay).reverse());
const c = new Contract(artifact, [binToHex(pkh), 100000n, 1n, catRaw], { provider: new MockNetworkProvider() });
console.log("pot B token address:", c.tokenAddress);
console.log("pot B address:", c.address);
