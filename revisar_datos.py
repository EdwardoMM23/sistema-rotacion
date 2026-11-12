import sqlite3
from pathlib import Path

RUTA_BD = Path("instance") / "rotacion.db"

if not RUTA_BD.exists():
    print("ERROR: No se encontró la base de datos.")
    print("Revisa que estés en la carpeta principal del proyecto.")
    raise SystemExit

conexion = sqlite3.connect(RUTA_BD)
conexion.row_factory = sqlite3.Row

print("\n========== TABLAS EXISTENTES ==========")

tablas = conexion.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""").fetchall()

for tabla in tablas:
    print("-", tabla["name"])

print("\n========== REGISTROS POR TABLA ==========")

for tabla in tablas:
    nombre = tabla["name"]

    # Ignorar las tablas internas de SQLite
    if nombre.startswith("sqlite_"):
        continue

    cantidad = conexion.execute(f"SELECT COUNT(*) AS total FROM {nombre}").fetchone()["total"]

    print(f"Tabla: {nombre} → {cantidad} registros")

conexion.close()
