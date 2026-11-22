from flask import render_template, request
from . import rrhh_bp

@rrhh_bp.route("/")
def panel():
    return "hola rrhh"