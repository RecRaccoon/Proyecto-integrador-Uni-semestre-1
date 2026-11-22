"""
client.py - Cliente del juego (Jugador 2). Se conecta al servidor por LAN.
Licencia: MIT
"""
import socket
import time

from game_logic import PUERTO, leer_jugada, mostrar_mano, mostrar_resultado, pedir_si_no
from server import Conexion


def modo_cliente(host=None, puerto=PUERTO):
    while True:  # connect: si falla, se puede reintentar con otra IP/puerto
        if not host:
            host = input("IP del servidor: ").strip()
            p = input(f"Puerto [{PUERTO}]: ").strip()
            puerto = int(p) if p.isdigit() else PUERTO
        try:
            sock = socket.create_connection((host, puerto), timeout=10)
            break
        except OSError as e:
            print(f"Servidor no disponible: {e}")
            if not pedir_si_no("¿Reintentar? [s/n]: "):
                return
            host = None

    conn = Conexion(sock)
    enviado = None  # para medir el tiempo de respuesta (debe ser < 1 s)
    try:
        if conn.recibir().get("tipo") != "CONEXION_OK":
            raise ConnectionError("Respuesta inesperada del servidor.")
        print("¡Conectado! Esperando el inicio de la partida...")
        while True:
            msg = conn.recibir()
            if enviado is not None:
                print(f"  (respuesta del servidor en {(time.perf_counter() - enviado) * 1000:.0f} ms)")
                enviado = None
            tipo = msg.get("tipo")
            if tipo == "ESTADO":
                print("\n== Jugador 2 ==")
                mostrar_mano(msg["mano"], msg["puntaje"], msg["casa_visible"])
                if msg["estado"] == "TURNO_J2":
                    conn.enviar({"tipo": "JUGADA", "accion": leer_jugada()})
                    enviado = time.perf_counter()
                else:
                    print("Esperando al otro jugador...")
            elif tipo == "ERROR":
                print("El servidor rechazó la jugada.")
                if msg.get("reintentar"):
                    conn.enviar({"tipo": "JUGADA", "accion": leer_jugada()})
            elif tipo == "FIN_RONDA":
                mostrar_resultado(msg)
                otra = pedir_si_no("¿Otra ronda? [s/n]: ")
                conn.enviar({"tipo": "CONTROL", "accion": "OTRA_RONDA" if otra else "SALIR"})
                if not otra:
                    break
                print("Esperando al otro jugador...")
    except (ConnectionError, TimeoutError, ValueError) as e:
        print(f"\n[!] {e}")
    finally:
        conn.cerrar()


if __name__ == "__main__":
    import sys
    modo_cliente(sys.argv[1] if len(sys.argv) > 1 else None,
                 int(sys.argv[2]) if len(sys.argv) > 2 else PUERTO)
