from flask import render_template, request
from . import cliente_bp

@cliente_bp.route("/")
def panel():
    return "hola cliente"