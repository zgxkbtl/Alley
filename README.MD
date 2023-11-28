# Alley - 内网穿透工具

![Alley Logo](https://github.com/your_username/your_repository/raw/main/logo.png)

Alley 是一个使用纯 Python 实现的内网穿透工具，提供了服务端和客户端两个组件，帮助您将内网环境的资源暴露成外部网络资源。

## 特性

- 快速简单的设置，无需复杂的配置
- 支持多种协议，包括 HTTP、TCP、UDP
- 安全可靠的数据传输，使用加密算法保护数据
- 支持自定义域名和端口映射
- 跨平台支持，可以在 Windows、Linux 和 macOS 上运行

## 安装

首先，确保您已经安装了 Python 3.8 或更高版本

1. 克隆此仓库到您的本地机器：

```bash
git clone https://github.com/zgxkbtl/Alley.git
```

2. 进入项目目录：

```bash
cd Alley
```

3. 安装依赖：

```bash
pip install -r requirements.txt
```

## 使用

### 服务端

1. 在您的服务器上运行以下命令启动服务端：

```bash
python -m src.server.server
```

2. 服务端将会监听默认端口 8765，您可以通过 `--port` 参数指定端口号。

### 客户端

1. 在您的客户端上运行以下命令启动客户端：

```bash
python -m src.client.client <port> --hostport <host>:<port>
```

2. 客户端将会连接到指定的服务端，并在本地启动一个代理服务器，代理本地的 `<port>` 端口。

## 示例

以下是一个使用 Alley 的示例：

```python
import requests

response = requests.get("http://localhost:8000")
print(response.text)
```

## 贡献

欢迎贡献代码和提出问题！请阅读 [贡献指南](CONTRIBUTING.md) 获取更多信息。

## 许可证

本项目基于 MIT 许可证。请阅读 [许可证文件](LICENSE) 获取更多信息。
