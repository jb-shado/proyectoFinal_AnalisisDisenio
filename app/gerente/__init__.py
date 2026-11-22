from flask import Blueprint

gerente_bp = Blueprint("gerente", __name__)

from . import routes