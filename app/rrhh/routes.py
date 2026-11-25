"""Rutas del rol RR. HH. con datos simulados (sin base de datos).

Cuando conectes PostgreSQL, reemplaza cada bloque de datos por la consulta
correspondiente; las plantillas esperan exactamente estas claves.
"""
import calendar
from datetime import date, timedelta

from flask import abort, flash, redirect, render_template, request, url_for

from . import rrhh_bp

MENU = [
    ("Panel", "rrhh.panel", "Resumen del personal"),
    ("Personal y asistencia", "rrhh.personal", "Registro del personal"),
    ("Asistencia diaria", "rrhh.asistencia", "Entradas y salidas"),
    ("Nómina", "rrhh.nomina", "Cálculo según asistencia"),
    ("Capacitaciones", "rrhh.capacitaciones", "Alerta de renovación"),
]
TASA_DESCUENTO = 0.12


def _render(plantilla, **ctx):
    return render_template(plantilla, menu=MENU, rol="RR. HH.", **ctx)


def _hoy():
    return date.today()


def _d(dias):
    return _hoy() + timedelta(days=dias)


def _sumar_meses(f, meses):
    y, m = divmod(f.month - 1 + meses, 12)
    y, m = f.year + y, m + 1
    return date(y, m, min(f.day, calendar.monthrange(y, m)[1]))


# ====================================================================
# DATOS SIMULADOS
# ====================================================================
CARGOS = [  # tabla cargos
    dict(id_cargo=1, nombre="Gerente General", salario_base=15000),
    dict(id_cargo=2, nombre="Jefe de Producción", salario_base=8000),
    dict(id_cargo=3, nombre="Almacenero", salario_base=4000),
    dict(id_cargo=4, nombre="Comprador", salario_base=5000),
    dict(id_cargo=5, nombre="Vendedor", salario_base=4500),
    dict(id_cargo=6, nombre="Contador", salario_base=6000),
    dict(id_cargo=7, nombre="Responsable de Calidad", salario_base=6500),
    dict(id_cargo=8, nombre="Operario de Planta", salario_base=3500),
]


def _emp(i, nombres, apellidos, ci, nac, tel, id_cargo, ingreso, activo=True):
    return dict(id_empleado=i, codigo_empleado=f"EMP{i:03d}", nombres=nombres, apellidos=apellidos, ci=ci,
                fecha_nacimiento=nac, telefono=tel, email=f"{nombres[0].lower()}{apellidos.split()[0].lower()}@erp.bo",
                direccion="La Paz", id_cargo=id_cargo, fecha_ingreso=ingreso, activo=activo)


EMPLEADOS = [  # tabla empleados
    _emp(1, "Carlos", "Mamani Quispe", "1234567", date(1980, 5, 10), "70010001", 1, date(2015, 1, 15)),
    _emp(2, "María", "Flores Choque", "1234568", date(1985, 8, 20), "70010002", 2, date(2016, 3, 10)),
    _emp(3, "Juan", "Condori Apaza", "1234569", date(1990, 2, 15), "70010003", 3, date(2017, 6, 1)),
    _emp(4, "Ana", "Ticona Vargas", "1234570", date(1988, 11, 30), "70010004", 4, date(2018, 9, 12)),
    _emp(5, "Luis", "Callisaya Sumi", "1234571", date(1992, 4, 25), "70010005", 5, date(2019, 2, 20)),
    _emp(6, "Patricia", "Zenteno Ruiz", "1234572", date(1983, 7, 14), "70010006", 6, date(2014, 11, 5)),
    _emp(7, "Roberto", "Villacorta Nina", "1234573", date(1987, 12, 3), "70010007", 7, date(2020, 1, 15)),
    _emp(8, "Silvia", "Tarqui Loza", "1234574", date(1995, 3, 18), "70010008", 8, date(2021, 5, 10)),
    _emp(9, "Hugo", "Nina Quispe", "1234575", date(1993, 9, 22), "70010009", 8, date(2022, 8, 1)),
    _emp(10, "Carmen", "Callisaya Lima", "1234576", date(1986, 6, 9), "70010010", 8, date(2013, 4, 25),
         activo=False),
]

CAPACITACIONES = [  # tabla capacitaciones
    dict(id_capacitacion=1, nombre="Higiene personal", vigencia_meses=12),
    dict(id_capacitacion=2, nombre="Manipulación de alimentos", vigencia_meses=12),
    dict(id_capacitacion=3, nombre="BPM básico", vigencia_meses=12),
    dict(id_capacitacion=4, nombre="HACCP introducción", vigencia_meses=12),
    dict(id_capacitacion=5, nombre="Primeros auxilios", vigencia_meses=24),
    dict(id_capacitacion=6, nombre="Uso de extintores", vigencia_meses=12),
]

# empleado_capacitaciones: (empleado, capacitación, hace cuántos días se realizó)
REGISTROS = []


def _registrar(id_emp, id_cap, fecha):
    cap = next(c for c in CAPACITACIONES if c["id_capacitacion"] == id_cap)
    REGISTROS.append(dict(id_empleado=id_emp, id_capacitacion=id_cap, fecha_realizacion=fecha,
                          fecha_vencimiento=_sumar_meses(fecha, cap["vigencia_meses"])))


for _e, _c, _dias in [(1, 1, 400), (2, 2, 340), (3, 3, 200), (4, 4, 350), (5, 1, 100), (6, 5, 300),
                      (7, 6, 345), (8, 2, 30), (9, 3, 372), (2, 1, 330), (3, 1, 90)]:
    _registrar(_e, _c, _d(-_dias))

ASISTENCIAS = {}  # (fecha_iso, id_empleado) -> dict(entrada, salida, obs)
for _i in (1, 2, 3, 4, 5, 6, 7, 8):
    ASISTENCIAS[(_hoy().isoformat(), _i)] = dict(entrada="08:00", salida="17:00" if _i != 5 else "13:00",
                                                 obs="Permiso médico" if _i == 5 else None)

NOMINAS = []  # tabla nominas + nomina_detalle


def _dias_laborables(periodo):
    anio, mes = map(int, periodo.split("-"))
    return sum(1 for d in range(1, calendar.monthrange(anio, mes)[1] + 1) if date(anio, mes, d).weekday() < 5)


def _crear_nomina(periodo, estado):
    laborables = _dias_laborables(periodo)
    detalle = []
    for e in (e for e in EMPLEADOS if e["activo"]):
        salario = next(c["salario_base"] for c in CARGOS if c["id_cargo"] == e["id_cargo"])
        dias = max(laborables - (e["id_empleado"] % 3), 0)  # asistencia simulada
        haberes = round(salario * dias / laborables, 2)
        desc = round(haberes * TASA_DESCUENTO, 2)
        detalle.append(dict(codigo_empleado=e["codigo_empleado"], empleado=_nombre(e),
                            cargo=_cargo(e["id_cargo"]), dias_trabajados=dias, haberes=haberes,
                            descuentos=desc, neto=round(haberes - desc, 2)))
    n = dict(id_nomina=len(NOMINAS) + 1, periodo=periodo, generada=_hoy(), estado=estado, detalle=detalle,
             total_haberes=round(sum(d["haberes"] for d in detalle), 2),
             total_descuentos=round(sum(d["descuentos"] for d in detalle), 2),
             total_neto=round(sum(d["neto"] for d in detalle), 2))
    NOMINAS.append(n)
    return n


def _nombre(e):
    return f"{e['nombres']} {e['apellidos']}"


def _cargo(id_cargo):
    return next((c["nombre"] for c in CARGOS if c["id_cargo"] == id_cargo), None)


def _periodo_atras(meses):
    f = _sumar_meses(_hoy().replace(day=1), -meses)
    return f.strftime("%Y-%m")


_crear_nomina(_periodo_atras(2), "pagada")
_crear_nomina(_periodo_atras(1), "aprobada")


def _estado_cap(venc):
    if venc < _hoy():
        return "vencida"
    return "por_vencer" if venc <= _d(30) else "vigente"


def _alertas(estado=""):
    """Última realización de cada capacitación por empleado activo (vista v_capacitaciones_estado)."""
    ultimas = {}
    for r in sorted(REGISTROS, key=lambda r: r["fecha_realizacion"]):
        ultimas[(r["id_empleado"], r["id_capacitacion"])] = r
    filas = []
    for r in ultimas.values():
        emp = next(e for e in EMPLEADOS if e["id_empleado"] == r["id_empleado"])
        if not emp["activo"]:
            continue
        est = _estado_cap(r["fecha_vencimiento"])
        if estado and est != estado:
            continue
        filas.append(dict(empleado=_nombre(emp),
                          capacitacion=next(c["nombre"] for c in CAPACITACIONES
                                            if c["id_capacitacion"] == r["id_capacitacion"]),
                          fecha_realizacion=r["fecha_realizacion"], fecha_vencimiento=r["fecha_vencimiento"],
                          dias_restantes=(r["fecha_vencimiento"] - _hoy()).days, estado=est))
    return sorted(filas, key=lambda f: f["fecha_vencimiento"])


def _horas(entrada, salida):
    h1, m1 = map(int, entrada.split(":"))
    h2, m2 = map(int, salida.split(":"))
    return round(((h2 * 60 + m2) - (h1 * 60 + m1)) / 60, 2)


# ====================================================================
# RUTAS
# ====================================================================
@rrhh_bp.route("/")
def panel():
    todas = _alertas()
    kpis = dict(
        empleados_activos=sum(1 for e in EMPLEADOS if e["activo"]),
        asistencias_hoy=sum(1 for (f, _) in ASISTENCIAS if f == _hoy().isoformat()),
        por_vencer=sum(1 for a in todas if a["estado"] == "por_vencer"),
        vencidas=sum(1 for a in todas if a["estado"] == "vencida"),
        ultima_nomina=NOMINAS[-1]["periodo"] if NOMINAS else None)
    return _render("rrhh/panel.html", kpis=kpis, alertas=_alertas("por_vencer")[:6])


# ------------------------------------------------------------ Personal
@rrhh_bp.route("/personal")
def personal():
    buscar = request.args.get("q", "").strip()
    ver_bajas = request.args.get("bajas") == "1"
    filas = []
    for e in EMPLEADOS:
        texto = f"{_nombre(e)} {e['ci']} {e['codigo_empleado']}".lower()
        if buscar.lower() in texto and (ver_bajas or e["activo"]):
            filas.append({**e, "nombre": _nombre(e), "cargo": _cargo(e["id_cargo"]),
                          "estado": "activo" if e["activo"] else "baja"})
    return _render("rrhh/personal.html", buscar=buscar, ver_bajas=ver_bajas, empleados=filas)


def _datos_empleado():
    f = request.form
    return dict(nombres=f.get("nombres", "").strip(), apellidos=f.get("apellidos", "").strip(),
                ci=f.get("ci") or None, fecha_nacimiento=f.get("fecha_nacimiento") or None,
                telefono=f.get("telefono") or None, email=f.get("email") or None,
                direccion=f.get("direccion") or None, id_cargo=f.get("id_cargo", type=int),
                fecha_ingreso=f.get("fecha_ingreso") or _hoy().isoformat())


@rrhh_bp.route("/personal/nuevo", methods=["GET", "POST"])
def empleado_nuevo():
    if request.method == "POST":
        datos = _datos_empleado()
        if not datos["nombres"] or not datos["apellidos"]:
            flash("Escribe nombres y apellidos.", "error")
            return _render("rrhh/empleado_form.html", e=datos, cargos=CARGOS)
        n = len(EMPLEADOS) + 1
        EMPLEADOS.append(dict(id_empleado=n, codigo_empleado=f"EMP{n:03d}", activo=True, **datos))
        flash("Empleado registrado.", "ok")
        return redirect(url_for("rrhh.personal"))
    return _render("rrhh/empleado_form.html", e={}, cargos=CARGOS)


def _empleado(id):
    e = next((e for e in EMPLEADOS if e["id_empleado"] == id), None)
    if not e:
        abort(404)
    return e


@rrhh_bp.route("/personal/<int:id>/editar", methods=["GET", "POST"])
def empleado_editar(id):
    e = _empleado(id)
    if request.method == "POST":
        e.update(_datos_empleado())
        flash("Datos actualizados.", "ok")
        return redirect(url_for("rrhh.personal"))
    return _render("rrhh/empleado_form.html", e=e, id=id, cargos=CARGOS)


@rrhh_bp.route("/personal/<int:id>/baja", methods=["POST"])
def empleado_baja(id):
    _empleado(id)["activo"] = False
    flash("Empleado dado de baja.", "ok")
    return redirect(url_for("rrhh.personal"))


# ------------------------------------------------------------ Asistencia
@rrhh_bp.route("/asistencia", methods=["GET", "POST"])
def asistencia():
    fecha = request.values.get("fecha") or _hoy().isoformat()
    if request.method == "POST":
        guardados = 0
        for id_emp in request.form.getlist("id_empleado"):
            entrada = request.form.get(f"entrada_{id_emp}")
            salida = request.form.get(f"salida_{id_emp}")
            if entrada and salida:
                ASISTENCIAS[(fecha, int(id_emp))] = dict(entrada=entrada, salida=salida,
                                                         obs=request.form.get(f"obs_{id_emp}") or None)
                guardados += 1
        if guardados:
            flash(f"Asistencia del {fecha} guardada.", "ok")
        else:
            flash("Completa entrada y salida de al menos un empleado.", "error")
        return redirect(url_for("rrhh.asistencia", fecha=fecha))
    filas = []
    for e in (e for e in EMPLEADOS if e["activo"]):
        a = ASISTENCIAS.get((fecha, e["id_empleado"]))
        filas.append(dict(id_empleado=e["id_empleado"], nombre=_nombre(e), cargo=_cargo(e["id_cargo"]),
                          hora_entrada=a["entrada"] if a else None, hora_salida=a["salida"] if a else None,
                          horas_trabajadas=_horas(a["entrada"], a["salida"]) if a else None,
                          observacion=a["obs"] if a else None))
    return _render("rrhh/asistencia.html", fecha=fecha, filas=filas)


# ------------------------------------------------------------ Nómina
@rrhh_bp.route("/nomina")
def nomina():
    return _render("rrhh/nomina.html", nominas=sorted(NOMINAS, key=lambda n: n["periodo"], reverse=True),
                   periodo_sugerido=_hoy().strftime("%Y-%m"))


@rrhh_bp.route("/nomina/generar", methods=["POST"])
def nomina_generar():
    periodo = request.form.get("periodo", "")
    try:
        _dias_laborables(periodo)
    except ValueError:
        flash("Elige un mes válido para la nómina.", "error")
        return redirect(url_for("rrhh.nomina"))
    if any(n["periodo"] == periodo for n in NOMINAS):
        flash(f"Ya existe una nómina para {periodo}.", "error")
        return redirect(url_for("rrhh.nomina"))
    n = _crear_nomina(periodo, "borrador")
    flash(f"Nómina {periodo} calculada con {_dias_laborables(periodo)} días laborables.", "ok")
    return redirect(url_for("rrhh.nomina_detalle", id=n["id_nomina"]))


def _nomina(id):
    n = next((n for n in NOMINAS if n["id_nomina"] == id), None)
    if not n:
        abort(404)
    return n


@rrhh_bp.route("/nomina/<int:id>")
def nomina_detalle(id):
    n = _nomina(id)
    return _render("rrhh/nomina_detalle.html", n=n, filas=n["detalle"])


@rrhh_bp.route("/nomina/<int:id>/estado", methods=["POST"])
def nomina_estado(id):
    estado = request.form.get("estado")
    if estado not in ("borrador", "aprobada", "pagada"):
        abort(400)
    _nomina(id)["estado"] = estado
    flash(f"Nómina {estado}.", "ok")
    return redirect(url_for("rrhh.nomina_detalle", id=id))


# ------------------------------------------------------------ Capacitaciones
@rrhh_bp.route("/capacitaciones", methods=["GET", "POST"])
def capacitaciones():
    if request.method == "POST":
        id_emp = request.form.get("id_empleado", type=int)
        id_cap = request.form.get("id_capacitacion", type=int)
        if not id_emp or not id_cap:
            flash("Elige empleado y capacitación.", "error")
        else:
            _registrar(id_emp, id_cap, date.fromisoformat(request.form.get("fecha") or _hoy().isoformat()))
            flash("Capacitación registrada.", "ok")
        return redirect(url_for("rrhh.capacitaciones"))
    estado = request.args.get("estado", "")
    return _render("rrhh/capacitaciones.html", estado=estado, hoy=_hoy(), alertas=_alertas(estado),
                   empleados=[dict(id_empleado=e["id_empleado"], nombre=_nombre(e))
                              for e in EMPLEADOS if e["activo"]],
                   catalogo=CAPACITACIONES)
