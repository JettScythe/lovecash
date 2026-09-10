"""Watch for a real DSProof on mainnet to validate notification format.
Run this for a while; mainnet produces dsproofs regularly."""

import asyncio
import json

from lovecash.bch.electrum import ElectrumClient
from lovecash.config import Settings


async def main() -> None:
    s = Settings.from_yaml("config.yaml")
    srv = s.bch.servers[0]
    c = ElectrumClient(srv.host, srv.port, srv.ssl, tls_verify=srv.tls_verify)
    await c.connect()
    print("polling dsproof.list for a real double-spend proof...")
    while True:
        live = await c.call("blockchain.transaction.dsproof.list")
        if live:
            txid = live[0]
            print(f"FOUND live dsproof on txid: {txid}")
            proof = await c.call("blockchain.transaction.dsproof.get", txid)
            print("get() shape:", json.dumps(proof, indent=2)[:600])
            # Now subscribe and watch the notification format.
            ev = c.watch_dsproof(txid)
            sub = await c.call("blockchain.transaction.dsproof.subscribe", txid)
            print("subscribe() returned:", repr(sub))
            print("watching for notification (it may already be set)...")
            try:
                await asyncio.wait_for(ev.wait(), timeout=30)
                print("EVENT FIRED — routing works against real notification")
            except TimeoutError:
                print("no push within 30s (proof may predate subscribe)")
            await c.close()
            return
        await asyncio.sleep(5)


asyncio.run(main())
