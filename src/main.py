import asyncio, asyncssh, sys
from time import time
from typing import Optional
from asyncssh.connection import SSHServerConnection
from asyncssh.server import _NewListener, _NewTCPSession

from rich.console import Console, Group
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn, TimeElapsedColumn

from asyncssh.misc import MaybeAwait

async def handle_client(process: asyncssh.SSHServerProcess) -> None:
    class SSHWriterWrapper:
        def __init__(self, writer: asyncssh.SSHWriter) -> None:
            self.writer = writer
        
        def write(self, data: bytes) -> None:
            return self.writer.write(data)

        def flush(self) -> None:
            # SSHWriter doesn't have a flush method
            pass
    
    stdout_wrapper = SSHWriterWrapper(process.stdout)
    width, height, pixwidth, pixheight = process.get_terminal_size()
    username = process.get_extra_info('username')
    console = Console(file=stdout_wrapper, width=width, height=height, force_terminal=True)
    
    time_progress = Progress(BarColumn(), console=console, )
    time_task = time_progress.add_task('Time Usage', total=3600)
    start_time = time()

    table = Table(title="Alley Help", show_header=True, header_style="bold magenta")
    table.add_column("Command", justify="right", style="cyan", no_wrap=True)
    table.add_column("Description", justify="right", style="green")
    table.add_row("exit", "Exit Alley")
    table.add_row("usage", "Show usage of Alley")
    table.add_row("help", "Show this help message")
    table.add_row("clear", "Clear the screen")
    table.add_row("getport", "Get the port of the server")

    async def monitor_stdin() -> None:
        try:
            while True:
                try:
                    async for line in process.stdin:
                        line = line.rstrip('\n')
                        if line == 'exit':
                            raise asyncssh.BreakReceived(1)
                        elif line == 'usage':
                            console.print(Text.from_markup(f'\n[blink]Alley for [i]{username}[/i][/blink]', justify='center'))
                            console.print(Text.from_markup(f'\n[i]Time Elapsed: {(time() - start_time)}[/i]', justify='center'))
                            time_progress.update(time_task, advance=(time() - start_time))
                            console.print(time_progress)

                        elif line == 'clear':
                            console.clear()

                        elif line == 'getport':
                            console.print(process.get_extra_info('getport'))

                        elif line == 'help':
                            console.print(table)

                except asyncssh.BreakReceived as e:
                    raise e
                except asyncssh.TerminalSizeChanged:
                    pass
        except Exception as e:
            process.stderr.write(f'Error: {e}')
            print(e)

    try:
        await monitor_stdin()
    except Exception as e:
        print(e)
        process.stderr.write(f'Error: {e}')

    process.exit(0)


class AlleyServer(asyncssh.SSHServer):
    def connection_made(self, conn: SSHServerConnection) -> None:
        self._conn = conn
        print('Connection received from %s.' % conn.get_extra_info('peername')[0])

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            print('Connection lost with exception: ' + str(exc), file=sys.stderr)
        else:
            print('Connection closed.')

    def begin_auth(self, username: str) -> MaybeAwait[bool]:
        return True

    def password_auth_supported(self) -> bool:
        return True
    
    def validate_password(self, username: str, password: str) -> MaybeAwait[bool]:
        return username == 'guest'
    
    def connection_requested(self, dest_host: str, dest_port: int, orig_host: str, orig_port: int) -> _NewTCPSession:
        return True
    
    async def server_requested(self, listen_host: str, listen_port: int) -> MaybeAwait[_NewListener]:
        listener = await self._conn.forward_local_port('', listen_port, listen_host, listen_port)
        print('Listening on port %s for connections to port %s.' % (listener.get_port(), listen_port))
        self._conn.set_extra_info(getport=listener.get_port())
        return listener
    

async def start_server() -> None:
    await asyncssh.create_server(AlleyServer, '', 8022, server_host_keys=['ssh_host_key'], process_factory=handle_client)

loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(start_server())
except (OSError, asyncssh.Error) as exc:
    sys.exit('Error starting server: ' + str(exc))

loop.run_forever()