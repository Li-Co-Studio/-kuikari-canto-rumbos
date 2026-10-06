# manda_osc.py
# Manda un mensaje Open Sound Control suelto a TouchDesigner (puerto 7000).
# Uso: python src\manda_osc.py /paneo/manual 90
import sys
from pythonosc.udp_client import SimpleUDPClient

direccion, *valores = sys.argv[1:]

def convertir(v):
    try:
        return float(v)
    except ValueError:
        return v

SimpleUDPClient("127.0.0.1", 7000).send_message(direccion, [convertir(v) for v in valores])
print("enviado", direccion, valores)