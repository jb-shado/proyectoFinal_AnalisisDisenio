from flask import render_template, request
from . import jefe_bp

@jefe_bp.route("/")
def panel():
    return "hola jefe"