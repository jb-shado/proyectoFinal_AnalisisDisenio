"""
models.py
Modelos SQLAlchemy (Flask-SQLAlchemy) generados a partir de db.sql
Sistema Integral de Gestión Empresarial (ERP) - Empresa Manufacturera de Alimentos

Uso típico en tu app.py / __init__.py:

    from flask import Flask
    from config import Config
    from models import db

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

Notas de diseño:
- Cada clase define __tablename__ exactamente igual al nombre de tabla en PostgreSQL.
- Las columnas GENERATED ALWAYS AS ... STORED (subtotal, diferencia) se modelan con
  sqlalchemy.Computed para que SQLAlchemy sepa que las calcula la base de datos.
- Se agregaron relationship() solo donde la relación es clara y no ambigua
  (una única FK hacia la tabla padre). Para columnas con múltiples FKs hacia el
  mismo modelo (ej. varias "id_usuario_x" que apuntan a Usuario), se dejó solo
  la columna con ForeignKey, sin relationship(), para evitar errores de
  relación ambigua en SQLAlchemy. Si necesitás esas relaciones, avisame y las
  agrego con foreign_keys= explícito y backref con nombres únicos.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Computed, inspect
from sqlalchemy.dialects.postgresql import JSONB

db = SQLAlchemy()


class CRUDMixin:
    """
    Métodos genéricos de CRUD para todos los modelos.
    Usa inspect() para detectar la clave primaria; si el modelo no
    tiene clave primaria, los métodos que la necesitan quedan en 'pass'.
    """

    @classmethod
    def _pk_columns(cls):
        return inspect(cls).primary_key

    @classmethod
    def consultar(cls, **filtros):
        """Consulta registros. Sin filtros trae todos."""
        query = cls.query
        if filtros:
            query = query.filter_by(**filtros)
        return query.all()

    def agregar(self):
        """Agrega esta instancia a la sesión y confirma el cambio."""
        if not self._pk_columns():
            pass
            return None
        db.session.add(self)
        db.session.commit()
        return self

    @classmethod
    def insertar(cls, **datos):
        """Crea e inserta un nuevo registro."""
        if not cls._pk_columns():
            pass
            return None
        obj = cls(**datos)
        db.session.add(obj)
        db.session.commit()
        return obj

    @classmethod
    def actualizar(cls, pk_valor, **datos):
        """Actualiza un registro existente según su clave primaria."""
        if not cls._pk_columns():
            pass
            return None
        obj = cls.query.get(pk_valor)
        if obj is None:
            return None
        for campo, valor in datos.items():
            setattr(obj, campo, valor)
        db.session.commit()
        return obj

    @classmethod
    def eliminar(cls, pk_valor):
        """Elimina un registro existente según su clave primaria."""
        if not cls._pk_columns():
            pass
            return None
        obj = cls.query.get(pk_valor)
        if obj is None:
            return None
        db.session.delete(obj)
        db.session.commit()
        return True



# ============================================================
# 2. SEGURIDAD Y USUARIOS
# ============================================================

class Rol(CRUDMixin, db.Model):
    __tablename__ = "roles"

    id_rol = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    usuarios = db.relationship("Usuario", backref="rol", lazy=True)


class Usuario(CRUDMixin, db.Model):
    __tablename__ = "usuarios"

    id_usuario = db.Column(db.Integer, primary_key=True)
    nombre_usuario = db.Column(db.String(50), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre_completo = db.Column(db.String(150), nullable=False)
    id_rol = db.Column(db.Integer, db.ForeignKey("roles.id_rol"), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    ultimo_acceso = db.Column(db.DateTime)
    intentos_fallidos = db.Column(db.Integer, default=0)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Auditoria(CRUDMixin, db.Model):
    __tablename__ = "auditoria"

    id_auditoria = db.Column(db.BigInteger, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    accion = db.Column(db.String(100), nullable=False)
    tabla_afectada = db.Column(db.String(100))
    registro_id = db.Column(db.String(50))
    datos_anteriores = db.Column(JSONB)
    datos_nuevos = db.Column(JSONB)
    ip_origen = db.Column(db.String(45))
    fecha_hora = db.Column(db.DateTime, default=datetime.utcnow, index=True)


# ============================================================
# 3. TERCEROS: PROVEEDORES Y CLIENTES
# ============================================================

class Proveedor(CRUDMixin, db.Model):
    __tablename__ = "proveedores"

    id_proveedor = db.Column(db.Integer, primary_key=True)
    nit = db.Column(db.String(20), unique=True)
    razon_social = db.Column(db.String(150), nullable=False)
    nombre_contacto = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(150))
    direccion = db.Column(db.String(255))
    condiciones_comerciales = db.Column(db.Text)
    calificacion = db.Column(db.Numeric(3, 2), default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)


class Cliente(CRUDMixin, db.Model):
    __tablename__ = "clientes"

    id_cliente = db.Column(db.Integer, primary_key=True)
    nit_ci = db.Column(db.String(20), unique=True)
    razon_social = db.Column(db.String(150), nullable=False)
    nombre_contacto = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(150))
    direccion = db.Column(db.String(255))
    limite_credito = db.Column(db.Numeric(12, 2), default=0)
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)


class CuentaCliente(CRUDMixin, db.Model):
    __tablename__ = "cuentas_cliente"
    __table_args__ = (db.UniqueConstraint("id_cliente", "id_usuario"),)

    id_cuenta = db.Column(db.Integer, primary_key=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey("clientes.id_cliente"), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 4. CATÁLOGOS: PRODUCTOS, INSUMOS, RECETAS
# ============================================================

class CategoriaProducto(CRUDMixin, db.Model):
    __tablename__ = "categorias_producto"

    id_categoria = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255))

    productos = db.relationship("Producto", backref="categoria", lazy=True)


class UnidadMedida(CRUDMixin, db.Model):
    __tablename__ = "unidades_medida"

    id_unidad = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    abreviatura = db.Column(db.String(10), nullable=False)


class Insumo(CRUDMixin, db.Model):
    __tablename__ = "insumos"

    id_insumo = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    id_unidad = db.Column(db.Integer, db.ForeignKey("unidades_medida.id_unidad"))
    stock_minimo = db.Column(db.Numeric(12, 3), default=0)
    stock_maximo = db.Column(db.Numeric(12, 3))
    perecedero = db.Column(db.Boolean, default=True)
    activo = db.Column(db.Boolean, default=True)

    unidad = db.relationship("UnidadMedida", lazy=True)


class Producto(CRUDMixin, db.Model):
    __tablename__ = "productos"

    id_producto = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    id_categoria = db.Column(db.Integer, db.ForeignKey("categorias_producto.id_categoria"))
    id_unidad = db.Column(db.Integer, db.ForeignKey("unidades_medida.id_unidad"))
    precio_venta = db.Column(db.Numeric(12, 2), nullable=False)
    vida_util_dias = db.Column(db.Integer)
    activo = db.Column(db.Boolean, default=True)

    unidad = db.relationship("UnidadMedida", lazy=True)


class Receta(CRUDMixin, db.Model):
    __tablename__ = "recetas"
    __table_args__ = (db.UniqueConstraint("id_producto", "version"),)

    id_receta = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    version = db.Column(db.String(10), nullable=False)
    descripcion = db.Column(db.String(255))
    rendimiento = db.Column(db.Numeric(12, 3))
    id_unidad = db.Column(db.Integer, db.ForeignKey("unidades_medida.id_unidad"))
    vigente = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    producto = db.relationship("Producto", backref="recetas", lazy=True)
    detalle = db.relationship("RecetaDetalle", backref="receta", lazy=True, cascade="all, delete-orphan")


class RecetaDetalle(CRUDMixin, db.Model):
    __tablename__ = "receta_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_receta = db.Column(db.Integer, db.ForeignKey("recetas.id_receta", ondelete="CASCADE"), nullable=False)
    id_insumo = db.Column(db.Integer, db.ForeignKey("insumos.id_insumo"), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    id_unidad = db.Column(db.Integer, db.ForeignKey("unidades_medida.id_unidad"))
    merma_esperada = db.Column(db.Numeric(5, 2), default=0)

    insumo = db.relationship("Insumo", lazy=True)


# ============================================================
# 5. INVENTARIOS Y LOTES
# ============================================================

class LoteInsumo(CRUDMixin, db.Model):
    __tablename__ = "lotes_insumos"
    __table_args__ = (db.UniqueConstraint("id_insumo", "numero_lote"),)

    id_lote_insumo = db.Column(db.Integer, primary_key=True)
    id_insumo = db.Column(db.Integer, db.ForeignKey("insumos.id_insumo"), nullable=False)
    numero_lote = db.Column(db.String(50), nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedores.id_proveedor"))
    fecha_recepcion = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date, index=True)
    cantidad_inicial = db.Column(db.Numeric(12, 3), nullable=False)
    cantidad_actual = db.Column(db.Numeric(12, 3), nullable=False)
    costo_unitario = db.Column(db.Numeric(12, 4))
    estado = db.Column(db.String(20), default="disponible")

    insumo = db.relationship("Insumo", lazy=True)
    proveedor = db.relationship("Proveedor", lazy=True)


class LoteProducto(CRUDMixin, db.Model):
    __tablename__ = "lotes_productos"

    id_lote_producto = db.Column(db.Integer, primary_key=True)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    numero_lote = db.Column(db.String(50), nullable=False, unique=True)
    fecha_produccion = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False, index=True)
    cantidad_inicial = db.Column(db.Numeric(12, 3), nullable=False)
    cantidad_actual = db.Column(db.Numeric(12, 3), nullable=False)
    estado = db.Column(db.String(20), default="disponible")
    id_orden_produccion = db.Column(db.Integer, db.ForeignKey("ordenes_produccion.id_orden_produccion"))
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    producto = db.relationship("Producto", lazy=True)


class MovimientoInventario(CRUDMixin, db.Model):
    __tablename__ = "movimientos_inventario"

    id_movimiento = db.Column(db.BigInteger, primary_key=True)
    tipo_item = db.Column(db.String(20), nullable=False, index=True)
    id_item = db.Column(db.Integer, nullable=False, index=True)
    id_lote = db.Column(db.Integer, nullable=False)
    tipo_movimiento = db.Column(db.String(30), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    costo_unitario = db.Column(db.Numeric(12, 4))
    documento_ref = db.Column(db.String(50))
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    observacion = db.Column(db.Text)
    fecha_movimiento = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class InventarioFisico(CRUDMixin, db.Model):
    __tablename__ = "inventarios_fisicos"

    id_inventario = db.Column(db.Integer, primary_key=True)
    fecha_inicio = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_fin = db.Column(db.DateTime)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    estado = db.Column(db.String(20), default="en_proceso")
    justificacion = db.Column(db.Text)

    detalle = db.relationship("InventarioFisicoDetalle", backref="inventario", lazy=True,
                               cascade="all, delete-orphan")


class InventarioFisicoDetalle(CRUDMixin, db.Model):
    __tablename__ = "inventario_fisico_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_inventario = db.Column(db.Integer, db.ForeignKey("inventarios_fisicos.id_inventario", ondelete="CASCADE"),
                               nullable=False)
    tipo_item = db.Column(db.String(20), nullable=False)
    id_item = db.Column(db.Integer, nullable=False)
    id_lote = db.Column(db.Integer, nullable=False)
    cantidad_sistema = db.Column(db.Numeric(12, 3), nullable=False)
    cantidad_contada = db.Column(db.Numeric(12, 3), nullable=False)
    # Columna calculada por PostgreSQL (GENERATED ALWAYS AS ... STORED): solo lectura.
    diferencia = db.Column(db.Numeric(12, 3), Computed("cantidad_contada - cantidad_sistema"))
    justificacion = db.Column(db.Text)


# ============================================================
# 6. COMPRAS
# ============================================================

class SolicitudCompra(CRUDMixin, db.Model):
    __tablename__ = "solicitudes_compra"

    id_solicitud = db.Column(db.Integer, primary_key=True)
    numero_solicitud = db.Column(db.String(30), unique=True, nullable=False)
    id_usuario_solicita = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    fecha_solicitud = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), default="pendiente")
    observacion = db.Column(db.Text)

    detalle = db.relationship("SolicitudCompraDetalle", backref="solicitud", lazy=True,
                               cascade="all, delete-orphan")


class SolicitudCompraDetalle(CRUDMixin, db.Model):
    __tablename__ = "solicitud_compra_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_solicitud = db.Column(db.Integer, db.ForeignKey("solicitudes_compra.id_solicitud", ondelete="CASCADE"),
                              nullable=False)
    id_insumo = db.Column(db.Integer, db.ForeignKey("insumos.id_insumo"), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)

    insumo = db.relationship("Insumo", lazy=True)


class OrdenCompra(CRUDMixin, db.Model):
    __tablename__ = "ordenes_compra"

    id_orden_compra = db.Column(db.Integer, primary_key=True)
    numero_orden = db.Column(db.String(30), unique=True, nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedores.id_proveedor"), nullable=False)
    id_solicitud = db.Column(db.Integer, db.ForeignKey("solicitudes_compra.id_solicitud"))
    fecha_emision = db.Column(db.Date, default=datetime.utcnow)
    fecha_entrega_esperada = db.Column(db.Date)
    estado = db.Column(db.String(20), default="emitida")
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    impuestos = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    id_usuario_crea = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    observacion = db.Column(db.Text)

    proveedor = db.relationship("Proveedor", lazy=True)
    detalle = db.relationship("OrdenCompraDetalle", backref="orden_compra", lazy=True,
                               cascade="all, delete-orphan")


class OrdenCompraDetalle(CRUDMixin, db.Model):
    __tablename__ = "orden_compra_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_orden_compra = db.Column(db.Integer, db.ForeignKey("ordenes_compra.id_orden_compra", ondelete="CASCADE"),
                                 nullable=False)
    id_insumo = db.Column(db.Integer, db.ForeignKey("insumos.id_insumo"), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 4), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), Computed("cantidad * precio_unitario"))

    insumo = db.relationship("Insumo", lazy=True)


class RecepcionCompra(CRUDMixin, db.Model):
    __tablename__ = "recepciones_compra"

    id_recepcion = db.Column(db.Integer, primary_key=True)
    id_orden_compra = db.Column(db.Integer, db.ForeignKey("ordenes_compra.id_orden_compra"), nullable=False)
    numero_lote = db.Column(db.String(50), nullable=False)
    fecha_recepcion = db.Column(db.Date, default=datetime.utcnow)
    fecha_vencimiento = db.Column(db.Date)
    cantidad_recibida = db.Column(db.Numeric(12, 3), nullable=False)
    id_lote_insumo = db.Column(db.Integer, db.ForeignKey("lotes_insumos.id_lote_insumo"))
    id_usuario_recibe = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    observacion = db.Column(db.Text)


class EvaluacionProveedor(CRUDMixin, db.Model):
    __tablename__ = "evaluaciones_proveedor"

    id_evaluacion = db.Column(db.Integer, primary_key=True)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedores.id_proveedor"), nullable=False)
    fecha_evaluacion = db.Column(db.Date, default=datetime.utcnow)
    cumplimiento_entrega = db.Column(db.Numeric(3, 2))
    calidad_producto = db.Column(db.Numeric(3, 2))
    precio = db.Column(db.Numeric(3, 2))
    calificacion_final = db.Column(db.Numeric(3, 2))
    id_usuario_evalua = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    observacion = db.Column(db.Text)

    proveedor = db.relationship("Proveedor", lazy=True)


# ============================================================
# 7. PRODUCCIÓN
# ============================================================

class OrdenProduccion(CRUDMixin, db.Model):
    __tablename__ = "ordenes_produccion"

    id_orden_produccion = db.Column(db.Integer, primary_key=True)
    numero_orden = db.Column(db.String(30), unique=True, nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    id_receta = db.Column(db.Integer, db.ForeignKey("recetas.id_receta"), nullable=False)
    cantidad_planificada = db.Column(db.Numeric(12, 3), nullable=False)
    cantidad_producida = db.Column(db.Numeric(12, 3), default=0)
    fecha_inicio = db.Column(db.DateTime)
    fecha_fin = db.Column(db.DateTime)
    estado = db.Column(db.String(20), default="planificada")
    id_usuario_responsable = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    observacion = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    producto = db.relationship("Producto", lazy=True)
    receta = db.relationship("Receta", lazy=True)
    lotes_producidos = db.relationship("LoteProducto", backref="orden_produccion", lazy=True)
    consumos = db.relationship("ConsumoInsumoProduccion", backref="orden_produccion", lazy=True,
                                cascade="all, delete-orphan")
    mermas = db.relationship("MermaProduccion", backref="orden_produccion", lazy=True,
                              cascade="all, delete-orphan")


class ConsumoInsumoProduccion(CRUDMixin, db.Model):
    __tablename__ = "consumo_insumos_produccion"

    id_consumo = db.Column(db.Integer, primary_key=True)
    id_orden_produccion = db.Column(db.Integer,
                                     db.ForeignKey("ordenes_produccion.id_orden_produccion", ondelete="CASCADE"),
                                     nullable=False)
    id_insumo = db.Column(db.Integer, db.ForeignKey("insumos.id_insumo"), nullable=False)
    id_lote_insumo = db.Column(db.Integer, db.ForeignKey("lotes_insumos.id_lote_insumo"), nullable=False)
    cantidad_consumida = db.Column(db.Numeric(12, 3), nullable=False)
    fecha_consumo = db.Column(db.DateTime, default=datetime.utcnow)

    insumo = db.relationship("Insumo", lazy=True)
    lote_insumo = db.relationship("LoteInsumo", lazy=True)


class MermaProduccion(CRUDMixin, db.Model):
    __tablename__ = "mermas_produccion"

    id_merma = db.Column(db.Integer, primary_key=True)
    id_orden_produccion = db.Column(db.Integer,
                                     db.ForeignKey("ordenes_produccion.id_orden_produccion", ondelete="CASCADE"),
                                     nullable=False)
    tipo_merma = db.Column(db.String(50))
    id_insumo = db.Column(db.Integer, db.ForeignKey("insumos.id_insumo"))
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    causa = db.Column(db.String(255))
    id_usuario_registra = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 8. CALIDAD E INOCUIDAD
# ============================================================

class ControlCalidad(CRUDMixin, db.Model):
    __tablename__ = "controles_calidad"

    id_control = db.Column(db.Integer, primary_key=True)
    id_lote_producto = db.Column(db.Integer, db.ForeignKey("lotes_productos.id_lote_producto"))
    id_lote_insumo = db.Column(db.Integer, db.ForeignKey("lotes_insumos.id_lote_insumo"))
    tipo_control = db.Column(db.String(50), nullable=False)
    resultado = db.Column(db.String(20), nullable=False)
    valor_medido = db.Column(db.Numeric(12, 3))
    unidad_medida = db.Column(db.String(20))
    observacion = db.Column(db.Text)
    id_usuario_responsable = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    fecha_control = db.Column(db.DateTime, default=datetime.utcnow)


class DocumentoCalidad(CRUDMixin, db.Model):
    __tablename__ = "documentos_calidad"

    id_documento = db.Column(db.Integer, primary_key=True)
    tipo_documento = db.Column(db.String(50), nullable=False)
    nombre_archivo = db.Column(db.String(255))
    ruta_archivo = db.Column(db.String(500))
    id_lote_producto = db.Column(db.Integer, db.ForeignKey("lotes_productos.id_lote_producto"))
    fecha_carga = db.Column(db.DateTime, default=datetime.utcnow)
    id_usuario_carga = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))


# ============================================================
# 9. VENTAS Y PORTAL DE CLIENTES
# ============================================================

class Pedido(CRUDMixin, db.Model):
    __tablename__ = "pedidos"

    id_pedido = db.Column(db.Integer, primary_key=True)
    numero_pedido = db.Column(db.String(30), unique=True, nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey("clientes.id_cliente"), nullable=False)
    fecha_pedido = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_entrega_estimada = db.Column(db.Date)
    origen = db.Column(db.String(20), default="vendedor")
    estado = db.Column(db.String(20), default="pendiente")
    subtotal = db.Column(db.Numeric(12, 2), default=0)
    impuestos = db.Column(db.Numeric(12, 2), default=0)
    total = db.Column(db.Numeric(12, 2), default=0)
    id_usuario_confirma = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    observacion = db.Column(db.Text)

    cliente = db.relationship("Cliente", backref="pedidos", lazy=True)
    detalle = db.relationship("PedidoDetalle", backref="pedido", lazy=True, cascade="all, delete-orphan")
    lotes = db.relationship("PedidoLote", backref="pedido", lazy=True, cascade="all, delete-orphan")


class PedidoDetalle(CRUDMixin, db.Model):
    __tablename__ = "pedido_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey("pedidos.id_pedido", ondelete="CASCADE"), nullable=False)
    id_producto = db.Column(db.Integer, db.ForeignKey("productos.id_producto"), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), Computed("cantidad * precio_unitario"))

    producto = db.relationship("Producto", lazy=True)


class PedidoLote(CRUDMixin, db.Model):
    __tablename__ = "pedido_lotes"

    id_pedido_lote = db.Column(db.Integer, primary_key=True)
    id_pedido = db.Column(db.Integer, db.ForeignKey("pedidos.id_pedido", ondelete="CASCADE"), nullable=False)
    id_lote_producto = db.Column(db.Integer, db.ForeignKey("lotes_productos.id_lote_producto"), nullable=False)
    cantidad = db.Column(db.Numeric(12, 3), nullable=False)

    lote_producto = db.relationship("LoteProducto", lazy=True)


class Factura(CRUDMixin, db.Model):
    __tablename__ = "facturas"

    id_factura = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(30), unique=True, nullable=False)
    id_pedido = db.Column(db.Integer, db.ForeignKey("pedidos.id_pedido"))
    id_cliente = db.Column(db.Integer, db.ForeignKey("clientes.id_cliente"), nullable=False)
    fecha_emision = db.Column(db.DateTime, default=datetime.utcnow)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    impuestos = db.Column(db.Numeric(12, 2), nullable=False)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    estado = db.Column(db.String(20), default="emitida")
    saldo_pendiente = db.Column(db.Numeric(12, 2), default=0)
    id_usuario_emite = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))

    cliente = db.relationship("Cliente", backref="facturas", lazy=True)


class NotaDespacho(CRUDMixin, db.Model):
    __tablename__ = "notas_despacho"

    id_nota = db.Column(db.Integer, primary_key=True)
    numero_nota = db.Column(db.String(30), unique=True, nullable=False)
    id_factura = db.Column(db.Integer, db.ForeignKey("facturas.id_factura"))
    id_pedido = db.Column(db.Integer, db.ForeignKey("pedidos.id_pedido"))
    fecha_despacho = db.Column(db.DateTime, default=datetime.utcnow)
    transportista = db.Column(db.String(150))
    direccion_entrega = db.Column(db.String(255))
    estado = db.Column(db.String(20), default="emitida")
    id_usuario_despacha = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))


class CuentaPorCobrar(CRUDMixin, db.Model):
    __tablename__ = "cuentas_por_cobrar"

    id_cxc = db.Column(db.Integer, primary_key=True)
    id_factura = db.Column(db.Integer, db.ForeignKey("facturas.id_factura"), nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey("clientes.id_cliente"), nullable=False)
    monto_original = db.Column(db.Numeric(12, 2), nullable=False)
    saldo = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_vencimiento = db.Column(db.Date)
    estado = db.Column(db.String(20), default="pendiente")

    factura = db.relationship("Factura", lazy=True)
    pagos = db.relationship("PagoCliente", backref="cuenta_por_cobrar", lazy=True)


class PagoCliente(CRUDMixin, db.Model):
    __tablename__ = "pagos_cliente"

    id_pago = db.Column(db.Integer, primary_key=True)
    id_cxc = db.Column(db.Integer, db.ForeignKey("cuentas_por_cobrar.id_cxc"), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)
    metodo_pago = db.Column(db.String(50))
    referencia = db.Column(db.String(100))
    id_usuario_registra = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))


class ReclamoCliente(CRUDMixin, db.Model):
    __tablename__ = "reclamos_cliente"

    id_reclamo = db.Column(db.Integer, primary_key=True)
    numero_reclamo = db.Column(db.String(30), unique=True, nullable=False)
    id_cliente = db.Column(db.Integer, db.ForeignKey("clientes.id_cliente"), nullable=False)
    id_factura = db.Column(db.Integer, db.ForeignKey("facturas.id_factura"))
    id_lote_producto = db.Column(db.Integer, db.ForeignKey("lotes_productos.id_lote_producto"))
    descripcion = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), default="abierto")
    fecha_reclamo = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_resolucion = db.Column(db.DateTime)
    id_usuario_atendio = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    resolucion = db.Column(db.Text)

    cliente = db.relationship("Cliente", backref="reclamos", lazy=True)


# ============================================================
# 10. CONTABILIDAD Y FINANZAS
# ============================================================

class PlanCuenta(CRUDMixin, db.Model):
    __tablename__ = "plan_cuentas"

    id_cuenta = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    nombre = db.Column(db.String(150), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    naturaleza = db.Column(db.String(1), nullable=False)
    cuenta_padre = db.Column(db.Integer, db.ForeignKey("plan_cuentas.id_cuenta"))
    activa = db.Column(db.Boolean, default=True)

    hijas = db.relationship("PlanCuenta", backref=db.backref("padre", remote_side=[id_cuenta]), lazy=True)


class AsientoContable(CRUDMixin, db.Model):
    __tablename__ = "asientos_contables"

    id_asiento = db.Column(db.Integer, primary_key=True)
    numero_asiento = db.Column(db.String(30), unique=True, nullable=False)
    fecha_asiento = db.Column(db.Date, nullable=False)
    descripcion = db.Column(db.String(255))
    tipo_origen = db.Column(db.String(30))
    id_origen = db.Column(db.Integer)
    estado = db.Column(db.String(20), default="registrado")
    id_usuario_registra = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)

    detalle = db.relationship("AsientoDetalle", backref="asiento", lazy=True, cascade="all, delete-orphan")


class AsientoDetalle(CRUDMixin, db.Model):
    __tablename__ = "asiento_detalle"
    __table_args__ = (
        CheckConstraint(
            "(debe > 0 AND haber = 0) OR (haber > 0 AND debe = 0)",
            name="chk_debe_haber",
        ),
    )

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_asiento = db.Column(db.Integer, db.ForeignKey("asientos_contables.id_asiento", ondelete="CASCADE"),
                            nullable=False)
    id_cuenta = db.Column(db.Integer, db.ForeignKey("plan_cuentas.id_cuenta"), nullable=False)
    debe = db.Column(db.Numeric(14, 2), default=0)
    haber = db.Column(db.Numeric(14, 2), default=0)

    cuenta = db.relationship("PlanCuenta", lazy=True)


class CuentaPorPagar(CRUDMixin, db.Model):
    __tablename__ = "cuentas_por_pagar"

    id_cxp = db.Column(db.Integer, primary_key=True)
    id_orden_compra = db.Column(db.Integer, db.ForeignKey("ordenes_compra.id_orden_compra"), nullable=False)
    id_proveedor = db.Column(db.Integer, db.ForeignKey("proveedores.id_proveedor"), nullable=False)
    monto_original = db.Column(db.Numeric(12, 2), nullable=False)
    saldo = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_vencimiento = db.Column(db.Date)
    estado = db.Column(db.String(20), default="pendiente")

    proveedor = db.relationship("Proveedor", lazy=True)
    pagos = db.relationship("PagoProveedor", backref="cuenta_por_pagar", lazy=True)


class PagoProveedor(CRUDMixin, db.Model):
    __tablename__ = "pagos_proveedor"

    id_pago = db.Column(db.Integer, primary_key=True)
    id_cxp = db.Column(db.Integer, db.ForeignKey("cuentas_por_pagar.id_cxp"), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)
    metodo_pago = db.Column(db.String(50))
    referencia = db.Column(db.String(100))
    id_usuario_registra = db.Column(db.Integer, db.ForeignKey("usuarios.id_usuario"))


class CostoProduccion(CRUDMixin, db.Model):
    __tablename__ = "costos_produccion"

    id_costo = db.Column(db.Integer, primary_key=True)
    id_orden_produccion = db.Column(db.Integer, db.ForeignKey("ordenes_produccion.id_orden_produccion"),
                                     nullable=False)
    costo_insumos = db.Column(db.Numeric(12, 2), default=0)
    costo_mano_obra = db.Column(db.Numeric(12, 2), default=0)
    costo_indirecto = db.Column(db.Numeric(12, 2), default=0)
    costo_total = db.Column(db.Numeric(12, 2), default=0)
    costo_unitario = db.Column(db.Numeric(12, 4), default=0)
    fecha_calculo = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# 11. RECURSOS HUMANOS
# ============================================================

class Cargo(CRUDMixin, db.Model):
    __tablename__ = "cargos"

    id_cargo = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.String(255))
    salario_base = db.Column(db.Numeric(12, 2))

    empleados = db.relationship("Empleado", backref="cargo", lazy=True)


class Empleado(CRUDMixin, db.Model):
    __tablename__ = "empleados"

    id_empleado = db.Column(db.Integer, primary_key=True)
    codigo_empleado = db.Column(db.String(20), unique=True, nullable=False)
    nombres = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    ci = db.Column(db.String(20), unique=True)
    fecha_nacimiento = db.Column(db.Date)
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(150))
    direccion = db.Column(db.String(255))
    id_cargo = db.Column(db.Integer, db.ForeignKey("cargos.id_cargo"))
    fecha_ingreso = db.Column(db.Date, nullable=False)
    fecha_baja = db.Column(db.Date)
    activo = db.Column(db.Boolean, default=True)

    asistencias = db.relationship("Asistencia", backref="empleado", lazy=True)
    capacitaciones = db.relationship("EmpleadoCapacitacion", backref="empleado", lazy=True)
    nomina_detalle = db.relationship("NominaDetalle", backref="empleado", lazy=True)


class Asistencia(CRUDMixin, db.Model):
    __tablename__ = "asistencias"
    __table_args__ = (db.UniqueConstraint("id_empleado", "fecha"),)

    id_asistencia = db.Column(db.BigInteger, primary_key=True)
    id_empleado = db.Column(db.Integer, db.ForeignKey("empleados.id_empleado"), nullable=False)
    fecha = db.Column(db.Date, nullable=False)
    hora_entrada = db.Column(db.Time)
    hora_salida = db.Column(db.Time)
    horas_trabajadas = db.Column(db.Numeric(5, 2))
    observacion = db.Column(db.String(255))


class Capacitacion(CRUDMixin, db.Model):
    __tablename__ = "capacitaciones"

    id_capacitacion = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    tipo = db.Column(db.String(50))
    fecha_inicio = db.Column(db.Date)
    fecha_fin = db.Column(db.Date)
    vigencia_meses = db.Column(db.Integer)
    obligatoria = db.Column(db.Boolean, default=True)

    empleados_capacitados = db.relationship("EmpleadoCapacitacion", backref="capacitacion", lazy=True)


class EmpleadoCapacitacion(CRUDMixin, db.Model):
    __tablename__ = "empleado_capacitaciones"
    __table_args__ = (db.UniqueConstraint("id_empleado", "id_capacitacion", "fecha_realizacion"),)

    id_registro = db.Column(db.Integer, primary_key=True)
    id_empleado = db.Column(db.Integer, db.ForeignKey("empleados.id_empleado"), nullable=False)
    id_capacitacion = db.Column(db.Integer, db.ForeignKey("capacitaciones.id_capacitacion"), nullable=False)
    fecha_realizacion = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date)
    aprobado = db.Column(db.Boolean, default=True)


class Nomina(CRUDMixin, db.Model):
    __tablename__ = "nominas"

    id_nomina = db.Column(db.Integer, primary_key=True)
    periodo = db.Column(db.String(20), nullable=False)
    fecha_generacion = db.Column(db.DateTime, default=datetime.utcnow)
    total_haberes = db.Column(db.Numeric(14, 2), default=0)
    total_descuentos = db.Column(db.Numeric(14, 2), default=0)
    total_neto = db.Column(db.Numeric(14, 2), default=0)
    estado = db.Column(db.String(20), default="borrador")

    detalle = db.relationship("NominaDetalle", backref="nomina", lazy=True, cascade="all, delete-orphan")


class NominaDetalle(CRUDMixin, db.Model):
    __tablename__ = "nomina_detalle"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_nomina = db.Column(db.Integer, db.ForeignKey("nominas.id_nomina", ondelete="CASCADE"), nullable=False)
    id_empleado = db.Column(db.Integer, db.ForeignKey("empleados.id_empleado"), nullable=False)
    haberes = db.Column(db.Numeric(12, 2), nullable=False)
    descuentos = db.Column(db.Numeric(12, 2), nullable=False)
    neto = db.Column(db.Numeric(12, 2), nullable=False)