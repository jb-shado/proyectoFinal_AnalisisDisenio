"""Rutas del rol ALMACENERO conectadas a PostgreSQL (Flask-SQLAlchemy + app/models.py).

Pantallas (diagrama de navegación del almacenero y hoja pantallas_ERP_por_rol):
  ALM-00 Panel de inicio .............. RF-10
  ALM-01 Recepción de insumos ......... RF-06, RF-11  (RN-05, RN-06)
  ALM-02 Existencias por lote ......... RF-08, RF-10  (RN-20)
  ALM-03 Despacho FEFO ................ RF-09        (RN-07, RN-08, RN-12)
  ALM-04 Inventario físico y ajustes .. RF-12        (RN-09)

Tablas que usa: insumos, productos, unidades_medida, lotes_insumos, lotes_productos,
ordenes_compra, orden_compra_detalle, recepciones_compra, cuentas_por_pagar,
movimientos_inventario, inventarios_fisicos, inventario_fisico_detalle,
ordenes_produccion, receta_detalle, consumo_insumos_produccion, auditoria.

Notas de la base de datos:
- Al insertar en consumo_insumos_produccion, el trigger trg_consumo_insumo descuenta el
  lote y registra el movimiento: por eso el despacho a una orden de producción NO
  descuenta a mano.
- Las plantillas reciben las mismas claves que cuando había datos simulados.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import flash, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from . import almacen_bp
from ..models import (Auditoria, ConsumoInsumoProduccion, CuentaPorPagar, Insumo, InventarioFisico,
                      InventarioFisicoDetalle, LoteInsumo, LoteProducto, MovimientoInventario, OrdenCompra,
                      OrdenProduccion, Producto, Proveedor, RecepcionCompra, Rol, Usuario, db)

MENU = [
    ("Panel", "almacen.panel", "Resumen del día"),
    ("Recepción de insumos", "almacen.recepcion", "Lote y vencimiento"),
    ("Existencias por lote", "almacen.existencias", "Alertas de vencimiento"),
    ("Despacho FEFO", "almacen.despacho", "Primero en vencer"),
    ("Inventario físico", "almacen.inventario", "Ajustes con justificación"),
]
DIAS_ALERTA = 30        # misma ventana que la vista v_productos_por_vencer
DIAS_PAGO = 30          # plazo por defecto de la cuenta por pagar


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="almacenero", **ctx)


# ====================================================================
# UTILIDADES
# ====================================================================
def _n(x):
    """Decimal('110.000') -> 110 ; Decimal('3.250') -> 3.25 (para mostrar)."""
    if x is None:
        return 0
    x = Decimal(x)
    return int(x) if x == x.to_integral_value() else float(x.normalize())


def _dec(valor):
    try:
        return Decimal(str(valor).replace(",", ".")).quantize(Decimal("0.001"))
    except (InvalidOperation, ValueError):
        return None


def _fecha(x):
    if x is None:
        return None
    if isinstance(x, datetime):
        x = x.date()
    return x.isoformat()


def _uid():
    """Usuario que hace la acción: el de la sesión o, mientras no haya login, el primer almacenero."""
    if session.get("id_usuario"):
        return session["id_usuario"]
    u = Usuario.query.join(Rol).filter(Rol.nombre == "almacenero").order_by(Usuario.id_usuario).first()
    return u.id_usuario if u else None


def _auditar(accion, tabla, registro, datos=None):     # RN-03
    db.session.add(Auditoria(id_usuario=_uid(), accion=accion, tabla_afectada=tabla, registro_id=str(registro),
                             datos_nuevos=datos, ip_origen=request.remote_addr))


def _error_bd(e, mensaje="No se pudo guardar en la base de datos. Intenta de nuevo."):
    db.session.rollback()
    print("Error de base de datos:", e)
    flash(mensaje, "error")


def _alerta(lote):
    if lote.estado in ("agotado", "baja"):
        return None
    if lote.fecha_vencimiento is None:
        return "sin_vencimiento"
    d = (lote.fecha_vencimiento - date.today()).days
    if d < 0:
        return "vencido"
    if d <= 7:
        return "critico"
    if d <= DIAS_ALERTA:
        return "por_vencer"
    return "ok"


def _fila_insumo(l):
    i = l.insumo
    return dict(tipo="insumo", id_lote=l.id_lote_insumo, id_item=i.id_insumo, codigo=i.codigo, item=i.nombre,
                unidad=i.unidad.abreviatura if i.unidad else "", numero_lote=l.numero_lote,
                fecha_vencimiento=_fecha(l.fecha_vencimiento), cantidad_actual=_n(l.cantidad_actual),
                estado=l.estado, alerta=_alerta(l), proveedor=l.proveedor.razon_social if l.proveedor else None,
                dias=(l.fecha_vencimiento - date.today()).days if l.fecha_vencimiento else None)


def _fila_producto(l):
    p = l.producto
    return dict(tipo="producto", id_lote=l.id_lote_producto, id_item=p.id_producto, codigo=p.codigo, item=p.nombre,
                unidad=p.unidad.abreviatura if p.unidad else "unid", numero_lote=l.numero_lote,
                fecha_vencimiento=_fecha(l.fecha_vencimiento), cantidad_actual=_n(l.cantidad_actual),
                estado=l.estado, alerta=_alerta(l), proveedor=None,
                dias=(l.fecha_vencimiento - date.today()).days if l.fecha_vencimiento else None)


def _todas_las_filas():
    return ([_fila_insumo(l) for l in LoteInsumo.query.all()] +
            [_fila_producto(l) for l in LoteProducto.query.all()])


def _usable(l):
    return (l.estado == "disponible" and l.cantidad_actual > 0
            and (l.fecha_vencimiento is None or l.fecha_vencimiento >= date.today()))


def _stock_insumos():
    """Como la vista v_stock_insumos, pero sin contar lotes vencidos."""
    hoy = date.today()
    sumas = dict(db.session.query(LoteInsumo.id_insumo, func.coalesce(func.sum(LoteInsumo.cantidad_actual), 0))
                 .filter(LoteInsumo.estado == "disponible",
                         (LoteInsumo.fecha_vencimiento.is_(None)) | (LoteInsumo.fecha_vencimiento >= hoy))
                 .group_by(LoteInsumo.id_insumo).all())
    filas = []
    for i in Insumo.query.filter_by(activo=True).order_by(Insumo.codigo):
        stock = sumas.get(i.id_insumo, Decimal(0))
        filas.append(dict(id_insumo=i.id_insumo, codigo=i.codigo, nombre=i.nombre,
                          unidad=i.unidad.abreviatura if i.unidad else "", stock_minimo=_n(i.stock_minimo),
                          stock_actual=_n(stock),
                          estado_stock="reponer" if stock <= (i.stock_minimo or 0) else "ok"))
    return filas


def _modelo(tipo):
    return LoteInsumo if tipo == "insumo" else LoteProducto


def _lotes_fefo(tipo, id_item):
    """RN-07: lotes utilizables ordenados por vencimiento (el que vence primero sale primero)."""
    M = _modelo(tipo)
    campo = M.id_insumo if tipo == "insumo" else M.id_producto
    lotes = [l for l in M.query.filter(campo == id_item).all() if _usable(l)]
    return sorted(lotes, key=lambda l: l.fecha_vencimiento or date.max)


def _plan_fefo(tipo, id_item, cantidad):
    plan, falta = [], Decimal(cantidad)
    fila = _fila_insumo if tipo == "insumo" else _fila_producto
    for l in _lotes_fefo(tipo, id_item):
        if falta <= 0:
            break
        toma = min(falta, l.cantidad_actual)
        plan.append(dict(fila(l), lote=l, tomar=_n(toma), _toma=toma, queda=_n(l.cantidad_actual - toma)))
        falta -= toma
    return plan, falta


def _registrar_salida(lote, tipo, cantidad, documento, motivo="despacho", observacion=None):
    """Descuenta el lote y deja el movimiento. RN-08: si llega a cero pasa a 'agotado'."""
    lote.cantidad_actual = lote.cantidad_actual - cantidad
    if lote.cantidad_actual <= 0:
        lote.cantidad_actual, lote.estado = Decimal(0), "agotado"
    db.session.add(MovimientoInventario(
        tipo_item=tipo, id_item=lote.id_insumo if tipo == "insumo" else lote.id_producto,
        id_lote=lote.id_lote_insumo if tipo == "insumo" else lote.id_lote_producto,
        tipo_movimiento=motivo, cantidad=-cantidad, documento_ref=documento[:50], id_usuario=_uid(),
        observacion=observacion, costo_unitario=getattr(lote, "costo_unitario", None)))


def _recibido_por_linea():
    """{(id_orden_compra, id_insumo): cantidad ya recibida} usando recepciones_compra + lotes_insumos."""
    filas = (db.session.query(RecepcionCompra.id_orden_compra, LoteInsumo.id_insumo,
                              func.sum(RecepcionCompra.cantidad_recibida))
             .join(LoteInsumo, LoteInsumo.id_lote_insumo == RecepcionCompra.id_lote_insumo)
             .group_by(RecepcionCompra.id_orden_compra, LoteInsumo.id_insumo).all())
    return {(o, i): c for o, i, c in filas}


def _lineas_pendientes():
    """Líneas de órdenes de compra emitidas con saldo por recibir (RN-05)."""
    recibido = _recibido_por_linea()
    filas = []
    ordenes = (OrdenCompra.query.filter(OrdenCompra.estado.in_(("emitida", "recibida_parcial")))
               .order_by(OrdenCompra.fecha_entrega_esperada, OrdenCompra.id_orden_compra).all())
    for o in ordenes:
        for d in sorted(o.detalle, key=lambda x: x.id_detalle):
            rec = recibido.get((o.id_orden_compra, d.id_insumo), Decimal(0))
            pendiente = d.cantidad - rec
            if pendiente > 0:
                i = d.insumo
                filas.append(dict(clave=str(d.id_detalle), numero_orden=o.numero_orden,
                                  proveedor=o.proveedor.razon_social, insumo=i.nombre,
                                  unidad=i.unidad.abreviatura if i.unidad else "", perecedero=i.perecedero,
                                  pedido=_n(d.cantidad), recibido=_n(rec), pendiente=_n(pendiente),
                                  entrega=_fecha(o.fecha_entrega_esperada), _detalle=d, _orden=o, _pend=pendiente))
    return filas


def _recepciones(limite=None):
    q = (db.session.query(RecepcionCompra, OrdenCompra, Insumo, Proveedor, Usuario)
         .join(OrdenCompra, OrdenCompra.id_orden_compra == RecepcionCompra.id_orden_compra)
         .outerjoin(LoteInsumo, LoteInsumo.id_lote_insumo == RecepcionCompra.id_lote_insumo)
         .outerjoin(Insumo, Insumo.id_insumo == LoteInsumo.id_insumo)
         .outerjoin(Proveedor, Proveedor.id_proveedor == OrdenCompra.id_proveedor)
         .outerjoin(Usuario, Usuario.id_usuario == RecepcionCompra.id_usuario_recibe)
         .order_by(RecepcionCompra.fecha_recepcion.desc(), RecepcionCompra.id_recepcion.desc()))
    if limite:
        q = q.limit(limite)
    return [dict(fecha=_fecha(r.fecha_recepcion), numero_orden=o.numero_orden, insumo=i.nombre if i else "—",
                 numero_lote=r.numero_lote, fecha_vencimiento=_fecha(r.fecha_vencimiento),
                 cantidad=_n(r.cantidad_recibida), unidad=i.unidad.abreviatura if i and i.unidad else "",
                 proveedor=p.razon_social if p else None, responsable=u.nombre_completo if u else None)
            for r, o, i, p, u in q.all()]


def _ops_pendientes():
    """Órdenes de producción planificadas o en proceso: lo que cada una todavía necesita del almacén."""
    pend = []
    ops = (OrdenProduccion.query.filter(OrdenProduccion.estado.in_(("planificada", "en_proceso")))
           .order_by(OrdenProduccion.id_orden_produccion).all())
    for op in ops:
        rec = op.receta
        if not rec or not rec.rendimiento:
            continue
        entregado = {}
        for c in op.consumos:
            entregado[c.id_insumo] = entregado.get(c.id_insumo, Decimal(0)) + c.cantidad_consumida
        for d in rec.detalle:
            req = (d.cantidad * op.cantidad_planificada / rec.rendimiento).quantize(Decimal("0.001"))
            falta = req - entregado.get(d.id_insumo, Decimal(0))
            if falta > 0:
                pend.append(dict(id_solicitud=f"{op.id_orden_produccion}-{d.id_insumo}", documento=op.numero_orden,
                                 destino=f"Producción · {op.producto.nombre}", tipo="insumo", id_item=d.id_insumo,
                                 cantidad=_n(falta), item=d.insumo.nombre))
    return pend


# ====================================================================
# RUTAS
# ====================================================================
# ------------------------------------------------------------ ALM-00 Panel
@almacen_bp.route("/")
def panel():
    filas = _todas_las_filas()
    por_vencer = sorted([f for f in filas if f["alerta"] in ("critico", "por_vencer") and f["estado"] == "disponible"],
                        key=lambda f: f["fecha_vencimiento"])
    vencidos = [f for f in filas if f["alerta"] == "vencido" and f["cantidad_actual"] > 0
                and f["estado"] not in ("rechazado", "baja")]
    stock_bajo = [s for s in _stock_insumos() if s["estado_stock"] == "reponer"]
    kpis = dict(
        por_vencer=len(por_vencer),
        vencidos=len(vencidos),
        stock_bajo=len(stock_bajo),
        recepciones_hoy=RecepcionCompra.query.filter(RecepcionCompra.fecha_recepcion == date.today()).count(),
        por_recibir=len(_lineas_pendientes()),
        solicitudes=len(_ops_pendientes()),
    )
    return _render("almacenero/panel.html", kpis=kpis, por_vencer=por_vencer, vencidos=vencidos,
                   stock_bajo=stock_bajo, recepciones=_recepciones(5))


# ------------------------------------------------------------ ALM-01 Recepción de insumos
@almacen_bp.route("/recepcion", methods=["GET", "POST"])
def recepcion():
    pendientes = _lineas_pendientes()
    hoy = date.today()
    if request.method == "POST":
        f = request.form
        linea = next((p for p in pendientes if p["clave"] == f.get("linea")), None)
        numero_lote = f.get("numero_lote", "").strip().upper()
        vence = f.get("fecha_vencimiento") or None
        cantidad = _dec(f.get("cantidad", "0")) or Decimal(0)
        errores = []
        if not linea:
            errores.append("Elige la orden de compra y el insumo que estás recibiendo.")
        else:
            d = linea["_detalle"]
            if not numero_lote:
                errores.append("Escribe el número de lote del proveedor.")
            elif LoteInsumo.query.filter_by(id_insumo=d.id_insumo, numero_lote=numero_lote).first():
                errores.append(f"El lote {numero_lote} ya está registrado para {linea['insumo']} (RN-06).")
            if linea["perecedero"] and not vence:
                errores.append("Este insumo es perecedero: la fecha de vencimiento es obligatoria.")
            if vence and vence <= hoy.isoformat():
                errores.append("La fecha de vencimiento debe ser posterior a hoy; no se recibe mercadería vencida.")
            if cantidad <= 0:
                errores.append("La cantidad recibida debe ser mayor que cero.")
            elif cantidad > linea["_pend"]:
                errores.append(f"Solo faltan {linea['pendiente']} {linea['unidad']} por recibir de esa orden.")
        if errores:
            for e in errores:
                flash(e, "error")
            return _render("almacenero/recepcion.html", pendientes=pendientes, recepciones=_recepciones(),
                           form=f, hoy=hoy.isoformat())
        d, o = linea["_detalle"], linea["_orden"]
        try:
            # 1) lote del insumo  2) recepción  3) movimiento de inventario (RF-11)
            lote = LoteInsumo(id_insumo=d.id_insumo, numero_lote=numero_lote, id_proveedor=o.id_proveedor,
                              fecha_recepcion=hoy, fecha_vencimiento=vence, cantidad_inicial=cantidad,
                              cantidad_actual=cantidad, costo_unitario=d.precio_unitario, estado="disponible")
            db.session.add(lote)
            db.session.flush()
            db.session.add(RecepcionCompra(id_orden_compra=o.id_orden_compra, numero_lote=numero_lote,
                                           fecha_recepcion=hoy, fecha_vencimiento=vence, cantidad_recibida=cantidad,
                                           id_lote_insumo=lote.id_lote_insumo, id_usuario_recibe=_uid(),
                                           observacion=f.get("observacion") or None))
            db.session.add(MovimientoInventario(tipo_item="insumo", id_item=d.id_insumo, id_lote=lote.id_lote_insumo,
                                                tipo_movimiento="entrada", cantidad=cantidad,
                                                costo_unitario=d.precio_unitario, documento_ref=o.numero_orden,
                                                id_usuario=_uid()))
            # 4) estado de la orden: recibida o recibida_parcial
            db.session.flush()
            recibido = _recibido_por_linea()
            completa = all(recibido.get((o.id_orden_compra, x.id_insumo), 0) >= x.cantidad for x in o.detalle)
            o.estado = "recibida" if completa else "recibida_parcial"
            # 5) cuenta por pagar al proveedor (RF-26): se suma a la de esa orden o se crea
            monto = (cantidad * d.precio_unitario).quantize(Decimal("0.01"))
            cxp = CuentaPorPagar.query.filter_by(id_orden_compra=o.id_orden_compra).first()
            if cxp:
                cxp.monto_original += monto
                cxp.saldo += monto
                cxp.estado = "pendiente"
            else:
                db.session.add(CuentaPorPagar(id_orden_compra=o.id_orden_compra, id_proveedor=o.id_proveedor,
                                              monto_original=monto, saldo=monto,
                                              fecha_vencimiento=hoy + timedelta(days=DIAS_PAGO), estado="pendiente"))
            _auditar("RECEPCION", "recepciones_compra", numero_lote,
                     {"orden": o.numero_orden, "insumo": linea["insumo"], "cantidad": str(cantidad)})
            db.session.commit()
        except SQLAlchemyError as e:
            _error_bd(e)
            return redirect(url_for("almacen.recepcion"))
        flash(f"Recepción registrada: lote {numero_lote}, {_n(cantidad)} {linea['unidad']} de {linea['insumo']}. "
              f"El inventario ya está actualizado y se generó la cuenta por pagar de Bs {monto}.", "ok")
        return redirect(url_for("almacen.recepcion"))
    return _render("almacenero/recepcion.html", pendientes=pendientes, recepciones=_recepciones(), form={},
                   hoy=hoy.isoformat())


# ------------------------------------------------------------ ALM-02 Existencias por lote
@almacen_bp.route("/existencias")
def existencias():
    tipo = request.args.get("tipo", "")
    alerta = request.args.get("alerta", "")
    buscar = request.args.get("q", "").strip().lower()
    ver_agotados = request.args.get("agotados") == "1"
    filas = []
    for f in _todas_las_filas():
        if tipo and f["tipo"] != tipo:
            continue
        if not ver_agotados and f["estado"] in ("agotado", "baja"):
            continue
        if alerta == "atencion" and f["alerta"] not in ("vencido", "critico", "por_vencer"):
            continue
        if buscar and buscar not in f["item"].lower() and buscar not in f["numero_lote"].lower():
            continue
        filas.append(f)
    filas.sort(key=lambda f: (f["item"], f["fecha_vencimiento"] or "9999"))
    resumen = dict(vencidos=sum(1 for f in filas if f["alerta"] == "vencido"),
                   criticos=sum(1 for f in filas if f["alerta"] == "critico"),
                   por_vencer=sum(1 for f in filas if f["alerta"] == "por_vencer"))
    return _render("almacenero/existencias.html", filas=filas, tipo=tipo, alerta=alerta,
                   buscar=request.args.get("q", ""), ver_agotados=ver_agotados, resumen=resumen,
                   stock=_stock_insumos(), dias_alerta=DIAS_ALERTA)


@almacen_bp.route("/existencias/baja", methods=["POST"])
def dar_de_baja():
    """Lote vencido: se da de baja con justificación (RN-20: no se elimina, se anula)."""
    tipo = request.form.get("tipo")
    id_lote = request.form.get("id_lote", type=int)
    motivo = request.form.get("motivo", "").strip()
    lote = db.session.get(_modelo(tipo), id_lote) if tipo in ("insumo", "producto") else None
    if not lote:
        flash("No se encontró el lote.", "error")
    elif not motivo:
        flash("Escribe el motivo para dar de baja el lote.", "error")
    else:
        try:
            cant = lote.cantidad_actual
            _registrar_salida(lote, tipo, cant, "BAJA", motivo="baja", observacion=motivo)
            lote.estado = "baja"
            _auditar("BAJA_LOTE", "lotes_insumos" if tipo == "insumo" else "lotes_productos", lote.numero_lote,
                     {"cantidad": str(cant), "motivo": motivo})
            db.session.commit()
            flash(f"Lote {lote.numero_lote} dado de baja ({_n(cant)}). Queda en el historial.", "ok")
        except SQLAlchemyError as e:
            _error_bd(e)
    return redirect(url_for("almacen.existencias", alerta="atencion"))


# ------------------------------------------------------------ ALM-03 Despacho FEFO
@almacen_bp.route("/despacho", methods=["GET", "POST"])
def despacho():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        id_item = request.form.get("id_item", type=int)
        cantidad = _dec(request.form.get("cantidad", "0")) or Decimal(0)
        documento = request.form.get("documento", "").strip().upper()
        plan, falta = _plan_fefo(tipo, id_item, cantidad) if tipo in ("insumo", "producto") else ([], cantidad)
        if cantidad <= 0 or not plan:
            flash("Indica un ítem y una cantidad válida.", "error")
        elif falta > 0:
            flash("No hay stock utilizable suficiente; el despacho no se registró.", "error")
        elif not documento:
            flash("Escribe el documento de referencia (orden de producción o pedido).", "error")
        else:
            op = OrdenProduccion.query.filter_by(numero_orden=documento).first() if tipo == "insumo" else None
            try:
                for p in plan:
                    if op:
                        # RN-12: el consumo guarda el lote usado; el trigger descuenta y registra el movimiento
                        db.session.add(ConsumoInsumoProduccion(id_orden_produccion=op.id_orden_produccion,
                                                               id_insumo=id_item, id_lote_insumo=p["id_lote"],
                                                               cantidad_consumida=p["_toma"]))
                    else:
                        _registrar_salida(p["lote"], tipo, p["_toma"], documento)
                _auditar("DESPACHO_FEFO", "movimientos_inventario", documento,
                         {"lotes": [[p["numero_lote"], str(p["_toma"])] for p in plan]})
                db.session.commit()
                usados = ", ".join(f"{p['numero_lote']} ({p['tomar']})" for p in plan)
                destino = f" (consumo registrado en la orden {op.numero_orden})" if op else ""
                flash(f"Despacho registrado para {documento}{destino}. Lotes usados: {usados}.", "ok")
                return redirect(url_for("almacen.despacho"))
            except SQLAlchemyError as e:
                _error_bd(e)
        return redirect(url_for("almacen.despacho", tipo=tipo, id_item=id_item, cantidad=cantidad,
                                documento=documento))

    tipo = request.args.get("tipo", "insumo")
    if tipo not in ("insumo", "producto"):
        tipo = "insumo"
    id_item = request.args.get("id_item", type=int)
    cantidad = _dec(request.args.get("cantidad")) if request.args.get("cantidad") else None
    plan, falta, disponible = [], 0, None
    if id_item and cantidad:
        plan, falta = _plan_fefo(tipo, id_item, cantidad)
        disponible = _n(sum((l.cantidad_actual for l in _lotes_fefo(tipo, id_item)), Decimal(0)))
        falta = _n(falta)
    excluidos = []
    if id_item:  # lotes que NO se pueden usar y por qué
        M = _modelo(tipo)
        campo = M.id_insumo if tipo == "insumo" else M.id_producto
        fila = _fila_insumo if tipo == "insumo" else _fila_producto
        for l in M.query.filter(campo == id_item, M.cantidad_actual > 0).all():
            if not _usable(l):
                excluidos.append(dict(fila(l), razon="vencido" if _alerta(l) == "vencido" else l.estado))
    if tipo == "insumo":
        items = [dict(id=i.id_insumo, nombre=i.nombre, unidad=i.unidad.abreviatura if i.unidad else "")
                 for i in Insumo.query.filter_by(activo=True).order_by(Insumo.nombre)]
    else:
        items = [dict(id=p.id_producto, nombre=p.nombre, unidad=p.unidad.abreviatura if p.unidad else "unid")
                 for p in Producto.query.filter_by(activo=True).order_by(Producto.nombre)]
    movs = (db.session.query(MovimientoInventario, Usuario)
            .outerjoin(Usuario, Usuario.id_usuario == MovimientoInventario.id_usuario)
            .filter(MovimientoInventario.cantidad < 0)
            .order_by(MovimientoInventario.fecha_movimiento.desc(), MovimientoInventario.id_movimiento.desc())
            .limit(8).all())
    nombres = {("insumo", i.id_insumo): i.nombre for i in Insumo.query.all()}
    nombres.update({("producto", p.id_producto): p.nombre for p in Producto.query.all()})
    lotes = {("insumo", l.id_lote_insumo): l.numero_lote for l in LoteInsumo.query.all()}
    lotes.update({("producto", l.id_lote_producto): l.numero_lote for l in LoteProducto.query.all()})
    salidas = [dict(fecha=m.fecha_movimiento.strftime("%Y-%m-%d %H:%M") if m.fecha_movimiento else None,
                    item=nombres.get((m.tipo_item, m.id_item), "—"), numero_lote=lotes.get((m.tipo_item, m.id_lote), "—"),
                    cantidad=_n(m.cantidad), documento_ref=m.documento_ref,
                    responsable=u.nombre_completo if u else "Sistema (trigger)") for m, u in movs]
    return _render("almacenero/despacho.html", tipo=tipo, items=items, id_item=id_item,
                   cantidad=_n(cantidad) if cantidad else None,
                   documento=request.args.get("documento", ""), id_solicitud=request.args.get("id_solicitud", ""),
                   plan=plan, falta=falta, disponible=disponible, excluidos=excluidos,
                   pendientes=_ops_pendientes(), salidas=salidas)


# ------------------------------------------------------------ ALM-04 Inventario físico y ajustes
@almacen_bp.route("/inventario", methods=["GET", "POST"])
def inventario():
    tipo = request.values.get("tipo", "insumo")
    if tipo not in ("insumo", "producto"):
        tipo = "insumo"
    M, fila = (LoteInsumo, _fila_insumo) if tipo == "insumo" else (LoteProducto, _fila_producto)
    objetos = {(l.id_lote_insumo if tipo == "insumo" else l.id_lote_producto): l
               for l in M.query.filter(M.estado.notin_(("agotado", "baja"))).all()}
    lotes = sorted((fila(l) for l in objetos.values()), key=lambda f: (f["item"], f["numero_lote"]))
    if request.method == "POST":
        ajustes, errores = [], []
        for f in lotes:
            valor = request.form.get(f"contado_{f['id_lote']}", "").strip()
            if valor == "":
                continue
            contado = _dec(valor)
            if contado is None or contado < 0:
                errores.append(f"{f['numero_lote']}: la cantidad contada no es válida.")
                continue
            lote = objetos[f["id_lote"]]
            dif = contado - lote.cantidad_actual
            just = request.form.get(f"just_{f['id_lote']}", "").strip()
            if dif and not just:  # RN-09
                errores.append(f"{f['numero_lote']}: hay una diferencia de {_n(dif):+}; escribe la justificación.")
            ajustes.append((f, lote, contado, dif, just))
        if not ajustes and not errores:
            errores.append("Ingresa la cantidad contada de al menos un lote.")
        if errores:
            for e in errores:
                flash(e, "error")
            return _render("almacenero/inventario.html", tipo=tipo, lotes=lotes, form=request.form,
                           historial=_historial())
        try:
            inv = InventarioFisico(id_usuario=_uid(), fecha_inicio=datetime.now(), fecha_fin=datetime.now(),
                                   estado="cerrado", justificacion=f"Conteo de {tipo}s")
            db.session.add(inv)
            db.session.flush()
            n_ajustes = 0
            for f, lote, contado, dif, just in ajustes:
                db.session.add(InventarioFisicoDetalle(id_inventario=inv.id_inventario, tipo_item=tipo,
                                                       id_item=f["id_item"], id_lote=f["id_lote"],
                                                       cantidad_sistema=lote.cantidad_actual,
                                                       cantidad_contada=contado, justificacion=just or None))
                if dif:
                    n_ajustes += 1
                    lote.cantidad_actual = contado
                    if contado == 0:
                        lote.estado = "agotado"
                    db.session.add(MovimientoInventario(tipo_item=tipo, id_item=f["id_item"], id_lote=f["id_lote"],
                                                        tipo_movimiento="ajuste", cantidad=dif,
                                                        documento_ref=f"INV-{inv.id_inventario:03d}",
                                                        id_usuario=_uid(), observacion=just))
            _auditar("INVENTARIO_FISICO", "inventarios_fisicos", inv.id_inventario,
                     {"lotes": len(ajustes), "ajustes": n_ajustes})
            db.session.commit()
        except SQLAlchemyError as e:
            _error_bd(e)
            return redirect(url_for("almacen.inventario", tipo=tipo))
        flash(f"Inventario físico registrado: {len(ajustes)} lotes contados, {n_ajustes} ajustes aplicados.", "ok")
        return redirect(url_for("almacen.inventario", tipo=tipo))
    return _render("almacenero/inventario.html", tipo=tipo, lotes=lotes, form={}, historial=_historial())


def _historial(limite=10):
    nombres = {("insumo", i.id_insumo): i.nombre for i in Insumo.query.all()}
    nombres.update({("producto", p.id_producto): p.nombre for p in Producto.query.all()})
    lotes = {("insumo", l.id_lote_insumo): l.numero_lote for l in LoteInsumo.query.all()}
    lotes.update({("producto", l.id_lote_producto): l.numero_lote for l in LoteProducto.query.all()})
    filas = []
    q = (db.session.query(InventarioFisico, Usuario)
         .outerjoin(Usuario, Usuario.id_usuario == InventarioFisico.id_usuario)
         .order_by(InventarioFisico.id_inventario.desc()).limit(limite))
    for inv, u in q.all():
        det = inv.detalle
        filas.append(dict(
            id_inventario=inv.id_inventario, fecha=_fecha(inv.fecha_inicio),
            tipo=det[0].tipo_item if det else "insumo", lotes_contados=len(det),
            responsable=u.nombre_completo if u else "—",
            ajustes=[dict(item=nombres.get((x.tipo_item, x.id_item), "—"),
                          numero_lote=lotes.get((x.tipo_item, x.id_lote), "—"),
                          cantidad_sistema=_n(x.cantidad_sistema), cantidad_contada=_n(x.cantidad_contada),
                          diferencia=_n(x.cantidad_contada - x.cantidad_sistema), justificacion=x.justificacion)
                     for x in det if x.cantidad_contada != x.cantidad_sistema]))
    return filas
