"""Verificación básica de la Fase 9. Ejecutar desde la raíz del proyecto."""
from database import crear_base_datos, conectar
from generador import PERIODOS_PRODUCCION, PERIODOS_MFI

crear_base_datos()
con = conectar()
errores = []
try:
    lineas = {r["name"] for r in con.execute("PRAGMA table_info(lineas)").fetchall()}
    if "area" not in lineas:
        errores.append("Falta la columna lineas.area")
    estaciones = {r["nombre_estacion"]: r["postura"] for r in con.execute(
        "SELECT nombre_estacion,postura FROM estaciones").fetchall()}
    for nombre in ("Breakout 1", "Breakout 2", "Inserción 1", "Inserción 2", "Empaque 1", "Empaque 2"):
        if nombre not in estaciones:
            errores.append(f"Falta la estación {nombre}")
finally:
    con.close()

if PERIODOS_MFI["Matutino"] != [("06:00","10:00"),("10:30","15:12")]:
    errores.append("Los horarios matutinos de MFI no coinciden")
if len(PERIODOS_PRODUCCION["Matutino"]) != 3:
    errores.append("Producción debe conservar tres periodos matutinos")
if errores:
    print("REVISIÓN CON OBSERVACIONES:")
    for e in errores: print(" -", e)
    raise SystemExit(1)
print("OK: área de línea, catálogo MFI y horarios comprobados.")
print("Importante: falta validar desde navegador préstamos, restricciones y el diseño con datos reales.")
