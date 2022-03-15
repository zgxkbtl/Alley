import argparse
from ast import arg
import asyncio
from asyncio import tasks
import json
import logging

# Extranet Address
SERVER_ADDR = ('8.141.175.112', 9876)
# SERVER_ADDR = ('123.57.47.211', 19876)

SEPARATOR = b'\xFF\xFF'
TUNNEL_MAP = {}

logging.basicConfig(level=logging.DEBUG)

def encode_msg(msg):
    if type(msg) == dict:
        return encode_msg(json.dumps(msg))
    if type(msg) == bytes:
        return msg + SEPARATOR
    return msg.encode() + SEPARATOR

def decode_msg(msg: bytes):
    return msg.strip(SEPARATOR).decode()

async def join_pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(2048)
            writer.write(data)
            await writer.drain()
            # print("to", writer.get_extra_info('peername') )
    finally:
        writer.close()

async def start_proxy(tunnel_info: dict, msg: str):
    
    # local net connection
    local_reader, local_writer = await asyncio.open_connection(tunnel_info['local_addr'], tunnel_info['local_port'])
    
    # make pipe
    remote_reader, remote_writer = await asyncio.open_connection(*SERVER_ADDR)
    # 1. hand shake
    data = {
        'type': 'PLUG_IN',
        'payload': {
            "server_id": msg.split()[-1]
        }
    }
    remote_writer.write(encode_msg(data))
    # remote_writer.write(encode_msg('hello'))
    await remote_writer.drain()

    task_list = [
            asyncio.create_task(join_pipe(local_reader, remote_writer)),
            asyncio.create_task(join_pipe(remote_reader, local_writer)),
        ]
    
    await asyncio.wait(task_list)
    logging.info(f"tunnel {data} disconnected")

async def parse_msg(reader: asyncio.StreamReader, writer, tunnel_info):
    tunnel_info = json.loads(tunnel_info)
    try:
        while True:
            data = await reader.readuntil(SEPARATOR)
            data = decode_msg(data)
            if data == 'pong':
                # TODO: record last pong
                continue

            logging.debug(data)
            if data == 'ping':
                writer.write(encode_msg('pong'))
                await writer.drain()
            
            if 'start proxy' in data:
                asyncio.create_task(start_proxy(tunnel_info, data))

    except asyncio.IncompleteReadError as e:
        logging.error(e, exc_info=True)
    finally:
        logging.info("Close the connection")
        writer.close()

async def heart_beat(writer):
    while True:
        writer.write(encode_msg('ping'))
        await writer.drain()
        await asyncio.sleep(10)

async def make_tunnel(message):
    message = json.dumps(message)
    reader, writer = await asyncio.open_connection(*SERVER_ADDR)
    # hand shake
    writer.write(encode_msg(message))
    await writer.drain()
    data = await reader.readuntil(SEPARATOR)
    data = decode_msg(data)
    logging.info(data)

    tasks_list = [
        asyncio.create_task(heart_beat(writer)), # heart beat
        asyncio.create_task(parse_msg(reader, writer, message)) # deal instraction
    ]

    await asyncio.wait(tasks_list)

async def run():
    messages = [
        {
            'type': "CONNECTOR",
            'local_addr':'127.0.0.1',
            'local_port':'3389',
            'remote_addr':'0.0.0.0',
            'remote_port':'21354'
        },
        # {
        #     'local_addr':'www.baidu.com',
        #     'local_port':'80',
        #     'remote_addr':'192.168.3.47',
        #     'remote_port':'21355'
        # },
    ]
    task_list = [asyncio.create_task(make_tunnel(msg)) for msg in messages]
    await asyncio.wait(task_list)

def main():
    asyncio.run(run())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Alley client")
    parser.add_argument('--host', help="Server host(ip)")
    parser.add_argument('--port', help="Server port")
    parser.add_argument('--debug', help="Turn on debug mod", action='store_true')
    args = parser.parse_args()
    if args.host and args.port:
        SERVER_ADDR = (args.host, args.port)
    print(SERVER_ADDR)
    if args.debug: logging.basicConfig(level=logging.DEBUG)
    main()