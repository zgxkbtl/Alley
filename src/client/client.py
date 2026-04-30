import asyncio
import json
import argparse
from src.common.log_config import configure_logger
from src.common.protocol import Packet, PacketType
from src.common.ws import ConnectionClosed, connect

logger = configure_logger(__name__)
websocket_listener_logger = configure_logger('alley.ws')
TCP_CHUNK_SIZE = 64 * 1024

active_tcp_connections = {}
active_tcp_events = {}


async def send_tcp_close_signal(
        websocket,
        connection_id: str,
        message: str,
        send_lock: asyncio.Lock):
    response = Packet({
        "type": PacketType.TCP_CLOSE,
        "connection_id": connection_id,
        "data": message
    }).json()
    try:
        async with send_lock:
            await websocket.send(json.dumps(response))
    except ConnectionClosed:
        logger.info("WebSocket closed before TCP close signal could be sent: %s", connection_id)

async def handle_tcp_connection(
        connection_id, 
        target_host, 
        target_port, 
        websocket,
        send_lock: asyncio.Lock,
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
        logger.debug(f"New TCP connection {connection_id} to {target_host}:{target_port}")
        reader, writer = await asyncio.open_connection(target_host, target_port)
        active_tcp_connections[connection_id] = (reader, writer)
        if event:
            event.set()
        logger.debug(f"Connected to {target_host}:{target_port}")
        while True:
            data = await reader.read(TCP_CHUNK_SIZE)
            if not data:
                break
            # 将内网TCP数据编码并通过WebSocket发送给服务器
            response = Packet({
                "type": PacketType.TCP_DATA,
                "connection_id": connection_id,
                "data": data.hex()
            }).json()
            async with send_lock:
                await websocket.send(json.dumps(response))
    except Exception as e:
        logger.error('Local TCP handler failed: %s', e, exc_info=True)
    finally:
        if 'writer' in locals():
            try:
                if not writer.is_closing():
                    writer.close()
                await writer.wait_closed()
            except Exception as e:
                logger.error("Error closing TCP connection for Local socket: %s", e)

        active_tcp_connections.pop(connection_id, None)
        active_tcp_events.pop(connection_id, None)
        if event:
            event.set()

        await send_tcp_close_signal(websocket, connection_id, 'Connection closed', send_lock)
        logger.debug(f"Closed TCP connection for local socket: {connection_id}")

async def websocket_listener(websocket, send_lock: asyncio.Lock, target_host='localhost', target_port=22):
    """
    监听WebSocket消息
    :param websocket: WebSocket连接对象
    :param target_host: 本地目标主机
    :param target_port: 本地目标端口
    :return: None
    """
    async for message in websocket:
        # message = await websocket.recv()
        try:
            data = Packet(json.loads(message))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning('Invalid packet from server: %s', e)
            continue
        if data.type == PacketType.NEW_NOTIFICATION:
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
                    connection_id, target_host, target_port, websocket, send_lock,
                    event=event))

            task.add_done_callback(lambda x: logger.debug(f"Task {x} done"))

        elif data.type == PacketType.TCP_DATA:
            # 从服务端接收TCP数据
            connection_id = data.connection_id
            tcp_data = bytes.fromhex(data.data)
            # 从活跃的TCP连接中获取writer对象
            event: asyncio.Event = active_tcp_events.get(connection_id, None)
            if event:
                await event.wait()
            _r, w = active_tcp_connections.get(connection_id, (None, None))
            if w:
                # 将数据写入内网TCP连接
                w.write(tcp_data)
                await w.drain()
            else:
                logger.error(f"Invalid connection ID: {connection_id}")

        elif data.type == PacketType.NEW_TCP_SERVER:
            # 服务端通知新的TCP服务器已建立
            logger.info(f"New TCP server on remote: {data.payload.remote_host}:{data.payload.remote_port}")

        elif data.type == PacketType.TCP_CLOSE:
            # 服务端通知TCP连接已关闭
            connection_id = data.connection_id
            if connection_id in active_tcp_connections:
                # 远端输入已关闭，半关闭本地写入端，继续读取本地服务响应。
                _reader, writer = active_tcp_connections[connection_id]
                try:
                    if not writer.is_closing() and writer.can_write_eof():
                        writer.write_eof()
                        await writer.drain()
                    elif not writer.is_closing():
                        writer.close()
                except Exception as e:
                    logger.error("Error half-closing TCP connection for Local socket: %s", e)
                logger.debug(f"Half-closed local TCP writer: {connection_id}")
            else:
                logger.debug(f"TCP connection already closed: {connection_id}")

async def async_main(hostport, 
                     target_port, target_host, 
                     remote_port, remote_host='localhost',
                     schema='tcp', **kwargs):
    listen_type = PacketType.TCP_LISTEN if schema == 'tcp' else PacketType.HTTP_LISTEN
    if listen_type == PacketType.HTTP_LISTEN:
        async with connect(f"ws://{hostport}") as websocket:
            send_lock = asyncio.Lock()
            # TODO: support multiple proxy servers: using for loop with config_id
            response = Packet({
                "type": listen_type,
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
            await websocket_listener(websocket, send_lock, target_host=target_host, target_port=target_port)

    elif listen_type == PacketType.TCP_LISTEN:
        async with connect(f"ws://{hostport}") as websocket:
            send_lock = asyncio.Lock()
            response = Packet({
                "type": listen_type,
                "payload": {
                    "config_id": 0,
                    "port": target_port,
                    "remote_host": remote_host,
                    "remote_port": remote_port
                }
            }).json()
            await websocket.send(json.dumps(response))

            await websocket_listener(websocket, send_lock, target_host=target_host, target_port=target_port)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int, nargs='?', default=8000, help="The port to listen on")
    parser.add_argument("--target_host", type=str, default='localhost', help="The target host")
    parser.add_argument("--schema", choices=('http', 'tcp'), default='http', help="The schema to use")
    parser.add_argument("--hostport", type=str, default='localhost:8765', help="The host:port to bind to")
    parser.add_argument("--remote_port", type=int, default=None, help="The remote port to connect to")
    parser.add_argument("--domain", type=str, default=None, help="The sub domain to use")

    args = parser.parse_args()

    target_port = args.port
    schema = args.schema
    hostport = args.hostport
    target_host = args.target_host
    remote_port = args.remote_port

    try:
        asyncio.run(async_main(hostport, target_port, target_host, remote_port, schema=schema, 
                               domain=args.domain))
    except KeyboardInterrupt:
        logger.warning('KeyboardInterrupt')

if __name__ == "__main__":
    main()
