"""
game_logic.py - Lógica del juego + interfaz de consola (modo local).
Blackjack 21 por red - Proyecto Integrador Redes de Datos
Integrantes: Eduardo Tituaña, Gabriel Díaz, Stalyn Ojeda
Licencia: MIT
"""
import random

PUERTO = 5000
TIMEOUT_CONEXION = 60  # segundos esperando al Jugador 2
TIMEOUT_JUGADA = 30    # segundos que tiene el Jugador 2 para responder
MAX_INVALIDAS = 3      # entradas inválidas seguidas -> se asume STAND
PALOS = "♠♥♦♣"
VALORES = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
NOMBRES = {"J1": "Jugador 1", "J2": "Jugador 2", "CASA": "la Casa"}


# ---------------- Reglas ----------------
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


# ---------------- Interfaz de consola ----------------
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


class Local:
    """Jugador que juega por consola en este mismo equipo."""
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
