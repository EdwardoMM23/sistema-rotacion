"""Comprobaciones rápidas de rutas de la fase 4. No modifica la base de datos."""
from app import app

RUTAS_ESPERADAS = {
    "login", "usuarios", "historial_rotaciones", "rotaciones",
    "generar_rotaciones", "editar_asignacion", "asistencia",
    "autorizaciones", "restricciones", "nueva_restriccion",
}

endpoints = set(app.view_functions)
faltantes = sorted(RUTAS_ESPERADAS - endpoints)
if faltantes:
    print("ERROR: faltan estos endpoints:", ", ".join(faltantes))
    raise SystemExit(1)

print("CORRECTO: se encontraron las rutas principales de la fase 4.")
print("Rutas de cambio de estación:")
for regla in app.url_map.iter_rules():
    if "editar_asignacion" in regla.endpoint:
        print(f"  {regla.rule} [{', '.join(sorted(regla.methods - {'HEAD', 'OPTIONS'}))}]")
print("Esta prueba verifica que las rutas existan; no reemplaza las pruebas manuales en el navegador.")
