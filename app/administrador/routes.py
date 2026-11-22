from flask import render_template, request
from . import admin_bp

@admin_bp.route("/")
def panel():
    return "hola admin"