from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import abort, flash, redirect, render_template, request, url_for
from psycopg2.extras import RealDictCursor

from app.database import obtener_conexion
from . import compras_bp


MENU = [
    ("Panel principal", "compras.panel", "Indicadores y alertas"),
    ("Solicitudes", "compras.solicitudes", "Revisión y aprobación"),
    ("Órdenes de compra", "compras.ordenes", "Creación y consulta"),
    ("Proveedores", "compras.proveedores", "Registro y administración"),
    ("Cotizaciones", "compras.cotizaciones", "Comparación de precios históricos"),
    ("Seguimiento", "compras.seguimiento", "Control de entregas"),
]


@contextmanager
def _conexion():
    conexion = obtener_conexion()
    if conexion is None:
        abort(503, description="No fue posible conectar con la base de datos de compras.")
    try:
        yield conexion
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


def _filas(conexion, consulta, parametros=()):
    with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(consulta, parametros)
        return [dict(fila) for fila in cursor.fetchall()]


def _fila(conexion, consulta, parametros=()):
    with conexion.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(consulta, parametros)
        resultado = cursor.fetchone()
        return dict(resultado) if resultado else None


def _render(plantilla, **contexto):
    return render_template(plantilla, menu=MENU, rol="Comprador", **contexto)


def _decimal(valor, etiqueta, minimo=Decimal("0"), maximo=None):
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, f"El valor de {etiqueta} no es numérico."
    if not numero.is_finite() or numero <= minimo or (maximo is not None and numero > maximo):
        return None, f"El valor de {etiqueta} debe ser mayor que cero y estar dentro del límite permitido."
    return numero, None


def _dinero(valor):
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _insumos(conexion):
    return _filas(
        conexion,
        """
        SELECT i.id_insumo AS id, i.nombre, COALESCE(u.abreviatura, '') AS unidad,
               i.stock_minimo, i.activo
        FROM insumos i
        LEFT JOIN unidades_medida u ON u.id_unidad = i.id_unidad
        WHERE i.activo = TRUE
        ORDER BY i.nombre
        """,
    )


def _proveedores(conexion, solo_activos=False):
    consulta = """
        SELECT id_proveedor AS id, nit, razon_social, nombre_contacto AS contacto,
               telefono, email, direccion, condiciones_comerciales AS condiciones,
               calificacion, activo, fecha_registro
        FROM proveedores
    """
    if solo_activos:
        consulta += " WHERE activo = TRUE"
    consulta += " ORDER BY razon_social"
    return _filas(conexion, consulta)


def _proveedor(conexion, id_proveedor):
    proveedor = _fila(
        conexion,
        """
        SELECT id_proveedor AS id, nit, razon_social, nombre_contacto AS contacto,
               telefono, email, direccion, condiciones_comerciales AS condiciones,
               calificacion, activo, fecha_registro
        FROM proveedores
        WHERE id_proveedor = %s
        """,
        (id_proveedor,),
    )
    if proveedor is None:
        abort(404)
    return proveedor


def _solicitud(conexion, id_solicitud):
    solicitud = _fila(
        conexion,
        """
        SELECT s.id_solicitud AS id, s.numero_solicitud AS numero,
               s.id_usuario_solicita, s.fecha_solicitud::date AS fecha,
               s.estado, s.observacion,
               u.nombre_completo AS solicitante,
               o.id_orden_compra AS orden_id, o.numero_orden
        FROM solicitudes_compra s
        LEFT JOIN usuarios u ON u.id_usuario = s.id_usuario_solicita
        LEFT JOIN ordenes_compra o ON o.id_solicitud = s.id_solicitud
        WHERE s.id_solicitud = %s
        """,
        (id_solicitud,),
    )
    if solicitud is None:
        abort(404)
    solicitud["solicitante"] = solicitud["solicitante"] or "No especificado"
    solicitud["items"] = _filas(
        conexion,
        """
        SELECT d.id_insumo AS insumo_id, d.cantidad,
               i.nombre AS nombre_insumo, COALESCE(u.abreviatura, '') AS unidad
        FROM solicitud_compra_detalle d
        JOIN insumos i ON i.id_insumo = d.id_insumo
        LEFT JOIN unidades_medida u ON u.id_unidad = i.id_unidad
        WHERE d.id_solicitud = %s
        ORDER BY d.id_detalle
        """,
        (id_solicitud,),
    )
    return solicitud


def _solicitudes(conexion, estado=None):
    consulta = """
        SELECT s.id_solicitud AS id, s.numero_solicitud AS numero,
               s.id_usuario_solicita, s.fecha_solicitud::date AS fecha,
               s.estado, s.observacion,
               u.nombre_completo AS solicitante,
               o.id_orden_compra AS orden_id, o.numero_orden
        FROM solicitudes_compra s
        LEFT JOIN usuarios u ON u.id_usuario = s.id_usuario_solicita
        LEFT JOIN ordenes_compra o ON o.id_solicitud = s.id_solicitud
    """
    parametros = ()
    if estado:
        consulta += " WHERE s.estado = %s"
        parametros = (estado,)
    consulta += " ORDER BY s.fecha_solicitud DESC, s.id_solicitud DESC"
    solicitudes = _filas(conexion, consulta, parametros)
    for solicitud in solicitudes:
        solicitud["solicitante"] = solicitud["solicitante"] or "No especificado"
        solicitud["items"] = _filas(
            conexion,
            """
            SELECT d.id_insumo AS insumo_id, d.cantidad,
                   i.nombre AS nombre_insumo, COALESCE(u.abreviatura, '') AS unidad
            FROM solicitud_compra_detalle d
            JOIN insumos i ON i.id_insumo = d.id_insumo
            LEFT JOIN unidades_medida u ON u.id_unidad = i.id_unidad
            WHERE d.id_solicitud = %s
            ORDER BY d.id_detalle
            """,
            (solicitud["id"],),
        )
    return solicitudes


def _cantidad_recibida(conexion, id_orden, id_insumo=None):
    consulta = """
        SELECT COALESCE(SUM(r.cantidad_recibida), 0) AS cantidad
        FROM recepciones_compra r
        JOIN lotes_insumos l ON l.id_lote_insumo = r.id_lote_insumo
        WHERE r.id_orden_compra = %s
    """
    parametros = [id_orden]
    if id_insumo is not None:
        consulta += " AND l.id_insumo = %s"
        parametros.append(id_insumo)
    resultado = _fila(conexion, consulta, tuple(parametros))
    return resultado["cantidad"]


def _enriquecer_entrega(conexion, orden):
    lineas = []
    for item in orden["items"]:
        recibida = _cantidad_recibida(conexion, orden["id"], item["insumo_id"])
        lineas.append({
            **item,
            "recibida": recibida,
            "pendiente": max(item["cantidad"] - recibida, Decimal("0")),
        })
    recibida_total = sum((item["recibida"] for item in lineas), Decimal("0"))
    pendiente_total = sum((item["pendiente"] for item in lineas), Decimal("0"))
    fecha_entrega = orden["fecha_entrega_esperada"]
    if isinstance(fecha_entrega, datetime):
        fecha_entrega = fecha_entrega.date()
    elif isinstance(fecha_entrega, str):
        fecha_entrega = date.fromisoformat(fecha_entrega)
    atrasada = (
        orden["estado"] not in ("recibida", "anulada")
        and fecha_entrega is not None
        and fecha_entrega < date.today()
    )
    return {
        **orden,
        "items_seguimiento": lineas,
        "recibida": recibida_total,
        "pendiente": pendiente_total,
        "atrasada": atrasada,
    }


def _ordenes(conexion, estado=None, id_orden=None):
    consulta = """
        SELECT o.id_orden_compra AS id, o.numero_orden AS numero,
               o.id_proveedor AS proveedor_id, p.razon_social AS proveedor,
               o.id_solicitud AS solicitud_id, s.numero_solicitud,
               o.fecha_emision, o.fecha_entrega_esperada, o.estado,
               o.subtotal, o.impuestos, o.total, o.observacion,
               CASE WHEN o.subtotal > 0 THEN o.impuestos / o.subtotal * 100
                    ELSE 0 END AS impuesto_porcentaje
        FROM ordenes_compra o
        JOIN proveedores p ON p.id_proveedor = o.id_proveedor
        LEFT JOIN solicitudes_compra s ON s.id_solicitud = o.id_solicitud
    """
    condiciones = []
    parametros = []
    if estado:
        condiciones.append("o.estado = %s")
        parametros.append(estado)
    if id_orden is not None:
        condiciones.append("o.id_orden_compra = %s")
        parametros.append(id_orden)
    if condiciones:
        consulta += " WHERE " + " AND ".join(condiciones)
    consulta += " ORDER BY o.fecha_emision DESC, o.id_orden_compra DESC"
    ordenes = _filas(conexion, consulta, tuple(parametros))
    if not ordenes:
        return []
    ids = [orden["id"] for orden in ordenes]
    detalles = _filas(
        conexion,
        """
        SELECT d.id_orden_compra AS orden_id, d.id_insumo AS insumo_id,
               i.nombre AS nombre_insumo, COALESCE(u.abreviatura, '') AS unidad,
               d.cantidad, d.precio_unitario, d.subtotal
        FROM orden_compra_detalle d
        JOIN insumos i ON i.id_insumo = d.id_insumo
        LEFT JOIN unidades_medida u ON u.id_unidad = i.id_unidad
        WHERE d.id_orden_compra = ANY(%s)
        ORDER BY d.id_detalle
        """,
        (ids,),
    )
    por_orden = {id_item: [] for id_item in ids}
    for detalle in detalles:
        por_orden[detalle["orden_id"]].append({
            "insumo_id": detalle["insumo_id"],
            "nombre_insumo": detalle["nombre_insumo"],
            "unidad": detalle["unidad"],
            "cantidad": detalle["cantidad"],
            "precio_unitario": detalle["precio_unitario"],
            "subtotal": detalle["subtotal"],
        })
    for orden in ordenes:
        orden["items"] = por_orden[orden["id"]]
        orden.update(_enriquecer_entrega(conexion, orden))
    return ordenes


def _orden(conexion, id_orden):
    ordenes = _ordenes(conexion, id_orden=id_orden)
    if not ordenes:
        abort(404)
    return ordenes[0]


def _insumos_bajo_minimo(conexion):
    return _filas(
        conexion,
        """
        SELECT i.id_insumo AS id, i.nombre, COALESCE(u.abreviatura, '') AS unidad,
               i.stock_minimo,
               COALESCE(SUM(CASE WHEN l.estado = 'disponible'
                                 THEN l.cantidad_actual ELSE 0 END), 0) AS stock_actual
        FROM insumos i
        LEFT JOIN unidades_medida u ON u.id_unidad = i.id_unidad
        LEFT JOIN lotes_insumos l ON l.id_insumo = i.id_insumo
        WHERE i.activo = TRUE
        GROUP BY i.id_insumo, i.nombre, u.abreviatura, i.stock_minimo
        HAVING COALESCE(SUM(CASE WHEN l.estado = 'disponible'
                                 THEN l.cantidad_actual ELSE 0 END), 0) < i.stock_minimo
        ORDER BY i.nombre
        """,
    )


def _precios_historicos(conexion, insumo_id=None, limite=None):
    consulta = """
        SELECT d.id_detalle AS id, d.id_insumo AS insumo_id,
               i.nombre AS insumo, COALESCE(u.abreviatura, '') AS unidad,
               d.cantidad, d.precio_unitario, o.id_orden_compra AS orden_id,
               o.numero_orden AS numero_orden, o.fecha_emision AS fecha,
               o.id_proveedor AS proveedor_id, p.razon_social AS proveedor,
               'histórico' AS estado_vista
        FROM orden_compra_detalle d
        JOIN ordenes_compra o ON o.id_orden_compra = d.id_orden_compra
        JOIN proveedores p ON p.id_proveedor = o.id_proveedor
        JOIN insumos i ON i.id_insumo = d.id_insumo
        LEFT JOIN unidades_medida u ON u.id_unidad = i.id_unidad
        WHERE o.estado <> 'anulada'
    """
    parametros = []
    if insumo_id is not None:
        consulta += " AND d.id_insumo = %s"
        parametros.append(insumo_id)
    consulta += " ORDER BY o.fecha_emision DESC, d.id_detalle DESC"
    if limite is not None:
        consulta += " LIMIT %s"
        parametros.append(limite)
    return _filas(conexion, consulta, tuple(parametros))


def _parsear_lineas(formulario, insumos):
    insumos_raw = formulario.getlist("insumo_id")
    cantidades = formulario.getlist("cantidad")
    precios = formulario.getlist("precio_unitario")
    if not (len(insumos_raw) == len(cantidades) == len(precios)):
        return None, "Revisa las líneas de insumos de la orden."

    disponibles = {insumo["id"]: insumo for insumo in insumos}
    agregados = set()
    lineas = []
    for id_raw, cantidad_raw, precio_raw in zip(insumos_raw, cantidades, precios):
        if not id_raw and not cantidad_raw and not precio_raw:
            continue
        if not id_raw or not cantidad_raw or not precio_raw:
            return None, "Completa insumo, cantidad y precio en cada línea."
        try:
            id_insumo = int(id_raw)
        except ValueError:
            return None, "Selecciona un insumo válido."
        insumo = disponibles.get(id_insumo)
        if insumo is None:
            return None, "El insumo seleccionado no está activo o no existe."
        if id_insumo in agregados:
            return None, "No repitas un insumo en la orden; suma sus cantidades en una sola línea."
        agregados.add(id_insumo)
        cantidad, error = _decimal(
            cantidad_raw, "cantidad", maximo=Decimal("999999999.999")
        )
        if error:
            return None, error
        precio, error = _decimal(
            precio_raw, "precio unitario", maximo=Decimal("99999999.9999")
        )
        if error:
            return None, error
        lineas.append({
            "insumo_id": id_insumo,
            "nombre_insumo": insumo["nombre"],
            "unidad": insumo["unidad"],
            "cantidad": cantidad,
            "precio_unitario": precio,
            "subtotal": _dinero(cantidad * precio),
        })
    if not lineas:
        return None, "Agrega al menos un insumo a la orden."
    return lineas, None


def _validar_orden(conexion, formulario, insumos, id_orden=None):
    datos = {
        "proveedor_id": formulario.get("proveedor_id", ""),
        "solicitud_id": formulario.get("solicitud_id", ""),
        "fecha_entrega_esperada": formulario.get("fecha_entrega_esperada", ""),
        "impuesto_porcentaje": formulario.get("impuesto_porcentaje", "0"),
        "observacion": formulario.get("observacion", "").strip(),
        "lineas_form": [
            dict(insumo_id=i, cantidad=c, precio_unitario=p)
            for i, c, p in zip(
                formulario.getlist("insumo_id"),
                formulario.getlist("cantidad"),
                formulario.getlist("precio_unitario"),
            )
        ],
    }
    try:
        proveedor_id = int(datos["proveedor_id"])
    except ValueError:
        return datos, None, "Selecciona un proveedor válido."
    proveedor = _fila(
        conexion,
        "SELECT id_proveedor, activo FROM proveedores WHERE id_proveedor = %s",
        (proveedor_id,),
    )
    proveedor_anterior = _orden(conexion, id_orden)["proveedor_id"] if id_orden else None
    if proveedor is None or (
        not proveedor["activo"]
        and (id_orden is None or proveedor_anterior != proveedor_id)
    ):
        return datos, None, "El proveedor seleccionado no está activo."

    solicitud = None
    if datos["solicitud_id"]:
        try:
            solicitud_id = int(datos["solicitud_id"])
        except ValueError:
            return datos, None, "Selecciona una solicitud válida."
        solicitud = _solicitud(conexion, solicitud_id)
        solicitud_permitida = (
            solicitud["estado"] == "aprobada"
            or (
                id_orden is not None
                and solicitud["estado"] == "atendida"
                and solicitud.get("orden_id") == id_orden
            )
        )
        if not solicitud_permitida:
            return datos, None, "Solo se pueden asociar solicitudes aprobadas."

    try:
        fecha_entrega = date.fromisoformat(datos["fecha_entrega_esperada"])
    except ValueError:
        return datos, None, "Selecciona una fecha de entrega válida."
    if len(datos["observacion"]) > 500:
        return datos, None, "La observación no debe superar 500 caracteres."
    impuesto, error = _decimal(
        datos["impuesto_porcentaje"], "porcentaje de impuesto",
        minimo=Decimal("-0.01"), maximo=Decimal("100"),
    )
    if error:
        return datos, None, "El impuesto debe ser un porcentaje entre 0 y 100."
    lineas, error = _parsear_lineas(formulario, insumos)
    if error:
        return datos, None, error
    if solicitud:
        requeridos = {
            item["insumo_id"]: item["cantidad"] for item in solicitud["items"]
        }
        pedidos = {item["insumo_id"]: item["cantidad"] for item in lineas}
        if any(
            pedidos.get(id_insumo, Decimal("0")) < cantidad
            for id_insumo, cantidad in requeridos.items()
        ):
            return datos, None, "La orden debe cubrir la cantidad solicitada para cada insumo."
    if id_orden is not None and _cantidad_recibida(conexion, id_orden):
        return datos, None, "No se puede modificar una orden que ya tiene entregas registradas."

    subtotal = _dinero(sum((item["subtotal"] for item in lineas), Decimal("0")))
    impuestos = _dinero(subtotal * impuesto / Decimal("100"))
    datos.update({
        "proveedor_id": proveedor_id,
        "solicitud_id": solicitud["id"] if solicitud else None,
        "fecha_entrega_esperada": fecha_entrega,
        "impuesto_porcentaje": impuesto,
        "lineas": lineas,
        "subtotal": subtotal,
        "impuestos": impuestos,
        "total": subtotal + impuestos,
    })
    return datos, solicitud, None


def _orden_formulario(formulario):
    return {
        "proveedor_id": formulario.get("proveedor_id", ""),
        "solicitud_id": formulario.get("solicitud_id", ""),
        "fecha_entrega_esperada": formulario.get("fecha_entrega_esperada", ""),
        "impuesto_porcentaje": formulario.get("impuesto_porcentaje", "13"),
        "observacion": formulario.get("observacion", ""),
        "items": [
            dict(insumo_id=i, cantidad=c, precio_unitario=p)
            for i, c, p in zip(
                formulario.getlist("insumo_id"),
                formulario.getlist("cantidad"),
                formulario.getlist("precio_unitario"),
            )
        ],
    }


def _solicitudes_activas(conexion, id_orden=None):
    solicitudes = _solicitudes(conexion, estado="aprobada")
    if id_orden is not None:
        orden = _orden(conexion, id_orden)
        if orden["solicitud_id"]:
            vinculada = _solicitud(conexion, orden["solicitud_id"])
            if vinculada not in solicitudes:
                solicitudes.append(vinculada)
    return solicitudes


def _insertar_lineas(conexion, id_orden, lineas):
    with conexion.cursor() as cursor:
        for linea in lineas:
            cursor.execute(
                """
                INSERT INTO orden_compra_detalle
                    (id_orden_compra, id_insumo, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    id_orden,
                    linea["insumo_id"],
                    linea["cantidad"],
                    linea["precio_unitario"],
                ),
            )


def _crear_orden(conexion, datos, solicitud=None):
    with conexion.cursor() as cursor:
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence('ordenes_compra', 'id_orden_compra'))"
        )
        id_orden = cursor.fetchone()[0]
        numero = f"OC-{date.today().year}-{id_orden:03d}"
        cursor.execute(
            """
            INSERT INTO ordenes_compra
                (id_orden_compra, numero_orden, id_proveedor, id_solicitud,
                 fecha_emision, fecha_entrega_esperada, estado, subtotal,
                 impuestos, total, observacion)
            VALUES (%s, %s, %s, %s, CURRENT_DATE, %s, 'emitida', %s, %s, %s, %s)
            """,
            (
                id_orden,
                numero,
                datos["proveedor_id"],
                datos["solicitud_id"],
                datos["fecha_entrega_esperada"],
                datos["subtotal"],
                datos["impuestos"],
                datos["total"],
                datos["observacion"],
            ),
        )
    _insertar_lineas(conexion, id_orden, datos["lineas"])
    if solicitud:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE solicitudes_compra
                SET estado = 'atendida'
                WHERE id_solicitud = %s AND estado = 'aprobada'
                """,
                (solicitud["id"],),
            )
            if cursor.rowcount != 1:
                abort(409, description="La solicitud ya no está disponible para asociar.")
    return {"id": id_orden, "numero": numero}


def _validar_proveedor(conexion, formulario, id_proveedor=None):
    datos = {
        "razon_social": formulario.get("razon_social", "").strip(),
        "nit": formulario.get("nit", "").strip(),
        "contacto": formulario.get("contacto", "").strip(),
        "telefono": formulario.get("telefono", "").strip(),
        "email": formulario.get("email", "").strip().lower(),
        "direccion": formulario.get("direccion", "").strip(),
        "condiciones": formulario.get("condiciones", "").strip(),
    }
    if not datos["razon_social"] or len(datos["razon_social"]) > 150:
        return datos, "La razón social es obligatoria y no debe superar 150 caracteres."
    if len(datos["nit"]) > 20 or len(datos["contacto"]) > 100 or len(datos["telefono"]) > 20:
        return datos, "Revisa el límite de caracteres de NIT, contacto o teléfono."
    if len(datos["email"]) > 150 or (
        datos["email"]
        and ("@" not in datos["email"] or "." not in datos["email"].rsplit("@", 1)[-1])
    ):
        return datos, "Ingresa un correo electrónico válido."
    if len(datos["direccion"]) > 255 or len(datos["condiciones"]) > 1000:
        return datos, "La dirección o las condiciones comerciales superan el límite permitido."
    if datos["nit"]:
        consulta = "SELECT 1 FROM proveedores WHERE nit = %s"
        parametros = [datos["nit"]]
        if id_proveedor is not None:
            consulta += " AND id_proveedor <> %s"
            parametros.append(id_proveedor)
        if _fila(conexion, consulta, tuple(parametros)):
            return datos, "Ya existe un proveedor con ese NIT."
    return datos, None


def _datos_proveedor(datos):
    return (
        datos["nit"] or None,
        datos["razon_social"],
        datos["contacto"] or None,
        datos["telefono"] or None,
        datos["email"] or None,
        datos["direccion"] or None,
        datos["condiciones"] or None,
    )


@compras_bp.route("/")
def panel():
    with _conexion() as conexion:
        solicitudes_pendientes = _solicitudes(conexion, estado="pendiente")
        ordenes_abiertas = [
            orden for orden in _ordenes(conexion)
            if orden["estado"] in ("emitida", "parcial")
        ]
        atrasadas = [orden for orden in ordenes_abiertas if orden["atrasada"]]
        bajos = _insumos_bajo_minimo(conexion)
        precios_recientes = _precios_historicos(conexion, limite=5)
        proveedor_count = _fila(
            conexion, "SELECT COUNT(*) AS total FROM proveedores WHERE activo = TRUE"
        )["total"]
        kpis = {
            "solicitudes_pendientes": len(solicitudes_pendientes),
            "ordenes_abiertas": len(ordenes_abiertas),
            "entregas_atrasadas": len(atrasadas),
            "proveedores_activos": proveedor_count,
            "insumos_bajo_minimo": len(bajos),
        }
    return _render(
        "comprador/index.html",
        kpis=kpis,
        atrasadas=atrasadas,
        solicitudes=solicitudes_pendientes,
        insumos_bajo_minimo=bajos,
        precios_recientes=precios_recientes,
    )


@compras_bp.route("/solicitudes")
def solicitudes():
    estado = request.args.get("estado", "").strip()
    buscar = request.args.get("q", "").strip().lower()
    with _conexion() as conexion:
        filas = _solicitudes(conexion, estado=estado or None)
    if buscar:
        filas = [
            solicitud for solicitud in filas
            if buscar in (
                f"{solicitud['numero']} {solicitud['solicitante']} "
                f"{solicitud['observacion'] or ''} "
                f"{' '.join(item['nombre_insumo'] for item in solicitud['items'])}"
            ).lower()
        ]
    return _render("comprador/solicitudes.html", solicitudes=filas, estado=estado, buscar=buscar)


@compras_bp.route("/solicitudes/<int:id_solicitud>")
def solicitud_detalle(id_solicitud):
    with _conexion() as conexion:
        solicitud = _solicitud(conexion, id_solicitud)
    return _render("comprador/solicitud_detalle.html", solicitud=solicitud)


@compras_bp.route("/solicitudes/<int:id_solicitud>/estado", methods=["POST"])
def solicitud_estado(id_solicitud):
    accion = request.form.get("accion")
    transiciones = {"aprobar": "aprobada", "rechazar": "rechazada"}
    if accion not in transiciones:
        abort(400)
    with _conexion() as conexion:
        solicitud = _solicitud(conexion, id_solicitud)
        if solicitud["estado"] != "pendiente":
            abort(400, description="Solo se pueden procesar solicitudes pendientes.")
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                UPDATE solicitudes_compra SET estado = %s
                WHERE id_solicitud = %s AND estado = 'pendiente'
                """,
                (transiciones[accion], id_solicitud),
            )
            if cursor.rowcount != 1:
                abort(409, description="La solicitud cambió mientras se procesaba.")
        conexion.commit()
        numero = solicitud["numero"]
    flash(f"Solicitud {numero} {transiciones[accion]}.", "ok")
    return redirect(url_for("compras.solicitud_detalle", id_solicitud=id_solicitud))


@compras_bp.route("/ordenes")
def ordenes():
    estado = request.args.get("estado", "").strip()
    buscar = request.args.get("q", "").strip().lower()
    with _conexion() as conexion:
        filas = _ordenes(conexion, estado=estado or None)
    if buscar:
        filas = [
            orden for orden in filas
            if buscar in (
                f"{orden['numero']} {orden['proveedor']} {orden['observacion'] or ''}"
            ).lower()
        ]
    return _render("comprador/ordenes.html", ordenes=filas, estado=estado, buscar=buscar)


@compras_bp.route("/ordenes/nueva", methods=["GET", "POST"])
def orden_nueva():
    with _conexion() as conexion:
        insumos = _insumos(conexion)
        proveedores = _proveedores(conexion, solo_activos=True)
        solicitudes_disponibles = _solicitudes(conexion, estado="aprobada")
        if request.method == "POST":
            datos, solicitud, error = _validar_orden(conexion, request.form, insumos)
            if error:
                flash(error, "error")
                return _render(
                    "comprador/orden_form.html",
                    orden=_orden_formulario(request.form),
                    proveedores=proveedores,
                    solicitudes=solicitudes_disponibles,
                    insumos=insumos,
                    nueva=True,
                )
            nueva = _crear_orden(conexion, datos, solicitud)
            conexion.commit()
        else:
            solicitud_id = request.args.get("solicitud", type=int)
            solicitud = _solicitud(conexion, solicitud_id) if solicitud_id else None
            if solicitud and solicitud["estado"] != "aprobada":
                abort(400)
            lineas = [
                dict(
                    insumo_id=item["insumo_id"],
                    cantidad=str(item["cantidad"]),
                    precio_unitario="",
                )
                for item in solicitud["items"]
            ] if solicitud else [
                dict(insumo_id="", cantidad="", precio_unitario="")
            ]
            orden_form = {
                "proveedor_id": "",
                "solicitud_id": solicitud["id"] if solicitud else "",
                "fecha_entrega_esperada": (date.today() + timedelta(days=7)).isoformat(),
                "impuesto_porcentaje": "13",
                "observacion": "",
                "items": lineas,
            }
    if request.method == "POST":
        flash(f"Orden {nueva['numero']} creada.", "ok")
        return redirect(url_for("compras.ordenes"))
    return _render(
        "comprador/orden_form.html",
        orden=orden_form,
        proveedores=proveedores,
        solicitudes=solicitudes_disponibles,
        insumos=insumos,
        nueva=True,
    )


@compras_bp.route("/ordenes/<int:id_orden>/editar", methods=["GET", "POST"])
def orden_editar(id_orden):
    with _conexion() as conexion:
        orden = _orden(conexion, id_orden)
        if orden["estado"] in ("recibida", "anulada") or _cantidad_recibida(conexion, id_orden):
            flash("Las órdenes con recepciones registradas o anuladas no se pueden modificar.", "error")
            return redirect(url_for("compras.ordenes"))
        insumos = _insumos(conexion)
        proveedores = _proveedores(conexion, solo_activos=True)
        if not any(proveedor["id"] == orden["proveedor_id"] for proveedor in proveedores):
            proveedores.append(_proveedor(conexion, orden["proveedor_id"]))
        solicitudes_disponibles = _solicitudes_activas(conexion, id_orden)

        if request.method == "POST":
            datos, solicitud, error = _validar_orden(
                conexion, request.form, insumos, id_orden=id_orden
            )
            if error:
                flash(error, "error")
                return _render(
                    "comprador/orden_form.html",
                    orden=_orden_formulario(request.form),
                    proveedores=proveedores,
                    solicitudes=solicitudes_disponibles,
                    insumos=insumos,
                    nueva=False,
                    id_orden=id_orden,
                )

            solicitud_anterior_id = orden["solicitud_id"]
            solicitud_nueva_id = datos["solicitud_id"]
            if solicitud_anterior_id and solicitud_anterior_id != solicitud_nueva_id:
                with conexion.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE solicitudes_compra SET estado = 'aprobada'
                        WHERE id_solicitud = %s AND estado = 'atendida'
                        """,
                        (solicitud_anterior_id,),
                    )
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ordenes_compra
                    SET id_proveedor = %s, id_solicitud = %s,
                        fecha_entrega_esperada = %s, subtotal = %s,
                        impuestos = %s, total = %s, observacion = %s
                    WHERE id_orden_compra = %s
                    """,
                    (
                        datos["proveedor_id"],
                        solicitud_nueva_id,
                        datos["fecha_entrega_esperada"],
                        datos["subtotal"],
                        datos["impuestos"],
                        datos["total"],
                        datos["observacion"],
                        id_orden,
                    ),
                )
                cursor.execute(
                    "DELETE FROM orden_compra_detalle WHERE id_orden_compra = %s",
                    (id_orden,),
                )
            _insertar_lineas(conexion, id_orden, datos["lineas"])
            if solicitud and solicitud_nueva_id != solicitud_anterior_id:
                with conexion.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE solicitudes_compra SET estado = 'atendida'
                        WHERE id_solicitud = %s AND estado = 'aprobada'
                        """,
                        (solicitud_nueva_id,),
                    )
                    if cursor.rowcount != 1:
                        abort(409, description="La solicitud ya no está disponible para asociar.")
            conexion.commit()
            numero = orden["numero"]
        else:
            formulario = {
                "proveedor_id": orden["proveedor_id"],
                "solicitud_id": orden["solicitud_id"] or "",
                "fecha_entrega_esperada": orden["fecha_entrega_esperada"].isoformat(),
                "impuesto_porcentaje": str(orden["impuesto_porcentaje"]),
                "observacion": orden["observacion"] or "",
                "items": [
                    dict(
                        insumo_id=item["insumo_id"],
                        cantidad=str(item["cantidad"]),
                        precio_unitario=str(item["precio_unitario"]),
                    )
                    for item in orden["items"]
                ],
            }
    if request.method == "POST":
        flash(f"Orden {numero} actualizada.", "ok")
        return redirect(url_for("compras.ordenes"))
    return _render(
        "comprador/orden_form.html",
        orden=formulario,
        proveedores=proveedores,
        solicitudes=solicitudes_disponibles,
        insumos=insumos,
        nueva=False,
        id_orden=id_orden,
    )


@compras_bp.route("/proveedores")
def proveedores():
    buscar = request.args.get("q", "").strip().lower()
    estado = request.args.get("estado", "").strip()
    with _conexion() as conexion:
        filas = _proveedores(conexion)
    if buscar:
        filas = [
            proveedor for proveedor in filas
            if buscar in " ".join(
                str(proveedor[campo] or "")
                for campo in ("razon_social", "nit", "contacto", "email")
            ).lower()
        ]
    if estado:
        activo = estado == "activo"
        filas = [proveedor for proveedor in filas if proveedor["activo"] == activo]
    return _render("comprador/proveedores.html", proveedores=filas, buscar=buscar, estado=estado)


@compras_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
def proveedor_nuevo():
    if request.method == "POST":
        with _conexion() as conexion:
            datos, error = _validar_proveedor(conexion, request.form)
            if error:
                flash(error, "error")
                return _render("comprador/proveedor_form.html", proveedor=datos, nuevo=True)
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO proveedores
                        (nit, razon_social, nombre_contacto, telefono, email,
                         direccion, condiciones_comerciales, activo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                    """,
                    _datos_proveedor(datos),
                )
            conexion.commit()
        flash("Proveedor registrado.", "ok")
        return redirect(url_for("compras.proveedores"))
    return _render("comprador/proveedor_form.html", proveedor={}, nuevo=True)


@compras_bp.route("/proveedores/<int:id_proveedor>/editar", methods=["GET", "POST"])
def proveedor_editar(id_proveedor):
    if request.method == "POST":
        with _conexion() as conexion:
            proveedor = _proveedor(conexion, id_proveedor)
            datos, error = _validar_proveedor(conexion, request.form, id_proveedor)
            if error:
                flash(error, "error")
                return _render(
                    "comprador/proveedor_form.html",
                    proveedor={**proveedor, **datos},
                    nuevo=False,
                )
            with conexion.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE proveedores
                    SET nit = %s, razon_social = %s, nombre_contacto = %s,
                        telefono = %s, email = %s, direccion = %s,
                        condiciones_comerciales = %s
                    WHERE id_proveedor = %s
                    """,
                    (*_datos_proveedor(datos), id_proveedor),
                )
            conexion.commit()
        flash("Datos del proveedor actualizados.", "ok")
        return redirect(url_for("compras.proveedores"))
    with _conexion() as conexion:
        proveedor = _proveedor(conexion, id_proveedor)
    return _render("comprador/proveedor_form.html", proveedor=proveedor, nuevo=False)


@compras_bp.route("/proveedores/<int:id_proveedor>/estado", methods=["POST"])
def proveedor_estado(id_proveedor):
    accion = request.form.get("accion")
    if accion not in ("activar", "desactivar"):
        abort(400)
    activo = accion == "activar"
    with _conexion() as conexion:
        proveedor = _proveedor(conexion, id_proveedor)
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE proveedores SET activo = %s WHERE id_proveedor = %s",
                (activo, id_proveedor),
            )
        conexion.commit()
    flash(f"Proveedor {'activado' if activo else 'desactivado'}.", "ok")
    return redirect(url_for("compras.proveedores"))


@compras_bp.route("/cotizaciones")
def cotizaciones():
    insumo_id = request.args.get("insumo", type=int)
    with _conexion() as conexion:
        insumos = _insumos(conexion)
        if insumo_id and not any(insumo["id"] == insumo_id for insumo in insumos):
            abort(400)
        filas = _precios_historicos(conexion, insumo_id=insumo_id)
    return _render(
        "comprador/cotizaciones.html",
        cotizaciones=filas,
        insumos=insumos,
        insumo_seleccionado=insumo_id,
    )


@compras_bp.route("/cotizaciones/nueva", methods=["GET", "POST"])
def cotizacion_nueva():
    flash(
        "La base de datos no tiene una tabla de cotizaciones; se muestran precios históricos de órdenes.",
        "error",
    )
    return redirect(url_for("compras.cotizaciones"))


@compras_bp.route("/seguimiento")
def seguimiento():
    estado = request.args.get("estado", "").strip()
    if estado not in ("", "atrasada", "en_plazo"):
        abort(400)
    with _conexion() as conexion:
        filas = [
            orden for orden in _ordenes(conexion)
            if orden["estado"] not in ("recibida", "anulada")
        ]
        if estado == "atrasada":
            filas = [orden for orden in filas if orden["atrasada"]]
        elif estado == "en_plazo":
            filas = [orden for orden in filas if not orden["atrasada"]]
        ids = [orden["id"] for orden in filas]
        recepciones = {id_orden: [] for id_orden in ids}
        if ids:
            for recepcion in _filas(
                conexion,
                """
                SELECT r.id_orden_compra AS orden_id, r.numero_lote AS lote,
                       r.fecha_recepcion AS fecha, r.fecha_vencimiento,
                       r.cantidad_recibida AS cantidad, r.observacion,
                       i.nombre AS insumo
                FROM recepciones_compra r
                LEFT JOIN lotes_insumos l ON l.id_lote_insumo = r.id_lote_insumo
                LEFT JOIN insumos i ON i.id_insumo = l.id_insumo
                WHERE r.id_orden_compra = ANY(%s)
                ORDER BY r.fecha_recepcion DESC, r.id_recepcion DESC
                """,
                (ids,),
            ):
                recepciones[recepcion["orden_id"]].append(recepcion)
    return _render(
        "comprador/seguimiento.html",
        ordenes=filas,
        estado=estado,
        recepciones=recepciones,
        hoy=date.today().isoformat(),
    )


@compras_bp.route("/seguimiento/<int:id_orden>/recibir", methods=["POST"])
def recibir_entrega(id_orden):
    with _conexion() as conexion:
        orden = _orden(conexion, id_orden)
        if orden["estado"] in ("recibida", "anulada"):
            abort(400)
        cantidad, error = _decimal(
            request.form.get("cantidad_recibida", ""),
            "cantidad recibida",
            maximo=Decimal("999999999.999"),
        )
        lote = request.form.get("numero_lote", "").strip()
        try:
            insumo_id = int(request.form.get("insumo_id", ""))
        except ValueError:
            insumo_id = 0
            error = error or "Selecciona un insumo de la orden."
        observacion = request.form.get("observacion", "").strip()
        try:
            fecha_recepcion = date.fromisoformat(request.form.get("fecha_recepcion", ""))
        except ValueError:
            fecha_recepcion = None
            error = error or "Ingresa una fecha de recepción válida."
        if fecha_recepcion and fecha_recepcion > date.today():
            error = error or "La fecha de recepción no puede ser futura."
        vencimiento_raw = request.form.get("fecha_vencimiento", "").strip()
        try:
            fecha_vencimiento = date.fromisoformat(vencimiento_raw) if vencimiento_raw else None
        except ValueError:
            fecha_vencimiento = None
            error = error or "La fecha de vencimiento no es válida."
        if not lote or len(lote) > 50:
            error = error or "El número de lote es obligatorio y no debe superar 50 caracteres."
        if len(observacion) > 500:
            error = error or "La observación no debe superar 500 caracteres."
        linea = next(
            (item for item in orden["items"] if item["insumo_id"] == insumo_id),
            None,
        )
        if linea is None:
            error = error or "El insumo seleccionado no pertenece a esta orden."
        if fecha_vencimiento and fecha_recepcion and fecha_vencimiento < fecha_recepcion:
            error = error or "El vencimiento no puede ser anterior a la recepción."
        if error:
            flash(error, "error")
            return redirect(url_for("compras.seguimiento"))

        pendiente = linea["cantidad"] - _cantidad_recibida(
            conexion, id_orden, insumo_id
        )
        if cantidad > pendiente:
            flash(f"La cantidad supera lo pendiente ({pendiente}).", "error")
            return redirect(url_for("compras.seguimiento"))

        estado_lote = (
            "vencido"
            if fecha_vencimiento and fecha_vencimiento < date.today()
            else "disponible"
        )
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lotes_insumos
                    (id_insumo, numero_lote, id_proveedor, fecha_recepcion,
                     fecha_vencimiento, cantidad_inicial, cantidad_actual,
                     costo_unitario, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id_lote_insumo
                """,
                (
                    insumo_id,
                    lote,
                    orden["proveedor_id"],
                    fecha_recepcion,
                    fecha_vencimiento,
                    cantidad,
                    cantidad,
                    linea["precio_unitario"],
                    estado_lote,
                ),
            )
            id_lote = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO recepciones_compra
                    (id_orden_compra, numero_lote, fecha_recepcion,
                     fecha_vencimiento, cantidad_recibida, id_lote_insumo,
                     observacion)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_orden,
                    lote,
                    fecha_recepcion,
                    fecha_vencimiento,
                    cantidad,
                    id_lote,
                    observacion,
                ),
            )
        completo = all(
            _cantidad_recibida(conexion, id_orden, item["insumo_id"])
            >= item["cantidad"]
            for item in orden["items"]
        )
        estado_orden = "recibida" if completo else "parcial"
        with conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE ordenes_compra SET estado = %s WHERE id_orden_compra = %s",
                (estado_orden, id_orden),
            )
        conexion.commit()
        unidad = linea["unidad"]
        numero_orden = orden["numero"]
    flash(
        f"Recepción de {cantidad} {unidad} registrada para {numero_orden}.",
        "ok",
    )
    return redirect(url_for("compras.seguimiento"))
