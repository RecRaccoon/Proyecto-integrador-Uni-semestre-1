#!/usr/bin/env python3
"""
juego.py - Punto de entrada: menú y modo local.
Blackjack 21 por red (Cliente-Servidor TCP) - Proyecto Integrador Redes de Datos
Integrantes: Eduardo Tituaña, Gabriel Díaz, Stalyn Ojeda

Uso:
  python3 juego.py                         # menú
  python3 juego.py local
  python3 juego.py servidor [puerto]
  python3 juego.py cliente <ip> [puerto]
Licencia: MIT
"""
import sys

from game_logic import PUERTO, Local, jugar
from server import modo_servidor
from client import modo_cliente


def modo_local():
    print("== Modo LOCAL (2 jugadores en este equipo) ==")
    jugar(Local("Jugador 1"), Local("Jugador 2"))


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
