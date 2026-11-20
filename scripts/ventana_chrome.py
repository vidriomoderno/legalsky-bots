"""Pone delante la ventana de Chrome (o la minimiza, para pruebas).

Windows deja de pintar una ventana de Chrome minimizada o tapada del todo (por ejemplo por
la consola del bot maximizada) y entonces la captura de pantalla de Claude in Chrome se
queda colgada. Antes de cada captura la skill ejecuta:

    python scripts/ventana_chrome.py delante [TEXTO_DEL_TITULO]

que restaura y pone encima la ventana de Chrome cuyo título contiene TEXTO (p. ej.
"FlightStats"); si no hay ninguna, todas las ventanas de Chrome visibles.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

SW_RESTORE, SW_MINIMIZE, SW_SHOWMAXIMIZED = 9, 6, 3
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40


def ventanas_chrome() -> list[tuple[int, str]]:
    u = ctypes.windll.user32
    res: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cada(hwnd, _):
        clase = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(hwnd, clase, 64)
        if clase.value != "Chrome_WidgetWin_1" or not u.IsWindowVisible(hwnd):
            return True
        n = u.GetWindowTextLengthW(hwnd)
        titulo = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, titulo, n + 1)
        if titulo.value.endswith("Google Chrome"):
            res.append((hwnd, titulo.value))
        return True

    u.EnumWindows(cada, 0)
    return res


def poner_delante(hwnd: int) -> None:
    u = ctypes.windll.user32
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, SW_RESTORE)
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW
    u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    u.SetForegroundWindow(hwnd)


def main(argv: list[str]) -> None:
    orden = argv[0] if argv else "delante"
    texto = " ".join(argv[1:]).lower()
    todas = ventanas_chrome()
    elegidas = [v for v in todas if texto and texto in v[1].lower()] or todas
    for hwnd, titulo in elegidas:
        if orden == "minimizar":
            ctypes.windll.user32.ShowWindow(hwnd, SW_MINIMIZE)
        else:
            poner_delante(hwnd)
        print(f"{orden}: {titulo}")
    if not elegidas:
        print("No hay ninguna ventana de Chrome abierta.")


if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("Solo para Windows.")
    sys.stdout.reconfigure(errors="replace")
    main(sys.argv[1:])
