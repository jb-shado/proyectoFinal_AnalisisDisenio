"""Rutas del rol VENDEDOR conectadas a PostgreSQL (Flask-SQLAlchemy).

Usa los modelos de app/models.py tal como están (sin modificarlos). Cada vista
devuelve a las plantillas las mismas claves que antes devolvían los datos
simulados, para que los templates no cambien.

Notas de la base de datos:
- El stock de un producto es la suma de lotes_productos 'disponible' y no vencidos.
- Al insertar en pedido_lotes, el trigger trg_despacho_producto descuenta el stock
  del lote y registra el movimiento de inventario: aquí NO se descuenta a mano.
- Al emitir una factura se crea también su cuenta por cobrar (cuentas_por_cobrar);
  los cobros y pagos trabajan sobre esa tabla.
- Reclamos y trazabilidad siguen viniendo de ..calidad.routes (ver nota abajo).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from . import ventas_bp
# Reclamos y trazabilidad se comparten con el rol calidad. Siguen usando lo que
# haga calidad/routes.py: cuando conectes ese archivo a la BD, estas vistas
# quedan conectadas también.
from ..calidad.routes import (actualizar_reclamo, filas_reclamos, reclamo_por_id,
                              traza_adelante, traza_atras)
from ..models import (Cliente, CuentaPorCobrar, Factura, LoteProducto, NotaDespacho,
                      PagoCliente, Pedido, PedidoDetalle, PedidoLote, Producto, db)

MENU = [
    ("Panel", "ventas.panel", "Resumen comercial"),
    ("Clientes", "ventas.clientes", "Datos comerciales"),
    ("Pedidos", "ventas.pedidos", "Stock en tiempo real"),
    ("Pedidos en línea", "ventas.pedidos_online", "Confirmar o rechazar"),
    ("Facturas y despachos", "ventas.facturas", "Asigna lotes entregados"),
    ("Cobros", "ventas.cobros", "Pagos de clientes"),
    ("Reclamos", "ventas.reclamos", "Atender con trazabilidad"),
]
IVA = Decimal("0.13")
CENT = Decimal("0.01")
DIAS_CREDITO = 30


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="vendedor", **ctx)


# ====================================================================
# UTILIDADES
# ====================================================================
def _n(x):
    """Cantidad sin ceros sobrantes: Decimal('110.000') -> 110."""
    if x is None:
        return 0
    x = Decimal(x)
    return int(x) if x == x.to_integral_value() else float(x)


def _m(x):
    """Dinero como float con 2 decimales (para mostrar en plantillas)."""
    return round(float(x or 0), 2)


def _fecha(x):
    """date/datetime -> 'YYYY-MM-DD' (mismo formato que usaban las plantillas)."""
    if x is None:
        return None
    if isinstance(x, datetime):
        x = x.date()
    return x.isoformat()


def _uid():
    """Id del usuario logueado (si tu login guarda 'id_usuario' en la sesión)."""
    return session.get("id_usuario")


def _error_bd(mensaje="No se pudo guardar en la base de datos. Intenta de nuevo."):
    db.session.rollback()
    flash(mensaje, "error")


def _siguiente_numero(columna, prefijo):
    """Genera PED-2026-011, FAC-2026-011, etc. según el último número del año."""
    patron = f"{prefijo}-{date.today().year}-"
    ultimo = (db.session.query(columna).filter(columna.like(patron + "%"))
              .order_by(func.length(columna).desc(), columna.desc()).first())
    n = int(ultimo[0].rsplit("-", 1)[1]) + 1 if ultimo else 1
    return f"{patron}{n:03d}"


def _stocks(ids=None):
    """{id_producto: stock} sumando lotes disponibles y no vencidos."""
    q = (db.session.query(LoteProducto.id_producto, func.coalesce(func.sum(LoteProducto.cantidad_actual), 0))
         .filter(LoteProducto.estado == "disponible", LoteProducto.fecha_vencimiento >= date.today())
         .group_by(LoteProducto.id_producto))
    if ids:
        q = q.filter(LoteProducto.id_producto.in_(ids))
    return {i: _n(s) for i, s in q.all()}


# ---------------------------------------------------------- vistas (lo que esperan las plantillas)
def _query_pedidos():
    return Pedido.query.options(joinedload(Pedido.cliente))


def _vistas_pedidos(pedidos):
    facturas = {}
    ids = [p.id_pedido for p in pedidos]
    if ids:
        for f in (Factura.query.filter(Factura.id_pedido.in_(ids), Factura.estado != "anulada")
                  .order_by(Factura.id_factura)):
            facturas[f.id_pedido] = f
    filas = []
    for p in pedidos:
        f = facturas.get(p.id_pedido)
        filas.append(dict(
            id_pedido=p.id_pedido, numero_pedido=p.numero_pedido, id_cliente=p.id_cliente,
            origen=p.origen, estado=p.estado, fecha=_fecha(p.fecha_pedido), fecha_pedido=_fecha(p.fecha_pedido),
            fecha_entrega_estimada=_fecha(p.fecha_entrega_estimada), entrega=_fecha(p.fecha_entrega_estimada),
            subtotal=_m(p.subtotal), impuestos=_m(p.impuestos), total=_m(p.total), observacion=p.observacion,
            cliente=p.cliente.razon_social, id_factura=f.id_factura if f else None,
            numero_factura=f.numero_factura if f else None))
    return filas


def _lineas(pedido):
    return [dict(id_producto=d.id_producto, codigo=d.producto.codigo, producto=d.producto.nombre,
                 cantidad=_n(d.cantidad), precio_unitario=_m(d.precio_unitario),
                 subtotal=_m(d.cantidad * d.precio_unitario))
            for d in sorted(pedido.detalle, key=lambda d: d.id_detalle)]


def _nota_de(id_factura):
    """Última nota de despacho no anulada de una factura (o None)."""
    return (NotaDespacho.query.filter(NotaDespacho.id_factura == id_factura, NotaDespacho.estado != "anulada")
            .order_by(NotaDespacho.id_nota.desc()).first())


def _vistas_facturas(facturas):
    if not facturas:
        return []
    notas = {}
    for n in (NotaDespacho.query.filter(NotaDespacho.id_factura.in_([f.id_factura for f in facturas]),
                                        NotaDespacho.estado != "anulada").order_by(NotaDespacho.id_nota)):
        notas[n.id_factura] = n
    ids_pedido = [f.id_pedido for f in facturas if f.id_pedido]
    numeros = {p.id_pedido: p.numero_pedido
               for p in Pedido.query.filter(Pedido.id_pedido.in_(ids_pedido))} if ids_pedido else {}
    filas = []
    for f in facturas:
        n = notas.get(f.id_factura)
        filas.append(dict(
            id_factura=f.id_factura, numero_factura=f.numero_factura, id_pedido=f.id_pedido,
            id_cliente=f.id_cliente, fecha=_fecha(f.fecha_emision), fecha_emision=_fecha(f.fecha_emision),
            subtotal=_m(f.subtotal), impuestos=_m(f.impuestos), total=_m(f.total), estado=f.estado,
            saldo_pendiente=_m(f.saldo_pendiente), cliente=f.cliente.razon_social,
            numero_pedido=numeros.get(f.id_pedido), despacho=n.estado if n else None,
            numero_nota=n.numero_nota if n else None, transportista=n.transportista if n else None,
            id_nota=n.id_nota if n else None))
    return filas


def _pedido_de(factura):
    if not factura.id_pedido:
        abort(404)
    return Pedido.query.get_or_404(factura.id_pedido)


def _lotes_candidatos(pedido, bloquear=False):
    """Lotes disponibles y no vencidos de los productos del pedido (vence primero = primero en la lista)."""
    ids = [d.id_producto for d in pedido.detalle]
    q = LoteProducto.query.filter(LoteProducto.id_producto.in_(ids), LoteProducto.estado == "disponible",
                                  LoteProducto.cantidad_actual > 0, LoteProducto.fecha_vencimiento >= date.today())
    if bloquear:
        q = q.with_for_update()  # evita que dos vendedores usen el mismo stock a la vez
    lotes = q.all()
    nombres = {p.id_producto: p.nombre for p in Producto.query.filter(Producto.id_producto.in_(ids))}
    lotes.sort(key=lambda l: (nombres[l.id_producto], l.fecha_vencimiento))
    return lotes, nombres


def _vista_lote(l, nombres):
    return dict(id_lote_producto=l.id_lote_producto, numero_lote=l.numero_lote, id_producto=l.id_producto,
                fecha_vencimiento=_fecha(l.fecha_vencimiento), cantidad_actual=_n(l.cantidad_actual),
                producto=nombres[l.id_producto])


# ====================================================================
# RUTAS
# ====================================================================
@ventas_bp.route("/")
def panel():
    por_cobrar = (db.session.query(func.coalesce(func.sum(Factura.saldo_pendiente), 0))
                  .filter(Factura.estado != "anulada").scalar())
    kpis = dict(
        pedidos_pendientes=Pedido.query.filter_by(estado="pendiente", origen="vendedor").count(),
        online_pendientes=Pedido.query.filter_by(estado="pendiente", origen="portal").count(),
        por_cobrar=_m(por_cobrar),
        reclamos_abiertos=sum(1 for r in filas_reclamos() if r["estado"] in ("abierto", "en_revision")))
    recientes = _vistas_pedidos(_query_pedidos().order_by(Pedido.id_pedido.desc()).limit(6).all())
    return _render("vendedor/panel.html", kpis=kpis, recientes=recientes)


# ------------------------------------------------------------ Clientes
def _dict_cliente(c, **extra):
    return dict(id_cliente=c.id_cliente, nit_ci=c.nit_ci, razon_social=c.razon_social,
                nombre_contacto=c.nombre_contacto, telefono=c.telefono, email=c.email,
                direccion=c.direccion, limite_credito=_n(c.limite_credito), **extra)


@ventas_bp.route("/clientes")
def clientes():
    buscar = request.args.get("q", "").strip()
    q = Cliente.query
    if buscar:
        patron = f"%{buscar}%"
        q = q.filter(or_(Cliente.razon_social.ilike(patron), Cliente.nit_ci.ilike(patron)))
    saldos = dict(db.session.query(Factura.id_cliente, func.sum(Factura.saldo_pendiente))
                  .filter(Factura.estado != "anulada").group_by(Factura.id_cliente).all())
    filas = [_dict_cliente(c, saldo_pendiente=_m(saldos.get(c.id_cliente)))
             for c in q.order_by(Cliente.id_cliente).all()]
    return _render("vendedor/clientes.html", buscar=buscar, clientes=filas)


def _datos_cliente():
    f = request.form
    try:
        limite = Decimal(f.get("limite_credito") or 0)
    except InvalidOperation:
        limite = Decimal(0)
    return dict(nit_ci=f.get("nit_ci", "").strip() or None, razon_social=f.get("razon_social", "").strip(),
                nombre_contacto=f.get("nombre_contacto") or None, telefono=f.get("telefono") or None,
                email=f.get("email") or None, direccion=f.get("direccion") or None,
                limite_credito=limite)


@ventas_bp.route("/clientes/nuevo", methods=["GET", "POST"])
def cliente_nuevo():
    if request.method == "POST":
        datos = _datos_cliente()
        if not datos["razon_social"]:
            flash("Escribe la razón social del cliente.", "error")
            return _render("vendedor/cliente_form.html", c=datos)
        try:
            Cliente.insertar(**datos)
        except SQLAlchemyError:
            _error_bd("No se pudo crear el cliente (¿ya existe ese NIT/CI?).")
            return _render("vendedor/cliente_form.html", c=datos)
        flash("Cliente creado.", "ok")
        return redirect(url_for("ventas.clientes"))
    return _render("vendedor/cliente_form.html", c={})


@ventas_bp.route("/clientes/<int:id>/editar", methods=["GET", "POST"])
def cliente_editar(id):
    cliente = Cliente.query.get_or_404(id)
    if request.method == "POST":
        datos = _datos_cliente()
        if not datos["razon_social"]:
            flash("Escribe la razón social del cliente.", "error")
            return _render("vendedor/cliente_form.html", c=datos, id=id)
        try:
            Cliente.actualizar(id, **datos)
        except SQLAlchemyError:
            _error_bd("No se pudo actualizar el cliente (¿ya existe ese NIT/CI?).")
            return _render("vendedor/cliente_form.html", c=datos, id=id)
        flash("Cliente actualizado.", "ok")
        return redirect(url_for("ventas.clientes"))
    return _render("vendedor/cliente_form.html", c=_dict_cliente(cliente), id=id)


# ------------------------------------------------------------ Pedidos
@ventas_bp.route("/pedidos")
def pedidos():
    estado = request.args.get("estado", "")
    q = _query_pedidos()
    if estado:
        q = q.filter(Pedido.estado == estado)
    filas = _vistas_pedidos(q.order_by(Pedido.id_pedido.desc()).all())
    return _render("vendedor/pedidos.html", estado=estado, pedidos=filas)


def _productos_con_stock():
    stocks = _stocks()
    return [dict(id_producto=p.id_producto, codigo=p.codigo, nombre=p.nombre,
                 precio_venta=_m(p.precio_venta), stock=stocks.get(p.id_producto, 0))
            for p in Producto.query.filter_by(activo=True).order_by(Producto.id_producto).all()]


@ventas_bp.route("/pedidos/nuevo", methods=["GET", "POST"])
def pedido_nuevo():
    productos = _productos_con_stock()
    if request.method == "POST":
        lineas, errores = [], []
        for p in productos:
            cant = request.form.get(f"cant_{p['id_producto']}", type=int) or 0
            if cant <= 0:
                continue
            if cant > p["stock"]:
                errores.append(f"{p['nombre']}: pides {cant} y hay {p['stock']}.")
            lineas.append((p["id_producto"], cant))
        id_cliente = request.form.get("id_cliente", type=int)
        cliente = db.session.get(Cliente, id_cliente) if id_cliente else None
        if not cliente:
            errores.append("Elige un cliente.")
        if not lineas:
            errores.append("Agrega al menos un producto.")
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            precios = {p.id_producto: p.precio_venta
                       for p in Producto.query.filter(Producto.id_producto.in_([i for i, _ in lineas]))}
            subtotal = sum((precios[i] * c for i, c in lineas), Decimal(0)).quantize(CENT)
            impuestos = (subtotal * IVA).quantize(CENT)
            try:
                entrega = date.fromisoformat(request.form.get("entrega"))
            except (TypeError, ValueError):
                entrega = date.today() + timedelta(days=3)
            try:
                pedido = Pedido(
                    numero_pedido=_siguiente_numero(Pedido.numero_pedido, "PED"), id_cliente=id_cliente,
                    origen="vendedor", estado="confirmado", fecha_entrega_estimada=entrega,
                    subtotal=subtotal, impuestos=impuestos, total=subtotal + impuestos,
                    id_usuario_confirma=_uid(), observacion=request.form.get("observacion") or None)
                pedido.detalle = [PedidoDetalle(id_producto=i, cantidad=c, precio_unitario=precios[i])
                                  for i, c in lineas]
                db.session.add(pedido)
                db.session.commit()
            except SQLAlchemyError:
                _error_bd("No se pudo registrar el pedido. Intenta de nuevo.")
            else:
                flash("Pedido registrado.", "ok")
                return redirect(url_for("ventas.pedido_detalle", id=pedido.id_pedido))
    clientes_activos = [_dict_cliente(c) for c in
                        Cliente.query.filter_by(activo=True).order_by(Cliente.razon_social).all()]
    return _render("vendedor/pedido_nuevo.html", productos=productos, clientes=clientes_activos,
                   iva=float(IVA), manana=date.today() + timedelta(days=1))


@ventas_bp.route("/pedidos/<int:id>")
def pedido_detalle(id):
    pedido = _query_pedidos().filter(Pedido.id_pedido == id).first_or_404()
    return _render("vendedor/pedido_detalle.html", p=_vistas_pedidos([pedido])[0], lineas=_lineas(pedido))


# ------------------------------------------------------------ Pedidos en línea
@ventas_bp.route("/pedidos-en-linea")
def pedidos_online():
    pendientes = (_query_pedidos().filter_by(origen="portal", estado="pendiente")
                  .order_by(Pedido.id_pedido).all())
    stocks = _stocks()
    filas = []
    for p, vista in zip(pendientes, _vistas_pedidos(pendientes)):
        lineas = [dict(producto=l["producto"], cantidad=l["cantidad"], stock=stocks.get(l["id_producto"], 0))
                  for l in _lineas(p)]
        filas.append({**vista, "lineas": lineas,
                      "hay_stock": all(l["stock"] >= l["cantidad"] for l in lineas)})
    return _render("vendedor/pedidos_online.html", pedidos=filas)


@ventas_bp.route("/pedidos-en-linea/<int:id>/<accion>", methods=["POST"])
def resolver_pedido_online(id, accion):
    if accion not in ("confirmar", "rechazar"):
        abort(404)
    pedido = Pedido.query.get_or_404(id)
    stocks = _stocks([d.id_producto for d in pedido.detalle])
    if pedido.estado != "pendiente":
        flash("Este pedido ya fue resuelto.", "error")
    elif accion == "confirmar" and any(stocks.get(d.id_producto, 0) < d.cantidad for d in pedido.detalle):
        flash("No hay stock suficiente para confirmar este pedido.", "error")
    elif accion == "rechazar" and not request.form.get("motivo", "").strip():
        flash("Escribe el motivo del rechazo.", "error")
    else:
        pedido.estado = "confirmado" if accion == "confirmar" else "rechazado"
        pedido.observacion = request.form.get("motivo") or pedido.observacion
        pedido.id_usuario_confirma = _uid()
        try:
            db.session.commit()
            flash(f"Pedido {pedido.estado}.", "ok")
        except SQLAlchemyError:
            _error_bd()
    return redirect(url_for("ventas.pedidos_online"))


# ------------------------------------------------------------ Facturas y despachos
@ventas_bp.route("/facturas")
def facturas():
    lista = (Factura.query.options(joinedload(Factura.cliente)).order_by(Factura.id_factura.desc()).all())
    facturados = {i for (i,) in db.session.query(Factura.id_pedido)
                  .filter(Factura.id_pedido.isnot(None), Factura.estado != "anulada")}
    por_facturar = [dict(id_pedido=p["id_pedido"], numero_pedido=p["numero_pedido"],
                         cliente=p["cliente"], total=p["total"])
                    for p in _vistas_pedidos(_query_pedidos().filter(Pedido.estado == "confirmado")
                                             .order_by(Pedido.id_pedido).all())
                    if p["id_pedido"] not in facturados]
    return _render("vendedor/facturas.html", facturas=_vistas_facturas(lista), por_facturar=por_facturar)


@ventas_bp.route("/facturas/emitir/<int:id_pedido>", methods=["POST"])
def emitir_factura(id_pedido):
    pedido = Pedido.query.get_or_404(id_pedido)
    if Factura.query.filter(Factura.id_pedido == id_pedido, Factura.estado != "anulada").first():
        flash("Ese pedido ya tiene factura.", "error")
        return redirect(url_for("ventas.facturas"))
    if pedido.estado != "confirmado":
        flash("Solo se pueden facturar pedidos confirmados.", "error")
        return redirect(url_for("ventas.facturas"))
    try:
        factura = Factura(numero_factura=_siguiente_numero(Factura.numero_factura, "FAC"),
                          id_pedido=pedido.id_pedido, id_cliente=pedido.id_cliente,
                          subtotal=pedido.subtotal, impuestos=pedido.impuestos, total=pedido.total,
                          estado="emitida", saldo_pendiente=pedido.total, id_usuario_emite=_uid())
        db.session.add(factura)
        db.session.flush()  # obtiene id_factura
        db.session.add(CuentaPorCobrar(id_factura=factura.id_factura, id_cliente=pedido.id_cliente,
                                       monto_original=pedido.total, saldo=pedido.total,
                                       fecha_vencimiento=date.today() + timedelta(days=DIAS_CREDITO),
                                       estado="pendiente"))
        db.session.commit()
    except SQLAlchemyError:
        _error_bd("No se pudo emitir la factura. Intenta de nuevo.")
        return redirect(url_for("ventas.facturas"))
    flash("Factura emitida. Ahora asigna los lotes.", "ok")
    return redirect(url_for("ventas.factura_detalle", id=factura.id_factura))


@ventas_bp.route("/facturas/<int:id>")
def factura_detalle(id):
    factura = Factura.query.options(joinedload(Factura.cliente)).filter_by(id_factura=id).first_or_404()
    pedido = _pedido_de(factura)
    asignados = [dict(producto=prod.nombre, numero_lote=lote.numero_lote, cantidad=_n(pl.cantidad),
                      fecha_vencimiento=_fecha(lote.fecha_vencimiento))
                 for pl, lote, prod in (db.session.query(PedidoLote, LoteProducto, Producto)
                                        .join(LoteProducto, LoteProducto.id_lote_producto == PedidoLote.id_lote_producto)
                                        .join(Producto, Producto.id_producto == LoteProducto.id_producto)
                                        .filter(PedidoLote.id_pedido == pedido.id_pedido)
                                        .order_by(PedidoLote.id_pedido_lote))]
    lotes, nombres = _lotes_candidatos(pedido)
    return _render("vendedor/factura_detalle.html", f=_vistas_facturas([factura])[0], lineas=_lineas(pedido),
                   asignados=asignados, candidatos=[_vista_lote(l, nombres) for l in lotes])


@ventas_bp.route("/facturas/<int:id>/asignar-lotes", methods=["POST"])
def asignar_lotes(id):
    factura = Factura.query.get_or_404(id)
    pedido = _pedido_de(factura)
    if _nota_de(factura.id_factura):
        flash("Esta factura ya tiene un despacho registrado.", "error")
        return redirect(url_for("ventas.factura_detalle", id=id))
    lotes, _ = _lotes_candidatos(pedido, bloquear=True)
    elegidos = []
    for l in lotes:
        cant = request.form.get(f"lote_{l.id_lote_producto}", type=int) or 0
        if cant <= 0:
            continue
        if cant > l.cantidad_actual:
            db.session.rollback()  # libera el bloqueo de los lotes
            flash(f"Lote {l.numero_lote}: solo quedan {_n(l.cantidad_actual)}.", "error")
            return redirect(url_for("ventas.factura_detalle", id=id))
        elegidos.append((l, cant))
    if not elegidos:
        db.session.rollback()
        flash("Indica la cantidad de al menos un lote.", "error")
        return redirect(url_for("ventas.factura_detalle", id=id))
    try:
        for l, cant in elegidos:
            # El trigger de la BD descuenta el stock del lote y registra el movimiento.
            db.session.add(PedidoLote(id_pedido=pedido.id_pedido, id_lote_producto=l.id_lote_producto,
                                      cantidad=cant))
        db.session.add(NotaDespacho(
            numero_nota=_siguiente_numero(NotaDespacho.numero_nota, "ND"), id_factura=factura.id_factura,
            id_pedido=pedido.id_pedido, transportista=request.form.get("transportista") or None,
            direccion_entrega=pedido.cliente.direccion, estado="emitida", id_usuario_despacha=_uid()))
        pedido.estado = "despachado"
        db.session.commit()
    except SQLAlchemyError:
        _error_bd("No se pudo registrar el despacho. Intenta de nuevo.")
        return redirect(url_for("ventas.factura_detalle", id=id))
    flash("Lotes asignados y despacho registrado.", "ok")
    return redirect(url_for("ventas.factura_detalle", id=id))


@ventas_bp.route("/facturas/<int:id>/entregado", methods=["POST"])
def marcar_entregado(id):
    factura = Factura.query.get_or_404(id)
    nota = _nota_de(factura.id_factura)
    if not nota:
        abort(404)
    nota.estado = "entregada"
    _pedido_de(factura).estado = "entregado"
    try:
        db.session.commit()
        flash("Entrega confirmada.", "ok")
    except SQLAlchemyError:
        _error_bd()
    return redirect(url_for("ventas.factura_detalle", id=id))


# ------------------------------------------------------------ Cobros
def _cobros():
    q = (db.session.query(CuentaPorCobrar, Factura, Cliente)
         .join(Factura, Factura.id_factura == CuentaPorCobrar.id_factura)
         .join(Cliente, Cliente.id_cliente == CuentaPorCobrar.id_cliente)
         .filter(CuentaPorCobrar.saldo > 0, CuentaPorCobrar.estado != "anulada")
         .order_by(CuentaPorCobrar.fecha_vencimiento.asc().nullslast(), CuentaPorCobrar.id_cxc))
    return [dict(id_cxc=cxc.id_cxc, numero_factura=f.numero_factura, cliente=c.razon_social,
                 fecha_vencimiento=_fecha(cxc.fecha_vencimiento),
                 dias_mora=max((date.today() - cxc.fecha_vencimiento).days, 0) if cxc.fecha_vencimiento else 0,
                 saldo=_m(cxc.saldo))
            for cxc, f, c in q.all()]


def _ultimos_pagos(limite=10):
    q = (db.session.query(PagoCliente, Factura, Cliente)
         .join(CuentaPorCobrar, CuentaPorCobrar.id_cxc == PagoCliente.id_cxc)
         .join(Factura, Factura.id_factura == CuentaPorCobrar.id_factura)
         .join(Cliente, Cliente.id_cliente == CuentaPorCobrar.id_cliente)
         .order_by(PagoCliente.fecha_pago.desc(), PagoCliente.id_pago.desc()).limit(limite))
    return [dict(fecha=_fecha(p.fecha_pago), cliente=c.razon_social, numero_factura=f.numero_factura,
                 monto=_m(p.monto), metodo_pago=p.metodo_pago, referencia=p.referencia)
            for p, f, c in q.all()]


@ventas_bp.route("/cobros")
def cobros():
    return _render("vendedor/cobros.html", cobros=_cobros(), pagos=_ultimos_pagos())


@ventas_bp.route("/cobros/<int:id_cxc>/pago", methods=["POST"])
def registrar_pago(id_cxc):
    cxc = CuentaPorCobrar.query.get_or_404(id_cxc)
    try:
        monto = Decimal(str(request.form.get("monto", type=float) or 0)).quantize(CENT)
    except InvalidOperation:
        monto = Decimal(0)
    if cxc.estado == "anulada" or monto <= 0 or monto > cxc.saldo:
        flash(f"El pago debe ser mayor que 0 y no superar el saldo ({_m(cxc.saldo):.2f}).", "error")
        return redirect(url_for("ventas.cobros"))
    try:
        db.session.add(PagoCliente(id_cxc=cxc.id_cxc, monto=monto, metodo_pago=request.form.get("metodo"),
                                   referencia=request.form.get("referencia") or None,
                                   id_usuario_registra=_uid()))
        cxc.saldo = cxc.saldo - monto
        factura = cxc.factura
        factura.saldo_pendiente = cxc.saldo
        if cxc.saldo <= 0:
            cxc.estado = "pagada"
            factura.estado = "pagada"
        db.session.commit()
    except SQLAlchemyError:
        _error_bd("No se pudo registrar el pago. Intenta de nuevo.")
        return redirect(url_for("ventas.cobros"))
    flash("Pago registrado.", "ok")
    return redirect(url_for("ventas.cobros"))


# ------------------------------------------------------------ Reclamos (datos compartidos con calidad)
@ventas_bp.route("/reclamos")
def reclamos():
    estado = request.args.get("estado", "")
    return _render("vendedor/reclamos.html", estado=estado, reclamos=filas_reclamos(estado))


@ventas_bp.route("/reclamos/<int:id>")
def reclamo_detalle(id):
    r = reclamo_por_id(id)
    if not r:
        abort(404)
    return _render("vendedor/reclamo_detalle.html", r=r,
                   atras=traza_atras(r["numero_lote"]), adelante=traza_adelante(r["numero_lote"]))


@ventas_bp.route("/reclamos/<int:id>/atender", methods=["POST"])
def atender_reclamo(id):
    actualizar_reclamo(id, request.form.get("estado", "en_revision"), request.form.get("resolucion"))
    flash("Reclamo actualizado.", "ok")
    return redirect(url_for("ventas.reclamo_detalle", id=id))