"""Servidor WSGI para uso interno en un equipo autorizado de la planta."""
import os
from database import crear_base_datos
from app import app

if __name__ == "__main__":
    crear_base_datos()
    try:
        from waitress import serve
    except ImportError as exc:
        raise SystemExit("Falta Waitress. Ejecuta: python -m pip install -r requirements.txt") from exc
    if os.environ.get("SECRET_KEY", "").strip() == "":
        raise SystemExit("Configura SECRET_KEY como variable de entorno antes de iniciar el servidor.")
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    serve(app, host=host, port=port, threads=8)
