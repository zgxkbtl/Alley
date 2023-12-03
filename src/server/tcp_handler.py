import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
SERVER_DOMAIN = os.getenv('SERVER_DOMAIN', '')


import asyncio
import json
import websockets
import logging

from src.common.protocol import Packet, PacketType
from src.common.log_config import configure_logger

logger = configure_logger(__name__)

# 用于存储所有活跃的TCP连接
active_tcp_connections = {}

async def tcp_server_handler(
        client_reader: asyncio.StreamReader, 
        client_writer: asyncio.StreamWriter, 
        websocket: websockets.WebSocketServerProtocol):
    # TODO: support multiple TCP connections: bring config_id to tcp_server_handler

    # 为新的TCP连接生成一个唯一的标识符
    connection_id = str(uuid.uuid4())
    active_tcp_connections[connection_id] = (client_reader, client_writer)
    # 通知客户端新的TCP连接已建立，包括连接ID
    response = Packet({
        "type": PacketType.NEW_CONNECTION,
        "connection_id": connection_id,
        "payload": {
            "data_tunnel_mode": 'reuse'
        }
    }).json()
    await websocket.send(json.dumps(response))
    try:
        while True:
            data = await client_reader.read(4096)  # 读取TCP连接的数据
            if not data:
                break
            # 将数据通过WebSocket发送到客户端，包括连接ID
            await websocket.send(json.dumps({
                "type": "tcp_data",
                "connection_id": connection_id,
                "data": data.hex()  # 将二进制数据编码为十六进制字符串
            }))
    except Exception as e:
        logger.error(e)
    finally:
        try:
            if not client_writer.is_closing():
                client_writer.close()
            await client_writer.wait_closed()
        except Exception as e:
            logger.error("Error closing TCP connection for Remote socket: %s", e)
        # TODO: 通知客户端TCP连接已关闭，包括连接ID
        await send_tcp_close_signal(websocket, connection_id, 'TCP connection closed')
        active_tcp_connections.pop(connection_id, None)  # 移除已关闭的连接

async def tcp_server_response_handler(data: Packet, websocket: websockets.WebSocketServerProtocol):
    # 从WebSocket接收到TCP数据
    connection_id = data.connection_id
    if connection_id not in active_tcp_connections:
        logger.error(f"Invalid connection ID: {connection_id}")
        return
    _client_reader, client_writer = active_tcp_connections[connection_id]
    assert isinstance(client_writer, asyncio.StreamWriter)
    # 将数据写入TCP连接
    client_writer.write(bytes.fromhex(data.data))
    await client_writer.drain()


async def tcp_server_listener(websocket: websockets.WebSocketServerProtocol, data: Packet) -> asyncio.Server:
    # # 获取主机的所有IP地址
    # host_info = socket.getaddrinfo(socket.gethostname(), None)

    # # 获取所有的IPv4地址
    # ip_addresses = [info[4][0] for info in host_info if info[0] == socket.AF_INET]

    # 开启TCP服务器监听指定端口
    host = data.payload.remote_host
    if data.type == PacketType.TCP_LISTEN:
        host = '0.0.0.0'
    tcp_server = await asyncio.start_server(
        lambda r, w: tcp_server_handler(r, w, websocket),
        host=host,
        port=data.payload.remote_port
    )
    # 通知客户端新的TCP服务器已建立
    remote_host = SERVER_DOMAIN if SERVER_DOMAIN else websocket.remote_address[0]
    remote_port = tcp_server.sockets[0].getsockname()[1]
    # response = Packet({
    #     "type": PacketType.NEW_TCP_SERVER,
    #     "payload": {
    #         "remote_host": remote_host,
    #         "remote_port": tcp_server.sockets[0].getsockname()[1],
    #         "data_tunnel_mode": 'reuse'
    #     }
    # }).json()
    # await websocket.send(json.dumps(response))
    await send_notification(websocket, f'New TCP server {remote_host}:{remote_port} ---> {data.payload.port}')
    return tcp_server

async def send_notification(websocket: websockets.WebSocketServerProtocol, message: str):
    response = Packet({
        "type": PacketType.NEW_NOTIFICATION,
        "data": message
    }).json()
    await websocket.send(json.dumps(response))

async def terminate_tcp_connection(websocket: websockets.WebSocketServerProtocol, connection_id: str):
    reader, writer = active_tcp_connections[connection_id]
    if not isinstance(writer, asyncio.StreamWriter):
        logger.error(f"Invalid connection ID: {connection_id}")
        return
    try:
        if not writer.is_closing():
            writer.close()
        await writer.wait_closed()
    except Exception as e:
        logger.error("Error closing TCP connection for Remote socket: %s", e)
    active_tcp_connections.pop(connection_id, None)
    logger.info(f"TCP connection {connection_id} closed")
    await send_notification(websocket, f'TCP connection {connection_id} closed')

async def send_tcp_close_signal(websocket: websockets.WebSocketServerProtocol, connection_id: str, message: str):
    response = Packet({
        "type": PacketType.TCP_CLOSE,
        "connection_id": connection_id,
        "data": message
    }).json()
    await websocket.send(json.dumps(response))