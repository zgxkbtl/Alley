import argparse
import asyncio
import json
import logging
import functools
from random import randint

# Extranet Address
SERVER_ADDR = ('0.0.0.0', 9876)
SEPARATOR = b'\xFF\xFF'
TUNNEL_MAP = {}

logging.basicConfig(level=logging.DEBUG)

def encode_msg(msg):
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

async def make_pipe(pipe_reader: asyncio.StreamReader, pipe_writer: asyncio.StreamWriter, message : dict):
    # parse msg
    if not message:
        logging.error(f"No pipe make message")
        return
    
    logging.info(f"make pipe for {message}")
    payload = message['payload']
    server_id = int(payload['server_id'])
    endpoint_reader, endpoint_writer = TUNNEL_MAP[server_id]

    # make pipe
    task_list = [
            asyncio.create_task(join_pipe(pipe_reader, endpoint_writer)),
            asyncio.create_task(join_pipe(endpoint_reader, pipe_writer)),
        ]
    
    await asyncio.wait(task_list)
    logging.info("pipe %d disconnected", server_id)




async def make_endpoint(tunnel_server_id, 
                    tunnel_reader: asyncio.StreamReader, tunnel_writer: asyncio.StreamWriter, 
                    endpoint_reader: asyncio.StreamReader, endpoint_writer: asyncio.StreamWriter):
    server_id = randint(0, 19260817)
    TUNNEL_MAP[server_id] = (endpoint_reader, endpoint_writer)

    endpoint_addr = endpoint_writer.get_extra_info('peername')
    tunnel_addr = tunnel_writer.get_extra_info('peername')
    logging.info(f"serving endpoint {endpoint_addr}, current tunnel is {tunnel_addr}")
    # if endpoint_addr[0] == tunnel_addr[0]:
    #     return await make_pipe(endpoint_reader, endpoint_writer)

    server_id = randint(0, 19260817)
    TUNNEL_MAP[server_id] = (endpoint_reader, endpoint_writer)
    
    tunnel_writer.write(encode_msg(f'start proxy at {server_id}'))
    await tunnel_writer.drain()


async def make_endpoint_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                server_id, message, data):
    # TODO: try Exception send to client
    tunnel_server = await asyncio.start_server(
        functools.partial(make_endpoint, server_id, reader, writer), message['remote_addr'], message['remote_port'])
    await tunnel_server.start_serving()
    logging.info(f"listening endpoint on : {(message['remote_addr'], message['remote_port'])!r}")
    writer.write(data)
    await writer.drain()

    # hreat_beat
    try:
        while True:
            data = await reader.readuntil(SEPARATOR)
            data = decode_msg(data)
            if data == 'heart beat':
                writer.write(encode_msg(data))
                await writer.drain()
            logging.info(data)
    except asyncio.IncompleteReadError as e:
        logging.error(e, exc_info=True)
    finally:
        logging.info("Close the connection")
        writer.close()
        tunnel_server.close()


async def make_tunnel(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    # hand shake
    data = await reader.readuntil(SEPARATOR)
    message = data.strip(SEPARATOR).decode()
    addr = writer.get_extra_info('peername')

    logging.info("%s", f"Received {message!r} from {addr!r}")

    message = json.loads(message)

    # make a tunnel persistence
    server_id = randint(0, 19260817)
    TUNNEL_MAP[server_id] = (reader, writer)

    # parse msg
    logging.info(decode_msg(data))
    msg_type = message['type']
    
    if msg_type == 'PLUG_IN':
        return await make_pipe(reader, writer, message)
    if msg_type == 'CONNECTOR':
        return await make_endpoint_server(reader, writer, server_id, message, data)

async def run():
    my_server = await asyncio.start_server(make_tunnel, *SERVER_ADDR)
    await my_server.serve_forever()

def main():
    asyncio.run(run())

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Alley server")
    parser.add_argument('--host', default='0.0.0.0', help="Server host(ip)")
    parser.add_argument('--port', default='9876', help="Server port")
    parser.add_argument('--debug', help="Turn on debug mod", action='store_true')
    args = parser.parse_args()
    SERVER_ADDR = (args.host, args.port)
    logging.info("Alley server listening on {}".format(SERVER_ADDR))
    main()

