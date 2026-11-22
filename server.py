"""
server.py - Servidor del juego (Jugador 1) y comunicación por socket.
Protocolo: un objeto JSON (UTF-8) por línea, terminado en "\\n", sobre TCP.
  CONEXION_OK  S->C  {"tipo":"CONEXION_OK"}
  ESTADO       S->C  {"tipo":"ESTADO","estado":"TURNO_J2"|"ESPERA","mano":[..],"puntaje":18,"casa_visible":"7♠"}
  JUGADA       C->S  {"tipo":"JUGADA","accion":"HIT"|"STAND"}
  ERROR        S->C  {"tipo":"ERROR","motivo":"JUGADA_INVALIDA","reintentar":true}
  FIN_RONDA    S->C  {"tipo":"FIN_RONDA","ganador":"J1"|"J2"|"CASA"|"EMPATE","puntajes":{..},"casa":[..],"motivo":""}
  CONTROL      C->S  {"tipo":"CONTROL","accion":"OTRA_RONDA"|"SALIR"}
Licencia: MIT
"""
import json
import socket

from game_logic import (PUERTO, TIMEOUT_CONEXION, TIMEOUT_JUGADA, MAX_INVALIDAS,
                        Local, jugar, pedir_si_no, puntaje)


# ---------------- Red: JSON delimitado por salto de línea ----------------
class Conexion:
    """Envoltorio sobre un socket TCP. Lo usan servidor y cliente."""

    def __init__(self, sock):
        self.sock = sock
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b""

    def enviar(self, obj):
        datos = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            self.sock.sendall(datos)
        except OSError:
            raise ConnectionError("Se perdió la conexión.")

    def recibir(self, timeout=None):
        """Devuelve un dict. TimeoutError si expira, ConnectionError si se cae,
        ValueError si el mensaje no es un JSON válido."""
        self.sock.settimeout(timeout)
        while b"\n" not in self.buf:
            try:
                datos = self.sock.recv(4096)
            except socket.timeout:
                raise TimeoutError("Tiempo de espera agotado.")
            except OSError:
                raise ConnectionError("Se perdió la conexión.")
            if not datos:
                raise ConnectionError("La otra parte cerró la conexión (fin de la partida).")
            self.buf += datos
        linea, self.buf = self.buf.split(b"\n", 1)
        try:
            msg = json.loads(linea.decode("utf-8"))
        except ValueError:  # incluye UnicodeDecodeError y JSONDecodeError
            raise ValueError("JSON inválido")
        if not isinstance(msg, dict):
            raise ValueError("JSON inválido")
        return msg

    def cerrar(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------- Jugador remoto (Jugador 2 visto desde el servidor) ----------------
class Remoto:
    remoto = True

    def __init__(self, conn):
        self.nombre = "Jugador 2"
        self.conn = conn

    def mostrar(self, mano, casa_visible, tu_turno):
        self.conn.enviar({"tipo": "ESTADO", "estado": "TURNO_J2" if tu_turno else "ESPERA",
                          "mano": mano, "puntaje": puntaje(mano), "casa_visible": casa_visible})

    def pedir_jugada(self, mano, casa_visible):
        """Espera la jugada (30 s). Timeout/desconexión se propagan como excepción."""
        self.mostrar(mano, casa_visible, True)
        for intento in range(1, MAX_INVALIDAS + 1):
            try:
                msg = self.conn.recibir(TIMEOUT_JUGADA)
                if msg.get("tipo") == "JUGADA" and msg.get("accion") in ("HIT", "STAND"):
                    return msg["accion"]
            except ValueError:
                pass  # JSON inválido
            self.conn.enviar({"tipo": "ERROR", "motivo": "JUGADA_INVALIDA",
                              "reintentar": intento < MAX_INVALIDAS})
        return "STAND"  # 3 entradas inválidas seguidas

    def fin_ronda(self, res):
        try:
            self.conn.enviar(dict(res, tipo="FIN_RONDA"))
        except ConnectionError:
            pass  # el jugador ya no está

    def quiere_otra(self):
        try:
            msg = self.conn.recibir(TIMEOUT_JUGADA)
            return msg.get("tipo") == "CONTROL" and msg.get("accion") == "OTRA_RONDA"
        except (TimeoutError, ConnectionError, ValueError):
            return False

    def cerrar(self):
        self.conn.cerrar()


# ---------------- Modo servidor ----------------
def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no envía nada, solo elige la interfaz
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def modo_servidor(puerto=PUERTO):
    while True:  # bind: si el puerto está ocupado se propone otro
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("0.0.0.0", puerto))
            srv.listen(1)
            break
        except OSError as e:
            srv.close()
            print(f"No se pudo abrir el puerto {puerto}: {e}")
            nuevo = input("Otro puerto (Enter para cancelar): ").strip()
            if not nuevo.isdigit():
                return
            puerto = int(nuevo)

    print(f"== SERVIDOR (Jugador 1) ==\nIP: {ip_local()}   Puerto: {puerto}")
    srv.settimeout(TIMEOUT_CONEXION)
    while True:  # accept con timeout de 60 s y opción de reintentar
        print(f"Esperando al Jugador 2 (máx. {TIMEOUT_CONEXION} s)...")
        try:
            sock, addr = srv.accept()
            break
        except socket.timeout:
            if not pedir_si_no("Nadie se conectó. ¿Reintentar? [s/n]: "):
                srv.close()
                return
    srv.close()

    print(f"Jugador 2 conectado por LAN desde {addr[0]}")
    j2 = Remoto(Conexion(sock))
    try:
        j2.conn.enviar({"tipo": "CONEXION_OK"})
        jugar(Local("Jugador 1"), j2)
    except ConnectionError as e:
        print(f"\n[!] {e} La partida terminó.")
    finally:
        j2.cerrar()


if __name__ == "__main__":
    import sys
    modo_servidor(int(sys.argv[1]) if len(sys.argv) > 1 else PUERTO)
