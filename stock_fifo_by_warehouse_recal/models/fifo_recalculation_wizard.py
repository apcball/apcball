# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from collections import defaultdict
from datetime import datetime
import io
import base64
import json
try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class FifoRecalculationWizard(models.TransientModel):
    """
    Wizard for recalculating FIFO valuation layers by warehouse.
    Allows users to preview and apply recalculation for specific date ranges,
    warehouses, and products.
    """
    _name = 'fifo.recalculation.wizard'
    _description = 'Recalculate FIFO by Warehouse'

    date_from = fields.Datetime(
        string='Start Date',
        required=True,
        default=fields.Datetime.now
    )
    date_to = fields.Datetime(
        string='End Date',
        required=True,
        default=fields.Datetime.now
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses',
        help='Leave empty for all warehouses'
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        help='Leave empty for all products'
    )
    product_categ_ids = fields.Many2many(
        'product.category',
        string='Product Categories',
        help='Filter products by categories'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    dry_run = fields.Boolean(
        string='Dry Run (No Commit)',
        default=True,
        help='If checked, system will simulate recalculation without modifying any valuation layer.'
    )
    clear_old_layers = fields.Selection([
        ('none', 'Do not touch existing layers'),
        ('range', 'Delete & Rebuild in selected date range'),
        ('all_product', 'Delete all layers for selected products'),
    ], string='Existing Layers Handling', default='range')
    lock_after_recal = fields.Boolean(
        string='Lock new layers after recalculation',
        default=True
    )
    batch_size = fields.Integer(
        string='Batch Size',
        default=100,
        help='Number of product-warehouse combinations to process per batch. '
             'Smaller batches use less memory but take longer. '
             'Recommended: 50-200 for large datasets.'
    )
    progress_percent = fields.Float(
        string='Progress (%)',
        readonly=True,
        default=0.0
    )
    progress_message = fields.Char(
        string='Progress Message',
        readonly=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('preview', 'Preview'),
        ('processing', 'Processing'),
        ('done', 'Done'),
    ], default='draft', string='State')
    log_text = fields.Text(
        string='Log',
        readonly=True
    )
    line_ids = fields.One2many(
        'fifo.recalculation.wizard.line',
        'wizard_id',
        string='Preview Lines',
        readonly=True
    )
    backup_id = fields.Many2one(
        'fifo.recalculation.backup',
        string='Backup Reference',
        readonly=True,
        help='Reference to backup created before recalculation'
    )
    can_rollback = fields.Boolean(
        string='Can Rollback',
        compute='_compute_can_rollback',
        help='Whether this recalculation can be rolled back'
    )
    excel_file = fields.Binary(
        string='Excel Export',
        readonly=True
    )
    excel_filename = fields.Char(
        string='Excel Filename',
        readonly=True
    )

    @api.depends('backup_id', 'state')
    def _compute_can_rollback(self):
        """Check if rollback is possible."""
        for record in self:
            record.can_rollback = bool(
                record.backup_id and 
                record.state == 'done' and
                record.backup_id.state == 'active'
            )

    @api.model
    def default_get(self, fields_list):
        """Override to show notification if context has it."""
        res = super().default_get(fields_list)
        if self.env.context.get('default_show_notification'):
            message = self.env.context.get('notification_message', 'Operation completed successfully.')
            # Note: Notification will be shown by the client action return
        return res

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """
        Validate that date_from is not after date_to.
        """
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise UserError(_(
                    'Start Date cannot be after End Date.\n'
                    'Start Date: %s\n'
                    'End Date: %s'
                ) % (record.date_from, record.date_to))
    
    @api.constrains('batch_size')
    def _check_batch_size(self):
        """
        Validate batch size is within reasonable limits.
        """
        for record in self:
            if record.batch_size < 1:
                raise UserError(_('Batch Size must be at least 1.'))
            if record.batch_size > 1000:
                raise UserError(_(
                    'Batch Size is too large (max 1000).\n'
                    'Large batch sizes may cause memory issues.'
                ))

    def action_preview(self):
        """
        Generate preview of FIFO recalculation impact.
        Shows before/after quantities and values per product-warehouse combination.
        """
        self.ensure_one()
        
        # Clear existing preview lines
        self.line_ids.unlink()
        
        log = []
        log.append(f"=== FIFO Recalculation Preview ===")
        log.append(f"Date Range: {self.date_from} to {self.date_to}")
        log.append(f"Company: {self.company_id.name}")
        log.append(f"Dry Run: {self.dry_run}")
        log.append("")
        
        # Build domain for stock moves
        move_domain = [
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        
        # Filter by products
        if self.product_ids:
            move_domain.append(('product_id', 'in', self.product_ids.ids))
        elif self.product_categ_ids:
            products = self.env['product.product'].search([
                ('categ_id', 'child_of', self.product_categ_ids.ids)
            ])
            move_domain.append(('product_id', 'in', products.ids))
        
        # Search moves
        moves = self.env['stock.move'].search(move_domain, order='date, id')
        log.append(f"Found {len(moves)} stock moves in date range")
        
        # Group moves by (product_id, warehouse_id)
        groups = self._group_moves_by_product_warehouse(moves)
        log.append(f"Grouped into {len(groups)} product-warehouse combinations")
        log.append("")
        
        # Simulate FIFO for each group
        preview_lines = self._simulate_fifo(groups, log)
        
        # Create preview lines
        self.env['fifo.recalculation.wizard.line'].create(preview_lines)
        
        # Update state and log
        self.write({
            'state': 'preview',
            'log_text': '\n'.join(log)
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_export_excel(self):
        """Export preview data to Excel file."""
        self.ensure_one()
        
        if not xlsxwriter:
            raise UserError(_(
                'Python library xlsxwriter is not installed.\n'
                'Please install it using: pip install xlsxwriter'
            ))
        
        if not self.line_ids:
            raise UserError(_('No preview data to export. Please run Preview first.'))
        
        # Create Excel file in memory
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('FIFO Recalculation Preview')
        
        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        number_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text_format = workbook.add_format({'border': 1})
        positive_format = workbook.add_format({'num_format': '#,##0.00', 'bg_color': '#C6EFCE', 'border': 1})
        negative_format = workbook.add_format({'num_format': '#,##0.00', 'bg_color': '#FFC7CE', 'border': 1})
        
        # Write header
        headers = [
            'Product', 'Warehouse', 
            'Qty Before', 'Value Before',
            'Qty After', 'Value After',
            'Qty Diff', 'Value Diff'
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)
        
        # Set column widths
        worksheet.set_column(0, 0, 40)  # Product
        worksheet.set_column(1, 1, 25)  # Warehouse
        worksheet.set_column(2, 7, 15)  # Numbers
        
        # Write data
        row = 1
        for line in self.line_ids:
            worksheet.write(row, 0, line.product_id.display_name, text_format)
            worksheet.write(row, 1, line.warehouse_id.name if line.warehouse_id else 'N/A', text_format)
            worksheet.write(row, 2, line.qty_before, number_format)
            worksheet.write(row, 3, line.value_before, number_format)
            worksheet.write(row, 4, line.qty_after, number_format)
            worksheet.write(row, 5, line.value_after, number_format)
            
            # Diff columns with color coding
            diff_qty_format = positive_format if line.diff_qty > 0 else (negative_format if line.diff_qty < 0 else number_format)
            diff_value_format = positive_format if line.diff_value > 0 else (negative_format if line.diff_value < 0 else number_format)
            worksheet.write(row, 6, line.diff_qty, diff_qty_format)
            worksheet.write(row, 7, line.diff_value, diff_value_format)
            row += 1
        
        # Add summary row
        row += 1
        worksheet.write(row, 0, 'TOTAL', header_format)
        worksheet.write(row, 1, '', header_format)
        for col in range(2, 8):
            formula_col = chr(65 + col)  # Convert to Excel column letter
            worksheet.write_formula(row, col, f'=SUM({formula_col}2:{formula_col}{row})', header_format)
        
        workbook.close()
        output.seek(0)
        
        # Save to wizard
        filename = f'FIFO_Recalculation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        self.write({
            'excel_file': base64.b64encode(output.read()),
            'excel_filename': filename
        })
        
        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content?model={self._name}&id={self.id}&field=excel_file&download=true&filename={filename}',
            'target': 'new',
        }

    def _group_moves_by_product_warehouse(self, moves):
        """
        Group stock moves by (product_id, warehouse_id) tuple.
        Returns dict with key=(product_id, warehouse_id), value=list of moves sorted by date.
        """
        groups = defaultdict(list)
        
        for move in moves:
            # Get warehouse using helper from stock_fifo_by_warehouse module
            warehouse = self._get_move_warehouse(move)
            
            # Filter by warehouse if specified
            if self.warehouse_ids:
                if not warehouse or warehouse not in self.warehouse_ids:
                    continue
            
            key = (move.product_id.id, warehouse.id if warehouse else False)
            groups[key].append(move)
        
        # Sort moves in each group by date
        for key in groups:
            groups[key] = sorted(groups[key], key=lambda m: (m.date, m.id))
        
        return groups

    def _get_move_warehouse(self, move):
        """
        Get warehouse for a stock move using the same logic as stock_fifo_by_location.
        
        Returns the warehouse that should own the valuation layer for this move.
        This follows the FIFO by warehouse rules for layer assignment.
        """
        if not move.location_id or not move.location_dest_id:
            return False
        
        # Use the move's method if it has _get_fifo_valuation_layer_warehouse
        if hasattr(move, '_get_fifo_valuation_layer_warehouse'):
            return move._get_fifo_valuation_layer_warehouse()
        
        # Fallback to manual logic if method doesn't exist
        source_usage = move.location_id.usage
        dest_usage = move.location_dest_id.usage
        source_wh = move.location_id.warehouse_id
        dest_wh = move.location_dest_id.warehouse_id
        
        # Return moves - use destination warehouse
        if move.origin_returned_move_id:
            if dest_usage == 'internal' and dest_wh:
                return dest_wh
            if dest_usage == 'transit' and dest_wh:
                return dest_wh
        
        # Incoming stock (supplier/production/inventory → internal/transit)
        if source_usage in ('supplier', 'production', 'inventory'):
            return dest_wh
        
        # Customer returns
        if source_usage == 'customer' and dest_usage == 'internal':
            return dest_wh
        
        # Transit → Internal (warehouse receipt)
        if source_usage == 'transit' and dest_usage == 'internal':
            return dest_wh
        
        # Transit → Transit
        if source_usage == 'transit' and dest_usage == 'transit':
            return dest_wh
        
        # Internal → Transit (warehouse shipment)
        if source_usage == 'internal' and dest_usage == 'transit':
            return source_wh
        
        # Internal → Internal
        if source_usage == 'internal' and dest_usage == 'internal':
            # Same warehouse - no new layer needed
            if source_wh and dest_wh and source_wh.id == dest_wh.id:
                return None
            # Different warehouses - use destination
            return dest_wh
        
        # Internal → Customer/Other (outgoing)
        if source_usage == 'internal':
            return source_wh
        
        # Default fallback
        return dest_wh or source_wh or False

    def _simulate_fifo(self, groups, log):
        """
        Simulate FIFO recalculation for grouped moves.
        Returns list of vals for creating preview lines.
        Does not modify database.
        """
        preview_lines = []
        
        for (product_id, warehouse_id), moves in groups.items():
            product = self.env['product.product'].browse(product_id)
            warehouse = self.env['stock.warehouse'].browse(warehouse_id) if warehouse_id else False
            
            log.append(f"--- Product: {product.display_name}, Warehouse: {warehouse.name if warehouse else 'N/A'} ---")
            
            # Get existing layers (before recalculation)
            layer_domain = [
                ('product_id', '=', product_id),
                ('company_id', '=', self.company_id.id),
                '|',
                ('locked', '=', False),
                ('locked', '=', None),
            ]
            if warehouse_id:
                layer_domain.append(('warehouse_id', '=', warehouse_id))
            
            if self.clear_old_layers == 'range':
                layer_domain.extend([
                    ('create_date', '>=', self.date_from),
                    ('create_date', '<=', self.date_to),
                ])
            
            existing_layers = self.env['stock.valuation.layer'].search(layer_domain)
            
            qty_before = sum(existing_layers.mapped('remaining_qty'))
            value_before = sum(existing_layers.mapped('remaining_value'))
            
            log.append(f"  Existing layers: {len(existing_layers)}")
            log.append(f"  Qty before: {qty_before}, Value before: {value_before}")
            
            # Rebuild FIFO for this group (simulation only)
            qty_after, value_after = self._rebuild_fifo_for_group(moves, product_id, warehouse_id, log)
            
            log.append(f"  Qty after: {qty_after}, Value after: {value_after}")
            log.append(f"  Diff: Qty={qty_after - qty_before}, Value={value_after - value_before}")
            log.append("")
            
            # Create preview line data
            preview_lines.append({
                'wizard_id': self.id,
                'product_id': product_id,
                'warehouse_id': warehouse_id,
                'qty_before': qty_before,
                'value_before': value_before,
                'qty_after': qty_after,
                'value_after': value_after,
                'diff_qty': qty_after - qty_before,
                'diff_value': value_after - value_before,
            })
        
        return preview_lines

    def _rebuild_fifo_for_group(self, moves, product_id, warehouse_id, log):
        """
        Rebuild FIFO layers in memory for a specific product-warehouse group.
        Returns (total_qty, total_value) based on simulated FIFO.
        Does not write to database.
        """
        # In-memory FIFO queue: list of dicts {'qty': x, 'unit_cost': y, 'value': z}
        fifo_queue = []
        
        for move in moves:
            # Classify move and get cost
            move_type, qty, unit_cost, value = self._classify_move_and_get_cost(move, warehouse_id)
            
            if move_type == 'in':
                # Add to FIFO queue
                fifo_queue.append({
                    'qty': qty,
                    'unit_cost': unit_cost,
                    'value': value,
                })
                log.append(f"    IN: {qty} units @ {unit_cost} = {value}")
            
            elif move_type == 'out':
                # Consume from FIFO queue
                qty_to_consume = abs(qty)
                log.append(f"    OUT: {qty_to_consume} units to consume")
                
                while qty_to_consume > 0 and fifo_queue:
                    layer = fifo_queue[0]
                    
                    if layer['qty'] <= qty_to_consume:
                        # Consume entire layer
                        qty_to_consume -= layer['qty']
                        log.append(f"      Consumed layer: {layer['qty']} units @ {layer['unit_cost']}")
                        fifo_queue.pop(0)
                    else:
                        # Partial consumption
                        layer['qty'] -= qty_to_consume
                        layer['value'] = layer['qty'] * layer['unit_cost']
                        log.append(f"      Partial consume: {qty_to_consume} units, remaining: {layer['qty']}")
                        qty_to_consume = 0
                
                if qty_to_consume > 0:
                    log.append(f"      WARNING: Shortage of {qty_to_consume} units!")
        
        # Calculate final totals
        total_qty = sum(layer['qty'] for layer in fifo_queue)
        total_value = sum(layer['value'] for layer in fifo_queue)
        
        return total_qty, total_value

    def _classify_move_and_get_cost(self, move, warehouse_id):
        """
        Classify stock move as 'in' or 'out' and calculate cost.
        Uses proper FIFO valuation logic.
        
        Returns tuple: (move_type, quantity, unit_cost, value)
        - move_type: 'in' (positive layer), 'out' (negative layer), 'neutral' (skip)
        - quantity: absolute quantity of the move
        - unit_cost: cost per unit (0 for 'out' moves, calculated by FIFO)
        - value: total value (qty * unit_cost for 'in' moves)
        """
        product = move.product_id
        location_from_usage = move.location_id.usage
        location_to_usage = move.location_dest_id.usage
        source_wh = move.location_id.warehouse_id
        dest_wh = move.location_dest_id.warehouse_id
        move_warehouse = self._get_move_warehouse(move)
        
        # Skip if not for this warehouse
        if warehouse_id and move_warehouse and move_warehouse.id != warehouse_id:
            return 'neutral', 0, 0, 0
        
        # INCOMING MOVES (positive layers)
        # 1. Supplier/Production/Inventory → Internal/Transit
        if location_from_usage in ('supplier', 'production', 'inventory') and \
           location_to_usage in ('internal', 'transit'):
            qty = move.product_uom_qty
            unit_cost = move.price_unit if move.price_unit > 0 else product.standard_price
            return 'in', qty, unit_cost, qty * unit_cost
        
        # 2. Customer returns
        if location_from_usage == 'customer' and location_to_usage == 'internal':
            qty = move.product_uom_qty
            # Try to get cost from existing layer
            existing_layer = self.env['stock.valuation.layer'].search([
                ('stock_move_id', '=', move.id),
                ('quantity', '>', 0)
            ], limit=1)
            unit_cost = existing_layer.unit_cost if existing_layer else product.standard_price
            return 'in', qty, unit_cost, qty * unit_cost
        
        # 3. Inter-warehouse transfer RECEIPT (positive layer at dest)
        if location_from_usage in ('internal', 'transit') and location_to_usage == 'internal':
            if source_wh and dest_wh and source_wh.id != dest_wh.id:
                if move_warehouse and move_warehouse.id == dest_wh.id:
                    qty = move.product_uom_qty
                    # Get cost from source warehouse's negative layer
                    source_layer = self.env['stock.valuation.layer'].search([
                        ('stock_move_id', '=', move.id),
                        ('warehouse_id', '=', source_wh.id),
                        ('quantity', '<', 0)
                    ], limit=1)
                    unit_cost = abs(source_layer.unit_cost) if source_layer else product.standard_price
                    return 'in', qty, unit_cost, qty * unit_cost
        
        # 4. Return moves (positive layer at destination)
        if move.origin_returned_move_id and location_to_usage == 'internal' and dest_wh:
            if move_warehouse and move_warehouse.id == dest_wh.id:
                qty = move.product_uom_qty
                # Get cost from original move
                original_layer = self.env['stock.valuation.layer'].search([
                    ('stock_move_id', '=', move.origin_returned_move_id.id),
                    ('quantity', '<', 0)
                ], limit=1)
                unit_cost = abs(original_layer.unit_cost) if original_layer else product.standard_price
                return 'in', qty, unit_cost, qty * unit_cost
        
        # OUTGOING MOVES (negative layers, consume FIFO)
        # 1. Sales/Consumption (internal → customer/production/inventory)
        if location_from_usage == 'internal' and \
           location_to_usage in ('customer', 'production', 'inventory'):
            qty = move.product_uom_qty
            return 'out', qty, 0, 0  # Cost calculated by FIFO
        
        # 2. Inter-warehouse transfer SHIPMENT (negative layer at source)
        if location_from_usage == 'internal' and location_to_usage in ('internal', 'transit'):
            if source_wh and dest_wh and source_wh.id != dest_wh.id:
                if move_warehouse and move_warehouse.id == source_wh.id:
                    qty = move.product_uom_qty
                    return 'out', qty, 0, 0  # Cost from FIFO
        
        # 3. Return shipment (negative at source of return)
        if move.origin_returned_move_id and location_from_usage == 'internal' and source_wh:
            if move_warehouse and move_warehouse.id == source_wh.id:
                qty = move.product_uom_qty
                return 'out', qty, 0, 0
        
        # NEUTRAL MOVES (same warehouse internal)
        if location_from_usage == 'internal' and location_to_usage == 'internal':
            if source_wh and dest_wh and source_wh.id == dest_wh.id:
                return 'neutral', 0, 0, 0
        
        # Default
        return 'neutral', 0, 0, 0

    def action_apply(self):
        """
        Apply FIFO recalculation with batch processing.
        Deletes old layers and recreates them based on simulated FIFO.
        Processes in batches to handle large datasets efficiently.
        """
        self.ensure_one()
        
        if self.dry_run:
            raise UserError(_('Cannot apply recalculation in Dry Run mode. Please uncheck "Dry Run" first.'))
        
        if not self.line_ids:
            raise UserError(_('No preview data found. Please run Preview first.'))
        
        # Check if already processing (prevent double-click)
        if self.state == 'processing':
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
        
        # Create backup BEFORE any changes
        log = []
        log.append(f"=== Applying FIFO Recalculation ===")
        log.append(f"Time: {datetime.now()}")
        log.append(f"User: {self.env.user.name}")
        log.append("")
        
        # Fix NULL locked fields first
        log.append("=== Fixing NULL locked fields ===")
        try:
            fixed_count = self._fix_null_locked_fields()
            log.append(f"Fixed {fixed_count} layers with locked=NULL")
            log.append("")
        except Exception as e:
            log.append(f"WARNING: Failed to fix NULL locked fields: {str(e)}")
            log.append("")
        
        try:
            backup = self._create_backup()
            log.append(f"Backup created: {backup.name}")
            log.append(f"Backed up {backup.layer_count} layers")
            log.append("")
        except Exception as e:
            log.append(f"WARNING: Failed to create backup: {str(e)}")
            log.append("Continuing without backup...")
            log.append("")
            backup = False
        
        # Update state to processing
        self.write({
            'state': 'processing',
            'progress_percent': 0.0,
            'progress_message': 'Starting recalculation...',
            'backup_id': backup.id if backup else False,
        })
        # No commit here - let it process immediately
        
        log.append(f"=== Processing ===")
        log.append(f"Batch Size: {self.batch_size}")
        log.append("")
        
        # Get affected product-warehouse combinations
        affected_combinations = list(set(
            (line.product_id.id, line.warehouse_id.id if line.warehouse_id else False)
            for line in self.line_ids
        ))
        
        total_combinations = len(affected_combinations)
        log.append(f"Total combinations: {total_combinations}")
        log.append(f"Will process in batches of {self.batch_size}")
        log.append("")
        
        # Rebuild moves groups (same as preview)
        move_domain = [
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        
        if self.product_ids:
            move_domain.append(('product_id', 'in', self.product_ids.ids))
        elif self.product_categ_ids:
            products = self.env['product.product'].search([
                ('categ_id', 'child_of', self.product_categ_ids.ids)
            ])
            move_domain.append(('product_id', 'in', products.ids))
        
        moves = self.env['stock.move'].search(move_domain, order='date, id')
        groups = self._group_moves_by_product_warehouse(moves)
        
        # Process in batches
        deleted_count = 0
        created_count = 0
        
        # Split combinations into batches
        for batch_num in range(0, total_combinations, self.batch_size):
            batch_end = min(batch_num + self.batch_size, total_combinations)
            batch_combinations = affected_combinations[batch_num:batch_end]
            
            # Update progress
            batch_number = batch_num // self.batch_size + 1
            total_batches = (total_combinations + self.batch_size - 1) // self.batch_size
            progress = (batch_num / total_combinations) * 100
            
            progress_msg = f'Batch {batch_number}/{total_batches}: Processing items {batch_num + 1}-{batch_end} of {total_combinations}'
            self.write({
                'progress_percent': progress,
                'progress_message': progress_msg
            })
            
            log.append(f"--- {progress_msg} ---")
            
            # Delete old layers for this batch
            batch_deleted = self._delete_old_layers(batch_combinations, log)
            deleted_count += batch_deleted
            log.append(f"  Batch deleted: {batch_deleted} layers")
            
            # Filter groups for this batch only
            batch_groups = {
                key: value for key, value in groups.items()
                if key in batch_combinations
            }
            
            # Recreate layers for this batch
            batch_created = self._recreate_layers_for_groups(batch_groups, log)
            created_count += batch_created
            log.append(f"  Batch deleted: {batch_deleted} layers, created: {batch_created} layers")
            log.append("")
        
        log.append(f"=== Total Summary ===")
        log.append(f"Total combinations processed: {total_combinations}")
        log.append(f"Total deleted layers: {deleted_count}")
        log.append(f"Total created layers: {created_count}")
        log.append(f"Completed at: {datetime.now()}")
        log.append("")
        
        # Update state to done
        self.write({
            'state': 'done',
            'progress_percent': 100.0,
            'progress_message': f'Completed! Processed {total_combinations} combinations, deleted {deleted_count} layers, created {created_count} layers',
            'log_text': self.log_text + '\n\n' + '\n'.join(log)
        })
        
        # Return action to reload wizard with results
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_show_notification': True,
                'notification_message': _(
                    'FIFO recalculation completed successfully!\n\n'
                    'Combinations: %d\n'
                    'Deleted: %d layers\n'
                    'Created: %d layers'
                ) % (total_combinations, deleted_count, created_count),
            }
        }

    def _delete_old_layers(self, affected_combinations, log):
        """
        Delete old valuation layers based on wizard settings.
        Returns count of deleted layers.
        IMPORTANT: Must delete related stock.valuation.layer.usage records first to avoid FK constraint.
        """
        deleted_count = 0
        
        for product_id, warehouse_id in affected_combinations:
            layer_domain = [
                ('product_id', '=', product_id),
                ('company_id', '=', self.company_id.id),
                '|',
                ('locked', '=', False),
                ('locked', '=', None),
            ]
            
            if warehouse_id:
                layer_domain.append(('warehouse_id', '=', warehouse_id))
            
            if self.clear_old_layers == 'range':
                layer_domain.extend([
                    ('create_date', '>=', self.date_from),
                    ('create_date', '<=', self.date_to),
                ])
            elif self.clear_old_layers == 'none':
                continue  # Skip deletion
            
            old_layers = self.env['stock.valuation.layer'].search(layer_domain)
            
            if old_layers:
                product = self.env['product.product'].browse(product_id)
                warehouse = self.env['stock.warehouse'].browse(warehouse_id) if warehouse_id else False
                log.append(f"  Deleting {len(old_layers)} layers for {product.display_name} @ {warehouse.name if warehouse else 'N/A'}")
                
                # CRITICAL: Delete related stock.valuation.layer.usage records first
                # to avoid foreign key constraint violation
                usage_records = self.env['stock.valuation.layer.usage'].search([
                    ('stock_valuation_layer_id', 'in', old_layers.ids)
                ])
                if usage_records:
                    log.append(f"    Deleting {len(usage_records)} related usage records")
                    usage_records.unlink()
                
                # Now safe to delete the layers
                old_layers.unlink()
                deleted_count += len(old_layers)
        
        return deleted_count

    def _recreate_layers_for_groups(self, groups, log):
        """
        Recreate valuation layers for each product-warehouse group.
        Actually writes to database (unlike _rebuild_fifo_for_group).
        Returns count of created layers.
        """
        created_count = 0
        SVL = self.env['stock.valuation.layer']
        
        for (product_id, warehouse_id), moves in groups.items():
            product = self.env['product.product'].browse(product_id)
            warehouse = self.env['stock.warehouse'].browse(warehouse_id) if warehouse_id else False
            
            log.append(f"  Recreating layers for {product.display_name} @ {warehouse.name if warehouse else 'N/A'}")
            
            # FIFO queue for actual layer creation
            fifo_queue = []
            
            for move in moves:
                move_type, qty, unit_cost, value = self._classify_move_and_get_cost(move, warehouse_id)
                
                if move_type == 'in':
                    # Create IN layer
                    layer_vals = {
                        'product_id': product_id,
                        'company_id': self.company_id.id,
                        'warehouse_id': warehouse_id,
                        'quantity': qty,
                        'unit_cost': unit_cost,
                        'value': value,
                        'remaining_qty': qty,
                        'remaining_value': value,
                        'stock_move_id': move.id,
                        'description': move.reference or move.name,
                    }
                    
                    if self.lock_after_recal:
                        layer_vals['locked'] = True
                    
                    new_layer = SVL.create(layer_vals)
                    created_count += 1
                    
                    # Add to memory queue for FIFO tracking
                    fifo_queue.append({
                        'layer_id': new_layer.id,
                        'qty': qty,
                        'unit_cost': unit_cost,
                        'value': value,
                        'remaining_qty': qty,
                        'remaining_value': value,
                    })
                
                elif move_type == 'out':
                    # Create OUT layer and update FIFO queue
                    qty_to_consume = abs(qty)
                    total_cost = 0
                    
                    # Consume from FIFO queue
                    consumed_layers = []  # Now 5-tuple: (layer_id, consumed_qty, consumed_value, remaining_qty, remaining_value)
                    while qty_to_consume > 0 and fifo_queue:
                        layer = fifo_queue[0]
                        
                        if layer['remaining_qty'] <= qty_to_consume:
                            # Consume entire layer
                            consumed_qty = layer['remaining_qty']
                            consumed_value = layer['remaining_value']
                            qty_to_consume -= consumed_qty
                            total_cost += consumed_value
                            
                            consumed_layers.append((layer['layer_id'], consumed_qty, consumed_value, 0, 0))
                            fifo_queue.pop(0)
                        else:
                            # Partial consumption
                            consumed_qty = qty_to_consume
                            consumed_value = qty_to_consume * layer['unit_cost']
                            
                            layer['remaining_qty'] -= consumed_qty
                            layer['remaining_value'] -= consumed_value
                            
                            total_cost += consumed_value
                            consumed_layers.append((layer['layer_id'], consumed_qty, consumed_value, layer['remaining_qty'], layer['remaining_value']))
                            qty_to_consume = 0
                    
                    # Update consumed layers in DB and create usage records
                    for layer_id, consumed_qty, consumed_value, remaining_qty, remaining_value in consumed_layers:
                        in_layer = SVL.browse(layer_id)
                        in_layer.write({
                            'remaining_qty': remaining_qty,
                            'remaining_value': remaining_value,
                        })
                        
                        # Create usage record if module is installed
                        if consumed_qty > 0 and 'stock.valuation.layer.usage' in self.env:
                            self.env['stock.valuation.layer.usage'].sudo().create({
                                'stock_valuation_layer_id': layer_id,
                                'stock_move_id': move.id,
                                'quantity': consumed_qty,
                                'value': consumed_value,
                                'company_id': self.company_id.id,
                            })
                    
                    # Create OUT layer
                    unit_cost_out = total_cost / abs(qty) if qty != 0 else 0
                    layer_vals = {
                        'product_id': product_id,
                        'company_id': self.company_id.id,
                        'warehouse_id': warehouse_id,
                        'quantity': -abs(qty),
                        'unit_cost': unit_cost_out,
                        'value': -total_cost,
                        'remaining_qty': 0,
                        'remaining_value': 0,
                        'stock_move_id': move.id,
                        'description': move.reference or move.name,
                    }
                    
                    if self.lock_after_recal:
                        layer_vals['locked'] = True
                    
                    SVL.create(layer_vals)
                    created_count += 1
            
            log.append(f"    Created {created_count} layers")
        
        return created_count

    def _fix_null_locked_fields(self):
        """Fix layers with locked=NULL by setting them to False."""
        self.ensure_one()
        
        # Get affected product-warehouse combinations from preview lines
        affected_combinations = set(
            (line.product_id.id, line.warehouse_id.id if line.warehouse_id else False)
            for line in self.line_ids
        )
        
        fixed_count = 0
        
        # Fix locked=NULL for affected products
        for product_id, warehouse_id in affected_combinations:
            layer_domain = [
                ('product_id', '=', product_id),
                ('company_id', '=', self.company_id.id),
                ('locked', '=', None),
            ]
            
            if warehouse_id:
                layer_domain.append(('warehouse_id', '=', warehouse_id))
            
            layers_to_fix = self.env['stock.valuation.layer'].search(layer_domain)
            
            if layers_to_fix:
                layers_to_fix.write({'locked': False})
                fixed_count += len(layers_to_fix)
        
        return fixed_count

    def _create_backup(self):
        """Create backup of layers before recalculation."""
        self.ensure_one()
        
        # Get affected product-warehouse combinations from preview lines
        affected_combinations = set(
            (line.product_id.id, line.warehouse_id.id if line.warehouse_id else False)
            for line in self.line_ids
        )
        
        # IMPORTANT: Also include all explicitly selected products/warehouses
        # even if they don't have moves in the date range
        # This ensures we backup all layers for selected products
        if self.product_ids:
            # Add all combinations of selected products with selected/all warehouses
            for product in self.product_ids:
                if self.warehouse_ids:
                    for warehouse in self.warehouse_ids:
                        affected_combinations.add((product.id, warehouse.id))
                else:
                    # No warehouse filter - backup all warehouses for this product
                    affected_combinations.add((product.id, False))
        elif self.product_categ_ids:
            # Add all products in selected categories
            products = self.env['product.product'].search([
                ('categ_id', 'child_of', self.product_categ_ids.ids)
            ])
            for product in products:
                if self.warehouse_ids:
                    for warehouse in self.warehouse_ids:
                        affected_combinations.add((product.id, warehouse.id))
                else:
                    # No warehouse filter - backup all warehouses for this product
                    affected_combinations.add((product.id, False))
        
        # Collect all layers that will be affected
        # Even if we're not deleting, we need to backup because remaining_qty/value will change
        all_layers_to_backup = self.env['stock.valuation.layer']
        
        for product_id, warehouse_id in affected_combinations:
            layer_domain = [
                ('product_id', '=', product_id),
                ('company_id', '=', self.company_id.id),
                '|',
                ('locked', '=', False),
                ('locked', '=', None),
            ]
            
            if warehouse_id:
                layer_domain.append(('warehouse_id', '=', warehouse_id))
            
            # Backup layers based on deletion strategy
            if self.clear_old_layers == 'range':
                # Backup only layers in date range that will be deleted
                layer_domain.extend([
                    ('create_date', '>=', self.date_from),
                    ('create_date', '<=', self.date_to),
                ])
            elif self.clear_old_layers == 'all_product':
                # Backup all layers for this product-warehouse (will all be deleted)
                pass  # No additional filter needed
            elif self.clear_old_layers == 'none':
                # Even if not deleting, backup existing layers because remaining values will change
                # Backup all existing layers for accurate rollback
                pass  # No additional filter needed
            
            layers = self.env['stock.valuation.layer'].search(layer_domain)
            all_layers_to_backup |= layers
        
        layers_to_backup = all_layers_to_backup
        
        # Log what we're backing up
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(f"Backup: Found {len(affected_combinations)} product-warehouse combinations")
        _logger.info(f"Backup: Total layers to backup: {len(layers_to_backup)}")
        
        # Group layers by product for logging
        product_layer_count = {}
        for layer in layers_to_backup:
            product_name = layer.product_id.display_name
            if product_name not in product_layer_count:
                product_layer_count[product_name] = 0
            product_layer_count[product_name] += 1
        
        for product_name, count in sorted(product_layer_count.items()):
            _logger.info(f"Backup:   {product_name}: {count} layers")
        
        # Create backup record (even if no layers to backup, for audit trail)
        backup_vals = {
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
            'layer_count': len(layers_to_backup),
        }
        backup = self.env['fifo.recalculation.backup'].create(backup_vals)
        
        # Log backup creation
        if not layers_to_backup:
            # No layers to backup (might be clear_old_layers='none')
            _logger.warning("No layers found to backup!")
            return backup
        
        _logger.info(f"Starting to create {len(layers_to_backup)} backup lines...")
        
        # Backup layer data - use batch creation for better performance
        backup_line_count = 0
        failed_layers = []
        backup_lines_vals = []
        
        for layer in layers_to_backup:
            try:
                line_vals = {
                    'backup_id': backup.id,
                    'layer_id': layer.id,
                    'product_id': layer.product_id.id,
                    'warehouse_id': layer.warehouse_id.id if layer.warehouse_id else False,
                    'quantity': layer.quantity or 0.0,
                    'unit_cost': layer.unit_cost or 0.0,
                    'value': layer.value or 0.0,
                    'remaining_qty': layer.remaining_qty or 0.0,
                    'remaining_value': layer.remaining_value or 0.0,
                    'stock_move_id': layer.stock_move_id.id if layer.stock_move_id else False,
                    'description': layer.description or '',
                    'layer_data': json.dumps({
                        'create_date': layer.create_date.isoformat() if layer.create_date else None,
                        'write_date': layer.write_date.isoformat() if layer.write_date else None,
                    }),
                }
                backup_lines_vals.append(line_vals)
            except Exception as e:
                # Log error but continue with other layers
                _logger.error(f"Failed to prepare backup for layer {layer.id} (Product: {layer.product_id.display_name}): {str(e)}")
                import traceback
                _logger.error(traceback.format_exc())
                failed_layers.append({
                    'layer_id': layer.id,
                    'product': layer.product_id.display_name,
                    'error': str(e)
                })
                continue
        
        # Create all backup lines in batch
        try:
            if backup_lines_vals:
                _logger.info(f"Creating {len(backup_lines_vals)} backup lines in batch...")
                created_lines = self.env['fifo.recalculation.backup.line'].create(backup_lines_vals)
                backup_line_count = len(created_lines)
                _logger.info(f"Successfully created {backup_line_count} backup lines")
        except Exception as e:
            _logger.error(f"CRITICAL: Failed to create backup lines in batch: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
            
            # Fallback: Try creating one by one
            _logger.info("Attempting to create backup lines one by one...")
            for line_vals in backup_lines_vals:
                try:
                    self.env['fifo.recalculation.backup.line'].create(line_vals)
                    backup_line_count += 1
                except Exception as e2:
                    layer_id = line_vals.get('layer_id', 'unknown')
                    _logger.error(f"Failed to create backup line for layer {layer_id}: {str(e2)}")
                    failed_layers.append({
                        'layer_id': layer_id,
                        'error': str(e2)
                    })
        
        # Update backup with actual line count
        if backup_line_count != backup.layer_count:
            backup.write({'layer_count': backup_line_count})
        
        # CRITICAL: Commit backup and lines to database immediately
        # This ensures backup is persisted even if wizard transaction is rolled back
        try:
            self.env.cr.commit()
            _logger.info(f"Backup committed to database: {backup.name} with {backup_line_count} lines")
        except Exception as e:
            _logger.error(f"Failed to commit backup: {str(e)}")
            import traceback
            _logger.error(traceback.format_exc())
        
        # Log failed layers if any
        if failed_layers:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(f"Failed to backup {len(failed_layers)} layers out of {len(layers_to_backup)}")
            for failed in failed_layers[:10]:  # Log first 10 failures
                _logger.warning(f"  Layer {failed['layer_id']} ({failed['product']}): {failed['error']}")
        
        return backup

    def action_rollback(self):
        """Rollback recalculation to previous state."""
        self.ensure_one()
        
        if not self.can_rollback:
            raise UserError(_('Cannot rollback this recalculation.'))
        
        return self.backup_id.action_restore()

    @api.model
    def run_scheduled_recalculation(self, config_id=None):
        """Run recalculation based on saved configuration.
        Called by scheduled action (cron job).
        """
        if config_id:
            config = self.env['fifo.recalculation.config'].browse(config_id)
        else:
            # Get active default config
            config = self.env['fifo.recalculation.config'].search([
                ('active', '=', True),
                ('is_default', '=', True)
            ], limit=1)
        
        if not config:
            return False
        
        # Create wizard with config settings
        wizard = self.create({
            'date_from': config.date_from or fields.Datetime.now(),
            'date_to': config.date_to or fields.Datetime.now(),
            'warehouse_ids': [(6, 0, config.warehouse_ids.ids)],
            'product_ids': [(6, 0, config.product_ids.ids)],
            'product_categ_ids': [(6, 0, config.product_categ_ids.ids)],
            'company_id': config.company_id.id,
            'dry_run': False,  # Never dry run in scheduled action
            'clear_old_layers': config.clear_old_layers,
            'lock_after_recal': config.lock_after_recal,
            'batch_size': config.batch_size,
        })
        
        # Run preview first
        wizard.action_preview()
        
        # Apply if configured to auto-apply
        if config.auto_apply:
            wizard.action_apply()
            
            # Send notification to configured users
            if config.notification_user_ids:
                wizard._send_notification(config.notification_user_ids)
        
        return True

    def _send_notification(self, users):
        """Send notification after scheduled recalculation."""
        self.ensure_one()
        
        subject = _('FIFO Recalculation Completed: %s') % self.company_id.name
        body = _(
            '<p>Automatic FIFO recalculation has been completed.</p>'
            '<ul>'
            '<li>Date Range: %s to %s</li>'
            '<li>Status: %s</li>'
            '<li>Log:</li>'
            '</ul>'
            '<pre>%s</pre>'
        ) % (
            self.date_from,
            self.date_to,
            dict(self._fields['state'].selection).get(self.state),
            self.log_text or 'No log available'
        )
        
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': ','.join(users.mapped('email')),
        }).send()


class FifoRecalculationWizardLine(models.TransientModel):
    """
    Preview line for FIFO recalculation wizard.
    Shows before/after quantities and values per product-warehouse combination.
    """
    _name = 'fifo.recalculation.wizard.line'
    _description = 'Recalculated FIFO Preview Line'

    wizard_id = fields.Many2one(
        'fifo.recalculation.wizard',
        required=True,
        ondelete='cascade'
    )
    product_id = fields.Many2one(
        'product.product',
        required=True,
        string='Product'
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse'
    )
    qty_before = fields.Float(
        string='Qty Before',
        digits='Product Unit of Measure'
    )
    value_before = fields.Float(
        string='Value Before',
        digits='Product Price'
    )
    qty_after = fields.Float(
        string='Qty After',
        digits='Product Unit of Measure'
    )
    value_after = fields.Float(
        string='Value After',
        digits='Product Price'
    )
    diff_qty = fields.Float(
        string='Qty Diff',
        digits='Product Unit of Measure'
    )
    diff_value = fields.Float(
        string='Value Diff',
        digits='Product Price'
    )


class FifoRecalculationBackup(models.Model):
    """Backup of valuation layers before recalculation."""
    _name = 'fifo.recalculation.backup'
    _description = 'FIFO Recalculation Backup'
    _order = 'create_date desc'

    name = fields.Char(
        string='Backup Name',
        compute='_compute_name',
        store=True
    )
    wizard_id = fields.Many2one(
        'fifo.recalculation.wizard',
        string='Wizard Reference',
        ondelete='set null'
    )
    date_from = fields.Datetime(
        string='Date From',
        required=True
    )
    date_to = fields.Datetime(
        string='Date To',
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True
    )
    layer_count = fields.Integer(
        string='Layer Count',
        readonly=True
    )
    state = fields.Selection([
        ('active', 'Active'),
        ('restored', 'Restored'),
        ('expired', 'Expired'),
    ], default='active', string='State')
    line_ids = fields.One2many(
        'fifo.recalculation.backup.line',
        'backup_id',
        string='Backup Lines'
    )
    restore_date = fields.Datetime(
        string='Restore Date',
        readonly=True
    )

    @api.depends('create_date', 'company_id')
    def _compute_name(self):
        for record in self:
            if record.create_date:
                record.name = f"Backup {record.company_id.name} - {record.create_date.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                record.name = f"Backup {record.company_id.name}"

    def action_restore(self):
        """Restore backed up layers."""
        self.ensure_one()
        
        if self.state != 'active':
            raise UserError(_('This backup has already been restored or expired.'))
        
        log = []
        log.append(f"=== Restoring Backup: {self.name} ===")
        log.append(f"Layers to restore: {len(self.line_ids)}")
        log.append("")
        
        restored_count = 0
        failed_count = 0
        
        for line in self.line_ids:
            try:
                # Check if layer still exists
                layer = self.env['stock.valuation.layer'].browse(line.layer_id.id)
                if layer.exists():
                    # Restore original values
                    layer.write({
                        'quantity': line.quantity,
                        'unit_cost': line.unit_cost,
                        'value': line.value,
                        'remaining_qty': line.remaining_qty,
                        'remaining_value': line.remaining_value,
                    })
                    restored_count += 1
                else:
                    log.append(f"WARNING: Layer {line.layer_id.id} no longer exists")
                    failed_count += 1
            except Exception as e:
                log.append(f"ERROR restoring layer {line.layer_id.id}: {str(e)}")
                failed_count += 1
        
        log.append("")
        log.append(f"Restored: {restored_count} layers")
        log.append(f"Failed: {failed_count} layers")
        
        # Update backup state
        self.write({
            'state': 'restored',
            'restore_date': fields.Datetime.now()
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Rollback Complete'),
                'message': _('Successfully restored %d layers.\nFailed: %d') % (restored_count, failed_count),
                'type': 'success' if failed_count == 0 else 'warning',
                'sticky': True,
            }
        }


class FifoRecalculationBackupLine(models.Model):
    """Individual layer backup line."""
    _name = 'fifo.recalculation.backup.line'
    _description = 'FIFO Recalculation Backup Line'

    backup_id = fields.Many2one(
        'fifo.recalculation.backup',
        required=True,
        ondelete='cascade'
    )
    layer_id = fields.Many2one(
        'stock.valuation.layer',
        string='Original Layer',
        required=True
    )
    product_id = fields.Many2one(
        'product.product',
        required=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse'
    )
    quantity = fields.Float(
        digits='Product Unit of Measure'
    )
    unit_cost = fields.Float(
        digits='Product Price'
    )
    value = fields.Float(
        digits='Product Price'
    )
    remaining_qty = fields.Float(
        digits='Product Unit of Measure'
    )
    remaining_value = fields.Float(
        digits='Product Price'
    )
    stock_move_id = fields.Many2one(
        'stock.move'
    )
    description = fields.Char()
    layer_data = fields.Text(
        help='JSON data of additional layer information'
    )


class FifoRecalculationConfig(models.Model):
    """Configuration for scheduled FIFO recalculation."""
    _name = 'fifo.recalculation.config'
    _description = 'FIFO Recalculation Configuration'

    name = fields.Char(
        string='Config Name',
        required=True
    )
    active = fields.Boolean(
        default=True
    )
    is_default = fields.Boolean(
        string='Default Config',
        help='Use this config for scheduled actions when no specific config is provided'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    date_from = fields.Datetime(
        string='Start Date',
        help='Leave empty to use current date'
    )
    date_to = fields.Datetime(
        string='End Date',
        help='Leave empty to use current date'
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses'
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products'
    )
    product_categ_ids = fields.Many2many(
        'product.category',
        string='Product Categories'
    )
    clear_old_layers = fields.Selection([
        ('none', 'Do not touch existing layers'),
        ('range', 'Delete & Rebuild in selected date range'),
        ('all_product', 'Delete all layers for selected products'),
    ], string='Existing Layers Handling', default='range')
    lock_after_recal = fields.Boolean(
        string='Lock new layers',
        default=True
    )
    batch_size = fields.Integer(
        string='Batch Size',
        default=100
    )
    auto_apply = fields.Boolean(
        string='Auto Apply',
        default=False,
        help='If checked, recalculation will be applied automatically without preview'
    )
    notification_user_ids = fields.Many2many(
        'res.users',
        string='Notify Users',
        help='Users to notify after scheduled recalculation'
    )

    @api.constrains('is_default')
    def _check_single_default(self):
        """Ensure only one default config per company."""
        for record in self:
            if record.is_default:
                other_defaults = self.search([
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id),
                    ('is_default', '=', True)
                ])
                if other_defaults:
                    raise ValidationError(_(
                        'Only one default configuration is allowed per company.'
                    ))
