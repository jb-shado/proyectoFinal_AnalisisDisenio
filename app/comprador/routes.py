from flask import render_template, request
from . import compras_bp

@compras_bp.route("/")
def panel():
    return "hola compras"