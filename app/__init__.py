from flask import Flask
from .models import db

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)

    from .acceso_comun import comun_bp
    from .administrador import admin_bp
    from .almacenero import almacen_bp
    from .calidad import calidad_bp
    from .comprador import compras_bp
    from .contador import finanzas_bp
    from .gerente import gerente_bp
    from .jefe_produccion import jefe_bp
    from .portal_cliente import cliente_bp
    from .rrhh import rrhh_bp
    from .vendedor import ventas_bp
    
    app.register_blueprint(comun_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(almacen_bp, url_prefix='/almacen')
    app.register_blueprint(calidad_bp, url_prefix='/calidad')
    app.register_blueprint(compras_bp, url_prefix='/compras')
    app.register_blueprint(finanzas_bp, url_prefix='/finanzas')
    app.register_blueprint(jefe_bp, url_prefix='/jefe')
    app.register_blueprint(gerente_bp, url_prefix='/gerente')
    app.register_blueprint(cliente_bp, url_prefix='/cliente')
    app.register_blueprint(rrhh_bp, url_prefix='/rrhh')
    app.register_blueprint(ventas_bp, url_prefix='/ventas')
    
    return app