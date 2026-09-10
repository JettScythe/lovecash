import { decodeKeyExchangeURI, initiateDappRelay } from "@wizardconnect/core";

const sample = "wiz://?p=lmglval84aa9mjx7cz7l5nsh2tvn5zel8ks8g395ujmu04ct6t4s&s=q7p6tw94xt6xw";
try {
  const d = decodeKeyExchangeURI(sample);
  console.log("URI parses OK:", { hostname: d.hostname, port: d.port, protocol: d.protocol });
} catch (e) {
  console.log("URI parse FAILED:", e.message);
}

console.log("connecting to relay (10s)...");
const relay = initiateDappRelay((payload) => {
  console.log("status:", JSON.stringify(payload.status && payload.status.status ? payload.status.status : payload.status));
});
setTimeout(() => { console.log("done waiting"); process.exit(0); }, 10000);
