# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class StockValuationRecalculateWizard(models.TransientModel):
    _name = 'stock.valuation.recalculate.wizard'
    _description = 'Recalculate Stock Valuation by Warehouse'

    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses',
        help='Select warehouses to recalculate. Leave empty to process all warehouses.'
    )
    
    recalculate_remaining = fields.Boolean(
        string='Recalculate Remaining Qty/Value',
        default=True,
        help='Recalculate remaining_qty and remaining_value using FIFO per warehouse'
    )
    
    fix_value_mismatch = fields.Boolean(
        string='Fix Value Mismatch (Product Level)',
        default=False,
        help='Fix products where total_qty=0 but total_value≠0 across all warehouses'
    )
    
    fix_value_mismatch_per_warehouse = fields.Boolean(
        string='Fix Value Mismatch Per Warehouse',
        default=True,
        help='Fix products where qty=0 but value≠0 in each warehouse separately'
    )
    
    fix_null_remaining = fields.Boolean(
        string='Fix NULL Remaining Values',
        default=True,
        help='Set remaining_value=0.0 for negative layers with NULL values'
    )
    
    fix_negative_remaining = fields.Boolean(
        string='Fix Negative Remaining',
        default=True,
        help='Fix positive layers with negative remaining_qty (should never happen)'
    )
    
    fix_excess_remaining = fields.Boolean(
        string='Fix Excess Remaining',
        default=True,
        help='Fix layers where remaining_qty > quantity (consumed more than received)'
    )
    
    fix_rounding_errors = fields.Boolean(
        string='Fix Rounding Errors',
        default=True,
        help='Fix small value differences (< 0.10) where qty=0 per warehouse'
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processing', 'Processing'),
        ('done', 'Done'),
    ], default='draft')
    
    result_message = fields.Html(
        string='Result',
        readonly=True
    )
    
    def action_recalculate(self):
        """Execute recalculation process"""
        self.ensure_one()
        
        if not any([self.recalculate_remaining, self.fix_value_mismatch, 
                    self.fix_value_mismatch_per_warehouse, self.fix_rounding_errors,
                    self.fix_null_remaining, self.fix_negative_remaining, 
                    self.fix_excess_remaining]):
            raise UserError(_('Please select at least one operation to perform.'))
        
        self.state = 'processing'
        
        result_html = '<div style="font-family: monospace;">'
        result_html += '<h3>🔄 Recalculation Results</h3>'
        
        try:
            # Step 1: Fix NULL remaining values
            if self.fix_null_remaining:
                result_html += '<h4>Step 1: Fix NULL Remaining Values</h4>'
                null_count = self._fix_null_remaining_values()
                result_html += f'<p>✅ Fixed {null_count} negative layers with NULL remaining_value</p>'
            
            # Step 2: Fix negative remaining qty (should never happen)
            if self.fix_negative_remaining:
                result_html += '<h4>Step 2: Fix Negative Remaining</h4>'
                neg_count = self._fix_negative_remaining()
                result_html += f'<p>✅ Fixed {neg_count} layers with negative remaining_qty</p>'
            
            # Step 3: Fix excess remaining (remaining > quantity)
            if self.fix_excess_remaining:
                result_html += '<h4>Step 3: Fix Excess Remaining</h4>'
                excess_count = self._fix_excess_remaining()
                result_html += f'<p>✅ Fixed {excess_count} layers with excess remaining_qty</p>'
            
            # Step 4: Recalculate remaining qty/value
            if self.recalculate_remaining:
                result_html += '<h4>Step 4: Recalculate Remaining Qty/Value</h4>'
                products_fixed, layers_updated = self._recalculate_remaining_by_warehouse()
                result_html += f'<p>✅ Processed {products_fixed} products, updated {layers_updated} layers</p>'
            
            # Step 5: Fix value mismatch (product level)
            if self.fix_value_mismatch:
                result_html += '<h4>Step 5: Fix Value Mismatch (Product Level)</h4>'
                value_fixed = self._fix_value_mismatch()
                result_html += f'<p>✅ Fixed {value_fixed} products with value mismatch</p>'
            
            # Step 6: Fix value mismatch per warehouse
            if self.fix_value_mismatch_per_warehouse:
                result_html += '<h4>Step 6: Fix Value Mismatch Per Warehouse</h4>'
                value_fixed_wh = self._fix_value_mismatch_per_warehouse()
                result_html += f'<p>✅ Fixed {value_fixed_wh} product-warehouse combinations</p>'
            
            # Step 7: Fix rounding errors
            if self.fix_rounding_errors:
                result_html += '<h4>Step 7: Fix Rounding Errors</h4>'
                rounding_fixed = self._fix_rounding_errors()
                result_html += f'<p>✅ Fixed {rounding_fixed} small value differences</p>'
            
            # Verification
            result_html += '<h4>Verification</h4>'
            verification = self._verify_database()
            result_html += f'<p>Total products: {verification["total_products"]}</p>'
            result_html += f'<p>Value mismatch: {verification["value_mismatch"]} ✅</p>'
            result_html += f'<p>Value mismatch per WH: {verification["value_mismatch_per_wh"]} ✅</p>'
            result_html += f'<p>Remaining mismatch: {verification["remain_mismatch"]} ✅</p>'
            result_html += f'<p>Negative remaining: {verification["negative_remaining"]} ✅</p>'
            result_html += f'<p>Excess remaining: {verification["excess_remaining"]} ✅</p>'
            
            result_html += '<h4 style="color: green;">✅ Recalculation completed successfully!</h4>'
            
        except Exception as e:
            _logger.error(f"Recalculation error: {e}", exc_info=True)
            result_html += f'<h4 style="color: red;">❌ Error: {str(e)}</h4>'
            raise
        
        result_html += '</div>'
        
        self.write({
            'state': 'done',
            'result_message': result_html,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.valuation.recalculate.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def _fix_null_remaining_values(self):
        """Fix NULL remaining_value in negative layers"""
        query = """
            UPDATE stock_valuation_layer
            SET remaining_value = 0.0
            WHERE quantity < 0
              AND remaining_value IS NULL
        """
        self.env.cr.execute(query)
        return self.env.cr.rowcount
    
    def _fix_negative_remaining(self):
        """Fix positive layers with negative remaining_qty (should never happen)"""
        query = """
            SELECT id, quantity, remaining_qty, value, remaining_value
            FROM stock_valuation_layer
            WHERE quantity > 0 AND remaining_qty < 0
        """
        self.env.cr.execute(query)
        layers_with_issue = self.env.cr.fetchall()
        
        fixed_count = 0
        for layer_id, qty, remain_qty, value, remain_value in layers_with_issue:
            # Reset to original values (nothing consumed yet)
            self.env.cr.execute("""
                UPDATE stock_valuation_layer
                SET remaining_qty = quantity,
                    remaining_value = value
                WHERE id = %s
            """, (layer_id,))
            fixed_count += 1
            
            _logger.warning(f"Fixed negative remaining: layer_id={layer_id}, "
                          f"qty={qty}, remain_qty={remain_qty} -> {qty}")
        
        return fixed_count
    
    def _fix_excess_remaining(self):
        """Fix layers where remaining_qty > quantity"""
        query = """
            SELECT id, quantity, remaining_qty, value, remaining_value
            FROM stock_valuation_layer
            WHERE quantity > 0 AND remaining_qty > quantity
        """
        self.env.cr.execute(query)
        layers_with_issue = self.env.cr.fetchall()
        
        fixed_count = 0
        for layer_id, qty, remain_qty, value, remain_value in layers_with_issue:
            # Cap remaining to original quantity
            if qty > 0:
                unit_cost = value / qty
                new_remain_qty = qty
                new_remain_value = qty * unit_cost
            else:
                new_remain_qty = 0.0
                new_remain_value = 0.0
            
            self.env.cr.execute("""
                UPDATE stock_valuation_layer
                SET remaining_qty = %s,
                    remaining_value = %s
                WHERE id = %s
            """, (new_remain_qty, new_remain_value, layer_id))
            fixed_count += 1
            
            _logger.warning(f"Fixed excess remaining: layer_id={layer_id}, "
                          f"qty={qty}, remain_qty={remain_qty} -> {new_remain_qty}")
        
        return fixed_count
    
    def _recalculate_remaining_by_warehouse(self):
        """Recalculate remaining_qty and remaining_value per warehouse"""
        warehouses = self.warehouse_ids if self.warehouse_ids else self.env['stock.warehouse'].search([])
        
        total_products = 0
        total_layers = 0
        
        for warehouse in warehouses:
            _logger.info(f"Processing warehouse: {warehouse.name} ({warehouse.code})")
            
            # Get all products in this warehouse
            query = """
                SELECT DISTINCT product_id
                FROM stock_valuation_layer
                WHERE warehouse_id = %s
                ORDER BY product_id
            """
            self.env.cr.execute(query, (warehouse.id,))
            product_ids = [row[0] for row in self.env.cr.fetchall()]
            
            for product_id in product_ids:
                # Get all layers for this product in this warehouse
                self.env.cr.execute("""
                    SELECT id, quantity, value
                    FROM stock_valuation_layer
                    WHERE product_id = %s AND warehouse_id = %s
                    ORDER BY create_date, id
                """, (product_id, warehouse.id))
                
                layers = self.env.cr.fetchall()
                
                # Simulate FIFO
                remaining_stock = {}  # layer_id -> {'qty': float, 'value': float}
                
                for layer_id, qty, value in layers:
                    if qty > 0:
                        # Positive layer
                        remaining_stock[layer_id] = {'qty': qty, 'value': value}
                    elif qty < 0:
                        # Negative layer: consume from FIFO queue
                        qty_to_consume = abs(qty)
                        
                        for pos_layer_id in list(remaining_stock.keys()):
                            if qty_to_consume <= 0:
                                break
                            
                            available = remaining_stock[pos_layer_id]['qty']
                            consumed_qty = min(available, qty_to_consume)
                            
                            if available > 0:
                                unit_cost = remaining_stock[pos_layer_id]['value'] / available
                                consumed_value = consumed_qty * unit_cost
                            else:
                                consumed_value = 0
                            
                            remaining_stock[pos_layer_id]['qty'] -= consumed_qty
                            remaining_stock[pos_layer_id]['value'] -= consumed_value
                            qty_to_consume -= consumed_qty
                            
                            if remaining_stock[pos_layer_id]['qty'] <= 0.0001:
                                del remaining_stock[pos_layer_id]
                
                # Update database
                for layer_id, qty, value in layers:
                    if qty > 0:
                        new_qty = remaining_stock.get(layer_id, {}).get('qty', 0.0)
                        new_value = remaining_stock.get(layer_id, {}).get('value', 0.0)
                    else:
                        new_qty = 0.0
                        new_value = 0.0
                    
                    self.env.cr.execute("""
                        UPDATE stock_valuation_layer
                        SET remaining_qty = %s, remaining_value = %s
                        WHERE id = %s
                    """, (new_qty, new_value, layer_id))
                    
                    total_layers += 1
                
                total_products += 1
                
                # Commit every 100 products
                if total_products % 100 == 0:
                    self.env.cr.commit()
        
        return total_products, total_layers
    
    def _fix_value_mismatch(self):
        """Fix products where total_qty=0 but total_value≠0"""
        query = """
            SELECT 
                pp.id as product_id,
                SUM(svl.quantity) as total_qty,
                SUM(svl.value) as total_value
            FROM stock_valuation_layer svl
            JOIN product_product pp ON pp.id = svl.product_id
            GROUP BY pp.id
            HAVING ABS(SUM(svl.quantity)) < 0.01
               AND ABS(SUM(svl.value)) > 0.01
        """
        self.env.cr.execute(query)
        products_with_issue = self.env.cr.fetchall()
        
        fixed_count = 0
        
        for product_id, total_qty, total_value in products_with_issue:
            # Get all layers
            self.env.cr.execute("""
                SELECT id, quantity, value, warehouse_id
                FROM stock_valuation_layer
                WHERE product_id = %s
                ORDER BY create_date, id
            """, (product_id,))
            
            layers = self.env.cr.fetchall()
            
            positive_layers = [(lid, qty, val, wh) for lid, qty, val, wh in layers if qty > 0]
            negative_layers = [(lid, qty, val, wh) for lid, qty, val, wh in layers if qty < 0]
            
            positive_value = sum(val for _, _, val, _ in positive_layers)
            negative_value = sum(val for _, _, val, _ in negative_layers)
            
            value_diff = positive_value + negative_value
            
            if abs(value_diff) < 0.01:
                continue
            
            # Distribute adjustment across negative layers
            total_negative_qty = abs(sum(qty for _, qty, _, _ in negative_layers))
            
            if total_negative_qty < 0.01:
                continue
            
            for layer_id, qty, val, wh in negative_layers:
                proportion = abs(qty) / total_negative_qty
                adjustment = -value_diff * proportion
                new_value = val + adjustment
                
                self.env.cr.execute("""
                    UPDATE stock_valuation_layer
                    SET value = %s
                    WHERE id = %s
                """, (new_value, layer_id))
            
            fixed_count += 1
        
        return fixed_count
    
    def _fix_value_mismatch_per_warehouse(self):
        """Fix products where qty=0 but value≠0 in each warehouse"""
        query = """
            SELECT 
                svl.warehouse_id,
                svl.product_id,
                SUM(svl.quantity) as total_qty,
                SUM(svl.value) as total_value
            FROM stock_valuation_layer svl
            GROUP BY svl.warehouse_id, svl.product_id
            HAVING ABS(SUM(svl.quantity)) < 0.01
               AND ABS(SUM(svl.value)) > 0.01
        """
        self.env.cr.execute(query)
        issues = self.env.cr.fetchall()
        
        fixed_count = 0
        
        for warehouse_id, product_id, total_qty, total_value in issues:
            # Get all layers for this product-warehouse combination
            self.env.cr.execute("""
                SELECT id, quantity, value
                FROM stock_valuation_layer
                WHERE product_id = %s AND warehouse_id = %s
                ORDER BY create_date, id
            """, (product_id, warehouse_id))
            
            layers = self.env.cr.fetchall()
            
            positive_layers = [(lid, qty, val) for lid, qty, val in layers if qty > 0]
            negative_layers = [(lid, qty, val) for lid, qty, val in layers if qty < 0]
            
            if not negative_layers:
                continue
            
            positive_value = sum(val for _, _, val in positive_layers)
            negative_value = sum(val for _, _, val in negative_layers)
            value_diff = positive_value + negative_value
            
            if abs(value_diff) < 0.01:
                continue
            
            # Distribute adjustment across negative layers
            total_negative_qty = abs(sum(qty for _, qty, _ in negative_layers))
            
            if total_negative_qty < 0.01:
                continue
            
            for layer_id, qty, val in negative_layers:
                proportion = abs(qty) / total_negative_qty
                adjustment = -value_diff * proportion
                new_value = val + adjustment
                
                self.env.cr.execute("""
                    UPDATE stock_valuation_layer
                    SET value = %s
                    WHERE id = %s
                """, (new_value, layer_id))
            
            fixed_count += 1
            _logger.info(f"Fixed value mismatch for warehouse_id={warehouse_id}, "
                        f"product_id={product_id}, value_diff={value_diff:.2f}")
        
        return fixed_count
    
    def _fix_rounding_errors(self):
        """Fix small value differences (< 1.00) where qty≈0 per warehouse"""
        query = """
            SELECT 
                svl.warehouse_id,
                svl.product_id,
                SUM(svl.quantity) as total_qty,
                SUM(svl.value) as total_value
            FROM stock_valuation_layer svl
            GROUP BY svl.warehouse_id, svl.product_id
            HAVING ABS(SUM(svl.quantity)) < 0.01
               AND ABS(SUM(svl.value)) > 0.0001
               AND ABS(SUM(svl.value)) < 1.00
        """
        self.env.cr.execute(query)
        issues = self.env.cr.fetchall()
        
        fixed_count = 0
        
        for warehouse_id, product_id, total_qty, total_value in issues:
            # Get the last negative layer to adjust
            self.env.cr.execute("""
                SELECT id, value
                FROM stock_valuation_layer
                WHERE product_id = %s AND warehouse_id = %s AND quantity < 0
                ORDER BY create_date DESC, id DESC
                LIMIT 1
            """, (product_id, warehouse_id))
            
            result = self.env.cr.fetchone()
            if not result:
                continue
            
            layer_id, current_value = result
            
            # Adjust to make total = 0
            new_value = current_value - total_value
            
            self.env.cr.execute("""
                UPDATE stock_valuation_layer
                SET value = %s
                WHERE id = %s
            """, (new_value, layer_id))
            
            fixed_count += 1
            _logger.info(f"Fixed rounding error for warehouse_id={warehouse_id}, "
                        f"product_id={product_id}, adjusted={total_value:.4f}")
        
        return fixed_count
    
    def _verify_database(self):
        """Verify database consistency"""
        query = """
            SELECT 
                COUNT(*) as total_products,
                COUNT(CASE WHEN ABS(total_qty) < 0.01 AND ABS(total_value) > 0.01 THEN 1 END) as value_mismatch,
                COUNT(CASE WHEN ABS(moved_remain_diff) > 0.01 THEN 1 END) as remain_mismatch
            FROM (
                SELECT 
                    pp.id,
                    SUM(svl.quantity) as total_qty,
                    SUM(svl.value) as total_value,
                    SUM(svl.quantity) - SUM(svl.remaining_qty) as moved_remain_diff
                FROM stock_valuation_layer svl
                JOIN product_product pp ON pp.id = svl.product_id
                GROUP BY pp.id
            ) sub
        """
        self.env.cr.execute(query)
        result = self.env.cr.fetchone()
        
        # Check for negative remaining
        self.env.cr.execute("""
            SELECT COUNT(*)
            FROM stock_valuation_layer
            WHERE quantity > 0 AND remaining_qty < 0
        """)
        negative_remaining = self.env.cr.fetchone()[0]
        
        # Check for excess remaining
        self.env.cr.execute("""
            SELECT COUNT(*)
            FROM stock_valuation_layer
            WHERE quantity > 0 AND remaining_qty > quantity
        """)
        excess_remaining = self.env.cr.fetchone()[0]
        
        # Check for value mismatch per warehouse
        self.env.cr.execute("""
            SELECT COUNT(*)
            FROM (
                SELECT 
                    svl.warehouse_id,
                    svl.product_id
                FROM stock_valuation_layer svl
                GROUP BY svl.warehouse_id, svl.product_id
                HAVING ABS(SUM(svl.quantity)) < 0.01
                   AND ABS(SUM(svl.value)) > 0.01
            ) sub
        """)
        value_mismatch_per_wh = self.env.cr.fetchone()[0]
        
        return {
            'total_products': result[0],
            'value_mismatch': result[1],
            'remain_mismatch': result[2],
            'negative_remaining': negative_remaining,
            'excess_remaining': excess_remaining,
            'value_mismatch_per_wh': value_mismatch_per_wh,
        }
    
    def action_close(self):
        """Close wizard"""
        return {'type': 'ir.actions.act_window_close'}
