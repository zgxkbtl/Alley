#!/usr/bin/env python3
"""
Alley standalone client: zero third-party dependencies.

Usage:
  python3 client.py 8000 --hostport example.com:8765 --remote_port 9000

This copy-paste build supports TCP tunnels only. Keep reading while writing for
large full-duplex flows; "write all first, read later" can hit OS backpressure.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import struct
from contextlib import suppress
from urllib.parse import urlparse


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TCP_CHUNK_SIZE = 64 * 1024
XOR_TABLES = [bytes(byte ^ mask for byte in range(256)) for mask in range(256)]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%m-%d %H:%M:%S",
)
logger = logging.getLogger("alley-standalone-client")


class ConnectionClosed(Exception):
    pass


class WebSocket:
    def __init__(self, reader, writer, *, mask_outgoing=True):
        self.reader = reader
        self.writer = writer
        self.mask_outgoing = mask_outgoing
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except ConnectionClosed:
            raise StopAsyncIteration

    async def send(self, message):
        if self.closed:
            raise ConnectionClosed("websocket is closed")
        payload = message.encode("utf-8")
        header = bytearray([0x81])
        mask_bit = 0x80 if self.mask_outgoing else 0
        length = len(payload)
        if length < 126:
            header.append(mask_bit | length)
        elif length < 2**16:
            header.extend((mask_bit | 126, *struct.pack("!H", length)))
        else:
            header.extend((mask_bit | 127, *struct.pack("!Q", length)))
        if self.mask_outgoing:
            mask = os.urandom(4)
            header.extend(mask)
            payload = apply_mask(payload, mask)
        try:
            self.writer.write(header + payload)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as exc:
            self.closed = True
            raise ConnectionClosed("websocket stream ended") from exc

    async def recv(self):
        message = bytearray()
        while True:
            opcode, payload, final = await self.read_frame()
            if opcode == 0x8:
                await self.close(send_close=not self.closed)
                raise ConnectionClosed("websocket closed")
            if opcode == 0x9:
                await self.write_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode not in (0x0, 0x1):
                raise ConnectionClosed(f"unsupported websocket opcode: {opcode}")
            message.extend(payload)
            if final:
                return message.decode("utf-8")

    async def close(self, *, send_close=True):
        if self.closed:
            return
        self.closed = True
        if send_close:
            with suppress(Exception):
                await self.write_frame(0x8, b"")
        self.writer.close()
        with suppress(Exception):
            await self.writer.wait_closed()

    async def read_frame(self):
        try:
            first, second = await self.reader.readexactly(2)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", await self.reader.readexactly(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
            mask = await self.reader.readexactly(4) if second & 0x80 else None
            payload = await self.reader.readexactly(length) if length else b""
        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError) as exc:
            raise ConnectionClosed("websocket stream ended") from exc
        return first & 0x0F, apply_mask(payload, mask) if mask else payload, bool(first & 0x80)

    async def write_frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length < 2**16:
            header.extend((126, *struct.pack("!H", length)))
        else:
            header.extend((127, *struct.pack("!Q", length)))
        try:
            self.writer.write(header + payload)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError) as exc:
            self.closed = True
            raise ConnectionClosed("websocket stream ended") from exc


def apply_mask(payload, mask):
    data = bytearray(payload)
    for index, mask_byte in enumerate(mask):
        data[index::4] = data[index::4].translate(XOR_TABLES[mask_byte])
    return bytes(data)


async def connect_websocket(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "ws":
        raise ValueError("only ws:// URLs are supported")
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
    status_line, headers = await read_http_response(reader)
    expected = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
    if not status_line.startswith("HTTP/1.1 101") or headers.get("sec-websocket-accept") != expected:
        raise ConnectionClosed(f"websocket handshake failed: {status_line}")
    return WebSocket(reader, writer)


async def read_http_response(reader):
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(4096)
        if not chunk:
            raise ConnectionClosed("connection closed during HTTP header read")
        data.extend(chunk)
        if len(data) > 65536:
            raise ConnectionClosed("HTTP headers too large")
    head, _body = bytes(data).split(b"\r\n\r\n", 1)
    lines = head.decode("iso-8859-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
    return lines[0], headers


class TunnelClient:
    def __init__(self, target_host, target_port):
        self.target_host = target_host
        self.target_port = target_port
        self.tcp_connections = {}
        self.tcp_events = {}

    async def run(self, hostport, remote_port):
        websocket = await connect_websocket(f"ws://{hostport}")
        send_lock = asyncio.Lock()
        try:
            await websocket.send(json.dumps({
                "type": "tcp_listen",
                "payload": {
                    "port": self.target_port,
                    "remote_host": "0.0.0.0",
                    "remote_port": remote_port,
                },
            }))
            async for message in websocket:
                await self.handle_packet(websocket, send_lock, json.loads(message))
        finally:
            await self.close_all_tcp()
            await websocket.close()

    async def handle_packet(self, websocket, send_lock, packet):
        packet_type = packet.get("type")
        connection_id = packet.get("connection_id")
        if packet_type == "new_notification":
            logger.info(packet.get("data"))
        elif packet_type == "new_connection":
            event = asyncio.Event()
            self.tcp_events[connection_id] = event
            asyncio.create_task(self.tcp_handler(connection_id, websocket, send_lock, event))
        elif packet_type == "tcp_data":
            event = self.tcp_events.get(connection_id)
            if event:
                await event.wait()
            _reader, writer = self.tcp_connections.get(connection_id, (None, None))
            if writer:
                try:
                    writer.write(bytes.fromhex(packet.get("data") or ""))
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    await self.close_tcp(connection_id)
        elif packet_type == "tcp_close":
            _reader, writer = self.tcp_connections.get(connection_id, (None, None))
            if writer and not writer.is_closing():
                with suppress(Exception):
                    if writer.can_write_eof():
                        writer.write_eof()
                        await writer.drain()
                    else:
                        writer.close()

    async def tcp_handler(self, connection_id, websocket, send_lock, event):
        try:
            reader, writer = await asyncio.open_connection(self.target_host, self.target_port)
            self.tcp_connections[connection_id] = (reader, writer)
            event.set()
            while True:
                data = await reader.read(TCP_CHUNK_SIZE)
                if not data:
                    break
                await self.send_packet(websocket, send_lock, {
                    "type": "tcp_data",
                    "connection_id": connection_id,
                    "data": data.hex(),
                })
        except Exception:
            logger.debug("Local TCP handler ended", exc_info=True)
        finally:
            _reader, writer = self.tcp_connections.pop(connection_id, (None, None))
            self.tcp_events.pop(connection_id, None)
            event.set()
            if writer and not writer.is_closing():
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
            with suppress(ConnectionClosed):
                await self.send_packet(websocket, send_lock, {
                    "type": "tcp_close",
                    "connection_id": connection_id,
                    "data": "Connection closed",
                })

    async def send_packet(self, websocket, send_lock, packet):
        async with send_lock:
            await websocket.send(json.dumps(packet))

    async def close_all_tcp(self):
        connection_ids = list(self.tcp_connections)
        for connection_id in connection_ids:
            await self.close_tcp(connection_id)

    async def close_tcp(self, connection_id):
        _reader, writer = self.tcp_connections.pop(connection_id, (None, None))
        self.tcp_events.pop(connection_id, None)
        if writer and not writer.is_closing():
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int, help="local target port")
    parser.add_argument("--target_host", default="127.0.0.1", help="local target host")
    parser.add_argument("--hostport", default="127.0.0.1:8765", help="server host:port")
    parser.add_argument("--remote_port", type=int, default=None, help="server-side TCP port; omit for random")
    args = parser.parse_args()
    try:
        asyncio.run(TunnelClient(args.target_host, args.port).run(args.hostport, args.remote_port))
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
