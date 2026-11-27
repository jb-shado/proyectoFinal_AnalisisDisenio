import csv
import io
import re
import unicodedata
from datetime import datetime

from flask import abort, flash, make_response, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from . import admin_bp

MENU = [
    ("Panel", "admin.panel", "Resumen general"),
    ("Usuarios", "admin.usuarios", "Registro y mantenimiento"),
    ("Roles y permisos", "admin.roles", "Asignación de accesos"),
    ("Configuración", "admin.configuracion", "Parámetros generales"),
    ("Datos y catálogos", "admin.catalogos", "Información compartida"),
    ("Actividad", "admin.actividad", "Auditoría del sistema"),
    ("Reportes", "admin.reportes", "Resumen de usuarios"),
]

PERMISOS = [
    dict(id="panel.view", nombre="Ver panel principal", grupo="Sistema"),
    dict(id="users.manage", nombre="Registrar y modificar usuarios", grupo="Seguridad"),
    dict(id="roles.manage", nombre="Administrar roles y permisos", grupo="Seguridad"),
    dict(id="config.manage", nombre="Cambiar configuración", grupo="Sistema"),
    dict(id="catalogs.manage", nombre="Administrar datos y catálogos", grupo="Datos"),
    dict(id="audit.view", nombre="Consultar auditoría", grupo="Seguridad"),
    dict(id="reports.view", nombre="Consultar reportes", grupo="Gerencia"),
    dict(id="production.view", nombre="Consultar producción", grupo="Operaciones"),
    dict(id="inventory.view", nombre="Consultar inventarios", grupo="Operaciones"),
    dict(id="finance.view", nombre="Consultar finanzas", grupo="Gerencia"),
    dict(id="quality.view", nombre="Consultar calidad", grupo="Operaciones"),
    dict(id="hr.view", nombre="Consultar recursos humanos", grupo="Personal"),
    dict(id="client.portal", nombre="Acceder al portal de clientes", grupo="Clientes"),
]
TODOS_LOS_PERMISOS = {permiso["id"] for permiso in PERMISOS}
PERMISOS_ADMIN_OBLIGATORIOS = {
    "panel.view", "users.manage", "roles.manage", "config.manage",
    "catalogs.manage", "audit.view",
}

ROLES = [
    dict(id="gerente", nombre="Gerente", descripcion="Supervisión e informes empresariales",
         activo=True, permisos=["panel.view", "reports.view", "production.view", "inventory.view", "finance.view"]),
    dict(id="jefe_produccion", nombre="Jefe de Producción", descripcion="Supervisión de producción",
         activo=True, permisos=["panel.view", "production.view"]),
    dict(id="almacenero", nombre="Almacenero", descripcion="Control de inventarios",
         activo=True, permisos=["panel.view", "inventory.view"]),
    dict(id="comprador", nombre="Comprador", descripcion="Gestión de compras",
         activo=True, permisos=["panel.view", "inventory.view"]),
    dict(id="vendedor", nombre="Vendedor", descripcion="Gestión de ventas",
         activo=True, permisos=["panel.view"]),
    dict(id="contador", nombre="Contador", descripcion="Contabilidad y finanzas",
         activo=True, permisos=["panel.view", "finance.view", "reports.view"]),
    dict(id="calidad", nombre="Calidad", descripcion="Controles de calidad",
         activo=True, permisos=["panel.view", "quality.view"]),
    dict(id="administrador", nombre="Administrador", descripcion="Administración del sistema",
         activo=True, permisos=sorted(TODOS_LOS_PERMISOS)),
    dict(id="cliente", nombre="Cliente", descripcion="Acceso al portal de clientes",
         activo=True, permisos=["client.portal"]),
    dict(id="rrhh", nombre="Recursos Humanos", descripcion="Administración de personal",
         activo=True, permisos=["panel.view", "hr.view"]),
]
ROLES_VALIDOS = {rol["id"] for rol in ROLES}
ETIQUETAS_ROL = {rol["id"]: rol["nombre"] for rol in ROLES}

# Datos de demostración: se reemplazarán por consultas cuando se conecte PostgreSQL.
USUARIOS = [
    dict(id=1, nombre_usuario="admin", email="admin@erp.local",
         nombre_completo="Administrador del Sistema", rol="administrador",
         activo=True, fecha_creacion="2026-01-01 09:00", password_hash=""),
    dict(id=2, nombre_usuario="calidad1", email="calidad1@erp.local",
         nombre_completo="Roberto Villacorta", rol="calidad",
         activo=True, fecha_creacion="2026-01-02 09:00", password_hash=""),
    dict(id=3, nombre_usuario="produccion1", email="produccion1@erp.local",
         nombre_completo="María López", rol="jefe_produccion",
         activo=True, fecha_creacion="2026-01-03 09:00", password_hash=""),
    dict(id=4, nombre_usuario="vendedor1", email="vendedor1@erp.local",
         nombre_completo="Juan Flores", rol="vendedor",
         activo=True, fecha_creacion="2026-01-04 09:00", password_hash=""),
    dict(id=5, nombre_usuario="almacen1", email="almacen1@erp.local",
         nombre_completo="Ana Rojas", rol="almacenero",
         activo=False, fecha_creacion="2026-01-05 09:00", password_hash=""),
]
ACTIVIDADES = []
CONFIGURACION = {
    "nombre_empresa": "ERP Alimentos",
    "moneda": "BOB",
    "zona_horaria": "America/La_Paz",
    "intentos_maximos": 5,
    "duracion_sesion": 30,
    "modo_mantenimiento": False,
}
CATALOGOS = {
    "categorias": [
        dict(id=1, nombre="Lácteos", descripcion="Productos y derivados lácteos", activo=True),
        dict(id=2, nombre="Panadería", descripcion="Productos horneados", activo=True),
        dict(id=3, nombre="Bebidas", descripcion="Jugos y bebidas", activo=True),
    ],
    "unidades": [
        dict(id=1, nombre="Unidad", descripcion="Pieza o producto individual", activo=True),
        dict(id=2, nombre="Kilogramo", descripcion="Unidad de masa", activo=True),
        dict(id=3, nombre="Litro", descripcion="Unidad de volumen", activo=True),
    ],
}
ETIQUETAS_CATALOGO = {"categorias": "Categorías de producto", "unidades": "Unidades de medida"}


def _render(plantilla, **ctx):
    return render_template(
        plantilla,
        menu=MENU,
        rol_sistema="Administrador",
        etiquetas_rol=ETIQUETAS_ROL,
        **ctx
    )


def _registrar_auditoria(accion, entidad, registro_id, detalles, actor="Administrador"):
    ACTIVIDADES.insert(0, {
        "id": len(ACTIVIDADES) + 1,
        "descripcion": detalles,
        "usuario": actor,
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "accion": accion,
        "entidad": entidad,
        "registro_id": str(registro_id),
        "detalles": detalles,
    })


def _usuario(id_usuario):
    usuario = next((u for u in USUARIOS if u["id"] == id_usuario), None)
    if usuario is None:
        abort(404)
    return usuario


def _rol(id_rol):
    rol = next((r for r in ROLES if r["id"] == id_rol), None)
    if rol is None:
        abort(404)
    return rol


def _catalogo(tipo):
    if tipo not in CATALOGOS:
        abort(404)
    return CATALOGOS[tipo]


def _roles_para_usuario(id_usuario=None):
    roles = [rol for rol in ROLES if rol["activo"]]
    if id_usuario is not None:
        rol_actual = _rol(_usuario(id_usuario)["rol"])
        if not rol_actual["activo"]:
            roles.append({**rol_actual, "nombre": f"{rol_actual['nombre']} (inactivo)"})
    return roles


def _permisos_seleccionados(formulario, rol_id):
    seleccionados = set(formulario.getlist("permisos"))
    if not seleccionados.issubset(TODOS_LOS_PERMISOS):
        return None, "La selección contiene permisos no válidos."
    if not seleccionados:
        return None, "Asigna al menos un permiso al rol."
    if rol_id == "administrador" and not PERMISOS_ADMIN_OBLIGATORIOS.issubset(seleccionados):
        return None, "El rol administrador debe conservar los permisos esenciales del sistema."
    return sorted(seleccionados), None


def _validar_formulario(formulario, id_usuario=None):
    datos = {
        "nombre_usuario": formulario.get("nombre_usuario", "").strip(),
        "email": formulario.get("email", "").strip().lower(),
        "nombre_completo": formulario.get("nombre_completo", "").strip(),
        "rol": formulario.get("rol", "").strip(),
    }
    contrasena = formulario.get("contrasena", "")

    if not all(datos.values()):
        return datos, "Completa todos los campos obligatorios."
    if len(datos["nombre_usuario"]) > 50 or len(datos["nombre_completo"]) > 150:
        return datos, "El nombre de usuario o el nombre completo supera el límite permitido."
    if len(datos["email"]) > 150 or "@" not in datos["email"] or "." not in datos["email"].rsplit("@", 1)[-1]:
        return datos, "Ingresa un correo electrónico válido."
    if datos["rol"] not in ROLES_VALIDOS:
        return datos, "Selecciona un rol válido."
    rol = next(rol for rol in ROLES if rol["id"] == datos["rol"])
    rol_actual = _usuario(id_usuario)["rol"] if id_usuario is not None else None
    if not rol["activo"] and rol_actual != datos["rol"]:
        return datos, "No se puede asignar un rol inactivo."
    if any(u["id"] != id_usuario and u["nombre_usuario"].lower() == datos["nombre_usuario"].lower()
           for u in USUARIOS):
        return datos, "Ese nombre de usuario ya está registrado."
    if any(u["id"] != id_usuario and u["email"].lower() == datos["email"]
           for u in USUARIOS):
        return datos, "Ese correo electrónico ya está registrado."
    if id_usuario is None and len(contrasena) < 8:
        return datos, "La contraseña debe tener al menos 8 caracteres."
    if contrasena and len(contrasena) < 8:
        return datos, "La contraseña debe tener al menos 8 caracteres."
    return datos, None


def _usuarios_filtrados():
    buscar = request.args.get("q", "").strip().lower()
    rol = request.args.get("rol", "").strip()
    estado = request.args.get("estado", "").strip()
    filas = [
        u for u in USUARIOS
        if (not buscar or buscar in " ".join(
            (u["nombre_usuario"], u["email"], u["nombre_completo"])
        ).lower())
        and (not rol or u["rol"] == rol)
        and (estado not in ("activo", "inactivo") or u["activo"] == (estado == "activo"))
    ]
    return filas, buscar, rol, estado


def _filtrar_actividades():
    buscar = request.args.get("q", "").strip().lower()
    accion = request.args.get("accion", "").strip().upper()
    entidad = request.args.get("entidad", "").strip()
    filas = [
        actividad for actividad in ACTIVIDADES
        if (not buscar or buscar in " ".join(
            (actividad["descripcion"], actividad["usuario"], actividad["detalles"])
        ).lower())
        and (not accion or actividad["accion"] == accion)
        and (not entidad or actividad["entidad"] == entidad)
    ]
    return filas, buscar, accion, entidad


def _csv_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@admin_bp.route("/")
def panel():
    kpis = {
        "usuarios": len(USUARIOS),
        "usuarios_activos": sum(1 for u in USUARIOS if u["activo"]),
        "usuarios_inactivos": sum(1 for u in USUARIOS if not u["activo"]),
        "roles": sum(1 for rol in ROLES if rol["activo"]),
        "catalogos": sum(sum(1 for item in filas if item["activo"]) for filas in CATALOGOS.values()),
        "actividades": len(ACTIVIDADES),
    }
    return _render(
        "administrador/index.html",
        kpis=kpis,
        usuarios=USUARIOS[:5],
        actividades=ACTIVIDADES[:5],
        configuracion=CONFIGURACION,
    )


@admin_bp.route("/usuarios")
def usuarios():
    filas, buscar, rol, estado = _usuarios_filtrados()
    return _render(
        "administrador/usuarios.html",
        usuarios=filas,
        buscar=buscar,
        filtro_rol=rol,
        estado=estado,
        roles=ROLES,
    )


@admin_bp.route("/usuarios/nuevo", methods=["GET", "POST"])
def usuario_nuevo():
    if request.method == "POST":
        datos, error = _validar_formulario(request.form)
        if error:
            flash(error, "error")
            return _render("administrador/usuario_form.html", usuario=datos,
                           roles=_roles_para_usuario(), nuevo=True)

        nuevo = {
            **datos,
            "id": max((u["id"] for u in USUARIOS), default=0) + 1,
            "activo": True,
            "fecha_creacion": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "password_hash": generate_password_hash(request.form["contrasena"]),
        }
        USUARIOS.append(nuevo)
        _registrar_auditoria("INSERT", "usuarios", nuevo["id"],
                             f"Registro de usuario: {nuevo['nombre_usuario']}")
        flash("Usuario registrado correctamente.", "ok")
        return redirect(url_for("admin.usuarios"))

    return _render("administrador/usuario_form.html", usuario={}, roles=_roles_para_usuario(), nuevo=True)


@admin_bp.route("/usuarios/<int:id_usuario>/editar", methods=["GET", "POST"])
def usuario_editar(id_usuario):
    usuario = _usuario(id_usuario)
    if request.method == "POST":
        datos, error = _validar_formulario(request.form, id_usuario)
        admins_activos = sum(1 for u in USUARIOS if u["activo"] and u["rol"] == "administrador")
        if (not error and usuario["activo"] and usuario["rol"] == "administrador"
                and datos["rol"] != "administrador" and admins_activos <= 1):
            error = "No se puede cambiar el rol del único administrador activo."
        if error:
            flash(error, "error")
            return _render("administrador/usuario_form.html", usuario={**usuario, **datos},
                           roles=_roles_para_usuario(id_usuario), nuevo=False)

        usuario.update(datos)
        if request.form.get("contrasena"):
            usuario["password_hash"] = generate_password_hash(request.form["contrasena"])
        _registrar_auditoria("UPDATE", "usuarios", id_usuario,
                             f"Actualización de usuario: {usuario['nombre_usuario']}")
        flash("Datos del usuario actualizados.", "ok")
        return redirect(url_for("admin.usuarios"))

    return _render("administrador/usuario_form.html", usuario=usuario,
                   roles=_roles_para_usuario(id_usuario), nuevo=False)


@admin_bp.route("/usuarios/<int:id_usuario>/estado", methods=["POST"])
def usuario_estado(id_usuario):
    usuario = _usuario(id_usuario)
    activar = request.form.get("accion") == "activar"
    if request.form.get("accion") not in ("activar", "desactivar"):
        abort(400)
    if not activar and usuario["activo"] and usuario["rol"] == "administrador":
        admins_activos = sum(1 for u in USUARIOS if u["activo"] and u["rol"] == "administrador")
        if admins_activos <= 1:
            flash("No se puede desactivar al único administrador activo.", "error")
            return redirect(url_for("admin.usuarios"))

    if activar and not _rol(usuario["rol"])["activo"]:
        flash("No se puede activar un usuario cuyo rol está inactivo.", "error")
        return redirect(url_for("admin.usuarios"))
    usuario["activo"] = activar
    estado = "activado" if activar else "desactivado"
    _registrar_auditoria("ACTIVATE" if activar else "DEACTIVATE", "usuarios", id_usuario,
                         f"Usuario {estado}: {usuario['nombre_usuario']}")
    flash(f"Usuario {estado} correctamente.", "ok")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/roles")
def roles():
    filas = []
    for rol in ROLES:
        filas.append({
            **rol,
            "usuarios_activos": sum(
                1 for usuario in USUARIOS
                if usuario["rol"] == rol["id"] and usuario["activo"]
            ),
            "cantidad_permisos": len(rol["permisos"]),
        })
    return _render("administrador/roles.html", roles=filas,
                   catalogo_permisos={permiso["id"]: permiso["nombre"] for permiso in PERMISOS})


@admin_bp.route("/roles/nuevo", methods=["GET", "POST"])
def rol_nuevo():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        permisos, error = _permisos_seleccionados(request.form, "")
        slug = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")

        if not nombre or len(nombre) > 50 or len(descripcion) > 200:
            error = error or "El nombre es obligatorio (máximo 50 caracteres) y la descripción no puede superar 200."
        elif not slug or slug in ROLES_VALIDOS:
            error = error or "Ya existe un rol con ese nombre o no se pudo generar un código válido."
        if error:
            flash(error, "error")
            return _render("administrador/rol_form.html", nombre=nombre, descripcion=descripcion,
                           permisos=PERMISOS, seleccionados=request.form.getlist("permisos"))

        nuevo = dict(id=slug, nombre=nombre, descripcion=descripcion,
                     activo=True, permisos=permisos)
        ROLES.append(nuevo)
        ROLES_VALIDOS.add(slug)
        ETIQUETAS_ROL[slug] = nombre
        _registrar_auditoria("INSERT", "roles", slug, f"Creación del rol: {nombre}")
        flash("Rol creado. Revisa su asignación a usuarios.", "ok")
        return redirect(url_for("admin.roles"))

    return _render("administrador/rol_form.html", nombre="", descripcion="",
                   permisos=PERMISOS, seleccionados=[])


@admin_bp.route("/roles/<string:id_rol>/permisos", methods=["GET", "POST"])
def rol_permisos(id_rol):
    rol = _rol(id_rol)
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        permisos, error = _permisos_seleccionados(request.form, id_rol)
        if not nombre or len(nombre) > 50 or len(descripcion) > 200:
            error = error or "El nombre es obligatorio (máximo 50 caracteres) y la descripción no puede superar 200."
        if any(otro["id"] != id_rol and otro["nombre"].casefold() == nombre.casefold()
               for otro in ROLES):
            error = error or "Ya existe otro rol con ese nombre."
        if error:
            flash(error, "error")
            return _render("administrador/rol_permisos.html", rol={**rol, "nombre": nombre,
                           "descripcion": descripcion}, permisos=PERMISOS,
                           seleccionados=request.form.getlist("permisos"))

        rol["nombre"] = nombre
        rol["descripcion"] = descripcion
        rol["permisos"] = permisos
        ETIQUETAS_ROL[id_rol] = nombre
        _registrar_auditoria("UPDATE", "roles", id_rol, f"Actualización de permisos del rol: {nombre}")
        flash("Rol y permisos actualizados.", "ok")
        return redirect(url_for("admin.roles"))

    return _render("administrador/rol_permisos.html", rol=rol, permisos=PERMISOS,
                   seleccionados=rol["permisos"])


@admin_bp.route("/roles/<string:id_rol>/estado", methods=["POST"])
def rol_estado(id_rol):
    rol = _rol(id_rol)
    accion = request.form.get("accion")
    if accion not in ("activar", "desactivar"):
        abort(400)
    if id_rol == "administrador" and accion == "desactivar":
        flash("El rol administrador del sistema no se puede desactivar.", "error")
        return redirect(url_for("admin.roles"))
    if accion == "desactivar":
        asignados = sum(1 for usuario in USUARIOS
                        if usuario["rol"] == id_rol and usuario["activo"])
        if asignados:
            flash("Reasigna o desactiva los usuarios activos antes de desactivar este rol.", "error")
            return redirect(url_for("admin.roles"))

    rol["activo"] = accion == "activar"
    _registrar_auditoria(
        "ACTIVATE" if rol["activo"] else "DEACTIVATE",
        "roles",
        id_rol,
        f"Rol {'activado' if rol['activo'] else 'desactivado'}: {rol['nombre']}",
    )
    flash(f"Rol {'activado' if rol['activo'] else 'desactivado'} correctamente.", "ok")
    return redirect(url_for("admin.roles"))


@admin_bp.route("/configuracion", methods=["GET", "POST"])
def configuracion():
    if request.method == "POST":
        nombre_empresa = request.form.get("nombre_empresa", "").strip()
        moneda = request.form.get("moneda", "").strip()
        zona_horaria = request.form.get("zona_horaria", "").strip()
        try:
            intentos = int(request.form.get("intentos_maximos", ""))
            duracion = int(request.form.get("duracion_sesion", ""))
        except ValueError:
            flash("Los intentos y la duración deben ser números enteros.", "error")
            return _render("administrador/configuracion.html", configuracion=CONFIGURACION)

        if not nombre_empresa or len(nombre_empresa) > 120:
            flash("El nombre de la empresa es obligatorio y no debe superar 120 caracteres.", "error")
        elif moneda not in ("BOB", "USD", "EUR"):
            flash("Selecciona una moneda válida.", "error")
        elif zona_horaria not in ("America/La_Paz", "America/Santiago", "UTC"):
            flash("Selecciona una zona horaria válida.", "error")
        elif not 3 <= intentos <= 10 or not 5 <= duracion <= 480:
            flash("Los intentos deben estar entre 3 y 10; la sesión, entre 5 y 480 minutos.", "error")
        else:
            CONFIGURACION.update({
                "nombre_empresa": nombre_empresa,
                "moneda": moneda,
                "zona_horaria": zona_horaria,
                "intentos_maximos": intentos,
                "duracion_sesion": duracion,
                "modo_mantenimiento": request.form.get("modo_mantenimiento") == "1",
            })
            _registrar_auditoria("UPDATE", "configuracion", "general",
                                 "Actualización de parámetros generales del sistema")
            flash("Configuración general actualizada.", "ok")
            return redirect(url_for("admin.configuracion"))

        return _render("administrador/configuracion.html", configuracion={
            "nombre_empresa": nombre_empresa,
            "moneda": moneda,
            "zona_horaria": zona_horaria,
            "intentos_maximos": request.form.get("intentos_maximos", ""),
            "duracion_sesion": request.form.get("duracion_sesion", ""),
            "modo_mantenimiento": request.form.get("modo_mantenimiento") == "1",
        })

    return _render("administrador/configuracion.html", configuracion=CONFIGURACION)


@admin_bp.route("/catalogos")
def catalogos():
    return _render(
        "administrador/catalogos.html",
        catalogos=CATALOGOS,
        etiquetas_catalogo=ETIQUETAS_CATALOGO,
    )


@admin_bp.route("/catalogos/nuevo", methods=["POST"])
def catalogo_nuevo():
    tipo = request.form.get("tipo", "")
    filas = _catalogo(tipo)
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    if not nombre or len(nombre) > 80 or len(descripcion) > 200:
        flash("El nombre es obligatorio (máximo 80 caracteres) y la descripción no debe superar 200.", "error")
        return redirect(url_for("admin.catalogos"))
    if any(fila["nombre"].casefold() == nombre.casefold() for fila in filas):
        flash("Ese dato ya existe en el catálogo.", "error")
        return redirect(url_for("admin.catalogos"))

    nuevo = dict(
        id=max((fila["id"] for fila in filas), default=0) + 1,
        nombre=nombre,
        descripcion=descripcion,
        activo=True,
    )
    filas.append(nuevo)
    _registrar_auditoria("INSERT", tipo, nuevo["id"], f"Registro de catálogo: {nombre}")
    flash("Dato agregado al catálogo.", "ok")
    return redirect(url_for("admin.catalogos"))


@admin_bp.route("/catalogos/<string:tipo>/<int:id_item>/editar", methods=["POST"])
def catalogo_editar(tipo, id_item):
    filas = _catalogo(tipo)
    item = next((fila for fila in filas if fila["id"] == id_item), None)
    if item is None:
        abort(404)
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    if not nombre or len(nombre) > 80 or len(descripcion) > 200:
        flash("El nombre es obligatorio (máximo 80 caracteres) y la descripción no debe superar 200.", "error")
    elif any(fila["id"] != id_item and fila["nombre"].casefold() == nombre.casefold()
             for fila in filas):
        flash("Ese nombre ya existe en el catálogo.", "error")
    else:
        item.update(nombre=nombre, descripcion=descripcion)
        _registrar_auditoria("UPDATE", tipo, id_item, f"Modificación del catálogo: {nombre}")
        flash("Dato del catálogo actualizado.", "ok")
    return redirect(url_for("admin.catalogos"))


@admin_bp.route("/catalogos/<string:tipo>/<int:id_item>/estado", methods=["POST"])
def catalogo_estado(tipo, id_item):
    filas = _catalogo(tipo)
    item = next((fila for fila in filas if fila["id"] == id_item), None)
    if item is None:
        abort(404)
    accion = request.form.get("accion")
    if accion not in ("activar", "desactivar"):
        abort(400)
    item["activo"] = accion == "activar"
    _registrar_auditoria(
        "ACTIVATE" if item["activo"] else "DEACTIVATE",
        tipo,
        id_item,
        f"Dato {'activado' if item['activo'] else 'desactivado'}: {item['nombre']}",
    )
    flash("Estado del dato actualizado.", "ok")
    return redirect(url_for("admin.catalogos"))


@admin_bp.route("/actividad")
def actividad():
    filas, buscar, accion, entidad = _filtrar_actividades()
    acciones = sorted({item["accion"] for item in ACTIVIDADES})
    entidades = sorted({item["entidad"] for item in ACTIVIDADES})
    return _render("administrador/actividad.html", actividades=filas, buscar=buscar,
                   accion=accion, entidad=entidad, acciones=acciones, entidades=entidades)


@admin_bp.route("/actividad.csv")
def actividad_csv():
    filas, _, _, _ = _filtrar_actividades()
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)
    escritor.writerow(["ID", "Fecha", "Actor", "Acción", "Entidad", "Registro", "Detalles"])
    for actividad in filas:
        escritor.writerow([
            actividad["id"], actividad["fecha"], _csv_safe(actividad["usuario"]),
            _csv_safe(actividad["accion"]), _csv_safe(actividad["entidad"]),
            _csv_safe(actividad["registro_id"]), _csv_safe(actividad["detalles"]),
        ])
    respuesta = make_response("\ufeff" + salida.getvalue())
    respuesta.headers["Content-Type"] = "text/csv; charset=utf-8"
    respuesta.headers["Content-Disposition"] = "attachment; filename=auditoria_sistema.csv"
    return respuesta


@admin_bp.route("/reportes")
def reportes():
    conteo_roles = [
        {
            "rol": rol["id"],
            "etiqueta": rol["nombre"],
            "total": sum(1 for u in USUARIOS if u["rol"] == rol["id"]),
            "activos": sum(1 for u in USUARIOS if u["rol"] == rol["id"] and u["activo"]),
            "inactivos": sum(1 for u in USUARIOS if u["rol"] == rol["id"] and not u["activo"]),
        }
        for rol in ROLES
    ]
    return _render(
        "administrador/reportes.html",
        total=len(USUARIOS),
        activos=sum(1 for u in USUARIOS if u["activo"]),
        inactivos=sum(1 for u in USUARIOS if not u["activo"]),
        conteo_roles=[fila for fila in conteo_roles if fila["total"]],
        actividades=ACTIVIDADES[:20],
    )

from app.database import obtener_conexion

@admin_bp.route("/probar-db")
def probar_db():

    conexion = obtener_conexion()

    if conexion:
        cursor = conexion.cursor()
        cursor.execute("SELECT current_database();")

        resultado = cursor.fetchone()

        cursor.close()
        conexion.close()

        return f"Conectado a: {resultado[0]}"

    return "Error de conexión con PostgreSQL"

@admin_bp.route("/reportes/usuarios.csv")
def reporte_usuarios_csv():
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)
    escritor.writerow(["ID", "Usuario", "Nombre completo", "Correo", "Rol", "Estado", "Fecha de registro"])
    for usuario in USUARIOS:
        escritor.writerow([
            usuario["id"],
            _csv_safe(usuario["nombre_usuario"]),
            _csv_safe(usuario["nombre_completo"]),
            _csv_safe(usuario["email"]),
            _csv_safe(ETIQUETAS_ROL[usuario["rol"]]),
            "Activo" if usuario["activo"] else "Inactivo",
            usuario["fecha_creacion"],
        ])

    respuesta = make_response("\ufeff" + salida.getvalue())
    respuesta.headers["Content-Type"] = "text/csv; charset=utf-8"
    respuesta.headers["Content-Disposition"] = "attachment; filename=reporte_usuarios.csv"
    return respuesta

    
