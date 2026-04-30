# Alley

Alley 是一个极简 Python 内网穿透工具：服务端开放远端端口，客户端把流量转发到本地服务。

## 安装

需要 Python 3.10+ 和 uv。

```bash
git clone https://github.com/zgxkbtl/Alley.git
cd Alley
uv sync
```

## TCP 转发

服务端：

```bash
uv run alley-server --host 0.0.0.0 --port 8765
```

客户端把本地 `127.0.0.1:8000` 暴露到服务端 `0.0.0.0:9000`：

```bash
uv run alley-client 8000 --target_host 127.0.0.1 --schema tcp --hostport example.com:8765 --remote_port 9000
```

然后访问 `example.com:9000` 即可连接到客户端本地服务。

## HTTP 域名转发

HTTP 模式依赖服务端安装 nginx unit，并通过 `/var/run/control.unit.sock` 控制配置：

```bash
export SERVER_DOMAIN=example.com
uv run alley-client 8000 --schema http --hostport example.com:8765 --domain app
```

成功后可访问 `http://app.example.com`。如果服务端没有 nginx unit，Alley 会保留 TCP 转发并提示直接使用远端端口。

## 零依赖单文件版

`standalone/` 目录只包含 `server.py` 和 `client.py`，可直接复制到只有 Python 3 的机器上运行，适合临时 TCP 转发：

```bash
python3 server.py --host 0.0.0.0 --port 8765
python3 client.py 8000 --target_host 127.0.0.1 --hostport example.com:8765 --remote_port 9000
```

这个版本不包含 HTTP 域名转发；大流量全双工场景建议边写边读，避免“先一次性写完再读取”触发系统回压。

## 许可证

MIT
