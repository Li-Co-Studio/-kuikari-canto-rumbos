# dispatcher_callbacks.py
# Este es el único DAT que va como "Callbacks DAT" del OSC In DAT en :7000.
# Reenvía cada mensaje a los dos módulos (visual y relay) sin duplicar el
# bind del puerto UDP. Ver MONTAJE.md.

def onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer):
    op('/telar_visual/callbacks').module.onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer)
    op('/relay/callbacks').module.onReceiveOSC(dat, rowIndex, message, bytes, timeStamp, address, args, peer)
    return
