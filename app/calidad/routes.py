"""Rutas del rol CALIDAD conectadas a PostgreSQL (Flask-SQLAlchemy).

Usa los modelos de app/models.py sin modificarlos. Las vistas devuelven a las
plantillas las mismas claves que antes devolvían los datos simulados.

- Trazabilidad: lee las vistas v_trazabilidad_atras / v_trazabilidad_adelante de db.sql.
- Reclamos: tabla reclamos_cliente (compartida con el rol vendedor, que importa
  filas_reclamos, reclamo_por_id, actualizar_reclamo, traza_atras y traza_adelante).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import calidad_bp
from ..models import (Cliente, ControlCalidad, Factura, Insumo, LoteInsumo, LoteProducto,
                      Producto, ReclamoCliente, Usuario, db)

MENU = [
    ("Panel", "calidad.panel", "Resumen del día"),
    ("Control de calidad", "calidad.controles", "Registro por lote"),
    ("Aprobar o rechazar", "calidad.decision", "Decisión sobre el lote"),
    ("Rastreo hacia atrás", "calidad.rastreo_atras", "Lote a proveedores"),
    ("Rastreo hacia adelante", "calidad.rastreo_adelante", "Lote a clientes"),
    ("Atender reclamos", "calidad.reclamos", "Apoyo con trazabilidad"),
]


def _render(plantilla, **ctx):
    # Se pasa el menú aquí para no depender del context_processor del __init__
    return render_template(plantilla, menu=MENU, rol="calidad", **ctx)


# ====================================================================
# UTILIDADES
# ====================================================================
def _n(x):
    """Cantidad sin ceros sobrantes: Decimal('110.000') -> 110."""
    if x is None:
        return 0
    x = Decimal(x)
    return int(x) if x == x.to_integral_value() else float(x)


def _fecha(x):
    """date/datetime -> 'YYYY-MM-DD' (formato que esperan las plantillas)."""
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


def _vistas_lotes(lotes):
    ids = {l.id_producto for l in lotes}
    nombres = ({p.id_producto: p.nombre for p in Producto.query.filter(Producto.id_producto.in_(ids))}
               if ids else {})
    return [dict(id_lote_producto=l.id_lote_producto, numero_lote=l.numero_lote,
                 producto=nombres.get(l.id_producto), fecha_produccion=_fecha(l.fecha_produccion),
                 fecha_vencimiento=_fecha(l.fecha_vencimiento), cantidad_actual=_n(l.cantidad_actual),
                 estado=l.estado)
            for l in lotes]


def _vistas_controles(controles):
    ids_p = {c.id_lote_producto for c in controles if c.id_lote_producto}
    ids_i = {c.id_lote_insumo for c in controles if c.id_lote_insumo}
    ids_u = {c.id_usuario_responsable for c in controles if c.id_usuario_responsable}
    lotes_p = ({l.id_lote_producto: l.numero_lote
                for l in LoteProducto.query.filter(LoteProducto.id_lote_producto.in_(ids_p))} if ids_p else {})
    lotes_i = ({l.id_lote_insumo: l.numero_lote
                for l in LoteInsumo.query.filter(LoteInsumo.id_lote_insumo.in_(ids_i))} if ids_i else {})
    usuarios = ({u.id_usuario: u.nombre_completo
                 for u in Usuario.query.filter(Usuario.id_usuario.in_(ids_u))} if ids_u else {})
    return [dict(fecha=_fecha(c.fecha_control),
                 lote=lotes_p.get(c.id_lote_producto) if c.id_lote_producto else lotes_i.get(c.id_lote_insumo),
                 tipo_control=c.tipo_control,
                 valor_medido=float(c.valor_medido) if c.valor_medido is not None else None,
                 unidad_medida=c.unidad_medida, resultado=c.resultado,
                 responsable=usuarios.get(c.id_usuario_responsable))
            for c in controles]


# ====================================================================
# Funciones reutilizables (también las usa el rol vendedor)
# ====================================================================
def _filas_vista(vista, columna_orden, numero):
    if not numero:
        return []
    filas = db.session.execute(
        text(f"SELECT * FROM {vista} WHERE lote_producto = :n ORDER BY {columna_orden}"), {"n": numero})
    return [dict(f._mapping) for f in filas]


def traza_atras(numero):
    """Insumos y proveedores usados en un lote de producto (v_trazabilidad_atras)."""
    filas = _filas_vista("v_trazabilidad_atras", "fecha_consumo, insumo", numero)
    for f in filas:
        f["cantidad_consumida"] = _n(f["cantidad_consumida"])
        f["fecha_consumo"] = _fecha(f["fecha_consumo"])
    return filas


def traza_adelante(numero):
    """Clientes y facturas a los que llegó un lote de producto (v_trazabilidad_adelante)."""
    filas = _filas_vista("v_trazabilidad_adelante", "fecha_emision, cliente", numero)
    for f in filas:
        f["cantidad"] = _n(f["cantidad"])
        f["fecha_emision"] = _fecha(f["fecha_emision"])
    return filas


def _query_reclamos():
    return (db.session.query(ReclamoCliente, Cliente, Factura, LoteProducto, Producto)
            .join(Cliente, Cliente.id_cliente == ReclamoCliente.id_cliente)
            .outerjoin(Factura, Factura.id_factura == ReclamoCliente.id_factura)
            .outerjoin(LoteProducto, LoteProducto.id_lote_producto == ReclamoCliente.id_lote_producto)
            .outerjoin(Producto, Producto.id_producto == LoteProducto.id_producto))


def _vista_reclamo(fila):
    r, c, f, l, p = fila
    return dict(id_reclamo=r.id_reclamo, numero_reclamo=r.numero_reclamo, cliente=c.razon_social,
                telefono=c.telefono, email=c.email, numero_factura=f.numero_factura if f else None,
                numero_lote=l.numero_lote if l else None, producto=p.nombre if p else None,
                estado=r.estado, fecha=_fecha(r.fecha_reclamo), descripcion=r.descripcion,
                resolucion=r.resolucion)


def filas_reclamos(estado=""):
    q = _query_reclamos()
    if estado:
        q = q.filter(ReclamoCliente.estado == estado)
    q = q.order_by(ReclamoCliente.fecha_reclamo.desc(), ReclamoCliente.id_reclamo.desc())
    return [_vista_reclamo(f) for f in q.all()]


def reclamo_por_id(id):
    fila = _query_reclamos().filter(ReclamoCliente.id_reclamo == id).first()
    return _vista_reclamo(fila) if fila else None


def actualizar_reclamo(id, estado, resolucion):
    """Actualiza estado y resolución. Devuelve True si se guardó, False si falló la BD."""
    r = ReclamoCliente.query.get_or_404(id)
    r.estado = estado
    r.resolucion = resolucion or None
    r.id_usuario_atendio = _uid()
    r.fecha_resolucion = datetime.now() if estado in ("resuelto", "cerrado") else None
    try:
        db.session.commit()
        return True
    except SQLAlchemyError:
        _error_bd("No se pudo actualizar el reclamo. Intenta de nuevo.")
        return False


# ====================================================================
# RUTAS
# ====================================================================
@calidad_bp.route("/")
def panel():
    hoy = datetime.combine(date.today(), datetime.min.time())
    kpis = dict(
        controles_hoy=ControlCalidad.query.filter(ControlCalidad.fecha_control >= hoy).count(),
        lotes_pendientes=LoteProducto.query.filter_by(estado="cuarentena").count(),
        rechazos_30d=ControlCalidad.query.filter(
            ControlCalidad.resultado == "rechazado",
            ControlCalidad.fecha_control >= datetime.now() - timedelta(days=30)).count(),
        lotes_por_vencer=LoteProducto.query.filter(
            LoteProducto.estado == "disponible", LoteProducto.cantidad_actual > 0,
            LoteProducto.fecha_vencimiento <= date.today() + timedelta(days=30)).count(),
        reclamos_pendientes=ReclamoCliente.query.filter(
            ReclamoCliente.estado.in_(["abierto", "en_revision"])).count(),
    )
    pendientes = _vistas_lotes(LoteProducto.query.filter_by(estado="cuarentena")
                               .order_by(LoteProducto.id_lote_producto).all())
    ultimos = _vistas_controles(ControlCalidad.query
                                .order_by(ControlCalidad.fecha_control.desc(), ControlCalidad.id_control.desc())
                                .limit(8).all())
    return _render("calidad/panel.html", kpis=kpis, pendientes=pendientes, ultimos=ultimos)


@calidad_bp.route("/controles", methods=["GET", "POST"])
def controles():
    if request.method == "POST":
        tipo, _, id_lote = request.form.get("lote", ":").partition(":")
        modelo = {"producto": LoteProducto, "insumo": LoteInsumo}.get(tipo)
        lote = db.session.get(modelo, int(id_lote)) if modelo and id_lote.isdigit() else None
        tipo_control = request.form.get("tipo_control", "").strip()
        resultado = request.form.get("resultado")
        if not lote:
            flash("Elige el lote que vas a controlar.", "error")
            return redirect(url_for("calidad.controles"))
        if not tipo_control or not resultado:
            flash("Indica el tipo de control y el resultado.", "error")
            return redirect(url_for("calidad.controles"))
        try:
            valor = Decimal(request.form.get("valor_medido")) if request.form.get("valor_medido") else None
        except InvalidOperation:
            flash("El valor medido debe ser un número.", "error")
            return redirect(url_for("calidad.controles"))
        try:
            db.session.add(ControlCalidad(
                id_lote_producto=lote.id_lote_producto if tipo == "producto" else None,
                id_lote_insumo=lote.id_lote_insumo if tipo == "insumo" else None,
                tipo_control=tipo_control, resultado=resultado, valor_medido=valor,
                unidad_medida=request.form.get("unidad_medida") or None,
                observacion=request.form.get("observacion") or None,
                id_usuario_responsable=_uid(), fecha_control=datetime.now()))
            db.session.commit()
        except SQLAlchemyError:
            _error_bd("No se pudo registrar el control.")
            return redirect(url_for("calidad.controles"))
        flash("Control registrado.", "ok")
        return redirect(url_for("calidad.controles"))

    excluidos = ["rechazado", "agotado"]
    lotes_p = (LoteProducto.query.filter(LoteProducto.estado.notin_(excluidos))
               .order_by(LoteProducto.id_lote_producto.desc()).all())
    nombres_p = {p.id_producto: p.nombre for p in Producto.query.all()}
    lotes = [dict(tipo="producto", id_lote=l.id_lote_producto, numero_lote=l.numero_lote,
                  item=nombres_p.get(l.id_producto)) for l in lotes_p]
    lotes_i = (LoteInsumo.query.filter(LoteInsumo.estado.notin_(excluidos))
               .order_by(LoteInsumo.id_lote_insumo.desc()).all())
    nombres_i = {i.id_insumo: i.nombre for i in Insumo.query.all()}
    lotes += [dict(tipo="insumo", id_lote=l.id_lote_insumo, numero_lote=l.numero_lote,
                   item=nombres_i.get(l.id_insumo)) for l in lotes_i]
    historial = _vistas_controles(ControlCalidad.query
                                  .order_by(ControlCalidad.fecha_control.desc(), ControlCalidad.id_control.desc())
                                  .limit(100).all())
    return _render("calidad/controles.html", lotes=lotes, historial=historial)


@calidad_bp.route("/decision", methods=["GET", "POST"])
def decision():
    if request.method == "POST":
        accion = request.form.get("accion")
        id_lote = request.form.get("id_lote", type=int)
        lote = db.session.get(LoteProducto, id_lote) if id_lote else None
        if accion not in ("aprobar", "rechazar") or not lote:
            abort(400)
        lote.estado = "disponible" if accion == "aprobar" else "rechazado"
        try:
            db.session.commit()
        except SQLAlchemyError:
            _error_bd("No se pudo guardar la decisión.")
            return redirect(url_for("calidad.decision"))
        flash(f"Lote {lote.numero_lote} {'aprobado' if accion == 'aprobar' else 'rechazado'}.", "ok")
        return redirect(url_for("calidad.decision"))

    estado = request.args.get("estado", "cuarentena")
    lotes = LoteProducto.query.filter_by(estado=estado).order_by(LoteProducto.id_lote_producto).all()
    ultimos = {}
    if lotes:
        for c in (ControlCalidad.query
                  .filter(ControlCalidad.id_lote_producto.in_([l.id_lote_producto for l in lotes]))
                  .order_by(ControlCalidad.fecha_control.desc(), ControlCalidad.id_control.desc())):
            ultimos.setdefault(c.id_lote_producto, c.resultado)
    filas = [{**v, "ultimo_control": ultimos.get(v["id_lote_producto"])} for v in _vistas_lotes(lotes)]
    return _render("calidad/decision.html", estado=estado, lotes=filas)


def _rastreo(sentido):
    lote = request.args.get("lote", "").strip()
    funcion = traza_atras if sentido == "atras" else traza_adelante
    buscables = [dict(numero_lote=v["numero_lote"], producto=v["producto"])
                 for v in _vistas_lotes(LoteProducto.query.order_by(LoteProducto.id_lote_producto.desc()).all())]
    return _render("calidad/rastreo.html", sentido=sentido, lote=lote,
                   filas=funcion(lote) if lote else None, lotes=buscables)


@calidad_bp.route("/rastreo-atras")
def rastreo_atras():
    return _rastreo("atras")


@calidad_bp.route("/rastreo-adelante")
def rastreo_adelante():
    return _rastreo("adelante")


@calidad_bp.route("/reclamos")
def reclamos():
    estado = request.args.get("estado", "")
    return _render("calidad/reclamos.html", estado=estado, reclamos=filas_reclamos(estado))


@calidad_bp.route("/reclamos/<int:id>")
def reclamo_detalle(id):
    r = reclamo_por_id(id)
    if not r:
        abort(404)
    return _render("calidad/reclamo_detalle.html", r=r,
                   atras=traza_atras(r["numero_lote"]), adelante=traza_adelante(r["numero_lote"]))


@calidad_bp.route("/reclamos/<int:id>/atender", methods=["POST"])
def atender_reclamo(id):
    if actualizar_reclamo(id, request.form.get("estado", "en_revision"), request.form.get("resolucion")):
        flash("Reclamo actualizado.", "ok")
    return redirect(url_for("calidad.reclamo_detalle", id=id))