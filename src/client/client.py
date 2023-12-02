import sys
import os
from src.client.tcp_handler import send_tcp_close_signal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import asyncio
import json
import logging
import websockets
import argparse
import signal
from src.common.log_config import configure_logger
from src.common.protocol import Packet, PacketType

logger = configure_logger(__name__)
websocket_listener_logger = configure_logger('websockets')

active_tcp_connections = {}
active_tcp_events = {}

async def handle_tcp_connection(
        connection_id, 
        target_host, 
        target_port, 
        websocket: websockets.WebSocketClientProtocol,
        event: asyncio.Event = None
        ):
    """
    用于处理内网TCP连接的任务
    :param connection_id: 连接ID
    :param target_host: 目标主机
    :param target_port: 目标端口
    :param websocket: WebSocket连接对象
    :return: None
    """
    
    try:
        logger.info(f"New TCP connection {connection_id} to {target_host}:{target_port}")
        reader, writer = await asyncio.open_connection(target_host, target_port)
        if event:
            event.set()
        logger.info(f"Connected to {target_host}:{target_port}")
        active_tcp_connections[connection_id] = (reader, writer)
        while True:
            data = await reader.read(4096)
            if not data:
                break
            # 将内网TCP数据编码并通过WebSocket发送给服务器
            response = Packet({
                "type": PacketType.TCP_DATA,
                "connection_id": connection_id,
                "data": data.hex()
            }).json()
            await websocket.send(json.dumps(response))
    except Exception as e:
        logger.error(e)
    finally:
        if 'writer' in locals():
            writer.close()
            await writer.wait_closed()
        active_tcp_connections.pop(connection_id, None)
        eve = active_tcp_events.pop(connection_id, None)
        if event:
            event.set()
        # TODO: 通知服务端关闭连接 connection_id
        await send_tcp_close_signal(websocket, connection_id, 'Connection closed')
        logger.info(f"Closed TCP connection: {connection_id}")

async def websocket_listener(websocket, target_host='localhost', target_port=22):
    """
    监听WebSocket消息
    :param websocket: WebSocket连接对象
    :param target_host: 本地目标主机
    :param target_port: 本地目标端口
    :return: None
    """
    async for message in websocket:
        # message = await websocket.recv()
        data = json.loads(message)
        data = Packet(data)
        logger.info(f"Received message: {data}")
        # TODO: support multiple proxy servers: using config_id to identify proxy server
        if data.type == PacketType.NEW_CONNECTION:
            # 服务端通知新的TCP连接
            connection_id = data.connection_id
            # 创建新的任务以处理内网TCP连接
            event = asyncio.Event()
            active_tcp_events[connection_id] = event
            task = asyncio.create_task(
                handle_tcp_connection(
                    connection_id, target_host, target_port, websocket,
                    event=event))
            # TODO: 通知服务端关闭连接 connection_id
            task.add_done_callback(lambda x: logger.info(f"Task {x} done"))
        elif data.type == PacketType.TCP_DATA:
            # 从服务端接收TCP数据
            connection_id = data.connection_id
            tcp_data = bytes.fromhex(data.data)
            # 从活跃的TCP连接中获取writer对象
            event: asyncio.Event = active_tcp_events.get(connection_id, None)
            if event: await event.wait()
            r, w = active_tcp_connections.get(connection_id, (None, None))
            if w:
                # 将数据写入内网TCP连接
                w.write(tcp_data)
                await w.drain()
            else:
                logger.error(f"Invalid connection ID: {connection_id}")
        elif data.type == PacketType.NEW_TCP_SERVER:
            # 服务端通知新的TCP服务器已建立
            logger.info(f"New TCP server on remote: {data.payload.remote_host}:{data.payload.remote_port}")

async def async_main(hostport, 
                     target_port, target_host, 
                     remote_port, remote_host='localhost',
                     schema='tcp', **kwargs):
    type = PacketType.TCP_LISTEN if schema == 'tcp' else PacketType.HTTP_LISTEN
    if type == PacketType.HTTP_LISTEN:
        async with websockets.connect(f"ws://{hostport}") as websocket:
            # TODO: support multiple proxy servers: using for loop with config_id
            response = Packet({
                "type": type,
                "payload": {
                    "config_id": 0,
                    "port": target_port,
                    "remote_host": remote_host,
                    "remote_port": remote_port,
                    "domain": kwargs.get('domain', '')
                }
            }).json()
            await websocket.send(json.dumps(response))
            # TODO: support multiple proxy servers: using config with config_id
            await websocket_listener(websocket, target_host=target_host, target_port=target_port)

    if type == PacketType.TCP_LISTEN:
        async with websockets.connect(f"ws://{hostport}") as websocket:
            response = Packet({
                "type": type,
                "payload": {
                    "config_id": 0,
                    "port": target_port,
                    "remote_host": remote_host,
                    "remote_port": remote_port
                }
            }).json()
            await websocket.send(json.dumps(response))

            await websocket_listener(websocket, target_host=target_host, target_port=target_port)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int, nargs='?', default=8000, help="The port to listen on")
    parser.add_argument("--target_host", type=str, default='localhost', help="The target host")
    parser.add_argument("--schema", type=str, default='http', help="The schema to use, http or tcp")
    parser.add_argument("--hostport", type=str, default='localhost:8765', help="The host:port to bind to")
    parser.add_argument("--remote_port", type=int, default=None, help="The remote port to connect to")
    parser.add_argument("--domain", type=str, default=None, help="The sub domain to use")

    args = parser.parse_args()

    target_port = args.port
    schema = args.schema
    hostport = args.hostport
    target_host = args.target_host
    remote_port = args.remote_port

    asyncio.run(async_main(hostport, target_port, target_host, remote_port, schema=schema, 
                           domain=args.domain))

if __name__ == "__main__":
    main()
