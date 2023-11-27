from enum import Enum


class PacketType(Enum):
    # Client -> Server
    TCP_LISTEN = 'tcp_listen'
    TCP_DATA = 'tcp_data'
    TCP_CLOSE = 'tcp_close'
    # Server -> Client
    NEW_CONNECTION = 'new_connection'



class Packet:

    class Payload:
        def __init__(self, data):
            self.data = data.get('data')
            self.port = data.get('port') # 本地监听端口
            self.remote_host = data.get('remote_host') # 远程主机
            self.remote_port = data.get('remote_port') # 请求远程监听的端口

        def __repr__(self):
            return f'<Payload data={self.data} connection_id={self.connection_id}>'

    def __init__(self, data):
        self.type = PacketType(data['type']) # 数据包类型
        self.data = data.get('data') # 二进制数据
        self.payload = Packet.Payload(data.get('payload')) # 附加数据
        self.size = len(data) # 数据包大小
        self.connection_id = data.get('connection_id') # 连接ID

    def __repr__(self):
        return f'<Packet type={self.type} payload={self.payload}>'
    
    def json(self):
        return {
            'type': self.type.value,
            'data': self.data,
            'payload': {
                'data': self.payload.data,
                'port': self.payload.port,
                'remote_host': self.payload.remote_host,
                'remote_port': self.payload.remote_port
            },
            'connection_id': self.connection_id
        }