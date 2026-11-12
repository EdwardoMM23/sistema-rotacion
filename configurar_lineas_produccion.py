"""Activa y crea el catálogo de 10 líneas de Producción y 4 líneas MFI.
No elimina operadores ni rotaciones. Ejecutar después de respaldar instance/rotacion.db.
"""
from database import crear_base_datos, conectar

def main():
    crear_base_datos()
    con = conectar()
    try:
        con.execute("BEGIN")
        # Compatibilidad con nombres de líneas de prueba comunes.
        renombres = [("LINEA_PRUEBA1", "Línea 1"), ("LINEA_PRUEBA2", "Línea 2")]
        for anterior, nuevo in renombres:
            existe_nuevo = con.execute("SELECT 1 FROM lineas WHERE nombre_linea=?", (nuevo,)).fetchone()
            existe_anterior = con.execute("SELECT id_linea FROM lineas WHERE nombre_linea=?", (anterior,)).fetchone()
            if existe_anterior and not existe_nuevo:
                con.execute("UPDATE lineas SET nombre_linea=?, area='Producción', activa=1 WHERE nombre_linea=?", (nuevo, anterior))
        for n in range(1, 11):
            con.execute("""INSERT INTO lineas(nombre_linea,area,activa) VALUES(?, 'Producción',1)
                ON CONFLICT(nombre_linea) DO UPDATE SET area='Producción',activa=1""", (f"Línea {n}",))
        for n in range(1, 5):
            con.execute("""INSERT INTO lineas(nombre_linea,area,activa) VALUES(?, 'MFI',1)
                ON CONFLICT(nombre_linea) DO UPDATE SET area='MFI',activa=1""", (f"MFI{n}",))
        con.commit()
        print("Catálogo activo: 10 líneas de Producción y 4 líneas MFI.")
        for area in ("Producción", "MFI"):
            print(f"\\n{area}:")
            for r in con.execute("SELECT nombre_linea FROM lineas WHERE area=? AND activa=1 ORDER BY id_linea", (area,)):
                print(" -", r["nombre_linea"])
        print("\\nNota: este script no borra ni mueve operadores de prueba.")
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    main()
