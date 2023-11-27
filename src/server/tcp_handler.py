import asyncio
import json
import websockets
import logging

logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s')
# logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)
logger.addHandler(ch)

async def tcp_server_handler(
        client_reader: asyncio.StreamReader, 
        client_writer: asyncio.StreamWriter, 
        connection_id: str,
        websocket: websockets.WebSocketServerProtocol):
    try:
        while True:
            data = await client_reader.read(4096)  # 读取TCP连接的数据
            if not data:
                break
            # 将数据通过WebSocket发送到客户端，包括连接ID
            await websocket.send(json.dumps({
                "connection_id": connection_id,
                "data": data.hex()  # 将二进制数据编码为十六进制字符串
            }))
            # 从客户端接收数据
            response = await websocket.recv()
            # 将客户端的数据写回TCP连接
            client_writer.write(response)
            await client_writer.drain()
    except Exception as e:
        logger.error(e)
    finally:
        client_writer.close()
        await client_writer.wait_closed()
