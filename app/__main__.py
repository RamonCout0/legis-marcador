"""Inicia o programa e abre o navegador padrao sozinho:  python -m app"""
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

HOST, PORTA = "127.0.0.1", 8765
URL = f"http://localhost:{PORTA}"


def _porta_aberta() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORTA)) == 0


def _abrir_quando_pronto():
    for _ in range(60):  # espera o servidor responder (ate ~15 s)
        if _porta_aberta():
            webbrowser.open(URL)
            return
        time.sleep(0.25)


if __name__ == "__main__":
    if _porta_aberta():
        print("O Legis Marcador já está aberto. Abrindo o navegador...")
        webbrowser.open(URL)
        sys.exit(0)
    threading.Thread(target=_abrir_quando_pronto, daemon=True).start()
    uvicorn.run("app.server:app", host=HOST, port=PORTA, log_level="warning")
