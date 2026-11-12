from database import conectar 
conexion = conectar()
 
try:   
     for tabla in [        
          "restricciones_medicas",        
          "detalle_restriccion",        
          "asistencia",        
          "autorizaciones",       
            "rotaciones",       
             "asignaciones"   
               ]:        
               print(f"\n--- {tabla} ---")        
               filas = conexion.execute(            
                       f"PRAGMA table_info({tabla})"       
                         ).fetchall()        
               for fila in filas:            
                print(fila["name"], "-", fila["type"])
finally:   
                conexion.close()
