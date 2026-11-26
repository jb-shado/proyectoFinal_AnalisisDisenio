"""Inicio de sesión, recuperación de contraseña y menú principal (datos simulados).

Cuando conectes PostgreSQL, valida contra la tabla usuarios (con hash de contraseña).
Requiere SECRET_KEY en config.py para usar session y flash.
"""
from flask import flash, redirect, render_template, request, session, url_for

from . import comun_bp

# usuario -> (clave, rol, nombre). El rol decide qué módulos aparecen en el menú.
USUARIOS = {
    "jefe": ("1234", "jefe_produccion", "Jefe de producción"),
    "conta": ("1234", "contador", "Contador"),
    "vendedor": ("1234", "vendedor", "Vendedor"),
    "rrhh": ("1234", "rrhh", "Recursos humanos"),
    "calidad": ("1234", "calidad", "Calidad"),
    "admin": ("1234", "administrador", "Administrador"),
}
CODIGO_VERIFICACION = "123456"

# (módulo, rol que lo usa, endpoint de su panel, descripción)
MODULOS = [
    ("Compras", "comprador", "compras.panel", "Comprador"),
    ("Inventarios", "almacenero", "almacen.panel", "Almacenero"),
    ("Producción", "jefe_produccion", "jefe.panel", "Jefe de producción"),
    ("Calidad y trazabilidad", "calidad", "calidad.panel", "Calidad"),
    ("Ventas", "vendedor", "ventas.panel", "Vendedor"),
    ("Finanzas", "contador", "finanzas.panel", "Contador"),
    ("Recursos humanos", "rrhh", "rrhh.panel", "RR. HH."),
    ("Reportes y panel", "gerente", "gerente.panel", "Gerente"),
    ("Administración", "administrador", "admin.panel", "Administrador"),
]


@comun_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        datos = USUARIOS.get(usuario)
        if datos and datos[0] == request.form.get("clave", ""):
            session["usuario"], session["rol"], session["nombre"] = usuario, datos[1], datos[2]
            return redirect(url_for("/.menu"))
        flash("Usuario o contraseña incorrectos. Revisa los datos e inténtalo de nuevo.", "error")
    return render_template("acceso_comun/login.html")


@comun_bp.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "POST":
        session["recuperando"] = request.form.get("usuario", "").strip().lower()
        flash("Si el usuario existe, enviamos un código de verificación a su correo.", "ok")
        return redirect(url_for("/.verificar"))
    return render_template("acceso_comun/recuperar.html")


@comun_bp.route("/recuperar/verificar", methods=["GET", "POST"])
def verificar():
    if request.method == "POST":
        f = request.form
        if f.get("codigo") != CODIGO_VERIFICACION:
            flash("El código no es correcto.", "error")
        elif len(f.get("clave", "")) < 4 or f.get("clave") != f.get("repetir"):
            flash("Las contraseñas deben coincidir y tener al menos 4 caracteres.", "error")
        else:
            usuario = session.pop("recuperando", None)
            if usuario in USUARIOS:
                USUARIOS[usuario] = (f["clave"],) + USUARIOS[usuario][1:]
            flash("Contraseña actualizada. Ya puedes iniciar sesión.", "ok")
            return redirect(url_for("/.login"))
    return render_template("acceso_comun/verificar.html")


@comun_bp.route("/menu")
def menu():
    rol = session.get("rol")
    if not rol:
        return redirect(url_for("/.login"))
    modulos = [dict(titulo=t, sub=s, url=url_for(ep)) for t, r, ep, s in MODULOS if rol == r or rol == "administrador"]
    return render_template("acceso_comun/menu.html", nombre=session.get("nombre"), modulos=modulos)


@comun_bp.route("/salir")
def salir():
    session.clear()
    flash("Cerraste sesión.", "ok")
    return redirect(url_for("/.login"))
