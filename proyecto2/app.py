# Archivo comentado de app.py: explicaciones en español sobre la función de cada sección/línea
from flask import Flask, render_template, request, redirect, url_for, session, flash
# Importa Flask y utilidades de renderizado, manejo de peticiones, redirecciones y sesión
import mysql.connector
# Cliente MySQL para conectar a la base de datos
from mysql.connector import Error
# Importa la excepción Error de mysql.connector
import hashlib
# Biblioteca para calcular hashes (se usa SHA-256 en el original)

app = Flask(__name__)
# Crea la aplicación Flask
app.secret_key = "cambia-esta-clave-secreta"  # IMPORTANTE: cambiar en producción
# Clave secreta usada por Flask para sesiones y seguridad (cambiar en producción)

# Configuración MySQL (ajusta usuario y contraseña)
DB_CONFIG = {
    "host": "localhost",
    "user": "root",      # Cambia esto
    "password": "mc2025",  # Cambia esto
    "database":"tienda_de_ropa"
}
# Diccionario con parámetros de conexión a MySQL


def get_connection(use_db=True):
    """Devuelve una conexión a MySQL."""
    # Función ayudante para abrir la conexión MySQL usando DB_CONFIG
    try:
        config = DB_CONFIG.copy()
        # Si no se quiere usar database, lo removemos
        if not use_db:
            config.pop("database", None)
        else:
            config["database"] = "tienda_de_ropa"
        conn = mysql.connector.connect(**config)
        return conn
    except Error as e:
        print("Error de conexión:", e)
        return None


def init_db():
    """Crea base de datos, tablas y superusuario si no existen."""
    # Inicializa esquema y crea un superusuario por defecto
    try:
        conn = get_connection(use_db=False)
        cursor = conn.cursor()

        # Crear base de datos
        cursor.execute("CREATE DATABASE IF NOT EXISTS tienda_de_ropa")
        cursor.execute("USE tienda_de_ropa")

        # Tabla usuarios: la siguiente línea crea la tabla si no existe
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                password VARCHAR(255) NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                apellido VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL,
                telefono VARCHAR(20),
                direccion VARCHAR(200),
                    activo TINYINT(1) DEFAULT 1,
                    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (email)
             )
 """)
        # NOTA: se mantiene el literal SQL sin comentarios internos para evitar romperlo

        # Tabla actividad: crea la tabla de logs de acciones de usuario
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actividad_usuarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                usuario_id INT NOT NULL,
                accion VARCHAR(100) NOT NULL,
                descripcion TEXT,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
            )
        """)

        # Crear superusuario si no existe (inserta ignorando si ya existe)
        password_hash = hashlib.sha256("super123".encode()).hexdigest()
        cursor.execute("""
            INSERT IGNORE INTO usuarios (password, nombre, apellido, email, activo)
            VALUES (%s, %s, %s, %s, %s)
        """, (password_hash, 'Super', 'Usuario', 'supersu@sistema.com', 1))

        conn.commit()
        cursor.close()
        conn.close()
        print("Base de datos inicializada correctamente.")
    except Error as e:
        print("Error al inicializar la base de datos:", e)


def registrar_actividad(usuario_id, accion, descripcion=""):
    # Inserta un registro de actividad en la tabla actividad_usuarios
    conn = get_connection()
    if not conn:
        return
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO actividad_usuarios (usuario_id, accion, descripcion)
        VALUES (%s, %s, %s)
    """, (usuario_id, accion, descripcion))
    conn.commit()
    cursor.close()
    conn.close()


def get_usuario_actual():
    """Devuelve el usuario actual desde la sesión (como dict) o None."""
    # Verifica si hay usuario logueado en la sesión
    if "usuario_id" not in session:
        return None

    conn = get_connection()
    if not conn:
        return None
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (session["usuario_id"],))
    usuario = cursor.fetchone()
    cursor.close()
    conn.close()
    return usuario


def login_requerido(func):
    """Decorator simple para proteger rutas."""
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Si no hay usuario en sesión, redirige al login
        if "usuario_id" not in session:
            flash("Debe iniciar sesión.", "warning")
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    # Ruta de login (también la raíz). Si ya hay sesión muestra opciones
    if "usuario_id" in session:
        usuario = get_usuario_actual()
        return render_template("login.html", usuario=usuario)

    if request.method == "POST":
        # Obtiene email y password del formulario
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email  or not password:
            flash("Complete todos los campos.", "warning")
            return redirect(url_for("login"))

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_connection()
        if not conn:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect(url_for("login"))

        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM usuarios
            WHERE email = %s AND password = %s 
        """, (email,password_hash))
        usuario = cursor.fetchone()
        cursor.close()
        conn.close()

        if usuario:
            # Si existe coincidencia, crea sesión y registra actividad
            session["usuario_id"] = usuario["id"]
            session["email"] = usuario["email"]
            registrar_actividad(usuario["id"], "Login", "Inicio de sesión exitoso")
            return redirect(url_for("dashboard"))
        else:
            flash("Usuario o contraseña incorrectos.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
@login_requerido
def logout():
    # Cierra la sesión y registra la actividad
    usuario = get_usuario_actual()
    if usuario:
        registrar_actividad(usuario["id"], "Logout", "Cerró sesión")
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_requerido
def dashboard():
    # Muestra el panel principal para el usuario logueado
    usuario = get_usuario_actual()
    return render_template("dashboard.html", usuario=usuario)


@app.route("/usuarios")
@login_requerido
def lista_usuarios():
    # Lista todos los usuarios desde la base de datos
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios")
    usuarios = cursor.fetchall()
    cursor.close()
    conn.close()

    usuario_actual = get_usuario_actual()
    registrar_actividad(usuario_actual["id"], "Consulta", "Consultó lista de usuarios")

    return render_template("usuarios_list.html", usuarios=usuarios)


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_requerido
def nuevo_usuario():
    # Alta de un nuevo usuario (solo accesible si estás logueado)
    if request.method == "POST":
       # username = request.form.get(, "").strip()
        password = request.form.get("password", "").strip()
        nombre = request.form.get("nombre", "").strip()
        apellido = request.form.get("apellido", "").strip()
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        direccion = request.form.get("direccion", "").strip()

        if not (email and password and nombre and apellido and email):
            flash("Complete los campos obligatorios (*).", "warning")
            return redirect(url_for("nuevo_usuario"))

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usuarios ( password, nombre, apellido, email, telefono, direccion, activo)
                VALUES ( %s, %s, %s, %s, %s, %s, %s)
            """, ( password_hash, nombre, apellido, email, telefono, direccion, 1))
            conn.commit()
            cursor.close()
            conn.close()

            usuario_actual = get_usuario_actual()
            registrar_actividad(usuario_actual["id"], "Alta Usuario", f"Creó usuario: {email}")

            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("lista_usuarios"))
        except Error as e:
            flash(f"Error al crear usuario: {e}", "danger")
            return redirect(url_for("nuevo_usuario"))

    return render_template("usuario_form.html", modo="nuevo", usuario=None)


@app.route("/registro", methods=["GET", "POST"])
def registro():
    # Ruta pública para que un usuario se registre por sí mismo
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        nombre = request.form.get("nombre", "").strip()
        apellido = request.form.get("apellido", "").strip()
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        direccion = request.form.get("direccion", "").strip()

        if not (email and password and nombre and apellido):
            flash("Complete los campos obligatorios (*).", "warning")
            return redirect(url_for("registro"))

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_connection()
        if not conn:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect(url_for("registro"))

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usuarios (password, nombre, apellido, email, telefono, direccion, activo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (password_hash, nombre, apellido, email, telefono, direccion, 1))
            conn.commit()
            new_id = cursor.lastrowid
            cursor.close()
            conn.close()

            # Loguear al usuario recién creado
            session["usuario_id"] = new_id
            session["email"] = email

            registrar_actividad(new_id, "Registro", "Registró una nueva cuenta")

            flash("Registro exitoso. Bienvenido!", "success")
            return redirect(url_for("dashboard"))
        except Error as e:
            flash(f"Error al registrar usuario: {e}", "danger")
            return redirect(url_for("registro"))

    return render_template("usuario_form.html", modo="registro", usuario=None)


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_requerido
def editar_usuario(usuario_id):
    # Edita los datos de un usuario dado su id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM usuarios WHERE id = %s", (usuario_id,))
    usuario = cursor.fetchone()

    if not usuario:
        cursor.close()
        conn.close()
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("lista_usuarios"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        apellido = request.form.get("apellido", "").strip()
        email = request.form.get("email", "").strip()
        telefono = request.form.get("telefono", "").strip()
        direccion = request.form.get("direccion", "").strip()
        activo = 1 if request.form.get("activo") == "on" else 0

        cursor.execute("""
            UPDATE usuarios
            SET nombre=%s, apellido=%s, email=%s, telefono=%s, direccion=%s, activo=%s
            WHERE id=%s
        """, (nombre, apellido, email, telefono, direccion, activo, usuario_id))
        conn.commit()
        cursor.close()
        conn.close()

        usuario_actual = get_usuario_actual()
        registrar_actividad(usuario_actual["id"], "Modificación", f"Modificó usuario ID: {usuario_id}")

        flash("Usuario actualizado correctamente.", "success")
        return redirect(url_for("lista_usuarios"))

    cursor.close()
    conn.close()
    return render_template("usuario_form.html", modo="editar", usuario=usuario)


@app.route("/usuarios/<int:usuario_id>/baja", methods=["POST"])
@login_requerido
def baja_usuario(usuario_id):
    # Marca de baja (lógica comentada en el original) evitando que el usuario se borre a sí mismo
    usuario_actual = get_usuario_actual()

    if usuario_actual["id"] == usuario_id:
        flash("No puede darse de baja a sí mismo.", "warning")
        return redirect(url_for("lista_usuarios"))

    conn = get_connection()
    cursor = conn.cursor()
    # En el original la línea de actualización está comentada; aquí se mantiene comentada
    # cursor.execute("UPDATE usuarios SET activo = FALSE WHERE id = %s", (usuario_id,))
    conn.commit()
    cursor.close()
    conn.close()

    registrar_actividad(usuario_actual["id"], "Baja Usuario", f"Dio de baja usuario ID: {usuario_id}")
    flash("Usuario dado de baja correctamente.", "success")
    return redirect(url_for("lista_usuarios"))


@app.route("/actividad")
@login_requerido
def actividad():
    # Recupera registros de actividad y los muestra
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, u.email, a.accion, a.descripcion, a.fecha
        FROM actividad_usuarios a
        JOIN usuarios u ON a.usuario_id = u.id
        ORDER BY a.fecha DESC
        LIMIT 200
    """)
    registros = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("actividad.html", registros=registros)


if __name__ == "__main__":
    # Inicializa la BD si es necesario y arranca el servidor en modo debug
    init_db()
    app.run(debug=True)