-- Query to check FIFO20 valuation layers and warehouse assignment
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
    sm.id as move_id,
    svl.warehouse_id as warehouse_id
FROM stock_valuation_layer svl
LEFT JOIN stock_move sm ON svl.stock_move_id = sm.id
LEFT JOIN product_product pp ON svl.product_id = pp.id
LEFT JOIN stock_warehouse sw ON svl.warehouse_id = sw.id
LEFT JOIN stock_location sl_from ON sm.location_id = sl_from.id
LEFT JOIN stock_location sl_to ON sm.location_dest_id = sl_to.id
WHERE pp.default_code = 'FIFO20'
ORDER BY svl.create_date DESC
LIMIT 20;

-- Check which warehouse each location belongs to
SELECT 
    sl.id,
    sl.complete_name,
    sl.usage,
    sw.id as warehouse_id,
    sw.name as warehouse_name
FROM stock_location sl
LEFT JOIN stock_warehouse sw ON sl.warehouse_id = sw.id
WHERE sl.complete_name LIKE '%ทรัพย์สิน%' 
   OR sl.complete_name LIKE '%NC%'
   OR sl.complete_name LIKE '%คลังสินค้า%'
ORDER BY sl.complete_name;
