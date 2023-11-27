import argparse
import asyncio
import json
import logging
import os
import signal
import uuid
import websockets

logging.basicConfig(level=logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)



# 用于存储所有活跃的TCP连接
active_tcp_connections = {}

async def tcp_server_handler(
        client_reader: asyncio.StreamReader, 
        client_writer: asyncio.StreamWriter, 
        websocket: websockets.WebSocketServerProtocol):
    # 为新的TCP连接生成一个唯一的标识符
    connection_id = str(uuid.uuid4())
    active_tcp_connections[connection_id] = (client_reader, client_writer)
    # 通知客户端新的TCP连接已建立，包括连接ID
    await websocket.send(json.dumps({
        "type": "new_connection",
        "connection_id": connection_id,
        "port": port,
        "data_tunnel_mode": 'reuse'
    }))
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
            # # 从客户端接收数据
            # response = await websocket.recv()
            # # 将客户端的数据写回TCP连接
            # client_writer.write(response)
            # await client_writer.drain()
    except Exception as e:
        logger.error(e)
    finally:
        client_writer.close()
        await client_writer.wait_closed()
        del active_tcp_connections[connection_id]  # 移除已关闭的连接


CONNECTIONS = {}

async def handler(websocket: websockets.WebSocketServerProtocol, path: str):
    logger.info(f'New connection from {websocket.remote_address}')
    websocket_id = str(uuid.uuid4())
    CONNECTIONS[websocket_id] = {
        'websocket': websocket,
        'tcp_server': [],
        'websocket_id': websocket_id
    }
    try:
        async for message in websocket:
            data = json.loads(message)
            logger.info(f"Received message: {data}")
            if data['type'] == 'tcp_listen':
                # 为新的TCP连接生成一个唯一的标识符
                # connection_id = str(uuid.uuid4())
                port = data['payload']['port']
                remote_host = data['payload']['remote_host']
                remote_port = data['payload']['remote_port']
                # 开启TCP服务器监听指定端口
                tcp_server = await asyncio.start_server(
                    lambda r, w: tcp_server_handler(r, w, websocket),
                    '0.0.0.0', remote_port
                )
                # 通知客户端新的TCP服务器已建立
                await websocket.send(json.dumps({
                    "type": "new_tcp_server",
                    # "connection_id": connection_id,
                    "port": port,
                    "websocket_id": websocket_id,
                    "data_tunnel_mode": 'reuse'
                }))
                # 将TCP服务器加入到活跃的TCP连接中
                CONNECTIONS[websocket_id]['tcp_server'].append(tcp_server)
            elif data['type'] == 'tcp_data':
                # 从活跃的TCP连接中找到指定的连接
                connection_id = data['payload']['connection_id']
                if connection_id in active_tcp_connections:
                    # 将数据写回TCP连接
                    client_reader, client_writer = active_tcp_connections[connection_id]
                    assert isinstance(client_writer, asyncio.StreamWriter)
                    client_writer.write(bytes.fromhex(data['data']))
                    await client_writer.drain()
    except websockets.exceptions.ConnectionClosed:
        logger.info(f'Connection closed from {websocket.remote_address}')
    finally:
        logger.info(f'Cancelling all TCP servers for {websocket.remote_address}')
        for tcp_server in CONNECTIONS[websocket_id]['tcp_server']:
            tcp_server.close()
            await tcp_server.wait_closed()
        del CONNECTIONS[websocket_id]
        logger.info(f'Cancelled all TCP servers for {websocket.remote_address}')

async def start_server(host: str, port: int):
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    if os.name != 'nt':  # Not Windows
        loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)
        loop.add_signal_handler(signal.SIGINT, stop.set_result, None)

    async with websockets.serve(handler, host, port):
        await stop


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765, help="The port to listen on")
    parser.add_argument("--host", type=str, default='localhost', help="The host to bind to")
    args = parser.parse_args()

    port = args.port
    host = args.host

    asyncio.run(start_server(host, port))
