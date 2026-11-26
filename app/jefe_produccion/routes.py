"""Rutas del rol JEFE DE PRODUCCIÓN con datos simulados (sin base de datos).

Cuando conectes PostgreSQL, reemplaza cada bloque de datos por la consulta
correspondiente; las plantillas esperan exactamente estas claves.
"""
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for

from . import jefe_bp

MENU = [
    ("Panel", "jefe.panel", "Resumen de planta"),
    ("Recetas", "jefe.recetas", "Registro y versiones"),
    ("Orden de producción", "jefe.ordenes", "Verifica insumos"),
    ("Consumo de insumos", "jefe.consumo", "Descuenta inventario"),
    ("Lote y etiqueta", "jefe.lotes", "Asigna lote, imprime"),
    ("Mermas y rendimiento", "jefe.mermas", "Por orden"),
]


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="jefe de producción", **ctx)


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


# ====================================================================
# DATOS SIMULADOS
# ====================================================================
PRODUCTOS = [  # tabla productos
    dict(id_producto=1, codigo="PROD001", nombre="Yogur natural 1L", vida_util_dias=21),
    dict(id_producto=3, codigo="PROD003", nombre="Pan de molde", vida_util_dias=7),
    dict(id_producto=4, codigo="PROD004", nombre="Galletas de avena", vida_util_dias=120),
]

INSUMOS = [  # tabla insumos + stock sumado de lotes_insumos disponibles
    dict(id_insumo=1, codigo="INS001", nombre="Leche entera", unidad="L", stock=800.0, stock_minimo=200),
    dict(id_insumo=2, codigo="INS002", nombre="Harina de trigo", unidad="kg", stock=400.0, stock_minimo=100),
    dict(id_insumo=3, codigo="INS003", nombre="Levadura", unidad="kg", stock=1.2, stock_minimo=3),
    dict(id_insumo=4, codigo="INS004", nombre="Azúcar", unidad="kg", stock=150.0, stock_minimo=50),
    dict(id_insumo=5, codigo="INS005", nombre="Avena", unidad="kg", stock=90.0, stock_minimo=40),
    dict(id_insumo=6, codigo="INS006", nombre="Sal", unidad="kg", stock=30.0, stock_minimo=5),
    dict(id_insumo=7, codigo="INS007", nombre="Fermento lácteo", unidad="kg", stock=6.0, stock_minimo=2),
]

RECETAS = [  # tabla recetas; 'detalle' = receta_detalle (id_insumo, cantidad por rendimiento)
    dict(id_receta=1, id_producto=3, version="v1", descripcion="Pan de molde clásico", rendimiento=100,
         vigente=False, fecha=_d(-120), detalle=[(2, 25.0), (3, 0.5), (6, 0.5)]),
    dict(id_receta=2, id_producto=3, version="v2", descripcion="Pan de molde con azúcar", rendimiento=100,
         vigente=True, fecha=_d(-30), detalle=[(2, 25.0), (3, 0.6), (6, 0.5), (4, 1.0)]),
    dict(id_receta=3, id_producto=1, version="v1", descripcion="Yogur natural", rendimiento=200,
         vigente=True, fecha=_d(-90), detalle=[(1, 210.0), (7, 0.8), (4, 10.0)]),
    dict(id_receta=4, id_producto=4, version="v1", descripcion="Galleta de avena", rendimiento=300,
         vigente=True, fecha=_d(-60), detalle=[(5, 15.0), (2, 10.0), (4, 6.0)]),
]

ORDENES = [  # tabla ordenes_produccion
    dict(id_orden_produccion=1, numero_orden="OP-2026-001", id_receta=2, cantidad_planificada=500,
         cantidad_producida=472, fecha_inicio=_d(-6), estado="completada", consumido=True, lote="LP-2026-093"),
    dict(id_orden_produccion=2, numero_orden="OP-2026-002", id_receta=3, cantidad_planificada=400,
         cantidad_producida=0, fecha_inicio=_d(-1), estado="en_proceso", consumido=False, lote=None),
    dict(id_orden_produccion=3, numero_orden="OP-2026-003", id_receta=4, cantidad_planificada=600,
         cantidad_producida=0, fecha_inicio=_d(2), estado="planificada", consumido=False, lote=None),
]
LOTES = [dict(id_orden_produccion=1, numero_lote="LP-2026-093", fecha_produccion=_d(-5),
              fecha_vencimiento=_d(2), cantidad=472)]  # tabla lotes_productos
CONSUMOS = []  # tabla consumo_insumos_produccion
MERMAS = [dict(id_orden_produccion=1, tipo_merma="Proceso", insumo="Harina de trigo", cantidad=3.5,
               causa="Derrame en amasado", fecha=_d(-5))]  # tabla mermas_produccion


def _producto(id):
    return next(p for p in PRODUCTOS if p["id_producto"] == id)


def _insumo(id):
    return next(i for i in INSUMOS if i["id_insumo"] == id)


def _receta(id):
    r = next((r for r in RECETAS if r["id_receta"] == id), None)
    if not r:
        abort(404)
    return r


def _orden(id):
    o = next((o for o in ORDENES if o["id_orden_produccion"] == id), None)
    if not o:
        abort(404)
    return o


def _nombre_receta(r):
    return f"{_producto(r['id_producto'])['nombre']} ({r['version']})"


def _requerimiento(receta, cantidad):
    """Insumos necesarios para producir 'cantidad' unidades y si alcanza el stock."""
    filas = []
    for id_insumo, por_tanda in receta["detalle"]:
        i = _insumo(id_insumo)
        req = round(por_tanda * cantidad / receta["rendimiento"], 3)
        filas.append(dict(id_insumo=id_insumo, insumo=i["nombre"], unidad=i["unidad"], requerido=req,
                          disponible=i["stock"], falta=round(max(req - i["stock"], 0), 3),
                          suficiente=i["stock"] >= req))
    return filas


def _vista_orden(o):
    r = _receta(o["id_receta"])
    prod = o["cantidad_producida"]
    rend = round(prod * 100 / o["cantidad_planificada"]) if o["estado"] == "completada" else None
    return {**o, "producto": _producto(r["id_producto"])["nombre"], "version": r["version"],
            "receta": _nombre_receta(r), "fecha": o["fecha_inicio"], "rendimiento": rend,
            "merma_total": round(sum(m["cantidad"] for m in MERMAS
                                     if m["id_orden_produccion"] == o["id_orden_produccion"]), 3)}


def _rendimiento_promedio():
    r = [v["rendimiento"] for v in map(_vista_orden, ORDENES) if v["rendimiento"] is not None]
    return round(sum(r) / len(r)) if r else 0


# ====================================================================
# RUTAS
# ====================================================================
@jefe_bp.route("/")
def panel():
    kpis = dict(
        en_proceso=sum(1 for o in ORDENES if o["estado"] == "en_proceso"),
        planificadas=sum(1 for o in ORDENES if o["estado"] == "planificada"),
        por_reponer=sum(1 for i in INSUMOS if i["stock"] < i["stock_minimo"]),
        rendimiento=f"{_rendimiento_promedio()} %")
    recientes = [_vista_orden(o) for o in reversed(ORDENES)][:6]
    return _render("jefe_produccion/panel.html", kpis=kpis, recientes=recientes)


# ------------------------------------------------------------ Recetas
@jefe_bp.route("/recetas")
def recetas():
    filas = [dict(id_receta=r["id_receta"], producto=_producto(r["id_producto"])["nombre"],
                  version=r["version"], descripcion=r["descripcion"], rendimiento=r["rendimiento"],
                  fecha=r["fecha"], estado="vigente" if r["vigente"] else "baja")
             for r in sorted(RECETAS, key=lambda r: (r["id_producto"], r["version"]), reverse=True)]
    return _render("jefe_produccion/recetas.html", recetas=filas)


@jefe_bp.route("/recetas/<int:id>")
def receta_detalle(id):
    r = _receta(id)
    lineas = [dict(codigo=_insumo(i)["codigo"], insumo=_insumo(i)["nombre"], unidad=_insumo(i)["unidad"],
                   cantidad=c) for i, c in r["detalle"]]
    return _render("jefe_produccion/receta_detalle.html", r=dict(**r, nombre=_nombre_receta(r)), lineas=lineas)


@jefe_bp.route("/recetas/nueva", methods=["GET", "POST"])
def receta_nueva():
    if request.method == "POST":
        f = request.form
        id_producto = f.get("id_producto", type=int)
        rendimiento = f.get("rendimiento", type=float) or 0
        detalle = [(i["id_insumo"], f.get(f"ins_{i['id_insumo']}", type=float) or 0) for i in INSUMOS]
        detalle = [(i, c) for i, c in detalle if c > 0]
        errores = []
        if not any(p["id_producto"] == id_producto for p in PRODUCTOS):
            errores.append("Elige un producto.")
        if rendimiento <= 0:
            errores.append("El rendimiento debe ser mayor que cero.")
        if not detalle:
            errores.append("Agrega al menos un insumo con cantidad.")
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            previas = [r for r in RECETAS if r["id_producto"] == id_producto]
            for r in previas:
                r["vigente"] = False
            RECETAS.append(dict(id_receta=len(RECETAS) + 1, id_producto=id_producto, version=f"v{len(previas) + 1}",
                                descripcion=f.get("descripcion") or None, rendimiento=rendimiento, vigente=True,
                                fecha=_d(0), detalle=detalle))
            flash("Receta guardada como nueva versión vigente.", "ok")
            return redirect(url_for("jefe.recetas"))
    return _render("jefe_produccion/receta_form.html", productos=PRODUCTOS, insumos=INSUMOS)


# ------------------------------------------------------------ Orden de producción
@jefe_bp.route("/ordenes")
def ordenes():
    estado = request.args.get("estado", "")
    filas = [_vista_orden(o) for o in reversed(ORDENES) if not estado or o["estado"] == estado]
    return _render("jefe_produccion/ordenes.html", estado=estado, ordenes=filas)


@jefe_bp.route("/ordenes/nueva", methods=["GET", "POST"])
def orden_nueva():
    vigentes = [dict(id_receta=r["id_receta"], nombre=_nombre_receta(r)) for r in RECETAS if r["vigente"]]
    id_receta = request.values.get("id_receta", type=int)
    cantidad = request.values.get("cantidad", type=int) or 0
    requerimiento, alcanza = None, False
    if id_receta and cantidad > 0:
        r = _receta(id_receta)
        requerimiento = _requerimiento(r, cantidad)
        alcanza = all(x["suficiente"] for x in requerimiento)
    if request.method == "POST":
        if not requerimiento:
            flash("Elige la receta y la cantidad a producir.", "error")
        elif not alcanza:
            flash("No se puede crear la orden: faltan insumos.", "error")
        else:
            n = len(ORDENES) + 1
            ORDENES.append(dict(id_orden_produccion=n, numero_orden=f"OP-{date.today().year}-{n:03d}",
                                id_receta=id_receta, cantidad_planificada=cantidad, cantidad_producida=0,
                                fecha_inicio=request.form.get("fecha") or _d(0), estado="planificada",
                                consumido=False, lote=None))
            flash("Orden de producción creada.", "ok")
            return redirect(url_for("jefe.ordenes"))
    return _render("jefe_produccion/orden_nueva.html", recetas=vigentes, id_receta=id_receta, cantidad=cantidad,
                   requerimiento=requerimiento, alcanza=alcanza, hoy=_d(0))


@jefe_bp.route("/ordenes/<int:id>/iniciar", methods=["POST"])
def orden_iniciar(id):
    o = _orden(id)
    if o["estado"] != "planificada":
        flash("Solo se inicia una orden planificada.", "error")
    elif not all(x["suficiente"] for x in _requerimiento(_receta(o["id_receta"]), o["cantidad_planificada"])):
        flash("Faltan insumos para iniciar esta orden.", "error")
    else:
        o["estado"] = "en_proceso"
        flash(f"Orden {o['numero_orden']} en proceso.", "ok")
    return redirect(url_for("jefe.ordenes"))


@jefe_bp.route("/ordenes/<int:id>/finalizar", methods=["POST"])
def orden_finalizar(id):
    o = _orden(id)
    producida = request.form.get("producida", type=int) or 0
    if o["estado"] != "en_proceso" or not o["consumido"]:
        flash("Registra primero el consumo de insumos de esta orden.", "error")
    elif producida <= 0:
        flash("Escribe la cantidad producida.", "error")
    else:
        o.update(estado="completada", cantidad_producida=producida)
        flash(f"Orden {o['numero_orden']} finalizada.", "ok")
    return redirect(url_for("jefe.ordenes"))


# ------------------------------------------------------------ Consumo de insumos
@jefe_bp.route("/consumo")
def consumo():
    pendientes = [dict(**_vista_orden(o), lineas=_requerimiento(_receta(o["id_receta"]), o["cantidad_planificada"]))
                  for o in ORDENES if o["estado"] == "en_proceso" and not o["consumido"]]
    return _render("jefe_produccion/consumo.html", pendientes=pendientes, historial=list(reversed(CONSUMOS)))


@jefe_bp.route("/consumo/<int:id>", methods=["POST"])
def consumo_registrar(id):
    o = _orden(id)
    lineas = _requerimiento(_receta(o["id_receta"]), o["cantidad_planificada"])
    reales = {x["id_insumo"]: request.form.get(f"real_{x['id_insumo']}", type=float) for x in lineas}
    errores = [f"{x['insumo']}: pides {reales[x['id_insumo']]} y hay {x['disponible']}."
               for x in lineas if reales[x["id_insumo"]] is None or reales[x["id_insumo"]] < 0
               or reales[x["id_insumo"]] > x["disponible"]]
    if o["estado"] != "en_proceso" or o["consumido"]:
        flash("Esta orden ya no admite consumo.", "error")
    elif errores:
        for e in errores:
            flash(e, "error")
    else:
        for x in lineas:
            _insumo(x["id_insumo"])["stock"] = round(_insumo(x["id_insumo"])["stock"] - reales[x["id_insumo"]], 3)
            CONSUMOS.append(dict(fecha=_d(0), numero_orden=o["numero_orden"], insumo=x["insumo"],
                                 cantidad=f"{reales[x['id_insumo']]} {x['unidad']}"))
        o["consumido"] = True
        flash("Consumo registrado y descontado del inventario.", "ok")
    return redirect(url_for("jefe.consumo"))


# ------------------------------------------------------------ Lote y etiqueta
@jefe_bp.route("/lotes")
def lotes():
    sin_lote = []
    for o in ORDENES:
        if o["estado"] == "completada" and not o["lote"]:
            v = _vista_orden(o)
            vida = _producto(_receta(o["id_receta"])["id_producto"])["vida_util_dias"]
            sin_lote.append({**v, "lote_sugerido": f"LP-{date.today().year}-{100 + o['id_orden_produccion']}",
                             "vence_sugerido": _d(vida)})
    filas = [dict(**l, orden=_orden(l["id_orden_produccion"])["numero_orden"],
                  producto=_vista_orden(_orden(l["id_orden_produccion"]))["producto"]) for l in reversed(LOTES)]
    return _render("jefe_produccion/lotes.html", sin_lote=sin_lote, lotes=filas)


@jefe_bp.route("/lotes/<int:id>/asignar", methods=["POST"])
def lote_asignar(id):
    o = _orden(id)
    numero = request.form.get("numero_lote", "").strip()
    vence = request.form.get("vencimiento", "")
    if o["estado"] != "completada" or o["lote"]:
        flash("Esta orden no admite un lote nuevo.", "error")
    elif not numero or not vence:
        flash("Escribe el número de lote y su vencimiento.", "error")
    elif any(l["numero_lote"] == numero for l in LOTES):
        flash("Ese número de lote ya existe.", "error")
    else:
        LOTES.append(dict(id_orden_produccion=id, numero_lote=numero, fecha_produccion=_d(0),
                          fecha_vencimiento=vence, cantidad=o["cantidad_producida"]))
        o["lote"] = numero
        flash("Lote asignado.", "ok")
        return redirect(url_for("jefe.etiqueta", numero=numero))
    return redirect(url_for("jefe.lotes"))


@jefe_bp.route("/lotes/<numero>/etiqueta")
def etiqueta(numero):
    l = next((l for l in LOTES if l["numero_lote"] == numero), None)
    if not l:
        abort(404)
    o = _vista_orden(_orden(l["id_orden_produccion"]))
    return _render("jefe_produccion/etiqueta.html", l=l, o=o)


# ------------------------------------------------------------ Mermas y rendimiento
@jefe_bp.route("/mermas", methods=["GET", "POST"])
def mermas():
    if request.method == "POST":
        f = request.form
        cantidad = f.get("cantidad", type=float) or 0
        o = next((o for o in ORDENES if o["id_orden_produccion"] == f.get("id_orden", type=int)), None)
        if not o or cantidad <= 0:
            flash("Elige la orden y escribe una cantidad mayor que cero.", "error")
        else:
            i = next((i for i in INSUMOS if i["id_insumo"] == f.get("id_insumo", type=int)), None)
            MERMAS.append(dict(id_orden_produccion=o["id_orden_produccion"], tipo_merma=f.get("tipo", "Proceso"),
                               insumo=i["nombre"] if i else "—", cantidad=cantidad,
                               causa=f.get("causa") or None, fecha=_d(0)))
            flash("Merma registrada.", "ok")
            return redirect(url_for("jefe.mermas"))
    resumen = [_vista_orden(o) for o in reversed(ORDENES) if o["estado"] != "planificada"]
    detalle = [dict(**m, orden=_orden(m["id_orden_produccion"])["numero_orden"]) for m in reversed(MERMAS)]
    return _render("jefe_produccion/mermas.html", ordenes=[_vista_orden(o) for o in ORDENES],
                   insumos=INSUMOS, resumen=resumen, detalle=detalle)
