"""Rutas del rol RR. HH. conectadas a PostgreSQL (Flask-SQLAlchemy).

Usa los modelos de app/models.py sin modificarlos. Las vistas devuelven a las
plantillas las mismas claves que antes devolvían los datos simulados.

Notas de la base de datos:
- La nómina se calcula con las filas de la tabla asistencias del mes
  (un día con registro = un día trabajado).
- nomina_detalle no guarda los días trabajados: al mostrar una nómina se
  deducen de haberes / salario base * días laborables del mes.
- El estado de las capacitaciones (vigente / por vencer / vencida) se calcula
  aquí a partir de empleado_capacitaciones.
"""
import calendar
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from . import rrhh_bp
from ..models import (Asistencia, Capacitacion, Cargo, Empleado, EmpleadoCapacitacion,
                      Nomina, NominaDetalle, db)

MENU = [
    ("Panel", "rrhh.panel", "Resumen del personal"),
    ("Personal y asistencia", "rrhh.personal", "Registro del personal"),
    ("Asistencia diaria", "rrhh.asistencia", "Entradas y salidas"),
    ("Nómina", "rrhh.nomina", "Cálculo según asistencia"),
    ("Capacitaciones", "rrhh.capacitaciones", "Alerta de renovación"),
]
TASA_DESCUENTO = Decimal("0.12")
CENT = Decimal("0.01")


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="RR. HH.", **ctx)


# ====================================================================
# UTILIDADES
# ====================================================================
def _hoy():
    return date.today()


def _d(dias):
    return _hoy() + timedelta(days=dias)


def _sumar_meses(f, meses):
    y, m = divmod(f.month - 1 + meses, 12)
    y, m = f.year + y, m + 1
    return date(y, m, min(f.day, calendar.monthrange(y, m)[1]))


def _n(x):
    """Cantidad sin ceros sobrantes: Decimal('15000.00') -> 15000."""
    if x is None:
        return 0
    x = Decimal(x)
    return int(x) if x == x.to_integral_value() else float(x)


def _m(x):
    return round(float(x or 0), 2)


def _dinero(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def _parse_fecha(texto):
    """'YYYY-MM-DD' -> date (None si viene vacío; ValueError si es inválido)."""
    return date.fromisoformat(texto) if texto else None


def _parse_hora(texto):
    for formato in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(texto, formato).time()
        except (TypeError, ValueError):
            continue
    return None


def _error_bd(mensaje="No se pudo guardar en la base de datos. Intenta de nuevo."):
    db.session.rollback()
    flash(mensaje, "error")


def _nombre(e):
    return f"{e.nombres} {e.apellidos}"


def _cargos():
    return [dict(id_cargo=c.id_cargo, nombre=c.nombre, salario_base=_n(c.salario_base))
            for c in Cargo.query.order_by(Cargo.id_cargo).all()]


def _dias_laborables(periodo):
    """Lunes a viernes del mes 'YYYY-MM' (ValueError si el periodo no es válido)."""
    anio, mes = map(int, periodo.split("-"))
    return sum(1 for d in range(1, calendar.monthrange(anio, mes)[1] + 1) if date(anio, mes, d).weekday() < 5)


def _limites_mes(periodo):
    anio, mes = map(int, periodo.split("-"))
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


# ====================================================================
# CAPACITACIONES: estado calculado
# ====================================================================
def _estado_cap(venc):
    if venc < _hoy():
        return "vencida"
    return "por_vencer" if venc <= _d(30) else "vigente"


def _alertas(estado=""):
    """Última realización aprobada de cada capacitación por empleado activo."""
    q = (db.session.query(EmpleadoCapacitacion, Empleado, Capacitacion)
         .join(Empleado, Empleado.id_empleado == EmpleadoCapacitacion.id_empleado)
         .join(Capacitacion, Capacitacion.id_capacitacion == EmpleadoCapacitacion.id_capacitacion)
         .filter(Empleado.activo.is_(True), EmpleadoCapacitacion.aprobado.is_(True))
         .order_by(EmpleadoCapacitacion.fecha_realizacion, EmpleadoCapacitacion.id_registro))
    ultimas = {}
    for r, e, c in q.all():
        ultimas[(r.id_empleado, r.id_capacitacion)] = (r, e, c)
    filas = []
    for r, e, c in ultimas.values():
        venc = r.fecha_vencimiento or (_sumar_meses(r.fecha_realizacion, c.vigencia_meses)
                                       if c.vigencia_meses else None)
        if venc is None:  # capacitación sin vigencia: no genera alerta
            continue
        est = _estado_cap(venc)
        if estado and est != estado:
            continue
        filas.append(dict(empleado=_nombre(e), capacitacion=c.nombre, fecha_realizacion=r.fecha_realizacion,
                          fecha_vencimiento=venc, dias_restantes=(venc - _hoy()).days, estado=est))
    return sorted(filas, key=lambda f: f["fecha_vencimiento"])


# ====================================================================
# NÓMINA: cálculo y vistas
# ====================================================================
def _calcular_detalle(periodo):
    """Calcula haberes/descuentos de cada empleado del periodo según sus asistencias."""
    laborables = _dias_laborables(periodo)
    inicio, fin = _limites_mes(periodo)
    asistidos = dict(db.session.query(Asistencia.id_empleado, func.count(Asistencia.id_asistencia))
                     .filter(Asistencia.fecha >= inicio, Asistencia.fecha <= fin)
                     .group_by(Asistencia.id_empleado).all())
    empleados = (Empleado.query.options(joinedload(Empleado.cargo))
                 .filter(Empleado.fecha_ingreso <= fin,
                         or_(Empleado.activo.is_(True), Empleado.fecha_baja >= inicio))
                 .order_by(Empleado.id_empleado).all())
    filas = []
    for e in empleados:
        salario = (e.cargo.salario_base if e.cargo and e.cargo.salario_base is not None else Decimal(0))
        dias = min(asistidos.get(e.id_empleado, 0), laborables)
        haberes = _dinero(salario * dias / laborables)
        desc = _dinero(haberes * TASA_DESCUENTO)
        filas.append(NominaDetalle(id_empleado=e.id_empleado, haberes=haberes, descuentos=desc,
                                   neto=haberes - desc))
    return filas


def _vistas_nominas(nominas):
    ids = [n.id_nomina for n in nominas]
    detalles = {i: [] for i in ids}
    if ids:
        q = (db.session.query(NominaDetalle, Empleado, Cargo)
             .join(Empleado, Empleado.id_empleado == NominaDetalle.id_empleado)
             .outerjoin(Cargo, Cargo.id_cargo == Empleado.id_cargo)
             .filter(NominaDetalle.id_nomina.in_(ids)).order_by(NominaDetalle.id_detalle))
        periodos = {n.id_nomina: n.periodo for n in nominas}
        for d, e, c in q.all():
            try:
                laborables = _dias_laborables(periodos[d.id_nomina])
            except ValueError:
                laborables = 0
            salario = c.salario_base if c and c.salario_base else None
            dias = min(round(float(d.haberes) / float(salario) * laborables), laborables) if salario else 0
            detalles[d.id_nomina].append(dict(
                codigo_empleado=e.codigo_empleado, empleado=_nombre(e), cargo=c.nombre if c else None,
                dias_trabajados=dias, haberes=_m(d.haberes), descuentos=_m(d.descuentos), neto=_m(d.neto)))
    return [dict(id_nomina=n.id_nomina, periodo=n.periodo,
                 generada=n.fecha_generacion.date() if n.fecha_generacion else None, estado=n.estado,
                 detalle=detalles[n.id_nomina], total_haberes=_m(n.total_haberes),
                 total_descuentos=_m(n.total_descuentos), total_neto=_m(n.total_neto))
            for n in nominas]


# ====================================================================
# RUTAS
# ====================================================================
@rrhh_bp.route("/")
def panel():
    todas = _alertas()
    ultima = Nomina.query.order_by(Nomina.id_nomina.desc()).first()
    kpis = dict(
        empleados_activos=Empleado.query.filter_by(activo=True).count(),
        asistencias_hoy=Asistencia.query.filter_by(fecha=_hoy()).count(),
        por_vencer=sum(1 for a in todas if a["estado"] == "por_vencer"),
        vencidas=sum(1 for a in todas if a["estado"] == "vencida"),
        ultima_nomina=ultima.periodo if ultima else None)
    return _render("rrhh/panel.html", kpis=kpis, alertas=_alertas("por_vencer")[:6])


# ------------------------------------------------------------ Personal
def _dict_empleado(e):
    return dict(id_empleado=e.id_empleado, codigo_empleado=e.codigo_empleado, nombres=e.nombres,
                apellidos=e.apellidos, ci=e.ci, fecha_nacimiento=e.fecha_nacimiento, telefono=e.telefono,
                email=e.email, direccion=e.direccion, id_cargo=e.id_cargo, fecha_ingreso=e.fecha_ingreso,
                fecha_baja=e.fecha_baja, activo=e.activo)


@rrhh_bp.route("/personal")
def personal():
    buscar = request.args.get("q", "").strip()
    ver_bajas = request.args.get("bajas") == "1"
    q = Empleado.query.options(joinedload(Empleado.cargo))
    if buscar:
        patron = f"%{buscar}%"
        q = q.filter(or_(func.concat(Empleado.nombres, " ", Empleado.apellidos).ilike(patron),
                         Empleado.ci.ilike(patron), Empleado.codigo_empleado.ilike(patron)))
    if not ver_bajas:
        q = q.filter(Empleado.activo.is_(True))
    filas = [{**_dict_empleado(e), "nombre": _nombre(e), "cargo": e.cargo.nombre if e.cargo else None,
              "estado": "activo" if e.activo else "baja"}
             for e in q.order_by(Empleado.id_empleado).all()]
    return _render("rrhh/personal.html", buscar=buscar, ver_bajas=ver_bajas, empleados=filas)


def _datos_empleado(actual=None):
    f = request.form
    por_defecto = actual.fecha_ingreso.isoformat() if actual and actual.fecha_ingreso else _hoy().isoformat()
    return dict(nombres=f.get("nombres", "").strip(), apellidos=f.get("apellidos", "").strip(),
                ci=f.get("ci") or None, fecha_nacimiento=f.get("fecha_nacimiento") or None,
                telefono=f.get("telefono") or None, email=f.get("email") or None,
                direccion=f.get("direccion") or None, id_cargo=f.get("id_cargo", type=int),
                fecha_ingreso=f.get("fecha_ingreso") or por_defecto)


def _valores_empleado(datos):
    """Convierte las fechas de texto a date (ValueError si alguna es inválida)."""
    return {**datos, "fecha_nacimiento": _parse_fecha(datos["fecha_nacimiento"]),
            "fecha_ingreso": _parse_fecha(datos["fecha_ingreso"])}


def _siguiente_codigo():
    ultimo = (db.session.query(Empleado.codigo_empleado)
              .order_by(func.length(Empleado.codigo_empleado).desc(), Empleado.codigo_empleado.desc()).first())
    try:
        n = int(ultimo[0].replace("EMP", "")) + 1 if ultimo else 1
    except ValueError:
        n = Empleado.query.count() + 1
    return f"EMP{n:03d}"


@rrhh_bp.route("/personal/nuevo", methods=["GET", "POST"])
def empleado_nuevo():
    if request.method == "POST":
        datos = _datos_empleado()
        if not datos["nombres"] or not datos["apellidos"]:
            flash("Escribe nombres y apellidos.", "error")
            return _render("rrhh/empleado_form.html", e=datos, cargos=_cargos())
        try:
            valores = _valores_empleado(datos)
        except ValueError:
            flash("Revisa las fechas: deben tener formato válido.", "error")
            return _render("rrhh/empleado_form.html", e=datos, cargos=_cargos())
        try:
            db.session.add(Empleado(codigo_empleado=_siguiente_codigo(), activo=True, **valores))
            db.session.commit()
        except SQLAlchemyError:
            _error_bd("No se pudo registrar al empleado (¿ya existe esa CI?).")
            return _render("rrhh/empleado_form.html", e=datos, cargos=_cargos())
        flash("Empleado registrado.", "ok")
        return redirect(url_for("rrhh.personal"))
    return _render("rrhh/empleado_form.html", e={}, cargos=_cargos())


@rrhh_bp.route("/personal/<int:id>/editar", methods=["GET", "POST"])
def empleado_editar(id):
    empleado = Empleado.query.get_or_404(id)
    if request.method == "POST":
        datos = _datos_empleado(empleado)
        if not datos["nombres"] or not datos["apellidos"]:
            flash("Escribe nombres y apellidos.", "error")
            return _render("rrhh/empleado_form.html", e=datos, id=id, cargos=_cargos())
        try:
            valores = _valores_empleado(datos)
        except ValueError:
            flash("Revisa las fechas: deben tener formato válido.", "error")
            return _render("rrhh/empleado_form.html", e=datos, id=id, cargos=_cargos())
        try:
            Empleado.actualizar(id, **valores)
        except SQLAlchemyError:
            _error_bd("No se pudo actualizar (¿ya existe esa CI?).")
            return _render("rrhh/empleado_form.html", e=datos, id=id, cargos=_cargos())
        flash("Datos actualizados.", "ok")
        return redirect(url_for("rrhh.personal"))
    return _render("rrhh/empleado_form.html", e=_dict_empleado(empleado), id=id, cargos=_cargos())


@rrhh_bp.route("/personal/<int:id>/baja", methods=["POST"])
def empleado_baja(id):
    empleado = Empleado.query.get_or_404(id)
    empleado.activo = False
    empleado.fecha_baja = _hoy()
    try:
        db.session.commit()
        flash("Empleado dado de baja.", "ok")
    except SQLAlchemyError:
        _error_bd()
    return redirect(url_for("rrhh.personal"))


# ------------------------------------------------------------ Asistencia
@rrhh_bp.route("/asistencia", methods=["GET", "POST"])
def asistencia():
    texto = request.values.get("fecha") or _hoy().isoformat()
    try:
        dia = date.fromisoformat(texto)
    except ValueError:
        dia = _hoy()
    fecha = dia.isoformat()

    if request.method == "POST":
        existentes = {a.id_empleado: a for a in Asistencia.query.filter_by(fecha=dia)}
        guardados, errores = 0, 0
        try:
            for id_emp in request.form.getlist("id_empleado"):
                if not id_emp.isdigit():
                    continue
                id_emp = int(id_emp)
                entrada = _parse_hora(request.form.get(f"entrada_{id_emp}"))
                salida = _parse_hora(request.form.get(f"salida_{id_emp}"))
                if not entrada or not salida:
                    continue
                if salida <= entrada:
                    errores += 1
                    continue
                minutos = (salida.hour * 60 + salida.minute) - (entrada.hour * 60 + entrada.minute)
                a = existentes.get(id_emp)
                if a is None:
                    a = Asistencia(id_empleado=id_emp, fecha=dia)
                    db.session.add(a)
                a.hora_entrada, a.hora_salida = entrada, salida
                a.horas_trabajadas = _dinero(Decimal(minutos) / 60)
                a.observacion = request.form.get(f"obs_{id_emp}") or None
                guardados += 1
            db.session.commit()
        except SQLAlchemyError:
            _error_bd("No se pudo guardar la asistencia. Intenta de nuevo.")
            return redirect(url_for("rrhh.asistencia", fecha=fecha))
        if errores:
            flash("En algunos empleados la salida debe ser posterior a la entrada; no se guardaron.", "error")
        if guardados:
            flash(f"Asistencia del {fecha} guardada.", "ok")
        elif not errores:
            flash("Completa entrada y salida de al menos un empleado.", "error")
        return redirect(url_for("rrhh.asistencia", fecha=fecha))

    registradas = {a.id_empleado: a for a in Asistencia.query.filter_by(fecha=dia)}
    filas = []
    for e in (Empleado.query.options(joinedload(Empleado.cargo)).filter_by(activo=True)
              .order_by(Empleado.id_empleado)):
        a = registradas.get(e.id_empleado)
        filas.append(dict(
            id_empleado=e.id_empleado, nombre=_nombre(e), cargo=e.cargo.nombre if e.cargo else None,
            hora_entrada=a.hora_entrada.strftime("%H:%M") if a and a.hora_entrada else None,
            hora_salida=a.hora_salida.strftime("%H:%M") if a and a.hora_salida else None,
            horas_trabajadas=_m(a.horas_trabajadas) if a and a.horas_trabajadas is not None else None,
            observacion=a.observacion if a else None))
    return _render("rrhh/asistencia.html", fecha=fecha, filas=filas)


# ------------------------------------------------------------ Nómina
@rrhh_bp.route("/nomina")
def nomina():
    nominas = Nomina.query.order_by(Nomina.periodo.desc(), Nomina.id_nomina.desc()).all()
    return _render("rrhh/nomina.html", nominas=_vistas_nominas(nominas),
                   periodo_sugerido=_hoy().strftime("%Y-%m"))


@rrhh_bp.route("/nomina/generar", methods=["POST"])
def nomina_generar():
    periodo = request.form.get("periodo", "")
    try:
        laborables = _dias_laborables(periodo)
    except ValueError:
        flash("Elige un mes válido para la nómina.", "error")
        return redirect(url_for("rrhh.nomina"))
    if Nomina.query.filter_by(periodo=periodo).first():
        flash(f"Ya existe una nómina para {periodo}.", "error")
        return redirect(url_for("rrhh.nomina"))
    try:
        detalle = _calcular_detalle(periodo)
        n = Nomina(periodo=periodo, estado="borrador",
                   total_haberes=sum((d.haberes for d in detalle), Decimal(0)),
                   total_descuentos=sum((d.descuentos for d in detalle), Decimal(0)),
                   total_neto=sum((d.neto for d in detalle), Decimal(0)))
        n.detalle = detalle
        db.session.add(n)
        db.session.commit()
    except SQLAlchemyError:
        _error_bd("No se pudo generar la nómina. Intenta de nuevo.")
        return redirect(url_for("rrhh.nomina"))
    flash(f"Nómina {periodo} calculada con {laborables} días laborables.", "ok")
    return redirect(url_for("rrhh.nomina_detalle", id=n.id_nomina))


@rrhh_bp.route("/nomina/<int:id>")
def nomina_detalle(id):
    n = _vistas_nominas([Nomina.query.get_or_404(id)])[0]
    return _render("rrhh/nomina_detalle.html", n=n, filas=n["detalle"])


@rrhh_bp.route("/nomina/<int:id>/estado", methods=["POST"])
def nomina_estado(id):
    estado = request.form.get("estado")
    if estado not in ("borrador", "aprobada", "pagada"):
        abort(400)
    nomina_ = Nomina.query.get_or_404(id)
    nomina_.estado = estado
    try:
        db.session.commit()
        flash(f"Nómina {estado}.", "ok")
    except SQLAlchemyError:
        _error_bd()
    return redirect(url_for("rrhh.nomina_detalle", id=id))


# ------------------------------------------------------------ Capacitaciones
@rrhh_bp.route("/capacitaciones", methods=["GET", "POST"])
def capacitaciones():
    if request.method == "POST":
        id_emp = request.form.get("id_empleado", type=int)
        id_cap = request.form.get("id_capacitacion", type=int)
        cap = db.session.get(Capacitacion, id_cap) if id_cap else None
        emp = db.session.get(Empleado, id_emp) if id_emp else None
        if not emp or not cap:
            flash("Elige empleado y capacitación.", "error")
            return redirect(url_for("rrhh.capacitaciones"))
        try:
            fecha = date.fromisoformat(request.form.get("fecha") or _hoy().isoformat())
        except ValueError:
            flash("La fecha no es válida.", "error")
            return redirect(url_for("rrhh.capacitaciones"))
        try:
            db.session.add(EmpleadoCapacitacion(
                id_empleado=id_emp, id_capacitacion=id_cap, fecha_realizacion=fecha,
                fecha_vencimiento=_sumar_meses(fecha, cap.vigencia_meses) if cap.vigencia_meses else None,
                aprobado=True))
            db.session.commit()
        except SQLAlchemyError:
            _error_bd("No se pudo registrar (¿ya existe esa capacitación en esa fecha?).")
            return redirect(url_for("rrhh.capacitaciones"))
        flash("Capacitación registrada.", "ok")
        return redirect(url_for("rrhh.capacitaciones"))
    estado = request.args.get("estado", "")
    return _render("rrhh/capacitaciones.html", estado=estado, hoy=_hoy(), alertas=_alertas(estado),
                   empleados=[dict(id_empleado=e.id_empleado, nombre=_nombre(e))
                              for e in Empleado.query.filter_by(activo=True).order_by(Empleado.id_empleado)],
                   catalogo=[dict(id_capacitacion=c.id_capacitacion, nombre=c.nombre,
                                  vigencia_meses=c.vigencia_meses)
                             for c in Capacitacion.query.order_by(Capacitacion.id_capacitacion)])