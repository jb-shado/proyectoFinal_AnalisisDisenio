"""Rutas del rol ALMACENERO con datos simulados (sin base de datos).

Pantallas (diagrama de navegación del almacenero y hoja pantallas_ERP_por_rol):
  ALM-00 Panel de inicio .............. RF-10
  ALM-01 Recepción de insumos ......... RF-06, RF-11  (RN-05, RN-06)
  ALM-02 Existencias por lote ......... RF-08, RF-10
  ALM-03 Despacho FEFO ................ RF-09        (RN-07, RN-08)
  ALM-04 Inventario físico y ajustes .. RF-12        (RN-09)

Cuando conecten PostgreSQL, reemplacen cada bloque de DATOS SIMULADOS por la
consulta indicada en el comentario; las plantillas esperan exactamente estas claves.
"""
import os
from datetime import date, datetime, timedelta

from flask import flash, redirect, render_template, request, url_for

from . import almacen_bp

MENU = [
    ("Panel", "almacen.panel", "Resumen del día"),
    ("Recepción de insumos", "almacen.recepcion", "Lote y vencimiento"),
    ("Existencias por lote", "almacen.existencias", "Alertas de vencimiento"),
    ("Despacho FEFO", "almacen.despacho", "Primero en vencer"),
    ("Inventario físico", "almacen.inventario", "Ajustes con justificación"),
]
RESPONSABLE = "Carlos Quispe"   # usuario con rol almacenero (cuando exista el login interno)
DIAS_ALERTA = 30               # misma ventana que la vista v_productos_por_vencer


@almacen_bp.record_once
def _clave_sesion(state):
    # flash() necesita SECRET_KEY; mientras config.py la tenga comentada usamos una de desarrollo
    if not state.app.secret_key:
        state.app.secret_key = os.environ.get("SECRET_KEY", "clave-de-desarrollo")


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="almacenero", **ctx)


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


def _ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ====================================================================
# DATOS SIMULADOS
# ====================================================================
UNIDADES = {1: "kg", 2: "L", 3: "unid"}  # tabla unidades_medida

INSUMOS = [  # tabla insumos
    dict(id_insumo=1, codigo="INS001", nombre="Leche cruda", id_unidad=2, stock_minimo=300, perecedero=True),
    dict(id_insumo=2, codigo="INS002", nombre="Harina de trigo", id_unidad=1, stock_minimo=200, perecedero=True),
    dict(id_insumo=3, codigo="INS003", nombre="Azúcar refinada", id_unidad=1, stock_minimo=150, perecedero=False),
    dict(id_insumo=4, codigo="INS004", nombre="Mantequilla", id_unidad=1, stock_minimo=40, perecedero=True),
    dict(id_insumo=5, codigo="INS005", nombre="Fruta fresca (fresa)", id_unidad=1, stock_minimo=60, perecedero=True),
    dict(id_insumo=6, codigo="INS006", nombre="Sal fina", id_unidad=1, stock_minimo=20, perecedero=False),
    dict(id_insumo=7, codigo="INS007", nombre="Envase plástico 1L", id_unidad=3, stock_minimo=500, perecedero=False),
]

PROVEEDORES = {1: "Lácteos del Altiplano SRL", 2: "Harinas Bolivianas SA", 3: "Azúcares del Norte SRL",
               4: "Frutas y Conservas del Valle", 5: "Empaques Plásticos Andinos"}

LOTES_INSUMO = [  # tabla lotes_insumos
    dict(id_lote=1, id_insumo=1, numero_lote="LI-2026-041", id_proveedor=1, fecha_recepcion=_d(-3),
         fecha_vencimiento=_d(4), cantidad_inicial=400, cantidad_actual=180, estado="disponible"),
    dict(id_lote=2, id_insumo=1, numero_lote="LI-2026-047", id_proveedor=1, fecha_recepcion=_d(-1),
         fecha_vencimiento=_d(6), cantidad_inicial=300, cantidad_actual=300, estado="disponible"),
    dict(id_lote=3, id_insumo=2, numero_lote="LI-2026-042", id_proveedor=2, fecha_recepcion=_d(-20),
         fecha_vencimiento=_d(160), cantidad_inicial=500, cantidad_actual=140, estado="disponible"),
    dict(id_lote=4, id_insumo=3, numero_lote="LI-2026-043", id_proveedor=3, fecha_recepcion=_d(-15),
         fecha_vencimiento=_d(400), cantidad_inicial=300, cantidad_actual=210, estado="disponible"),
    dict(id_lote=5, id_insumo=4, numero_lote="LI-2026-044", id_proveedor=1, fecha_recepcion=_d(-10),
         fecha_vencimiento=_d(18), cantidad_inicial=60, cantidad_actual=35, estado="disponible"),
    dict(id_lote=6, id_insumo=5, numero_lote="LI-2026-048", id_proveedor=4, fecha_recepcion=_d(-6),
         fecha_vencimiento=_d(-1), cantidad_inicial=80, cantidad_actual=12, estado="disponible"),
    dict(id_lote=7, id_insumo=5, numero_lote="LI-2026-049", id_proveedor=4, fecha_recepcion=_d(-2),
         fecha_vencimiento=_d(5), cantidad_inicial=90, cantidad_actual=90, estado="disponible"),
    dict(id_lote=8, id_insumo=6, numero_lote="LI-2026-046", id_proveedor=3, fecha_recepcion=_d(-40),
         fecha_vencimiento=_d(700), cantidad_inicial=50, cantidad_actual=44, estado="disponible"),
    dict(id_lote=9, id_insumo=7, numero_lote="LI-2026-050", id_proveedor=5, fecha_recepcion=_d(-12),
         fecha_vencimiento=None, cantidad_inicial=2000, cantidad_actual=1250, estado="disponible"),
    dict(id_lote=10, id_insumo=2, numero_lote="LI-2026-031", id_proveedor=2, fecha_recepcion=_d(-90),
         fecha_vencimiento=_d(70), cantidad_inicial=400, cantidad_actual=0, estado="agotado"),
]

PRODUCTOS = {1: "Yogur natural 1L", 2: "Queso fresco 500g", 3: "Pan de molde", 4: "Galletas de avena",
             5: "Mermelada de fresa", 6: "Jugo de naranja 1L", 7: "Papas fritas 200g"}

LOTES_PRODUCTO = [  # tabla lotes_productos (estado lo decide calidad: cuarentena / disponible / rechazado)
    dict(id_lote=1, id_producto=1, numero_lote="LP-2026-096", fecha_produccion=_d(-16),
         fecha_vencimiento=_d(12), cantidad_inicial=120, cantidad_actual=70, estado="disponible"),
    dict(id_lote=2, id_producto=1, numero_lote="LP-2026-097", fecha_produccion=_d(-4),
         fecha_vencimiento=_d(24), cantidad_inicial=60, cantidad_actual=40, estado="disponible"),
    dict(id_lote=3, id_producto=1, numero_lote="LP-2026-101", fecha_produccion=_d(-2),
         fecha_vencimiento=_d(28), cantidad_inicial=100, cantidad_actual=100, estado="cuarentena"),
    dict(id_lote=4, id_producto=2, numero_lote="LP-2026-094", fecha_produccion=_d(-11),
         fecha_vencimiento=_d(9), cantidad_inicial=80, cantidad_actual=45, estado="disponible"),
    dict(id_lote=5, id_producto=3, numero_lote="LP-2026-093", fecha_produccion=_d(-3),
         fecha_vencimiento=_d(4), cantidad_inicial=90, cantidad_actual=60, estado="disponible"),
    dict(id_lote=6, id_producto=4, numero_lote="LP-2026-098", fecha_produccion=_d(-10),
         fecha_vencimiento=_d(50), cantidad_inicial=150, cantidad_actual=110, estado="disponible"),
    dict(id_lote=7, id_producto=5, numero_lote="LP-2026-099", fecha_produccion=_d(-9),
         fecha_vencimiento=_d(170), cantidad_inicial=80, cantidad_actual=55, estado="disponible"),
    dict(id_lote=8, id_producto=6, numero_lote="LP-2026-100", fecha_produccion=_d(-8),
         fecha_vencimiento=_d(7), cantidad_inicial=120, cantidad_actual=95, estado="disponible"),
    dict(id_lote=9, id_producto=6, numero_lote="LP-2026-088", fecha_produccion=_d(-40),
         fecha_vencimiento=_d(-2), cantidad_inicial=100, cantidad_actual=8, estado="disponible"),
    dict(id_lote=10, id_producto=7, numero_lote="LP-2026-090", fecha_produccion=_d(-30),
         fecha_vencimiento=_d(60), cantidad_inicial=60, cantidad_actual=48, estado="rechazado"),
]

ORDENES_COMPRA = [  # ordenes_compra (estado 'emitida') + orden_compra_detalle
    dict(id_orden=1, numero_orden="OC-2026-021", id_proveedor=1, fecha_entrega_esperada=_d(0),
         lineas=[dict(id_insumo=1, cantidad=400, recibido=0), dict(id_insumo=4, cantidad=30, recibido=0)]),
    dict(id_orden=2, numero_orden="OC-2026-022", id_proveedor=2, fecha_entrega_esperada=_d(1),
         lineas=[dict(id_insumo=2, cantidad=300, recibido=0)]),
    dict(id_orden=3, numero_orden="OC-2026-023", id_proveedor=4, fecha_entrega_esperada=_d(2),
         lineas=[dict(id_insumo=5, cantidad=100, recibido=40)]),
]

RECEPCIONES = [  # recepciones_compra (la más reciente primero)
    dict(fecha=_d(-1), numero_orden="OC-2026-019", insumo="Leche cruda", numero_lote="LI-2026-047",
         fecha_vencimiento=_d(6), cantidad=300, unidad="L", proveedor="Lácteos del Altiplano SRL", responsable=RESPONSABLE),
    dict(fecha=_d(-2), numero_orden="OC-2026-023", insumo="Fruta fresca (fresa)", numero_lote="LI-2026-049",
         fecha_vencimiento=_d(5), cantidad=40, unidad="kg", proveedor="Frutas y Conservas del Valle", responsable=RESPONSABLE),
]

# Pedidos internos que esperan salida del almacén (órdenes de producción y pedidos confirmados)
SOLICITUDES = [
    dict(id_solicitud=1, documento="OP-2026-031", destino="Producción · Yogur natural 1L",
         tipo="insumo", id_item=1, cantidad=250, atendida=False),
    dict(id_solicitud=2, documento="OP-2026-032", destino="Producción · Mermelada de fresa",
         tipo="insumo", id_item=5, cantidad=60, atendida=False),
    dict(id_solicitud=3, documento="PED-2026-003", destino="Venta · Distribuidora El Sol",
         tipo="producto", id_item=1, cantidad=90, atendida=False),
]

MOVIMIENTOS = [  # movimientos_inventario (el más reciente primero)
    dict(fecha=_d(-1) + " 10:20", tipo_movimiento="recepcion", item="Leche cruda", numero_lote="LI-2026-047",
         cantidad=300, documento_ref="OC-2026-019", responsable=RESPONSABLE),
    dict(fecha=_d(-1) + " 15:05", tipo_movimiento="despacho", item="Leche cruda", numero_lote="LI-2026-041",
         cantidad=-220, documento_ref="OP-2026-030", responsable=RESPONSABLE),
]

INVENTARIOS = [  # inventarios_fisicos + inventario_fisico_detalle
    dict(id_inventario=1, fecha=_d(-7), tipo="insumo", lotes_contados=9, ajustes=[
        dict(item="Azúcar refinada", numero_lote="LI-2026-043", cantidad_sistema=215, cantidad_contada=210,
             diferencia=-5, justificacion="Bolsa rota durante el traslado")],
         responsable=RESPONSABLE, estado="cerrado"),
]


# ====================================================================
# Funciones de apoyo (lo que harían las vistas y JOIN de la BD)
# ====================================================================
def _insumo(id):
    return next((i for i in INSUMOS if i["id_insumo"] == id), None)


def _dias(fecha):
    return (date.fromisoformat(fecha) - date.today()).days if fecha else None


def _alerta(lote):
    """Alerta de vencimiento (extend de 'Consultar existencias por lote')."""
    if lote["estado"] in ("agotado", "baja"):
        return None
    d = _dias(lote["fecha_vencimiento"])
    if d is None:
        return "sin_vencimiento"
    if d < 0:
        return "vencido"
    if d <= 7:
        return "critico"
    if d <= DIAS_ALERTA:
        return "por_vencer"
    return "ok"


def _fila(lote, tipo):
    """Une el lote con su ítem y calcula días y alerta."""
    if tipo == "insumo":
        ins = _insumo(lote["id_insumo"])
        item, codigo, unidad = ins["nombre"], ins["codigo"], UNIDADES[ins["id_unidad"]]
        id_item = ins["id_insumo"]
    else:
        item, codigo, unidad = PRODUCTOS[lote["id_producto"]], f"PROD{lote['id_producto']:03d}", "unid"
        id_item = lote["id_producto"]
    return {**lote, "tipo": tipo, "item": item, "codigo": codigo, "unidad": unidad, "id_item": id_item,
            "dias": _dias(lote["fecha_vencimiento"]), "alerta": _alerta(lote),
            "proveedor": PROVEEDORES.get(lote.get("id_proveedor"))}


def _todas_las_filas():
    return ([_fila(l, "insumo") for l in LOTES_INSUMO] +
            [_fila(l, "producto") for l in LOTES_PRODUCTO])


def _lista_lotes(tipo):
    return LOTES_INSUMO if tipo == "insumo" else LOTES_PRODUCTO


def _stock_insumos():
    """Equivale a la vista v_stock_insumos (solo lotes 'disponible' y no vencidos)."""
    filas = []
    for i in INSUMOS:
        stock = sum(l["cantidad_actual"] for l in LOTES_INSUMO
                    if l["id_insumo"] == i["id_insumo"] and l["estado"] == "disponible"
                    and _alerta(l) != "vencido")
        filas.append(dict(codigo=i["codigo"], nombre=i["nombre"], unidad=UNIDADES[i["id_unidad"]],
                          stock_minimo=i["stock_minimo"], stock_actual=stock,
                          estado_stock="reponer" if stock <= i["stock_minimo"] else "ok"))
    return filas


def _lotes_fefo(tipo, id_item):
    """RN-07: lotes utilizables ordenados por vencimiento (el que vence primero sale primero).
    Excluye vencidos, agotados, en cuarentena, rechazados o dados de baja."""
    campo = "id_insumo" if tipo == "insumo" else "id_producto"
    lotes = [l for l in _lista_lotes(tipo)
             if l[campo] == id_item and l["estado"] == "disponible" and l["cantidad_actual"] > 0
             and _alerta(l) != "vencido"]
    return sorted(lotes, key=lambda l: l["fecha_vencimiento"] or "9999-12-31")


def _plan_fefo(tipo, id_item, cantidad):
    """Reparte la cantidad pedida entre los lotes en orden FEFO."""
    plan, falta = [], cantidad
    for l in _lotes_fefo(tipo, id_item):
        if falta <= 0:
            break
        toma = min(falta, l["cantidad_actual"])
        plan.append(dict(_fila(l, tipo), tomar=toma, queda=l["cantidad_actual"] - toma))
        falta -= toma
    return plan, falta


def _registrar_salida(lote, tipo, cantidad, documento, motivo="despacho"):
    """Descuenta el lote. RN-08: si llega a cero pasa a 'agotado' (en la BD lo hace el trigger)."""
    lote["cantidad_actual"] = round(lote["cantidad_actual"] - cantidad, 3)
    if lote["cantidad_actual"] <= 0:
        lote["cantidad_actual"], lote["estado"] = 0, "agotado"
    MOVIMIENTOS.insert(0, dict(fecha=_ahora(), tipo_movimiento=motivo, item=_fila(lote, tipo)["item"],
                               numero_lote=lote["numero_lote"], cantidad=-cantidad,
                               documento_ref=documento, responsable=RESPONSABLE))


def _items(tipo):
    if tipo == "insumo":
        return [dict(id=i["id_insumo"], nombre=i["nombre"], unidad=UNIDADES[i["id_unidad"]]) for i in INSUMOS]
    return [dict(id=k, nombre=v, unidad="unid") for k, v in PRODUCTOS.items()]


def _lineas_pendientes():
    """Líneas de órdenes de compra emitidas con saldo por recibir (RN-05)."""
    filas = []
    for o in ORDENES_COMPRA:
        for n, ln in enumerate(o["lineas"]):
            pendiente = ln["cantidad"] - ln["recibido"]
            if pendiente > 0:
                ins = _insumo(ln["id_insumo"])
                filas.append(dict(clave=f"{o['id_orden']}:{n}", numero_orden=o["numero_orden"],
                                  proveedor=PROVEEDORES[o["id_proveedor"]], insumo=ins["nombre"],
                                  unidad=UNIDADES[ins["id_unidad"]], perecedero=ins["perecedero"],
                                  pedido=ln["cantidad"], recibido=ln["recibido"], pendiente=pendiente,
                                  entrega=o["fecha_entrega_esperada"]))
    return filas


# ====================================================================
# RUTAS
# ====================================================================
# ------------------------------------------------------------ ALM-00 Panel
@almacen_bp.route("/")
def panel():
    filas = _todas_las_filas()
    por_vencer = sorted([f for f in filas if f["alerta"] in ("critico", "por_vencer") and f["estado"] == "disponible"],
                        key=lambda f: f["fecha_vencimiento"])
    vencidos = [f for f in filas if f["alerta"] == "vencido" and f["cantidad_actual"] > 0]
    stock_bajo = [s for s in _stock_insumos() if s["estado_stock"] == "reponer"]
    kpis = dict(
        por_vencer=len(por_vencer),
        vencidos=len(vencidos),
        stock_bajo=len(stock_bajo),
        recepciones_hoy=sum(1 for r in RECEPCIONES if r["fecha"] == _d(0)),
        por_recibir=len(_lineas_pendientes()),
        solicitudes=sum(1 for s in SOLICITUDES if not s["atendida"]),
    )
    return _render("almacenero/panel.html", kpis=kpis, por_vencer=por_vencer, vencidos=vencidos,
                   stock_bajo=stock_bajo, recepciones=RECEPCIONES[:5])


# ------------------------------------------------------------ ALM-01 Recepción de insumos
@almacen_bp.route("/recepcion", methods=["GET", "POST"])
def recepcion():
    pendientes = _lineas_pendientes()
    if request.method == "POST":
        f = request.form
        linea = next((p for p in pendientes if p["clave"] == f.get("linea")), None)
        numero_lote = f.get("numero_lote", "").strip().upper()
        vence = f.get("fecha_vencimiento") or None
        cantidad = f.get("cantidad", type=float) or 0
        errores = []
        if not linea:
            errores.append("Elige la orden de compra y el insumo que estás recibiendo.")
        else:
            o_id, n = (int(x) for x in linea["clave"].split(":"))
            orden = next(o for o in ORDENES_COMPRA if o["id_orden"] == o_id)
            ln = orden["lineas"][n]
            if not numero_lote:
                errores.append("Escribe el número de lote del proveedor.")
            elif any(l["id_insumo"] == ln["id_insumo"] and l["numero_lote"] == numero_lote for l in LOTES_INSUMO):
                errores.append(f"El lote {numero_lote} ya está registrado para {linea['insumo']} (RN-06).")
            if linea["perecedero"] and not vence:
                errores.append("Este insumo es perecedero: la fecha de vencimiento es obligatoria.")
            if vence and vence <= _d(0):
                errores.append("La fecha de vencimiento debe ser posterior a hoy; no se recibe mercadería vencida.")
            if cantidad <= 0:
                errores.append("La cantidad recibida debe ser mayor que cero.")
            elif cantidad > linea["pendiente"]:
                errores.append(f"Solo faltan {linea['pendiente']:g} {linea['unidad']} por recibir de esa orden.")
        if errores:
            for e in errores:
                flash(e, "error")
            return _render("almacenero/recepcion.html", pendientes=pendientes, recepciones=RECEPCIONES,
                           form=f, hoy=_d(0))
        # 1) crea el lote de insumo  2) actualiza la orden  3) movimiento de inventario (include RF-11)
        LOTES_INSUMO.append(dict(id_lote=len(LOTES_INSUMO) + 1, id_insumo=ln["id_insumo"], numero_lote=numero_lote,
                                 id_proveedor=orden["id_proveedor"], fecha_recepcion=_d(0), fecha_vencimiento=vence,
                                 cantidad_inicial=cantidad, cantidad_actual=cantidad, estado="disponible"))
        ln["recibido"] += cantidad
        RECEPCIONES.insert(0, dict(fecha=_d(0), numero_orden=orden["numero_orden"], insumo=linea["insumo"],
                                   numero_lote=numero_lote, fecha_vencimiento=vence, cantidad=cantidad,
                                   unidad=linea["unidad"], proveedor=linea["proveedor"], responsable=RESPONSABLE))
        MOVIMIENTOS.insert(0, dict(fecha=_ahora(), tipo_movimiento="recepcion", item=linea["insumo"],
                                   numero_lote=numero_lote, cantidad=cantidad, documento_ref=orden["numero_orden"],
                                   responsable=RESPONSABLE))
        flash(f"Recepción registrada: lote {numero_lote}, {cantidad:g} {linea['unidad']} de {linea['insumo']}. "
              "El inventario ya está actualizado.", "ok")
        return redirect(url_for("almacen.recepcion"))
    return _render("almacenero/recepcion.html", pendientes=pendientes, recepciones=RECEPCIONES, form={}, hoy=_d(0))


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
        if not ver_agotados and f["estado"] == "agotado":
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
    lote = next((l for l in _lista_lotes(tipo) if l["id_lote"] == id_lote), None) if tipo in ("insumo", "producto") else None
    if not lote:
        flash("No se encontró el lote.", "error")
    elif not motivo:
        flash("Escribe el motivo para dar de baja el lote.", "error")
    else:
        cant = lote["cantidad_actual"]
        _registrar_salida(lote, tipo, cant, "BAJA", motivo="baja")
        lote["estado"] = "baja"
        MOVIMIENTOS[0]["documento_ref"] = f"BAJA: {motivo}"
        flash(f"Lote {lote['numero_lote']} dado de baja ({cant:g}).", "ok")
    return redirect(url_for("almacen.existencias", alerta="atencion"))


# ------------------------------------------------------------ ALM-03 Despacho FEFO
@almacen_bp.route("/despacho", methods=["GET", "POST"])
def despacho():
    if request.method == "POST":
        tipo = request.form.get("tipo")
        id_item = request.form.get("id_item", type=int)
        cantidad = request.form.get("cantidad", type=float) or 0
        documento = request.form.get("documento", "").strip()
        plan, falta = _plan_fefo(tipo, id_item, cantidad) if tipo in ("insumo", "producto") else ([], cantidad)
        if cantidad <= 0 or not plan:
            flash("Indica un ítem y una cantidad válida.", "error")
        elif falta > 0:
            flash("No hay stock utilizable suficiente; el despacho no se registró.", "error")
        elif not documento:
            flash("Escribe el documento de referencia (orden de producción o pedido).", "error")
        else:
            for p in plan:
                lote = next(l for l in _lista_lotes(tipo) if l["id_lote"] == p["id_lote"])
                _registrar_salida(lote, tipo, p["tomar"], documento)
            sol = request.form.get("id_solicitud", type=int)
            for s in SOLICITUDES:
                if s["id_solicitud"] == sol:
                    s["atendida"] = True
            usados = ", ".join(f"{p['numero_lote']} ({p['tomar']:g})" for p in plan)
            flash(f"Despacho registrado para {documento}. Lotes usados: {usados}.", "ok")
            return redirect(url_for("almacen.despacho"))
        return redirect(url_for("almacen.despacho", tipo=tipo, id_item=id_item, cantidad=cantidad,
                                documento=documento))

    tipo = request.args.get("tipo", "insumo")
    if tipo not in ("insumo", "producto"):
        tipo = "insumo"
    id_item = request.args.get("id_item", type=int)
    cantidad = request.args.get("cantidad", type=float)
    plan, falta, disponible = [], 0, None
    if id_item and cantidad:
        plan, falta = _plan_fefo(tipo, id_item, cantidad)
        disponible = sum(l["cantidad_actual"] for l in _lotes_fefo(tipo, id_item))
    excluidos = []
    if id_item:  # lotes que NO se pueden usar y por qué (para explicar FEFO)
        campo = "id_insumo" if tipo == "insumo" else "id_producto"
        for l in _lista_lotes(tipo):
            if l[campo] == id_item and l not in _lotes_fefo(tipo, id_item) and l["cantidad_actual"] > 0:
                razon = "vencido" if _alerta(l) == "vencido" else l["estado"]
                excluidos.append(dict(_fila(l, tipo), razon=razon))
    pendientes = [dict(s, item=(_insumo(s["id_item"])["nombre"] if s["tipo"] == "insumo" else PRODUCTOS[s["id_item"]]))
                  for s in SOLICITUDES if not s["atendida"]]
    salidas = [m for m in MOVIMIENTOS if m["tipo_movimiento"] == "despacho"][:8]
    return _render("almacenero/despacho.html", tipo=tipo, items=_items(tipo), id_item=id_item, cantidad=cantidad,
                   documento=request.args.get("documento", ""), id_solicitud=request.args.get("id_solicitud", ""),
                   plan=plan, falta=falta, disponible=disponible, excluidos=excluidos,
                   pendientes=pendientes, salidas=salidas)


# ------------------------------------------------------------ ALM-04 Inventario físico y ajustes
@almacen_bp.route("/inventario", methods=["GET", "POST"])
def inventario():
    tipo = request.values.get("tipo", "insumo")
    if tipo not in ("insumo", "producto"):
        tipo = "insumo"
    lotes = [_fila(l, tipo) for l in _lista_lotes(tipo) if l["estado"] not in ("agotado", "baja")]
    lotes.sort(key=lambda f: (f["item"], f["numero_lote"]))
    if request.method == "POST":
        ajustes, errores = [], []
        for f in lotes:
            valor = request.form.get(f"contado_{f['id_lote']}", "").strip()
            if valor == "":
                continue
            try:
                contado = float(valor)
            except ValueError:
                errores.append(f"{f['numero_lote']}: la cantidad contada no es un número.")
                continue
            if contado < 0:
                errores.append(f"{f['numero_lote']}: la cantidad contada no puede ser negativa.")
                continue
            dif = round(contado - f["cantidad_actual"], 3)
            just = request.form.get(f"just_{f['id_lote']}", "").strip()
            if dif and not just:  # RN-09
                errores.append(f"{f['numero_lote']}: hay una diferencia de {dif:+g}; escribe la justificación.")
            ajustes.append((f, contado, dif, just))
        if not ajustes and not errores:
            errores.append("Ingresa la cantidad contada de al menos un lote.")
        if errores:
            for e in errores:
                flash(e, "error")
            return _render("almacenero/inventario.html", tipo=tipo, lotes=lotes, form=request.form,
                           historial=INVENTARIOS)
        detalle = []
        for f, contado, dif, just in ajustes:
            if dif:
                lote = next(l for l in _lista_lotes(tipo) if l["id_lote"] == f["id_lote"])
                lote["cantidad_actual"] = contado
                if contado == 0:
                    lote["estado"] = "agotado"
                MOVIMIENTOS.insert(0, dict(fecha=_ahora(), tipo_movimiento="ajuste", item=f["item"],
                                           numero_lote=f["numero_lote"], cantidad=dif,
                                           documento_ref=f"INV-{len(INVENTARIOS) + 1:03d}", responsable=RESPONSABLE))
                detalle.append(dict(item=f["item"], numero_lote=f["numero_lote"], cantidad_sistema=f["cantidad_actual"],
                                    cantidad_contada=contado, diferencia=dif, justificacion=just))
        INVENTARIOS.insert(0, dict(id_inventario=len(INVENTARIOS) + 1, fecha=_d(0), tipo=tipo,
                                   lotes_contados=len(ajustes), ajustes=detalle, responsable=RESPONSABLE,
                                   estado="cerrado"))
        flash(f"Inventario físico registrado: {len(ajustes)} lotes contados, {len(detalle)} ajustes aplicados.", "ok")
        return redirect(url_for("almacen.inventario", tipo=tipo))
    return _render("almacenero/inventario.html", tipo=tipo, lotes=lotes, form={}, historial=INVENTARIOS)
