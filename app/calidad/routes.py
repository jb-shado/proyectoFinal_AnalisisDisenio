from flask import render_template, request
from . import calidad_bp

@calidad_bp.route("/")
def panel():
    return "hola calidad"