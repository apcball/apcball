-- ============================================================================
-- Fix Negative Warehouse Balance - Manual SQL Script
-- Version: 17.0.1.1.1
-- Date: 27 พฤศจิกายน 2568
-- ============================================================================

-- ============================================================================
-- STEP 1: ตรวจสอบ Warehouse ที่มี Balance ติดลบ
-- ============================================================================

SELECT 
    w.name as "Warehouse",
    pt.name as "Product",
    pp.default_code as "Internal Ref",
    SUM(svl.quantity) as "Total Qty",
    ROUND(SUM(svl.value)::numeric, 2) as "Total Value",
    SUM(svl.remaining_qty) as "Remaining Qty",
    ROUND(SUM(svl.remaining_value)::numeric, 2) as "Remaining Value"
FROM stock_valuation_layer svl
JOIN stock_warehouse w ON w.id = svl.warehouse_id
JOIN product_product pp ON pp.id = svl.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE svl.warehouse_id IS NOT NULL
GROUP BY w.name, pt.name, pp.default_code
HAVING SUM(svl.remaining_value) < -0.01 OR SUM(svl.remaining_qty) < -0.01
ORDER BY SUM(svl.remaining_value);

-- ============================================================================
-- STEP 2: ดูรายละเอียด Layers ของสินค้าที่มีปัญหา
-- ============================================================================

-- แก้ไข WHERE clause ให้ตรงกับ warehouse และ product ที่ต้องการตรวจสอบ
SELECT 
    svl.id,
    svl.create_date,
    w.name as "Warehouse",
    pt.name as "Product",
    sm.name as "Move Reference",
    sm.origin_returned_move_id as "Return Move ID",
    svl.quantity,
    ROUND(svl.value::numeric, 2) as "Value",
    ROUND(svl.unit_cost::numeric, 2) as "Unit Cost",
    svl.remaining_qty,
    ROUND(svl.remaining_value::numeric, 2) as "Remaining Value",
    svl.description
FROM stock_valuation_layer svl
LEFT JOIN stock_warehouse w ON w.id = svl.warehouse_id
LEFT JOIN product_product pp ON pp.id = svl.product_id
LEFT JOIN product_template pt ON pt.id = pp.product_tmpl_id
LEFT JOIN stock_move sm ON sm.id = svl.stock_move_id
WHERE w.name = 'คลังDead Stock'  -- แก้ไขชื่อ warehouse
  AND pt.name LIKE '%AC13%'        -- แก้ไขชื่อสินค้า
ORDER BY svl.create_date, svl.id;

-- ============================================================================
-- STEP 3: หา Return Moves ที่อาจไปผิด Warehouse
-- ============================================================================

SELECT 
    sm_return.id as "Return Move ID",
    sm_return.name as "Return Move",
    sm_return.date as "Return Date",
    w_return.name as "Return Warehouse",
    sm_original.id as "Original Move ID",
    sm_original.name as "Original Move",
    w_original.name as "Original Warehouse",
    pt.name as "Product",
    sm_return.product_uom_qty as "Quantity",
    CASE 
        WHEN w_return.id != w_original.id THEN '❌ WRONG WAREHOUSE'
        ELSE '✅ Correct'
    END as "Status"
FROM stock_move sm_return
JOIN stock_move sm_original ON sm_original.id = sm_return.origin_returned_move_id
LEFT JOIN stock_warehouse w_return ON w_return.id = sm_return.warehouse_id
LEFT JOIN stock_warehouse w_original ON w_original.id = sm_original.warehouse_id
JOIN product_product pp ON pp.id = sm_return.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE sm_return.origin_returned_move_id IS NOT NULL
  AND sm_return.state = 'done'
  AND w_return.id != w_original.id  -- Return ไปคนละ warehouse
ORDER BY sm_return.date DESC;

-- ============================================================================
-- STEP 4: สร้าง Adjustment Layer เพื่อแก้ไข Negative Balance
-- ============================================================================

-- ⚠️ ระวัง: ต้องแก้ไขค่าให้ตรงกับข้อมูลจริง

-- Example: แก้ไขสินค้า AC13 ใน Dead Stock warehouse
DO $$
DECLARE
    v_warehouse_id INTEGER;
    v_product_id INTEGER;
    v_company_id INTEGER;
    v_negative_qty NUMERIC;
    v_negative_value NUMERIC;
    v_unit_cost NUMERIC;
BEGIN
    -- หา warehouse ID
    SELECT id INTO v_warehouse_id 
    FROM stock_warehouse 
    WHERE name = 'คลังDead Stock' 
    LIMIT 1;
    
    -- หา product ID
    SELECT pp.id INTO v_product_id
    FROM product_product pp
    JOIN product_template pt ON pt.id = pp.product_tmpl_id
    WHERE pt.name LIKE '%AC13%'
    LIMIT 1;
    
    -- หา company ID
    SELECT company_id INTO v_company_id
    FROM stock_warehouse
    WHERE id = v_warehouse_id;
    
    -- คำนวณยอดติดลบ
    SELECT 
        SUM(remaining_qty),
        SUM(remaining_value)
    INTO v_negative_qty, v_negative_value
    FROM stock_valuation_layer
    WHERE warehouse_id = v_warehouse_id
      AND product_id = v_product_id;
    
    -- ถ้ายอดติดลบ ให้สร้าง adjustment layer
    IF v_negative_qty < -0.01 OR v_negative_value < -0.01 THEN
        -- คำนวณ unit cost
        v_unit_cost := CASE 
            WHEN v_negative_qty < -0.01 THEN ABS(v_negative_value / v_negative_qty)
            ELSE 0
        END;
        
        -- สร้าง adjustment layer
        INSERT INTO stock_valuation_layer (
            product_id,
            warehouse_id,
            quantity,
            value,
            unit_cost,
            remaining_qty,
            remaining_value,
            description,
            company_id,
            create_date,
            write_date
        ) VALUES (
            v_product_id,
            v_warehouse_id,
            ABS(v_negative_qty),  -- เพิ่มของกลับมา
            ABS(v_negative_value),
            v_unit_cost,
            ABS(v_negative_qty),
            ABS(v_negative_value),
            'Manual adjustment v17.0.1.1.1: Fix negative balance from wrong return warehouse',
            v_company_id,
            NOW(),
            NOW()
        );
        
        RAISE NOTICE 'Created adjustment layer: Qty=%, Value=%', ABS(v_negative_qty), ABS(v_negative_value);
    ELSE
        RAISE NOTICE 'No adjustment needed. Current balance: Qty=%, Value=%', v_negative_qty, v_negative_value;
    END IF;
END $$;

-- ============================================================================
-- STEP 5: Recalculate Remaining Qty/Value for All Layers
-- ============================================================================

-- ⚠️ ระวัง: Script นี้จะ recalculate ทุก layer ของ product นั้น

DO $$
DECLARE
    v_warehouse_id INTEGER;
    v_product_id INTEGER;
    v_layer RECORD;
    v_running_qty NUMERIC := 0;
    v_running_value NUMERIC := 0;
BEGIN
    -- หา warehouse และ product ID
    SELECT id INTO v_warehouse_id 
    FROM stock_warehouse 
    WHERE name = 'คลังDead Stock' 
    LIMIT 1;
    
    SELECT pp.id INTO v_product_id
    FROM product_product pp
    JOIN product_template pt ON pt.id = pp.product_tmpl_id
    WHERE pt.name LIKE '%AC13%'
    LIMIT 1;
    
    -- Loop through all layers in order
    FOR v_layer IN 
        SELECT id, quantity, value
        FROM stock_valuation_layer
        WHERE warehouse_id = v_warehouse_id
          AND product_id = v_product_id
        ORDER BY create_date, id
    LOOP
        -- Update running totals
        v_running_qty := v_running_qty + v_layer.quantity;
        v_running_value := v_running_value + v_layer.value;
        
        -- Update layer
        IF v_layer.quantity > 0 THEN
            -- Positive layer: remaining = quantity
            UPDATE stock_valuation_layer
            SET remaining_qty = v_layer.quantity,
                remaining_value = v_layer.value,
                write_date = NOW()
            WHERE id = v_layer.id;
        ELSE
            -- Negative layer: remaining = 0 (consumed)
            UPDATE stock_valuation_layer
            SET remaining_qty = 0,
                remaining_value = 0,
                write_date = NOW()
            WHERE id = v_layer.id;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Recalculated layers. Final balance: Qty=%, Value=%', v_running_qty, v_running_value;
END $$;

-- ============================================================================
-- STEP 6: ตรวจสอบผลลัพธ์หลังแก้ไข
-- ============================================================================

SELECT 
    w.name as "Warehouse",
    pt.name as "Product",
    SUM(svl.quantity) as "Total Qty",
    ROUND(SUM(svl.value)::numeric, 2) as "Total Value",
    SUM(svl.remaining_qty) as "Remaining Qty",
    ROUND(SUM(svl.remaining_value)::numeric, 2) as "Remaining Value"
FROM stock_valuation_layer svl
JOIN stock_warehouse w ON w.id = svl.warehouse_id
JOIN product_product pp ON pp.id = svl.product_id
JOIN product_template pt ON pt.id = pp.product_tmpl_id
WHERE w.name = 'คลังDead Stock'  -- แก้ไขชื่อ warehouse
  AND pt.name LIKE '%AC13%'       -- แก้ไขชื่อสินค้า
GROUP BY w.name, pt.name;

-- ============================================================================
-- STEP 7: ลบ Adjustment Layers (ถ้าต้องการ rollback)
-- ============================================================================

-- ⚠️ DANGER: ใช้เมื่อต้องการลบ adjustment layers ที่สร้างไป

/*
DELETE FROM stock_valuation_layer
WHERE description LIKE '%Manual adjustment v17.0.1.1.1%'
  AND warehouse_id IN (
      SELECT id FROM stock_warehouse WHERE name = 'คลังDead Stock'
  );
*/

-- ============================================================================
-- STEP 8: สร้าง Summary Report หลังแก้ไข
-- ============================================================================

SELECT 
    w.name as "Warehouse",
    COUNT(DISTINCT svl.product_id) as "Products",
    ROUND(SUM(svl.remaining_value)::numeric, 2) as "Total Inventory Value",
    CASE 
        WHEN SUM(svl.remaining_value) < 0 THEN '❌ Negative'
        ELSE '✅ Positive'
    END as "Status"
FROM stock_valuation_layer svl
JOIN stock_warehouse w ON w.id = svl.warehouse_id
WHERE svl.warehouse_id IS NOT NULL
GROUP BY w.name
ORDER BY w.name;

-- ============================================================================
-- คำแนะนำการใช้งาน:
-- ============================================================================
-- 1. รัน STEP 1 เพื่อหา warehouse และสินค้าที่มีปัญหา
-- 2. รัน STEP 2 เพื่อดูรายละเอียด layers
-- 3. รัน STEP 3 เพื่อหา return moves ที่อาจผิด warehouse
-- 4. แก้ไขค่าใน STEP 4 และ 5 ให้ตรงกับข้อมูลจริง
-- 5. รัน STEP 4 เพื่อสร้าง adjustment layer
-- 6. รัน STEP 5 เพื่อ recalculate balances
-- 7. รัน STEP 6 เพื่อตรวจสอบผลลัพธ์
-- 8. รัน STEP 8 เพื่อดู summary ของทุก warehouse
-- ============================================================================
