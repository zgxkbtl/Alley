import json
import httpx

NGINX_UNIT_CONTROL_SOCKET = '/var/run/control.unit.sock'
# https://www.python-httpx.org/advanced/#usage_1

async def get_config():
    transport = httpx.AsyncHTTPTransport(uds=NGINX_UNIT_CONTROL_SOCKET)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("http://localhost/config")
        print(response.status_code)
        print(response.text)


async def set_config(config: json):
    transport = httpx.AsyncHTTPTransport(uds=NGINX_UNIT_CONTROL_SOCKET)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.put("http://localhost/config", json=config)
        print(response.status_code)
        print(response.text)

async def set_proxy_config(port: int):
    config = {
        "listeners": {
            "*:80": {
                "pass": "routes"
            }
        },
        "routes": [
            {
            "match": {
                "host": "test.nn.luobotou.org",
                "uri": "/*"
            },

            "action": {
                "proxy": f"http://127.0.0.1:{port}/*"
            }
        }
        ]
    }
    await set_config(config)


async def main():
    async with httpx.AsyncClient(uds=NGINX_UNIT_CONTROL_SOCKET) as client:
        response = await client.get("http://localhost")
        print(response.status_code)
        print(response.text)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
