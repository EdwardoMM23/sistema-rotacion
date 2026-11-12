"""Verificación básica de migraciones de Fase 16. Ejecutar desde la carpeta del proyecto."""
from database import crear_base_datos, conectar

crear_base_datos()
conexion = conectar()
try:
    tablas = {r[0] for r in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columnas_operadores = {r[1] for r in conexion.execute("PRAGMA table_info(operadores)")}
    assert "seguimiento_capacitacion" in tablas, "Falta tabla seguimiento_capacitacion"
    assert "area" in columnas_operadores, "Falta columna operadores.area"
    mfi = [r[0] for r in conexion.execute("SELECT nombre_linea FROM lineas WHERE area='MFI' ORDER BY id_linea")]
    for nombre in ("MFI1", "MFI2", "MFI3", "MFI4"):
        assert nombre in mfi, f"Falta la línea {nombre}"
    print("FASE 16: migraciones y catálogo MFI correctos.")
    print("Líneas MFI:", ", ".join(mfi))
finally:
    conexion.close()
