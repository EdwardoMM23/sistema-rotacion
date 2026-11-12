import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CARPETA_BD = BASE_DIR / "instance"
RUTA_BD = CARPETA_BD / "rotacion.db"


def conectar():
    """Abre una conexión SQLite y activa las claves foráneas."""
    CARPETA_BD.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(RUTA_BD)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def crear_base_datos():
    """Crea las tablas si no existen. No elimina datos existentes."""
    conexion = conectar()
    try:
        conexion.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_usuario TEXT NOT NULL UNIQUE,
            nombre_completo TEXT NOT NULL,
            contrasena_hash TEXT NOT NULL,
            rol TEXT NOT NULL CHECK (rol IN
                ('Lider','Supervisor','Doctor','Enfermeria','Administrador')),
            activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1))
        );

        CREATE TABLE IF NOT EXISTS puestos_linea (
            id_puesto INTEGER PRIMARY KEY AUTOINCREMENT,
            id_linea INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            cantidad_requerida INTEGER NOT NULL DEFAULT 0 CHECK (cantidad_requerida BETWEEN 0 AND 30),
            activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0,1)),
            UNIQUE(id_linea,id_estacion),
            FOREIGN KEY (id_linea) REFERENCES lineas(id_linea),
            FOREIGN KEY (id_estacion) REFERENCES estaciones(id_estacion)
        );

        CREATE TABLE IF NOT EXISTS lineas (
            id_linea INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_linea TEXT NOT NULL UNIQUE,
            activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0,1)),
            area TEXT NOT NULL DEFAULT 'Producción' CHECK (area IN ('Producción','MFI'))
        );

        CREATE TABLE IF NOT EXISTS operadores (
            id_operador INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_empleado TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            id_linea INTEGER NOT NULL,
            activo INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0,1)),
            turno TEXT NOT NULL DEFAULT 'Matutino' CHECK (turno IN ('Matutino','Vespertino')),
            FOREIGN KEY (id_linea) REFERENCES lineas(id_linea)
        );

        CREATE TABLE IF NOT EXISTS estaciones (
            id_estacion INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_estacion TEXT NOT NULL UNIQUE,
            postura TEXT NOT NULL CHECK (postura IN ('Sentado','De pie','Ambas')),
            activa INTEGER NOT NULL DEFAULT 1 CHECK (activa IN (0,1))
        );

        CREATE TABLE IF NOT EXISTS autorizaciones (
            id_autorizacion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_operador INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            autorizado INTEGER NOT NULL CHECK (autorizado IN (0,1)),
            UNIQUE (id_operador,id_estacion),
            FOREIGN KEY (id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY (id_estacion) REFERENCES estaciones(id_estacion)
        );

        CREATE TABLE IF NOT EXISTS asistencia (
            id_asistencia INTEGER PRIMARY KEY AUTOINCREMENT,
            id_operador INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            estado TEXT NOT NULL CHECK (estado IN ('Presente','Ausente','Pendiente')),
            hora_confirmacion TEXT,
            confirmado_por INTEGER,
            UNIQUE (id_operador,fecha),
            FOREIGN KEY (id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY (confirmado_por) REFERENCES usuarios(id_usuario)
        );

        CREATE TABLE IF NOT EXISTS restricciones_medicas (
            id_restriccion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_operador INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT,
            condicion TEXT,
            observaciones TEXT,
            registrado_por INTEGER,
            fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            estado TEXT NOT NULL DEFAULT 'Activa'
                CHECK (estado IN ('Activa','Finalizada')),
            archivada INTEGER NOT NULL DEFAULT 0 CHECK (archivada IN (0,1)),
            FOREIGN KEY (id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY (registrado_por) REFERENCES usuarios(id_usuario),
            CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
        );

        CREATE TABLE IF NOT EXISTS detalle_restriccion (
            id_detalle INTEGER PRIMARY KEY AUTOINCREMENT,
            id_restriccion INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            permitida INTEGER NOT NULL CHECK (permitida IN (0,1)),
            UNIQUE (id_restriccion,id_estacion),
            FOREIGN KEY (id_restriccion) REFERENCES restricciones_medicas(id_restriccion),
            FOREIGN KEY (id_estacion) REFERENCES estaciones(id_estacion)
        );

        CREATE TABLE IF NOT EXISTS rotaciones (
            id_rotacion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_linea INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            turno TEXT NOT NULL DEFAULT 'Matutino' CHECK (turno IN ('Matutino','Vespertino')),
            numero_rotacion INTEGER NOT NULL,
            hora_inicio TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Generada'
                CHECK (estado IN ('Generada','Validada','Modificada','Cancelada')),
            generada_por INTEGER,
            fecha_generacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (id_linea,fecha,numero_rotacion),
            FOREIGN KEY (id_linea) REFERENCES lineas(id_linea),
            FOREIGN KEY (generada_por) REFERENCES usuarios(id_usuario)
        );

        CREATE TABLE IF NOT EXISTS asignaciones (
            id_asignacion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_rotacion INTEGER NOT NULL,
            id_operador INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            hora_inicio TEXT NOT NULL,
            hora_fin TEXT NOT NULL,
            es_prestado INTEGER NOT NULL DEFAULT 0 CHECK (es_prestado IN (0,1)),
            id_linea_origen INTEGER,
            FOREIGN KEY (id_rotacion) REFERENCES rotaciones(id_rotacion),
            FOREIGN KEY (id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY (id_estacion) REFERENCES estaciones(id_estacion),
            FOREIGN KEY (id_linea_origen) REFERENCES lineas(id_linea),
            CHECK ((es_prestado=0 AND id_linea_origen IS NULL) OR
                   (es_prestado=1 AND id_linea_origen IS NOT NULL))
        );

        CREATE TABLE IF NOT EXISTS prestamos_operadores (
            id_prestamo INTEGER PRIMARY KEY AUTOINCREMENT,
            id_operador INTEGER NOT NULL,
            id_linea_origen INTEGER NOT NULL,
            id_linea_destino INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT,
            motivo TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente','Aprobado','Rechazado','Devuelto')),
            solicitado_por INTEGER,
            autorizado_por INTEGER,
            fecha_solicitud TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY (id_linea_origen) REFERENCES lineas(id_linea),
            FOREIGN KEY (id_linea_destino) REFERENCES lineas(id_linea),
            FOREIGN KEY (solicitado_por) REFERENCES usuarios(id_usuario),
            FOREIGN KEY (autorizado_por) REFERENCES usuarios(id_usuario),
            CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
        );

        CREATE TABLE IF NOT EXISTS historial_cambios (
            id_cambio INTEGER PRIMARY KEY AUTOINCREMENT,
            id_rotacion INTEGER NOT NULL,
            descripcion TEXT NOT NULL,
            motivo TEXT,
            usuario_responsable INTEGER,
            fecha_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            tipo_cambio TEXT NOT NULL,
            FOREIGN KEY (id_rotacion) REFERENCES rotaciones(id_rotacion),
            FOREIGN KEY (usuario_responsable) REFERENCES usuarios(id_usuario)
        );
        """)

        # Fase 12: seguimiento médico, préstamos por intervalo y habilidades por estación.
        conexion.executescript("""
        CREATE TABLE IF NOT EXISTS historial_restricciones (
            id_evento INTEGER PRIMARY KEY AUTOINCREMENT,
            id_restriccion INTEGER NOT NULL,
            tipo_evento TEXT NOT NULL,
            fecha_efectiva TEXT,
            fecha_fin_anterior TEXT,
            fecha_fin_nueva TEXT,
            nota_operativa TEXT,
            usuario_id INTEGER,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(id_restriccion) REFERENCES restricciones_medicas(id_restriccion),
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id_usuario)
        );
        CREATE TABLE IF NOT EXISTS puestos_periodo (
            id_demanda INTEGER PRIMARY KEY AUTOINCREMENT,
            id_linea INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            turno TEXT NOT NULL DEFAULT 'Matutino',
            periodo INTEGER NOT NULL,
            cantidad_requerida INTEGER NOT NULL DEFAULT 0 CHECK(cantidad_requerida BETWEEN 0 AND 30),
            UNIQUE(id_linea,id_estacion,turno,periodo),
            FOREIGN KEY(id_linea) REFERENCES lineas(id_linea),
            FOREIGN KEY(id_estacion) REFERENCES estaciones(id_estacion)
        );
        CREATE TABLE IF NOT EXISTS habilidades_estacion (
            id_habilidad INTEGER PRIMARY KEY AUTOINCREMENT,
            id_operador INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            nivel TEXT NOT NULL CHECK(nivel IN ('Baja','Media','Alta')),
            actualizado_por INTEGER,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(id_operador,id_estacion),
            FOREIGN KEY(id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY(id_estacion) REFERENCES estaciones(id_estacion),
            FOREIGN KEY(actualizado_por) REFERENCES usuarios(id_usuario)
        );
        CREATE TABLE IF NOT EXISTS seguimiento_capacitacion (
            id_seguimiento INTEGER PRIMARY KEY AUTOINCREMENT,
            id_operador INTEGER NOT NULL,
            id_estacion INTEGER NOT NULL,
            estado TEXT NOT NULL CHECK(estado IN ('Pendiente','En entrenamiento','Evaluación programada','Autorizado','No aprobado')),
            fecha_evaluacion TEXT,
            fecha_ultima_evaluacion TEXT,
            observaciones TEXT,
            actualizado_por INTEGER,
            actualizado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(id_operador,id_estacion),
            FOREIGN KEY(id_operador) REFERENCES operadores(id_operador),
            FOREIGN KEY(id_estacion) REFERENCES estaciones(id_estacion),
            FOREIGN KEY(actualizado_por) REFERENCES usuarios(id_usuario)
        );
        """)
        columnas_prestamos = {fila[1] for fila in conexion.execute("PRAGMA table_info(prestamos_operadores)").fetchall()}
        for columna, definicion in {
            "hora_inicio": "TEXT", "hora_fin": "TEXT", "hora_devolucion": "TEXT", "devolucion_anticipada": "INTEGER NOT NULL DEFAULT 0"
        }.items():
            if columna not in columnas_prestamos:
                conexion.execute(f"ALTER TABLE prestamos_operadores ADD COLUMN {columna} {definicion}")
        columnas_restricciones = {fila[1] for fila in conexion.execute("PRAGMA table_info(restricciones_medicas)").fetchall()}
        if "ultima_revision" not in columnas_restricciones:
            conexion.execute("ALTER TABLE restricciones_medicas ADD COLUMN ultima_revision TEXT")
        if "requiere_revaloracion" not in columnas_restricciones:
            conexion.execute("ALTER TABLE restricciones_medicas ADD COLUMN requiere_revaloracion INTEGER NOT NULL DEFAULT 1")

        # Migración segura: clasifica cada línea por área sin borrar datos.
        columnas_lineas = {fila[1] for fila in conexion.execute("PRAGMA table_info(lineas)").fetchall()}
        if "area" not in columnas_lineas:
            conexion.execute("ALTER TABLE lineas ADD COLUMN area TEXT NOT NULL DEFAULT 'Producción'")
        # Catálogo adicional para puestos específicos de MFI; en Producción quedan en cero hasta configurarse.
        estaciones_mfi = [
            ("Breakout 1", "De pie"), ("Breakout 2", "De pie"),
            ("Inserción 1", "Sentado"), ("Inserción 2", "Sentado"),
            ("Empaque 1", "Sentado"), ("Empaque 2", "Sentado")
        ]
        conexion.executemany("INSERT OR IGNORE INTO estaciones (nombre_estacion, postura) VALUES (?,?)", estaciones_mfi)
        # Int/Visual e IL/RL se normalizan más abajo; no reinsertar alias antiguos
        # en cada arranque porque producirían estaciones duplicadas.
        # Las cuatro líneas MFI se crean automáticamente, sin modificar las líneas existentes.
        for numero in range(1, 5):
            conexion.execute("INSERT OR IGNORE INTO lineas (nombre_linea, area, activa) VALUES (?, 'MFI', 1)", (f"MFI{numero}",))

        # Migración segura: separa operadores y rotaciones por turno.
        columnas_operadores = {fila[1] for fila in conexion.execute("PRAGMA table_info(operadores)").fetchall()}
        if "turno" not in columnas_operadores:
            conexion.execute("ALTER TABLE operadores ADD COLUMN turno TEXT NOT NULL DEFAULT 'Matutino'")
        if "estado_laboral" not in columnas_operadores:
            conexion.execute("ALTER TABLE operadores ADD COLUMN estado_laboral TEXT NOT NULL DEFAULT 'Activo'")
        if "detalle_estado" not in columnas_operadores:
            conexion.execute("ALTER TABLE operadores ADD COLUMN detalle_estado TEXT")
        if "fecha_estado_fin" not in columnas_operadores:
            conexion.execute("ALTER TABLE operadores ADD COLUMN fecha_estado_fin TEXT")
        columnas_operadores = {fila[1] for fila in conexion.execute("PRAGMA table_info(operadores)").fetchall()}
        if "area" not in columnas_operadores:
            conexion.execute("ALTER TABLE operadores ADD COLUMN area TEXT NOT NULL DEFAULT 'Producción'")
        conexion.execute("UPDATE operadores SET area=COALESCE((SELECT area FROM lineas WHERE lineas.id_linea=operadores.id_linea),'Producción')")
        columnas_restricciones = {fila[1] for fila in conexion.execute("PRAGMA table_info(restricciones_medicas)").fetchall()}
        if "archivada" not in columnas_restricciones:
            conexion.execute("ALTER TABLE restricciones_medicas ADD COLUMN archivada INTEGER NOT NULL DEFAULT 0")
        columnas_rotaciones = {fila[1] for fila in conexion.execute("PRAGMA table_info(rotaciones)").fetchall()}
        if "turno" not in columnas_rotaciones:
            conexion.execute("ALTER TABLE rotaciones ADD COLUMN turno TEXT NOT NULL DEFAULT 'Matutino'")

        # Migración segura: unifica las cuentas antiguas de Doctor y Enfermería
        # en el rol único Enfermeria. La tabla ya permite ambos valores.
        conexion.execute("UPDATE usuarios SET rol='Enfermeria' WHERE rol='Doctor'")

        # Migración segura para proyectos existentes: añade ámbito de línea a cuentas.
        columnas_usuario = {fila[1] for fila in conexion.execute("PRAGMA table_info(usuarios)").fetchall()}
        if "id_linea" not in columnas_usuario:
            conexion.execute("ALTER TABLE usuarios ADD COLUMN id_linea INTEGER REFERENCES lineas(id_linea)")
        columnas_usuario = {fila[1] for fila in conexion.execute("PRAGMA table_info(usuarios)").fetchall()}
        if "estado_cuenta" not in columnas_usuario:
            conexion.execute("ALTER TABLE usuarios ADD COLUMN estado_cuenta TEXT NOT NULL DEFAULT 'Aprobada'")

        estaciones_iniciales = [
            ("Pegamento", "Sentado"), ("Accesorios", "Sentado"),
            ("Anel", "Sentado"), ("Decapado", "Sentado"),
            ("Crimpeo", "Sentado"), ("Horno", "Ambas"),
            ("Pulido", "De pie"), ("Brady", "De pie"), ("Amarre", "De pie")
        ]
        conexion.executemany("""
            INSERT OR IGNORE INTO estaciones (nombre_estacion, postura)
            VALUES (?, ?)
        """, estaciones_iniciales)

        # Catálogo por área: una estación compartida puede pertenecer a ambas
        # áreas, pero la postura puede variar según el proceso.
        conexion.execute("""CREATE TABLE IF NOT EXISTS estaciones_areas (
            id_estacion INTEGER NOT NULL,
            area TEXT NOT NULL CHECK(area IN ('Producción','MFI')),
            postura TEXT NOT NULL CHECK(postura IN ('Sentado','De pie','Ambas')),
            PRIMARY KEY(id_estacion,area),
            FOREIGN KEY(id_estacion) REFERENCES estaciones(id_estacion)
        )""")

        # Normalizar nombres del catálogo conservando los IDs históricos.
        # Se fusiona el antiguo registro MFI "Int./Visual" con el de Producción
        # "Visual" para mantener un solo nombre canónico compartido.
        visual = conexion.execute("SELECT id_estacion FROM estaciones WHERE nombre_estacion='Visual'").fetchone()
        int_visual = conexion.execute("SELECT id_estacion FROM estaciones WHERE nombre_estacion='Int./Visual'").fetchone()
        if visual and int_visual and visual[0] != int_visual[0]:
            destino, origen = int(visual[0]), int(int_visual[0])
            # Fusionar relaciones con restricciones UNIQUE sin duplicar filas.
            for tabla, columna, extra, claves in [
                ('autorizaciones','id_estacion','autorizado',('id_operador',)),
                ('detalle_restriccion','id_estacion','permitida',('id_restriccion',)),
                ('puestos_linea','id_estacion','cantidad_requerida',('id_linea',)),
                ('puestos_periodo','id_estacion','cantidad_requerida',('id_linea','turno','periodo')),
                ('habilidades_estacion','id_estacion','nivel',('id_operador',)),
                ('seguimiento_capacitacion','id_estacion','estado',('id_operador',))]:
                existe = conexion.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone()
                if not existe: continue
                pk = {'autorizaciones':'id_autorizacion','detalle_restriccion':'id_detalle','puestos_linea':'id_puesto','puestos_periodo':'id_demanda','habilidades_estacion':'id_habilidad','seguimiento_capacitacion':'id_seguimiento'}[tabla]
                filas_origen = conexion.execute(f"SELECT * FROM {tabla} WHERE {columna}=?", (origen,)).fetchall()
                for fila in filas_origen:
                    datos = dict(fila)
                    where = ' AND '.join(f'"{k}"=?' for k in claves)
                    valores = [datos[k] for k in claves]
                    duplicado = conexion.execute(f"SELECT * FROM {tabla} WHERE {columna}=? AND {where} LIMIT 1", [destino,*valores]).fetchone()
                    if duplicado:
                        if tabla in ('puestos_linea','puestos_periodo'):
                            conexion.execute(f"UPDATE {tabla} SET {extra}=MAX({extra},?) WHERE {pk}=?", (datos[extra],duplicado[pk]))
                        elif tabla == 'autorizaciones':
                            conexion.execute(f"UPDATE {tabla} SET {extra}=MIN({extra},?) WHERE {pk}=?", (datos[extra],duplicado[pk]))
                        elif tabla == 'detalle_restriccion':
                            conexion.execute(f"UPDATE {tabla} SET {extra}=MIN({extra},?) WHERE {pk}=?", (datos[extra],duplicado[pk]))
                        # En capacitación/habilidades se conserva el registro ya existente.
                        conexion.execute(f"DELETE FROM {tabla} WHERE {pk}=?", (datos[pk],))
                    else:
                        conexion.execute(f"UPDATE {tabla} SET {columna}=? WHERE {pk}=?", (destino,datos[pk]))
            # Tablas sin clave compuesta conocida.
            for tabla in ('asignaciones','alias'):
                existe = conexion.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)).fetchone()
                if existe:
                    conexion.execute(f"UPDATE {tabla} SET id_estacion=? WHERE id_estacion=?", (destino,origen))
            conexion.execute("DELETE FROM estaciones WHERE id_estacion=?", (origen,))
            conexion.execute("UPDATE estaciones SET nombre_estacion='Int/Visual' WHERE id_estacion=?", (destino,))
        else:
            conexion.execute("UPDATE estaciones SET nombre_estacion='Int/Visual' WHERE nombre_estacion='Visual'")
            conexion.execute("UPDATE estaciones SET nombre_estacion='Int/Visual' WHERE nombre_estacion='Int./Visual'")

        conexion.execute("UPDATE estaciones SET nombre_estacion='IL/RL' WHERE nombre_estacion='IL'")
        if not conexion.execute("SELECT 1 FROM estaciones WHERE nombre_estacion='IL/RL'").fetchone():
            conexion.execute("INSERT INTO estaciones(nombre_estacion,postura) VALUES('IL/RL','Ambas')")
        if not conexion.execute("SELECT 1 FROM estaciones WHERE nombre_estacion='Int/Visual'").fetchone():
            conexion.execute("INSERT INTO estaciones(nombre_estacion,postura) VALUES('Int/Visual','Sentado')")
        conexion.execute("UPDATE estaciones SET nombre_estacion='Test A' WHERE nombre_estacion='IL/Test A'")
        if not conexion.execute("SELECT 1 FROM estaciones WHERE nombre_estacion='Test A'").fetchone():
            conexion.execute("INSERT INTO estaciones(nombre_estacion,postura) VALUES('Test A','Sentado')")
        # Crear estaciones MFI que falten (idempotente).
        mfi_extra = [
            ('Breakout 1','De pie'),('Breakout 2','De pie'),
            ('Inserción 1','Sentado'),('Inserción 2','Sentado'),
            ('Test A','Sentado'),('Empaque 1','Sentado'),('Empaque 2','Sentado')]
        conexion.executemany("INSERT OR IGNORE INTO estaciones(nombre_estacion,postura) VALUES(?,?)", mfi_extra)

        # Relación exacta de estaciones permitidas y postura por área.
        nombres_area = {
            'Producción': {
                'Pegamento':'Sentado','Accesorios':'Sentado','Anel':'Sentado','Decapado':'Sentado',
                'Crimpeo':'Sentado','Horno':'Ambas','Pulido':'De pie','Int/Visual':'Sentado',
                'IL/RL':'Ambas','Brady':'De pie','Amarre':'De pie'},
            'MFI': {
                'Pegamento':'Sentado','Breakout 1':'De pie','Breakout 2':'De pie',
                'Inserción 1':'Sentado','Inserción 2':'Sentado','Crimpeo':'Sentado',
                'Horno':'Sentado','Pulido':'De pie','Int/Visual':'Sentado','Test A':'Sentado',
                'Empaque 1':'Sentado','Empaque 2':'Sentado'}}
        for area, catalogo in nombres_area.items():
            for nombre, postura in catalogo.items():
                fila = conexion.execute("SELECT id_estacion FROM estaciones WHERE nombre_estacion=?", (nombre,)).fetchone()
                if fila:
                    conexion.execute("INSERT INTO estaciones_areas(id_estacion,area,postura) VALUES(?,?,?) ON CONFLICT(id_estacion,area) DO UPDATE SET postura=excluded.postura", (fila['id_estacion'],area,postura))
        conexion.commit()
    except sqlite3.Error:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def obtener_estaciones_autorizadas(conexion, id_operador):
    """Devuelve las estaciones activas autorizadas para un operador."""
    return conexion.execute("""
        SELECT e.id_estacion, e.nombre_estacion
        FROM estaciones e
        JOIN autorizaciones a ON a.id_estacion = e.id_estacion
        WHERE a.id_operador = ?
          AND a.autorizado = 1
          AND e.activa = 1
        ORDER BY e.nombre_estacion
    """, (id_operador,)).fetchall()
