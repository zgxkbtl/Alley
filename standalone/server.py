#!/usr/bin/env python3
"""
Alley standalone server: zero third-party dependencies.

Usage:
  python3 server.py --host 0.0.0.0 --port 8765

This copy-paste build supports TCP tunnels only. HTTP domain routing via nginx
unit stays in the packaged Alley server.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import logging
import os
import signal
import socket
import struct
import uuid
from contextlib import suppress


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TCP_CHUNK_SIZE = 64 * 1024
XOR_TABLES = [bytes(byte ^ mask for byte in range(256)) for mask in range(256)]


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%m-%d %H:%M:%S",
)
logger = logging.getLogger("alley-standalone-server")


class ConnectionClosed(Exception):
    pass


class WebSocket:
    def __init__(self, reader, writer, *, mask_outgoing=False):
        self.reader = reader
        self.writer = writer
        self.mask_outgoing = mask_outgoing
        self.remote_address = writer.get_extra_info("peername")
        self.local_address = writer.get_extra_info("sockname")
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


async def read_http_headers(reader):
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
    return headers


async def accept_websocket(reader, writer):
    headers = await read_http_headers(reader)
    key = headers.get("sec-websocket-key")
    if not key:
        raise ConnectionClosed("missing Sec-WebSocket-Key")
    accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
    writer.write(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        ).encode("ascii")
    )
    await writer.drain()
    return WebSocket(reader, writer)


class TunnelServer:
    def __init__(self):
        self.tcp_connections = {}
        self.tcp_websockets = {}
        self.websocket_servers = {}

    async def websocket_handler(self, reader, writer):
        websocket = None
        websocket_id = str(uuid.uuid4())
        send_lock = asyncio.Lock()
        self.websocket_servers[websocket_id] = []
        try:
            websocket = await accept_websocket(reader, writer)
            logger.info("WebSocket connected from %s", websocket.remote_address)
            async for message in websocket:
                try:
                    packet = json.loads(message)
                except json.JSONDecodeError:
                    logger.warning("Ignoring invalid JSON packet")
                    continue
                packet_type = packet.get("type")
                if packet_type == "tcp_listen":
                    server = await self.start_tcp_listener(websocket, packet, send_lock)
                    self.websocket_servers[websocket_id].append(server)
                elif packet_type == "tcp_data":
                    await self.write_tcp(packet)
                elif packet_type == "tcp_close":
                    await self.close_tcp(packet.get("connection_id"))
        except ConnectionClosed:
            logger.info("WebSocket closed")
        except Exception:
            logger.exception("WebSocket handler error")
        finally:
            await self.close_websocket_tcp(websocket)
            for server in self.websocket_servers.pop(websocket_id, []):
                server.close()
                with suppress(Exception):
                    await asyncio.wait_for(server.wait_closed(), timeout=3)

    async def start_tcp_listener(self, websocket, packet, send_lock):
        payload = packet.get("payload", {})
        target_port = payload.get("port")
        remote_port = payload.get("remote_port")
        tcp_server = await asyncio.start_server(
            lambda r, w: self.tcp_handler(r, w, websocket, send_lock),
            host="0.0.0.0",
            port=remote_port,
        )
        listen_port = tcp_server.sockets[0].getsockname()[1]
        await self.notify(websocket, send_lock, f"New TCP server 0.0.0.0:{listen_port} ---> {target_port}")
        for ip_address in local_ipv4_addresses():
            await self.notify(websocket, send_lock, f"New TCP server {ip_address}:{listen_port} ---> {target_port}")
        return tcp_server

    async def tcp_handler(self, reader, writer, websocket, send_lock):
        connection_id = str(uuid.uuid4())
        self.tcp_connections[connection_id] = (reader, writer)
        self.tcp_websockets[connection_id] = websocket
        await self.send_packet(websocket, send_lock, {
            "type": "new_connection",
            "connection_id": connection_id,
            "payload": {"data_tunnel_mode": "reuse"},
        })
        try:
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
            logger.debug("Remote TCP handler ended", exc_info=True)
            await self.close_tcp(connection_id)
        else:
            await self.send_packet(websocket, send_lock, {
                "type": "tcp_close",
                "connection_id": connection_id,
                "data": "TCP input closed",
            })
            asyncio.create_task(self.close_tcp_later(connection_id))

    async def write_tcp(self, packet):
        connection_id = packet.get("connection_id")
        if connection_id not in self.tcp_connections:
            logger.debug("Ignoring data for closed TCP connection %s", connection_id)
            return
        _reader, writer = self.tcp_connections[connection_id]
        try:
            writer.write(bytes.fromhex(packet.get("data") or ""))
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            await self.close_tcp(connection_id)

    async def close_tcp(self, connection_id):
        _reader, writer = self.tcp_connections.pop(connection_id, (None, None))
        self.tcp_websockets.pop(connection_id, None)
        if writer and not writer.is_closing():
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    async def close_tcp_later(self, connection_id, timeout=300):
        await asyncio.sleep(timeout)
        if connection_id in self.tcp_connections:
            logger.debug("Closing stale half-closed TCP connection %s", connection_id)
            await self.close_tcp(connection_id)

    async def close_websocket_tcp(self, websocket):
        if websocket is None:
            return
        connection_ids = [
            connection_id
            for connection_id, owner in list(self.tcp_websockets.items())
            if owner is websocket
        ]
        for connection_id in connection_ids:
            await self.close_tcp(connection_id)

    async def notify(self, websocket, send_lock, message):
        await self.send_packet(websocket, send_lock, {"type": "new_notification", "data": message})

    async def send_packet(self, websocket, send_lock, packet):
        async with send_lock:
            await websocket.send(json.dumps(packet))


def local_ipv4_addresses():
    addresses = []
    with suppress(OSError):
        for info in socket.getaddrinfo(socket.gethostname(), None):
            if info[0] == socket.AF_INET and info[4][0] not in addresses:
                addresses.append(info[4][0])
    return addresses


async def main_async(host, port):
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    if os.name != "nt":
        loop.add_signal_handler(signal.SIGTERM, lambda: stop.done() or stop.set_result(None))

    tunnel = TunnelServer()
    server = await asyncio.start_server(tunnel.websocket_handler, host, port)
    async with server:
        logger.info("Alley standalone server listening on %s:%s", host or "0.0.0.0", port)
        await stop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="", help="host to bind")
    parser.add_argument("--port", type=int, default=8765, help="websocket control port")
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
