from flask import Blueprint

calidad_bp = Blueprint("calidad", __name__)

from . import routes