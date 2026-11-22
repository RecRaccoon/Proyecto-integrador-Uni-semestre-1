#!/usr/bin/env python3
r"""
Blackjack 21 por red (Cliente-Servidor TCP) - Proyecto Integrador Redes de Datos
Integrantes: Eduardo Tituaña, Gabriel Díaz, Stalyn Ojeda

Jugador 1 = servidor (aloja la partida y la Casa). Jugador 2 = cliente (se conecta por LAN).
La Casa no es un jugador humano: la juega el servidor automáticamente.

Uso:
  python3 blackjack.py                              # menú
  python3 blackjack.py local
  python3 blackjack.py servidor [puerto]
  python3 blackjack.py cliente <ip> [puerto]

Protocolo: un objeto JSON (UTF-8) por línea, terminado en "\n", sobre TCP (puerto 5000).
  CONEXION_OK  S->C  {"tipo":"CONEXION_OK"}
  ESTADO       S->C  {"tipo":"ESTADO","estado":"TURNO_J2"|"ESPERA","mano":[..],"puntaje":18,"casa_visible":"7♠"}
  JUGADA       C->S  {"tipo":"JUGADA","accion":"HIT"|"STAND"}
  ERROR        S->C  {"tipo":"ERROR","motivo":"JUGADA_INVALIDA","reintentar":true}
  FIN_RONDA    S->C  {"tipo":"FIN_RONDA","ganador":"J1"|"J2"|"CASA"|"EMPATE","puntajes":{..},"casa":[..],"motivo":""}
  CONTROL      C->S  {"tipo":"CONTROL","accion":"OTRA_RONDA"|"SALIR"}
Licencia: MIT
"""
import json
import random
import socket
import sys
import time

PUERTO = 5000
TIMEOUT_CONEXION = 60  # segundos esperando al Jugador 2
TIMEOUT_JUGADA = 30    # segundos que tiene el Jugador 2 para responder
MAX_INVALIDAS = 3      # entradas inválidas seguidas -> se asume STAND
PALOS = "♠♥♦♣"
VALORES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
NOMBRES = {"J1": "Jugador 1", "J2": "Jugador 2", "CASA": "la Casa"}


# ---------------- Lógica del juego (solo en el servidor) ----------------
def nuevo_mazo():
    mazo = [v + p for p in PALOS for v in VALORES]
    random.shuffle(mazo)
    return mazo


def puntaje(mano):
    """2-10 su número, J/Q/K = 10, As = 11 y baja a 1 mientras te pases de 21."""
    total, ases = 0, 0
    for carta in mano:
        v = carta[:-1]
        if v == "A":
            total += 11
            ases += 1
        elif v in ("J", "Q", "K"):
            total += 10
        else:
            total += int(v)
    while total > 21 and ases:
        total -= 10
        ases -= 1
    return total


def resolver(p1, p2, pc):
    """Gana el mayor puntaje <= 21 entre J1, J2 y la Casa. Si coinciden: EMPATE.
    Si la Casa se pasa, solo se comparan los jugadores."""
    candidatos = {"J1": p1, "J2": p2}
    if pc <= 21:
        candidatos["CASA"] = pc
    mejor = max(candidatos.values())
    ganadores = [k for k, v in candidatos.items() if v == mejor]
    return ganadores[0] if len(ganadores) == 1 else "EMPATE"


# ---------------- Red: JSON delimitado por salto de línea ----------------
class Conexion:
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


# ---------------- Pantalla y entradas (compartidas por servidor y cliente) ----------------
def mostrar_mano(mano, p, casa_visible):
    print("-" * 40)
    print(f"Casa:     {casa_visible}  ??")
    print(f"Tu mano:  {'  '.join(mano)}  [{p}]" + ("  ¡TE PASASTE!" if p > 21 else ""))


def mostrar_resultado(res):
    p = res["puntajes"]
    print("\n" + "=" * 40)
    print(f"Casa: {'  '.join(res['casa'])}  [{p['CASA']}]")
    print(f"Jugador 1: {p['J1']}   Jugador 2: {p['J2']}")
    if res["motivo"]:
        print(res["motivo"])
    if res["ganador"] == "EMPATE":
        print("🤝 Empate")
    else:
        print(f"🏆 Gana {NOMBRES[res['ganador']]}")
    print("=" * 40)


def leer_jugada(max_intentos=None):
    """Pide H o S. Con max_intentos, tras esa cantidad de errores seguidos asume STAND."""
    intentos = 0
    while max_intentos is None or intentos < max_intentos:
        r = input("[H] Pedir carta / [S] Plantarse: ").strip().upper()
        if r in ("H", "HIT"):
            return "HIT"
        if r in ("S", "STAND"):
            return "STAND"
        intentos += 1
        print("Entrada inválida.")
    print(f"{max_intentos} entradas inválidas seguidas: se asume STAND.")
    return "STAND"


def pedir_si_no(msg):
    while True:
        r = input(msg).strip().lower()
        if r in ("s", "si", "sí"):
            return True
        if r in ("n", "no"):
            return False
        print("Responde s o n.")


# ---------------- Jugadores: local (consola) o remoto (socket) ----------------
class Local:
    remoto = False

    def __init__(self, nombre):
        self.nombre = nombre

    def mostrar(self, mano, casa_visible, tu_turno):
        print(f"\n== {self.nombre} ==")
        mostrar_mano(mano, puntaje(mano), casa_visible)

    def pedir_jugada(self, mano, casa_visible):
        self.mostrar(mano, casa_visible, True)
        return leer_jugada(MAX_INVALIDAS)

    def quiere_otra(self):
        return pedir_si_no(f"{self.nombre}: ¿Otra ronda? [s/n]: ")


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


# ---------------- Partida ----------------
def turno(j, mano, casa, mazo):
    """Juega el turno de un jugador. Devuelve 'ok', 'bust' o 'abandono'."""
    try:
        while puntaje(mano) < 21:  # con 21 se planta solo
            if j.pedir_jugada(mano, casa[0]) == "STAND":
                return "ok"
            mano.append(mazo.pop())
        j.mostrar(mano, casa[0], False)  # llegó a 21 o se pasó: muestra la mano final
    except (TimeoutError, ConnectionError):
        return "abandono"
    return "bust" if puntaje(mano) > 21 else "ok"


def jugar_ronda(j1, j2):
    """Juega una ronda. Devuelve False si la partida debe terminar (J2 abandonó)."""
    mazo = nuevo_mazo()
    m1 = [mazo.pop(), mazo.pop()]
    m2 = [mazo.pop(), mazo.pop()]
    casa = [mazo.pop(), mazo.pop()]  # solo casa[0] se muestra; la otra queda oculta
    motivo, abandono = "", False

    if j2.remoto:
        j2.mostrar(m2, casa[0], False)  # el J2 ve sus cartas mientras juega el J1

    if turno(j1, m1, casa, mazo) == "bust":
        ganador, motivo = "J2", "El Jugador 1 se pasó de 21."
    else:
        print("\nTurno del Jugador 2...")
        r2 = turno(j2, m2, casa, mazo)
        if r2 == "bust":
            ganador, motivo = "J1", "El Jugador 2 se pasó de 21."
        elif r2 == "abandono":
            ganador, abandono = "J1", True
            motivo = "El Jugador 2 no respondió a tiempo o se desconectó."
        else:
            while puntaje(casa) < 17:  # la Casa pide hasta llegar a 17
                casa.append(mazo.pop())
            ganador = resolver(puntaje(m1), puntaje(m2), puntaje(casa))

    res = {"ganador": ganador, "motivo": motivo, "casa": casa,
           "puntajes": {"J1": puntaje(m1), "J2": puntaje(m2), "CASA": puntaje(casa)}}
    mostrar_resultado(res)
    if j2.remoto:
        j2.fin_ronda(res)
    return not abandono


def jugar(j1, j2):
    while True:
        if not jugar_ronda(j1, j2):
            return
        r1 = j1.quiere_otra()
        r2 = j2.quiere_otra()
        if not (r1 and r2):
            print("Fin de la partida. ¡Gracias por jugar!")
            return


# ---------------- Modos ----------------
def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # no envía nada, solo elige la interfaz
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def modo_local():
    print("== Modo LOCAL (2 jugadores en este equipo) ==")
    jugar(Local("Jugador 1"), Local("Jugador 2"))


def modo_servidor(puerto):
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


def modo_cliente(host, puerto):
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


def menu():
    while True:
        print("\n=== BLACKJACK 21 ===")
        print("1) Modo local (2 jugadores, mismo equipo)")
        print("2) Multijugador LAN - Jugador 1 (servidor)")
        print("3) Multijugador LAN - Jugador 2 (cliente)")
        op = input("Elige [1/2/3]: ").strip()
        if op == "1":
            return modo_local()
        if op == "2":
            return modo_servidor(PUERTO)
        if op == "3":
            return modo_cliente(None, PUERTO)
        print("Opción inválida.")


def main():
    a = sys.argv[1:]
    try:
        if not a:
            menu()
        elif a[0] == "local":
            modo_local()
        elif a[0] == "servidor":
            modo_servidor(int(a[1]) if len(a) > 1 else PUERTO)
        elif a[0] == "cliente" and len(a) > 1:
            modo_cliente(a[1], int(a[2]) if len(a) > 2 else PUERTO)
        else:
            print(__doc__)
    except (KeyboardInterrupt, EOFError):
        print("\nSaliendo...")


if __name__ == "__main__":
    main()
