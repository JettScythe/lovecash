import asyncio
import json
import logging
import ssl
from collections.abc import AsyncIterator

log = logging.getLogger("lovecash.electrum")


class ElectrumClient:
    """Tiny async JSON-RPC client for the Electrum/Fulcrum protocol."""

    def __init__(self, host: str, port: int, use_ssl: bool = True) -> None:
        self._host = host
        self._port = port
        self._ssl = use_ssl
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._notifications: asyncio.Queue = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None

    async def connect(self) -> None:
        ctx = None
        if self._ssl:
            ctx = ssl.create_default_context()
            # Many community Fulcrum servers use self-signed certs.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port, ssl=ctx
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        log.info("Connected to Electrum %s:%s", self._host, self._port)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while not self._reader.at_eof():
            line = await self._reader.readline()
            if not line:
                break
            msg = json.loads(line.decode())
            if "id" in msg and msg["id"] in self._pending:
                fut = self._pending.pop(msg["id"])
                if "error" in msg and msg["error"]:
                    fut.set_exception(RuntimeError(str(msg["error"])))
                else:
                    fut.set_result(msg.get("result"))
            elif msg.get("method", "").endswith("subscribe"):
                await self._notifications.put(msg)

    async def call(self, method: str, *params) -> object:
        assert self._writer is not None
        self._id += 1
        req_id = self._id
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        payload = json.dumps({"id": req_id, "method": method, "params": list(params)})
        self._writer.write(payload.encode() + b"\n")
        await self._writer.drain()
        return await asyncio.wait_for(fut, timeout=30)

    async def subscribe_scripthash(self, scripthash: str) -> object:
        return await self.call("blockchain.scripthash.subscribe", scripthash)

    async def notifications(self) -> AsyncIterator[dict]:
        while True:
            yield await self._notifications.get()

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._writer:
            self._writer.close()
