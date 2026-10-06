# escucha_osc.py
# Imprime todo lo que llega por Open Sound Control a un puerto.
# Uso: python -u src\escucha_osc.py 7010
import sys
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 7010
d = Dispatcher()
d.set_default_handler(lambda addr, *args: print(f"{addr:<16} {args}"))
print(f"Escuchando en 127.0.0.1:{puerto} (Ctrl+C para salir)")
BlockingOSCUDPServer(("127.0.0.1", puerto), d).serve_forever()
