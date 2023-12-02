import json
import httpx
import os
import asyncio

from src.common.log_config import configure_logger

NGINX_UNIT_CONTROL_SOCKET = '/var/run/control.unit.sock'
SERVER_DOMAIN = os.getenv('SERVER_DOMAIN', 'localhost')

# https://www.python-httpx.org/advanced/#usage_1
logger = configure_logger(__name__)


async def get_config():
    transport = httpx.AsyncHTTPTransport(uds=NGINX_UNIT_CONTROL_SOCKET)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("http://localhost/config")
        print(response.status_code)
        print(response.text)
        return response.json()


async def set_config(config: json):
    transport = httpx.AsyncHTTPTransport(uds=NGINX_UNIT_CONTROL_SOCKET)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.put("http://localhost/config", json=config)
        print(response.status_code)
        print(response.text)

async def set_proxy_config(domain:str, port: int):
    if not domain:
        # random domain only contains letters
        import random
        import string
        domain = ''.join(random.choices(string.ascii_lowercase, k=10))

    config = await get_config()
    if 'listeners' not in config:
        config['listeners'] = {
            "*:80": {
                "pass": "routes"
            }
        }
    if 'routes' not in config:
        config['routes'] = []
    config['routes'].append({
        "match": {
            "host": f'{domain}.{SERVER_DOMAIN}',
            "uri": "/*"
        },

        "action": {
            "proxy": f"http://127.0.0.1:{port}"
        }
    })
    await set_config(config)
    return f'{domain}.{SERVER_DOMAIN}'

async def flush_proxy_config(tcp_servers: list[asyncio.Server]):
    try:
        config = await get_config()
        if 'routes' not in config:
            return
        routes = config['routes']
        for tcp_server in tcp_servers:
            for socket in tcp_server.sockets:
                for route in routes:
                    if route['action']['proxy'].endswith(str(socket.getsockname()[1])):
                        routes.remove(route)
        await set_config(config)
    except Exception as e:
        logger.error(e)
    

async def main():
    async with httpx.AsyncClient(uds=NGINX_UNIT_CONTROL_SOCKET) as client:
        response = await client.get("http://localhost")
        print(response.status_code)
        print(response.text)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
