from flask import render_template, request
from . import almacen_bp

@almacen_bp.route("/")
def panel():
    return "hola almacen"