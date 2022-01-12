import asyncio
from asyncio import tasks
from asyncio.streams import start_server
import json
import logging
import functools
from os import read
from random import randint

SERVER_ADDR = ('192.168.3.47', 9876)
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
    remote_reader, remote_writer = await asyncio.open_connection(tunnel_info['remote_addr'], tunnel_info['remote_port'])
    # 1. hand shake
    data = {
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
            logging.info(data)
            if 'start proxy' in data:
                asyncio.create_task(start_proxy(tunnel_info, data))

    except asyncio.IncompleteReadError as e:
        logging.error(e, exc_info=True)
    finally:
        logging.info("Close the connection")
        writer.close()

async def heart_beat(writer):
    while True:
        writer.write(encode_msg('heart beat'))
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

def main():
    message = {
        'local_addr':'splay.luobotou.org',
        'local_port':'5000',
        'remote_addr':'192.168.3.47',
        'remote_port':'21354'
    }
    asyncio.run(make_tunnel(message))

main()