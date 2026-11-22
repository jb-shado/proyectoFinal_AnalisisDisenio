from flask import render_template, request
from . import finanzas_bp

@finanzas_bp.route("/")
def panel():
    return "hola conta"