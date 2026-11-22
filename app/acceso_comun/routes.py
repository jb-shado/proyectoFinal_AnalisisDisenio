from flask import render_template, request
from . import comun_bp

@comun_bp.route("/")
def panel():
    return "hola"