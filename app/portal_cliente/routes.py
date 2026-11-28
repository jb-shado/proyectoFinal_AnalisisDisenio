"""Rutas del PORTAL DE CLIENTES conectadas a PostgreSQL (Flask-SQLAlchemy + app/models.py).

Pantallas (diagrama de navegación del portal y hoja pantallas_ERP_por_rol):
  CLI-01 Inicio de sesión del portal ... RF-36           (RNF-01, RN-02: bloqueo tras 3 intentos)
  CLI-00 Inicio del portal ............. RF-36, RF-40
  CLI-02 Catálogo y disponibilidad ..... RF-37           (RN-13: solo lotes disponibles y no vencidos)
  CLI-03 Nuevo pedido .................. RF-38           (RN-14: queda pendiente)
  CLI-04 Mis pedidos ................... RF-40
  CLI-05 Facturas y saldos ............. RF-41
  CLI-06 Mis reclamos .................. RF-42, RNF-14   (RN-21: solo lotes que recibió)

Cómo entra un cliente: tabla usuarios (rol 'cliente', contraseña cifrada con pgcrypto)
+ tabla cuentas_cliente (enlaza ese usuario con su cliente).

Lo que se registra aquí lo ven los demás roles porque es la misma base de datos:
  - pedidos con origen 'portal' y estado 'pendiente'  -> Ventas · Pedidos en línea
  - reclamos_cliente                                  -> Ventas y Calidad · Reclamos
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError

from . import cliente_bp
from ..models import (Auditoria, Cliente, CuentaCliente, CuentaPorCobrar, Factura, LoteProducto, NotaDespacho,
                      PagoCliente, Pedido, PedidoDetalle, PedidoLote, Producto, ReclamoCliente, Rol, Usuario, db)

MENU = [
    ("Inicio", "cliente.panel", "Resumen de tu cuenta"),
    ("Catálogo", "cliente.catalogo", "Disponibilidad"),
    ("Nuevo pedido", "cliente.pedido_nuevo", "Queda pendiente"),
    ("Mis pedidos", "cliente.pedidos", "Estado del pedido"),
    ("Facturas y saldos", "cliente.facturas", "Despachos"),
    ("Reclamos", "cliente.reclamos", "Indica el lote"),
]
MAX_INTENTOS = 3            # RN-02
IVA = Decimal("0.13")
CENT = Decimal("0.01")
DIAS_CREDITO = 30
CLAVE_DEMO = "Pass123*"     # contraseña de los usuarios de prueba de db.sql


# ====================================================================
# UTILIDADES
# ====================================================================
def _n(x):
    if x is None:
        return 0
    x = Decimal(x)
    return int(x) if x == x.to_integral_value() else float(x.normalize())


def _bs(x):
    return f"{Decimal(x or 0):,.2f}"


def _fecha(x):
    if x is None:
        return None
    if isinstance(x, datetime):
        x = x.date()
    return x.isoformat()


def _siguiente_numero(columna, prefijo):
    """PED-2026-011, REC-2026-011... según el último número del año (igual que en ventas)."""
    patron = f"{prefijo}-{date.today().year}-"
    ultimo = (db.session.query(columna).filter(columna.like(patron + "%"))
              .order_by(func.length(columna).desc(), columna.desc()).first())
    n = int(ultimo[0].rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{patron}{n:03d}"


def _auditar(accion, tabla, registro, datos=None):     # RN-03
    db.session.add(Auditoria(id_usuario=session.get("portal_usuario"), accion=accion, tabla_afectada=tabla,
                             registro_id=str(registro), datos_nuevos=datos, ip_origen=request.remote_addr))


def _error_bd(e, mensaje="No se pudo guardar. Intenta de nuevo en unos minutos."):
    db.session.rollback()
    print("Error de base de datos:", e)
    flash(mensaje, "error")


# ====================================================================
# Sesión y control de acceso (RN-01 / RN-21 / RNF-14)
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


def _cliente():
    return db.session.get(Cliente, _id_cliente())


def _render(plantilla, **ctx):
    c = _cliente() if _id_cliente() else None
    vista = None
    if c:
        vista = dict(id_cliente=c.id_cliente, razon_social=c.razon_social, nombre_contacto=c.nombre_contacto,
                     nit_ci=c.nit_ci, telefono=c.telefono, email=c.email,
                     limite_credito=float(c.limite_credito or 0))
    return render_template(plantilla, menu=MENU, rol=c.razon_social if c else "cliente", cliente=vista, **ctx)


# ====================================================================
# Consultas: SIEMPRE filtradas por el cliente de la sesión (RN-21)
# ====================================================================
def _stocks():
    """{id_producto: stock vendible} = lotes 'disponible' (aprobados) y no vencidos (RN-13)."""
    q = (db.session.query(LoteProducto.id_producto, func.coalesce(func.sum(LoteProducto.cantidad_actual), 0))
         .filter(LoteProducto.estado == "disponible", LoteProducto.fecha_vencimiento >= date.today())
         .group_by(LoteProducto.id_producto))
    return {i: s for i, s in q.all()}


def _catalogo():
    stocks = _stocks()
    filas = []
    for p in Producto.query.filter_by(activo=True).order_by(Producto.nombre):
        stock = stocks.get(p.id_producto, Decimal(0))
        disp = "agotado" if stock <= 0 else ("pocas unidades" if stock < 30 else "disponible")
        filas.append(dict(id_producto=p.id_producto, codigo=p.codigo, nombre=p.nombre,
                          precio_venta=float(p.precio_venta), stock=_n(stock), _stock=stock, disponibilidad=disp))
    return filas


def _mis_pedidos():
    return (Pedido.query.filter_by(id_cliente=_id_cliente())
            .order_by(Pedido.fecha_pedido.desc(), Pedido.id_pedido.desc()).all())


def _factura_de(pedido):
    return (Factura.query.filter(Factura.id_pedido == pedido.id_pedido, Factura.estado != "anulada")
            .order_by(Factura.id_factura.desc()).first())


def _nota_de(factura):
    if not factura:
        return None
    return (NotaDespacho.query.filter(NotaDespacho.id_factura == factura.id_factura, NotaDespacho.estado != "anulada")
            .order_by(NotaDespacho.id_nota.desc()).first())


def _vista_pedido(p):
    f = _factura_de(p)
    nota = _nota_de(f)
    return dict(id_pedido=p.id_pedido, numero_pedido=p.numero_pedido, estado=p.estado, origen=p.origen,
                fecha_pedido=_fecha(p.fecha_pedido), fecha_entrega_estimada=_fecha(p.fecha_entrega_estimada),
                observacion=p.observacion, items=len(p.detalle),
                subtotal_bs=_bs(p.subtotal), impuestos_bs=_bs(p.impuestos), total_bs=_bs(p.total),
                numero_factura=f.numero_factura if f else None, despacho=nota.estado if nota else None)


def _lotes_recibidos():
    """Lotes entregados al cliente (pedido_lotes): los únicos que puede reclamar (RN-21)."""
    filas = (db.session.query(PedidoLote, Pedido, LoteProducto, Producto)
             .join(Pedido, Pedido.id_pedido == PedidoLote.id_pedido)
             .join(LoteProducto, LoteProducto.id_lote_producto == PedidoLote.id_lote_producto)
             .join(Producto, Producto.id_producto == LoteProducto.id_producto)
             .filter(Pedido.id_cliente == _id_cliente())
             .order_by(Pedido.id_pedido.desc()).all())
    lotes = []
    for pl, p, l, prod in filas:
        f = _factura_de(p)
        lotes.append(dict(clave=f"{l.id_lote_producto}|{f.id_factura if f else 0}", id_lote=l.id_lote_producto,
                          id_factura=f.id_factura if f else None, numero_lote=l.numero_lote, producto=prod.nombre,
                          numero_factura=f.numero_factura if f else None, cantidad=_n(pl.cantidad)))
    return lotes


# ====================================================================
# RUTAS
# ====================================================================
# ------------------------------------------------------------ CLI-01 Inicio de sesión
def _cuentas_demo():
    filas = (db.session.query(Usuario.nombre_usuario, Cliente.razon_social)
             .join(CuentaCliente, CuentaCliente.id_usuario == Usuario.id_usuario)
             .join(Cliente, Cliente.id_cliente == CuentaCliente.id_cliente)
             .join(Rol, Rol.id_rol == Usuario.id_rol)
             .filter(Rol.nombre == "cliente", CuentaCliente.activo.is_(True))
             .order_by(Usuario.nombre_usuario).limit(5).all())
    return [(u, r) for u, r in filas]


@cliente_bp.route("/login", methods=["GET", "POST"])
def login():
    if _id_cliente():
        return redirect(url_for("cliente.panel"))
    if request.method == "POST":
        nombre = request.form.get("usuario", "").strip().lower()
        clave = request.form.get("clave", "")
        u = (Usuario.query.join(Rol).filter(func.lower(Usuario.nombre_usuario) == nombre, Rol.nombre == "cliente")
             .first())
        if u and (not u.activo or (u.intentos_fallidos or 0) >= MAX_INTENTOS):
            flash("Tu cuenta está bloqueada por intentos fallidos. Comunícate con tu vendedor.", "error")
        elif u:
            # la contraseña está cifrada con pgcrypto (crypt + gen_salt('bf')) en db.sql (RNF-01)
            ok = db.session.execute(text("SELECT password_hash = crypt(:c, password_hash) FROM usuarios "
                                         "WHERE id_usuario = :id"), {"c": clave, "id": u.id_usuario}).scalar()
            cuenta = CuentaCliente.query.filter_by(id_usuario=u.id_usuario, activo=True).order_by(
                CuentaCliente.id_cuenta).first()
            if ok and cuenta:
                u.intentos_fallidos, u.ultimo_acceso = 0, datetime.now()
                session.pop("portal_cliente", None)
                session["portal_cliente"], session["portal_usuario"] = cuenta.id_cliente, u.id_usuario
                _auditar("LOGIN_PORTAL", "usuarios", u.id_usuario)
                db.session.commit()
                destino = request.args.get("siguiente", "")
                return redirect(destino if destino.startswith("/cliente") else url_for("cliente.panel"))
            if ok and not cuenta:
                flash("Tu usuario no está enlazado a ningún cliente. Pide a tu vendedor que active tu cuenta.", "error")
            else:
                u.intentos_fallidos = (u.intentos_fallidos or 0) + 1
                quedan = MAX_INTENTOS - u.intentos_fallidos
                if quedan <= 0:
                    u.activo = False
                    flash("Superaste los 3 intentos. La cuenta quedó bloqueada.", "error")
                else:
                    flash(f"Usuario o contraseña incorrectos. Te quedan {quedan} intento(s).", "error")
                db.session.commit()
        else:
            flash("Usuario o contraseña incorrectos.", "error")
    return render_template("portal_cliente/login.html", demo=_cuentas_demo(), clave_demo=CLAVE_DEMO,
                           usuario=request.form.get("usuario", ""))


@cliente_bp.route("/salir")
def salir():
    session.pop("portal_cliente", None)
    session.pop("portal_usuario", None)
    flash("Cerraste sesión.", "ok")
    return redirect(url_for("cliente.login"))


# ------------------------------------------------------------ CLI-00 Inicio del portal
@cliente_bp.route("/")
@login_requerido
def panel():
    pedidos = _mis_pedidos()
    saldo = (db.session.query(func.coalesce(func.sum(Factura.saldo_pendiente), 0))
             .filter(Factura.id_cliente == _id_cliente(), Factura.estado != "anulada").scalar())
    kpis = dict(
        pendientes=sum(1 for p in pedidos if p.estado == "pendiente"),
        en_curso=sum(1 for p in pedidos if p.estado in ("confirmado", "despachado")),
        saldo=float(saldo),
        reclamos=ReclamoCliente.query.filter(ReclamoCliente.id_cliente == _id_cliente(),
                                             ReclamoCliente.estado.in_(("abierto", "en_revision"))).count(),
    )
    return _render("portal_cliente/panel.html", kpis=kpis, recientes=[_vista_pedido(p) for p in pedidos[:5]])


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
    manana = (date.today() + timedelta(days=1)).isoformat()
    if request.method == "POST":
        lineas, errores = [], []
        for p in productos:
            cant = request.form.get(f"cant_{p['id_producto']}", type=int) or 0
            if cant <= 0:
                continue
            if cant > p["_stock"]:
                errores.append(f"{p['nombre']}: pides {cant} y hay {p['stock']} disponibles.")
            lineas.append((p, cant))
        entrega = request.form.get("entrega") or None
        if not lineas:
            errores.append("Agrega al menos un producto a tu pedido.")
        if entrega and entrega <= date.today().isoformat():
            errores.append("La fecha de entrega debe ser posterior a hoy.")
        if errores:
            for e in errores:
                flash(e, "error")
            return _render("portal_cliente/pedido_nuevo.html", productos=productos, iva=float(IVA),
                           manana=manana, form=request.form)
        try:
            subtotal = sum((Decimal(str(p["precio_venta"])) * c for p, c in lineas), Decimal(0)).quantize(CENT)
            impuestos = (subtotal * IVA).quantize(CENT)
            # RN-14: el pedido del portal queda 'pendiente' hasta que el vendedor lo confirme
            pedido = Pedido(numero_pedido=_siguiente_numero(Pedido.numero_pedido, "PED"), id_cliente=_id_cliente(),
                            fecha_pedido=datetime.now(), fecha_entrega_estimada=entrega, origen="portal",
                            estado="pendiente", subtotal=subtotal, impuestos=impuestos, total=subtotal + impuestos,
                            observacion=request.form.get("observacion") or None)
            db.session.add(pedido)
            db.session.flush()
            for p, c in lineas:
                db.session.add(PedidoDetalle(id_pedido=pedido.id_pedido, id_producto=p["id_producto"], cantidad=c,
                                             precio_unitario=Decimal(str(p["precio_venta"]))))
            _auditar("PEDIDO_PORTAL", "pedidos", pedido.numero_pedido, {"total": str(pedido.total)})
            db.session.commit()
        except SQLAlchemyError as e:
            _error_bd(e)
            return redirect(url_for("cliente.pedido_nuevo"))
        flash(f"Pedido {pedido.numero_pedido} enviado. Queda pendiente hasta que tu vendedor lo confirme.", "ok")
        return redirect(url_for("cliente.pedido_detalle", id=pedido.id_pedido))
    seleccion = {f"cant_{request.args.get('producto')}": "1"} if request.args.get("producto") else {}
    return _render("portal_cliente/pedido_nuevo.html", productos=productos, iva=float(IVA), manana=manana,
                   form=seleccion)


# ------------------------------------------------------------ CLI-04 Mis pedidos
@cliente_bp.route("/pedidos")
@login_requerido
def pedidos():
    estado = request.args.get("estado", "")
    filas = [_vista_pedido(p) for p in _mis_pedidos() if not estado or p.estado == estado]
    return _render("portal_cliente/pedidos.html", pedidos=filas, estado=estado)


@cliente_bp.route("/pedidos/<int:id>")
@login_requerido
def pedido_detalle(id):
    p = Pedido.query.filter_by(id_pedido=id, id_cliente=_id_cliente()).first()
    if not p:
        abort(404)  # no existe o es de otro cliente (RN-21)
    f = _factura_de(p)
    nota = _nota_de(f)
    lineas = [dict(codigo=d.producto.codigo, producto=d.producto.nombre, cantidad=_n(d.cantidad),
                   precio_bs=_bs(d.precio_unitario), subtotal_bs=_bs(d.cantidad * d.precio_unitario))
              for d in sorted(p.detalle, key=lambda d: d.id_detalle)]
    lotes = [dict(producto=pl.lote_producto.producto.nombre, numero_lote=pl.lote_producto.numero_lote,
                  cantidad=_n(pl.cantidad), fecha_vencimiento=_fecha(pl.lote_producto.fecha_vencimiento))
             for pl in p.lotes]
    factura = dict(numero_factura=f.numero_factura, numero_nota=nota.numero_nota if nota else None,
                   despacho=nota.estado if nota else None) if f else None
    pasos = ["pendiente", "confirmado", "despachado", "entregado"]
    actual = pasos.index(p.estado) if p.estado in pasos else -1
    return _render("portal_cliente/pedido_detalle.html", p=_vista_pedido(p), lineas=lineas, factura=factura,
                   lotes=lotes, pasos=pasos, actual=actual)


# ------------------------------------------------------------ CLI-05 Facturas y saldos
@cliente_bp.route("/facturas")
@login_requerido
def facturas():
    filas = []
    hoy = date.today()
    for f in (Factura.query.filter(Factura.id_cliente == _id_cliente())
              .order_by(Factura.fecha_emision.desc(), Factura.id_factura.desc())):
        p = db.session.get(Pedido, f.id_pedido) if f.id_pedido else None
        nota = _nota_de(f)
        cxc = CuentaPorCobrar.query.filter_by(id_factura=f.id_factura).first()
        vence = cxc.fecha_vencimiento if cxc and cxc.fecha_vencimiento else \
            (f.fecha_emision.date() + timedelta(days=DIAS_CREDITO) if f.fecha_emision else None)
        saldo = float(f.saldo_pendiente or 0)
        filas.append(dict(numero_factura=f.numero_factura, fecha_emision=_fecha(f.fecha_emision),
                          id_pedido=f.id_pedido, numero_pedido=p.numero_pedido if p else "—",
                          total=float(f.total), saldo_pendiente=saldo, estado=f.estado,
                          vence_pago=_fecha(vence), vencida=bool(saldo > 0 and vence and vence < hoy),
                          numero_nota=nota.numero_nota if nota else None, despacho=nota.estado if nota else None,
                          transportista=nota.transportista if nota else None))
    pagos = [dict(fecha=_fecha(pg.fecha_pago), numero_factura=f.numero_factura, monto_bs=_bs(pg.monto),
                  metodo_pago=pg.metodo_pago, referencia=pg.referencia)
             for pg, cxc, f in (db.session.query(PagoCliente, CuentaPorCobrar, Factura)
                                .join(CuentaPorCobrar, CuentaPorCobrar.id_cxc == PagoCliente.id_cxc)
                                .join(Factura, Factura.id_factura == CuentaPorCobrar.id_factura)
                                .filter(Factura.id_cliente == _id_cliente())
                                .order_by(PagoCliente.fecha_pago.desc()).all())]
    saldo = round(sum(f["saldo_pendiente"] for f in filas if f["estado"] != "anulada"), 2)
    return _render("portal_cliente/facturas.html", facturas=filas, pagos=pagos, saldo=saldo,
                   limite=float(_cliente().limite_credito or 0))


# ------------------------------------------------------------ CLI-06 Reclamos
@cliente_bp.route("/reclamos", methods=["GET", "POST"])
@login_requerido
def reclamos():
    lotes = _lotes_recibidos()
    if request.method == "POST":
        elegido = next((l for l in lotes if l["clave"] == request.form.get("lote")), None)
        descripcion = request.form.get("descripcion", "").strip()
        if not elegido:
            flash("Elige el lote del producto que recibiste (está impreso en el envase).", "error")
        elif len(descripcion) < 10:
            flash("Describe el problema con un poco más de detalle.", "error")
        else:
            try:
                r = ReclamoCliente(numero_reclamo=_siguiente_numero(ReclamoCliente.numero_reclamo, "REC"),
                                   id_cliente=_id_cliente(), id_factura=elegido["id_factura"],
                                   id_lote_producto=elegido["id_lote"], descripcion=descripcion, estado="abierto",
                                   fecha_reclamo=datetime.now())
                db.session.add(r)
                _auditar("RECLAMO_PORTAL", "reclamos_cliente", r.numero_reclamo, {"lote": elegido["numero_lote"]})
                db.session.commit()
                flash(f"Reclamo {r.numero_reclamo} registrado. Te contactaremos con la respuesta.", "ok")
                return redirect(url_for("cliente.reclamos"))
            except SQLAlchemyError as e:
                _error_bd(e)
    nombres = {l.id_lote_producto: (l.numero_lote, l.producto.nombre) for l in LoteProducto.query.all()}
    numeros = {f.id_factura: f.numero_factura for f in Factura.query.filter_by(id_cliente=_id_cliente())}
    mis = [dict(numero_reclamo=r.numero_reclamo, fecha=_fecha(r.fecha_reclamo),
                producto=nombres.get(r.id_lote_producto, ("—", "—"))[1],
                numero_lote=nombres.get(r.id_lote_producto, ("—", "—"))[0],
                numero_factura=numeros.get(r.id_factura), estado=r.estado, resolucion=r.resolucion)
           for r in ReclamoCliente.query.filter_by(id_cliente=_id_cliente())
           .order_by(ReclamoCliente.fecha_reclamo.desc(), ReclamoCliente.id_reclamo.desc())]
    return _render("portal_cliente/reclamos.html", lotes=lotes, reclamos=mis, form=request.form)
