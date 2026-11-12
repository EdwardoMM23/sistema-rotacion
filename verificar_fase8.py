"""Verificación básica de la Fase 8. Ejecutar desde la carpeta del proyecto."""
from database import crear_base_datos, conectar
from generador import PERIODOS

crear_base_datos()
conexion = conectar()
try:
    requeridas = {
        "operadores": {"turno", "estado_laboral", "detalle_estado", "fecha_estado_fin"},
        "rotaciones": {"turno"},
        "restricciones_medicas": {"archivada"},
        "usuarios": {"estado_cuenta", "id_linea"},
    }
    errores = []
    for tabla, columnas_esperadas in requeridas.items():
        columnas = {r["name"] for r in conexion.execute(f"PRAGMA table_info({tabla})").fetchall()}
        faltan = columnas_esperadas - columnas
        if faltan:
            errores.append(f"{tabla}: faltan columnas {', '.join(sorted(faltan))}")
    tablas = {r["name"] for r in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "prestamos_operadores" not in tablas:
        errores.append("No existe la tabla prestamos_operadores")
finally:
    conexion.close()

if PERIODOS.get("Matutino") != [("06:00", "09:00"), ("09:00", "12:00"), ("12:00", "15:12")]:
    errores.append("Los periodos matutinos no coinciden con la configuración esperada")
if PERIODOS.get("Vespertino") != [("15:30", "18:30"), ("18:30", "21:30"), ("21:30", "00:30")]:
    errores.append("Los periodos vespertinos no coinciden con la fotografía proporcionada")

if errores:
    print("REVISIÓN CON OBSERVACIONES:")
    for error in errores:
        print(" -", error)
    raise SystemExit(1)
print("OK: columnas, tabla de préstamos y horarios de ambos turnos comprobados.")
print("NOTA: esto no sustituye las pruebas funcionales desde el navegador.")
