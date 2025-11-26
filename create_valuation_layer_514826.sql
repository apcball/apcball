-- SQL Script to create missing valuation layers for move 514826
-- Run this in psql for MOG_LIVE_15_08 database

BEGIN;

-- Check current status
SELECT 
    sm.id as move_id,
    sm.name as move_name,
    sm.product_qty,
    pt.name as product_name,
    sl_src.warehouse_id as source_wh,
    sw_src.name as source_wh_name,
    sl_dest.warehouse_id as dest_wh,
    sw_dest.name as dest_wh_name
FROM stock_move sm
JOIN product_product pp ON sm.product_id = pp.id
JOIN product_template pt ON pp.product_tmpl_id = pt.id
JOIN stock_location sl_src ON sm.location_id = sl_src.id
JOIN stock_location sl_dest ON sm.location_dest_id = sl_dest.id
LEFT JOIN stock_warehouse sw_src ON sl_src.warehouse_id = sw_src.id
LEFT JOIN stock_warehouse sw_dest ON sl_dest.warehouse_id = sw_dest.id
WHERE sm.id = 514826;

-- Create negative layer at source warehouse (FG10)
INSERT INTO stock_valuation_layer (
    stock_move_id,
    product_id,
    warehouse_id,
    quantity,
    unit_cost,
    value,
    company_id,
    description,
    create_date,
    write_date,
    create_uid,
    write_uid
)
SELECT 
    sm.id,
    sm.product_id,
    sl_src.warehouse_id,  -- Source warehouse
    -sm.product_qty,      -- Negative quantity
    100.0,  -- Default unit cost
    -sm.product_qty * 100.0,  -- Negative value
    sm.company_id,
    'Retroactive layer: ' || sw_src.name || ' → ' || sw_dest.name,
    NOW(),
    NOW(),
    2,  -- Admin user
    2   -- Admin user
FROM stock_move sm
JOIN product_product pp ON sm.product_id = pp.id
JOIN product_template pt ON pp.product_tmpl_id = pt.id
JOIN stock_location sl_src ON sm.location_id = sl_src.id
JOIN stock_location sl_dest ON sm.location_dest_id = sl_dest.id
JOIN stock_warehouse sw_src ON sl_src.warehouse_id = sw_src.id
JOIN stock_warehouse sw_dest ON sl_dest.warehouse_id = sw_dest.id
WHERE sm.id = 514826
AND NOT EXISTS (
    SELECT 1 FROM stock_valuation_layer WHERE stock_move_id = 514826
);

-- Create positive layer at destination warehouse (RM01)
INSERT INTO stock_valuation_layer (
    stock_move_id,
    product_id,
    warehouse_id,
    quantity,
    unit_cost,
    value,
    company_id,
    description,
    create_date,
    write_date,
    create_uid,
    write_uid
)
SELECT 
    sm.id,
    sm.product_id,
    sl_dest.warehouse_id,  -- Destination warehouse
    sm.product_qty,        -- Positive quantity
    100.0,  -- Default unit cost
    sm.product_qty * 100.0,  -- Positive value
    sm.company_id,
    'Retroactive layer: ' || sw_src.name || ' → ' || sw_dest.name,
    NOW(),
    NOW(),
    2,  -- Admin user
    2   -- Admin user
FROM stock_move sm
JOIN product_product pp ON sm.product_id = pp.id
JOIN product_template pt ON pp.product_tmpl_id = pt.id
JOIN stock_location sl_src ON sm.location_id = sl_src.id
JOIN stock_location sl_dest ON sm.location_dest_id = sl_dest.id
JOIN stock_warehouse sw_src ON sl_src.warehouse_id = sw_src.id
JOIN stock_warehouse sw_dest ON sl_dest.warehouse_id = sw_dest.id
WHERE sm.id = 514826
AND EXISTS (
    SELECT 1 FROM stock_valuation_layer 
    WHERE stock_move_id = 514826 AND quantity < 0
);

-- Verify results
SELECT 
    svl.id,
    svl.stock_move_id,
    svl.product_id,
    svl.warehouse_id,
    sw.name as warehouse_name,
    svl.quantity,
    svl.unit_cost,
    svl.value,
    svl.description
FROM stock_valuation_layer svl
LEFT JOIN stock_warehouse sw ON svl.warehouse_id = sw.id
WHERE svl.stock_move_id = 514826
ORDER BY svl.id;

COMMIT;

-- Summary
SELECT 
    'Move 514826: Created ' || COUNT(*) || ' valuation layers' as result
FROM stock_valuation_layer 
WHERE stock_move_id = 514826;
