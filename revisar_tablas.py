from database import conectar
conexion = conectar()
try:    
    tablas = conexion.execute("""       
      SELECT name        
      FROM sqlite_master        
      WHERE type = 'table'       
      ORDER BY name    
      """).fetchall()   
    for tabla in tablas:        
        nombre = tabla["name"]        
        print(f"\nTABLA: {nombre}")        
        columnas = conexion.execute(            
            f'PRAGMA table_info("{nombre}")'       
              ).fetchall()        
        for columna in columnas:            
            print(                
                f"  {columna['name']} "              
                    f"- {columna['type']}")
finally:   conexion.close()
