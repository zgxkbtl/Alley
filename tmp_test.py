import json
import asyncio

STREAM_SEPARATOR = b'\xFF\xFF'

async def f(w):
    w.write('hello'.encode())

async def tcp_echo_client(message):
    reader, writer = await asyncio.open_connection(
        '127.0.0.1', 9876)

    print(f'Send: {message!r}')
    writer.write(message.encode() + STREAM_SEPARATOR)

    data = await reader.read(100)
    print(f'Received: {data.strip(STREAM_SEPARATOR).decode()!r}')

    writer.write("heart_beat".encode() + STREAM_SEPARATOR)
    await asyncio.sleep(5)
    writer.write("heart_beat".encode() + STREAM_SEPARATOR)
    await asyncio.sleep(5)
    r, w = await asyncio.open_connection('127.0.0.1', 21354)
    asyncio.create_task(f(w))
    await asyncio.sleep(5)

    print('Close the connection')
    writer.close()

def main():
    message = {
        'local_addr':'127.0.0.1',
        'local_port':'11451',
        'remote_addr':'127.0.0.1',
        'remote_port':'21354'
    }
    asyncio.run(tcp_echo_client(json.dumps(message)))

main()