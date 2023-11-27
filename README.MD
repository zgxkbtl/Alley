reverse_proxy/
│
├── server/
│   ├── __init__.py
│   ├── server.py            # 公网服务器WebSocket代码
│   ├── tcp_handler.py       # TCP端口转发处理代码
│   └── connection_manager.py # 管理WebSocket连接和端口转发
│
├── client/
│   ├── __init__.py
│   └── client.py            # 内网客户端代码
│
└── common/
    ├── __init__.py
    └── utils.py             # 共用的工具函数
