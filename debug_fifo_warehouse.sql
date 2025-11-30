-- Query to debug FIFO warehouse consumption issue
-- Check valuation layers for product FIFO20

-- 1. Find product FIFO20
SELECT id, name, default_code 
FROM product_product 
WHERE default_code LIKE '%FIFO20%' 
LIMIT 5;

-- 2. Get all valuation layers for FIFO20 (replace PRODUCT_ID with actual ID from step 1)
-- Uncomment and replace XXXX with product_id
/*
SELECT 
    svl.id,
    svl.create_date,
    sm.name as move_name,
    pp.default_code as product,
    sw.name as warehouse,
    svl.quantity as moved_qty,
    svl.remaining_qty,
    svl.unit_cost,
    svl.value,
    sl_from.complete_name as location_from,
    sl_to.complete_name as location_to,
    svl.description
FROM stock_valuation_layer svl
LEFT JOIN stock_move sm ON svl.stock_move_id = sm.id
LEFT JOIN product_product pp ON svl.product_id = pp.id
LEFT JOIN stock_warehouse sw ON svl.warehouse_id = sw.id
LEFT JOIN stock_location sl_from ON sm.location_id = sl_from.id
LEFT JOIN stock_location sl_to ON sm.location_dest_id = sl_to.id
WHERE svl.product_id = XXXX
ORDER BY svl.create_date DESC
LIMIT 20;
*/

-- 3. Check recent deliveries (last 10)
SELECT 
    svl.id,
    svl.create_date,
    sm.name as move_name,
    pp.default_code as product,
    sw.name as warehouse,
    svl.quantity as moved_qty,
    svl.remaining_qty,
    svl.unit_cost,
    sl_from.complete_name as location_from,
    sl_to.complete_name as location_to
FROM stock_valuation_layer svl
LEFT JOIN stock_move sm ON svl.stock_move_id = sm.id
LEFT JOIN product_product pp ON svl.product_id = pp.id
LEFT JOIN stock_warehouse sw ON svl.warehouse_id = sw.id
LEFT JOIN stock_location sl_from ON sm.location_id = sl_from.id
LEFT JOIN stock_location sl_to ON sm.location_dest_id = sl_to.id
WHERE svl.quantity < 0  -- Negative = outgoing/delivery
  AND svl.create_date >= NOW() - INTERVAL '2 hours'
ORDER BY svl.create_date DESC
LIMIT 10;

-- 4. Check for layers with missing warehouse_id
SELECT 
    COUNT(*) as total_layers,
    COUNT(warehouse_id) as layers_with_warehouse,
    COUNT(*) - COUNT(warehouse_id) as layers_without_warehouse
FROM stock_valuation_layer
WHERE create_date >= NOW() - INTERVAL '1 day';

-- 5. Check warehouses
SELECT id, name, code FROM stock_warehouse ORDER BY id;
