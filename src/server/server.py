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
from src.server.tcp_handler import send_notification, tcp_server_response_handler, tcp_server_listener
from src.common.log_config import configure_logger
from src.server.nginx_unit_controller import set_proxy_config

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
                tcp_server = await tcp_server_listener(websocket, data)
                # 将TCP服务器加入到活跃的TCP连接中
                CONNECTIONS[websocket_id]['tcp_server'].append(tcp_server)
                logger.info(f'New TCP server {tcp_server.sockets[0].getsockname()} for {websocket.remote_address}')
            
            elif data.type == PacketType.HTTP_LISTEN:
                tcp_server = await tcp_server_listener(websocket, data)
                CONNECTIONS[websocket_id]['tcp_server'].append(tcp_server)
                logger.info(f'New TCP server {tcp_server.sockets[0].getsockname()} for {websocket.remote_address}')
                domain = await set_proxy_config(data.payload.domain, tcp_server.sockets[0].getsockname()[1])
                logger.info(f'Set proxy config for {websocket.remote_address}')
                await send_notification(websocket, f'Proxy config set for {domain} ---> {data.payload.port}')

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
    parser.add_argument("--host", type=str, default='', help="The host to bind to")
    args = parser.parse_args()

    port = args.port
    host = args.host
    
    try:
        asyncio.run(start_server(host, port))
    except KeyboardInterrupt:
        logger.warning('KeyboardInterrupt')

if __name__ == "__main__":
    main()
