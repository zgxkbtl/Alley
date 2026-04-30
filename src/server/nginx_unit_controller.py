import json
import httpx
import os
import asyncio
import secrets
import string

from src.common.log_config import configure_logger

NGINX_UNIT_CONTROL_SOCKET = '/var/run/control.unit.sock'
SERVER_DOMAIN = os.getenv('SERVER_DOMAIN', 'localhost')
MANAGED_PROXY_PORTS: set[int] = set()

# https://www.python-httpx.org/advanced/#usage_1
logger = configure_logger(__name__)


class UnitUnavailable(RuntimeError):
    pass


def _transport():
    if not os.path.exists(NGINX_UNIT_CONTROL_SOCKET):
        raise UnitUnavailable(f'nginx unit control socket not found: {NGINX_UNIT_CONTROL_SOCKET}')
    return httpx.AsyncHTTPTransport(uds=NGINX_UNIT_CONTROL_SOCKET)


async def get_config():
    transport = _transport()
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("http://localhost/config")
        response.raise_for_status()
        return response.json()


async def set_config(config: dict):
    transport = _transport()
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.put("http://localhost/config", json=config)
        response.raise_for_status()

async def set_proxy_config(domain:str, port: int):
    if not domain:
        domain = ''.join(secrets.choice(string.ascii_lowercase) for _ in range(10))

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
    MANAGED_PROXY_PORTS.add(port)
    return f'{domain}.{SERVER_DOMAIN}'

async def flush_proxy_config(tcp_servers: list[asyncio.Server]):
    try:
        config = await get_config()
        if 'routes' not in config:
            return
        routes = config['routes']
        active_ports = {
            listener_socket.getsockname()[1]
            for tcp_server in tcp_servers
            for listener_socket in tcp_server.sockets
        }
        new_routes = []
        for route in routes:
            proxy = route.get('action', {}).get('proxy', '')
            is_inactive_alley_route = any(
                proxy == f'http://127.0.0.1:{port}'
                for port in MANAGED_PROXY_PORTS - active_ports
            )
            if not is_inactive_alley_route:
                new_routes.append(route)
        config['routes'] = new_routes
        await set_config(config)
        MANAGED_PROXY_PORTS.intersection_update(active_ports)
    except UnitUnavailable as e:
        logger.info(e)
    except Exception as e:
        logger.error('Failed to flush nginx unit config: %s', e, exc_info=True)
    

async def main():
    config = await get_config()
    logger.info(config)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
