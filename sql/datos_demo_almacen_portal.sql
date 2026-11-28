-- ============================================================
-- DATOS DE DEMO PARA ALMACÉN Y PORTAL DE CLIENTES
-- Ejecutar UNA SOLA VEZ, después de db.sql, en la base erp_manufactura.
-- No borra nada de los demás módulos.
-- ============================================================
BEGIN;

-- 1) CUENTAS DEL PORTAL ---------------------------------------
-- En db.sql los 10 clientes quedaron enlazados al usuario 9 (admin1, que es administrador)
-- porque los id se corrieron al crear primero al usuario 'admin'. Se corrige:
DELETE FROM cuentas_cliente cc
 USING usuarios u, roles r
 WHERE cc.id_usuario = u.id_usuario AND u.id_rol = r.id_rol AND r.nombre <> 'cliente';

-- Dos usuarios cliente más (contraseña Pass123*, cifrada con pgcrypto como en db.sql)
INSERT INTO usuarios (nombre_usuario, email, password_hash, nombre_completo, id_rol)
SELECT v.u, v.e, crypt('Pass123*', gen_salt('bf')), v.n, r.id_rol
  FROM (VALUES ('cliente2', 'cliente2@erp.local', 'Supermercados Andinos'),
               ('cliente3', 'cliente3@erp.local', 'Tienda Doña Rosa')) AS v(u, e, n)
  JOIN roles r ON r.nombre = 'cliente'
ON CONFLICT (nombre_usuario) DO NOTHING;

-- cliente1 -> Distribuidora El Sol (1), cliente2 -> Supermercados Andinos (2), cliente3 -> Tienda Doña Rosa (3)
INSERT INTO cuentas_cliente (id_cliente, id_usuario)
SELECT v.id_cliente, u.id_usuario
  FROM (VALUES ('cliente1', 1), ('cliente2', 2), ('cliente3', 3)) AS v(usuario, id_cliente)
  JOIN usuarios u ON u.nombre_usuario = v.usuario
ON CONFLICT (id_cliente, id_usuario) DO NOTHING;

-- 2) FECHAS AL DÍA DE HOY --------------------------------------
-- Los lotes de db.sql son de enero 2026 y casi todos ya vencieron.
-- Se mueven todas sus fechas los mismos días para que queden alrededor de hoy.
UPDATE lotes_insumos
   SET fecha_recepcion   = fecha_recepcion   + (CURRENT_DATE - DATE '2026-01-20'),
       fecha_vencimiento = fecha_vencimiento + (CURRENT_DATE - DATE '2026-01-20')
 WHERE fecha_recepcion < DATE '2026-02-01';
UPDATE recepciones_compra
   SET fecha_recepcion   = fecha_recepcion   + (CURRENT_DATE - DATE '2026-01-20'),
       fecha_vencimiento = fecha_vencimiento + (CURRENT_DATE - DATE '2026-01-20')
 WHERE fecha_recepcion < DATE '2026-02-01';
UPDATE lotes_productos
   SET fecha_produccion  = fecha_produccion  + (CURRENT_DATE - DATE '2026-01-20'),
       fecha_vencimiento = fecha_vencimiento + (CURRENT_DATE - DATE '2026-01-20')
 WHERE fecha_produccion < DATE '2026-02-01';

-- 3) UNA ORDEN DE COMPRA EMITIDA PARA PROBAR LA RECEPCIÓN --------
INSERT INTO ordenes_compra (numero_orden, id_proveedor, fecha_emision, fecha_entrega_esperada, estado,
                            subtotal, impuestos, total, id_usuario_crea, observacion)
VALUES ('OC-2026-011', 1, CURRENT_DATE - 2, CURRENT_DATE, 'emitida', 3150, 409.50, 3559.50,
        (SELECT id_usuario FROM usuarios WHERE nombre_usuario = 'compra1'), 'Demo de recepción')
ON CONFLICT (numero_orden) DO NOTHING;
INSERT INTO orden_compra_detalle (id_orden_compra, id_insumo, cantidad, precio_unitario)
SELECT oc.id_orden_compra, v.id_insumo, v.cantidad, v.precio
  FROM ordenes_compra oc,
       (VALUES (1, 400, 4.50), (5, 30, 45.00)) AS v(id_insumo, cantidad, precio)
 WHERE oc.numero_orden = 'OC-2026-011'
   AND NOT EXISTS (SELECT 1 FROM orden_compra_detalle d WHERE d.id_orden_compra = oc.id_orden_compra);

-- 4) UNA ORDEN DE PRODUCCIÓN PLANIFICADA PARA PROBAR EL DESPACHO FEFO --
INSERT INTO ordenes_produccion (numero_orden, id_producto, id_receta, cantidad_planificada, estado,
                                id_usuario_responsable, observacion)
VALUES ('OP-2026-011', 1, 1, 100, 'planificada',
        (SELECT id_usuario FROM usuarios WHERE nombre_usuario = 'jproduc1'), 'Demo de despacho FEFO')
ON CONFLICT (numero_orden) DO NOTHING;

COMMIT;

-- Comprobación rápida
SELECT u.nombre_usuario, c.razon_social
  FROM cuentas_cliente cc JOIN usuarios u USING (id_usuario) JOIN clientes c USING (id_cliente);
