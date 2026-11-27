import csv
import io

from flask import abort, make_response, render_template, request

from . import gerente_bp

MENU = [
    ("Panel principal", "gerente.panel", "Resumen ejecutivo"),
    ("Indicadores", "gerente.indicadores", "Desempeño empresarial"),
    ("Producción", "gerente.produccion", "Supervisión de órdenes"),
    ("Inventarios", "gerente.inventarios", "Existencias y alertas"),
    ("Finanzas", "gerente.finanzas", "Ingresos y resultados"),
    ("Reportes", "gerente.reportes", "Informes empresariales"),
]

# Datos de demostración hasta que los módulos operativos se conecten a PostgreSQL.
ORDENES_PRODUCCION = [
    dict(codigo="OP-2026-041", producto="Yogur natural 1L", planificadas=3500,
         producidas=3200, estado="En proceso", responsable="María Flores"),
    dict(codigo="OP-2026-040", producto="Queso fresco 500g", planificadas=1800,
         producidas=1800, estado="Completada", responsable="Carlos Mamani"),
    dict(codigo="OP-2026-039", producto="Pan de molde", planificadas=2400,
         producidas=2050, estado="En proceso", responsable="Silvia Tarqui"),
    dict(codigo="OP-2026-038", producto="Galletas de avena", planificadas=1500,
         producidas=0, estado="Programada", responsable="Juan Condori"),
]

INVENTARIO = [
    dict(item="Leche entera", categoria="Insumo", stock=420, minimo=300, unidad="L", costo=4.2),
    dict(item="Cultivo lácteo", categoria="Insumo", stock=18, minimo=40, unidad="kg", costo=82),
    dict(item="Harina de trigo", categoria="Insumo", stock=95, minimo=120, unidad="kg", costo=6.5),
    dict(item="Envase plástico 1L", categoria="Empaque", stock=160, minimo=250, unidad="unid.", costo=0.85),
    dict(item="Azúcar", categoria="Insumo", stock=210, minimo=100, unidad="kg", costo=5.8),
]

FINANZAS = [
    dict(periodo="2026-08", ingresos=182000, costo_produccion=103500,
         gastos_operativos=35400, cuentas_por_cobrar=24600),
    dict(periodo="2026-09", ingresos=194500, costo_produccion=108200,
         gastos_operativos=36900, cuentas_por_cobrar=28100),
    dict(periodo="2026-10", ingresos=201800, costo_produccion=111600,
         gastos_operativos=38200, cuentas_por_cobrar=26300),
    dict(periodo="2026-11", ingresos=216400, costo_produccion=118300,
         gastos_operativos=40100, cuentas_por_cobrar=31800),
]


def _render(plantilla, **contexto):
    return render_template(plantilla, menu=MENU, rol="Gerencia", **contexto)


def _periodo_seleccionado():
    periodos = [fila["periodo"] for fila in FINANZAS]
    periodo = request.args.get("periodo") or periodos[-1]
    if periodo not in periodos:
        abort(400)
    return periodo


def _resumen_financiero(fila):
    utilidad = fila["ingresos"] - fila["costo_produccion"] - fila["gastos_operativos"]
    margen = round(utilidad / fila["ingresos"] * 100, 1) if fila["ingresos"] else 0
    return {**fila, "utilidad_neta": utilidad, "margen": margen}


def _resumen_inventario():
    filas = []
    for item in INVENTARIO:
        if item["stock"] <= item["minimo"] * 0.5:
            estado = "Crítico"
        elif item["stock"] <= item["minimo"]:
            estado = "Bajo"
        else:
            estado = "Normal"
        filas.append({
            **item,
            "valor": round(item["stock"] * item["costo"], 2),
            "estado": estado,
        })
    return filas


def _resumen_produccion():
    planificadas = sum(fila["planificadas"] for fila in ORDENES_PRODUCCION)
    producidas = sum(fila["producidas"] for fila in ORDENES_PRODUCCION)
    cumplimiento = round(producidas / planificadas * 100, 1) if planificadas else 0
    filas = [
        {
            **fila,
            "cumplimiento": round(fila["producidas"] / fila["planificadas"] * 100, 1)
            if fila["planificadas"] else 0,
        }
        for fila in ORDENES_PRODUCCION
    ]
    return filas, planificadas, producidas, cumplimiento


def _periodos_financieros():
    return [_resumen_financiero(fila) for fila in FINANZAS]


def _resumen_empresa(periodo):
    financieros = next(fila for fila in _periodos_financieros() if fila["periodo"] == periodo)
    inventarios = _resumen_inventario()
    _, planificadas, producidas, cumplimiento = _resumen_produccion()
    return {
        "finanzas": financieros,
        "produccion_planificada": planificadas,
        "produccion_realizada": producidas,
        "cumplimiento_produccion": cumplimiento,
        "valor_inventario": round(sum(item["valor"] for item in inventarios), 2),
        "alertas_inventario": sum(1 for item in inventarios if item["estado"] != "Normal"),
    }


@gerente_bp.route("/")
def panel():
    periodo = FINANZAS[-1]["periodo"]
    resumen = _resumen_empresa(periodo)
    produccion, _, _, _ = _resumen_produccion()
    inventarios = _resumen_inventario()
    return _render(
        "gerente/index.html",
        periodo=periodo,
        resumen=resumen,
        produccion=produccion[:3],
        alertas_inventario=[item for item in inventarios if item["estado"] != "Normal"],
    )


@gerente_bp.route("/indicadores")
def indicadores():
    periodo = _periodo_seleccionado()
    resumen = _resumen_empresa(periodo)
    return _render(
        "gerente/indicadores.html",
        periodo=periodo,
        periodos=_periodos_financieros(),
        resumen=resumen,
    )


@gerente_bp.route("/produccion")
def produccion():
    filas, planificadas, producidas, cumplimiento = _resumen_produccion()
    return _render(
        "gerente/produccion.html",
        ordenes=filas,
        planificadas=planificadas,
        producidas=producidas,
        cumplimiento=cumplimiento,
        en_proceso=sum(1 for fila in filas if fila["estado"] == "En proceso"),
    )


@gerente_bp.route("/inventarios")
def inventarios():
    filas = _resumen_inventario()
    estado = request.args.get("estado", "")
    if estado not in ("", "Crítico", "Bajo", "Normal"):
        abort(400)
    filtrados = [fila for fila in filas if not estado or fila["estado"] == estado]
    return _render(
        "gerente/inventarios.html",
        inventarios=filtrados,
        estado=estado,
        valor_total=round(sum(item["valor"] for item in filas), 2),
        unidades=sum(item["stock"] for item in filas),
        alertas=sum(1 for item in filas if item["estado"] != "Normal"),
        criticos=sum(1 for item in filas if item["estado"] == "Crítico"),
    )


@gerente_bp.route("/finanzas")
def finanzas():
    periodo = _periodo_seleccionado()
    filas = _periodos_financieros()
    resumen = next(fila for fila in filas if fila["periodo"] == periodo)
    return _render(
        "gerente/finanzas.html",
        periodo=periodo,
        finanzas=filas,
        resumen=resumen,
        max_ingresos=max(fila["ingresos"] for fila in filas),
    )


@gerente_bp.route("/reportes")
def reportes():
    periodo = _periodo_seleccionado()
    return _render(
        "gerente/reportes.html",
        periodo=periodo,
        periodos=_periodos_financieros(),
        resumen=_resumen_empresa(periodo),
    )


@gerente_bp.route("/reportes/empresarial.csv")
def reporte_empresarial_csv():
    periodo = _periodo_seleccionado()
    resumen = _resumen_empresa(periodo)
    salida = io.StringIO(newline="")
    escritor = csv.writer(salida)
    escritor.writerow(["Reporte", "Periodo", "Indicador", "Valor", "Unidad"])

    for fila in _periodos_financieros():
        escritor.writerow(["Financiero", fila["periodo"], "Ingresos", fila["ingresos"], "Bs"])
        escritor.writerow(["Financiero", fila["periodo"], "Costo de producción", fila["costo_produccion"], "Bs"])
        escritor.writerow(["Financiero", fila["periodo"], "Gastos operativos", fila["gastos_operativos"], "Bs"])
        escritor.writerow(["Financiero", fila["periodo"], "Utilidad neta", fila["utilidad_neta"], "Bs"])
        escritor.writerow(["Financiero", fila["periodo"], "Margen neto", fila["margen"], "%"])

    escritor.writerow(["Operaciones", periodo, "Producción planificada", resumen["produccion_planificada"], "unidades"])
    escritor.writerow(["Operaciones", periodo, "Producción realizada", resumen["produccion_realizada"], "unidades"])
    escritor.writerow(["Operaciones", periodo, "Cumplimiento de producción", resumen["cumplimiento_produccion"], "%"])
    escritor.writerow(["Inventario", periodo, "Valor de inventario", resumen["valor_inventario"], "Bs"])
    escritor.writerow(["Inventario", periodo, "Alertas de stock", resumen["alertas_inventario"], "ítems"])

    respuesta = make_response("\ufeff" + salida.getvalue())
    respuesta.headers["Content-Type"] = "text/csv; charset=utf-8"
    respuesta.headers["Content-Disposition"] = (
        f"attachment; filename=reporte_empresarial_{periodo}.csv"
    )
    return respuesta
