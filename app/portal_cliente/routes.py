"""Rutas del PORTAL DE CLIENTES con datos simulados (sin base de datos).

Pantallas (diagrama de navegación del portal y hoja pantallas_ERP_por_rol):
  CLI-01 Inicio de sesión del portal ... RF-36           (RN-02: bloqueo tras 3 intentos)
  CLI-00 Inicio del portal ............. RF-36, RF-40
  CLI-02 Catálogo y disponibilidad ..... RF-37
  CLI-03 Nuevo pedido .................. RF-38           (RN-14: queda pendiente)
  CLI-04 Mis pedidos ................... RF-40
  CLI-05 Facturas y saldos ............. RF-41
  CLI-06 Mis reclamos .................. RF-42, RNF-14   (RN-21: solo lotes que recibió)

El portal comparte los datos simulados del vendedor (clientes, productos, lotes,
pedidos, facturas) y de calidad (reclamos). Así, un pedido hecho aquí aparece en
"Pedidos en línea" del vendedor, y un reclamo aparece en "Reclamos" del vendedor
y de calidad: es el recorrido completo del diagrama de navegación.
"""
import os
from datetime import date, timedelta
from functools import wraps

from flask import abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import cliente_bp
from ..calidad.routes import RECLAMOS
from ..vendedor.routes import (ASIGNADOS, FACTURAS, IVA, PAGOS, PEDIDOS, PRODUCTOS, _cliente,
                               _crear_pedido, _lineas, _stock)

MENU = [
    ("Inicio", "cliente.panel", "Resumen de tu cuenta"),
    ("Catálogo", "cliente.catalogo", "Disponibilidad"),
    ("Nuevo pedido", "cliente.pedido_nuevo", "Queda pendiente"),
    ("Mis pedidos", "cliente.pedidos", "Estado del pedido"),
    ("Facturas y saldos", "cliente.facturas", "Despachos"),
    ("Reclamos", "cliente.reclamos", "Indica el lote"),
]
MAX_INTENTOS = 3  # RN-02


@cliente_bp.record_once
def _clave_sesion(state):
    # La sesión del portal necesita SECRET_KEY; mientras config.py la tenga comentada usamos una de desarrollo
    if not state.app.secret_key:
        state.app.secret_key = os.environ.get("SECRET_KEY", "clave-de-desarrollo")


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


# ====================================================================
# DATOS SIMULADOS: cuentas del portal (tablas usuarios + cuentas_cliente)
# ====================================================================
CUENTAS = [
    dict(usuario="elsol", id_cliente=1, clave=generate_password_hash("cliente123"), intentos=0, activo=True),
    dict(usuario="andinos", id_cliente=2, clave=generate_password_hash("cliente123"), intentos=0, activo=True),
    dict(usuario="donarosa", id_cliente=3, clave=generate_password_hash("cliente123"), intentos=0, activo=True),
]
CUENTAS_DEMO = [("elsol", "Distribuidora El Sol"), ("andinos", "Supermercados Andinos"),
                ("donarosa", "Tienda Doña Rosa")]


# ====================================================================
# Sesión y control de acceso (RN-01 / RN-21)
# ====================================================================
def _id_cliente():
    return session.get("portal_cliente")


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if not _id_cliente():
            flash("Inicia sesión para entrar al portal.", "error")
            return redirect(url_for("cliente.login", siguiente=request.path))
        return vista(*args, **kwargs)
    return envoltura


def _render(plantilla, **ctx):
    c = _cliente(_id_cliente()) if _id_cliente() else None
    return render_template(plantilla, menu=MENU, rol=c["razon_social"] if c else "cliente",
                           cliente=c, **ctx)


# ====================================================================
# Consultas del cliente: SIEMPRE filtradas por su id_cliente (RN-21)
# ====================================================================
def _mis_pedidos():
    return [p for p in PEDIDOS if p["id_cliente"] == _id_cliente()]


def _mi_pedido(id):
    p = next((p for p in _mis_pedidos() if p["id_pedido"] == id), None)
    if not p:
        abort(404)  # no existe o es de otro cliente
    return p


def _mis_facturas():
    return [f for f in FACTURAS if f["id_cliente"] == _id_cliente()]


def _factura_de(pedido):
    return next((f for f in FACTURAS if f["id_pedido"] == pedido["id_pedido"]), None)


def _bs(x):
    return f"{x:,.2f}"


def _vista_pedido(p):
    f = _factura_de(p)
    return {**p, "items": len(p["lineas"]), "numero_factura": f["numero_factura"] if f else None,
            "despacho": f["despacho"] if f else None, "total_bs": _bs(p["total"]),
            "subtotal_bs": _bs(p["subtotal"]), "impuestos_bs": _bs(p["impuestos"])}


def _lineas_bs(p):
    return [dict(l, precio_bs=_bs(l["precio_unitario"]), subtotal_bs=_bs(l["subtotal"])) for l in _lineas(p)]


def _mis_lotes_recibidos():
    """Lotes entregados al cliente (pedido_lotes): los únicos que puede reclamar."""
    lotes = []
    for p in _mis_pedidos():
        f = _factura_de(p)
        for a in ASIGNADOS.get(p["id_pedido"], []):
            lotes.append(dict(a, numero_factura=f["numero_factura"] if f else None,
                              clave=f"{a['numero_lote']}|{f['numero_factura'] if f else ''}"))
    return lotes


def _mis_reclamos():
    nombre = _cliente(_id_cliente())["razon_social"]
    return [r for r in RECLAMOS if r["cliente"] == nombre]


def _catalogo():
    filas = []
    for p in PRODUCTOS:
        stock = _stock(p["id_producto"])
        disp = "agotado" if stock <= 0 else ("pocas unidades" if stock < 30 else "disponible")
        filas.append({**p, "stock": stock, "disponibilidad": disp})
    return filas


# ====================================================================
# RUTAS
# ====================================================================
# ------------------------------------------------------------ CLI-01 Inicio de sesión
@cliente_bp.route("/login", methods=["GET", "POST"])
def login():
    if _id_cliente():
        return redirect(url_for("cliente.panel"))
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        clave = request.form.get("clave", "")
        cuenta = next((c for c in CUENTAS if c["usuario"] == usuario), None)
        if cuenta and not cuenta["activo"]:
            flash("Tu cuenta está bloqueada por intentos fallidos. Comunícate con tu vendedor.", "error")
        elif cuenta and check_password_hash(cuenta["clave"], clave):
            cuenta["intentos"] = 0
            session.clear()
            session["portal_cliente"] = cuenta["id_cliente"]
            destino = request.args.get("siguiente", "")
            return redirect(destino if destino.startswith("/cliente") else url_for("cliente.panel"))
        else:
            if cuenta:
                cuenta["intentos"] += 1
                if cuenta["intentos"] >= MAX_INTENTOS:
                    cuenta["activo"] = False
                    flash("Superaste los 3 intentos. La cuenta quedó bloqueada.", "error")
                else:
                    flash(f"Usuario o contraseña incorrectos. Te quedan {MAX_INTENTOS - cuenta['intentos']} intento(s).", "error")
            else:
                flash("Usuario o contraseña incorrectos.", "error")
    return render_template("portal_cliente/login.html", demo=CUENTAS_DEMO, usuario=request.form.get("usuario", ""))


@cliente_bp.route("/salir")
def salir():
    session.pop("portal_cliente", None)
    flash("Cerraste sesión.", "ok")
    return redirect(url_for("cliente.login"))


# ------------------------------------------------------------ CLI-00 Inicio del portal
@cliente_bp.route("/")
@login_requerido
def panel():
    pedidos = _mis_pedidos()
    facturas = _mis_facturas()
    kpis = dict(
        pendientes=sum(1 for p in pedidos if p["estado"] == "pendiente"),
        en_curso=sum(1 for p in pedidos if p["estado"] in ("confirmado", "despachado")),
        saldo=round(sum(f["saldo_pendiente"] for f in facturas), 2),
        reclamos=sum(1 for r in _mis_reclamos() if r["estado"] in ("abierto", "en_revision")),
    )
    recientes = [_vista_pedido(p) for p in reversed(pedidos)][:5]
    return _render("portal_cliente/panel.html", kpis=kpis, recientes=recientes)


# ------------------------------------------------------------ CLI-02 Catálogo
@cliente_bp.route("/catalogo")
@login_requerido
def catalogo():
    buscar = request.args.get("q", "").strip()
    filas = [p for p in _catalogo() if buscar.lower() in p["nombre"].lower()]
    return _render("portal_cliente/catalogo.html", productos=filas, buscar=buscar)


# ------------------------------------------------------------ CLI-03 Nuevo pedido
@cliente_bp.route("/pedidos/nuevo", methods=["GET", "POST"])
@login_requerido
def pedido_nuevo():
    productos = _catalogo()
    if request.method == "POST":
        lineas, errores = [], []
        for p in productos:
            cant = request.form.get(f"cant_{p['id_producto']}", type=int) or 0
            if cant <= 0:
                continue
            if cant > p["stock"]:
                errores.append(f"{p['nombre']}: pides {cant} y hay {p['stock']} disponibles.")
            lineas.append((p["id_producto"], cant))
        entrega = request.form.get("entrega") or None
        if not lineas:
            errores.append("Agrega al menos un producto a tu pedido.")
        if entrega and entrega <= _d(0):
            errores.append("La fecha de entrega debe ser posterior a hoy.")
        if errores:
            for e in errores:
                flash(e, "error")
            return _render("portal_cliente/pedido_nuevo.html", productos=productos, iva=IVA,
                           manana=_d(1), form=request.form)
        # RN-14: el pedido del portal queda 'pendiente' hasta que el vendedor lo confirme
        p = _crear_pedido(_id_cliente(), "portal", "pendiente", lineas, entrega=entrega,
                          obs=request.form.get("observacion") or None)
        flash(f"Pedido {p['numero_pedido']} enviado. Queda pendiente hasta que tu vendedor lo confirme.", "ok")
        return redirect(url_for("cliente.pedido_detalle", id=p["id_pedido"]))
    seleccion = {f"cant_{request.args.get('producto')}": "1"} if request.args.get("producto") else {}
    return _render("portal_cliente/pedido_nuevo.html", productos=productos, iva=IVA, manana=_d(1), form=seleccion)


# ------------------------------------------------------------ CLI-04 Mis pedidos
@cliente_bp.route("/pedidos")
@login_requerido
def pedidos():
    estado = request.args.get("estado", "")
    filas = [_vista_pedido(p) for p in reversed(_mis_pedidos()) if not estado or p["estado"] == estado]
    return _render("portal_cliente/pedidos.html", pedidos=filas, estado=estado)


@cliente_bp.route("/pedidos/<int:id>")
@login_requerido
def pedido_detalle(id):
    p = _mi_pedido(id)
    f = _factura_de(p)
    pasos = ["pendiente", "confirmado", "despachado", "entregado"]
    actual = pasos.index(p["estado"]) if p["estado"] in pasos else -1
    return _render("portal_cliente/pedido_detalle.html", p=_vista_pedido(p), lineas=_lineas_bs(p), factura=f,
                   lotes=ASIGNADOS.get(p["id_pedido"], []), pasos=pasos, actual=actual)


# ------------------------------------------------------------ CLI-05 Facturas y saldos
@cliente_bp.route("/facturas")
@login_requerido
def facturas():
    filas = []
    for f in reversed(_mis_facturas()):
        p = next(p for p in PEDIDOS if p["id_pedido"] == f["id_pedido"])
        venc = (date.fromisoformat(f["fecha"]) + timedelta(days=30)).isoformat()
        filas.append({**f, "numero_pedido": p["numero_pedido"], "id_pedido": p["id_pedido"],
                      "fecha_emision": f["fecha"], "vence_pago": venc,
                      "vencida": f["saldo_pendiente"] > 0 and venc < _d(0)})
    mis_numeros = {f["numero_factura"] for f in _mis_facturas()}
    pagos = [dict(pg, monto_bs=_bs(pg["monto"])) for pg in PAGOS if pg["numero_factura"] in mis_numeros]
    saldo = round(sum(f["saldo_pendiente"] for f in filas), 2)
    return _render("portal_cliente/facturas.html", facturas=filas, pagos=pagos, saldo=saldo,
                   limite=_cliente(_id_cliente())["limite_credito"])


# ------------------------------------------------------------ CLI-06 Reclamos
@cliente_bp.route("/reclamos", methods=["GET", "POST"])
@login_requerido
def reclamos():
    lotes = _mis_lotes_recibidos()
    if request.method == "POST":
        elegido = next((l for l in lotes if l["clave"] == request.form.get("lote")), None)
        descripcion = request.form.get("descripcion", "").strip()
        if not elegido:
            flash("Elige el lote del producto que recibiste (está impreso en el envase).", "error")
        elif len(descripcion) < 10:
            flash("Describe el problema con un poco más de detalle.", "error")
        else:
            c = _cliente(_id_cliente())
            n = max([r["id_reclamo"] for r in RECLAMOS] + [0]) + 1
            numero = f"REC-{date.today().year}-{9 + n:03d}"
            RECLAMOS.insert(0, dict(id_reclamo=n, numero_reclamo=numero, cliente=c["razon_social"],
                                    telefono=c["telefono"], email=c["email"],
                                    numero_factura=elegido["numero_factura"], numero_lote=elegido["numero_lote"],
                                    producto=elegido["producto"], estado="abierto", fecha=_d(0),
                                    descripcion=descripcion, resolucion=None))
            flash(f"Reclamo {numero} registrado. Te contactaremos con la respuesta.", "ok")
            return redirect(url_for("cliente.reclamos"))
    return _render("portal_cliente/reclamos.html", lotes=lotes, reclamos=_mis_reclamos(), form=request.form)
