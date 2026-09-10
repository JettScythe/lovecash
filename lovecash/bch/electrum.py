import asyncio
import contextlib
import json
import logging
import ssl
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger("lovecash.electrum")


class ElectrumClient:
    """Tiny async JSON-RPC client for the Electrum/Fulcrum protocol."""

    def __init__(
        self,
        host: str,
        port: int,
        use_ssl: bool = True,
        heartbeat_s=30.0,
        tls_verify: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._ssl = use_ssl
        self._tls_verify = tls_verify
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._notifications: asyncio.Queue = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self.disconnected = asyncio.Event()
        self._heartbeat_s = heartbeat_s
        self._hb_task: asyncio.Task | None = None
        self._dsproof_events: dict[str, asyncio.Event] = {}

    def watch_dsproof(self, txid: str) -> asyncio.Event:
        """Register interest in dsproof notifications for a txid.
        Returns an Event that fires when a proof notification arrives."""
        event = asyncio.Event()
        self._dsproof_events[txid] = event
        return event

    def unwatch_dsproof(self, txid: str) -> None:
        self._dsproof_events.pop(txid, None)

    def _ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if not self._tls_verify:
            # Self-signed server the operator explicitly trusts. Without
            # verification, a network MITM could inject fake tips.
            log.warning("TLS certificate verification DISABLED for %s", self._host)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    async def connect(self) -> None:
        # Guard against starting a second reader on a stale connection.
        if self._reader_task and not self._reader_task.done():
            await self.close()
        ctx = self._ssl_context() if self._ssl else None
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port, ssl=ctx
        )
        self.disconnected.clear()
        self._closing = False
        self._reader_task = asyncio.create_task(self._read_loop())
        self._hb_task = asyncio.create_task(self._heartbeat())
        log.info(
            "Connected to Electrum %s:%s (ssl=%s)", self._host, self._port, self._ssl
        )

    def _dispatch(self, msg: dict) -> None:
        msg_id = msg.get("id")
        if msg_id is not None and msg_id in self._pending:
            fut = self._pending.pop(msg_id)
            if fut.done():
                return
            err = msg.get("error")
            if err:
                fut.set_exception(RuntimeError(str(err)))
            else:
                fut.set_result(msg.get("result"))
            return

        method = msg.get("method", "")
        if method.endswith("dsproof.subscribe"):
            params = msg.get("params", [])
            if params:
                txid = params[0]
                event = self._dsproof_events.get(txid)
                if event is not None:
                    event.set()
            return
        if method.endswith("subscribe"):
            self._notifications.put_nowait(msg)

    def _fail(self, reason: str) -> None:
        if self.disconnected.is_set():
            return
        if not self._closing:  # quiet on intentional close
            log.warning("Electrum connection lost: %s", reason)
        self.disconnected.set()
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError(reason))
        self._pending.clear()

    async def _read_loop(self) -> None:
        reason = "server closed connection"
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:  # EOF
                    break
                try:
                    msg = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue  # ignore garbage lines
                self._dispatch(msg)
        except asyncio.CancelledError:
            raise  # intentional close
        except (ConnectionError, OSError) as exc:
            reason = f"read error: {exc}"
        finally:
            self._fail(reason)

    async def _heartbeat(self) -> None:
        try:
            while not self.disconnected.is_set():
                await asyncio.sleep(self._heartbeat_s)
                try:
                    await self.call("server.ping", timeout=10)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._fail(f"heartbeat failed: {exc!r}")
                    return
        except asyncio.CancelledError:
            raise

    async def call(self, method: str, *params, timeout: float = 30) -> Any:  # noqa: ASYNC109
        if self.disconnected.is_set():
            raise ConnectionError("not connected")
        assert self._writer is not None
        self._id += 1
        req_id = self._id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        payload = json.dumps({"id": req_id, "method": method, "params": list(params)})
        self._writer.write(payload.encode() + b"\n")
        await self._writer.drain()
        return await asyncio.wait_for(fut, timeout=timeout)

    async def subscribe_scripthash(self, scripthash: str) -> object:
        return await self.call("blockchain.scripthash.subscribe", scripthash)

    async def next_notification(self) -> dict:
        """Return the next notification, or raise if the connection drops."""
        getter = asyncio.ensure_future(self._notifications.get())
        dropped = asyncio.ensure_future(self.disconnected.wait())
        try:
            done, _ = await asyncio.wait(
                {getter, dropped}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for t in (getter, dropped):
                if not t.done():
                    t.cancel()
        if getter in done:
            return getter.result()
        raise ConnectionError("connection dropped while waiting")

    async def notifications(self) -> AsyncIterator[dict]:
        while True:
            yield await self._notifications.get()

    def drain_notifications(self) -> None:
        while not self._notifications.empty():
            try:
                self._notifications.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def close(self) -> None:
        self._closing = True
        self._fail("closed")
        for task in (self._reader_task, self._hb_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task  # AWAIT — fixes the leak
        self._reader_task = None
        self._hb_task = None
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
