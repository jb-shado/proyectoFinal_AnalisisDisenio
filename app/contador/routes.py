"""Rutas del rol CONTADOR con datos simulados (sin base de datos).

Cuando conectes PostgreSQL, reemplaza cada bloque de datos por la consulta
correspondiente; las plantillas esperan exactamente estas claves.
"""
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for

from . import finanzas_bp

MENU = [
    ("Panel", "finanzas.panel", "Resumen financiero"),
    ("Cuentas por pagar", "finanzas.cuentas", "Pagos a proveedores"),
    ("Asientos contables", "finanzas.asientos", "Generación automática"),
    ("Costo de producción", "finanzas.costos", "Por receta y lote"),
    ("Estados financieros", "finanzas.estados", "Reportes contables"),
]


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="contador", **ctx)


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


def _m(x):
    return f"{x:,.2f}"


# ====================================================================
# DATOS SIMULADOS
# ====================================================================
PLAN = {  # tabla plan_cuentas: codigo -> (nombre, tipo, naturaleza)
    "1.1.01": ("Caja y bancos", "activo", "D"),
    "1.1.02": ("Inventario de insumos", "activo", "D"),
    "1.1.03": ("Inventario de producto terminado", "activo", "D"),
    "1.1.04": ("Cuentas por cobrar", "activo", "D"),
    "2.1.01": ("Cuentas por pagar", "pasivo", "A"),
    "3.1.01": ("Capital social", "patrimonio", "A"),
    "4.1.01": ("Ventas", "ingreso", "A"),
    "5.1.01": ("Costo de ventas", "costo", "D"),
}

ASIENTOS = []  # tabla asientos_contables + asiento_detalle (lineas = [(codigo, debe, haber)])


def _asiento(descripcion, origen, lineas, dias=0):
    """Genera un asiento balanceado; es lo que se llama desde cada operación."""
    assert round(sum(d for _, d, _ in lineas), 2) == round(sum(h for _, _, h in lineas), 2)
    n = len(ASIENTOS) + 1
    ASIENTOS.append(dict(id_asiento=n, numero_asiento=f"AS-{date.today().year}-{n:03d}", fecha=_d(dias),
                         descripcion=descripcion, origen=origen, estado="registrado", lineas=lineas))


CXP = [  # tabla cuentas_por_pagar
    dict(id_cxp=1, proveedor="Molinos del Valle", orden_compra="OC-2026-011", monto_original=12400.0,
         saldo=12400.0, fecha_vencimiento=_d(3)),
    dict(id_cxp=2, proveedor="Empaques Andinos", orden_compra="OC-2026-012", monto_original=5150.0,
         saldo=5150.0, fecha_vencimiento=_d(5)),
    dict(id_cxp=3, proveedor="Lácteos La Paz", orden_compra="OC-2026-009", monto_original=3800.0,
         saldo=0.0, fecha_vencimiento=_d(-6)),
    dict(id_cxp=4, proveedor="Granos del Altiplano", orden_compra="OC-2026-008", monto_original=2200.0,
         saldo=2200.0, fecha_vencimiento=_d(-4)),
]
PAGOS = [dict(fecha=_d(-8), proveedor="Lácteos La Paz", orden_compra="OC-2026-009", monto=_m(3800),
              metodo_pago="Transferencia", referencia="TR-0457")]  # tabla pagos_proveedor

_asiento("Aporte de capital", "capital", [("1.1.01", 100000, 0), ("3.1.01", 0, 100000)], -90)
_asiento("Compra OC-2026-009", "compra", [("1.1.02", 3800, 0), ("2.1.01", 0, 3800)], -20)
_asiento("Pago OC-2026-009", "pago_proveedor", [("2.1.01", 3800, 0), ("1.1.01", 0, 3800)], -8)
_asiento("Compra OC-2026-008", "compra", [("1.1.02", 2200, 0), ("2.1.01", 0, 2200)], -15)
_asiento("Compra OC-2026-011", "compra", [("1.1.02", 12400, 0), ("2.1.01", 0, 12400)], -9)
_asiento("Compra OC-2026-012", "compra", [("1.1.02", 5150, 0), ("2.1.01", 0, 5150)], -7)
_asiento("Producción OP-2026-001", "produccion", [("1.1.03", 4200, 0), ("1.1.02", 0, 4200)], -5)
_asiento("Venta PED-2026-001", "venta", [("1.1.04", 9600, 0), ("4.1.01", 0, 9600)], -4)
_asiento("Costo de venta PED-2026-001", "venta", [("5.1.01", 4000, 0), ("1.1.03", 0, 4000)], -4)

COSTOS = [  # tabla costos_produccion (+ orden, receta y lote)
    dict(numero_orden="OP-2026-001", receta="Pan de molde (v2)", lote="LP-2026-093", unidades=472,
         insumos=3910.0, mano_obra=620.0, indirecto=310.0),
    dict(numero_orden="OP-2026-000", receta="Pan de molde (v1)", lote="LP-2026-085", unidades=455,
         insumos=3870.0, mano_obra=610.0, indirecto=305.0),
    dict(numero_orden="OP-2025-044", receta="Yogur natural (v1)", lote="LP-2026-078", unidades=380,
         insumos=2850.0, mano_obra=540.0, indirecto=270.0),
    dict(numero_orden="OP-2025-045", receta="Galletas de avena (v1)", lote="LP-2026-080", unidades=570,
         insumos=1980.0, mano_obra=480.0, indirecto=240.0),
]


def _cxp(id):
    c = next((c for c in CXP if c["id_cxp"] == id), None)
    if not c:
        abort(404)
    return c


def _estado_cxp(c):
    if c["saldo"] <= 0:
        return "pagada"
    return "vencida" if c["fecha_vencimiento"] < _d(0) else "pendiente"


def _saldos():
    """Saldo de cada cuenta del plan, sumando las líneas de todos los asientos."""
    saldos = {}
    for a in ASIENTOS:
        for cod, debe, haber in a["lineas"]:
            saldos[cod] = saldos.get(cod, 0) + (debe - haber if PLAN[cod][2] == "D" else haber - debe)
    return saldos


# ====================================================================
# RUTAS
# ====================================================================
@finanzas_bp.route("/")
def panel():
    pendientes = [c for c in CXP if c["saldo"] > 0]
    kpis = dict(
        por_pagar="Bs " + _m(sum(c["saldo"] for c in pendientes)),
        vencidas=sum(1 for c in pendientes if _estado_cxp(c) == "vencida"),
        asientos=len(ASIENTOS),
        costo_promedio="Bs " + _m(sum(c["insumos"] + c["mano_obra"] + c["indirecto"] for c in COSTOS)
                                  / sum(c["unidades"] for c in COSTOS)))
    proximas = [dict(proveedor=c["proveedor"], orden_compra=c["orden_compra"], fecha_vencimiento=c["fecha_vencimiento"],
                     saldo=_m(c["saldo"]), estado=_estado_cxp(c))
                for c in sorted(pendientes, key=lambda c: c["fecha_vencimiento"])][:5]
    return _render("contador/panel.html", kpis=kpis, proximas=proximas)


# ------------------------------------------------------------ Cuentas por pagar
@finanzas_bp.route("/cuentas-por-pagar")
def cuentas():
    estado = request.args.get("estado", "")
    filas = []
    for c in sorted(CXP, key=lambda c: c["fecha_vencimiento"]):
        e = _estado_cxp(c)
        if not estado or e == estado:
            filas.append({**c, "estado": e, "monto": _m(c["monto_original"]), "saldo_txt": _m(c["saldo"])})
    return _render("contador/cuentas.html", estado=estado, cuentas=filas, pagos=list(reversed(PAGOS)))


@finanzas_bp.route("/cuentas-por-pagar/<int:id>/pagar", methods=["POST"])
def pagar(id):
    c = _cxp(id)
    monto = request.form.get("monto", type=float) or 0
    if monto <= 0 or monto > c["saldo"] + 0.001:
        flash(f"El monto debe ser mayor que cero y no pasar de Bs {_m(c['saldo'])}.", "error")
    else:
        c["saldo"] = round(c["saldo"] - monto, 2)
        PAGOS.append(dict(fecha=_d(0), proveedor=c["proveedor"], orden_compra=c["orden_compra"], monto=_m(monto),
                          metodo_pago=request.form.get("metodo", "Transferencia"),
                          referencia=request.form.get("referencia") or None))
        _asiento(f"Pago {c['orden_compra']}", "pago_proveedor", [("2.1.01", monto, 0), ("1.1.01", 0, monto)])
        flash("Pago registrado. Se generó el asiento contable.", "ok")
    return redirect(url_for("finanzas.cuentas"))


# ------------------------------------------------------------ Asientos contables
@finanzas_bp.route("/asientos")
def asientos():
    origen = request.args.get("origen", "")
    filas = []
    for a in reversed(ASIENTOS):
        if origen and a["origen"] != origen:
            continue
        total = sum(d for _, d, _ in a["lineas"])
        filas.append({**a, "total": _m(total), "estado": a["estado"],
                      "detalle": [dict(cuenta=f"{cod} · {PLAN[cod][0]}", debe=_m(d) if d else "", haber=_m(h) if h else "")
                                  for cod, d, h in a["lineas"]]})
    origenes = sorted({a["origen"] for a in ASIENTOS})
    return _render("contador/asientos.html", origen=origen, origenes=origenes, asientos=filas)


# ------------------------------------------------------------ Costo de producción
@finanzas_bp.route("/costo-produccion")
def costos():
    buscar = request.args.get("q", "").strip().lower()
    filas, por_receta = [], {}
    for c in COSTOS:
        if buscar and buscar not in c["receta"].lower() and buscar not in c["lote"].lower():
            continue
        total = c["insumos"] + c["mano_obra"] + c["indirecto"]
        filas.append(dict(numero_orden=c["numero_orden"], receta=c["receta"], lote=c["lote"], unidades=c["unidades"],
                          insumos=_m(c["insumos"]), mano_obra=_m(c["mano_obra"]), indirecto=_m(c["indirecto"]),
                          total=_m(total), unitario=_m(total / c["unidades"])))
        r = por_receta.setdefault(c["receta"], [0, 0.0])
        r[0] += c["unidades"]
        r[1] += total
    resumen = [dict(receta=k, unidades=v[0], total=_m(v[1]), unitario=_m(v[1] / v[0])) for k, v in por_receta.items()]
    return _render("contador/costos.html", buscar=buscar, lotes=filas, resumen=resumen)


# ------------------------------------------------------------ Estados financieros
@finanzas_bp.route("/estados-financieros")
def estados():
    reporte = request.args.get("reporte", "balance")
    saldos = _saldos()

    def grupo(tipo):
        return [dict(cuenta=f"{c} · {PLAN[c][0]}", importe=_m(s)) for c, s in sorted(saldos.items())
                if PLAN[c][1] == tipo and abs(s) > 0.004]

    def suma(tipo):
        return sum(s for c, s in saldos.items() if PLAN[c][1] == tipo)

    ingresos, costos_ = suma("ingreso"), suma("costo")
    utilidad = ingresos - costos_
    datos = dict(
        activos=grupo("activo"), total_activos=_m(suma("activo")),
        pasivos=grupo("pasivo"), total_pasivos=_m(suma("pasivo")),
        patrimonio=grupo("patrimonio"), utilidad=_m(utilidad),
        total_pasivo_patrimonio=_m(suma("pasivo") + suma("patrimonio") + utilidad),
        ingresos=grupo("ingreso"), total_ingresos=_m(ingresos),
        costos=grupo("costo"), total_costos=_m(costos_))
    return _render("contador/estados.html", reporte=reporte, **datos)
