import asyncio
import json
import functools

async def join_pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(2048)
            writer.write(data)
            await writer.drain()
            # print("to", writer.get_extra_info('peername') )
    finally:
        writer.close()

async def handle_proxy(local_reader, local_writer):
    try:
        remote_reader, remote_writer = await asyncio.open_connection(
            '127.0.0.1', 3389
        )
        
        task_list = [
            asyncio.create_task(join_pipe(remote_reader, local_writer)),
            asyncio.create_task(join_pipe(local_reader, remote_writer)),
        ]
        # print(f'New TCP connection link { local_writer.get_extra_info('peername') !r} to { remote_writer.get_extra_info('peername') !r}')
        done, pending = await asyncio.wait(task_list)
    finally:
        local_writer.close()

class NewController:
    async def Run(self):
        reader, writer = await asyncio.open_connection(
            'splay.luobotou.org', 11451
        )
        self.ControlReader = reader
        self.ControlWriter = writer
        # asyncio.get_event_loop().add_reader(reader.fd, functools.partial(self.ControlConnection, self.ControlReader, self.ControlWriter))
        asyncio.create_task(self.ListeningControl(reader, writer))
        print('New Tunnel')

    async def ListeningControl(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while True:
            datas = b''
            try:
                if not reader.at_eof():
                    data = await reader.readuntil(separator=b"\xFF\xFF")
                    if not data:
                        break
                    datas += data
                    print('Recived from Control:', data)
            except Exception as e:
                print(e)
            finally:
                if len(datas) > 0:
                    datas = datas.strip(b"\xFF\xFF")
                    datas = json.loads(datas.decode())
                    print('Recived from ControlTunnel', datas)
                    CMD = datas['CMD']
                    if CMD == 'StartProxy':
                        remote_addr, remote_port = datas['payload']
                        for i in range(3):
                            try:
                                local_reader, local_writer = await asyncio.open_connection(
                                    remote_addr, remote_port
                                )
                            except OSError as e:
                                print(e, 'retry:', i)
                            else:
                                break
                        print('proxy trunel:', datas)
                        asyncio.create_task(handle_proxy(local_reader, local_writer))
                    if CMD == 'BEAT':
                        writer.write(
                            json.dumps({'CMD':'BEAT'}).encode()
                        )
                        writer.write(b"\xFF\xFF")
                        await writer.drain()

    async def ControlConnection(self, reader, writer, Msg = None):
        if Msg:
            writer.write(Msg)
            await writer.drain()
        else :  
            datas = b''
            try:
                while not reader.at_eof():
                    data = await reader.read(2048)
                    datas += data
            finally:
                datas = json.loads(data.decode())
            print('Recived from ControlTunnel', datas)
            CMD = datas['CMD']
            if CMD == 'StartProxy':
                remote_addr, remote_port = datas['payload']
                local_reader, local_writer = await asyncio.open_connection(
                    remote_addr, remote_port
                )
                asyncio.create_task(handle_proxy(local_reader, local_writer))


async def main():

    # myserver_reader, myserver_writer = await asyncio.open_connection(
    #     'splay.luobotou.org', 8899
    # )

    # server = await asyncio.start_server(
    #     handle_proxy, 'localhost', '11451'
    # )
    await NewController().Run()
    # loop = asyncio.get_event_loop()
    # loop.run_forever()
    # await asyncio.create_task(handle_proxy(myserver_reader, myserver_writer))

    # addr = server.sockets[0].getsockname()
    # print(f'Serving on {addr}')

    # async with server:
    #     await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())