import asyncio, asyncssh, sys
from typing import Optional
from asyncssh.connection import SSHServerConnection
from asyncssh.server import _NewListener, _NewTCPSession

from rich.console import Console, Group
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
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
    width, height, pixwidth, pixheight = await process.get_terminal_size()
    username = process.get_extra_info('username')

    try:
        console = Console(file=stdout_wrapper, width=width, height=height, force_terminal=True)
        console.print('Welcome to Alley!', style='bold')
        with console.screen(style='bold white on black') as screen:
            with Progress(console=console, auto_refresh=False) as progress:
                task = progress.add_task('Alley time lasted...', total=3600)
                for count in range(3600):
                    text = Align.center(Text(f'[blink]Alley for {username} time[/blink]\n{count}'), vertical='middle')
                    progress.update(task, advance=1)
                    screen.update(Panel(Group(text, process)))
                    await asyncio.sleep(1)
    except Exception as e:
        console.print(str(e))

    process.exit(0)


class AlleyServer(asyncssh.SSHServer):
    def connection_made(self, conn: SSHServerConnection) -> None:
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
        return super().connection_requested(dest_host, dest_port, orig_host, orig_port)
    
    def server_requested(self, listen_host: str, listen_port: int) -> MaybeAwait[_NewListener]:
        print(f'Listening for connection {listen_host} on port {listen_port}.')
        return True
    

async def start_server() -> None:
    await asyncssh.create_server(AlleyServer, 'localhost', 8022, server_host_keys=['ssh_host_key'])

loop = asyncio.get_event_loop()

try:
    loop.run_until_complete(start_server())
except (OSError, asyncssh.Error) as exc:
    sys.exit('Error starting server: ' + str(exc))

loop.run_forever()