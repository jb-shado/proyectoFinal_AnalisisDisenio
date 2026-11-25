"""Rutas del rol CALIDAD con datos simulados (sin base de datos).

Cuando conectes PostgreSQL, reemplaza cada bloque de datos por la consulta
correspondiente; las plantillas esperan exactamente estas claves.
"""
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for

from . import calidad_bp

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


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


# ====================================================================
# DATOS SIMULADOS
# ====================================================================
LOTES_PRODUCTO = [  # tabla lotes_productos + productos
    dict(id_lote_producto=1, numero_lote="LP-2026-101", producto="Yogur natural 1L",
         fecha_produccion=_d(-2), fecha_vencimiento=_d(28), cantidad_actual=100, estado="cuarentena"),
    dict(id_lote_producto=2, numero_lote="LP-2026-102", producto="Queso fresco 500g",
         fecha_produccion=_d(-1), fecha_vencimiento=_d(19), cantidad_actual=60, estado="cuarentena"),
    dict(id_lote_producto=3, numero_lote="LP-2026-103", producto="Pan de molde",
         fecha_produccion=_d(-1), fecha_vencimiento=_d(6), cantidad_actual=80, estado="cuarentena"),
    dict(id_lote_producto=4, numero_lote="LP-2026-098", producto="Galletas de avena",
         fecha_produccion=_d(-10), fecha_vencimiento=_d(50), cantidad_actual=110, estado="disponible"),
    dict(id_lote_producto=5, numero_lote="LP-2026-099", producto="Mermelada de fresa",
         fecha_produccion=_d(-9), fecha_vencimiento=_d(170), cantidad_actual=55, estado="disponible"),
    dict(id_lote_producto=6, numero_lote="LP-2026-100", producto="Jugo de naranja 1L",
         fecha_produccion=_d(-8), fecha_vencimiento=_d(7), cantidad_actual=95, estado="disponible"),
    dict(id_lote_producto=7, numero_lote="LP-2026-095", producto="Mayonesa 500g",
         fecha_produccion=_d(-20), fecha_vencimiento=_d(160), cantidad_actual=38, estado="disponible"),
    dict(id_lote_producto=8, numero_lote="LP-2026-090", producto="Papas fritas 200g",
         fecha_produccion=_d(-30), fecha_vencimiento=_d(60), cantidad_actual=48, estado="rechazado"),
]

LOTES_INSUMO = [  # tabla lotes_insumos + insumos
    dict(id_lote=1, numero_lote="LI-2026-041", item="Leche cruda"),
    dict(id_lote=2, numero_lote="LI-2026-042", item="Harina de trigo"),
    dict(id_lote=3, numero_lote="LI-2026-043", item="Azúcar refinada"),
    dict(id_lote=4, numero_lote="LI-2026-044", item="Mantequilla"),
]

CONTROLES = [  # tabla controles_calidad (el más reciente primero)
    dict(fecha=_d(0), lote="LP-2026-101", tipo_control="Temperatura", valor_medido=4.0,
         unidad_medida="°C", resultado="aprobado", responsable="Roberto Villacorta"),
    dict(fecha=_d(0), lote="LP-2026-102", tipo_control="Inspección visual", valor_medido=None,
         unidad_medida=None, resultado="observado", responsable="Roberto Villacorta"),
    dict(fecha=_d(-1), lote="LI-2026-041", tipo_control="Temperatura", valor_medido=5.2,
         unidad_medida="°C", resultado="aprobado", responsable="Roberto Villacorta"),
    dict(fecha=_d(-3), lote="LP-2026-090", tipo_control="Microbiológico", valor_medido=None,
         unidad_medida=None, resultado="rechazado", responsable="Roberto Villacorta"),
    dict(fecha=_d(-8), lote="LP-2026-100", tipo_control="pH", valor_medido=3.8,
         unidad_medida="pH", resultado="aprobado", responsable="Roberto Villacorta"),
    dict(fecha=_d(-9), lote="LP-2026-099", tipo_control="Inspección visual", valor_medido=None,
         unidad_medida=None, resultado="aprobado", responsable="Roberto Villacorta"),
]

# Vistas v_trazabilidad_atras / v_trazabilidad_adelante
INSUMOS_POR_PRODUCTO = {
    "Yogur natural 1L": [("Leche cruda", "LI-2026-041", "Lácteos del Altiplano SRL", 80),
                         ("Envase plástico 1L", "LI-2026-050", "Empaques Plásticos Andinos", 100)],
    "Queso fresco 500g": [("Leche cruda", "LI-2026-041", "Lácteos del Altiplano SRL", 40),
                          ("Sal fina", "LI-2026-046", "Especias y Condimentos SRL", 2)],
    "Jugo de naranja 1L": [("Azúcar refinada", "LI-2026-043", "Azúcares del Norte SRL", 10),
                           ("Envase plástico 1L", "LI-2026-050", "Empaques Plásticos Andinos", 100)],
    "Mermelada de fresa": [("Azúcar refinada", "LI-2026-043", "Azúcares del Norte SRL", 25),
                           ("Fruta fresca", "LI-2026-048", "Frutas y Conservas del Valle", 30)],
    "_otros": [("Harina de trigo", "LI-2026-042", "Harinas Bolivianas SA", 50),
               ("Etiqueta adhesiva", "LI-2026-051", "Envases y Etiquetas SRL", 100)],
}
CLIENTES_ENTREGA = ["Distribuidora El Sol", "Supermercados Andinos", "Tienda Doña Rosa",
                    "Mercado Central", "Comercial La Paz SRL"]

RECLAMOS = [  # tabla reclamos_cliente (compartida con el rol vendedor)
    dict(id_reclamo=1, numero_reclamo="REC-2026-014", cliente="Supermercados Andinos",
         telefono="2-333002", email="compras@superandinos.bo", numero_factura="FAC-2026-101",
         numero_lote="LP-2026-100", producto="Jugo de naranja 1L", estado="abierto", fecha=_d(-2),
         descripcion="Varias botellas llegaron con sabor fermentado.", resolucion=None),
    dict(id_reclamo=2, numero_reclamo="REC-2026-013", cliente="Tienda Doña Rosa",
         telefono="2-333003", email="rosita@mail.com", numero_factura="FAC-2026-098",
         numero_lote="LP-2026-099", producto="Mermelada de fresa", estado="en_revision", fecha=_d(-4),
         descripcion="Tapa floja en 3 frascos, se derramó el contenido.", resolucion=None),
    dict(id_reclamo=3, numero_reclamo="REC-2026-012", cliente="Distribuidora El Sol",
         telefono="2-333001", email="compras@elsol.bo", numero_factura="FAC-2026-095",
         numero_lote="LP-2026-098", producto="Galletas de avena", estado="abierto", fecha=_d(-5),
         descripcion="Galletas blandas, parecen húmedas.", resolucion=None),
    dict(id_reclamo=4, numero_reclamo="REC-2026-010", cliente="Mercado Central",
         telefono="2-333004", email="pedrol@mail.com", numero_factura="FAC-2026-090",
         numero_lote="LP-2026-095", producto="Mayonesa 500g", estado="resuelto", fecha=_d(-15),
         descripcion="Envase abollado al recibir.", resolucion="Se repuso la mercadería."),
    dict(id_reclamo=5, numero_reclamo="REC-2026-008", cliente="Comercial La Paz SRL",
         telefono="2-333005", email="compras@comlaps.bo", numero_factura="FAC-2026-085",
         numero_lote="LP-2026-098", producto="Galletas de avena", estado="cerrado", fecha=_d(-30),
         descripcion="Fecha de vencimiento ilegible.", resolucion="Reclamo sin fundamento: la fecha era legible."),
]


# ====================================================================
# Funciones reutilizables (también las usa el rol vendedor)
# ====================================================================
def _lote(numero):
    return next((l for l in LOTES_PRODUCTO if l["numero_lote"] == numero), None)


def traza_atras(numero):
    l = _lote(numero)
    if not l:
        return []
    insumos = INSUMOS_POR_PRODUCTO.get(l["producto"], INSUMOS_POR_PRODUCTO["_otros"])
    return [dict(lote_producto=numero, producto=l["producto"], insumo=i, lote_insumo=li,
                 proveedor=pr, cantidad_consumida=c, fecha_consumo=l["fecha_produccion"])
            for i, li, pr, c in insumos]


def traza_adelante(numero):
    l = _lote(numero)
    if not l or l["estado"] == "cuarentena":  # en cuarentena aún no se entrega a nadie
        return []
    ini = l["id_lote_producto"] % len(CLIENTES_ENTREGA)
    return [dict(lote_producto=numero, producto=l["producto"],
                 cliente=CLIENTES_ENTREGA[(ini + k) % len(CLIENTES_ENTREGA)],
                 numero_factura=f"FAC-2026-{90 + l['id_lote_producto'] + k:03d}",
                 cantidad=10 * (k + 1), fecha_emision=_d(-6 + k))
            for k in range(3)]


def filas_reclamos(estado=""):
    return [r for r in RECLAMOS if not estado or r["estado"] == estado]


def reclamo_por_id(id):
    return next((r for r in RECLAMOS if r["id_reclamo"] == id), None)


def actualizar_reclamo(id, estado, resolucion):
    r = reclamo_por_id(id)
    if not r:
        abort(404)
    r["estado"], r["resolucion"] = estado, resolucion or None


# ====================================================================
# RUTAS
# ====================================================================
@calidad_bp.route("/")
def panel():
    kpis = dict(
        controles_hoy=sum(1 for c in CONTROLES if c["fecha"] == _d(0)),
        lotes_pendientes=sum(1 for l in LOTES_PRODUCTO if l["estado"] == "cuarentena"),
        rechazos_30d=sum(1 for c in CONTROLES if c["resultado"] == "rechazado"),
        lotes_por_vencer=sum(1 for l in LOTES_PRODUCTO
                             if l["estado"] == "disponible" and l["fecha_vencimiento"] <= _d(30)),
        reclamos_pendientes=sum(1 for r in RECLAMOS if r["estado"] in ("abierto", "en_revision")),
    )
    pendientes = [l for l in LOTES_PRODUCTO if l["estado"] == "cuarentena"]
    return _render("calidad/panel.html", kpis=kpis, pendientes=pendientes, ultimos=CONTROLES[:8])


@calidad_bp.route("/controles", methods=["GET", "POST"])
def controles():
    lotes = [dict(tipo="producto", id_lote=l["id_lote_producto"], numero_lote=l["numero_lote"],
                  item=l["producto"]) for l in LOTES_PRODUCTO if l["estado"] != "rechazado"]
    lotes += [dict(tipo="insumo", **l) for l in LOTES_INSUMO]
    if request.method == "POST":
        tipo, _, id_lote = request.form.get("lote", ":").partition(":")
        elegido = next((l for l in lotes if l["tipo"] == tipo and str(l["id_lote"]) == id_lote), None)
        if not elegido:
            flash("Elige el lote que vas a controlar.", "error")
            return redirect(url_for("calidad.controles"))
        valor = request.form.get("valor_medido")
        CONTROLES.insert(0, dict(
            fecha=_d(0), lote=elegido["numero_lote"],
            tipo_control=request.form.get("tipo_control", "").strip(),
            valor_medido=float(valor) if valor else None,
            unidad_medida=request.form.get("unidad_medida") or None,
            resultado=request.form.get("resultado"), responsable="Roberto Villacorta"))
        flash("Control registrado.", "ok")
        return redirect(url_for("calidad.controles"))
    return _render("calidad/controles.html", lotes=lotes, historial=CONTROLES)


@calidad_bp.route("/decision", methods=["GET", "POST"])
def decision():
    if request.method == "POST":
        accion = request.form.get("accion")
        id_lote = request.form.get("id_lote", type=int)
        lote = next((l for l in LOTES_PRODUCTO if l["id_lote_producto"] == id_lote), None)
        if accion not in ("aprobar", "rechazar") or not lote:
            abort(400)
        lote["estado"] = "disponible" if accion == "aprobar" else "rechazado"
        flash(f"Lote {lote['numero_lote']} {'aprobado' if accion == 'aprobar' else 'rechazado'}.", "ok")
        return redirect(url_for("calidad.decision"))
    estado = request.args.get("estado", "cuarentena")
    filas = []
    for l in LOTES_PRODUCTO:
        if l["estado"] != estado:
            continue
        ultimo = next((c["resultado"] for c in CONTROLES if c["lote"] == l["numero_lote"]), None)
        filas.append({**l, "ultimo_control": ultimo})
    return _render("calidad/decision.html", estado=estado, lotes=filas)


def _rastreo(sentido):
    lote = request.args.get("lote", "").strip()
    funcion = traza_atras if sentido == "atras" else traza_adelante
    buscables = [dict(numero_lote=l["numero_lote"], producto=l["producto"]) for l in LOTES_PRODUCTO]
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
    actualizar_reclamo(id, request.form.get("estado", "en_revision"), request.form.get("resolucion"))
    flash("Reclamo actualizado.", "ok")
    return redirect(url_for("calidad.reclamo_detalle", id=id))
