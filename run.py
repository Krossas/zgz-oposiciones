"""
run.py — Punto de entrada de la aplicación.

Ejecutar con: python run.py
"""

from app import crear_app
from app.config import Config

if __name__ == "__main__":
    app = crear_app()
    app.run(
        host="0.0.0.0",
        port=Config.PORT,
        debug=Config.DEBUG,
        # use_reloader=False evita que Flask arranque dos veces en modo debug
        use_reloader=False,
    )
