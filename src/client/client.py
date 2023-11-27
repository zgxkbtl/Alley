import asyncio
import json
import logging
import websockets
import argparse
import signal

# logging.basicConfig(level=logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)


active_tcp_connections = {}
active_tcp_listeners = {}

async def handle_tcp_connection(connection_id, target_host, target_port, websocket):
    logger.info(f"New TCP connection: {connection_id}")
    reader, writer = await asyncio.open_connection(target_host, target_port)
    logger.info(f"Connected to {target_host}:{target_port}")
    active_tcp_connections[connection_id] = (reader, writer)
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            # 将内网TCP数据编码并通过WebSocket发送给服务器
            await websocket.send(json.dumps({
                "type": "tcp_data",
                "connection_id": connection_id,
                "payload" : {
                    "data": data.hex(),
                    "connection_id": connection_id
                },
                "data": data.hex()
            }))
    except Exception as e:
        print(f"Error in handle_tcp_connection: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def websocket_listener(websocket, target_host='localhost', target_port=22):

    async for message in websocket:
        # message = await websocket.recv()
        data = json.loads(message)
        logger.info(f"Received message: {data}")
        if data['type'] == 'new_connection':
            # 服务端通知新的TCP连接
            connection_id = data['connection_id']
            # ...
            # 创建新的任务以处理内网TCP连接
            task = asyncio.create_task(handle_tcp_connection(connection_id, target_host, target_port, websocket))
            active_tcp_listeners[connection_id] = task
        elif data['type'] == 'tcp_data':
            # 从服务端接收TCP数据
            connection_id = data['connection_id']
            tcp_data = bytes.fromhex(data['data'])
            # 从活跃的TCP连接中获取writer对象
            while not active_tcp_connections.get(connection_id):
                await asyncio.sleep(0.1)
            r, w = active_tcp_connections.get(connection_id)
            if w:
                # 将数据写入内网TCP连接
                w.write(tcp_data)
                await w.drain()

async def main(hostport, port):
    async with websockets.connect(f"ws://{hostport}") as websocket:
        await websocket.send(json.dumps({
            "type": 'tcp_listen',
            "payload": {
                "port": port,
                "remote_host": "localhost",
                "remote_port": 9999
            }
        }))

        await websocket_listener(websocket, target_port=port)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("port", type=int, nargs='?', default=8000, help="The port to listen on")
    parser.add_argument("--schema", type=str, default='tcp', help="The schema to use")
    parser.add_argument("--hostport", type=str, default='localhost:8765', help="The host:port to bind to")

    args = parser.parse_args()

    port = args.port
    schema = args.schema
    hostport = args.hostport

    if schema == 'tcp':
        asyncio.run(main(hostport, port))
