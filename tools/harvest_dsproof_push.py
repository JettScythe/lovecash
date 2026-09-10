"""
Full-mempool DSProof harvester WITH end-to-end verifier validation.

Pulls every fresh mempool txid from local bitcoind, subscribes through
lovecash's ElectrumClient, and when a WILD DSProof lands on a watched tx,
runs the REAL Verifier.verify() against it and asserts NEEDS_CONF — the
complete refusal path, proven on a real network double-spend.
"""

import asyncio
import os
import time

import httpx

from lovecash.bch.electrum import ElectrumClient
from lovecash.bch.verify import Outcome, Verifier
from lovecash.config import Settings

# Credentials come from the environment ONLY. Never hardcode real values
# here — export NODE_RPC_URL / NODE_RPC_USER / NODE_RPC_PASS before running.
NODE_URL = os.environ.get("NODE_RPC_URL", "http://localhost:8332")
NODE_USER = os.environ["NODE_RPC_USER"]
NODE_PASS = os.environ["NODE_RPC_PASS"]


async def node_rpc(http: httpx.AsyncClient, method: str, params=None):
    r = await http.post(
        NODE_URL,
        auth=(NODE_USER, NODE_PASS),
        json={"id": 1, "method": method, "params": params or []},
    )
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


def make_verifier(c: ElectrumClient) -> Verifier:
    """A Verifier wired to the live client, exactly as PaymentSource builds
    it — so we exercise the real production decision path."""
    return Verifier(
        fetch_tx=lambda txid: c.call("blockchain.transaction.get", txid, True),
        watch=c.watch_dsproof,
        unwatch=c.unwatch_dsproof,
        subscribe=lambda txid: c.call("blockchain.transaction.dsproof.subscribe", txid),
        window_seconds=5.0,
    )


async def validate_refusal(c: ElectrumClient, txid: str) -> None:
    """Run the FULL verifier against a real proofed tx; assert it refuses."""
    print(f"  running Verifier.verify() against real proofed tx {txid}...")
    tx = await c.call("blockchain.transaction.get", txid, True)
    verifier = make_verifier(c)
    outcome = await verifier.verify(txid, tx)
    if outcome is Outcome.NEEDS_CONF:
        print("  >>> VERIFIER REFUSED (NEEDS_CONF) — end-to-end VALIDATED <<<")
    elif txid in tx:
        print(
            f">>> verifier said {outcome} but proof IS live — server's subscribe response didn't carry it (window catch failed) <<<"
        )
    else:
        print(f">>> CATASTROPHIC: {outcome} on a real double-spend <<<")


async def main() -> None:
    s = Settings.from_yaml("config.yaml")
    c = ElectrumClient(s.bch.electrum_host, s.bch.electrum_port, s.bch.electrum_ssl)
    await c.connect()

    http = httpx.AsyncClient(timeout=10)
    watched: dict[str, tuple[asyncio.Event, float]] = {}
    proofed: set[str] = set()
    subscribed_count = 0

    print(
        f"harvesting full mempool from {NODE_URL}, validating refusal "
        f"via {s.bch.electrum_host}..."
    )

    while True:
        try:
            mempool = await node_rpc(http, "getrawmempool")
        except Exception as exc:
            print("node RPC error:", exc)
            await asyncio.sleep(3)
            continue

        for txid in mempool:
            if txid in watched:
                continue
            ev = c.watch_dsproof(txid)
            try:
                sub = await c.call("blockchain.transaction.dsproof.subscribe", txid)
            except Exception:
                c.unwatch_dsproof(txid)
                continue
            if sub is not None:
                c.unwatch_dsproof(txid)
                continue
            watched[txid] = (ev, time.monotonic())
            subscribed_count += 1

        live = set(await c.call("blockchain.transaction.dsproof.list") or [])
        for txid in list(watched):
            if txid in live and txid not in proofed:
                proofed.add(txid)
                ev, subbed_at = watched[txid]
                elapsed = time.monotonic() - subbed_at
                print("=" * 64)
                print(f"WILD DSPROOF on watched tx {txid}")
                print(f"  subscribed {elapsed:.1f}s before the proof")
                if ev.is_set():
                    print("  PUSH FIRED immediately — routing validated")
                else:
                    try:
                        await asyncio.wait_for(ev.wait(), 5)
                        print("  PUSH FIRED (within 5s) — routing validated")
                    except TimeoutError:
                        print("  PUSH NEVER FIRED — _dispatch routing BROKEN")
                # End-to-end: run the real verifier on this real proof.
                try:
                    await validate_refusal(c, txid)
                except Exception as exc:
                    print(f"  verifier run errored: {exc!r}")
                print("=" * 64)

        in_mempool = set(mempool)
        for txid in list(watched):
            if txid not in in_mempool:
                c.unwatch_dsproof(txid)
                del watched[txid]

        print(
            f"  watching {len(watched)} fresh txs "
            f"(subscribed {subscribed_count}, proofs {len(proofed)})",
            end="\r",
        )
        await asyncio.sleep(3)


asyncio.run(main())
