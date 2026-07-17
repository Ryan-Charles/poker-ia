"""Lanceur natif Windows de Poker IA.

Le serveur FastAPI reste strictement local et la fenêtre WebView n'expose aucune
fonction d'automatisation ou de connexion à une plateforme de poker.
"""

from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn
import webview

HOST = "127.0.0.1"
PREFERRED_PORT = 8765


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _data_root() -> Path:
    configured = os.environ.get("POKER_IA_DATA_DIR")
    if configured:
        return Path(configured)
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Poker IA" / "data"


def _health_is_ready(port: int) -> bool:
    try:
        with urlopen(f"http://{HOST}:{port}/api/health", timeout=0.5) as response:
            payload = json.load(response)
        return payload.get("status") == "ok" and payload.get("fictional_chips_only") is True
    except (OSError, URLError, ValueError, json.JSONDecodeError):
        return False


def _available_port() -> int:
    configured = os.environ.get("POKER_IA_PORT")
    candidates = (
        [int(configured)] if configured else list(range(PREFERRED_PORT, PREFERRED_PORT + 31))
    )
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
            return port
    raise RuntimeError("Aucun port local disponible pour Poker IA.")


def _wait_until_ready(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health_is_ready(port):
            return
        time.sleep(0.1)
    raise RuntimeError("Le serveur local Poker IA n'a pas démarré dans le délai prévu.")


def _serve(port: int) -> None:
    # L'import explicite permet à PyInstaller de suivre tout le graphe backend;
    # une chaîne "app.main:app" seule resterait invisible à son analyse statique.
    from app.main import app as poker_app

    uvicorn.run(poker_app, host=HOST, port=port, log_level="warning", access_log=False)


def _report_startup_failure(error: BaseException) -> None:
    data = _data_root()
    data.mkdir(parents=True, exist_ok=True)
    log_path = data / "poker-ia-launcher.log"
    log_path.write_text(traceback.format_exc(), encoding="utf-8")
    message = f"Poker IA n'a pas pu démarrer.\n\nDétail : {error}\n\nJournal : {log_path}"
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "Poker IA", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> None:
    multiprocessing.freeze_support()
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "PokerIA.Entrainement.Local.1"
        )
    root = _bundle_root()
    data = _data_root()
    data.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("POKER_IA_PROJECT_ROOT", str(root))
    os.environ.setdefault("POKER_IA_FRONTEND_DIST", str(root / "frontend" / "dist"))
    os.environ.setdefault("POKER_IA_DATA_DIR", str(data))

    if not getattr(sys, "frozen", False):
        backend = root / "backend"
        if str(backend) not in sys.path:
            sys.path.insert(0, str(backend))

    port = _available_port()
    server = threading.Thread(target=_serve, args=(port,), name="poker-ia-server", daemon=True)
    server.start()
    _wait_until_ready(port)

    if os.environ.get("POKER_IA_SMOKE_TEST") == "1":
        return

    window = webview.create_window(
        "Poker IA — Entraînement No-Limit Hold'em",
        f"http://{HOST}:{port}",
        width=1500,
        height=960,
        min_size=(1100, 720),
        background_color="#07110f",
        text_select=False,
    )
    webview.start(debug=False, private_mode=False)
    if window:
        window.destroy()


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        _report_startup_failure(error)
        raise SystemExit(1) from error
