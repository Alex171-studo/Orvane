"""Démarrer un serveur Streamlit local et vérifier sa disponibilité HTTP."""

import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.fileWatcherType=none",
    ]
    with subprocess.Popen(command, cwd=root) as process:
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Le serveur s’est arrêté avant le démarrage.")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as reply:
                        if reply.read() == b"ok":
                            break
                except (URLError, TimeoutError):
                    time.sleep(0.25)
            else:
                raise RuntimeError("Le serveur ne répond pas.")
            with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as reply:
                if reply.status != 200 or b"<html" not in reply.read():
                    raise RuntimeError("La page d’accueil est indisponible.")
            print("Serveur Streamlit disponible. Accueil HTTP 200, santé OK.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
