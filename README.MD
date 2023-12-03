# Alley - 内网穿透工具

![Alley Logo](https://github.com/your_username/your_repository/raw/main/logo.png)

Alley 是一个使用纯 Python 实现的内网穿透工具，提供了服务端和客户端两个组件，帮助您将内网环境的资源暴露成外部网络资源。

## 特性

- [x] 快速简单的设置，无需复杂的配置
- [ ] 支持多种协议，包括 HTTP、TCP、~~UDP~~
- [ ] 安全可靠的数据传输，使用加密算法保护数据
- [x] 支持自定义域名和端口映射
- [x] 跨平台支持，可以在 Windows、Linux 和 macOS 上运行

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

4. 安装 nginx unit：(可选)

参考 [nginx unit 安装指南](https://unit.nginx.org/installation/) 安装 nginx unit，然后（可选）将环境变量 `SERVER_DOMAIN` 设置为您的 nginx unit 的域名。

```bash
export SERVER_DOMAIN=example.com
```


## 使用

### 服务端

1. 在您的服务器上运行以下命令启动服务端：

```bash
export SERVER_DOMAIN=example.com

python -m src.server.server
```

2. 服务端将会监听默认端口 8765，您可以通过 `--port` 参数指定端口号。

### 客户端

1. 在您的客户端上运行以下命令启动客户端：

```bash
python -m src.client.client 33089 --hostport example.com:8765
```

2. 客户端将会连接到指定的服务端`example.com`，并在本地启动一个代理服务器，代理本地的 `33089` 端口。默认会认为服务是一个 HTTP 服务，服务器会自动分配一个子域名，您可以通过 `--remote_host`， `--remote_port` 参数指定您的域名和端口。

3. 如果一切运行正常，在控制台中您将会看到以下输出：

```bash
12-03 02:32:03 - __main__:client.py:82 - INFO - Received message: NOTIFICATION: New TCP server example.com:45961 ---> 33089
12-03 02:32:03 - __main__:client.py:82 - INFO - Received message: NOTIFICATION: Proxy config set for http://gvcewvoksx.example.com ---> 33089

```

4. 您可以通过访问 `http://gvcewvoksx.example.com` 来访问您的本地服务。

5. 如果您需要直接转发端口，您可以使用 `--schema tcp` 参数，例如：

```bash
python -m src.client.client 8888 --hostport example.com:8000 --schema tcp
```
然后您可以通过控制台信息访问类似 `example.com:45961` 来访问您的本地服务。


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
