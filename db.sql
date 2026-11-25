-- ============================================================
-- SISTEMA INTEGRAL DE GESTIÓN EMPRESARIAL (ERP)
-- Empresa Manufacturera de Alimentos
-- PostgreSQL 14+
-- ============================================================

-- ============================================================
-- 0. CREAR BASE DE DATOS (ejecutar por separado si usas psql)
-- ============================================================
CREATE DATABASE erp_manufactura
     WITH ENCODING 'UTF8'
     TEMPLATE template0;

-- ============================================================
-- 1. EXTENSIONES
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 2. SEGURIDAD Y USUARIOS (RF-01, RF-02, RF-03)
-- ============================================================
CREATE TABLE roles (
    id_rol          SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE,
    descripcion     VARCHAR(200),
    activo          BOOLEAN DEFAULT TRUE,
    fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO roles (nombre, descripcion) VALUES
('gerente',         'Acceso total a reportes y decisiones'),
('jefe_produccion', 'Gestión de producción y recetas'),
('almacenero',      'Control de inventarios y lotes'),
('comprador',       'Gestión de compras y proveedores'),
('vendedor',        'Gestión de ventas y pedidos'),
('contador',        'Contabilidad y finanzas'),
('calidad',         'Controles de calidad e inocuidad'),
('administrador',   'Administración del sistema'),
('cliente',         'Acceso al portal de clientes'),
('rrhh',            'Recursos humanos y nómina');

CREATE TABLE usuarios (
    id_usuario      SERIAL PRIMARY KEY,
    nombre_usuario  VARCHAR(50) NOT NULL UNIQUE,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(150) NOT NULL,
    id_rol          INT NOT NULL REFERENCES roles(id_rol),
    activo          BOOLEAN DEFAULT TRUE,
    ultimo_acceso   TIMESTAMP,
    intentos_fallidos INT DEFAULT 0,
    fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE auditoria (
    id_auditoria    BIGSERIAL PRIMARY KEY,
    id_usuario      INT REFERENCES usuarios(id_usuario),
    accion          VARCHAR(100) NOT NULL,
    tabla_afectada  VARCHAR(100),
    registro_id     VARCHAR(50),
    datos_anteriores JSONB,
    datos_nuevos    JSONB,
    ip_origen       VARCHAR(45),
    fecha_hora      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_auditoria_usuario ON auditoria(id_usuario);
CREATE INDEX idx_auditoria_fecha   ON auditoria(fecha_hora);

-- ============================================================
-- 3. TERCEROS: PROVEEDORES Y CLIENTES
-- ============================================================
CREATE TABLE proveedores (
    id_proveedor    SERIAL PRIMARY KEY,
    nit             VARCHAR(20) UNIQUE,
    razon_social    VARCHAR(150) NOT NULL,
    nombre_contacto VARCHAR(100),
    telefono        VARCHAR(20),
    email           VARCHAR(150),
    direccion       VARCHAR(255),
    condiciones_comerciales TEXT,
    calificacion    NUMERIC(3,2) DEFAULT 0,
    activo          BOOLEAN DEFAULT TRUE,
    fecha_registro  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE clientes (
    id_cliente      SERIAL PRIMARY KEY,
    nit_ci          VARCHAR(20) UNIQUE,
    razon_social    VARCHAR(150) NOT NULL,
    nombre_contacto VARCHAR(100),
    telefono        VARCHAR(20),
    email           VARCHAR(150),
    direccion       VARCHAR(255),
    limite_credito  NUMERIC(12,2) DEFAULT 0,
    activo          BOOLEAN DEFAULT TRUE,
    fecha_registro  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cuentas_cliente (
    id_cuenta       SERIAL PRIMARY KEY,
    id_cliente      INT NOT NULL REFERENCES clientes(id_cliente),
    id_usuario      INT NOT NULL REFERENCES usuarios(id_usuario),
    activo          BOOLEAN DEFAULT TRUE,
    fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_cliente, id_usuario)
);

-- ============================================================
-- 4. CATÁLOGOS: PRODUCTOS, INSUMOS, RECETAS (RF-13)
-- ============================================================
CREATE TABLE categorias_producto (
    id_categoria    SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    descripcion     VARCHAR(255)
);

CREATE TABLE unidades_medida (
    id_unidad       SERIAL PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL,
    abreviatura     VARCHAR(10) NOT NULL
);

CREATE TABLE insumos (
    id_insumo       SERIAL PRIMARY KEY,
    codigo          VARCHAR(30) UNIQUE NOT NULL,
    nombre          VARCHAR(150) NOT NULL,
    id_unidad       INT REFERENCES unidades_medida(id_unidad),
    stock_minimo    NUMERIC(12,3) DEFAULT 0,
    stock_maximo    NUMERIC(12,3),
    perecedero      BOOLEAN DEFAULT TRUE,
    activo          BOOLEAN DEFAULT TRUE
);

CREATE TABLE productos (
    id_producto     SERIAL PRIMARY KEY,
    codigo          VARCHAR(30) UNIQUE NOT NULL,
    nombre          VARCHAR(150) NOT NULL,
    id_categoria    INT REFERENCES categorias_producto(id_categoria),
    id_unidad       INT REFERENCES unidades_medida(id_unidad),
    precio_venta    NUMERIC(12,2) NOT NULL,
    vida_util_dias  INT,
    activo          BOOLEAN DEFAULT TRUE
);

CREATE TABLE recetas (
    id_receta       SERIAL PRIMARY KEY,
    id_producto     INT NOT NULL REFERENCES productos(id_producto),
    version         VARCHAR(10) NOT NULL,
    descripcion     VARCHAR(255),
    rendimiento     NUMERIC(12,3),
    id_unidad       INT REFERENCES unidades_medida(id_unidad),
    vigente         BOOLEAN DEFAULT TRUE,
    fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(id_producto, version)
);

CREATE TABLE receta_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_receta       INT NOT NULL REFERENCES recetas(id_receta) ON DELETE CASCADE,
    id_insumo       INT NOT NULL REFERENCES insumos(id_insumo),
    cantidad        NUMERIC(12,3) NOT NULL,
    id_unidad       INT REFERENCES unidades_medida(id_unidad),
    merma_esperada  NUMERIC(5,2) DEFAULT 0
);

-- ============================================================
-- 5. INVENTARIOS Y LOTES (RF-08 a RF-12)
-- ============================================================
CREATE TABLE lotes_insumos (
    id_lote_insumo  SERIAL PRIMARY KEY,
    id_insumo       INT NOT NULL REFERENCES insumos(id_insumo),
    numero_lote     VARCHAR(50) NOT NULL,
    id_proveedor    INT REFERENCES proveedores(id_proveedor),
    fecha_recepcion DATE NOT NULL,
    fecha_vencimiento DATE,
    cantidad_inicial NUMERIC(12,3) NOT NULL,
    cantidad_actual  NUMERIC(12,3) NOT NULL,
    costo_unitario  NUMERIC(12,4),
    estado          VARCHAR(20) DEFAULT 'disponible',
    UNIQUE(id_insumo, numero_lote)
);

CREATE INDEX idx_lotes_insumos_venc ON lotes_insumos(fecha_vencimiento)
    WHERE estado = 'disponible';

CREATE TABLE lotes_productos (
    id_lote_producto SERIAL PRIMARY KEY,
    id_producto      INT NOT NULL REFERENCES productos(id_producto),
    numero_lote      VARCHAR(50) NOT NULL UNIQUE,
    fecha_produccion DATE NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    cantidad_inicial NUMERIC(12,3) NOT NULL,
    cantidad_actual  NUMERIC(12,3) NOT NULL,
    estado           VARCHAR(20) DEFAULT 'disponible',
    id_orden_produccion INT,
    fecha_creacion   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_lotes_productos_venc ON lotes_productos(fecha_vencimiento)
    WHERE estado = 'disponible';

CREATE TABLE movimientos_inventario (
    id_movimiento   BIGSERIAL PRIMARY KEY,
    tipo_item       VARCHAR(20) NOT NULL,
    id_item         INT NOT NULL,
    id_lote         INT NOT NULL,
    tipo_movimiento VARCHAR(30) NOT NULL,
    cantidad        NUMERIC(12,3) NOT NULL,
    costo_unitario  NUMERIC(12,4),
    documento_ref   VARCHAR(50),
    id_usuario      INT REFERENCES usuarios(id_usuario),
    observacion     TEXT,
    fecha_movimiento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_mov_inv_item  ON movimientos_inventario(tipo_item, id_item);
CREATE INDEX idx_mov_inv_fecha ON movimientos_inventario(fecha_movimiento);

CREATE TABLE inventarios_fisicos (
    id_inventario   SERIAL PRIMARY KEY,
    fecha_inicio    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_fin       TIMESTAMP,
    id_usuario      INT REFERENCES usuarios(id_usuario),
    estado          VARCHAR(20) DEFAULT 'en_proceso',
    justificacion   TEXT
);

CREATE TABLE inventario_fisico_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_inventario   INT NOT NULL REFERENCES inventarios_fisicos(id_inventario) ON DELETE CASCADE,
    tipo_item       VARCHAR(20) NOT NULL,
    id_item         INT NOT NULL,
    id_lote         INT NOT NULL,
    cantidad_sistema NUMERIC(12,3) NOT NULL,
    cantidad_contada NUMERIC(12,3) NOT NULL,
    diferencia      NUMERIC(12,3) GENERATED ALWAYS AS (cantidad_contada - cantidad_sistema) STORED,
    justificacion   TEXT
);

-- ============================================================
-- 6. COMPRAS (RF-04 a RF-07)
-- ============================================================
CREATE TABLE solicitudes_compra (
    id_solicitud    SERIAL PRIMARY KEY,
    numero_solicitud VARCHAR(30) UNIQUE NOT NULL,
    id_usuario_solicita INT REFERENCES usuarios(id_usuario),
    fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    estado          VARCHAR(20) DEFAULT 'pendiente',
    observacion     TEXT
);

CREATE TABLE solicitud_compra_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_solicitud    INT NOT NULL REFERENCES solicitudes_compra(id_solicitud) ON DELETE CASCADE,
    id_insumo       INT NOT NULL REFERENCES insumos(id_insumo),
    cantidad        NUMERIC(12,3) NOT NULL
);

CREATE TABLE ordenes_compra (
    id_orden_compra SERIAL PRIMARY KEY,
    numero_orden    VARCHAR(30) UNIQUE NOT NULL,
    id_proveedor    INT NOT NULL REFERENCES proveedores(id_proveedor),
    id_solicitud    INT REFERENCES solicitudes_compra(id_solicitud),
    fecha_emision   DATE DEFAULT CURRENT_DATE,
    fecha_entrega_esperada DATE,
    estado          VARCHAR(20) DEFAULT 'emitida',
    subtotal        NUMERIC(12,2) DEFAULT 0,
    impuestos       NUMERIC(12,2) DEFAULT 0,
    total           NUMERIC(12,2) DEFAULT 0,
    id_usuario_crea INT REFERENCES usuarios(id_usuario),
    observacion     TEXT
);

CREATE TABLE orden_compra_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_orden_compra INT NOT NULL REFERENCES ordenes_compra(id_orden_compra) ON DELETE CASCADE,
    id_insumo       INT NOT NULL REFERENCES insumos(id_insumo),
    cantidad        NUMERIC(12,3) NOT NULL,
    precio_unitario NUMERIC(12,4) NOT NULL,
    subtotal        NUMERIC(12,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED
);

CREATE TABLE recepciones_compra (
    id_recepcion    SERIAL PRIMARY KEY,
    id_orden_compra INT NOT NULL REFERENCES ordenes_compra(id_orden_compra),
    numero_lote     VARCHAR(50) NOT NULL,
    fecha_recepcion DATE DEFAULT CURRENT_DATE,
    fecha_vencimiento DATE,
    cantidad_recibida NUMERIC(12,3) NOT NULL,
    id_lote_insumo  INT REFERENCES lotes_insumos(id_lote_insumo),
    id_usuario_recibe INT REFERENCES usuarios(id_usuario),
    observacion     TEXT
);

CREATE TABLE evaluaciones_proveedor (
    id_evaluacion   SERIAL PRIMARY KEY,
    id_proveedor    INT NOT NULL REFERENCES proveedores(id_proveedor),
    fecha_evaluacion DATE DEFAULT CURRENT_DATE,
    cumplimiento_entrega NUMERIC(3,2),
    calidad_producto     NUMERIC(3,2),
    precio               NUMERIC(3,2),
    calificacion_final   NUMERIC(3,2),
    id_usuario_evalua    INT REFERENCES usuarios(id_usuario),
    observacion          TEXT
);

-- ============================================================
-- 7. PRODUCCIÓN (RF-14 a RF-18)
-- ============================================================
CREATE TABLE ordenes_produccion (
    id_orden_produccion SERIAL PRIMARY KEY,
    numero_orden    VARCHAR(30) UNIQUE NOT NULL,
    id_producto     INT NOT NULL REFERENCES productos(id_producto),
    id_receta       INT NOT NULL REFERENCES recetas(id_receta),
    cantidad_planificada NUMERIC(12,3) NOT NULL,
    cantidad_producida   NUMERIC(12,3) DEFAULT 0,
    fecha_inicio    TIMESTAMP,
    fecha_fin       TIMESTAMP,
    estado          VARCHAR(20) DEFAULT 'planificada',
    id_usuario_responsable INT REFERENCES usuarios(id_usuario),
    observacion     TEXT,
    fecha_creacion  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE lotes_productos
    ADD CONSTRAINT fk_lote_producto_op
    FOREIGN KEY (id_orden_produccion) REFERENCES ordenes_produccion(id_orden_produccion);

CREATE TABLE consumo_insumos_produccion (
    id_consumo      SERIAL PRIMARY KEY,
    id_orden_produccion INT NOT NULL REFERENCES ordenes_produccion(id_orden_produccion) ON DELETE CASCADE,
    id_insumo       INT NOT NULL REFERENCES insumos(id_insumo),
    id_lote_insumo  INT NOT NULL REFERENCES lotes_insumos(id_lote_insumo),
    cantidad_consumida NUMERIC(12,3) NOT NULL,
    fecha_consumo   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mermas_produccion (
    id_merma        SERIAL PRIMARY KEY,
    id_orden_produccion INT NOT NULL REFERENCES ordenes_produccion(id_orden_produccion) ON DELETE CASCADE,
    tipo_merma      VARCHAR(50),
    id_insumo       INT REFERENCES insumos(id_insumo),
    cantidad        NUMERIC(12,3) NOT NULL,
    causa           VARCHAR(255),
    id_usuario_registra INT REFERENCES usuarios(id_usuario),
    fecha_registro  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 8. CALIDAD E INOCUIDAD (RF-17, RF-32)
-- ============================================================
CREATE TABLE controles_calidad (
    id_control      SERIAL PRIMARY KEY,
    id_lote_producto INT REFERENCES lotes_productos(id_lote_producto),
    id_lote_insumo  INT REFERENCES lotes_insumos(id_lote_insumo),
    tipo_control    VARCHAR(50) NOT NULL,
    resultado       VARCHAR(20) NOT NULL,
    valor_medido    NUMERIC(12,3),
    unidad_medida   VARCHAR(20),
    observacion     TEXT,
    id_usuario_responsable INT REFERENCES usuarios(id_usuario),
    fecha_control   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE documentos_calidad (
    id_documento    SERIAL PRIMARY KEY,
    tipo_documento  VARCHAR(50) NOT NULL,
    nombre_archivo  VARCHAR(255),
    ruta_archivo    VARCHAR(500),
    id_lote_producto INT REFERENCES lotes_productos(id_lote_producto),
    fecha_carga     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    id_usuario_carga INT REFERENCES usuarios(id_usuario)
);

-- ============================================================
-- 9. VENTAS Y PORTAL DE CLIENTES (RF-21 a RF-24, RF-36 a RF-43)
-- ============================================================
CREATE TABLE pedidos (
    id_pedido       SERIAL PRIMARY KEY,
    numero_pedido   VARCHAR(30) UNIQUE NOT NULL,
    id_cliente      INT NOT NULL REFERENCES clientes(id_cliente),
    fecha_pedido    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_entrega_estimada DATE,
    origen          VARCHAR(20) DEFAULT 'vendedor',
    estado          VARCHAR(20) DEFAULT 'pendiente',
    subtotal        NUMERIC(12,2) DEFAULT 0,
    impuestos       NUMERIC(12,2) DEFAULT 0,
    total           NUMERIC(12,2) DEFAULT 0,
    id_usuario_confirma INT REFERENCES usuarios(id_usuario),
    observacion     TEXT
);

CREATE TABLE pedido_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_pedido       INT NOT NULL REFERENCES pedidos(id_pedido) ON DELETE CASCADE,
    id_producto     INT NOT NULL REFERENCES productos(id_producto),
    cantidad        NUMERIC(12,3) NOT NULL,
    precio_unitario NUMERIC(12,2) NOT NULL,
    subtotal        NUMERIC(12,2) GENERATED ALWAYS AS (cantidad * precio_unitario) STORED
);

CREATE TABLE pedido_lotes (
    id_pedido_lote  SERIAL PRIMARY KEY,
    id_pedido       INT NOT NULL REFERENCES pedidos(id_pedido) ON DELETE CASCADE,
    id_lote_producto INT NOT NULL REFERENCES lotes_productos(id_lote_producto),
    cantidad        NUMERIC(12,3) NOT NULL
);

CREATE TABLE facturas (
    id_factura      SERIAL PRIMARY KEY,
    numero_factura  VARCHAR(30) UNIQUE NOT NULL,
    id_pedido       INT REFERENCES pedidos(id_pedido),
    id_cliente      INT NOT NULL REFERENCES clientes(id_cliente),
    fecha_emision   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subtotal        NUMERIC(12,2) NOT NULL,
    impuestos       NUMERIC(12,2) NOT NULL,
    total           NUMERIC(12,2) NOT NULL,
    estado          VARCHAR(20) DEFAULT 'emitida',
    saldo_pendiente NUMERIC(12,2) DEFAULT 0,
    id_usuario_emite INT REFERENCES usuarios(id_usuario)
);

CREATE TABLE notas_despacho (
    id_nota         SERIAL PRIMARY KEY,
    numero_nota     VARCHAR(30) UNIQUE NOT NULL,
    id_factura      INT REFERENCES facturas(id_factura),
    id_pedido       INT REFERENCES pedidos(id_pedido),
    fecha_despacho  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transportista   VARCHAR(150),
    direccion_entrega VARCHAR(255),
    estado          VARCHAR(20) DEFAULT 'emitida',
    id_usuario_despacha INT REFERENCES usuarios(id_usuario)
);

CREATE TABLE cuentas_por_cobrar (
    id_cxc          SERIAL PRIMARY KEY,
    id_factura      INT NOT NULL REFERENCES facturas(id_factura),
    id_cliente      INT NOT NULL REFERENCES clientes(id_cliente),
    monto_original  NUMERIC(12,2) NOT NULL,
    saldo           NUMERIC(12,2) NOT NULL,
    fecha_vencimiento DATE,
    estado          VARCHAR(20) DEFAULT 'pendiente'
);

CREATE TABLE pagos_cliente (
    id_pago         SERIAL PRIMARY KEY,
    id_cxc          INT NOT NULL REFERENCES cuentas_por_cobrar(id_cxc),
    monto           NUMERIC(12,2) NOT NULL,
    fecha_pago      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metodo_pago     VARCHAR(50),
    referencia      VARCHAR(100),
    id_usuario_registra INT REFERENCES usuarios(id_usuario)
);

CREATE TABLE reclamos_cliente (
    id_reclamo      SERIAL PRIMARY KEY,
    numero_reclamo  VARCHAR(30) UNIQUE NOT NULL,
    id_cliente      INT NOT NULL REFERENCES clientes(id_cliente),
    id_factura      INT REFERENCES facturas(id_factura),
    id_lote_producto INT REFERENCES lotes_productos(id_lote_producto),
    descripcion     TEXT NOT NULL,
    estado          VARCHAR(20) DEFAULT 'abierto',
    fecha_reclamo   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_resolucion TIMESTAMP,
    id_usuario_atendio INT REFERENCES usuarios(id_usuario),
    resolucion      TEXT
);

-- ============================================================
-- 10. CONTABILIDAD Y FINANZAS (RF-25 a RF-28)
-- ============================================================
CREATE TABLE plan_cuentas (
    id_cuenta       SERIAL PRIMARY KEY,
    codigo          VARCHAR(20) UNIQUE NOT NULL,
    nombre          VARCHAR(150) NOT NULL,
    tipo            VARCHAR(30) NOT NULL,
    naturaleza      CHAR(1) NOT NULL,
    cuenta_padre    INT REFERENCES plan_cuentas(id_cuenta),
    activa          BOOLEAN DEFAULT TRUE
);

CREATE TABLE asientos_contables (
    id_asiento      SERIAL PRIMARY KEY,
    numero_asiento  VARCHAR(30) UNIQUE NOT NULL,
    fecha_asiento   DATE NOT NULL,
    descripcion     VARCHAR(255),
    tipo_origen     VARCHAR(30),
    id_origen       INT,
    estado          VARCHAR(20) DEFAULT 'registrado',
    id_usuario_registra INT REFERENCES usuarios(id_usuario),
    fecha_registro  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE asiento_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_asiento      INT NOT NULL REFERENCES asientos_contables(id_asiento) ON DELETE CASCADE,
    id_cuenta       INT NOT NULL REFERENCES plan_cuentas(id_cuenta),
    debe            NUMERIC(14,2) DEFAULT 0,
    haber           NUMERIC(14,2) DEFAULT 0,
    CONSTRAINT chk_debe_haber CHECK (
        (debe > 0 AND haber = 0) OR (haber > 0 AND debe = 0)
    )
);

CREATE TABLE cuentas_por_pagar (
    id_cxp          SERIAL PRIMARY KEY,
    id_orden_compra INT NOT NULL REFERENCES ordenes_compra(id_orden_compra),
    id_proveedor    INT NOT NULL REFERENCES proveedores(id_proveedor),
    monto_original  NUMERIC(12,2) NOT NULL,
    saldo           NUMERIC(12,2) NOT NULL,
    fecha_vencimiento DATE,
    estado          VARCHAR(20) DEFAULT 'pendiente'
);

CREATE TABLE pagos_proveedor (
    id_pago         SERIAL PRIMARY KEY,
    id_cxp          INT NOT NULL REFERENCES cuentas_por_pagar(id_cxp),
    monto           NUMERIC(12,2) NOT NULL,
    fecha_pago      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metodo_pago     VARCHAR(50),
    referencia      VARCHAR(100),
    id_usuario_registra INT REFERENCES usuarios(id_usuario)
);

CREATE TABLE costos_produccion (
    id_costo        SERIAL PRIMARY KEY,
    id_orden_produccion INT NOT NULL REFERENCES ordenes_produccion(id_orden_produccion),
    costo_insumos   NUMERIC(12,2) DEFAULT 0,
    costo_mano_obra NUMERIC(12,2) DEFAULT 0,
    costo_indirecto NUMERIC(12,2) DEFAULT 0,
    costo_total     NUMERIC(12,2) DEFAULT 0,
    costo_unitario  NUMERIC(12,4) DEFAULT 0,
    fecha_calculo   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 11. RECURSOS HUMANOS (RF-29, RF-30)
-- ============================================================
CREATE TABLE cargos (
    id_cargo        SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    descripcion     VARCHAR(255),
    salario_base    NUMERIC(12,2)
);

CREATE TABLE empleados (
    id_empleado     SERIAL PRIMARY KEY,
    codigo_empleado VARCHAR(20) UNIQUE NOT NULL,
    nombres         VARCHAR(100) NOT NULL,
    apellidos       VARCHAR(100) NOT NULL,
    ci              VARCHAR(20) UNIQUE,
    fecha_nacimiento DATE,
    telefono        VARCHAR(20),
    email           VARCHAR(150),
    direccion       VARCHAR(255),
    id_cargo        INT REFERENCES cargos(id_cargo),
    fecha_ingreso   DATE NOT NULL,
    fecha_baja      DATE,
    activo          BOOLEAN DEFAULT TRUE
);

CREATE TABLE asistencias (
    id_asistencia   BIGSERIAL PRIMARY KEY,
    id_empleado     INT NOT NULL REFERENCES empleados(id_empleado),
    fecha           DATE NOT NULL,
    hora_entrada    TIME,
    hora_salida     TIME,
    horas_trabajadas NUMERIC(5,2),
    observacion     VARCHAR(255),
    UNIQUE(id_empleado, fecha)
);

CREATE TABLE capacitaciones (
    id_capacitacion SERIAL PRIMARY KEY,
    nombre          VARCHAR(150) NOT NULL,
    tipo            VARCHAR(50),
    fecha_inicio    DATE,
    fecha_fin       DATE,
    vigencia_meses  INT,
    obligatoria     BOOLEAN DEFAULT TRUE
);

CREATE TABLE empleado_capacitaciones (
    id_registro     SERIAL PRIMARY KEY,
    id_empleado     INT NOT NULL REFERENCES empleados(id_empleado),
    id_capacitacion INT NOT NULL REFERENCES capacitaciones(id_capacitacion),
    fecha_realizacion DATE NOT NULL,
    fecha_vencimiento DATE,
    aprobado        BOOLEAN DEFAULT TRUE,
    UNIQUE(id_empleado, id_capacitacion, fecha_realizacion)
);

CREATE TABLE nominas (
    id_nomina       SERIAL PRIMARY KEY,
    periodo         VARCHAR(20) NOT NULL,
    fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_haberes   NUMERIC(14,2) DEFAULT 0,
    total_descuentos NUMERIC(14,2) DEFAULT 0,
    total_neto      NUMERIC(14,2) DEFAULT 0,
    estado          VARCHAR(20) DEFAULT 'borrador'
);

CREATE TABLE nomina_detalle (
    id_detalle      SERIAL PRIMARY KEY,
    id_nomina       INT NOT NULL REFERENCES nominas(id_nomina) ON DELETE CASCADE,
    id_empleado     INT NOT NULL REFERENCES empleados(id_empleado),
    haberes         NUMERIC(12,2) NOT NULL,
    descuentos      NUMERIC(12,2) NOT NULL,
    neto            NUMERIC(12,2) NOT NULL
);

-- ============================================================
-- 12. VISTAS
-- ============================================================
CREATE OR REPLACE VIEW v_stock_insumos AS
SELECT i.id_insumo, i.codigo, i.nombre, i.stock_minimo,
       COALESCE(SUM(li.cantidad_actual), 0) AS stock_actual,
       CASE WHEN COALESCE(SUM(li.cantidad_actual), 0) <= i.stock_minimo
            THEN 'REPONER' ELSE 'OK' END AS estado_stock
FROM insumos i
LEFT JOIN lotes_insumos li
       ON li.id_insumo = i.id_insumo AND li.estado = 'disponible'
GROUP BY i.id_insumo, i.codigo, i.nombre, i.stock_minimo;

CREATE OR REPLACE VIEW v_productos_por_vencer AS
SELECT lp.id_lote_producto, p.codigo, p.nombre AS producto,
       lp.numero_lote, lp.fecha_vencimiento,
       (lp.fecha_vencimiento - CURRENT_DATE) AS dias_para_vencer,
       lp.cantidad_actual
FROM lotes_productos lp
JOIN productos p ON p.id_producto = lp.id_producto
WHERE lp.estado = 'disponible'
  AND lp.cantidad_actual > 0
  AND lp.fecha_vencimiento <= CURRENT_DATE + INTERVAL '30 days'
ORDER BY lp.fecha_vencimiento;

CREATE OR REPLACE VIEW v_trazabilidad_atras AS
SELECT lp.numero_lote AS lote_producto, p.nombre AS producto,
       li.numero_lote AS lote_insumo, i.nombre AS insumo,
       pr.razon_social AS proveedor,
       cip.cantidad_consumida, cip.fecha_consumo
FROM lotes_productos lp
JOIN productos p ON p.id_producto = lp.id_producto
JOIN consumo_insumos_produccion cip ON cip.id_orden_produccion = lp.id_orden_produccion
JOIN lotes_insumos li ON li.id_lote_insumo = cip.id_lote_insumo
JOIN insumos i ON i.id_insumo = cip.id_insumo
LEFT JOIN proveedores pr ON pr.id_proveedor = li.id_proveedor;

CREATE OR REPLACE VIEW v_trazabilidad_adelante AS
SELECT lp.numero_lote AS lote_producto, p.nombre AS producto,
       c.razon_social AS cliente, f.numero_factura,
       pl.cantidad, f.fecha_emision
FROM lotes_productos lp
JOIN productos p ON p.id_producto = lp.id_producto
JOIN pedido_lotes pl ON pl.id_lote_producto = lp.id_lote_producto
JOIN pedidos pe ON pe.id_pedido = pl.id_pedido
JOIN clientes c ON c.id_cliente = pe.id_cliente
LEFT JOIN facturas f ON f.id_pedido = pe.id_pedido;

CREATE OR REPLACE VIEW v_panel_gerencial AS
SELECT
    (SELECT COUNT(*) FROM pedidos WHERE estado = 'pendiente') AS pedidos_pendientes,
    (SELECT COUNT(*) FROM ordenes_produccion WHERE estado = 'en_proceso') AS ops_en_proceso,
    (SELECT COUNT(*) FROM v_productos_por_vencer) AS lotes_por_vencer,
    (SELECT COUNT(*) FROM reclamos_cliente WHERE estado = 'abierto') AS reclamos_abiertos,
    (SELECT COALESCE(SUM(total),0) FROM facturas
        WHERE fecha_emision::date = CURRENT_DATE) AS ventas_hoy;

-- ============================================================
-- 13. FUNCIONES Y TRIGGERS
-- ============================================================

-- Actualizar fecha_actualizacion en usuarios
CREATE OR REPLACE FUNCTION fn_actualizar_fecha()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_actualizacion = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_usuarios_update
BEFORE UPDATE ON usuarios
FOR EACH ROW EXECUTE FUNCTION fn_actualizar_fecha();

-- Descontar stock de insumo al consumir en producción
CREATE OR REPLACE FUNCTION fn_descontar_lote_insumo()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE lotes_insumos
       SET cantidad_actual = cantidad_actual - NEW.cantidad_consumida,
           estado = CASE WHEN cantidad_actual - NEW.cantidad_consumida <= 0
                         THEN 'agotado' ELSE estado END
     WHERE id_lote_insumo = NEW.id_lote_insumo;

    INSERT INTO movimientos_inventario
        (tipo_item, id_item, id_lote, tipo_movimiento, cantidad, documento_ref)
    VALUES
        ('insumo', NEW.id_insumo, NEW.id_lote_insumo, 'produccion',
         -NEW.cantidad_consumida, 'OP:' || NEW.id_orden_produccion);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_consumo_insumo
AFTER INSERT ON consumo_insumos_produccion
FOR EACH ROW EXECUTE FUNCTION fn_descontar_lote_insumo();

-- Descontar stock de producto al asignarlo a un pedido
CREATE OR REPLACE FUNCTION fn_descontar_lote_producto()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE lotes_productos
       SET cantidad_actual = cantidad_actual - NEW.cantidad,
           estado = CASE WHEN cantidad_actual - NEW.cantidad <= 0
                         THEN 'agotado' ELSE estado END
     WHERE id_lote_producto = NEW.id_lote_producto;

    INSERT INTO movimientos_inventario
        (tipo_item, id_item, id_lote, tipo_movimiento, cantidad, documento_ref)
    SELECT 'producto', lp.id_producto, NEW.id_lote_producto, 'despacho',
           -NEW.cantidad, 'PED:' || NEW.id_pedido
    FROM lotes_productos lp
    WHERE lp.id_lote_producto = NEW.id_lote_producto;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_despacho_producto
AFTER INSERT ON pedido_lotes
FOR EACH ROW EXECUTE FUNCTION fn_descontar_lote_producto();

-- ============================================================
-- 14. DATOS SEMILLA MÍNIMOS
-- ============================================================
INSERT INTO unidades_medida (nombre, abreviatura) VALUES
('Kilogramo','kg'), ('Litro','lt'), ('Unidad','und'), ('Caja','cja'), ('Gramo','g');

INSERT INTO categorias_producto (nombre, descripcion) VALUES
('Lácteos','Productos derivados de la leche'),
('Panificados','Productos de panadería'),
('Conservas','Alimentos en conserva');

-- Usuario administrador (password: Admin123* → cambiar en producción)
INSERT INTO usuarios (nombre_usuario, email, password_hash, nombre_completo, id_rol)
VALUES ('admin', 'admin@erp.local',
        crypt('Admin123*', gen_salt('bf')),
        'Administrador del Sistema', 8);

-- ============================================================
-- 15. VERIFICACIÓN FINAL
-- ============================================================
SELECT 'Tablas creadas: ' || COUNT(*) AS resultado
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';

SELECT 'Vistas creadas: ' || COUNT(*) AS resultado
FROM information_schema.views
WHERE table_schema = 'public';
-- PARA METER DATOS A LA BASE DE DATOS 
-- ============================================================
-- DATOS DE PRUEBA — 10 registros por tabla
-- ERP Manufactura de Alimentos
-- ============================================================

BEGIN;

-- ============================================================
-- 1. ROLES (10)
-- ============================================================
INSERT INTO roles (nombre, descripcion) VALUES
('gerente',         'Acceso total a reportes y decisiones'),
('jefe_produccion', 'Gestión de producción y recetas'),
('almacenero',      'Control de inventarios y lotes'),
('comprador',       'Gestión de compras y proveedores'),
('vendedor',        'Gestión de ventas y pedidos'),
('contador',        'Contabilidad y finanzas'),
('calidad',         'Controles de calidad e inocuidad'),
('administrador',   'Administración del sistema'),
('cliente',         'Acceso al portal de clientes'),
('rrhh',            'Recursos humanos y nómina')
ON CONFLICT (nombre) DO NOTHING;

-- ============================================================
-- 2. USUARIOS (10)
-- ============================================================
INSERT INTO usuarios (nombre_usuario, email, password_hash, nombre_completo, id_rol) VALUES
('gerente1',  'gerente1@erp.local',  crypt('Pass123*', gen_salt('bf')), 'Carlos Mamani Quispe',      1),
('jproduc1',  'jproduc1@erp.local',  crypt('Pass123*', gen_salt('bf')), 'María Flores Choque',       2),
('almacen1',  'almacen1@erp.local',  crypt('Pass123*', gen_salt('bf')), 'Juan Condori Apaza',        3),
('compra1',   'compra1@erp.local',   crypt('Pass123*', gen_salt('bf')), 'Ana Ticona Vargas',         4),
('vende1',    'vende1@erp.local',    crypt('Pass123*', gen_salt('bf')), 'Luis Callisaya Sumi',       5),
('conta1',    'conta1@erp.local',    crypt('Pass123*', gen_salt('bf')), 'Patricia Zenteno Ruiz',     6),
('calidad1',  'calidad1@erp.local',  crypt('Pass123*', gen_salt('bf')), 'Roberto Villacorta Nina',   7),
('admin1',    'admin1@erp.local',    crypt('Pass123*', gen_salt('bf')), 'Administrador Sistema',     8),
('cliente1',  'cliente1@erp.local',  crypt('Pass123*', gen_salt('bf')), 'Distribuidora El Sol',      9),
('rrhh1',     'rrhh1@erp.local',     crypt('Pass123*', gen_salt('bf')), 'Silvia Tarqui Loza',        10)
ON CONFLICT (nombre_usuario) DO NOTHING;

-- ============================================================
-- 3. AUDITORÍA (10)
-- ============================================================
INSERT INTO auditoria (id_usuario, accion, tabla_afectada, registro_id, ip_origen) VALUES
(1,'LOGIN','usuarios','1','192.168.1.10'),
(2,'INSERT','ordenes_produccion','1','192.168.1.11'),
(3,'UPDATE','lotes_insumos','1','192.168.1.12'),
(4,'INSERT','ordenes_compra','1','192.168.1.13'),
(5,'INSERT','pedidos','1','192.168.1.14'),
(6,'INSERT','asientos_contables','1','192.168.1.15'),
(7,'INSERT','controles_calidad','1','192.168.1.16'),
(8,'BACKUP','base_datos',NULL,'192.168.1.17'),
(9,'LOGIN','usuarios','9','192.168.1.18'),
(10,'INSERT','empleados','1','192.168.1.19');

-- ============================================================
-- 4. PROVEEDORES (10)
-- ============================================================
INSERT INTO proveedores (nit, razon_social, nombre_contacto, telefono, email, direccion, condiciones_comerciales, calificacion) VALUES
('1000001','Lácteos del Altiplano SRL','Pedro Quispe','2222333','ventas@lacteosaltiplano.bo','El Alto, La Paz','Crédito 30 días',4.50),
('1000002','Harinas Bolivianas SA','Rosa Mamani','2222334','ventas@harinasbol.bo','Cochabamba','Crédito 15 días',4.20),
('1000003','Azúcares del Norte SRL','Jorge Rojas','2222335','ventas@azucaresnorte.bo','Santa Cruz','Contado',4.80),
('1000004','Empaques Plásticos Andinos','Lucía Vargas','2222336','ventas@empaquesandinos.bo','El Alto, La Paz','Crédito 45 días',3.90),
('1000005','Frutas y Conservas del Valle','Mario Choque','2222337','ventas@frutasvalle.bo','Cochabamba','Crédito 30 días',4.10),
('1000006','Especias y Condimentos SRL','Elena Apaza','2222338','ventas@especias.bo','La Paz','Contado',4.60),
('1000007','Aceites y Grasas Bolivia','Raúl Ticona','2222339','ventas@aceitesbol.bo','Santa Cruz','Crédito 30 días',4.30),
('1000008','Insumos Químicos Andinos','Sofía Loza','2222340','ventas@quimicosandinos.bo','Oruro','Crédito 60 días',3.80),
('1000009','Verduras Frescas del Altiplano','Hugo Nina','2222341','ventas@verdurasaltiplano.bo','El Alto, La Paz','Contado',4.70),
('1000010','Envases y Etiquetas SRL','Carmen Callisaya','2222342','ventas@envasesetiquetas.bo','La Paz','Crédito 30 días',4.00);

-- ============================================================
-- 5. CLIENTES (10)
-- ============================================================
INSERT INTO clientes (nit_ci, razon_social, nombre_contacto, telefono, email, direccion, limite_credito) VALUES
('2000001','Distribuidora El Sol','Ana Pérez','3333001','compras@elsol.bo','La Paz',50000),
('2000002','Supermercados Andinos','Luis Gómez','3333002','compras@superandinos.bo','La Paz',80000),
('2000003','Tienda Doña Rosa','Rosa Flores','3333003','rosita@mail.com','El Alto',10000),
('2000004','Mercado Central','Pedro Layme','3333004','pedrol@mail.com','La Paz',15000),
('2000005','Comercial La Paz SRL','María Quispe','3333005','compras@comlaps.bo','La Paz',60000),
('2000006','Minimarket San Pedro','Jorge Mamani','3333006','jorgem@mail.com','La Paz',8000),
('2000007','Distribuidora Norte','Carmen Rojas','3333007','compras@distnorte.bo','El Alto',45000),
('2000008','Almacén Popular','Silvia Ticona','3333008','silviat@mail.com','El Alto',12000),
('2000009','Comercial Sur SRL','Raúl Apaza','3333009','compras@comsur.bo','La Paz',70000),
('2000010','Tienda La Estrella','Elena Condori','3333010','elenac@mail.com','El Alto',9000);

-- ============================================================
-- 6. CUENTAS CLIENTE (10)
-- ============================================================
INSERT INTO cuentas_cliente (id_cliente, id_usuario) VALUES
(1,9),(2,9),(3,9),(4,9),(5,9),(6,9),(7,9),(8,9),(9,9),(10,9);

-- ============================================================
-- 7. CATEGORÍAS PRODUCTO (10)
-- ============================================================
INSERT INTO categorias_producto (nombre, descripcion) VALUES
('Lácteos','Leche, yogur, queso'),
('Panificados','Pan, galletas, pasteles'),
('Conservas','Mermeladas, encurtidos'),
('Bebidas','Jugos, refrescos'),
('Snacks','Papas fritas, frutos secos'),
('Congelados','Productos congelados'),
('Cereales','Avena, quinua, maíz'),
('Salsas','Mayonesa, ketchup, ají'),
('Dulces','Chocolates, caramelos'),
('Comidas preparadas','Platos listos para consumir');

-- ============================================================
-- 8. UNIDADES DE MEDIDA (10)
-- ============================================================
INSERT INTO unidades_medida (nombre, abreviatura) VALUES
('Kilogramo','kg'),('Litro','lt'),('Unidad','und'),('Caja','cja'),
('Gramo','g'),('Mililitro','ml'),('Bolsa','bls'),('Paquete','pqt'),
('Docena','doc'),('Tonelada','tn');

-- ============================================================
-- 9. INSUMOS (10)
-- ============================================================
INSERT INTO insumos (codigo, nombre, id_unidad, stock_minimo, stock_maximo, perecedero) VALUES
('INS001','Leche cruda',1,500,2000,TRUE),
('INS002','Harina de trigo',1,300,1500,TRUE),
('INS003','Azúcar refinada',1,200,1000,TRUE),
('INS004','Sal fina',1,50,300,TRUE),
('INS005','Mantequilla',1,40,200,TRUE),
('INS006','Huevos',3,100,500,TRUE),
('INS007','Levadura',5,10,50,TRUE),
('INS008','Esencia de vainilla',6,5,30,TRUE),
('INS009','Envase plástico 1L',3,1000,5000,FALSE),
('INS010','Etiqueta adhesiva',3,2000,10000,FALSE);

-- ============================================================
-- 10. PRODUCTOS (10)
-- ============================================================
INSERT INTO productos (codigo, nombre, id_categoria, id_unidad, precio_venta, vida_util_dias) VALUES
('PROD001','Yogur natural 1L',1,3,12.50,30),
('PROD002','Queso fresco 500g',1,3,25.00,20),
('PROD003','Pan de molde',2,3,15.00,7),
('PROD004','Galletas de avena',2,3,8.00,60),
('PROD005','Mermelada de fresa',3,3,18.00,180),
('PROD006','Jugo de naranja 1L',4,3,14.00,15),
('PROD007','Papas fritas 200g',5,3,10.00,90),
('PROD008','Avena instantánea',7,3,9.00,365),
('PROD009','Mayonesa 500g',8,3,16.00,180),
('PROD010','Chocolate en barra',9,3,7.00,240);

-- ============================================================
-- 11. RECETAS (10)
-- ============================================================
INSERT INTO recetas (id_producto, version, descripcion, rendimiento, id_unidad) VALUES
(1,'v1','Yogur natural tradicional',100,2),
(2,'v1','Queso fresco artesanal',50,1),
(3,'v1','Pan de molde blanco',80,3),
(4,'v1','Galletas de avena',120,3),
(5,'v1','Mermelada de fresa casera',60,3),
(6,'v1','Jugo de naranja natural',100,2),
(7,'v1','Papas fritas crujientes',50,1),
(8,'v1','Avena instantánea',100,1),
(9,'v1','Mayonesa clásica',40,3),
(10,'v1','Chocolate en barra',80,3);

-- ============================================================
-- 12. RECETA DETALLE (10)
-- ============================================================
INSERT INTO receta_detalle (id_receta, id_insumo, cantidad, id_unidad, merma_esperada) VALUES
(1,1,80,2,2.0),
(2,1,40,2,3.0),
(3,2,50,1,1.5),
(4,2,30,1,2.0),
(5,3,25,1,1.0),
(6,3,10,1,0.5),
(7,4,5,1,1.0),
(8,7,2,5,0.5),
(9,6,30,3,2.0),
(10,5,20,1,1.5);

-- ============================================================
-- 13. LOTES INSUMOS (10)
-- ============================================================
INSERT INTO lotes_insumos (id_insumo, numero_lote, id_proveedor, fecha_recepcion, fecha_vencimiento, cantidad_inicial, cantidad_actual, costo_unitario, estado) VALUES
(1,'LI-2026-001',1,'2026-01-05','2026-02-05',500,450,4.50,'disponible'),
(2,'LI-2026-002',2,'2026-01-06','2026-04-06',400,380,3.20,'disponible'),
(3,'LI-2026-003',3,'2026-01-07','2026-06-07',300,290,2.80,'disponible'),
(4,'LI-2026-004',6,'2026-01-08','2026-07-08',100,95,1.50,'disponible'),
(5,'LI-2026-005',1,'2026-01-09','2026-03-09',80,70,12.00,'disponible'),
(6,'LI-2026-006',5,'2026-01-10','2026-02-10',200,180,0.80,'disponible'),
(7,'LI-2026-007',2,'2026-01-11','2026-08-11',50,45,8.00,'disponible'),
(8,'LI-2026-008',6,'2026-01-12','2026-12-12',30,28,15.00,'disponible'),
(9,'LI-2026-009',4,'2026-01-13',NULL,2000,1800,0.30,'disponible'),
(10,'LI-2026-010',10,'2026-01-14',NULL,5000,4700,0.05,'disponible');

-- ============================================================
-- 14. LOTES PRODUCTOS (10)
-- ============================================================
INSERT INTO lotes_productos (id_producto, numero_lote, fecha_produccion, fecha_vencimiento, cantidad_inicial, cantidad_actual, estado) VALUES
(1,'LP-2026-001','2026-01-15','2026-02-14',100,90,'disponible'),
(2,'LP-2026-002','2026-01-16','2026-02-05',50,45,'disponible'),
(3,'LP-2026-003','2026-01-17','2026-01-24',80,70,'disponible'),
(4,'LP-2026-004','2026-01-18','2026-03-19',120,110,'disponible'),
(5,'LP-2026-005','2026-01-19','2026-07-18',60,55,'disponible'),
(6,'LP-2026-006','2026-01-20','2026-02-04',100,95,'disponible'),
(7,'LP-2026-007','2026-01-21','2026-04-21',50,48,'disponible'),
(8,'LP-2026-008','2026-01-22','2027-01-22',100,98,'disponible'),
(9,'LP-2026-009','2026-01-23','2026-07-22',40,38,'disponible'),
(10,'LP-2026-010','2026-01-24','2026-09-22',80,79,'disponible');

-- ============================================================
-- 15. MOVIMIENTOS INVENTARIO (10)
-- ============================================================
INSERT INTO movimientos_inventario (tipo_item, id_item, id_lote, tipo_movimiento, cantidad, costo_unitario, documento_ref, id_usuario) VALUES
('insumo',1,1,'entrada',500,4.50,'OC-001',4),
('insumo',2,2,'entrada',400,3.20,'OC-002',4),
('insumo',3,3,'entrada',300,2.80,'OC-003',4),
('producto',1,1,'produccion',100,8.00,'OP-001',2),
('producto',2,2,'produccion',50,15.00,'OP-002',2),
('producto',3,3,'produccion',80,9.00,'OP-003',2),
('producto',1,1,'despacho',10,12.50,'PED-001',5),
('producto',2,2,'despacho',5,25.00,'PED-002',5),
('producto',3,3,'despacho',10,15.00,'PED-003',5),
('insumo',1,1,'merma',5,4.50,'MERMA-01',2);

-- ============================================================
-- 16. INVENTARIOS FÍSICOS (10)
-- ============================================================
INSERT INTO inventarios_fisicos (id_usuario, estado, justificacion) VALUES
(3,'cerrado','Inventario mensual enero'),
(3,'cerrado','Inventario mensual febrero'),
(3,'cerrado','Inventario semanal'),
(3,'cerrado','Inventario trimestral'),
(3,'cerrado','Inventario mensual marzo'),
(3,'en_proceso','Inventario abril'),
(3,'cerrado','Inventario mayo'),
(3,'cerrado','Inventario junio'),
(3,'cerrado','Inventario julio'),
(3,'en_proceso','Inventario agosto');

-- ============================================================
-- 17. INVENTARIO FÍSICO DETALLE (10)
-- ============================================================
INSERT INTO inventario_fisico_detalle (id_inventario, tipo_item, id_item, id_lote, cantidad_sistema, cantidad_contada, justificacion) VALUES
(1,'insumo',1,1,450,448,'Diferencia por merma'),
(2,'insumo',2,2,380,379,'Diferencia mínima'),
(3,'insumo',3,3,290,290,'Sin diferencias'),
(4,'producto',1,1,90,89,'Rotura de envase'),
(5,'producto',2,2,45,45,'Sin diferencias'),
(6,'producto',3,3,70,69,'Vencimiento'),
(7,'insumo',5,5,70,70,'Sin diferencias'),
(8,'insumo',6,6,180,178,'Merma'),
(9,'producto',5,5,55,55,'Sin diferencias'),
(10,'producto',8,8,98,97,'Rotura');

-- ============================================================
-- 18. SOLICITUDES COMPRA (10)
-- ============================================================
INSERT INTO solicitudes_compra (numero_solicitud, id_usuario_solicita, estado, observacion) VALUES
('SC-2026-001',3,'atendida','Reposición de leche'),
('SC-2026-002',3,'atendida','Reposición de harina'),
('SC-2026-003',3,'atendida','Reposición de azúcar'),
('SC-2026-004',3,'aprobada','Compra de sal'),
('SC-2026-005',3,'pendiente','Compra de mantequilla'),
('SC-2026-006',3,'aprobada','Compra de huevos'),
('SC-2026-007',3,'pendiente','Compra de levadura'),
('SC-2026-008',3,'atendida','Compra de esencia'),
('SC-2026-009',3,'rechazada','Compra de envases'),
('SC-2026-010',3,'pendiente','Compra de etiquetas');

-- ============================================================
-- 19. SOLICITUD COMPRA DETALLE (10)
-- ============================================================
INSERT INTO solicitud_compra_detalle (id_solicitud, id_insumo, cantidad) VALUES
(1,1,500),(2,2,400),(3,3,300),(4,4,100),(5,5,80),
(6,6,200),(7,7,50),(8,8,30),(9,9,2000),(10,10,5000);

-- ============================================================
-- 20. ÓRDENES COMPRA (10)
-- ============================================================
INSERT INTO ordenes_compra (numero_orden, id_proveedor, id_solicitud, fecha_emision, fecha_entrega_esperada, estado, subtotal, impuestos, total, id_usuario_crea) VALUES
('OC-2026-001',1,1,'2026-01-02','2026-01-05','recibida',2250,292.50,2542.50,4),
('OC-2026-002',2,2,'2026-01-03','2026-01-06','recibida',1280,166.40,1446.40,4),
('OC-2026-003',3,3,'2026-01-04','2026-01-07','recibida',840,109.20,949.20,4),
('OC-2026-004',6,4,'2026-01-05','2026-01-08','recibida',150,19.50,169.50,4),
('OC-2026-005',1,5,'2026-01-06','2026-01-09','recibida',960,124.80,1084.80,4),
('OC-2026-006',5,6,'2026-01-07','2026-01-10','recibida',160,20.80,180.80,4),
('OC-2026-007',2,7,'2026-01-08','2026-01-11','recibida',400,52.00,452.00,4),
('OC-2026-008',6,8,'2026-01-09','2026-01-12','recibida',450,58.50,508.50,4),
('OC-2026-009',4,9,'2026-01-10','2026-01-13','anulada',600,78.00,678.00,4),
('OC-2026-010',10,10,'2026-01-11','2026-01-14','emitida',250,32.50,282.50,4);

-- ============================================================
-- 21. ORDEN COMPRA DETALLE (10)
-- ============================================================
INSERT INTO orden_compra_detalle (id_orden_compra, id_insumo, cantidad, precio_unitario) VALUES
(1,1,500,4.50),(2,2,400,3.20),(3,3,300,2.80),(4,4,100,1.50),
(5,5,80,12.00),(6,6,200,0.80),(7,7,50,8.00),(8,8,30,15.00),
(9,9,2000,0.30),(10,10,5000,0.05);

-- ============================================================
-- 22. RECEPCIONES COMPRA (10)
-- ============================================================
INSERT INTO recepciones_compra (id_orden_compra, numero_lote, fecha_recepcion, fecha_vencimiento, cantidad_recibida, id_lote_insumo, id_usuario_recibe) VALUES
(1,'LI-2026-001','2026-01-05','2026-02-05',500,1,3),
(2,'LI-2026-002','2026-01-06','2026-04-06',400,2,3),
(3,'LI-2026-003','2026-01-07','2026-06-07',300,3,3),
(4,'LI-2026-004','2026-01-08','2026-07-08',100,4,3),
(5,'LI-2026-005','2026-01-09','2026-03-09',80,5,3),
(6,'LI-2026-006','2026-01-10','2026-02-10',200,6,3),
(7,'LI-2026-007','2026-01-11','2026-08-11',50,7,3),
(8,'LI-2026-008','2026-01-12','2026-12-12',30,8,3),
(9,'LI-2026-009','2026-01-13',NULL,2000,9,3),
(10,'LI-2026-010','2026-01-14',NULL,5000,10,3);

-- ============================================================
-- 23. EVALUACIONES PROVEEDOR (10)
-- ============================================================
INSERT INTO evaluaciones_proveedor (id_proveedor, cumplimiento_entrega, calidad_producto, precio, calificacion_final, id_usuario_evalua, observacion) VALUES
(1,4.50,4.60,4.40,4.50,4,'Excelente proveedor'),
(2,4.20,4.30,4.10,4.20,4,'Buen proveedor'),
(3,4.80,4.90,4.70,4.80,4,'Muy confiable'),
(4,3.80,3.90,4.00,3.90,4,'Cumple lo pactado'),
(5,4.10,4.20,4.00,4.10,4,'Bueno'),
(6,4.60,4.70,4.50,4.60,4,'Recomendado'),
(7,4.30,4.40,4.20,4.30,4,'Bueno'),
(8,3.70,3.80,3.90,3.80,4,'Mejorable'),
(9,4.70,4.80,4.60,4.70,4,'Excelente'),
(10,4.00,4.10,3.90,4.00,4,'Aceptable');

-- ============================================================
-- 24. ÓRDENES PRODUCCIÓN (10)
-- ============================================================
INSERT INTO ordenes_produccion (numero_orden, id_producto, id_receta, cantidad_planificada, cantidad_producida, fecha_inicio, fecha_fin, estado, id_usuario_responsable) VALUES
('OP-2026-001',1,1,100,100,'2026-01-15 08:00','2026-01-15 14:00','finalizada',2),
('OP-2026-002',2,2,50,50,'2026-01-16 08:00','2026-01-16 13:00','finalizada',2),
('OP-2026-003',3,3,80,80,'2026-01-17 07:00','2026-01-17 15:00','finalizada',2),
('OP-2026-004',4,4,120,120,'2026-01-18 08:00','2026-01-18 16:00','finalizada',2),
('OP-2026-005',5,5,60,60,'2026-01-19 08:00','2026-01-19 12:00','finalizada',2),
('OP-2026-006',6,6,100,100,'2026-01-20 08:00','2026-01-20 11:00','finalizada',2),
('OP-2026-007',7,7,50,50,'2026-01-21 08:00','2026-01-21 15:00','finalizada',2),
('OP-2026-008',8,8,100,100,'2026-01-22 08:00','2026-01-22 10:00','finalizada',2),
('OP-2026-009',9,9,40,40,'2026-01-23 08:00','2026-01-23 12:00','finalizada',2),
('OP-2026-010',10,10,80,80,'2026-01-24 08:00','2026-01-24 16:00','finalizada',2);

-- ============================================================
-- 25. CONSUMO INSUMOS PRODUCCIÓN (10)
-- ============================================================
INSERT INTO consumo_insumos_produccion (id_orden_produccion, id_insumo, id_lote_insumo, cantidad_consumida) VALUES
(1,1,1,80),(2,1,1,40),(3,2,2,50),(4,2,2,30),(5,3,3,25),
(6,3,3,10),(7,4,4,5),(8,7,7,2),(9,6,6,30),(10,5,5,20);

-- ============================================================
-- 26. MERMAS PRODUCCIÓN (10)
-- ============================================================
INSERT INTO mermas_produccion (id_orden_produccion, tipo_merma, id_insumo, cantidad, causa, id_usuario_registra) VALUES
(1,'insumo',1,2,'Derrame',2),
(2,'insumo',1,1.5,'Derrame',2),
(3,'insumo',2,0.75,'Merma natural',2),
(4,'insumo',2,0.6,'Merma natural',2),
(5,'insumo',3,0.25,'Derrame',2),
(6,'insumo',3,0.1,'Merma natural',2),
(7,'insumo',4,0.05,'Derrame',2),
(8,'insumo',7,0.01,'Merma natural',2),
(9,'insumo',6,0.6,'Rotura',2),
(10,'insumo',5,0.3,'Derrame',2);

-- ============================================================
-- 27. CONTROLES CALIDAD (10)
-- ============================================================
INSERT INTO controles_calidad (id_lote_producto, id_lote_insumo, tipo_control, resultado, valor_medido, unidad_medida, observacion, id_usuario_responsable) VALUES
(1,1,'Temperatura','aprobado',4.0,'°C','Dentro de rango',7),
(2,1,'Temperatura','aprobado',5.0,'°C','Dentro de rango',7),
(3,2,'Inspección visual','aprobado',NULL,NULL,'Sin defectos',7),
(4,2,'Microbiológico','aprobado',NULL,NULL,'Sin patógenos',7),
(5,3,'Temperatura','aprobado',3.5,'°C','Dentro de rango',7),
(6,3,'Inspección visual','aprobado',NULL,NULL,'Sin defectos',7),
(7,4,'Temperatura','aprobado',4.2,'°C','Dentro de rango',7),
(8,7,'Microbiológico','aprobado',NULL,NULL,'Sin patógenos',7),
(9,6,'Inspección visual','aprobado',NULL,NULL,'Sin defectos',7),
(10,5,'Temperatura','aprobado',3.0,'°C','Dentro de rango',7);

-- ============================================================
-- 28. DOCUMENTOS CALIDAD (10)
-- ============================================================
INSERT INTO documentos_calidad (tipo_documento, nombre_archivo, ruta_archivo, id_lote_producto, id_usuario_carga) VALUES
('BPM','bpm_lp001.pdf','/docs/bpm/lp001.pdf',1,7),
('HACCP','haccp_lp002.pdf','/docs/haccp/lp002.pdf',2,7),
('ISO22000','iso_lp003.pdf','/docs/iso/lp003.pdf',3,7),
('BPM','bpm_lp004.pdf','/docs/bpm/lp004.pdf',4,7),
('HACCP','haccp_lp005.pdf','/docs/haccp/lp005.pdf',5,7),
('ISO22000','iso_lp006.pdf','/docs/iso/lp006.pdf',6,7),
('BPM','bpm_lp007.pdf','/docs/bpm/lp007.pdf',7,7),
('HACCP','haccp_lp008.pdf','/docs/haccp/lp008.pdf',8,7),
('ISO22000','iso_lp009.pdf','/docs/iso/lp009.pdf',9,7),
('BPM','bpm_lp010.pdf','/docs/bpm/lp010.pdf',10,7);

-- ============================================================
-- 29. PEDIDOS (10)
-- ============================================================
INSERT INTO pedidos (numero_pedido, id_cliente, fecha_entrega_estimada, origen, estado, subtotal, impuestos, total, id_usuario_confirma) VALUES
('PED-2026-001',1,'2026-01-25','vendedor','entregado',125.00,16.25,141.25,5),
('PED-2026-002',2,'2026-01-26','vendedor','entregado',250.00,32.50,282.50,5),
('PED-2026-003',3,'2026-01-27','portal','entregado',150.00,19.50,169.50,5),
('PED-2026-004',4,'2026-01-28','vendedor','despachado',180.00,23.40,203.40,5),
('PED-2026-005',5,'2026-01-29','vendedor','confirmado',320.00,41.60,361.60,5),
('PED-2026-006',6,'2026-01-30','portal','confirmado',90.00,11.70,101.70,5),
('PED-2026-007',7,'2026-01-31','vendedor','pendiente',400.00,52.00,452.00,NULL),
('PED-2026-008',8,'2026-02-01','portal','pendiente',75.00,9.75,84.75,NULL),
('PED-2026-009',9,'2026-02-02','vendedor','confirmado',550.00,71.50,621.50,5),
('PED-2026-010',10,'2026-02-03','portal','rechazado',60.00,7.80,67.80,5);

-- ============================================================
-- 30. PEDIDO DETALLE (10)
-- ============================================================
INSERT INTO pedido_detalle (id_pedido, id_producto, cantidad, precio_unitario) VALUES
(1,1,10,12.50),(2,2,10,25.00),(3,3,10,15.00),(4,4,20,8.00),(5,5,15,18.00),
(6,6,5,14.00),(7,7,30,10.00),(8,8,10,9.00),(9,9,20,16.00),(10,10,5,7.00);

-- ============================================================
-- 31. PEDIDO LOTES (10)
-- ============================================================
INSERT INTO pedido_lotes (id_pedido, id_lote_producto, cantidad) VALUES
(1,1,10),(2,2,10),(3,3,10),(4,4,20),(5,5,15),
(6,6,5),(7,7,30),(8,8,10),(9,9,20),(10,10,5);

-- ============================================================
-- 32. FACTURAS (10)
-- ============================================================
INSERT INTO facturas (numero_factura, id_pedido, id_cliente, subtotal, impuestos, total, estado, saldo_pendiente, id_usuario_emite) VALUES
('FAC-2026-001',1,1,125.00,16.25,141.25,'pagada',0,6),
('FAC-2026-002',2,2,250.00,32.50,282.50,'pagada',0,6),
('FAC-2026-003',3,3,150.00,19.50,169.50,'pagada',0,6),
('FAC-2026-004',4,4,180.00,23.40,203.40,'emitida',203.40,6),
('FAC-2026-005',5,5,320.00,41.60,361.60,'emitida',361.60,6),
('FAC-2026-006',6,6,90.00,11.70,101.70,'emitida',101.70,6),
('FAC-2026-007',7,7,400.00,52.00,452.00,'emitida',452.00,6),
('FAC-2026-008',8,8,75.00,9.75,84.75,'emitida',84.75,6),
('FAC-2026-009',9,9,550.00,71.50,621.50,'emitida',621.50,6),
('FAC-2026-010',10,10,60.00,7.80,67.80,'anulada',0,6);

-- ============================================================
-- 33. NOTAS DESPACHO (10)
-- ============================================================
INSERT INTO notas_despacho (numero_nota, id_factura, id_pedido, transportista, direccion_entrega, estado, id_usuario_despacha) VALUES
('ND-2026-001',1,1,'TransBolivia','Av. Arce 123',       'entregada',5),
('ND-2026-002',2,2,'TransBolivia','Calle 6, Zona Sur',  'entregada',5),
('ND-2026-003',3,3,'Moto Express','Av. 16 de Julio 456','entregada',5),
('ND-2026-004',4,4,'TransBolivia','Calle Murillo 789',  'en_ruta',5),
('ND-2026-005',5,5,'Moto Express','Av. Busch 101',      'emitida',5),
('ND-2026-006',6,6,'TransBolivia','Calle 21, Calacoto', 'emitida',5),
('ND-2026-007',7,7,'TransBolivia','Av. Ballivián 202',  'emitida',5),
('ND-2026-008',8,8,'Moto Express','Calle 8, Obrajes',   'emitida',5),
('ND-2026-009',9,9,'TransBolivia','Av. 6 de Agosto 303','emitida',5),
('ND-2026-010',NULL,10,'Moto Express','Calle Sucre 404','anulada',5);

-- ============================================================
-- 34. CUENTAS POR COBRAR (10)
-- ============================================================
INSERT INTO cuentas_por_cobrar (id_factura, id_cliente, monto_original, saldo, fecha_vencimiento, estado) VALUES
(1,1,141.25,0,'2026-02-15','pagada'),
(2,2,282.50,0,'2026-02-16','pagada'),
(3,3,169.50,0,'2026-02-17','pagada'),
(4,4,203.40,203.40,'2026-02-18','pendiente'),
(5,5,361.60,361.60,'2026-02-19','pendiente'),
(6,6,101.70,101.70,'2026-02-20','pendiente'),
(7,7,452.00,452.00,'2026-02-21','pendiente'),
(8,8,84.75,84.75,'2026-02-22','pendiente'),
(9,9,621.50,621.50,'2026-02-23','pendiente'),
(10,10,67.80,0,'2026-02-24','anulada');

-- ============================================================
-- 35. PAGOS CLIENTE (10)
-- ============================================================
INSERT INTO pagos_cliente (id_cxc, monto, metodo_pago, referencia, id_usuario_registra) VALUES
(1,141.25,'Efectivo','REC-001',6),
(2,282.50,'Transferencia','REC-002',6),
(3,169.50,'Cheque','REC-003',6),
(4,50.00,'Efectivo','REC-004',6),
(5,100.00,'Transferencia','REC-005',6),
(6,50.00,'Efectivo','REC-006',6),
(7,100.00,'Transferencia','REC-007',6),
(8,40.00,'Efectivo','REC-008',6),
(9,200.00,'Transferencia','REC-009',6),
(10,67.80,'Efectivo','REC-010',6);

-- ============================================================
-- 36. RECLAMOS CLIENTE (10)
-- ============================================================
INSERT INTO reclamos_cliente (numero_reclamo, id_cliente, id_factura, id_lote_producto, descripcion, estado, id_usuario_atendio, resolucion) VALUES
('REC-2026-001',1,1,1,'Producto con sabor extraño','resuelto',7,'Se reemplazó el producto'),
('REC-2026-002',2,2,2,'Envase dañado','resuelto',7,'Se reembolsó el 50%'),
('REC-2026-003',3,3,3,'Producto vencido','resuelto',7,'Se reemplazó el producto'),
('REC-2026-004',4,4,4,'Textura inadecuada','en_revision',7,NULL),
('REC-2026-005',5,5,5,'Color alterado','abierto',NULL,NULL),
('REC-2026-006',6,6,6,'Olor desagradable','abierto',NULL,NULL),
('REC-2026-007',7,7,7,'Empaque roto','en_revision',7,NULL),
('REC-2026-008',8,8,8,'Producto incompleto','abierto',NULL,NULL),
('REC-2026-009',9,9,9,'Sabor amargo','resuelto',7,'Se reembolsó el 100%'),
('REC-2026-010',10,10,10,'Fecha vencida','cerrado',7,'Reclamo sin fundamento');

-- ============================================================
-- 37. PLAN CUENTAS (10)
-- ============================================================
INSERT INTO plan_cuentas (codigo, nombre, tipo, naturaleza) VALUES
('1','ACTIVO','activo','D'),
('1.1','ACTIVO CORRIENTE','activo','D'),
('1.1.1','Caja','activo','D'),
('1.1.2','Bancos','activo','D'),
('1.1.3','Cuentas por cobrar','activo','D'),
('1.1.4','Inventarios','activo','D'),
('2','PASIVO','pasivo','C'),
('2.1','Cuentas por pagar','pasivo','C'),
('3','PATRIMONIO','patrimonio','C'),
('4','INGRESOS','ingreso','C');

-- ============================================================
-- 38. ASIENTOS CONTABLES (10)
-- ============================================================
INSERT INTO asientos_contables (numero_asiento, fecha_asiento, descripcion, tipo_origen, id_origen, estado, id_usuario_registra) VALUES
('AST-2026-001','2026-01-10','Venta factura 001','venta',1,'registrado',6),
('AST-2026-002','2026-01-11','Venta factura 002','venta',2,'registrado',6),
('AST-2026-003','2026-01-12','Venta factura 003','venta',3,'registrado',6),
('AST-2026-004','2026-01-13','Compra OC 001','compra',1,'registrado',6),
('AST-2026-005','2026-01-14','Compra OC 002','compra',2,'registrado',6),
('AST-2026-006','2026-01-15','Producción OP 001','inventario',1,'registrado',6),
('AST-2026-007','2026-01-16','Producción OP 002','inventario',2,'registrado',6),
('AST-2026-008','2026-01-17','Pago proveedor 001','compra',1,'registrado',6),
('AST-2026-009','2026-01-18','Cobro cliente 001','venta',1,'registrado',6),
('AST-2026-010','2026-01-19','Nómina enero','nomina',1,'registrado',6);

-- ============================================================
-- 39. ASIENTO DETALLE (10)
-- ============================================================
INSERT INTO asiento_detalle (id_asiento, id_cuenta, debe, haber) VALUES
(1,4,141.25,0),(1,10,0,141.25),
(2,4,282.50,0),(2,10,0,282.50),
(3,4,169.50,0),(3,10,0,169.50),
(4,6,2250,0),(4,8,0,2250),
(5,6,1280,0),(5,8,0,1280);

-- ============================================================
-- 40. CUENTAS POR PAGAR (10)
-- ============================================================
INSERT INTO cuentas_por_pagar (id_orden_compra, id_proveedor, monto_original, saldo, fecha_vencimiento, estado) VALUES
(1,1,2542.50,0,'2026-02-05','pagada'),
(2,2,1446.40,0,'2026-02-06','pagada'),
(3,3,949.20,0,'2026-02-07','pagada'),
(4,6,169.50,169.50,'2026-02-08','pendiente'),
(5,1,1084.80,1084.80,'2026-02-09','pendiente'),
(6,5,180.80,180.80,'2026-02-10','pendiente'),
(7,2,452.00,452.00,'2026-02-11','pendiente'),
(8,6,508.50,508.50,'2026-02-12','pendiente'),
(9,4,678.00,0,'2026-02-13','anulada'),
(10,10,282.50,282.50,'2026-02-14','pendiente');

-- ============================================================
-- 41. PAGOS PROVEEDOR (10)
-- ============================================================
INSERT INTO pagos_proveedor (id_cxp, monto, metodo_pago, referencia, id_usuario_registra) VALUES
(1,2542.50,'Transferencia','PAG-001',6),
(2,1446.40,'Transferencia','PAG-002',6),
(3,949.20,'Cheque','PAG-003',6),
(4,50.00,'Transferencia','PAG-004',6),
(5,300.00,'Transferencia','PAG-005',6),
(6,50.00,'Efectivo','PAG-006',6),
(7,100.00,'Transferencia','PAG-007',6),
(8,150.00,'Cheque','PAG-008',6),
(9,678.00,'Transferencia','PAG-009',6),
(10,100.00,'Efectivo','PAG-010',6);

-- ============================================================
-- 42. COSTOS PRODUCCIÓN (10)
-- ============================================================
INSERT INTO costos_produccion (id_orden_produccion, costo_insumos, costo_mano_obra, costo_indirecto, costo_total, costo_unitario) VALUES
(1,320.00,150.00,80.00,550.00,5.50),
(2,480.00,200.00,100.00,780.00,15.60),
(3,350.00,180.00,90.00,620.00,7.75),
(4,260.00,160.00,80.00,500.00,4.17),
(5,420.00,180.00,100.00,700.00,11.67),
(6,300.00,150.00,70.00,520.00,5.20),
(7,280.00,170.00,90.00,540.00,10.80),
(8,180.00,120.00,60.00,360.00,3.60),
(9,240.00,140.00,80.00,460.00,11.50),
(10,320.00,180.00,90.00,590.00,7.38);

-- ============================================================
-- 43. CARGOS (10)
-- ============================================================
INSERT INTO cargos (nombre, descripcion, salario_base) VALUES
('Gerente General','Máxima autoridad ejecutiva',15000),
('Jefe de Producción','Coordina la producción',8000),
('Almacenero','Controla inventarios',4000),
('Comprador','Gestiona compras',5000),
('Vendedor','Gestiona ventas',4500),
('Contador','Lleva contabilidad',6000),
('Responsable de Calidad','Controla calidad',6500),
('Operario de Planta','Realiza producción',3500),
('Auxiliar de Almacén','Apoya almacén',3000),
('Encargado RR.HH.','Gestiona personal',5500);

-- ============================================================
-- 44. EMPLEADOS (10)
-- ============================================================
INSERT INTO empleados (codigo_empleado, nombres, apellidos, ci, fecha_nacimiento, telefono, email, direccion, id_cargo, fecha_ingreso, activo) VALUES
('EMP001','Carlos','Mamani Quispe','1234567','1980-05-10','70010001','cmamani@erp.bo','La Paz',1,'2015-01-15',TRUE),
('EMP002','María','Flores Choque','1234568','1985-08-20','70010002','mflores@erp.bo','La Paz',2,'2016-03-10',TRUE),
('EMP003','Juan','Condori Apaza','1234569','1990-02-15','70010003','jcondori@erp.bo','El Alto',3,'2017-06-01',TRUE),
('EMP004','Ana','Ticona Vargas','1234570','1988-11-30','70010004','aticona@erp.bo','La Paz',4,'2018-09-12',TRUE),
('EMP005','Luis','Callisaya Sumi','1234571','1992-04-25','70010005','lcallisaya@erp.bo','La Paz',5,'2019-02-20',TRUE),
('EMP006','Patricia','Zenteno Ruiz','1234572','1983-07-14','70010006','pzenteno@erp.bo','La Paz',6,'2014-11-05',TRUE),
('EMP007','Roberto','Villacorta Nina','1234573','1987-12-03','70010007','rvillacorta@erp.bo','El Alto',7,'2020-01-15',TRUE),
('EMP008','Silvia','Tarqui Loza','1234574','1995-03-18','70010008','starqui@erp.bo','La Paz',8,'2021-05-10',TRUE),
('EMP009','Hugo','Nina Quispe','1234575','1993-09-22','70010009','hnina@erp.bo','El Alto',9,'2022-08-01',TRUE),
('EMP010','Carmen','Callisaya Lima','1234576','1986-06-09','70010010','ccallisaya@erp.bo','La Paz',10,'2013-04-25',TRUE);

-- ============================================================
-- 45. ASISTENCIAS (10)
-- ============================================================
INSERT INTO asistencias (id_empleado, fecha, hora_entrada, hora_salida, horas_trabajadas, observacion) VALUES
(1,'2026-01-15','08:00','17:00',9.00,'Normal'),
(2,'2026-01-15','08:00','17:00',9.00,'Normal'),
(3,'2026-01-15','08:00','17:00',9.00,'Normal'),
(4,'2026-01-15','08:00','17:00',9.00,'Normal'),
(5,'2026-01-15','08:00','17:00',9.00,'Normal'),
(6,'2026-01-15','08:00','17:00',9.00,'Normal'),
(7,'2026-01-15','08:00','17:00',9.00,'Normal'),
(8,'2026-01-15','08:00','17:00',9.00,'Normal'),
(9,'2026-01-15','08:00','17:00',9.00,'Normal'),
(10,'2026-01-15','08:00','17:00',9.00,'Normal');

-- ============================================================
-- 46. CAPACITACIONES (10)
-- ============================================================
INSERT INTO capacitaciones (nombre, tipo, fecha_inicio, fecha_fin, vigencia_meses, obligatoria) VALUES
('Higiene personal','higiene','2025-01-10','2025-01-10',12,TRUE),
('Manipulación de alimentos','manipulacion_alimentos','2025-02-15','2025-02-15',12,TRUE),
('BPM básico','BPM','2025-03-20','2025-03-20',12,TRUE),
('HACCP introducción','HACCP','2025-04-25','2025-04-25',12,TRUE),
('ISO 22000','ISO22000','2025-05-30','2025-05-30',12,TRUE),
('Primeros auxilios','seguridad','2025-06-15','2025-06-15',24,TRUE),
('Uso de extintores','seguridad','2025-07-20','2025-07-20',12,TRUE),
('Limpieza y desinfección','higiene','2025-08-25','2025-08-25',12,TRUE),
('Control de plagas','higiene','2025-09-30','2025-09-30',12,TRUE),
('Atención al cliente','servicio','2025-10-15','2025-10-15',24,FALSE);

-- ============================================================
-- 47. EMPLEADO CAPACITACIONES (10)
-- ============================================================
INSERT INTO empleado_capacitaciones (id_empleado, id_capacitacion, fecha_realizacion, fecha_vencimiento, aprobado) VALUES
(1,1,'2025-01-10','2026-01-10',TRUE),
(2,2,'2025-02-15','2026-02-15',TRUE),
(3,3,'2025-03-20','2026-03-20',TRUE),
(4,4,'2025-04-25','2026-04-25',TRUE),
(5,5,'2025-05-30','2026-05-30',TRUE),
(6,6,'2025-06-15','2027-06-15',TRUE),
(7,7,'2025-07-20','2026-07-20',TRUE),
(8,8,'2025-08-25','2026-08-25',TRUE),
(9,9,'2025-09-30','2026-09-30',TRUE),
(10,10,'2025-10-15','2027-10-15',TRUE);

-- ============================================================
-- 48. NÓMINAS (10)
-- ============================================================
INSERT INTO nominas (periodo, total_haberes, total_descuentos, total_neto, estado) VALUES
('2025-01',58000,6960,51040,'pagada'),
('2025-02',58000,6960,51040,'pagada'),
('2025-03',58000,6960,51040,'pagada'),
('2025-04',58000,6960,51040,'pagada'),
('2025-05',58000,6960,51040,'pagada'),
('2025-06',58000,6960,51040,'pagada'),
('2025-07',58000,6960,51040,'pagada'),
('2025-08',58000,6960,51040,'pagada'),
('2025-09',58000,6960,51040,'pagada'),
('2025-10',58000,6960,51040,'pagada');

-- ============================================================
-- 49. NÓMINA DETALLE (10)
-- ============================================================
INSERT INTO nomina_detalle (id_nomina, id_empleado, haberes, descuentos, neto) VALUES
(1,1,15000,1800,13200),
(2,2,8000,960,7040),
(3,3,4000,480,3520),
(4,4,5000,600,4400),
(5,5,4500,540,3960),
(6,6,6000,720,5280),
(7,7,6500,780,5720),
(8,8,3500,420,3080),
(9,9,3000,360,2640),
(10,10,5500,660,4840);

COMMIT;

-- ============================================================
-- VERIFICACIÓN FINAL: conteo de filas por tabla
-- ============================================================
SELECT
    relname AS "Tabla",
    n_live_tup AS "Filas aproximadas"
FROM pg_stat_user_tables
ORDER BY relname;

-- CONTRASEÑA UNIVERSAL PARA LOS USUARIOS
-- Pass123*
-- CONTRASEÑA PARA EL ADMIN
-- Admin123*

