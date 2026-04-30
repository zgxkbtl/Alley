import asyncio
import base64
import hashlib
import os
import struct
from contextlib import suppress
from types import TracebackType
from urllib.parse import urlparse


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
XOR_TABLES = [
    bytes(byte ^ mask for byte in range(256))
    for mask in range(256)
]


class WebSocketError(Exception):
    pass


class ConnectionClosed(WebSocketError):
    pass


class WebSocketConnection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, mask_outgoing: bool):
        self.reader = reader
        self.writer = writer
        self.mask_outgoing = mask_outgoing
        self.remote_address = writer.get_extra_info("peername")
        self.local_address = writer.get_extra_info("sockname")
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except ConnectionClosed:
            raise StopAsyncIteration

    async def send(self, message: str):
        if self._closed:
            raise ConnectionClosed("websocket is closed")

        payload = message.encode("utf-8")
        header = bytearray([0x81])
        mask_bit = 0x80 if self.mask_outgoing else 0
        length = len(payload)
        if length < 126:
            header.append(mask_bit | length)
        elif length < 2**16:
            header.append(mask_bit | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(mask_bit | 127)
            header.extend(struct.pack("!Q", length))

        if self.mask_outgoing:
            mask = os.urandom(4)
            header.extend(mask)
            payload = _apply_mask(payload, mask)

        try:
            self.writer.write(header + payload)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as exc:
            self._closed = True
            raise ConnectionClosed("websocket stream ended") from exc

    async def recv(self) -> str:
        message = bytearray()
        while True:
            opcode, payload, final = await self._read_frame()
            if opcode == 0x8:
                await self.close(send_close=not self._closed)
                raise ConnectionClosed("websocket closed")
            if opcode == 0x9:
                await self._write_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode not in (0x0, 0x1):
                raise WebSocketError(f"unsupported websocket opcode: {opcode}")
            message.extend(payload)
            if final:
                return message.decode("utf-8")

    async def close(self, *, send_close: bool = True):
        if self._closed:
            return
        self._closed = True
        if send_close:
            with suppress(Exception):
                await self._write_frame(0x8, b"")
        self.writer.close()
        with suppress(Exception):
            await self.writer.wait_closed()

    async def _read_frame(self) -> tuple[int, bytes, bool]:
        try:
            first, second = await self.reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError) as exc:
            raise ConnectionClosed("websocket stream ended") from exc

        final = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", await self.reader.readexactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", await self.reader.readexactly(8))[0]

        try:
            mask = await self.reader.readexactly(4) if masked else None
            payload = await self.reader.readexactly(length) if length else b""
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError) as exc:
            raise ConnectionClosed("websocket stream ended") from exc
        if mask:
            payload = _apply_mask(payload, mask)
        return opcode, payload, final

    async def _write_frame(self, opcode: int, payload: bytes):
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length < 2**16:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))
        try:
            self.writer.write(header + payload)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as exc:
            self._closed = True
            raise ConnectionClosed("websocket stream ended") from exc


class WebSocketServer:
    def __init__(self, handler, host: str, port: int):
        self.handler = handler
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._accept, self.host, self.port)
        return self.server

    async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await _server_handshake(reader, writer)
            websocket = WebSocketConnection(reader, writer, mask_outgoing=False)
            await self.handler(websocket)
        except Exception:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


class WebSocketClient:
    def __init__(self, uri: str):
        self.uri = uri
        self.websocket: WebSocketConnection | None = None

    async def __aenter__(self):
        self.websocket = await _client_connect(self.uri)
        return self.websocket

    async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None):
        if self.websocket:
            await self.websocket.close()


def serve(handler, host: str, port: int, **_kwargs) -> WebSocketServer:
    return WebSocketServer(handler, host, port)


def connect(uri: str) -> WebSocketClient:
    return WebSocketClient(uri)


def _apply_mask(payload: bytes, mask: bytes) -> bytes:
    data = bytearray(payload)
    for index, mask_byte in enumerate(mask):
        data[index::4] = data[index::4].translate(XOR_TABLES[mask_byte])
    return bytes(data)


async def _server_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    headers = await _read_headers(reader)
    key = headers.get("sec-websocket-key")
    if not key:
        raise WebSocketError("missing Sec-WebSocket-Key")

    accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
    writer.write(
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
        .encode("ascii")
    )
    await writer.drain()


async def _client_connect(uri: str) -> WebSocketConnection:
    parsed = urlparse(uri)
    if parsed.scheme != "ws":
        raise WebSocketError(f"unsupported websocket scheme: {parsed.scheme}")

    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += f"?{parsed.query}"

    reader, writer = await asyncio.open_connection(host, port)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    writer.write(request.encode("ascii"))
    await writer.drain()

    status_line, headers = await _read_response(reader)
    if not status_line.startswith("HTTP/1.1 101"):
        raise WebSocketError(f"websocket handshake failed: {status_line}")

    expected = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
    if headers.get("sec-websocket-accept") != expected:
        raise WebSocketError("invalid Sec-WebSocket-Accept")
    return WebSocketConnection(reader, writer, mask_outgoing=True)


async def _read_headers(reader: asyncio.StreamReader) -> dict[str, str]:
    _start_line, headers = await _read_response(reader)
    return headers


async def _read_response(reader: asyncio.StreamReader) -> tuple[str, dict[str, str]]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(4096)
        if not chunk:
            raise WebSocketError("connection closed during HTTP header read")
        data.extend(chunk)
        if len(data) > 65536:
            raise WebSocketError("HTTP headers too large")

    head, _body = bytes(data).split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return lines[0], headers
