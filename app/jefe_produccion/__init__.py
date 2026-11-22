from flask import Blueprint

jefe_bp = Blueprint("jefe", __name__)

from . import routes