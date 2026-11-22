from flask import Blueprint

rrhh_bp = Blueprint("rrhh", __name__)

from . import routes