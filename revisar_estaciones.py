
from database import conectar
conexion = conectar()
try:   
   estaciones = conexion.execute("""        
   SELECT id_estacion, nombre_estacion, postura, activa        
   FROM estaciones       
     ORDER BY id_estacion   
     """).fetchall()  
     
   print("\nESTACIONES REGISTRADAS\n")   
   for estacion in estaciones:       
     print(            
         f"ID: {estacion['id_estacion']} | "           
           f"Nombre: {estacion['nombre_estacion']} | "          
               f"Postura: {estacion['postura']} | "           
                 f"Activa: {estacion['activa']}"      
                     )   
   print(f"\nTotal de estaciones: {len(estaciones)}")
           
finally:    conexion.close()



