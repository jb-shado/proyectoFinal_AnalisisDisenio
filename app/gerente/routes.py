from flask import render_template, request
from . import gerente_bp

@gerente_bp.route("/")
def panel():
    return "hola gerente"