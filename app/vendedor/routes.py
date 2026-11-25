"""Rutas del rol VENDEDOR con datos simulados (sin base de datos).

Cuando conectes PostgreSQL, reemplaza cada bloque de datos por la consulta
correspondiente; las plantillas esperan exactamente estas claves.
"""
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for

from . import ventas_bp
# Reclamos y trazabilidad se comparten con el rol calidad (mismos datos simulados)
from ..calidad.routes import (actualizar_reclamo, filas_reclamos, reclamo_por_id,
                              traza_adelante, traza_atras)

MENU = [
    ("Panel", "ventas.panel", "Resumen comercial"),
    ("Clientes", "ventas.clientes", "Datos comerciales"),
    ("Pedidos", "ventas.pedidos", "Stock en tiempo real"),
    ("Pedidos en línea", "ventas.pedidos_online", "Confirmar o rechazar"),
    ("Facturas y despachos", "ventas.facturas", "Asigna lotes entregados"),
    ("Cobros", "ventas.cobros", "Pagos de clientes"),
    ("Reclamos", "ventas.reclamos", "Atender con trazabilidad"),
]
IVA = 0.13


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="vendedor", **ctx)


def _d(dias):
    return (date.today() + timedelta(days=dias)).isoformat()


# ====================================================================
# DATOS SIMULADOS
# ====================================================================
CLIENTES = [  # tabla clientes
    dict(id_cliente=1, nit_ci="2000001", razon_social="Distribuidora El Sol", nombre_contacto="Ana Pérez",
         telefono="3333001", email="compras@elsol.bo", direccion="Av. Arce 123, La Paz", limite_credito=50000),
    dict(id_cliente=2, nit_ci="2000002", razon_social="Supermercados Andinos", nombre_contacto="Luis Gómez",
         telefono="3333002", email="compras@superandinos.bo", direccion="Calle 6, Zona Sur", limite_credito=80000),
    dict(id_cliente=3, nit_ci="2000003", razon_social="Tienda Doña Rosa", nombre_contacto="Rosa Flores",
         telefono="3333003", email="rosita@mail.com", direccion="Av. 16 de Julio 456, El Alto", limite_credito=10000),
    dict(id_cliente=4, nit_ci="2000004", razon_social="Mercado Central", nombre_contacto="Pedro Layme",
         telefono="3333004", email="pedrol@mail.com", direccion="Calle Murillo 789, La Paz", limite_credito=15000),
    dict(id_cliente=5, nit_ci="2000005", razon_social="Comercial La Paz SRL", nombre_contacto="María Quispe",
         telefono="3333005", email="compras@comlaps.bo", direccion="Av. Busch 101, La Paz", limite_credito=60000),
    dict(id_cliente=6, nit_ci="2000006", razon_social="Minimarket San Pedro", nombre_contacto="Jorge Mamani",
         telefono="3333006", email="jorgem@mail.com", direccion="Calle 21, Calacoto", limite_credito=8000),
    dict(id_cliente=7, nit_ci="2000007", razon_social="Distribuidora Norte", nombre_contacto="Carmen Rojas",
         telefono="3333007", email="compras@distnorte.bo", direccion="Av. Ballivián 202, El Alto", limite_credito=45000),
    dict(id_cliente=8, nit_ci="2000008", razon_social="Almacén Popular", nombre_contacto="Silvia Ticona",
         telefono="3333008", email="silviat@mail.com", direccion="Calle 8, Obrajes", limite_credito=12000),
]

PRODUCTOS = [  # tabla productos (el stock se calcula desde los lotes)
    dict(id_producto=1, codigo="PROD001", nombre="Yogur natural 1L", precio_venta=12.50),
    dict(id_producto=2, codigo="PROD002", nombre="Queso fresco 500g", precio_venta=25.00),
    dict(id_producto=3, codigo="PROD003", nombre="Pan de molde", precio_venta=15.00),
    dict(id_producto=4, codigo="PROD004", nombre="Galletas de avena", precio_venta=8.00),
    dict(id_producto=5, codigo="PROD005", nombre="Mermelada de fresa", precio_venta=18.00),
    dict(id_producto=6, codigo="PROD006", nombre="Jugo de naranja 1L", precio_venta=14.00),
    dict(id_producto=7, codigo="PROD007", nombre="Papas fritas 200g", precio_venta=10.00),
    dict(id_producto=8, codigo="PROD008", nombre="Avena instantánea", precio_venta=9.00),
    dict(id_producto=9, codigo="PROD009", nombre="Mayonesa 500g", precio_venta=16.00),
    dict(id_producto=10, codigo="PROD010", nombre="Chocolate en barra", precio_venta=7.00),
]

LOTES = [  # lotes_productos aprobados ('disponible') y no vencidos
    dict(id_lote_producto=1, numero_lote="LP-2026-098", id_producto=4, fecha_vencimiento=_d(50), cantidad_actual=110),
    dict(id_lote_producto=2, numero_lote="LP-2026-099", id_producto=5, fecha_vencimiento=_d(170), cantidad_actual=55),
    dict(id_lote_producto=3, numero_lote="LP-2026-100", id_producto=6, fecha_vencimiento=_d(7), cantidad_actual=95),
    dict(id_lote_producto=4, numero_lote="LP-2026-095", id_producto=9, fecha_vencimiento=_d(160), cantidad_actual=38),
    dict(id_lote_producto=5, numero_lote="LP-2026-096", id_producto=1, fecha_vencimiento=_d(12), cantidad_actual=70),
    dict(id_lote_producto=6, numero_lote="LP-2026-097", id_producto=1, fecha_vencimiento=_d(24), cantidad_actual=40),
    dict(id_lote_producto=7, numero_lote="LP-2026-094", id_producto=2, fecha_vencimiento=_d(9), cantidad_actual=45),
    dict(id_lote_producto=8, numero_lote="LP-2026-093", id_producto=3, fecha_vencimiento=_d(4), cantidad_actual=60),
    dict(id_lote_producto=9, numero_lote="LP-2026-092", id_producto=8, fecha_vencimiento=_d(300), cantidad_actual=20),
    dict(id_lote_producto=10, numero_lote="LP-2026-091", id_producto=10, fecha_vencimiento=_d(200), cantidad_actual=79),
]

PEDIDOS, FACTURAS, ASIGNADOS, PAGOS = [], [], {}, []


def _producto(id):
    return next(p for p in PRODUCTOS if p["id_producto"] == id)


def _cliente(id):
    return next((c for c in CLIENTES if c["id_cliente"] == id), None)


def _stock(id_producto):
    return sum(l["cantidad_actual"] for l in LOTES
               if l["id_producto"] == id_producto and l["fecha_vencimiento"] >= _d(0))


def _crear_pedido(id_cliente, origen, estado, lineas, dias=0, entrega=None, obs=None):
    sub = round(sum(_producto(i)["precio_venta"] * c for i, c in lineas), 2)
    imp = round(sub * IVA, 2)
    n = len(PEDIDOS) + 1
    p = dict(id_pedido=n, numero_pedido=f"PED-{date.today().year}-{n:03d}", id_cliente=id_cliente,
             origen=origen, estado=estado, lineas=lineas, fecha=_d(dias), fecha_pedido=_d(dias),
             fecha_entrega_estimada=entrega or _d(dias + 3), subtotal=sub, impuestos=imp,
             total=round(sub + imp, 2), observacion=obs)
    PEDIDOS.append(p)
    return p


def _crear_factura(pedido, dias, estado="emitida", saldo=None, despacho=None, transportista=None):
    n = len(FACTURAS) + 1
    f = dict(id_factura=n, numero_factura=f"FAC-{date.today().year}-{n:03d}", id_pedido=pedido["id_pedido"],
             id_cliente=pedido["id_cliente"], fecha=_d(dias), total=pedido["total"], estado=estado,
             saldo_pendiente=pedido["total"] if saldo is None else saldo, despacho=despacho,
             numero_nota=f"ND-{date.today().year}-{n:03d}" if despacho else None,
             transportista=transportista)
    FACTURAS.append(f)
    return f


# --- pedidos, facturas y pagos de ejemplo
_p1 = _crear_pedido(1, "vendedor", "entregado", [(1, 10), (2, 5)], dias=-45)
_p2 = _crear_pedido(2, "vendedor", "despachado", [(3, 20)], dias=-40)
_crear_pedido(3, "vendedor", "confirmado", [(4, 30), (5, 10)], dias=-2)
_crear_pedido(4, "vendedor", "confirmado", [(6, 12)], dias=-1)
_crear_pedido(5, "portal", "pendiente", [(1, 15), (9, 6)])
_crear_pedido(6, "portal", "pendiente", [(8, 50)])          # stock insuficiente a propósito
_crear_pedido(7, "vendedor", "pendiente", [(2, 8)])
_crear_pedido(8, "portal", "rechazado", [(5, 3)], dias=-6, obs="Cliente sin crédito disponible")
_p9 = _crear_pedido(2, "vendedor", "confirmado", [(1, 20)], dias=-5)

_f1 = _crear_factura(_p1, -45, "pagada", 0, "entregada", "TransBolivia")
_f2 = _crear_factura(_p2, -40, "emitida", _p2["total"] - 100, "en_ruta", "Moto Express")
_f3 = _crear_factura(_p9, -5)
ASIGNADOS[_p1["id_pedido"]] = [
    dict(producto="Yogur natural 1L", numero_lote="LP-2026-080", cantidad=10, fecha_vencimiento=_d(-20)),
    dict(producto="Queso fresco 500g", numero_lote="LP-2026-081", cantidad=5, fecha_vencimiento=_d(-25))]
ASIGNADOS[_p2["id_pedido"]] = [
    dict(producto="Pan de molde", numero_lote="LP-2026-089", cantidad=20, fecha_vencimiento=_d(-30))]
PAGOS += [
    dict(fecha=_d(-44), cliente="Distribuidora El Sol", numero_factura=_f1["numero_factura"],
         monto=_f1["total"], metodo_pago="Transferencia", referencia="REC-001"),
    dict(fecha=_d(-20), cliente="Supermercados Andinos", numero_factura=_f2["numero_factura"],
         monto=100.0, metodo_pago="Efectivo", referencia="REC-002")]


# --- vistas combinadas (lo que devolverían los JOIN)
def _vista_pedido(p):
    fac = next((f for f in FACTURAS if f["id_pedido"] == p["id_pedido"]), None)
    return {**p, "cliente": _cliente(p["id_cliente"])["razon_social"], "entrega": p["fecha_entrega_estimada"],
            "id_factura": fac["id_factura"] if fac else None,
            "numero_factura": fac["numero_factura"] if fac else None}


def _pedido(id):
    p = next((p for p in PEDIDOS if p["id_pedido"] == id), None)
    if not p:
        abort(404)
    return p


def _factura(id):
    f = next((f for f in FACTURAS if f["id_factura"] == id), None)
    if not f:
        abort(404)
    return f


def _vista_factura(f):
    p = _pedido(f["id_pedido"])
    return {**f, "fecha_emision": f["fecha"], "cliente": _cliente(f["id_cliente"])["razon_social"],
            "numero_pedido": p["numero_pedido"], "id_nota": f["id_factura"] if f["despacho"] else None}


def _lineas(p):
    return [dict(id_producto=i, codigo=_producto(i)["codigo"], producto=_producto(i)["nombre"], cantidad=c,
                 precio_unitario=_producto(i)["precio_venta"], subtotal=round(_producto(i)["precio_venta"] * c, 2))
            for i, c in p["lineas"]]


def _cobros():
    filas = []
    for f in FACTURAS:
        if f["saldo_pendiente"] > 0:
            venc = date.fromisoformat(f["fecha"]) + timedelta(days=30)
            filas.append(dict(id_cxc=f["id_factura"], numero_factura=f["numero_factura"],
                              cliente=_cliente(f["id_cliente"])["razon_social"], fecha_vencimiento=venc.isoformat(),
                              dias_mora=max((date.today() - venc).days, 0), saldo=round(f["saldo_pendiente"], 2)))
    return sorted(filas, key=lambda x: x["fecha_vencimiento"])


# ====================================================================
# RUTAS
# ====================================================================
@ventas_bp.route("/")
def panel():
    kpis = dict(
        pedidos_pendientes=sum(1 for p in PEDIDOS if p["estado"] == "pendiente" and p["origen"] == "vendedor"),
        online_pendientes=sum(1 for p in PEDIDOS if p["estado"] == "pendiente" and p["origen"] == "portal"),
        por_cobrar=sum(f["saldo_pendiente"] for f in FACTURAS),
        reclamos_abiertos=sum(1 for r in filas_reclamos() if r["estado"] in ("abierto", "en_revision")))
    recientes = [_vista_pedido(p) for p in reversed(PEDIDOS)][:6]
    return _render("vendedor/panel.html", kpis=kpis, recientes=recientes)


# ------------------------------------------------------------ Clientes
@ventas_bp.route("/clientes")
def clientes():
    buscar = request.args.get("q", "").strip()
    filas = []
    for c in CLIENTES:
        if buscar.lower() in c["razon_social"].lower() or buscar in c["nit_ci"]:
            saldo = sum(f["saldo_pendiente"] for f in FACTURAS if f["id_cliente"] == c["id_cliente"])
            filas.append({**c, "saldo_pendiente": round(saldo, 2)})
    return _render("vendedor/clientes.html", buscar=buscar, clientes=filas)


def _datos_cliente():
    f = request.form
    return dict(nit_ci=f.get("nit_ci", "").strip() or None, razon_social=f.get("razon_social", "").strip(),
                nombre_contacto=f.get("nombre_contacto") or None, telefono=f.get("telefono") or None,
                email=f.get("email") or None, direccion=f.get("direccion") or None,
                limite_credito=float(f.get("limite_credito") or 0))


@ventas_bp.route("/clientes/nuevo", methods=["GET", "POST"])
def cliente_nuevo():
    if request.method == "POST":
        datos = _datos_cliente()
        if not datos["razon_social"]:
            flash("Escribe la razón social del cliente.", "error")
            return _render("vendedor/cliente_form.html", c=datos)
        CLIENTES.append(dict(id_cliente=len(CLIENTES) + 1, **datos))
        flash("Cliente creado.", "ok")
        return redirect(url_for("ventas.clientes"))
    return _render("vendedor/cliente_form.html", c={})


@ventas_bp.route("/clientes/<int:id>/editar", methods=["GET", "POST"])
def cliente_editar(id):
    c = _cliente(id)
    if not c:
        abort(404)
    if request.method == "POST":
        c.update(_datos_cliente())
        flash("Cliente actualizado.", "ok")
        return redirect(url_for("ventas.clientes"))
    return _render("vendedor/cliente_form.html", c=c, id=id)


# ------------------------------------------------------------ Pedidos
@ventas_bp.route("/pedidos")
def pedidos():
    estado = request.args.get("estado", "")
    filas = [_vista_pedido(p) for p in reversed(PEDIDOS) if not estado or p["estado"] == estado]
    return _render("vendedor/pedidos.html", estado=estado, pedidos=filas)


@ventas_bp.route("/pedidos/nuevo", methods=["GET", "POST"])
def pedido_nuevo():
    productos = [{**p, "stock": _stock(p["id_producto"])} for p in PRODUCTOS]
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
        if not _cliente(id_cliente):
            errores.append("Elige un cliente.")
        if not lineas:
            errores.append("Agrega al menos un producto.")
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            p = _crear_pedido(id_cliente, "vendedor", "confirmado", lineas,
                              entrega=request.form.get("entrega") or None,
                              obs=request.form.get("observacion") or None)
            flash("Pedido registrado.", "ok")
            return redirect(url_for("ventas.pedido_detalle", id=p["id_pedido"]))
    return _render("vendedor/pedido_nuevo.html", productos=productos, clientes=CLIENTES, iva=IVA,
                   manana=date.today() + timedelta(days=1))


@ventas_bp.route("/pedidos/<int:id>")
def pedido_detalle(id):
    p = _pedido(id)
    return _render("vendedor/pedido_detalle.html", p=_vista_pedido(p), lineas=_lineas(p))


# ------------------------------------------------------------ Pedidos en línea
@ventas_bp.route("/pedidos-en-linea")
def pedidos_online():
    filas = []
    for p in PEDIDOS:
        if p["origen"] == "portal" and p["estado"] == "pendiente":
            lineas = [dict(producto=l["producto"], cantidad=l["cantidad"], stock=_stock(l["id_producto"]))
                      for l in _lineas(p)]
            filas.append({**_vista_pedido(p), "lineas": lineas,
                          "hay_stock": all(l["stock"] >= l["cantidad"] for l in lineas)})
    return _render("vendedor/pedidos_online.html", pedidos=filas)


@ventas_bp.route("/pedidos-en-linea/<int:id>/<accion>", methods=["POST"])
def resolver_pedido_online(id, accion):
    if accion not in ("confirmar", "rechazar"):
        abort(404)
    p = _pedido(id)
    if accion == "confirmar" and any(_stock(i) < c for i, c in p["lineas"]):
        flash("No hay stock suficiente para confirmar este pedido.", "error")
    elif accion == "rechazar" and not request.form.get("motivo", "").strip():
        flash("Escribe el motivo del rechazo.", "error")
    else:
        p["estado"] = "confirmado" if accion == "confirmar" else "rechazado"
        p["observacion"] = request.form.get("motivo") or p["observacion"]
        flash(f"Pedido {p['estado']}.", "ok")
    return redirect(url_for("ventas.pedidos_online"))


# ------------------------------------------------------------ Facturas y despachos
@ventas_bp.route("/facturas")
def facturas():
    filas = [dict(_vista_factura(f), fecha=f["fecha"]) for f in reversed(FACTURAS)]
    facturados = {f["id_pedido"] for f in FACTURAS}
    por_facturar = [dict(id_pedido=p["id_pedido"], numero_pedido=p["numero_pedido"],
                         cliente=_cliente(p["id_cliente"])["razon_social"], total=p["total"])
                    for p in PEDIDOS if p["estado"] == "confirmado" and p["id_pedido"] not in facturados]
    return _render("vendedor/facturas.html", facturas=filas, por_facturar=por_facturar)


@ventas_bp.route("/facturas/emitir/<int:id_pedido>", methods=["POST"])
def emitir_factura(id_pedido):
    p = _pedido(id_pedido)
    if any(f["id_pedido"] == id_pedido for f in FACTURAS):
        flash("Ese pedido ya tiene factura.", "error")
        return redirect(url_for("ventas.facturas"))
    f = _crear_factura(p, 0)
    flash("Factura emitida. Ahora asigna los lotes.", "ok")
    return redirect(url_for("ventas.factura_detalle", id=f["id_factura"]))


def _candidatos(pedido):
    ids = {i for i, _ in pedido["lineas"]}
    lotes = [dict(l, producto=_producto(l["id_producto"])["nombre"]) for l in LOTES
             if l["id_producto"] in ids and l["cantidad_actual"] > 0 and l["fecha_vencimiento"] >= _d(0)]
    return sorted(lotes, key=lambda l: (l["producto"], l["fecha_vencimiento"]))  # primero el que vence antes


@ventas_bp.route("/facturas/<int:id>")
def factura_detalle(id):
    f = _factura(id)
    p = _pedido(f["id_pedido"])
    return _render("vendedor/factura_detalle.html", f=_vista_factura(f), lineas=_lineas(p),
                   asignados=ASIGNADOS.get(p["id_pedido"], []), candidatos=_candidatos(p))


@ventas_bp.route("/facturas/<int:id>/asignar-lotes", methods=["POST"])
def asignar_lotes(id):
    f = _factura(id)
    p = _pedido(f["id_pedido"])
    elegidos = []
    for l in _candidatos(p):
        cant = request.form.get(f"lote_{l['id_lote_producto']}", type=int) or 0
        if cant <= 0:
            continue
        if cant > l["cantidad_actual"]:
            flash(f"Lote {l['numero_lote']}: solo quedan {l['cantidad_actual']}.", "error")
            return redirect(url_for("ventas.factura_detalle", id=id))
        elegidos.append((l, cant))
    if not elegidos:
        flash("Indica la cantidad de al menos un lote.", "error")
        return redirect(url_for("ventas.factura_detalle", id=id))
    for l, cant in elegidos:  # descuenta stock (en la BD lo hace el trigger)
        l["cantidad_actual"] -= cant
        ASIGNADOS.setdefault(p["id_pedido"], []).append(dict(
            producto=l["producto"], numero_lote=l["numero_lote"], cantidad=cant,
            fecha_vencimiento=l["fecha_vencimiento"]))
    f["despacho"] = "emitida"
    f["numero_nota"] = f"ND-{date.today().year}-{f['id_factura']:03d}"
    f["transportista"] = request.form.get("transportista") or None
    p["estado"] = "despachado"
    flash("Lotes asignados y despacho registrado.", "ok")
    return redirect(url_for("ventas.factura_detalle", id=id))


@ventas_bp.route("/facturas/<int:id>/entregado", methods=["POST"])
def marcar_entregado(id):
    f = _factura(id)
    if not f["despacho"]:
        abort(404)
    f["despacho"] = "entregada"
    _pedido(f["id_pedido"])["estado"] = "entregado"
    flash("Entrega confirmada.", "ok")
    return redirect(url_for("ventas.factura_detalle", id=id))


# ------------------------------------------------------------ Cobros
@ventas_bp.route("/cobros")
def cobros():
    return _render("vendedor/cobros.html", cobros=_cobros(), pagos=PAGOS[:10])


@ventas_bp.route("/cobros/<int:id_cxc>/pago", methods=["POST"])
def registrar_pago(id_cxc):
    f = _factura(id_cxc)
    monto = request.form.get("monto", type=float) or 0
    if monto <= 0 or monto > f["saldo_pendiente"] + 0.001:
        flash(f"El pago debe ser mayor que 0 y no superar el saldo ({f['saldo_pendiente']:.2f}).", "error")
        return redirect(url_for("ventas.cobros"))
    f["saldo_pendiente"] = round(f["saldo_pendiente"] - monto, 2)
    if f["saldo_pendiente"] <= 0:
        f["estado"] = "pagada"
    PAGOS.insert(0, dict(fecha=_d(0), cliente=_cliente(f["id_cliente"])["razon_social"],
                         numero_factura=f["numero_factura"], monto=monto,
                         metodo_pago=request.form.get("metodo"), referencia=request.form.get("referencia") or None))
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
