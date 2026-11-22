from flask import Blueprint

almacen_bp = Blueprint("almacen", __name__)

from . import routes