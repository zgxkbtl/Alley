import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import argparse
import asyncio
import json
import signal
import uuid
import websockets
from src.common.protocol import Packet, PacketType
from src.server.tcp_handler import tcp_server_handler, tcp_server_response_handler
from src.common.log_config import configure_logger

logger = configure_logger(__name__)
websockets_logger = configure_logger('websockets')

CONNECTIONS = {}

async def handler(websocket: websockets.WebSocketServerProtocol, path: str):
    logger.info(f'New websocket connection from {websocket.remote_address}')
    websocket_id = str(uuid.uuid4())
    CONNECTIONS[websocket_id] = {
        'websocket': websocket,
        'tcp_server': [],
        'websocket_id': websocket_id
    }
    try:
        async for message in websocket:
            data = json.loads(message)
            data = Packet(data)

            if data.type == PacketType.TCP_LISTEN:

                # # 获取主机的所有IP地址
                # host_info = socket.getaddrinfo(socket.gethostname(), None)

                # # 获取所有的IPv4地址
                # ip_addresses = [info[4][0] for info in host_info if info[0] == socket.AF_INET]

                # 开启TCP服务器监听指定端口
                tcp_server = await asyncio.start_server(
                    lambda r, w: tcp_server_handler(r, w, websocket),
                    host=data.payload.remote_host,
                    port=data.payload.remote_port
                )
                # 通知客户端新的TCP服务器已建立
                response = Packet({
                    "type": PacketType.NEW_TCP_SERVER,
                    "payload": {
                        "remote_host": tcp_server.sockets[0].getsockname()[0],
                        "remote_port": tcp_server.sockets[0].getsockname()[1],
                        "websocket_id": websocket_id,
                        "data_tunnel_mode": 'reuse'
                    }
                }).json()
                await websocket.send(json.dumps(response))
                # 将TCP服务器加入到活跃的TCP连接中
                CONNECTIONS[websocket_id]['tcp_server'].append(tcp_server)

            elif data.type == PacketType.TCP_DATA:
                await tcp_server_response_handler(data, websocket)

    except websockets.exceptions.ConnectionClosed:
        logger.info(f'Connection closed from {websocket.remote_address}')
    except Exception as e:
        logger.error(e)
    finally:
        logger.info(f'Cancelling all TCP servers for {websocket.remote_address}')
        for tcp_server in CONNECTIONS[websocket_id]['tcp_server']:
            assert isinstance(tcp_server, asyncio.Server)
            tcp_server.close()
            try:
                timeout = 5.0
                await asyncio.wait_for(tcp_server.wait_closed(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f'Failed to close TCP server in {timeout} seconds')
                # 获取事件循环中的所有任务
                tasks = asyncio.all_tasks()
                # 取消与当前服务器相关的所有任务
                for task in tasks:
                    if task.get_coro().__name__ == 'serve_forever' and task.get_coro().__self__ is tcp_server:
                        task.cancel()
                        
        del CONNECTIONS[websocket_id]
        logger.info(f'Cancelled all TCP servers for {websocket.remote_address}')

async def start_server(host: str, port: int):
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    if os.name != 'nt':  # Not Windows
        loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    try:
        async with websockets.serve(handler, host, port):
            await stop
    except asyncio.CancelledError:
        logger.info('Server stopped')
    except Exception as e:
        logger.error(e)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765, help="The port to listen on")
    parser.add_argument("--host", type=str, default='localhost', help="The host to bind to")
    args = parser.parse_args()

    port = args.port
    host = args.host
    
    try:
        asyncio.run(start_server(host, port))
    except KeyboardInterrupt:
        logger.warning('KeyboardInterrupt')

if __name__ == "__main__":
    main()
