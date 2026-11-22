from flask import Blueprint

comun_bp = Blueprint("/", __name__)

from . import routes