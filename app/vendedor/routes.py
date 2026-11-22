from flask import render_template, request
from . import ventas_bp

@ventas_bp.route("/")
def panel():
    return "hola ventas"