import os
import re
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, flash, redirect, url_for, session, abort
from database import crear_base_datos, conectar
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
from algoritmo import validar_secuencia
from generador import generar_propuesta, PERIODOS_PRODUCCION, PERIODOS_MFI

app = Flask(__name__)
# Para desarrollo se puede definir SECRET_KEY en las variables de entorno.
app.secret_key = os.environ.get("SECRET_KEY", "clave-temporal-solo-desarrollo")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

def requiere_inicio_sesion(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("id_usuario"):
            return redirect(url_for("login", siguiente=request.path))
        return func(*args, **kwargs)
    return wrapper

def requiere_rol(*roles):
    def decorador(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not session.get("id_usuario"):
                return redirect(url_for("login", siguiente=request.path))
            rol_actual = session.get("rol")
            # Acuerdo operativo: Supervisor puede cubrir funciones administrativas
            # cuando no esté disponible la persona Administradora.
            roles_efectivos = set(roles)
            if "Administrador" in roles_efectivos:
                roles_efectivos.add("Supervisor")
            if rol_actual not in roles_efectivos:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorador



def cargar_lineas_activas(conexion):
    return conexion.execute("""
        SELECT id_linea, nombre_linea, area
        FROM lineas WHERE activa = 1
        ORDER BY nombre_linea
    """).fetchall()


ROLES_LOGIN = {
    "Administrador": "Administrador",
    "Lider": "Lider",
    "Supervisor": "Supervisor",
    "Enfermeria": "Enfermeria",
}


def normalizar_rol(rol_guardado):
    """Unifica cuentas antiguas de Doctor y Enfermeria bajo Enfermeria."""
    if rol_guardado == "Doctor":
        return "Enfermeria"
    return rol_guardado


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("id_usuario"):
        return redirect(url_for("inicio"))

    if request.method == "POST":
        usuario = request.form.get("nombre_usuario", "").strip()
        contrasena = request.form.get("contrasena", "")
        rol_seleccionado = request.form.get("rol", "").strip()

        # No se confía en el rol enviado por el navegador: se compara con
        # el rol real de la cuenta almacenada en la base de datos.
        if rol_seleccionado not in ROLES_LOGIN:
            flash("Selecciona un tipo de usuario válido.", "warning")
            return render_template("login.html", rol_seleccionado="")

        conexion = conectar()
        try:
            cuenta = conexion.execute(
                "SELECT * FROM usuarios WHERE nombre_usuario=? AND activo=1 AND estado_cuenta='Aprobada'",
                (usuario,),
            ).fetchone()
        finally:
            conexion.close()

        rol_real = normalizar_rol(cuenta["rol"]) if cuenta else None
        credenciales_validas = bool(
            cuenta
            and check_password_hash(cuenta["contrasena_hash"], contrasena)
        )

        if credenciales_validas and rol_real == rol_seleccionado:
            session.clear()
            session["id_usuario"] = cuenta["id_usuario"]
            session["nombre_completo"] = cuenta["nombre_completo"]
            session["rol"] = rol_real
            session["id_linea"] = cuenta["id_linea"] if "id_linea" in cuenta.keys() else None
            destino = request.args.get("siguiente", "")
            if not destino.startswith("/") or destino.startswith("//"):
                destino = url_for("inicio")
            return redirect(destino)

        flash(
            "Los datos no coinciden con el tipo de usuario seleccionado, o la cuenta está desactivada.",
            "danger",
        )
        return render_template("login.html", rol_seleccionado=rol_seleccionado)

    return render_template("login.html", rol_seleccionado="")

@app.route("/solicitar-cuenta", methods=["GET", "POST"])
def solicitar_cuenta():
    """El registro público solo solicita rol Líder; no concede acceso hasta aprobación."""
    if session.get("id_usuario"):
        return redirect(url_for("inicio"))
    if request.method == "POST":
        nombre = request.form.get("nombre_completo", "").strip()
        usuario = request.form.get("nombre_usuario", "").strip()
        password = request.form.get("contrasena", "")
        confirmacion = request.form.get("confirmar_contrasena", "")
        if not nombre or not usuario:
            flash("Escribe tu nombre completo y un nombre de usuario.", "warning")
        elif len(password) < 10:
            flash("La contraseña debe tener al menos 10 caracteres.", "warning")
        elif password != confirmacion:
            flash("Las contraseñas no coinciden.", "warning")
        else:
            conexion = conectar()
            try:
                conexion.execute("""INSERT INTO usuarios
                    (nombre_usuario,nombre_completo,contrasena_hash,rol,activo,estado_cuenta)
                    VALUES(?,?,?,'Lider',0,'Pendiente')""",
                    (usuario,nombre,generate_password_hash(password)))
                conexion.commit()
                flash("Solicitud enviada. Un administrador debe aprobar la cuenta antes de iniciar sesión.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                conexion.rollback()
                flash("Ese nombre de usuario ya existe. Prueba con otro.", "danger")
            finally:
                conexion.close()
    return render_template("solicitar_cuenta.html")


@app.route("/usuarios", methods=["GET", "POST"])
@requiere_rol("Administrador")
def usuarios():
    conexion = conectar()
    roles_validos = {"Lider", "Supervisor", "Enfermeria", "Administrador"}
    try:
        if request.method == "POST":
            accion = request.form.get("accion", "crear")
            if accion == "crear":
                nombre_usuario = request.form.get("nombre_usuario", "").strip()
                nombre_completo = request.form.get("nombre_completo", "").strip()
                rol = request.form.get("rol", "").strip()
                contrasena = request.form.get("contrasena", "")
                confirmar = request.form.get("confirmar_contrasena", "")
                if not nombre_usuario or not nombre_completo or rol not in roles_validos:
                    flash("Completa los datos y selecciona una función válida.", "warning")
                elif len(contrasena) < 10:
                    flash("La contraseña debe tener al menos 10 caracteres.", "warning")
                elif contrasena != confirmar:
                    flash("Las contraseñas no coinciden.", "warning")
                else:
                    try:
                        conexion.execute("""INSERT INTO usuarios
                            (nombre_usuario,nombre_completo,contrasena_hash,rol,activo,estado_cuenta)
                            VALUES(?,?,?,?,1,'Aprobada')""",
                            (nombre_usuario, nombre_completo, generate_password_hash(contrasena), rol))
                        conexion.commit()
                        flash("Cuenta creada correctamente.", "success")
                    except sqlite3.IntegrityError:
                        conexion.rollback()
                        flash("Ese nombre de usuario ya existe. Elige otro.", "danger")
            elif accion == "estado":
                id_usuario = request.form.get("id_usuario", type=int)
                activo = request.form.get("activo", type=int)
                if not id_usuario or activo not in (0, 1):
                    flash("La solicitud de cambio de estado no es válida.", "warning")
                elif id_usuario == session.get("id_usuario") and activo == 0:
                    flash("No puedes desactivar tu propia cuenta.", "warning")
                else:
                    objetivo = conexion.execute("SELECT rol,activo FROM usuarios WHERE id_usuario=?", (id_usuario,)).fetchone()
                    if not objetivo:
                        flash("No se encontró esa cuenta.", "warning")
                    elif objetivo["rol"] == "Administrador" and objetivo["activo"] == 1 and activo == 0:
                        admins = conexion.execute("SELECT COUNT(*) n FROM usuarios WHERE rol='Administrador' AND activo=1").fetchone()["n"]
                        if admins <= 1:
                            flash("No puedes desactivar al último administrador activo.", "danger")
                        else:
                            conexion.execute("UPDATE usuarios SET activo=?, estado_cuenta=? WHERE id_usuario=?", (activo, "Aprobada" if activo else "Desactivada", id_usuario))
                            conexion.commit()
                            flash("Estado de la cuenta actualizado.", "success")
                    else:
                        conexion.execute("UPDATE usuarios SET activo=?, estado_cuenta=? WHERE id_usuario=?", (activo, "Aprobada" if activo else "Desactivada", id_usuario))
                        conexion.commit()
                        flash("Estado de la cuenta actualizado.", "success")
            else:
                flash("Acción de cuenta no reconocida.", "warning")
            return redirect(url_for("usuarios"))

        registros = conexion.execute("""SELECT id_usuario,nombre_usuario,nombre_completo,rol,activo,estado_cuenta
            FROM usuarios ORDER BY CASE estado_cuenta WHEN 'Pendiente' THEN 0 ELSE 1 END,nombre_completo""").fetchall()
        return render_template("usuarios.html", usuarios=registros)
    finally:
        conexion.close()


@app.route("/historial_rotaciones")
@requiere_rol("Lider", "Supervisor", "Administrador")
def historial_rotaciones():
    conexion = conectar()
    try:
        fecha = request.args.get("fecha") or date.today().isoformat()
        id_linea = request.args.get("id_linea", type=int)
        lineas = cargar_lineas_activas(conexion)
        sql = """SELECT c.fecha_hora,c.tipo_cambio,c.descripcion,c.motivo,
                        r.numero_rotacion,l.nombre_linea,u.nombre_completo
                 FROM historial_cambios c
                 JOIN rotaciones r ON r.id_rotacion=c.id_rotacion
                 JOIN lineas l ON l.id_linea=r.id_linea
                 LEFT JOIN usuarios u ON u.id_usuario=c.usuario_responsable
                 WHERE substr(c.fecha_hora,1,10)=?"""
        params = [fecha]
        if id_linea:
            sql += " AND r.id_linea=?"
            params.append(id_linea)
        sql += " ORDER BY c.fecha_hora DESC, c.id_cambio DESC"
        cambios = conexion.execute(sql, params).fetchall()
        return render_template("historial_rotaciones.html", cambios=cambios,
                               fecha=fecha, id_linea=id_linea, lineas=lineas)
    finally:
        conexion.close()


@app.route("/rotaciones/edicion")
@requiere_rol("Lider", "Supervisor", "Administrador")
def editor_rotaciones():
    """Panel para mover operadores, intercambiar y revisar propuestas vigentes."""
    conexion = conectar()
    try:
        lineas = cargar_lineas_activas(conexion)
        fecha = request.args.get("fecha") or date.today().isoformat()
        id_linea = request.args.get("id_linea", type=int)
        turno = request.args.get("turno", "Matutino")
        if turno not in ("Matutino", "Vespertino"):
            turno = "Matutino"
        registros = []
        nombre_linea = ""
        if id_linea:
            linea = conexion.execute("SELECT nombre_linea,area FROM lineas WHERE id_linea=? AND activa=1", (id_linea,)).fetchone()
            if not linea:
                id_linea = None
            else:
                nombre_linea = linea["nombre_linea"]
                rotaciones_db = conexion.execute("""SELECT id_rotacion,fecha,turno,numero_rotacion,hora_inicio,estado
                    FROM rotaciones WHERE id_linea=? AND fecha=? AND turno=? AND estado!='Cancelada'
                    ORDER BY numero_rotacion""", (id_linea, fecha, turno)).fetchall()
                for r in rotaciones_db:
                    item = dict(r)
                    item["asignaciones"] = [dict(a) for a in conexion.execute("""SELECT a.id_asignacion,a.id_operador,a.id_estacion,
                        a.hora_inicio,a.hora_fin,o.numero_empleado,o.nombre,e.nombre_estacion,ea.postura
                        FROM asignaciones a JOIN operadores o ON o.id_operador=a.id_operador
                        JOIN rotaciones rx ON rx.id_rotacion=a.id_rotacion JOIN lineas l ON l.id_linea=rx.id_linea
                        JOIN estaciones e ON e.id_estacion=a.id_estacion
                        JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area WHERE a.id_rotacion=?
                        ORDER BY a.hora_inicio,CASE UPPER(e.nombre_estacion)
 WHEN 'PEGAMENTO' THEN 1 WHEN 'ACCESORIOS' THEN 2 WHEN 'ANEL' THEN 3
 WHEN 'DECAPADO' THEN 4 WHEN 'INSERCION' THEN 5 WHEN 'INSERCIÓN' THEN 5
 WHEN 'MONTAJE' THEN 6 WHEN 'CRIMPEO' THEN 6 WHEN 'HORNO' THEN 7
 WHEN 'PULIDO' THEN 8 WHEN 'INT/VISUAL' THEN 9 WHEN 'VISUAL' THEN 9
 WHEN 'IL/RL' THEN 10 WHEN 'TEST A' THEN 10
 WHEN 'BRADY' THEN 11 WHEN 'EMPAQUE' THEN 12 WHEN 'AMARRE' THEN 12 ELSE 99 END,o.nombre""", (r["id_rotacion"],)).fetchall()]
                    registros.append(item)
        return render_template("editor_rotaciones.html", lineas=lineas, fecha=fecha, id_linea=id_linea,
                               turno=turno, registros=registros, nombre_linea=nombre_linea)
    finally:
        conexion.close()


@app.route("/rotaciones/versiones")
@requiere_rol("Lider", "Supervisor", "Administrador")
def versiones_rotaciones():
    """Consulta de versiones vigentes y anteriores; no altera registros."""
    conexion = conectar()
    try:
        lineas = cargar_lineas_activas(conexion)
        fecha = request.args.get("fecha") or date.today().isoformat()
        id_linea = request.args.get("id_linea", type=int)
        turno = request.args.get("turno", "Matutino")
        if turno not in ("Matutino", "Vespertino"):
            turno = "Matutino"
        versiones = []
        if id_linea:
            versiones = [dict(r) for r in conexion.execute("""SELECT r.id_rotacion,r.fecha,r.turno,r.numero_rotacion,
                r.hora_inicio,r.estado,r.fecha_generacion,u.nombre_completo,
                (SELECT COUNT(*) FROM asignaciones a WHERE a.id_rotacion=r.id_rotacion) AS total_asignaciones,
                (SELECT MAX(c.fecha_hora) FROM historial_cambios c WHERE c.id_rotacion=r.id_rotacion) AS ultimo_cambio
                FROM rotaciones r LEFT JOIN usuarios u ON u.id_usuario=r.generada_por
                WHERE r.id_linea=? AND r.fecha=? AND r.turno=?
                ORDER BY r.fecha_generacion DESC,r.id_rotacion DESC""", (id_linea, fecha, turno)).fetchall()]
            for v in versiones:
                v["asignaciones"] = [dict(a) for a in conexion.execute("""SELECT o.numero_empleado,o.nombre,e.nombre_estacion,a.hora_inicio,a.hora_fin
                    FROM asignaciones a JOIN operadores o ON o.id_operador=a.id_operador
                    JOIN estaciones e ON e.id_estacion=a.id_estacion WHERE a.id_rotacion=?
                    ORDER BY a.hora_inicio,o.nombre""", (v["id_rotacion"],)).fetchall()]
                v["eventos"] = [dict(e) for e in conexion.execute("""SELECT c.fecha_hora,c.tipo_cambio,c.descripcion,c.motivo,u.nombre_completo
                    FROM historial_cambios c LEFT JOIN usuarios u ON u.id_usuario=c.usuario_responsable
                    WHERE c.id_rotacion=? ORDER BY c.fecha_hora,c.id_cambio""", (v["id_rotacion"],)).fetchall()]
        return render_template("versiones_rotaciones.html", lineas=lineas, fecha=fecha, id_linea=id_linea,
                               turno=turno, versiones=versiones)
    finally:
        conexion.close()


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("login"))

@app.errorhandler(403)
def acceso_denegado(error):
    return render_template("acceso_denegado.html"), 403

@app.route("/")
@requiere_inicio_sesion
def inicio():
    conexion = conectar()
    try:
        estaciones = conexion.execute("""
            SELECT nombre_estacion, postura
            FROM estaciones WHERE activa = 1
            ORDER BY id_estacion
        """).fetchall()
        alertas_restricciones = []
        rol = session.get("rol")
        id_linea_usuario = session.get("id_linea")
        # Avisos operativos sin exponer diagnósticos ni observaciones clínicas.
        if rol in ("Lider", "Supervisor", "Administrador"):
            hoy = date.today().isoformat()
            consulta = """
                SELECT r.id_restriccion, o.numero_empleado, o.nombre,
                       r.fecha_inicio, r.fecha_fin, r.estado,
                       CASE
                         WHEN r.fecha_inicio > ? THEN 'Programada'
                         WHEN r.fecha_fin IS NOT NULL AND r.fecha_fin < ? THEN 'Vencida'
                         WHEN r.fecha_fin = ? THEN 'Vence hoy'
                         WHEN r.fecha_fin IS NOT NULL AND r.fecha_fin <= date(?, '+7 day') THEN 'Por vencer'
                         ELSE 'Vigente'
                       END AS vigencia,
                       GROUP_CONCAT(e.nombre_estacion, ', ') AS no_permitidas
                FROM restricciones_medicas r
                JOIN operadores o ON o.id_operador = r.id_operador
                LEFT JOIN detalle_restriccion d ON d.id_restriccion=r.id_restriccion AND d.permitida=0
                LEFT JOIN estaciones e ON e.id_estacion=d.id_estacion
                WHERE r.archivada=0
            """
            params = [hoy, hoy, hoy, hoy]
            if rol == "Lider":
                if id_linea_usuario:
                    area_lider = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea_usuario,)).fetchone()
                    if area_lider and area_lider["area"] == "MFI":
                        consulta += " AND o.area='MFI'"
                    else:
                        consulta += " AND o.id_linea=?"
                        params.append(id_linea_usuario)
                else:
                    consulta += " AND 1=0"  # Sin línea asignada no se revelan datos de otras líneas.
            consulta += " GROUP BY r.id_restriccion ORDER BY r.fecha_inicio DESC"
            alertas_restricciones = [dict(x) for x in conexion.execute(consulta, params).fetchall()]
        alertas_evaluacion = []
        if rol in ("Lider", "Supervisor", "Administrador"):
            hoy = date.today().isoformat()
            sql_eval = """SELECT sc.id_seguimiento, o.id_operador, o.numero_empleado, o.nombre,
                                  e.nombre_estacion, sc.estado, sc.fecha_evaluacion
                           FROM seguimiento_capacitacion sc
                           JOIN operadores o ON o.id_operador=sc.id_operador
                           JOIN estaciones e ON e.id_estacion=sc.id_estacion
                           WHERE sc.estado IN ('En entrenamiento','Evaluación programada')
                             AND sc.fecha_evaluacion IS NOT NULL AND sc.fecha_evaluacion<=?"""
            params_eval = [hoy]
            if rol == "Lider" and id_linea_usuario:
                area_lider = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea_usuario,)).fetchone()
                if area_lider and area_lider["area"] == "MFI":
                    sql_eval += " AND o.area='MFI'"
                else:
                    sql_eval += " AND o.id_linea=?"
                    params_eval.append(id_linea_usuario)
            elif rol == "Lider":
                sql_eval += " AND 1=0"
            sql_eval += " ORDER BY sc.fecha_evaluacion, o.nombre"
            alertas_evaluacion = [dict(x) for x in conexion.execute(sql_eval, params_eval).fetchall()]
        return render_template("inicio.html", estaciones=estaciones,
                               alertas_restricciones=alertas_restricciones,
                               alertas_evaluacion=alertas_evaluacion)
    finally:
        conexion.close()


@app.route("/rotaciones")
@requiere_inicio_sesion
def rotaciones():
    conexion = conectar()
    try:
        lineas = cargar_lineas_activas(conexion)
        fecha = request.args.get("fecha") or date.today().isoformat()
        id_linea = request.args.get("id_linea", type=int)
        turno = request.args.get("turno", "Matutino")
        if turno not in ("Matutino", "Vespertino"):
            turno = "Matutino"
        registros = []
        if id_linea:
            rotaciones_db = conexion.execute("""
                SELECT r.id_rotacion, r.fecha, r.numero_rotacion,
                       r.hora_inicio, r.estado, r.turno, l.nombre_linea, l.area
                FROM rotaciones r
                JOIN lineas l ON l.id_linea = r.id_linea
                WHERE r.id_linea = ? AND r.fecha = ? AND r.turno = ? AND r.estado != 'Cancelada'
                ORDER BY r.numero_rotacion
            """, (id_linea, fecha, turno)).fetchall()

            for r in rotaciones_db:
                asignaciones = conexion.execute("""
                    SELECT a.id_asignacion, a.id_operador,
                           a.id_estacion, a.hora_inicio, a.hora_fin, a.es_prestado, a.id_linea_origen,
                           o.numero_empleado, o.nombre,
                           e.nombre_estacion, ea.postura
                    FROM asignaciones a
                    JOIN operadores o ON o.id_operador = a.id_operador
                    JOIN rotaciones rx ON rx.id_rotacion=a.id_rotacion JOIN lineas l ON l.id_linea=rx.id_linea
                    JOIN estaciones e ON e.id_estacion = a.id_estacion
                    JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area
                    WHERE a.id_rotacion = ?
                    ORDER BY a.hora_inicio, o.numero_empleado
                """, (r["id_rotacion"],)).fetchall()

                item = dict(r)
                item["asignaciones"] = [dict(a) for a in asignaciones]
                registros.append(item)

        nombre_linea = ""
        if id_linea:
            fila_linea = conexion.execute("SELECT nombre_linea,area FROM lineas WHERE id_linea=?", (id_linea,)).fetchone()
            nombre_linea = fila_linea["nombre_linea"] if fila_linea else ""
        es_mfi = (fila_linea["area"] == "MFI") if id_linea and fila_linea and "area" in fila_linea.keys() else any(token in nombre_linea.upper() for token in ("MFI", "HFC", "META"))
        periodos = (PERIODOS_MFI if es_mfi else PERIODOS_PRODUCCION)[turno]
        operadores_apoyo = []
        if id_linea and registros:
            asignados_turno = {a["id_operador"] for registro in registros for a in registro["asignaciones"]}
            if es_mfi:
                operadores_presentes = conexion.execute("""SELECT o.id_operador,o.numero_empleado,o.nombre
                    FROM operadores o JOIN asistencia a ON a.id_operador=o.id_operador
                    WHERE o.area='MFI' AND o.turno=? AND o.activo=1 AND a.fecha=? AND a.estado='Presente'
                    ORDER BY o.nombre""", (turno, fecha)).fetchall()
            else:
                operadores_presentes = conexion.execute("""SELECT o.id_operador,o.numero_empleado,o.nombre
                    FROM operadores o JOIN asistencia a ON a.id_operador=o.id_operador
                    WHERE o.id_linea=? AND o.turno=? AND o.activo=1 AND a.fecha=? AND a.estado='Presente'
                    ORDER BY o.nombre""", (id_linea, turno, fecha)).fetchall()
            operadores_apoyo = [dict(o) for o in operadores_presentes if o["id_operador"] not in asignados_turno]
        orden_produccion = {"PEGAMENTO":1,"ACCESORIOS":2,"ANEL":3,"DECAPADO":4,"CRIMPEO":5,"HORNO":6,"PULIDO":7,"INT/VISUAL":8,"IL/RL":9,"BRADY":10,"AMARRE":11}
        orden_mfi = {"PEGAMENTO":1,"BREAKOUT 1":2,"BREAKOUT 2":3,"INSERCIÓN 1":4,"INSERCION 1":4,"INSERCIÓN 2":5,"INSERCION 2":5,"CRIMPEO":6,"HORNO":7,"PULIDO":8,"INT/VISUAL":9,"TEST A":10,"EMPAQUE 1":11,"EMPAQUE 2":12}
        ids_estaciones = sorted({a["id_estacion"] for registro in registros for a in registro["asignaciones"]})
        estaciones_tabla = []
        if ids_estaciones:
            marks = ",".join("?" for _ in ids_estaciones)
            estaciones_tabla = [dict(x) for x in conexion.execute(
                f"SELECT e.id_estacion,e.nombre_estacion,ea.postura FROM estaciones e JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=? WHERE e.id_estacion IN ({marks})", [fila_linea['area'], *ids_estaciones]).fetchall()]
            mapa_orden = orden_mfi if es_mfi else orden_produccion
            estaciones_tabla.sort(key=lambda x: (mapa_orden.get(x["nombre_estacion"].upper(), 99), x["nombre_estacion"]))
        grupo_sugerido = obtener_grupo_lineas(conexion, id_linea) if id_linea else []
        return render_template(
            "rotaciones.html",
            lineas=lineas,
            grupo_sugerido=grupo_sugerido,
            fecha=fecha,
            id_linea=id_linea,
            turno=turno,
            registros=registros,
            periodos=periodos,
            es_mfi=es_mfi,
            operadores_apoyo=operadores_apoyo,
            estaciones_tabla=estaciones_tabla
        )
    finally:
        conexion.close()



@app.route("/pantalla-rotaciones")
@requiere_inicio_sesion
def pantalla_rotaciones():
    """Vista de solo lectura para una computadora o pantalla compartida."""
    conexion = conectar()
    try:
        lineas = cargar_lineas_activas(conexion)
        fecha = request.args.get("fecha") or date.today().isoformat()
        id_linea = request.args.get("id_linea", type=int)
        turno = request.args.get("turno", "Matutino")
        if turno not in ("Matutino", "Vespertino"):
            turno = "Matutino"
        registros = []
        nombre_linea = ""
        es_mfi = False
        if id_linea:
            linea = conexion.execute(
                "SELECT nombre_linea, area FROM lineas WHERE id_linea=? AND activa=1",
                (id_linea,)
            ).fetchone()
            if not linea:
                id_linea = None
            else:
                nombre_linea = linea["nombre_linea"]
                es_mfi = (linea["area"] == "MFI") if "area" in linea.keys() else any(
                    token in nombre_linea.upper() for token in ("MFI", "HFC", "META")
                )
                rotaciones_db = conexion.execute("""
                    SELECT r.id_rotacion, r.fecha, r.numero_rotacion, r.hora_inicio,
                           r.estado, r.turno, l.nombre_linea
                    FROM rotaciones r JOIN lineas l ON l.id_linea=r.id_linea
                    WHERE r.id_linea=? AND r.fecha=? AND r.turno=?
                      AND r.estado != 'Cancelada'
                    ORDER BY r.numero_rotacion
                """, (id_linea, fecha, turno)).fetchall()
                for rot in rotaciones_db:
                    asignaciones = conexion.execute("""
                        SELECT a.id_asignacion, a.id_operador, a.id_estacion,
                               a.hora_inicio, a.hora_fin, a.es_prestado,
                               o.numero_empleado, o.nombre, e.nombre_estacion, ea.postura
                        FROM asignaciones a
                        JOIN operadores o ON o.id_operador=a.id_operador
                        JOIN rotaciones rx ON rx.id_rotacion=a.id_rotacion JOIN lineas l ON l.id_linea=rx.id_linea
                        JOIN estaciones e ON e.id_estacion=a.id_estacion
                        JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area
                        WHERE a.id_rotacion=?
                        ORDER BY a.hora_inicio, CASE UPPER(e.nombre_estacion)
 WHEN 'PEGAMENTO' THEN 1 WHEN 'ACCESORIOS' THEN 2 WHEN 'ANEL' THEN 3
 WHEN 'DECAPADO' THEN 4 WHEN 'INSERCION' THEN 5 WHEN 'INSERCIÓN' THEN 5
 WHEN 'MONTAJE' THEN 6 WHEN 'CRIMPEO' THEN 6 WHEN 'HORNO' THEN 7
 WHEN 'PULIDO' THEN 8 WHEN 'INT/VISUAL' THEN 9 WHEN 'VISUAL' THEN 9
 WHEN 'IL/RL' THEN 10 WHEN 'TEST A' THEN 10
 WHEN 'BRADY' THEN 11 WHEN 'EMPAQUE' THEN 12 WHEN 'AMARRE' THEN 12 ELSE 99 END, o.nombre
                    """, (rot["id_rotacion"],)).fetchall()
                    item = dict(rot)
                    item["asignaciones"] = [dict(a) for a in asignaciones]
                    orden_mfi = {"PEGAMENTO":1,"BREAKOUT 1":2,"BREAKOUT 2":3,"INSERCIÓN 1":4,"INSERCION 1":4,"INSERCIÓN 2":5,"INSERCION 2":5,"CRIMPEO":6,"HORNO":7,"PULIDO":8,"INT/VISUAL":9,"TEST A":10,"EMPAQUE 1":11,"EMPAQUE 2":12}
                    orden_prod = {"PEGAMENTO":1,"ACCESORIOS":2,"ANEL":3,"DECAPADO":4,"CRIMPEO":5,"HORNO":6,"PULIDO":7,"INT/VISUAL":8,"IL/RL":9,"BRADY":10,"AMARRE":11}
                    orden = orden_mfi if es_mfi else orden_prod
                    item["asignaciones"].sort(key=lambda a: (orden.get(a["nombre_estacion"].upper(), 99), a["nombre"]))
                    registros.append(item)
        periodos = (PERIODOS_MFI if es_mfi else PERIODOS_PRODUCCION)[turno]
        return render_template(
            "pantalla_rotaciones.html", lineas=lineas, fecha=fecha,
            id_linea=id_linea, turno=turno, registros=registros,
            periodos=periodos, es_mfi=es_mfi, nombre_linea=nombre_linea,
            auto_actualizar=request.args.get("auto") == "1"
        )
    finally:
        conexion.close()



@app.route("/asistencia", methods=["GET", "POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def asistencia():
    conexion = conectar()
    try:
        lineas = cargar_lineas_activas(conexion)
        fecha = request.values.get("fecha") or date.today().isoformat()
        id_linea = request.values.get("id_linea", type=int)
        turno = request.values.get("turno", "Matutino")
        if turno not in ("Matutino", "Vespertino"):
            turno = "Matutino"

        if request.method == "POST":
            id_linea = request.form.get("id_linea", type=int)
            fecha = request.form.get("fecha") or date.today().isoformat()
            turno = request.form.get("turno", "Matutino")
            if turno not in ("Matutino", "Vespertino"):
                turno = "Matutino"
            if not id_linea:
                flash("Selecciona una línea.", "warning")
                return redirect(url_for("asistencia", fecha=fecha))

            linea_area = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea,)).fetchone()
            es_mfi_asistencia = bool(linea_area and linea_area["area"] == "MFI")
            if es_mfi_asistencia:
                operadores = conexion.execute("SELECT id_operador FROM operadores WHERE area='MFI' AND activo=1 AND turno=?", (turno,)).fetchall()
            else:
                operadores = conexion.execute("SELECT id_operador FROM operadores WHERE id_linea=? AND activo=1 AND turno=?", (id_linea, turno)).fetchall()
            try:
                for op in operadores:
                    id_op = op["id_operador"]
                    estado = request.form.get(f"estado_{id_op}", "Pendiente")
                    if estado not in ("Presente", "Ausente", "Pendiente"):
                        estado = "Pendiente"
                    conexion.execute("""
                        INSERT INTO asistencia (id_operador, fecha, estado, hora_confirmacion)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(id_operador, fecha) DO UPDATE SET
                            estado = excluded.estado,
                            hora_confirmacion = excluded.hora_confirmacion
                    """, (id_op, fecha, estado, datetime.now().isoformat(timespec="seconds")))
                conexion.commit()
            except sqlite3.Error:
                conexion.rollback()
                raise
            flash("Asistencia guardada correctamente.", "success")
            return redirect(url_for("asistencia", fecha=fecha, id_linea=id_linea, turno=turno))

        lista_operadores = []
        pendientes = 0
        if id_linea:
            linea_area = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea,)).fetchone()
            if linea_area and linea_area["area"] == "MFI":
                lista_operadores = conexion.execute("""SELECT o.id_operador,o.numero_empleado,o.nombre,
                    COALESCE(a.estado,'Pendiente') AS estado FROM operadores o
                    LEFT JOIN asistencia a ON a.id_operador=o.id_operador AND a.fecha=?
                    WHERE o.area='MFI' AND o.activo=1 AND o.turno=? ORDER BY o.nombre""", (fecha,turno)).fetchall()
            else:
                lista_operadores = conexion.execute("""SELECT o.id_operador,o.numero_empleado,o.nombre,
                    COALESCE(a.estado,'Pendiente') AS estado FROM operadores o
                    LEFT JOIN asistencia a ON a.id_operador=o.id_operador AND a.fecha=?
                    WHERE o.id_linea=? AND o.activo=1 AND o.turno=? ORDER BY o.nombre""", (fecha,id_linea,turno)).fetchall()
            pendientes = sum(1 for op in lista_operadores if op["estado"] == "Pendiente")

        return render_template("asistencia.html", lineas=lineas, fecha=fecha,
                               id_linea=id_linea, turno=turno, operadores=lista_operadores,
                               pendientes=pendientes)
    finally:
        conexion.close()


@app.route("/autorizaciones", methods=["GET", "POST"])
@requiere_rol("Administrador")
def autorizaciones():
    conexion = conectar()
    try:
        busqueda = request.values.get("q", "").strip()[:100]
        operadores = conexion.execute("""
            SELECT id_operador, numero_empleado, nombre
            FROM operadores WHERE activo = 1 AND (?='' OR CAST(numero_empleado AS TEXT) LIKE ? OR LOWER(nombre) LIKE LOWER(?)) ORDER BY nombre LIMIT 300
        """, (busqueda, f"%{busqueda}%", f"%{busqueda}%")).fetchall()
        estaciones = conexion.execute("""
            SELECT id_estacion, nombre_estacion
            FROM estaciones WHERE activa = 1 ORDER BY id_estacion
        """).fetchall()
        id_operador = request.values.get("id_operador", type=int)

        if request.method == "POST":
            id_operador = request.form.get("id_operador", type=int)
            if not id_operador or not any(o["id_operador"] == id_operador for o in operadores):
                flash("Selecciona un operador válido.", "warning")
                return redirect(url_for("autorizaciones"))

            try:
                for estacion in estaciones:
                    campo = f"estacion_{estacion['id_estacion']}"
                    autorizado = 1 if request.form.get(campo) == "on" else 0
                    conexion.execute("""
                        INSERT INTO autorizaciones (id_operador, id_estacion, autorizado)
                        VALUES (?, ?, ?)
                        ON CONFLICT(id_operador, id_estacion)
                        DO UPDATE SET autorizado = excluded.autorizado
                    """, (id_operador, estacion["id_estacion"], autorizado))
                conexion.commit()
            except sqlite3.Error:
                conexion.rollback()
                raise
            flash("Autorizaciones guardadas correctamente.", "success")
            return redirect(url_for("autorizaciones", id_operador=id_operador))

        autorizadas = set()
        if id_operador:
            autorizadas = {
                fila["id_estacion"] for fila in conexion.execute("""
                    SELECT id_estacion FROM autorizaciones
                    WHERE id_operador = ? AND autorizado = 1
                """, (id_operador,)).fetchall()
            }
        return render_template("autorizaciones.html", operadores=operadores,
                               estaciones=estaciones, id_operador=id_operador,
                               autorizadas=autorizadas, busqueda=busqueda)
    finally:
        conexion.close()


@app.route("/operadores")
@requiere_rol("Lider", "Supervisor", "Administrador", "Enfermeria")
def operadores():
    conexion = conectar()
    try:
        busqueda = request.args.get("q", "").strip()[:100]
        turno = request.args.get("turno", "")
        if turno not in ("", "Matutino", "Vespertino"):
            turno = ""
        sql = """
            SELECT o.id_operador, o.numero_empleado, o.nombre,
                   CASE WHEN o.area='MFI' THEN 'MFI (asignación en rotaciones)' ELSE l.nombre_linea END AS nombre_linea,
                   o.activo, o.turno, o.estado_laboral, o.detalle_estado, o.fecha_estado_fin
            FROM operadores o JOIN lineas l ON l.id_linea = o.id_linea
            WHERE (? = '' OR CAST(o.numero_empleado AS TEXT) LIKE ? OR LOWER(o.nombre) LIKE LOWER(?))
              AND (? = '' OR o.turno = ?)
            ORDER BY o.nombre LIMIT 500
        """
        patron = f"%{busqueda}%"
        registros = conexion.execute(sql, (busqueda, patron, patron, turno, turno)).fetchall()
        return render_template("operadores.html", operadores=registros, busqueda=busqueda, turno=turno)
    finally:
        conexion.close()


@app.route("/operadores/nuevo", methods=["GET", "POST"])
@requiere_rol("Supervisor", "Administrador")
def nuevo_operador():
    conexion = conectar()
    try:
        lineas = cargar_lineas_activas(conexion)
        if request.method == "POST":
            numero = request.form.get("numero_empleado", "").strip()
            nombre = request.form.get("nombre", "").strip()
            area = request.form.get("area", "Producción")
            id_linea = request.form.get("id_linea", type=int)
            if area == "MFI":
                linea_mfi = conexion.execute("SELECT id_linea FROM lineas WHERE nombre_linea='MFI1' AND activa=1").fetchone()
                id_linea = linea_mfi["id_linea"] if linea_mfi else None
            turno = request.form.get("turno", "Matutino")
            if turno not in ("Matutino", "Vespertino"):
                turno = "Matutino"
            if not numero or not nombre or not id_linea or area not in ("Producción", "MFI"):
                flash("Completa los datos del operador y selecciona un área válida.", "warning")
                return render_template("nuevo_operador.html", lineas=lineas)
            if not any(l["id_linea"] == id_linea for l in lineas):
                flash("Selecciona una línea activa válida.", "warning")
                return render_template("nuevo_operador.html", lineas=lineas)
            try:
                conexion.execute("""
                    INSERT INTO operadores (numero_empleado, nombre, id_linea, activo, turno, area)
                    VALUES (?, ?, ?, 1, ?, ?)
                """, (numero, nombre, id_linea, turno, area))
                conexion.commit()
            except sqlite3.IntegrityError:
                conexion.rollback()
                flash("Ese número de empleado ya existe. Revisa el dato.", "danger")
                return render_template("nuevo_operador.html", lineas=lineas)
            flash("Operador registrado correctamente.", "success")
            return redirect(url_for("operadores"))
        return render_template("nuevo_operador.html", lineas=lineas)
    finally:
        conexion.close()


@app.route("/operadores/<int:id_operador>/turno", methods=["POST"])
@requiere_rol("Supervisor", "Administrador")
def cambiar_turno_operador(id_operador):
    turno = request.form.get("turno", "")
    if turno not in ("Matutino", "Vespertino"):
        flash("Selecciona un turno válido.", "warning")
        return redirect(url_for("operadores"))
    conexion = conectar()
    try:
        operador = conexion.execute("SELECT id_operador, turno FROM operadores WHERE id_operador=?", (id_operador,)).fetchone()
        if not operador:
            abort(404)
        if operador["turno"] != turno:
            futuras = conexion.execute("""SELECT COUNT(*) n FROM asignaciones a
                JOIN rotaciones r ON r.id_rotacion=a.id_rotacion
                WHERE a.id_operador=? AND r.fecha>=? AND r.estado!='Cancelada'""",
                (id_operador, date.today().isoformat())).fetchone()["n"]
            if futuras:
                flash("No se cambió el turno porque el operador tiene asignaciones guardadas desde hoy. Revisa o cancela esas rotaciones antes de cambiarlo.", "warning")
                return redirect(url_for("operadores"))
            conexion.execute("UPDATE operadores SET turno=? WHERE id_operador=?", (turno, id_operador))
            conexion.commit()
            flash("Turno del operador actualizado.", "success")
    finally:
        conexion.close()
    return redirect(url_for("operadores"))


@app.route("/operadores/<int:id_operador>/estado", methods=["POST"])
@requiere_rol("Supervisor", "Administrador")
def cambiar_estado_operador(id_operador):
    estado = request.form.get("estado_laboral", "")
    detalle = request.form.get("detalle_estado", "").strip()
    fecha_fin = request.form.get("fecha_estado_fin", "").strip() or None
    validos = {"Activo", "Vacaciones", "Incapacidad", "Permiso por horas", "Baja"}
    if estado not in validos:
        flash("Selecciona un estado válido.", "warning")
        return redirect(url_for("operadores"))
    if estado != "Activo" and not detalle:
        flash("Agrega una nota operativa breve, sin incluir diagnósticos médicos.", "warning")
        return redirect(url_for("operadores"))
    if fecha_fin:
        try: date.fromisoformat(fecha_fin)
        except ValueError:
            flash("La fecha de término no es válida.", "warning")
            return redirect(url_for("operadores"))
    # Baja y ausencias de jornada completa quedan excluidas del algoritmo actual.
    activo = 1 if estado == "Activo" else 0
    conexion = conectar()
    try:
        cur = conexion.execute("UPDATE operadores SET estado_laboral=?,detalle_estado=?,fecha_estado_fin=?,activo=? WHERE id_operador=?",
                               (estado,detalle or None,fecha_fin,activo,id_operador))
        if cur.rowcount == 0:
            flash("No se encontró el operador.", "warning")
        else:
            conexion.commit()
            flash("Estado del operador actualizado. Revisa la asistencia antes de generar rotaciones.", "success")
    finally:
        conexion.close()
    return redirect(url_for("operadores"))


@app.route("/puestos-linea", methods=["GET","POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def configuracion_puestos():
    conexion=conectar()
    try:
        lineas=cargar_lineas_activas(conexion)
        id_linea=request.values.get("id_linea",type=int)
        linea_actual = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea,)).fetchone() if id_linea else None
        area_actual = linea_actual["area"] if linea_actual else "Producción"
        if request.method == "POST":
            id_linea=request.form.get("id_linea",type=int)
            if not id_linea or not any(x["id_linea"]==id_linea for x in lineas):
                flash("Selecciona una línea activa.","warning")
                return redirect(url_for("configuracion_puestos"))
            area = request.form.get("area", area_actual)
            if area not in ("Producción", "MFI"):
                flash("Área no válida.","warning")
                return redirect(url_for("configuracion_puestos",id_linea=id_linea))
            if area != area_actual:
                conexion.execute("UPDATE lineas SET area=? WHERE id_linea=?", (area,id_linea))
                conexion.commit()
                flash(f"Área cambiada a {area}. Ahora aparecen únicamente sus estaciones; configura sus cantidades y guarda.","info")
                return redirect(url_for("configuracion_puestos",id_linea=id_linea))
            estaciones=conexion.execute("""SELECT e.id_estacion,e.nombre_estacion,ea.postura
                FROM estaciones e JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion
                WHERE ea.area=? AND e.activa=1 ORDER BY CASE e.nombre_estacion
                WHEN 'Pegamento' THEN 1 WHEN 'Accesorios' THEN 2 WHEN 'Anel' THEN 3 WHEN 'Decapado' THEN 4
                WHEN 'Breakout 1' THEN 2 WHEN 'Breakout 2' THEN 3 WHEN 'Inserción 1' THEN 4 WHEN 'Inserción 2' THEN 5
                WHEN 'Crimpeo' THEN 5 WHEN 'Horno' THEN 6 WHEN 'Pulido' THEN 7 WHEN 'Int/Visual' THEN 8
                WHEN 'IL/RL' THEN 9 WHEN 'Test A' THEN 10 WHEN 'Brady' THEN 10 WHEN 'Amarre' THEN 11
                WHEN 'Empaque 1' THEN 11 WHEN 'Empaque 2' THEN 12 ELSE 99 END""", (area,)).fetchall()
            try:
                for e in estaciones:
                    cantidad=int(request.form.get(f"cantidad_{e['id_estacion']}","0"))
                    if cantidad<0 or cantidad>30: raise ValueError("Cada cantidad debe estar entre 0 y 30.")
                    conexion.execute("""INSERT INTO puestos_linea(id_linea,id_estacion,cantidad_requerida,activa)
                        VALUES(?,?,?,1) ON CONFLICT(id_linea,id_estacion) DO UPDATE SET cantidad_requerida=excluded.cantidad_requerida,activa=1""", (id_linea,e['id_estacion'],cantidad))
                    num_periodos = 2 if area == 'MFI' else 3
                    for periodo in range(1,num_periodos+1):
                        valor=request.form.get(f"demanda_Matutino_{periodo}_{e['id_estacion']}")
                        if valor is not None:
                            valor=int(valor)
                            if valor<0 or valor>30: raise ValueError("La demanda por periodo debe estar entre 0 y 30.")
                            conexion.execute("""INSERT INTO puestos_periodo(id_linea,id_estacion,turno,periodo,cantidad_requerida)
                                VALUES(?,?,'Matutino',?,?) ON CONFLICT(id_linea,id_estacion,turno,periodo) DO UPDATE SET cantidad_requerida=excluded.cantidad_requerida""", (id_linea,e['id_estacion'],periodo,valor))
                conexion.commit()
                flash("Configuración de puestos guardada. Solo se guardaron estaciones del área seleccionada.","success")
            except (ValueError,sqlite3.Error) as error:
                conexion.rollback(); flash(f"No se guardó: {error}","danger")
            return redirect(url_for("configuracion_puestos",id_linea=id_linea))
        estaciones=[]; cantidades={}; demandas_periodo={}
        if id_linea:
            estaciones=conexion.execute("""SELECT e.id_estacion,e.nombre_estacion,ea.postura
                FROM estaciones e JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion
                WHERE ea.area=? AND e.activa=1 ORDER BY CASE e.nombre_estacion
                WHEN 'Pegamento' THEN 1 WHEN 'Accesorios' THEN 2 WHEN 'Anel' THEN 3 WHEN 'Decapado' THEN 4
                WHEN 'Breakout 1' THEN 2 WHEN 'Breakout 2' THEN 3 WHEN 'Inserción 1' THEN 4 WHEN 'Inserción 2' THEN 5
                WHEN 'Crimpeo' THEN 5 WHEN 'Horno' THEN 6 WHEN 'Pulido' THEN 7 WHEN 'Int/Visual' THEN 8
                WHEN 'IL/RL' THEN 9 WHEN 'Test A' THEN 10 WHEN 'Brady' THEN 10 WHEN 'Amarre' THEN 11
                WHEN 'Empaque 1' THEN 11 WHEN 'Empaque 2' THEN 12 ELSE 99 END""", (area_actual,)).fetchall()
            ids=[e['id_estacion'] for e in estaciones]
            if ids:
                marks=','.join('?' for _ in ids)
                cantidades={r['id_estacion']:r['cantidad_requerida'] for r in conexion.execute(
                    f"SELECT id_estacion,cantidad_requerida FROM puestos_linea WHERE id_linea=? AND id_estacion IN ({marks})",[id_linea,*ids]).fetchall()}
                demandas_periodo={(r['turno'],r['periodo'],r['id_estacion']):r['cantidad_requerida'] for r in conexion.execute(
                    f"SELECT turno,periodo,id_estacion,cantidad_requerida FROM puestos_periodo WHERE id_linea=? AND id_estacion IN ({marks})",[id_linea,*ids]).fetchall()}
        return render_template("configuracion_puestos.html",lineas=lineas,estaciones=estaciones,
            id_linea=id_linea,cantidades=cantidades,area_actual=area_actual,demandas_periodo=demandas_periodo)
    finally: conexion.close()


def obtener_grupo_lineas(conexion, id_linea):
    linea = conexion.execute("SELECT id_linea,area FROM lineas WHERE id_linea=? AND activa=1", (id_linea,)).fetchone()
    if not linea:
        return []
    if linea["area"] == "MFI":
        filas = [dict(r) for r in conexion.execute("SELECT id_linea,nombre_linea FROM lineas WHERE activa=1 AND area='MFI'").fetchall()]
        filas.sort(key=lambda x: (int(re.search(r"\d+", x["nombre_linea"]).group()) if re.search(r"\d+", x["nombre_linea"]) else 999, x["nombre_linea"]))
        return [r["id_linea"] for r in filas]
    filas = [dict(r) for r in conexion.execute("SELECT id_linea,nombre_linea FROM lineas WHERE activa=1 AND area='Producción'").fetchall()]
    filas.sort(key=lambda x: (int(re.search(r"\d+", x["nombre_linea"]).group()) if re.search(r"\d+", x["nombre_linea"]) else 999, x["nombre_linea"]))
    ids = [r["id_linea"] for r in filas]
    try:
        pos = ids.index(id_linea)
        return ids[(pos // 2) * 2:(pos // 2) * 2 + 2]
    except ValueError:
        return [id_linea]


@app.route("/rotaciones/generar-grupo", methods=["POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def generar_rotaciones_grupo():
    """Genera el grupo completo dentro de una transacción; si falla una línea, revierte todas."""
    conexion = conectar()
    try:
        id_linea = request.form.get("id_linea", type=int)
        fecha = request.form.get("fecha") or date.today().isoformat()
        turno = request.form.get("turno", "Matutino")
        if not id_linea:
            flash("Selecciona una línea para identificar su grupo.", "warning")
            return redirect(url_for("rotaciones", fecha=fecha, turno=turno))
        grupo_sugerido = obtener_grupo_lineas(conexion, id_linea)
        seleccionadas = request.form.getlist("lineas_grupo")
        if seleccionadas:
            try:
                grupo = list(dict.fromkeys(int(x) for x in seleccionadas))
            except (TypeError, ValueError):
                grupo = []
            if not grupo or any(x not in grupo_sugerido for x in grupo):
                flash("La selección contiene líneas que no pertenecen al grupo permitido. No se modificó ninguna rotación.", "warning")
                return redirect(url_for("rotaciones", fecha=fecha, id_linea=id_linea, turno=turno))
            area_seleccion = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea,)).fetchone()
            if area_seleccion and area_seleccion["area"] == "Producción" and set(grupo) != set(grupo_sugerido):
                flash("En Producción la generación grupal debe incluir la pareja completa asignada a la líder. Para generar una sola línea, utiliza ‘Generar propuesta individual’.", "warning")
                return redirect(url_for("rotaciones", fecha=fecha, id_linea=id_linea, turno=turno))
        else:
            grupo = grupo_sugerido
        if not grupo:
            flash("No se encontró un grupo activo.", "warning")
            return redirect(url_for("rotaciones", fecha=fecha, turno=turno))
        usar_habilidades = request.form.get("usar_habilidades") == "on"
        try:
            conexion.execute("BEGIN IMMEDIATE")
            # Retirar versiones vigentes de todo el grupo antes de calcular: así
            # no bloquean operadores que pertenecen al grupo compartido. Si falla,
            # el rollback restaura las versiones anteriores.
            for linea_id in grupo:
                antiguas = conexion.execute("SELECT id_rotacion FROM rotaciones WHERE id_linea=? AND fecha=? AND turno=? AND estado!='Cancelada'", (linea_id, fecha, turno)).fetchall()
                for antigua in antiguas:
                    conexion.execute("UPDATE rotaciones SET estado='Cancelada' WHERE id_rotacion=?", (antigua["id_rotacion"],))
                    conexion.execute("INSERT INTO historial_cambios(id_rotacion,descripcion,motivo,usuario_responsable,tipo_cambio) VALUES(?,?,?,?,?)",
                        (antigua["id_rotacion"], "Versión sustituida por generación grupal", "Se conserva para auditoría.", session["id_usuario"], "Regeneración grupal"))
            for linea_id in grupo:
                propuesta, errores = generar_propuesta(conexion, linea_id, fecha, turno, usar_habilidades=usar_habilidades, lineas_grupo=grupo)
                if errores:
                    nombre = conexion.execute("SELECT nombre_linea FROM lineas WHERE id_linea=?", (linea_id,)).fetchone()[0]
                    raise ValueError(nombre + ": " + " ".join(errores))
                max_num = conexion.execute("SELECT COALESCE(MAX(numero_rotacion),0) n FROM rotaciones WHERE id_linea=? AND fecha=? AND turno=?", (linea_id, fecha, turno)).fetchone()["n"]
                linea_area = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (linea_id,)).fetchone()["area"]
                periodos_linea = (PERIODOS_MFI if linea_area == "MFI" else PERIODOS_PRODUCCION)[turno]
                for i, periodo in enumerate(propuesta, 1):
                    hora_inicio = periodo[0]["hora_inicio"] if periodo else periodos_linea[i-1][0]
                    cur = conexion.execute("INSERT INTO rotaciones(id_linea,fecha,turno,numero_rotacion,hora_inicio,estado,generada_por) VALUES(?,?,?,?,?,'Generada',?)",
                        (linea_id, fecha, turno, max_num+i, hora_inicio, session["id_usuario"]))
                    for a in periodo:
                        conexion.execute("INSERT INTO asignaciones(id_rotacion,id_operador,id_estacion,hora_inicio,hora_fin,es_prestado,id_linea_origen) VALUES(?,?,?,?,?,?,?)",
                            (cur.lastrowid,a["id_operador"],a["id_estacion"],a["hora_inicio"],a["hora_fin"],a.get("es_prestado",0),a.get("id_linea_origen")))
                    conexion.execute("INSERT INTO historial_cambios(id_rotacion,descripcion,motivo,usuario_responsable,tipo_cambio) VALUES(?,?,?,?,?)",
                        (cur.lastrowid, "Propuesta generada como parte de grupo compartido", "Generación grupal; requiere revisión de líder.", session["id_usuario"], "Generación grupal"))
            conexion.commit()
            flash(f"Grupo generado para {len(grupo)} líneas. Consulta cada tabla individual y revisa la cobertura antes de validar.", "success")
        except (ValueError, sqlite3.Error) as exc:
            conexion.rollback()
            flash(f"No se guardó el grupo; toda la operación se revirtió. Motivo: {exc}", "danger")
        return redirect(url_for("rotaciones", fecha=fecha, id_linea=id_linea, turno=turno))
    finally:
        conexion.close()


@app.route("/rotaciones/generar",methods=["POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def generar_rotaciones():
    conexion=conectar()
    try:
        id_linea=request.form.get("id_linea",type=int)
        fecha=request.form.get("fecha") or date.today().isoformat()
        turno=request.form.get("turno", "Matutino")
        if turno not in ("Matutino", "Vespertino"):
            turno = "Matutino"
        if not id_linea:
            flash("Selecciona una línea.","warning")
            return redirect(url_for("rotaciones",fecha=fecha,turno=turno))
        # Primero generar y validar la alternativa. Si falla, la versión vigente no se toca.
        propuesta,errores=generar_propuesta(conexion,id_linea,fecha,turno,usar_habilidades=request.form.get("usar_habilidades") == "on" )
        if errores:
            for error in errores: flash(error,"warning")
            return redirect(url_for("rotaciones",fecha=fecha,id_linea=id_linea,turno=turno))
        try:
            conexion.execute("BEGIN IMMEDIATE")
            existentes=conexion.execute("SELECT id_rotacion,numero_rotacion FROM rotaciones WHERE id_linea=? AND fecha=? AND turno=? AND estado!='Cancelada' ORDER BY numero_rotacion",(id_linea,fecha,turno)).fetchall()
            # Mantener versiones previas para auditoría, sin eliminarlas.
            for antigua in existentes:
                conexion.execute("UPDATE rotaciones SET estado='Cancelada' WHERE id_rotacion=?", (antigua["id_rotacion"],))
                conexion.execute("INSERT INTO historial_cambios(id_rotacion,descripcion,motivo,usuario_responsable,tipo_cambio) VALUES(?,?,?,?,?)",
                    (antigua["id_rotacion"], "Versión sustituida por una nueva propuesta", "Se conserva la versión anterior para auditoría.", session["id_usuario"], "Regeneración"))
            max_numero=conexion.execute("SELECT COALESCE(MAX(numero_rotacion),0) AS n FROM rotaciones WHERE id_linea=? AND fecha=? AND turno=?",(id_linea,fecha,turno)).fetchone()["n"]
            linea_area = conexion.execute("SELECT area FROM lineas WHERE id_linea=?", (id_linea,)).fetchone()["area"]
            periodos_linea = (PERIODOS_MFI if linea_area == "MFI" else PERIODOS_PRODUCCION)[turno]
            for indice_periodo, periodo in enumerate(propuesta, start=1):
                hora_inicio = periodo[0]["hora_inicio"] if periodo else periodos_linea[indice_periodo-1][0]
                numero_version=max_numero + indice_periodo
                cur=conexion.execute("INSERT INTO rotaciones(id_linea,fecha,turno,numero_rotacion,hora_inicio,estado,generada_por) VALUES(?,?,?,?,?, 'Generada',?)",
                                     (id_linea,fecha,turno,numero_version,hora_inicio,session["id_usuario"]))
                for a in periodo:
                    conexion.execute("""INSERT INTO asignaciones(id_rotacion,id_operador,id_estacion,hora_inicio,hora_fin,es_prestado,id_linea_origen)
                                      VALUES(?,?,?,?,?,?,?)""",
                                     (cur.lastrowid,a["id_operador"],a["id_estacion"],a["hora_inicio"],a["hora_fin"],
                                      a.get("es_prestado", 0), a.get("id_linea_origen")))
                conexion.execute("""INSERT INTO historial_cambios
                    (id_rotacion,descripcion,motivo,usuario_responsable,tipo_cambio)
                    VALUES(?,?,?,?,?)""",
                    (cur.lastrowid, "Propuesta de rotación generada", "Generación automática; requiere revisión", session["id_usuario"], "Generación"))
            conexion.commit()
        except sqlite3.Error as error:
            conexion.rollback(); flash(f"No se guardó la propuesta: {error}","danger")
            return redirect(url_for("rotaciones",fecha=fecha,id_linea=id_linea,turno=turno))
        flash("Propuesta generada. Revísala antes de cualquier uso operativo.","success")
        return redirect(url_for("rotaciones",fecha=fecha,id_linea=id_linea,turno=turno))
    finally: conexion.close()



@app.route("/asignaciones/<int:id_asignacion>/editar", methods=["GET", "POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def editar_asignacion(id_asignacion):
    conexion = conectar()
    try:
        asignacion = conexion.execute("""SELECT a.id_asignacion,a.id_rotacion,a.id_operador,
                a.id_estacion,a.hora_inicio,a.hora_fin,r.fecha,r.turno,r.numero_rotacion,r.id_linea,l.area,
                o.numero_empleado,o.nombre,e.nombre_estacion
            FROM asignaciones a JOIN rotaciones r ON r.id_rotacion=a.id_rotacion
            JOIN lineas l ON l.id_linea=r.id_linea JOIN operadores o ON o.id_operador=a.id_operador
            JOIN estaciones e ON e.id_estacion=a.id_estacion
            WHERE a.id_asignacion=? AND r.estado!='Cancelada'""", (id_asignacion,)).fetchone()
        if not asignacion:
            abort(404)
        estaciones = conexion.execute("""SELECT e.id_estacion,e.nombre_estacion,ea.postura FROM estaciones e
            JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion
            WHERE e.activa=1 AND ea.area=? ORDER BY e.nombre_estacion""", (asignacion['area'],)).fetchall()
        if request.method == "POST":
            nuevo_id = request.form.get("id_estacion", type=int)
            motivo = request.form.get("motivo", "").strip()
            destino = next((e for e in estaciones if e["id_estacion"] == nuevo_id), None)
            if not destino or not motivo:
                flash("Selecciona una estación activa y escribe el motivo del cambio.", "warning")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            if nuevo_id == asignacion["id_estacion"]:
                flash("La estación seleccionada es la misma que la actual.", "info")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            autorizado = conexion.execute("SELECT 1 FROM autorizaciones WHERE id_operador=? AND id_estacion=? AND autorizado=1",
                                          (asignacion["id_operador"], nuevo_id)).fetchone()
            if not autorizado:
                flash("Cambio rechazado: el operador no está autorizado para esa estación.", "danger")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            bloqueada = conexion.execute("""SELECT 1 FROM restricciones_medicas r
                JOIN detalle_restriccion d ON d.id_restriccion=r.id_restriccion
                WHERE r.id_operador=? AND r.estado='Activa' AND r.fecha_inicio<=?
                  AND (r.fecha_fin IS NULL OR r.fecha_fin>=?)
                  AND d.id_estacion=? AND d.permitida=0 LIMIT 1""",
                (asignacion["id_operador"],asignacion["fecha"],asignacion["fecha"],nuevo_id)).fetchone()
            if bloqueada:
                flash("Cambio rechazado: la estación está bloqueada por una restricción vigente.", "danger")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            # No permitir que un cambio individual deje una estación por debajo
            # de su dotación requerida o sobrecargue la estación destino.
            conteos = {fila["id_estacion"]: fila["cantidad"] for fila in conexion.execute("""SELECT id_estacion,COUNT(*) AS cantidad
                FROM asignaciones WHERE id_rotacion=? GROUP BY id_estacion""", (asignacion["id_rotacion"],)).fetchall()}
            requeridos = {fila["id_estacion"]: fila["cantidad_requerida"] for fila in conexion.execute("""SELECT id_estacion,cantidad_requerida
                FROM puestos_linea WHERE id_linea=? AND activa=1""", (asignacion["id_linea"],)).fetchall()}
            cuenta_actual = conteos.get(asignacion["id_estacion"], 0)
            cuenta_destino = conteos.get(nuevo_id, 0)
            minimo_actual = requeridos.get(asignacion["id_estacion"], 0)
            maximo_destino = requeridos.get(nuevo_id, 0)
            if cuenta_actual - 1 < minimo_actual:
                flash("Cambio rechazado: dejaría la estación actual con menos operadores de los requeridos. Para intercambiar puestos, se necesita una operación de cambio simultáneo.", "danger")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            if maximo_destino <= 0 or cuenta_destino + 1 > maximo_destino:
                flash("Cambio rechazado: la estación destino ya tiene su dotación completa o no está configurada para esta línea.", "danger")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))

            vecinos = conexion.execute("""SELECT r.numero_rotacion,a.id_estacion,e.nombre_estacion,e.postura
                FROM asignaciones a JOIN rotaciones r ON r.id_rotacion=a.id_rotacion
                JOIN estaciones e ON e.id_estacion=a.id_estacion
                WHERE a.id_operador=? AND r.id_linea=? AND r.fecha=? AND r.estado!='Cancelada'
                  AND a.id_asignacion!=? ORDER BY r.numero_rotacion""",
                (asignacion["id_operador"],asignacion["id_linea"],asignacion["fecha"],id_asignacion)).fetchall()
            anterior = next((v for v in reversed(vecinos) if v["numero_rotacion"] < asignacion["numero_rotacion"]), None)
            siguiente = next((v for v in vecinos if v["numero_rotacion"] > asignacion["numero_rotacion"]), None)
            repeticion = conexion.execute("""SELECT 1 FROM asignaciones a
                JOIN rotaciones r ON r.id_rotacion=a.id_rotacion
                WHERE a.id_operador=? AND r.id_linea=? AND r.fecha=? AND r.turno=?
                  AND r.estado!='Cancelada' AND a.id_asignacion!=? AND a.id_estacion=? LIMIT 1""",
                (asignacion["id_operador"], asignacion["id_linea"], asignacion["fecha"], asignacion["turno"], id_asignacion, nuevo_id)).fetchone()
            if repeticion:
                flash("Cambio rechazado: el operador ya tiene esa estación en otro periodo del turno. Elige una estación diferente.", "warning")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            if anterior:
                ok, detalle = validar_secuencia(anterior["nombre_estacion"], destino["nombre_estacion"], anterior["postura"], destino["postura"])
                if not ok:
                    flash(f"Cambio rechazado: {detalle}", "danger")
                    return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            if siguiente:
                ok, detalle = validar_secuencia(destino["nombre_estacion"], siguiente["nombre_estacion"], destino["postura"], siguiente["postura"])
                if not ok:
                    flash(f"Cambio rechazado: {detalle}", "danger")
                    return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            try:
                conexion.execute("UPDATE asignaciones SET id_estacion=? WHERE id_asignacion=?", (nuevo_id,id_asignacion))
                conexion.execute("UPDATE rotaciones SET estado='Modificada' WHERE id_rotacion=?", (asignacion["id_rotacion"],))
                conexion.execute("""INSERT INTO historial_cambios
                    (id_rotacion,descripcion,motivo,usuario_responsable,tipo_cambio)
                    VALUES(?,?,?,?,?)""",
                    (asignacion["id_rotacion"],
                     f"{asignacion['numero_empleado']} cambió de {asignacion['nombre_estacion']} a {destino['nombre_estacion']}",
                     motivo,session["id_usuario"],"Cambio manual"))
                conexion.commit()
            except sqlite3.Error as error:
                conexion.rollback()
                flash(f"No se guardó el cambio: {error}", "danger")
                return redirect(url_for("editar_asignacion", id_asignacion=id_asignacion))
            flash("Cambio guardado y registrado en el historial.", "success")
            return redirect(url_for("rotaciones", fecha=asignacion["fecha"], id_linea=asignacion["id_linea"]))
        return render_template("editar_asignacion.html", asignacion=asignacion, estaciones=estaciones)
    finally:
        conexion.close()



@app.route("/restricciones")
@requiere_rol("Enfermeria", "Administrador")
def restricciones():
    conexion = conectar()
    try:
        busqueda = request.args.get("q", "").strip()[:100]
        patron = f"%{busqueda}%"
        registros = conexion.execute("""
            SELECT r.id_restriccion, o.numero_empleado, o.nombre,
                   r.fecha_inicio, r.fecha_fin, r.estado
            FROM restricciones_medicas r
            JOIN operadores o ON o.id_operador = r.id_operador
            WHERE r.archivada=0 AND (?='' OR CAST(o.numero_empleado AS TEXT) LIKE ? OR LOWER(o.nombre) LIKE LOWER(?))
            ORDER BY r.fecha_inicio DESC LIMIT 500
        """, (busqueda, patron, patron)).fetchall()
        return render_template("restricciones.html", restricciones=registros, busqueda=busqueda)
    finally:
        conexion.close()



@app.route("/restricciones/historial")
@requiere_rol("Enfermeria", "Administrador")
def historial_restricciones():
    conexion = conectar()
    try:
        busqueda = request.args.get("q", "").strip()[:100]
        patron = f"%{busqueda}%"
        filas = conexion.execute("""SELECT r.id_restriccion,o.numero_empleado,o.nombre,
            r.fecha_inicio,r.fecha_fin,r.estado,r.archivada,r.fecha_registro
            FROM restricciones_medicas r JOIN operadores o ON o.id_operador=r.id_operador
            WHERE (?='' OR CAST(o.numero_empleado AS TEXT) LIKE ? OR LOWER(o.nombre) LIKE LOWER(?))
            ORDER BY r.fecha_registro DESC LIMIT 500""", (busqueda, patron, patron)).fetchall()
        return render_template("historial_restricciones.html", reportes=filas, busqueda=busqueda)
    finally:
        conexion.close()

@app.route("/restricciones/<int:id_restriccion>/archivar", methods=["POST"])
@requiere_rol("Enfermeria", "Administrador")
def archivar_restriccion(id_restriccion):
    conexion = conectar()
    try:
        cur = conexion.execute("UPDATE restricciones_medicas SET archivada=1 WHERE id_restriccion=?", (id_restriccion,))
        if cur.rowcount:
            conexion.commit()
            flash("Reporte archivado. Se conserva en el historial y no se eliminó físicamente.", "success")
        else:
            flash("No se encontró el reporte.", "warning")
    finally:
        conexion.close()
    return redirect(url_for("historial_restricciones"))

@app.route("/restricciones/nueva", methods=["GET", "POST"])
@requiere_rol("Enfermeria", "Administrador")
def nueva_restriccion():
    conexion = conectar()
    try:
        busqueda_operador = request.args.get("q", "").strip()[:100]
        patron_operador = f"%{busqueda_operador}%"
        operadores = conexion.execute("SELECT id_operador,numero_empleado,nombre FROM operadores WHERE activo=1 AND (?='' OR CAST(numero_empleado AS TEXT) LIKE ? OR LOWER(nombre) LIKE LOWER(?)) ORDER BY nombre LIMIT 500", (busqueda_operador, patron_operador, patron_operador)).fetchall()
        estaciones = conexion.execute("SELECT id_estacion,nombre_estacion FROM estaciones WHERE activa=1 ORDER BY id_estacion").fetchall()
        if request.method == "POST":
            id_operador = request.form.get("id_operador", type=int)
            inicio = request.form.get("fecha_inicio", "")
            fin = request.form.get("fecha_fin", "") or None
            try:
                date.fromisoformat(inicio)
                if fin and date.fromisoformat(fin) < date.fromisoformat(inicio):
                    raise ValueError("La fecha final no puede ser anterior a la inicial.")
                if not any(o["id_operador"] == id_operador for o in operadores):
                    raise ValueError("Selecciona un operador válido.")
                cur = conexion.execute("""INSERT INTO restricciones_medicas
                    (id_operador,fecha_inicio,fecha_fin,condicion,observaciones,registrado_por,estado)
                    VALUES(?,?,?,?,?,?, 'Activa')""", (id_operador,inicio,fin,
                    request.form.get("condicion", "").strip(), request.form.get("observaciones", "").strip(),session["id_usuario"]))
                id_restriccion = cur.lastrowid
                for e in estaciones:
                    # Nuevo formulario: se marcan directamente las estaciones NO permitidas.
                    # Compatibilidad: si se recibe el formulario antiguo, se conserva su significado.
                    if f"no_permitida_{e['id_estacion']}" in request.form or any(k.startswith("no_permitida_") for k in request.form.keys()):
                        permitido = 0 if request.form.get(f"no_permitida_{e['id_estacion']}") == "1" else 1
                    else:
                        permitido = 1 if request.form.get(f"permitida_{e['id_estacion']}") == "1" else 0
                    conexion.execute("INSERT INTO detalle_restriccion(id_restriccion,id_estacion,permitida) VALUES(?,?,?)",(id_restriccion,e["id_estacion"],permitido))
                conexion.commit()
                flash("Restricción registrada. Verifica que las estaciones permitidas coincidan con la indicación autorizada.","success")
                return redirect(url_for("restricciones"))
            except (ValueError, sqlite3.Error) as error:
                conexion.rollback()
                flash(f"No se guardó la restricción: {error}","danger")
        return render_template("restriccion_nueva.html",operadores=operadores,estaciones=estaciones, busqueda_operador=busqueda_operador)
    finally:
        conexion.close()

@app.route("/restricciones/<int:id_restriccion>/reporte")
@requiere_rol("Enfermeria", "Supervisor", "Administrador")
def reporte_medico_detalle(id_restriccion):
    """Reporte clínico detallado: acceso restringido a Enfermería/Administración."""
    conexion = conectar()
    try:
        r = conexion.execute("""
            SELECT rm.*, o.numero_empleado, o.nombre,
                   u.nombre_completo AS registrado_por_nombre
            FROM restricciones_medicas rm
            JOIN operadores o ON o.id_operador = rm.id_operador
            LEFT JOIN usuarios u ON u.id_usuario = rm.registrado_por
            WHERE rm.id_restriccion = ?
        """, (id_restriccion,)).fetchone()
        if not r:
            abort(404)
        estaciones = conexion.execute("""
            SELECT e.nombre_estacion, d.permitida
            FROM detalle_restriccion d
            JOIN estaciones e ON e.id_estacion = d.id_estacion
            WHERE d.id_restriccion = ?
            ORDER BY e.id_estacion
        """, (id_restriccion,)).fetchall()
        return render_template("reporte_medico_detalle.html",
                               reporte=r, estaciones=estaciones)
    finally:
        conexion.close()


@app.route("/prestamos", methods=["GET", "POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def prestamos_operadores():
    conexion = conectar()
    try:
        if request.method == "POST":
            if session.get("rol") not in ("Lider", "Supervisor", "Administrador"):
                abort(403)
            id_operador = request.form.get("id_operador", type=int)
            destino = request.form.get("id_linea_destino", type=int)
            inicio = request.form.get("fecha_inicio", "")
            fin = request.form.get("fecha_fin", "") or None
            hora_inicio = request.form.get("hora_inicio", "") or None
            hora_fin = request.form.get("hora_fin", "") or None
            motivo = request.form.get("motivo", "").strip()
            try:
                date.fromisoformat(inicio)
                if fin and date.fromisoformat(fin) < date.fromisoformat(inicio):
                    raise ValueError("La fecha final no puede ser anterior al inicio.")
                if bool(hora_inicio) != bool(hora_fin):
                    raise ValueError("Captura ambas horas del préstamo o deja ambas vacías para todo el turno.")
                if hora_inicio and hora_fin and hora_fin <= hora_inicio:
                    raise ValueError("La hora final debe ser posterior a la hora inicial; los préstamos que crucen medianoche requieren registro separado.")
                operador = conexion.execute("SELECT id_operador,id_linea,activo FROM operadores WHERE id_operador=?", (id_operador,)).fetchone()
                if not operador or not operador["activo"]:
                    raise ValueError("Selecciona un operador activo.")
                if not destino or destino == operador["id_linea"]:
                    raise ValueError("La línea destino debe ser distinta a la línea de origen.")
                if not motivo:
                    raise ValueError("Indica el motivo operativo del préstamo.")
                conexion.execute("""INSERT INTO prestamos_operadores
                    (id_operador,id_linea_origen,id_linea_destino,fecha_inicio,fecha_fin,hora_inicio,hora_fin,motivo,solicitado_por)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (id_operador,operador["id_linea"],destino,inicio,fin,hora_inicio,hora_fin,motivo,session["id_usuario"]))
                conexion.commit()
                flash("Solicitud de préstamo registrada; debe ser autorizada antes de usarla en producción.", "success")
                return redirect(url_for("prestamos_operadores"))
            except (ValueError, sqlite3.Error) as error:
                conexion.rollback()
                flash(f"No se registró la solicitud: {error}", "danger")
        lineas = cargar_lineas_activas(conexion)
        operadores = conexion.execute("""SELECT o.id_operador,o.numero_empleado,o.nombre,o.id_linea,l.nombre_linea
            FROM operadores o JOIN lineas l ON l.id_linea=o.id_linea
            WHERE o.activo=1 ORDER BY o.nombre""").fetchall()
        filas = conexion.execute("""SELECT p.*,o.nombre,o.numero_empleado,lo.nombre_linea AS linea_origen,
            ld.nombre_linea AS linea_destino,us.nombre_completo AS solicitante,ua.nombre_completo AS autorizador
            FROM prestamos_operadores p JOIN operadores o ON o.id_operador=p.id_operador
            JOIN lineas lo ON lo.id_linea=p.id_linea_origen JOIN lineas ld ON ld.id_linea=p.id_linea_destino
            LEFT JOIN usuarios us ON us.id_usuario=p.solicitado_por LEFT JOIN usuarios ua ON ua.id_usuario=p.autorizado_por
            ORDER BY p.fecha_solicitud DESC""").fetchall()
        return render_template("prestamos.html", prestamos=filas,lineas=lineas,operadores=operadores)
    finally:
        conexion.close()

@app.route("/prestamos/<int:id_prestamo>/accion", methods=["POST"])
@requiere_rol("Supervisor", "Administrador")
def accion_prestamo(id_prestamo):
    accion = request.form.get("accion")
    estados = {"aprobar": "Aprobado", "rechazar": "Rechazado", "devolver": "Devuelto"}
    if accion not in estados:
        abort(400)
    conexion = conectar()
    try:
        registro = conexion.execute("SELECT * FROM prestamos_operadores WHERE id_prestamo=?", (id_prestamo,)).fetchone()
        if not registro:
            abort(404)
        if accion in ("aprobar", "rechazar") and registro["estado"] != "Pendiente":
            flash("Solo se pueden resolver solicitudes pendientes.", "warning")
        elif accion == "devolver" and registro["estado"] != "Aprobado":
            flash("Solo se puede registrar la devolución de un préstamo aprobado.", "warning")
        else:
            if accion == "devolver":
                hora_dev = datetime.now().strftime("%H:%M")
                conexion.execute("UPDATE prestamos_operadores SET estado='Devuelto',autorizado_por=?,hora_devolucion=?,devolucion_anticipada=CASE WHEN hora_fin IS NOT NULL AND ? < hora_fin THEN 1 ELSE 0 END WHERE id_prestamo=?",
                                 (session["id_usuario"],hora_dev,hora_dev,id_prestamo))
            else:
                conexion.execute("UPDATE prestamos_operadores SET estado=?,autorizado_por=? WHERE id_prestamo=?",
                                 (estados[accion],session["id_usuario"],id_prestamo))
            conexion.commit()
            flash("Estado del préstamo actualizado. Si está aprobado y vigente, el generador lo considerará en la línea de destino tras validar asistencia, autorizaciones y restricciones.", "success")
    finally:
        conexion.close()
    return redirect(url_for("prestamos_operadores"))


@app.route("/reporte-restricciones")
@requiere_rol("Lider", "Supervisor", "Enfermeria", "Administrador")
def reporte_restricciones():
    fecha = request.args.get("fecha") or date.today().isoformat()
    rol = session.get("rol")
    conexion = conectar()
    try:
        # La vista operativa no expone condicion ni observaciones clínicas.
        filas = conexion.execute("""SELECT r.id_restriccion,o.numero_empleado,o.nombre,r.fecha_inicio,r.fecha_fin,r.estado,
            GROUP_CONCAT(e.nombre_estacion, ', ') AS no_permitidas
            FROM restricciones_medicas r JOIN operadores o ON o.id_operador=r.id_operador
            LEFT JOIN detalle_restriccion d ON d.id_restriccion=r.id_restriccion AND d.permitida=0
            LEFT JOIN estaciones e ON e.id_estacion=d.id_estacion
            WHERE r.fecha_inicio<=? AND (r.fecha_fin IS NULL OR r.fecha_fin>=?)
            AND r.estado='Activa' GROUP BY r.id_restriccion,o.numero_empleado,o.nombre,r.fecha_inicio,r.fecha_fin,r.estado
            ORDER BY o.nombre""",(fecha,fecha)).fetchall()
        return render_template("reporte_restricciones.html",restricciones=[dict(r,estado_vigencia="Vigente") for r in filas],fecha=fecha)
    finally:
        conexion.close()


@app.route("/certificaciones", methods=["GET", "POST"])
@requiere_rol("Administrador")
def certificaciones():
    """Administra entrenamiento, evaluaciones programadas y certificación por estación."""
    conexion = conectar()
    try:
        busqueda = request.values.get("q", "").strip()[:100]
        id_operador = request.values.get("id_operador", type=int)
        operadores = conexion.execute("""SELECT id_operador,numero_empleado,nombre
            FROM operadores WHERE activo=1 AND (?='' OR CAST(numero_empleado AS TEXT) LIKE ? OR LOWER(nombre) LIKE LOWER(?))
            ORDER BY nombre LIMIT 300""", (busqueda, f"%{busqueda}%", f"%{busqueda}%")).fetchall()
        estaciones = conexion.execute("SELECT id_estacion,nombre_estacion FROM estaciones WHERE activa=1 ORDER BY id_estacion").fetchall()
        if request.method == "POST":
            id_operador = request.form.get("id_operador", type=int)
            id_estacion = request.form.get("id_estacion", type=int)
            estado = request.form.get("estado", "Pendiente")
            fecha_eval = request.form.get("fecha_evaluacion", "").strip() or None
            observaciones = request.form.get("observaciones", "").strip()[:500]
            if not any(o["id_operador"] == id_operador for o in operadores):
                flash("Selecciona un operador válido mediante el buscador.", "warning")
                return redirect(url_for("certificaciones", q=busqueda))
            if not any(e["id_estacion"] == id_estacion for e in estaciones):
                flash("Selecciona una estación válida.", "warning")
                return redirect(url_for("certificaciones", id_operador=id_operador, q=busqueda))
            if estado not in ("Pendiente", "En entrenamiento", "Evaluación programada", "Autorizado", "No aprobado"):
                abort(400)
            if estado == "Evaluación programada" and not fecha_eval:
                flash("Para programar una evaluación debes indicar la fecha.", "warning")
                return redirect(url_for("certificaciones", id_operador=id_operador, q=busqueda))
            if fecha_eval:
                date.fromisoformat(fecha_eval)
            try:
                conexion.execute("""INSERT INTO seguimiento_capacitacion
                    (id_operador,id_estacion,estado,fecha_evaluacion,observaciones,actualizado_por,actualizado_en)
                    VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(id_operador,id_estacion) DO UPDATE SET estado=excluded.estado,
                    fecha_evaluacion=excluded.fecha_evaluacion,observaciones=excluded.observaciones,
                    actualizado_por=excluded.actualizado_por,actualizado_en=CURRENT_TIMESTAMP""",
                    (id_operador,id_estacion,estado,fecha_eval,observaciones,session["id_usuario"]))
                if estado == "Autorizado":
                    conexion.execute("""INSERT INTO autorizaciones(id_operador,id_estacion,autorizado)
                        VALUES(?,?,1) ON CONFLICT(id_operador,id_estacion) DO UPDATE SET autorizado=1""", (id_operador,id_estacion))
                    conexion.execute("""UPDATE seguimiento_capacitacion SET fecha_ultima_evaluacion=?,fecha_evaluacion=NULL
                        WHERE id_operador=? AND id_estacion=?""", (date.today().isoformat(),id_operador,id_estacion))
                elif estado in ("Pendiente", "En entrenamiento", "Evaluación programada", "No aprobado"):
                    conexion.execute("""INSERT INTO autorizaciones(id_operador,id_estacion,autorizado)
                        VALUES(?,?,0) ON CONFLICT(id_operador,id_estacion) DO UPDATE SET autorizado=0""", (id_operador,id_estacion))
                conexion.commit()
                flash("Seguimiento de capacitación actualizado. La autorización se ajustó según el resultado registrado.", "success")
            except (ValueError, sqlite3.Error) as exc:
                conexion.rollback()
                flash(f"No se guardó el seguimiento: {exc}", "danger")
            return redirect(url_for("certificaciones", id_operador=id_operador, q=busqueda))
        registros = []
        autorizadas = set()
        if id_operador:
            registros = [dict(r) for r in conexion.execute("""SELECT sc.*,e.nombre_estacion
                FROM seguimiento_capacitacion sc JOIN estaciones e ON e.id_estacion=sc.id_estacion
                WHERE sc.id_operador=? ORDER BY e.id_estacion""", (id_operador,)).fetchall()]
            autorizadas = {r["id_estacion"] for r in conexion.execute(
                "SELECT id_estacion FROM autorizaciones WHERE id_operador=? AND autorizado=1", (id_operador,)).fetchall()}
        return render_template("certificaciones.html", operadores=operadores, estaciones=estaciones,
                               id_operador=id_operador, registros=registros, autorizadas=autorizadas, busqueda=busqueda)
    finally:
        conexion.close()


@app.route("/habilidades", methods=["GET", "POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def habilidades_estacion():
    """Matriz de habilidades para todas las estaciones activas."""
    conexion = conectar()
    try:
        id_operador = request.values.get("id_operador", type=int)
        busqueda = request.values.get("q", "").strip()[:100]
        operadores = conexion.execute("SELECT id_operador,numero_empleado,nombre FROM operadores WHERE activo=1 AND (?='' OR CAST(numero_empleado AS TEXT) LIKE ? OR LOWER(nombre) LIKE LOWER(?)) ORDER BY nombre LIMIT 300", (busqueda,f"%{busqueda}%",f"%{busqueda}%")).fetchall()
        estaciones = conexion.execute("SELECT id_estacion,nombre_estacion FROM estaciones WHERE activa=1 ORDER BY id_estacion").fetchall()
        if request.method == "POST":
            id_operador = request.form.get("id_operador", type=int)
            if not any(o["id_operador"] == id_operador for o in operadores):
                flash("Selecciona un operador válido.", "warning")
                return redirect(url_for("habilidades_estacion"))
            try:
                for e in estaciones:
                    nivel = request.form.get(f"nivel_{e['id_estacion']}", "Media")
                    if nivel not in ("Baja", "Media", "Alta"):
                        raise ValueError("Nivel de habilidad no válido.")
                    conexion.execute("""INSERT INTO habilidades_estacion(id_operador,id_estacion,nivel,actualizado_por,actualizado_en)
                        VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id_operador,id_estacion) DO UPDATE SET
                        nivel=excluded.nivel,actualizado_por=excluded.actualizado_por,actualizado_en=CURRENT_TIMESTAMP""",
                        (id_operador,e["id_estacion"],nivel,session["id_usuario"]))
                conexion.commit()
                flash("Habilidades guardadas para todas las estaciones activas.", "success")
                return redirect(url_for("habilidades_estacion", id_operador=id_operador))
            except (ValueError, sqlite3.Error) as error:
                conexion.rollback()
                flash(f"No se guardaron las habilidades: {error}", "danger")
        actuales = {}
        if id_operador:
            actuales = {r["id_estacion"]:r["nivel"] for r in conexion.execute(
                "SELECT id_estacion,nivel FROM habilidades_estacion WHERE id_operador=?",(id_operador,)).fetchall()}
        return render_template("habilidades.html", operadores=operadores, estaciones=estaciones,
                               id_operador=id_operador, actuales=actuales, busqueda=busqueda)
    finally:
        conexion.close()


@app.route("/restricciones/<int:id_restriccion>/seguimiento", methods=["POST"])
@requiere_rol("Enfermeria", "Administrador")
def seguimiento_restriccion(id_restriccion):
    """Registra revaloración, ampliación o cierre con auditoría de cambios."""
    accion = request.form.get("accion")
    nota = request.form.get("nota", "").strip()
    fin_nuevo = request.form.get("fecha_fin", "").strip() or None
    if accion not in ("revalorar", "ampliar", "finalizar") or not nota:
        flash("Selecciona una acción válida y agrega una nota de seguimiento.", "warning")
        return redirect(url_for("seguimiento_medico"))
    conexion = conectar()
    try:
        r = conexion.execute("SELECT * FROM restricciones_medicas WHERE id_restriccion=?",(id_restriccion,)).fetchone()
        if not r:
            abort(404)
        if r["estado"] != "Activa":
            flash("La restricción ya está finalizada; no se puede ampliar sin un nuevo registro autorizado.", "warning")
            return redirect(url_for("seguimiento_medico"))
        if accion == "ampliar":
            if not fin_nuevo:
                raise ValueError("Para ampliar, indica la nueva fecha de vencimiento.")
            date.fromisoformat(fin_nuevo)
            if fin_nuevo < r["fecha_inicio"] or (r["fecha_fin"] and fin_nuevo < r["fecha_fin"]):
                raise ValueError("La fecha nueva debe ser igual o posterior a la fecha de vencimiento actual.")
            conexion.execute("UPDATE restricciones_medicas SET fecha_fin=?,ultima_revision=?,requiere_revaloracion=1 WHERE id_restriccion=?",
                             (fin_nuevo,date.today().isoformat(),id_restriccion))
            tipo = "Ampliación"
        elif accion == "revalorar":
            conexion.execute("UPDATE restricciones_medicas SET ultima_revision=?,requiere_revaloracion=0 WHERE id_restriccion=?",
                             (date.today().isoformat(),id_restriccion))
            tipo = "Revaloración"
        else:
            conexion.execute("UPDATE restricciones_medicas SET estado='Finalizada',ultima_revision=?,requiere_revaloracion=0 WHERE id_restriccion=?",
                             (date.today().isoformat(),id_restriccion))
            tipo = "Finalización"
        conexion.execute("""INSERT INTO historial_restricciones(id_restriccion,tipo_evento,fecha_efectiva,fecha_fin_anterior,fecha_fin_nueva,nota_operativa,usuario_id)
            VALUES(?,?,?,?,?,?,?)""",(id_restriccion,tipo,date.today().isoformat(),r["fecha_fin"],fin_nuevo,nota,session["id_usuario"]))
        conexion.commit()
        flash("Seguimiento médico guardado en el historial.", "success")
    except (ValueError, sqlite3.Error) as error:
        conexion.rollback()
        flash(f"No se guardó el seguimiento: {error}", "danger")
    finally:
        conexion.close()
    return redirect(url_for("seguimiento_medico"))


@app.route("/seguimiento-medico")
@requiere_rol("Enfermeria", "Administrador")
def seguimiento_medico():
    conexion = conectar()
    try:
        hoy = date.today().isoformat()
        filas = conexion.execute("""SELECT r.id_restriccion,r.fecha_inicio,r.fecha_fin,r.estado,r.ultima_revision,
            o.numero_empleado,o.nombre,
            CASE WHEN r.estado='Activa' AND r.fecha_fin IS NOT NULL AND r.fecha_fin < ? THEN 'Vencida'
                 WHEN r.estado='Activa' AND r.fecha_fin = ? THEN 'Vence hoy'
                 WHEN r.estado='Activa' AND r.fecha_fin IS NOT NULL AND r.fecha_fin <= date(?, '+7 day') THEN 'Por vencer'
                 WHEN r.estado='Activa' AND (r.ultima_revision IS NULL OR r.ultima_revision <= date(?, '-30 day')) THEN 'Revalorar'
                 ELSE r.estado END AS alerta
            FROM restricciones_medicas r JOIN operadores o ON o.id_operador=r.id_operador
            WHERE r.archivada=0 ORDER BY CASE WHEN r.estado='Activa' THEN 0 ELSE 1 END, r.fecha_fin""",
            (hoy,hoy,hoy,hoy)).fetchall()
        eventos = conexion.execute("""SELECT h.*,o.nombre AS operador, o.numero_empleado, u.nombre_completo AS responsable
            FROM historial_restricciones h JOIN restricciones_medicas r ON r.id_restriccion=h.id_restriccion
            JOIN operadores o ON o.id_operador=r.id_operador LEFT JOIN usuarios u ON u.id_usuario=h.usuario_id
            ORDER BY h.creado_en DESC LIMIT 100""").fetchall()
        return render_template("seguimiento_medico.html", restricciones=filas, eventos=eventos)
    finally:
        conexion.close()


@app.route("/rotaciones/intercambio", methods=["GET", "POST"])
@requiere_rol("Lider", "Supervisor", "Administrador")
def intercambio_simultaneo():
    """Intercambia estaciones o sustituye una asignación con personal disponible."""
    conexion = conectar()
    try:
        id_rotacion = request.values.get("id_rotacion", type=int)
        rotaciones = conexion.execute("""SELECT r.id_rotacion,r.fecha,r.numero_rotacion,r.hora_inicio,l.nombre_linea
            FROM rotaciones r JOIN lineas l ON l.id_linea=r.id_linea
            WHERE r.estado!='Cancelada' ORDER BY r.fecha DESC,r.id_rotacion DESC LIMIT 200""").fetchall()
        asignaciones=[]; disponibles=[]
        rotacion = None
        if id_rotacion:
            rotacion=conexion.execute("""SELECT r.*,l.area,l.nombre_linea FROM rotaciones r
                JOIN lineas l ON l.id_linea=r.id_linea WHERE r.id_rotacion=? AND r.estado!='Cancelada'""",(id_rotacion,)).fetchone()
            if rotacion:
                grupo=obtener_grupo_lineas(conexion,rotacion['id_linea']) or [rotacion['id_linea']]
                marcas_grupo=','.join('?' for _ in grupo)
                asignaciones=conexion.execute(f"""SELECT a.id_asignacion,a.id_rotacion,a.id_operador,a.id_estacion,
                    a.hora_inicio,a.hora_fin,o.numero_empleado,o.nombre,e.nombre_estacion,
                    l.nombre_linea,r.numero_rotacion
                    FROM asignaciones a
                    JOIN rotaciones r ON r.id_rotacion=a.id_rotacion
                    JOIN lineas l ON l.id_linea=r.id_linea
                    JOIN operadores o ON o.id_operador=a.id_operador
                    JOIN estaciones e ON e.id_estacion=a.id_estacion
                    WHERE r.id_linea IN ({marcas_grupo}) AND r.fecha=? AND r.turno=?
                    AND r.hora_inicio=? AND r.estado!='Cancelada'
                    ORDER BY l.nombre_linea,o.nombre""",
                    [*grupo,rotacion['fecha'],rotacion['turno'],rotacion['hora_inicio']]).fetchall()
                hora_fin=conexion.execute("SELECT MAX(hora_fin) FROM asignaciones WHERE id_rotacion=?",(id_rotacion,)).fetchone()[0] or "23:59"
                grupo=obtener_grupo_lineas(conexion,rotacion['id_linea']) or [rotacion['id_linea']]
                marks=','.join('?' for _ in grupo)
                disponibles=conexion.execute(f"""SELECT DISTINCT o.id_operador,o.numero_empleado,o.nombre,l.nombre_linea AS linea_origen
                    FROM operadores o JOIN lineas l ON l.id_linea=o.id_linea
                    JOIN asistencia asi ON asi.id_operador=o.id_operador AND asi.fecha=? AND asi.estado='Presente'
                    WHERE o.activo=1 AND o.turno=? AND (
                        o.id_linea IN ({marks}) OR EXISTS (
                            SELECT 1 FROM prestamos_operadores pr WHERE pr.id_operador=o.id_operador
                            AND pr.id_linea_destino=? AND pr.estado='Aprobado'
                            AND pr.fecha_inicio<=? AND (pr.fecha_fin IS NULL OR pr.fecha_fin>=?)
                            AND (pr.hora_inicio IS NULL OR pr.hora_inicio<=?)
                            AND (pr.hora_fin IS NULL OR pr.hora_fin>=?)
                            AND (pr.hora_devolucion IS NULL OR pr.hora_devolucion>?)
                        ))
                    AND NOT EXISTS (
                        SELECT 1 FROM asignaciones ax JOIN rotaciones rx ON rx.id_rotacion=ax.id_rotacion
                        WHERE ax.id_operador=o.id_operador AND rx.fecha=? AND rx.turno=?
                        AND rx.estado!='Cancelada' AND ax.hora_inicio<? AND ax.hora_fin>?
                    ) AND NOT EXISTS (
                        SELECT 1 FROM prestamos_operadores px WHERE px.id_operador=o.id_operador
                        AND px.id_linea_origen=o.id_linea AND px.id_linea_destino<>? AND px.estado='Aprobado'
                        AND px.fecha_inicio<=? AND (px.fecha_fin IS NULL OR px.fecha_fin>=?)
                        AND (px.hora_inicio IS NULL OR px.hora_inicio<?)
                        AND (px.hora_fin IS NULL OR px.hora_fin>?)
                        AND (px.hora_devolucion IS NULL OR px.hora_devolucion>?)
                    ) ORDER BY o.nombre""",
                    [rotacion['fecha'], rotacion['turno'], *grupo,
                     rotacion['id_linea'], rotacion['fecha'], rotacion['fecha'],
                     rotacion['hora_inicio'], hora_fin, rotacion['hora_inicio'],
                     rotacion['fecha'], rotacion['turno'], hora_fin, rotacion['hora_inicio'],
                     rotacion['id_linea'], rotacion['fecha'], rotacion['fecha'],
                     hora_fin, rotacion['hora_inicio'], rotacion['hora_inicio']]).fetchall()
        if request.method == "POST":
            id_a=request.form.get("id_asignacion_a",type=int)
            # Un solo selector para el segundo participante: asignado o disponible.
            participante_b=request.form.get("participante_b","").strip()
            id_b=None
            id_disponible=None
            if participante_b.startswith("asignacion:"):
                id_b=int(participante_b.split(":",1)[1])
            elif participante_b.startswith("disponible:"):
                id_disponible=int(participante_b.split(":",1)[1])
            else:
                # Compatibilidad con formularios de versiones anteriores.
                id_b=request.form.get("id_asignacion_b",type=int)
                id_disponible=request.form.get("id_operador_disponible",type=int)
            motivo=request.form.get("motivo","").strip()
            if not id_a or not motivo:
                raise ValueError("Selecciona la asignación que deseas modificar y registra el motivo.")
            a=conexion.execute("""SELECT x.*,r.id_linea,r.fecha,r.turno,r.estado,r.numero_rotacion,
                r.hora_inicio AS hora_rotacion_inicio,l.area,l.nombre_linea,e.nombre_estacion,ea.postura
                FROM asignaciones x JOIN rotaciones r ON r.id_rotacion=x.id_rotacion
                JOIN lineas l ON l.id_linea=r.id_linea JOIN estaciones e ON e.id_estacion=x.id_estacion
                JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area
                WHERE x.id_asignacion=?""",(id_a,)).fetchone()
            grupo_intercambio=obtener_grupo_lineas(conexion,rotacion['id_linea']) if rotacion else []
            if (not a or not rotacion or a['id_linea'] not in grupo_intercambio
                    or a['fecha']!=rotacion['fecha'] or a['turno']!=rotacion['turno']
                    or a['hora_rotacion_inicio']!=rotacion['hora_inicio']
                    or a['hora_inicio']!=rotacion['hora_inicio']
                    or a['estado']=='Cancelada'):
                raise ValueError("La primera asignación debe pertenecer al mismo periodo y al grupo de líneas seleccionado.")
            rotaciones_afectadas=[a['id_rotacion']]
            mensaje_exito="Cambio aplicado y registrado en el historial."

            if id_b:
                b=conexion.execute("""SELECT x.*,r.id_linea,r.fecha,r.turno,r.estado,r.numero_rotacion,
                    r.hora_inicio AS hora_rotacion_inicio,l.area,l.nombre_linea,e.nombre_estacion,ea.postura
                    FROM asignaciones x JOIN rotaciones r ON r.id_rotacion=x.id_rotacion
                    JOIN lineas l ON l.id_linea=r.id_linea
                    JOIN estaciones e ON e.id_estacion=x.id_estacion
                    JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area
                    WHERE x.id_asignacion=?""",(id_b,)).fetchone()
                if (not b or id_b==id_a or b['id_operador']==a['id_operador'] or b['id_linea'] not in grupo_intercambio
                        or b['fecha']!=a['fecha'] or b['turno']!=a['turno']
                        or b['hora_rotacion_inicio']!=a['hora_rotacion_inicio']
                        or b['hora_inicio']!=a['hora_inicio'] or b['hora_fin']!=a['hora_fin']
                        or b['estado']=='Cancelada'):
                    raise ValueError("Para intercambiar, ambas personas deben pertenecer al mismo grupo y al mismo periodo de rotación.")
                for op, estacion in ((a,b['id_estacion']),(b,a['id_estacion'])):
                    if not conexion.execute("SELECT 1 FROM autorizaciones WHERE id_operador=? AND id_estacion=? AND autorizado=1",(op['id_operador'],estacion)).fetchone():
                        raise ValueError("Intercambio rechazado: una persona no está autorizada para la estación destino.")
                    if conexion.execute("""SELECT 1 FROM restricciones_medicas r JOIN detalle_restriccion d ON d.id_restriccion=r.id_restriccion
                        WHERE r.id_operador=? AND r.estado='Activa' AND r.fecha_inicio<=? AND (r.fecha_fin IS NULL OR r.fecha_fin>=?)
                        AND d.id_estacion=? AND d.permitida=0 LIMIT 1""",(op['id_operador'],a['fecha'],a['fecha'],estacion)).fetchone():
                        raise ValueError("Intercambio rechazado: una estación está bloqueada por restricción médica vigente.")
                for op, nueva in ((a,b),(b,a)):
                    repeticion=conexion.execute("""SELECT 1 FROM asignaciones x JOIN rotaciones r ON r.id_rotacion=x.id_rotacion
                        WHERE x.id_operador=? AND r.fecha=? AND r.turno=? AND r.estado!='Cancelada'
                        AND x.id_asignacion!=? AND x.id_estacion=? LIMIT 1""",(op['id_operador'],a['fecha'],a['turno'],op['id_asignacion'],nueva['id_estacion'])).fetchone()
                    if repeticion: raise ValueError("Intercambio rechazado: una persona repetiría estación en otro periodo del turno.")
                for op,nueva in ((a,b),(b,a)):
                    vecinos=conexion.execute("""SELECT r.numero_rotacion,e.nombre_estacion,ea.postura FROM asignaciones x
                        JOIN rotaciones r ON r.id_rotacion=x.id_rotacion JOIN lineas l ON l.id_linea=r.id_linea
                        JOIN estaciones e ON e.id_estacion=x.id_estacion JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area
                        WHERE x.id_operador=? AND r.fecha=? AND r.turno=? AND r.estado!='Cancelada'
                        AND x.id_asignacion!=? ORDER BY r.numero_rotacion""",(op['id_operador'],a['fecha'],a['turno'],op['id_asignacion'])).fetchall()
                    anterior=next((v for v in reversed(vecinos) if v['numero_rotacion']<op['numero_rotacion']),None)
                    siguiente=next((v for v in vecinos if v['numero_rotacion']>op['numero_rotacion']),None)
                    if anterior:
                        ok,detalle=validar_secuencia(anterior['nombre_estacion'],nueva['nombre_estacion'],anterior['postura'],nueva['postura'])
                        if not ok: raise ValueError(f"Intercambio rechazado: {detalle}")
                    if siguiente:
                        ok,detalle=validar_secuencia(nueva['nombre_estacion'],siguiente['nombre_estacion'],nueva['postura'],siguiente['postura'])
                        if not ok: raise ValueError(f"Intercambio rechazado por la siguiente rotación: {detalle}")
                conexion.execute("BEGIN IMMEDIATE")
                conexion.execute("UPDATE asignaciones SET id_estacion=? WHERE id_asignacion=?",(b['id_estacion'],id_a))
                conexion.execute("UPDATE asignaciones SET id_estacion=? WHERE id_asignacion=?",(a['id_estacion'],id_b))
                descripcion=(f"Intercambio simultáneo entre {a['nombre_linea']} y {b['nombre_linea']}: "
                    f"operador {a['id_operador']} ({a['nombre_estacion']}) ↔ "
                    f"operador {b['id_operador']} ({b['nombre_estacion']}). Sin préstamo; cada operador conserva su línea.")
                tipo="Intercambio simultáneo entre líneas del grupo"
                mensaje_exito="Intercambio aplicado y registrado en el historial de ambas líneas. Los operadores conservan su línea de origen; no se generó un préstamo."
                rotaciones_afectadas=list(dict.fromkeys([a['id_rotacion'],b['id_rotacion']]))
            elif id_disponible:
                linea=conexion.execute("SELECT area FROM lineas WHERE id_linea=?",(a['id_linea'],)).fetchone()
                grupo=obtener_grupo_lineas(conexion,a['id_linea']) or [a['id_linea']]
                hora_fin=a['hora_fin']; hora_inicio=a['hora_inicio']
                marks=','.join('?' for _ in grupo)
                candidato=conexion.execute(f"""SELECT o.id_operador,o.id_linea,o.nombre,o.numero_empleado FROM operadores o
                    JOIN asistencia asi ON asi.id_operador=o.id_operador AND asi.fecha=? AND asi.estado='Presente'
                    WHERE o.id_operador=? AND o.activo=1 AND o.turno=? AND (
                        o.id_linea IN ({marks}) OR EXISTS(SELECT 1 FROM prestamos_operadores pr WHERE pr.id_operador=o.id_operador
                        AND pr.id_linea_destino=? AND pr.estado='Aprobado' AND pr.fecha_inicio<=? AND (pr.fecha_fin IS NULL OR pr.fecha_fin>=?)
                        AND (pr.hora_inicio IS NULL OR pr.hora_inicio<=?) AND (pr.hora_fin IS NULL OR pr.hora_fin>=?)
                        AND (pr.hora_devolucion IS NULL OR pr.hora_devolucion>?)))
                    AND NOT EXISTS(SELECT 1 FROM asignaciones ax JOIN rotaciones rx ON rx.id_rotacion=ax.id_rotacion
                        WHERE ax.id_operador=o.id_operador AND rx.fecha=? AND rx.turno=? AND rx.estado!='Cancelada'
                        AND ax.hora_inicio<? AND ax.hora_fin>?)
                    AND NOT EXISTS(SELECT 1 FROM prestamos_operadores px WHERE px.id_operador=o.id_operador
                        AND px.id_linea_origen=o.id_linea AND px.id_linea_destino<>? AND px.estado='Aprobado'
                        AND px.fecha_inicio<=? AND (px.fecha_fin IS NULL OR px.fecha_fin>=?)
                        AND (px.hora_inicio IS NULL OR px.hora_inicio<?) AND (px.hora_fin IS NULL OR px.hora_fin>?)
                        AND (px.hora_devolucion IS NULL OR px.hora_devolucion>?))""",
                    [a['fecha'],id_disponible,a['turno'],*grupo,a['id_linea'],a['fecha'],a['fecha'],a['hora_inicio'],hora_fin,a['hora_inicio'],a['fecha'],a['turno'],hora_fin,hora_inicio,a['id_linea'],a['fecha'],a['fecha'],hora_fin,hora_inicio,hora_inicio]).fetchone()
                if not candidato: raise ValueError("Ese operador ya no está disponible, no confirmó asistencia o pertenece a otra línea sin préstamo autorizado.")
                if not conexion.execute("SELECT 1 FROM autorizaciones WHERE id_operador=? AND id_estacion=? AND autorizado=1",(id_disponible,a['id_estacion'])).fetchone():
                    raise ValueError("El operador disponible no está autorizado para la estación de destino.")
                if conexion.execute("""SELECT 1 FROM restricciones_medicas r JOIN detalle_restriccion d ON d.id_restriccion=r.id_restriccion
                    WHERE r.id_operador=? AND r.estado='Activa' AND r.fecha_inicio<=? AND (r.fecha_fin IS NULL OR r.fecha_fin>=?)
                    AND d.id_estacion=? AND d.permitida=0 LIMIT 1""",(id_disponible,a['fecha'],a['fecha'],a['id_estacion'])).fetchone():
                    raise ValueError("El operador disponible tiene una restricción activa para esa estación.")
                repeticion=conexion.execute("""SELECT 1 FROM asignaciones x JOIN rotaciones r ON r.id_rotacion=x.id_rotacion
                    WHERE x.id_operador=? AND r.fecha=? AND r.turno=? AND r.estado!='Cancelada' AND x.id_estacion=? LIMIT 1""",
                    (id_disponible,a['fecha'],a['turno'],a['id_estacion'])).fetchone()
                if repeticion: raise ValueError("El operador repetiría una estación durante el turno.")
                vecinos=conexion.execute("""SELECT r.numero_rotacion,e.nombre_estacion,ea.postura FROM asignaciones x
                    JOIN rotaciones r ON r.id_rotacion=x.id_rotacion JOIN lineas l ON l.id_linea=r.id_linea
                    JOIN estaciones e ON e.id_estacion=x.id_estacion JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=l.area
                    WHERE x.id_operador=? AND r.fecha=? AND r.turno=? AND r.estado!='Cancelada'
                    ORDER BY r.numero_rotacion""",(id_disponible,a['fecha'],a['turno'])).fetchall()
                anterior=next((v for v in reversed(vecinos) if v['numero_rotacion']<a['numero_rotacion']),None)
                siguiente=next((v for v in vecinos if v['numero_rotacion']>a['numero_rotacion']),None)
                if anterior:
                    ok,detalle=validar_secuencia(anterior['nombre_estacion'],a['nombre_estacion'],anterior['postura'],a['postura'])
                    if not ok: raise ValueError(f"No se puede incorporar al operador: {detalle}")
                if siguiente:
                    ok,detalle=validar_secuencia(a['nombre_estacion'],siguiente['nombre_estacion'],a['postura'],siguiente['postura'])
                    if not ok: raise ValueError(f"No se puede incorporar al operador por la siguiente rotación: {detalle}")
                prestamo=conexion.execute("""SELECT id_linea_origen FROM prestamos_operadores WHERE id_operador=?
                    AND id_linea_destino=? AND estado='Aprobado' AND fecha_inicio<=? AND (fecha_fin IS NULL OR fecha_fin>=?)
                    AND (hora_inicio IS NULL OR hora_inicio<=?) AND (hora_fin IS NULL OR hora_fin>=?)
                    AND (hora_devolucion IS NULL OR hora_devolucion>?)
                    ORDER BY fecha_solicitud DESC LIMIT 1""",(id_disponible,a['id_linea'],a['fecha'],a['fecha'],a['hora_inicio'],a['hora_fin'],a['hora_inicio'])).fetchone()
                es_prestado=1 if prestamo else 0
                origen=prestamo['id_linea_origen'] if prestamo else None
                conexion.execute("BEGIN IMMEDIATE")
                conexion.execute("UPDATE asignaciones SET id_operador=?,es_prestado=?,id_linea_origen=? WHERE id_asignacion=?",
                    (id_disponible,es_prestado,origen,id_a))
                descripcion=f"Sustitución por operador disponible {candidato['numero_empleado']} — {candidato['nombre']}; operador anterior {a['id_operador']} queda disponible"
                tipo="Sustitución por operador disponible"
                mensaje_exito="El operador disponible ocupó la estación seleccionada. El cambio quedó registrado en el historial."
            else:
                raise ValueError("Selecciona una segunda asignación para intercambiar estaciones o un operador disponible para sustituir.")
            for id_rotacion_afectada in rotaciones_afectadas:
                conexion.execute("UPDATE rotaciones SET estado='Modificada' WHERE id_rotacion=?",(id_rotacion_afectada,))
                conexion.execute("INSERT INTO historial_cambios(id_rotacion,descripcion,motivo,usuario_responsable,tipo_cambio) VALUES(?,?,?,?,?)",
                    (id_rotacion_afectada,descripcion,motivo,session['id_usuario'],tipo))
            conexion.commit()
            flash(mensaje_exito,"success")
            return redirect(url_for("rotaciones",fecha=a['fecha'],id_linea=a['id_linea'],turno=a['turno']))
        return render_template("intercambio.html",rotaciones=rotaciones,id_rotacion=id_rotacion,
            asignaciones=asignaciones,disponibles=disponibles,rotacion=rotacion)
    except (ValueError, sqlite3.Error) as error:
        conexion.rollback()
        if isinstance(error, sqlite3.Error):
            app.logger.exception("Error de base de datos al cargar o aplicar un intercambio")
        flash(f"No se pudo completar la operación: {error}", "danger")
        if request.method == "POST":
            return redirect(url_for("intercambio_simultaneo", id_rotacion=request.values.get("id_rotacion", "")))
        # Evita redirigir indefinidamente cuando falla una consulta durante la carga.
        return render_template("intercambio.html", rotaciones=rotaciones, id_rotacion=id_rotacion,
            asignaciones=asignaciones, disponibles=disponibles, rotacion=rotacion)
    finally:
        conexion.close()


if __name__ == "__main__":
    crear_base_datos()
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
