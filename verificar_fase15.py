"""Prueba aislada de Fase 15. No modifica la base de datos real del proyecto."""
import tempfile
from pathlib import Path
import sqlite3
import database
from generador import generar_propuesta


def ejecutar():
    carpeta = Path(tempfile.mkdtemp(prefix="rotaciones_fase15_"))
    ruta_original, carpeta_original = database.RUTA_BD, database.CARPETA_BD
    try:
        database.RUTA_BD = carpeta / "prueba.db"
        database.CARPETA_BD = carpeta
        database.crear_base_datos()
        con = database.conectar()
        lineas_mfi = [r[0] for r in con.execute("SELECT nombre_linea FROM lineas WHERE area='MFI' ORDER BY nombre_linea")]
        assert lineas_mfi == ["MFI1", "MFI2", "MFI3", "MFI4"], lineas_mfi

        con.execute("INSERT INTO lineas(nombre_linea,area) VALUES('LINEA_PRUEBA','Producción')")
        id_linea = con.execute("SELECT id_linea FROM lineas WHERE nombre_linea='LINEA_PRUEBA'").fetchone()[0]
        nombres = ["Pegamento", "Accesorios", "Anel", "Decapado", "Crimpeo", "Horno", "Pulido", "Visual", "IL", "Brady", "Amarre"]
        estaciones = con.execute(
            "SELECT id_estacion,nombre_estacion FROM estaciones WHERE nombre_estacion IN (" + ",".join("?" for _ in nombres) + ")",
            nombres,
        ).fetchall()
        assert len(estaciones) == 11, "No se encontró el catálogo de 11 estaciones de Producción."
        for e in estaciones:
            con.execute("INSERT INTO puestos_linea(id_linea,id_estacion,cantidad_requerida,activa) VALUES(?,?,1,1)", (id_linea,e["id_estacion"]))
        ids = []
        for i in range(12):
            con.execute("INSERT INTO operadores(numero_empleado,nombre,id_linea,activo,turno) VALUES(?,?,?,1,'Matutino')", (f"T{i+1:03}",f"Operador prueba {i+1}",id_linea))
            oid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
            ids.append(oid)
            con.execute("INSERT INTO asistencia(id_operador,fecha,estado) VALUES(?,'2026-10-29','Presente')", (oid,))
            for e in estaciones:
                con.execute("INSERT INTO autorizaciones(id_operador,id_estacion,autorizado) VALUES(?,?,1)", (oid,e["id_estacion"]))
        con.commit()
        propuesta, errores = generar_propuesta(con,id_linea,"2026-10-29","Matutino")
        assert not errores, errores
        grupos = [{a["id_operador"] for a in periodo} for periodo in propuesta]
        assert [len(g) for g in grupos] == [11,11,11], [len(g) for g in grupos]
        assert grupos[0] == grupos[1] == grupos[2], "El grupo de operadores cambia entre periodos."
        for oid in grupos[0]:
            estaciones_operador = [a["id_estacion"] for periodo in propuesta for a in periodo if a["id_operador"] == oid]
            assert len(estaciones_operador) == 3 and len(set(estaciones_operador)) == 3, (oid, estaciones_operador)
        sobrante = set(ids) - grupos[0]
        assert len(sobrante) == 1, sobrante
        print("OK: MFI1, MFI2, MFI3 y MFI4 se crean automáticamente.")
        print("OK: 12 presentes / 11 puestos = 11 operadores asignados en los 3 periodos y 1 disponible como apoyo.")
        print("OK: el mismo grupo se conserva y nadie repite estación durante el turno.")
        return True
    finally:
        database.RUTA_BD, database.CARPETA_BD = ruta_original, carpeta_original


if __name__ == "__main__":
    ejecutar()
