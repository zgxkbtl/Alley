import asyncio
import functools
import json

class Controller:
    
    async def init(self, reader, writer):
        self.ControlReader = reader
        self.ControlWriter = writer
        # asyncio.get_event_loop().add_reader(reader.fd, functools.partial(self.ControlConnection, self.ControlReader, self.ControlWriter))
        asyncio.create_task(self.ListeningControl(reader))
        asyncio.create_task(self.heartbeat(reader, writer))

    async def ListeningControl(self, reader: asyncio.StreamReader):
        while True:
            # await asyncio.sleep(3)
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
                return

    async def heartbeat(self, reader, writer):
        while True:
            try:
                writer.write(json.dumps({'CMD':'BEAT'}).encode())
                writer.write(b"\xFF\xFF")
                print('Sent BEAT')
                await writer.drain()
                await asyncio.sleep(5)
            except ConnectionResetError as e:
                print(e)
                return
        
    async def ControlConnection(self, reader, writer : asyncio.StreamWriter, Msg = None):
        print('Ready to send', Msg)
        try:
            if Msg:
                writer.write(Msg)
                writer.write(b"\xFF\xFF")
                await writer.drain()
            else :  
                print('Empty CMD')
        except Exception as e:
            print(e)            

C = Controller()

async def join_pipe(reader, writer):
    try:
        while not reader.at_eof():
            data = await reader.read(2048)
            writer.write(data)
            await writer.drain()
            # print("to", writer.get_extra_info('peername') )
    finally:
        writer.close()

async def server_pipe(local_reader, local_writer, remote_reader, remote_writer):
    try:
        task_list = [
            asyncio.create_task(join_pipe(remote_reader, local_writer)),
            asyncio.create_task(join_pipe(local_reader, remote_writer)),
        ]
        print('New HTTP connection link ', local_writer.get_extra_info("peername") ,' to ', remote_writer.get_extra_info("peername"))
        done, pending = await asyncio.wait(task_list)
    except Exception as e:
        # local_writer.close()
        print(e)


async def handle_http_client(local_reader, local_writer):
    print('Detect new HTTP request from', local_writer.get_extra_info('peername'))
    
    try:
        server = await asyncio.start_server(
            functools.partial(server_pipe, local_reader, local_writer), '172.17.27.87', ''
        )
        print('New proxy port on', server.sockets[0].getsockname())
        addr_port = ('splay.luobotou.org', server.sockets[0].getsockname()[1])
        await C.ControlConnection(C.ControlReader, C.ControlWriter, json.dumps(
            {'CMD':'StartProxy', 'payload': addr_port}
        ).encode())
        await asyncio.sleep(10)
        await server.wait_closed()
        # print(f'New tunnle connection', addr)
        # done, pending = await asyncio.wait(task_list)
    except Exception as e:
        # local_writer.close()
        # print(f'New tunnle connection', addr)
        print(e)




async def NewControl(reader : asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        await C.init(reader, writer)
        print('New Control Tunnel:', writer.get_extra_info('peername'))
    except Exception as e:
        print(e)
        # writer.close()
        

async def main():
    server_http = await asyncio.start_server(
        handle_http_client, '172.17.27.87', '8899'
    )
    
    addr = server_http.sockets[0].getsockname()
    print(f'Listening for public http connections on {addr}')

    tunnelListenler = await asyncio.start_server(
        NewControl , '172.17.27.87', '11451'
    )
    
    addr = tunnelListenler.sockets[0].getsockname()
    print(f'Listening for control and proxy connections on {addr}')

    task_list = [
        asyncio.create_task(server_http.serve_forever()),
        asyncio.create_task(tunnelListenler.serve_forever())
    ]

    done, pending = await asyncio.wait(task_list)

if __name__ == "__main__":
    asyncio.run(main())