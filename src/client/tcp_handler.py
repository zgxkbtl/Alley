import json
import websockets
from src.common.protocol import Packet, PacketType


async def send_tcp_close_signal(websocket: websockets.WebSocketServerProtocol, connection_id: str, message: str):
    response = Packet({
        "type": PacketType.TCP_CLOSE,
        "connection_id": connection_id,
        "data": message
    }).json()
    await websocket.send(json.dumps(response))