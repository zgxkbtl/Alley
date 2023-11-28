from enum import Enum


class PacketType(Enum):
    # Client -> Server
    TCP_LISTEN = 'tcp_listen'
    TCP_DATA = 'tcp_data'
    TCP_CLOSE = 'tcp_close'
    # Server -> Client
    NEW_CONNECTION = 'new_connection'
    NEW_TCP_SERVER = 'new_tcp_server'



class Packet:
    """
    This class is used to store a Packet object.
    
    Attributes:
        type: The type of the packet.
        data: The raw data to be sent over the wire. hex-encoded of binary.
        payload: The payload of the packet.
        size: The size of the packet.
        connection_id: The connection ID of the packet.
    """

    class Payload:
        """
        This class is used to store the payload of a Packet object.

        Attributes:
            data: The raw data to be sent over the wire. hex-encoded of binary.
            port: Local client port to listen on. not used.
            remote_host: The remote host to connect to.
            remote_port: The remote port to connect to.
            websocket_id: The ID of the WebSocket connection.
            data_tunnel_mode: The data tunnel mode to use.
        """
        def __init__(self, data: dict):
            self.data = data.get('data')
            self.port = data.get('port') # 本地监听端口
            self.remote_host: str = data.get('remote_host', '0.0.0.0') # 远程主机
            self.remote_port: int = data.get('remote_port', 80) # 请求远程监听的端口
            self.websocket_id: str = data.get('websocket_id', None)
            self.data_tunnel_mode: str = data.get('data_tunnel_mode', 'reuse')

        def __repr__(self):
            return f'<Payload data={self.data} port={self.port} remote_host={self.remote_host} remote_port={self.remote_port}>'

    def __init__(self, data: dict):
        self.type = PacketType(data['type']) # 数据包类型
        self.data = data.get('data') # 二进制数据
        self.payload = Packet.Payload(data.get('payload', {}))
        self.size = len(data) # 数据包大小
        self.connection_id = data.get('connection_id') # 连接ID

    def __repr__(self):
        return f'<Packet type={self.type} payload={self.payload} data_size={self.size} connection_id={self.connection_id}>'
    
    def json(self):
        return {
            'type': self.type.value,
            'data': self.data,
            'payload': {
                'data': self.payload.data,
                'port': self.payload.port,
                'remote_host': self.payload.remote_host,
                'remote_port': self.payload.remote_port,
                'websocket_id': self.payload.websocket_id,
                'data_tunnel_mode': self.payload.data_tunnel_mode
            },
            'connection_id': self.connection_id
        }