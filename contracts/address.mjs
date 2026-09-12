// Print the covenant addresses for a GoalShow parameter set.
// Usage: node address.mjs '<json>' where json =
//   {"performerPkh": "<40 hex>", "goalSats": 100000, "deadline": 900000,
//    "category": "<64 hex, RAW byte order = reversed explorer display hex>"}
// No network needed: address derivation is pure local crypto.
import { Contract, MockNetworkProvider } from "cashscript";
import artifact from "./goal_show.json" with { type: "json" };

const p = JSON.parse(process.argv[2]);
const provider = new MockNetworkProvider();
const contract = new Contract(
  artifact,
  [p.performerPkh, BigInt(p.goalSats), BigInt(p.deadline), p.category],
  { provider },
);
console.log(JSON.stringify({
  address: contract.address,
  tokenAddress: contract.tokenAddress,
}, null, 2));
