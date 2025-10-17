from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import json
import logging

_logger = logging.getLogger(__name__)


class ValuationRegenerateWizard(models.TransientModel):
    _name = 'valuation.regenerate.wizard'
    _description = 'Valuation Regenerate Wizard'

    # Company and scope
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True, 
        default=lambda self: self.env.company
    )
    
    # Target scope
    mode = fields.Selection([
        ('product', 'Products'),
        ('category', 'Categories'),
        ('domain', 'Domain'),
    ], string='Scope', default='product', required=True)
    
    product_ids = fields.Many2many('product.product', string='Products')
    categ_ids = fields.Many2many('product.category', string='Categories')
    domain_str = fields.Char('Domain Filter', help='Domain as string e.g. [\'|\', (\'categ_id\', \'=\', 1), (\'type\', \'=\', \'product\')]')
    
    # Date range
    date_from = fields.Date('Date From')
    date_to = fields.Date('Date To')
    
    # Options
    rebuild_valuation_layers = fields.Boolean('Rebuild Valuation Layers', default=True)
    rebuild_account_moves = fields.Boolean('Rebuild Journal Entries', default=True)
    include_landed_cost_layers = fields.Boolean('Include Landed Cost Layers', default=True)
    recompute_cost_method = fields.Selection([
        ('auto', 'Auto (Follow Product Category)'),
        ('fifo', 'FIFO'),
        ('avco', 'AVCO'),
    ], string='Recompute Cost Method', default='auto')
    
    dry_run = fields.Boolean('Dry Run', default=True, 
        help='Calculate plan but do not modify data')
    force_rebuild_even_if_locked = fields.Boolean('Force rebuild if locked', default=False,
        help='Override lock dates if set')
    post_new_moves = fields.Boolean('Post New Journal Entries', default=True)
    notes = fields.Text('Notes')
    
    # Results preview
    line_preview_ids = fields.One2many(
        'valuation.regenerate.wizard.line.preview', 
        'wizard_id', 
        string='Preview Lines'
    )
    
    @api.onchange('mode')
    def _onchange_mode(self):
        if self.mode != 'product':
            self.product_ids = False
        if self.mode != 'category':
            self.categ_ids = False
        if self.mode != 'domain':
            self.domain_str = False

    def action_compute_plan(self):
        """Compute the plan for regeneration without actually modifying data"""
        self.ensure_one()
        
        # Validate permissions
        if not self.user_has_groups('stock.group_stock_manager,account.group_account_manager'):
            raise UserError("You need Inventory or Accounting Manager permissions to use this feature.")
        
        # Validate date range
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError("Date from must be earlier than or equal to date to.")
        
        # Clear existing preview lines
        self.line_preview_ids.unlink()
        
        # Build scope of products to process
        products = self._get_products_to_process()
        
        if not products:
            raise UserError("No products found matching the selected criteria.")
        
        # Find relevant SVLs and Journal Entries
        svls_to_delete = self._find_svl_to_delete(products)
        moves_to_delete = self._find_moves_to_delete(svls_to_delete) if self.rebuild_account_moves else []
        
        # Create preview lines
        preview_lines = []
        for svl in svls_to_delete:
            preview_lines.append((0, 0, {
                'svl_id': svl.id,
                'product_id': svl.product_id.id,
                'date': svl.create_date,
                'old_value': svl.value,
                'old_unit_cost': svl.unit_cost,
                'description': svl.description or 'Valuation Layer',
            }))
            
        for move in moves_to_delete:
            preview_lines.append((0, 0, {
                'move_id': move.id,
                'date': move.date,
                'old_value': sum(move.line_ids.mapped('balance')),
                'description': move.name or 'Journal Entry',
            }))
            
        self.write({'line_preview_ids': preview_lines})
        
        # Show message about what was found
        message = f"Plan computed: Found {len(svls_to_delete)} SVL(s)"
        if self.rebuild_account_moves:
            message += f" and {len(moves_to_delete)} Journal Entry(ies)"
        message += f" for {len(products)} product(s)."
        
        if not svls_to_delete and not moves_to_delete:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Data Found',
                    'message': 'No valuation layers or journal entries found for the selected products and date range.',
                    'type': 'warning',
                    'sticky': False
                }
            }
        
        # Log the plan
        _logger.info(f"Compute Plan: {message}")
        
        # Show the wizard again with the results
        return {
            'name': 'Valuation Regeneration Plan',
            'view_mode': 'form',
            'res_model': 'valuation.regenerate.wizard',
            'type': 'ir.actions.act_window',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_apply_regeneration(self):
        """Apply the regeneration based on the wizard settings"""
        self.ensure_one()
        
        # Check if dry run is still enabled
        if self.dry_run:
            raise UserError(
                "Dry Run Mode is enabled. This will only preview changes without modifying data.\n\n"
                "To actually apply the regeneration:\n"
                "1. Turn OFF 'Dry Run Mode'\n"
                "2. Click 'Apply Regeneration' again"
            )
        
        # Validate permissions
        if not self.user_has_groups('stock.group_stock_manager,account.group_account_manager'):
            raise UserError("You need Inventory or Accounting Manager permissions to use this feature.")
        
        # Validate lock dates unless force override is set
        if not self.force_rebuild_even_if_locked:
            self._validate_period_lock()
        
        # Validate date range
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError("Date from must be earlier than or equal to date to.")
        
        # Build scope of products to process
        products = self._get_products_to_process()
        
        # Find relevant SVLs and Journal Entries
        svls_to_delete = self._find_svl_to_delete(products)
        moves_to_delete = self._find_moves_to_delete(svls_to_delete) if self.rebuild_account_moves else []
        
        # Create backup of existing data
        backup_log = self._create_backup_log(svls_to_delete, moves_to_delete)
        
        # Delete journal entries first (before SVLs since JEs are linked to SVLs)
        if self.rebuild_account_moves:
            moves_to_delete.unlink()
            
        # Delete SVLs
        if self.rebuild_valuation_layers:
            svls_to_delete.unlink()
        
        # Recompute valuation layers and journal entries
        new_svl_ids = []
        new_move_ids = []
        
        if self.rebuild_valuation_layers or self.rebuild_account_moves:
            new_svl_ids, new_move_ids = self._recompute_valuation(products)
        
        # Post new moves if required
        if self.post_new_moves and new_move_ids:
            new_moves = self.env['account.move'].browse(new_move_ids)
            new_moves.action_post()
        
        # Create log entry
        self._create_execution_log(backup_log, svls_to_delete, moves_to_delete, new_svl_ids, new_move_ids)
        
        # Return success message
        message = f"Valuation regeneration completed successfully. {len(new_svl_ids)} SVLs created, {len(new_move_ids)} Journal Entries created."
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success!',
                'message': message,
                'type': 'success',
                'sticky': False
            }
        }

    def _create_execution_log(self, backup_log, old_svls, old_moves, new_svl_ids, new_move_ids):
        """Update log with new data created"""
        # Update the log with the new SVLs and moves created
        backup_log.write({
            'new_svl_ids': json.dumps(new_svl_ids),
            'new_move_ids': json.dumps(new_move_ids),
        })
        
        # Create a CSV report of the changes and attach it to the log
        if old_svls or new_svl_ids:
            csv_data = self._generate_csv_report(old_svls, old_moves, new_svl_ids, new_move_ids)
            self._attach_csv_to_log(backup_log, csv_data)

    def _generate_csv_report(self, old_svls, old_moves, new_svl_ids, new_move_ids):
        """Generate a CSV report comparing old and new data"""
        import io
        import csv
        from odoo.tools.safe_eval import safe_eval
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Add header
        writer.writerow([
            'Type', 'Product', 'Date', 'Old Value', 'New Value', 
            'Old Quantity', 'New Quantity', 'Old Unit Cost', 'New Unit Cost', 
            'Description', 'Status'
        ])
        
        # Add old SVLs info
        for svl in old_svls:
            writer.writerow([
                'SVL',
                svl.product_id.display_name,
                svl.create_date,
                svl.value,
                '',  # New value
                svl.quantity,
                '',  # New quantity
                svl.unit_cost,
                '',  # New unit cost
                svl.description or '',
                'Deleted'
            ])
        
        # Add new SVLs info
        new_svls = self.env['stock.valuation.layer'].browse(new_svl_ids)
        for svl in new_svls:
            writer.writerow([
                'SVL',
                svl.product_id.display_name,
                svl.create_date,
                '',  # Old value
                svl.value,
                '',  # Old quantity
                svl.quantity,
                '',  # Old unit cost
                svl.unit_cost,
                svl.description or '',
                'Created'
            ])
            
        # Add old moves info
        for move in old_moves:
            writer.writerow([
                'Journal Entry',
                '',  # Product not applicable to JE
                move.date,
                sum(move.line_ids.mapped('balance')),
                '',  # New value
                '',  # Quantity not applicable
                '',  # New quantity
                '',  # Unit cost not applicable
                '',  # New unit cost
                move.name or move.ref or '',
                'Deleted'
            ])
        
        # Add new moves info
        new_moves = self.env['account.move'].browse(new_move_ids)
        for move in new_moves:
            writer.writerow([
                'Journal Entry',
                '',  # Product not applicable to JE
                move.date,
                '',  # Old value
                sum(move.line_ids.mapped('balance')),
                '',  # Quantity not applicable
                '',  # New quantity
                '',  # Unit cost not applicable
                '',  # New unit cost
                move.name or move.ref or '',
                'Created'
            ])
        
        return output.getvalue()
    
    def _attach_csv_to_log(self, log_record, csv_data):
        """Attach the CSV report to the log record"""
        attachment = self.env['ir.attachment'].create({
            'name': f'valuation_regeneration_report_{log_record.id}.csv',
            'type': 'binary',
            'datas': csv_data.encode('utf-8'),
            'res_model': 'valuation.regenerate.log',
            'res_id': log_record.id,
        })
        return attachment

    def _get_products_to_process(self):
        """Get products based on the selected scope"""
        if self.mode == 'product':
            if not self.product_ids:
                raise ValidationError("Please select at least one product.")
            # For product mode, return selected products
            # Filter by company if product has company_id set
            return self.product_ids.filtered(
                lambda p: not p.company_id or p.company_id == self.company_id
            )
        elif self.mode == 'category':
            if not self.categ_ids:
                raise ValidationError("Please select at least one category.")
            # Search for products in selected categories
            domain = [
                ('categ_id', 'in', self.categ_ids.ids),
                '|',
                ('company_id', '=', False),
                ('company_id', '=', self.company_id.id)
            ]
        elif self.mode == 'domain':
            if not self.domain_str:
                raise ValidationError("Please enter a domain filter.")
            try:
                additional_domain = eval(self.domain_str)
                domain = [
                    '|',
                    ('company_id', '=', False),
                    ('company_id', '=', self.company_id.id)
                ] + additional_domain
            except Exception as e:
                raise ValidationError(f"Invalid domain filter: {str(e)}")
        else:
            domain = [
                '|',
                ('company_id', '=', False),
                ('company_id', '=', self.company_id.id)
            ]
        
        return self.env['product.product'].search(domain)

    def _find_svl_to_delete(self, products):
        """Find SVLs that match the criteria for deletion"""
        domain = [
            ('product_id', 'in', products.ids),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.date_from:
            domain.append(('create_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('create_date', '<=', self.date_to))
        
        # Only include SVLs that are related to valuation (not manual)
        svls = self.env['stock.valuation.layer'].search(domain)
        
        # Filter to only include SVLs that can be regenerated
        # Exclude manually created SVLs or those from other sources if needed
        return svls

    def _find_moves_to_delete(self, svls):
        """Find Journal Entries that are linked to the SVLs"""
        move_ids = svls.mapped('account_move_id').filtered(lambda m: m != self.env['account.move'])
        return move_ids

    def _validate_period_lock(self):
        """Validate that we're not trying to modify locked periods"""
        # Check accounting lock date
        if self.company_id.fiscalyear_lock_date and self.date_from and self.date_from <= self.company_id.fiscalyear_lock_date:
            raise UserError(f"Cannot modify entries in a locked period. Lock date: {self.company_id.fiscalyear_lock_date}")
        
        if self.company_id.period_lock_date and self.date_from and self.date_from <= self.company_id.period_lock_date:
            raise UserError(f"Cannot modify entries in a locked period. Period lock date: {self.company_id.period_lock_date}")
            
        # For journal-specific locks, we'd need to check individual journals if needed

    def _create_backup_log(self, svls_to_delete, moves_to_delete):
        """Create a backup log of the data that will be deleted"""
        log_model = self.env['valuation.regenerate.log']
        
        # Convert records to JSON
        svl_backup_data = []
        for svl in svls_to_delete:
            svl_backup_data.append({
                'id': svl.id,
                'product_id': svl.product_id.id,
                'value': svl.value,
                'unit_cost': svl.unit_cost,
                'quantity': svl.quantity,
                'remaining_qty': svl.remaining_qty,
                'description': svl.description,
                'create_date': svl.create_date.isoformat() if svl.create_date else False,
                'company_id': svl.company_id.id,
                'stock_move_id': svl.stock_move_id.id if svl.stock_move_id else False,
                'account_move_id': svl.account_move_id.id if svl.account_move_id else False,
            })
        
        move_backup_data = []
        for move in moves_to_delete:
            move_backup_data.append({
                'id': move.id,
                'name': move.name,
                'date': move.date.isoformat() if move.date else False,
                'ref': move.ref,
                'journal_id': move.journal_id.id,
                'company_id': move.company_id.id,
                'state': move.state,
                'line_ids': [(0, 0, {
                    'name': line.name,
                    'account_id': line.account_id.id,
                    'debit': line.debit,
                    'credit': line.credit,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                }) for line in move.line_ids]
            })
        
        vals = {
            'user_id': self.env.uid,
            'company_id': self.company_id.id,
            'executed_at': fields.Datetime.now(),
            'scope_products': [(6, 0, self._get_products_to_process().ids)],
            'scope_date_from': self.date_from,
            'scope_date_to': self.date_to,
            'rebuild_valuation_layers': self.rebuild_valuation_layers,
            'rebuild_account_moves': self.rebuild_account_moves,
            'include_landed_cost_layers': self.include_landed_cost_layers,
            'recompute_cost_method': self.recompute_cost_method,
            'dry_run': self.dry_run,
            'post_new_moves': self.post_new_moves,
            'notes': self.notes,
            'old_svl_data': json.dumps(svl_backup_data),
            'old_move_data': json.dumps(move_backup_data),
        }
        
        return log_model.create(vals)

    def _recompute_valuation(self, products):
        """Recompute valuation layers and journal entries for the selected products"""
        new_svl_ids = []
        new_move_ids = []
        
        for product in products:
            # Determine the costing method to use
            cost_method = self._get_costing_method(product)
            
            if cost_method == 'fifo':
                svl_ids = self._recompute_fifo_valuation(product)
                new_svl_ids.extend(svl_ids)
            elif cost_method == 'avco':
                svl_ids = self._recompute_avco_valuation(product)
                new_svl_ids.extend(svl_ids)
            # Add other cost methods if needed
        
        # Collect the new move IDs from the SVLs that were created
        if new_svl_ids:
            new_svls = self.env['stock.valuation.layer'].browse(new_svl_ids)
            new_move_ids = new_svls.mapped('account_move_id').ids
        
        return new_svl_ids, new_move_ids

    def _get_costing_method(self, product):
        """Get the costing method to use for a product"""
        if self.recompute_cost_method == 'fifo':
            return 'fifo'
        elif self.recompute_cost_method == 'avco':
            return 'avco'
        else:  # auto
            return product.categ_id.property_cost_method or 'fifo'
    
    def _recompute_fifo_valuation(self, product):
        """Recompute FIFO valuation for a specific product"""
        svl_obj = self.env['stock.valuation.layer']
        new_svl_ids = []
        
        # Get stock moves for the product within the date range
        moves_domain = [
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.date_from:
            moves_domain.append(('date', '>=', self.date_from))
        if self.date_to:
            moves_domain.append(('date', '<=', self.date_to))
        
        stock_moves = self.env['stock.move'].search(moves_domain, order='date, id')
        
        # FIFO Inventory Queue: stores incoming stock layers
        # Format: [{'qty': remaining_qty, 'unit_cost': cost, 'origin_move': move, 'date': date}, ...]
        fifo_queue = []
        
        # Process each stock move to create appropriate SVLs
        for move in stock_moves:
            # Skip moves that don't affect valuation
            if not move._should_be_valued():
                continue
            
            move_qty = move.product_uom._compute_quantity(move.product_uom_qty, product.uom_id)
            
            # Determine move direction and create SVL accordingly
            if move._is_in():
                # Incoming move: add to FIFO queue
                unit_cost = move.price_unit or move.product_id.standard_price
                
                # Create incoming SVL
                svl_vals = {
                    'product_id': product.id,
                    'company_id': self.company_id.id,
                    'quantity': move_qty,
                    'unit_cost': unit_cost,
                    'value': move_qty * unit_cost,
                    'remaining_qty': move_qty,
                    'stock_move_id': move.id,
                    'description': f"FIFO In: {move.reference or move.name}",
                    'create_date': move.date,
                }
                
                # Apply landed costs if applicable
                if self.include_landed_cost_layers:
                    landed_cost_adjustment = self._get_landed_cost_adjustment(move)
                    if landed_cost_adjustment:
                        svl_vals['value'] += landed_cost_adjustment
                        svl_vals['unit_cost'] = svl_vals['value'] / move_qty if move_qty else 0
                
                new_svl = svl_obj.create(svl_vals)
                new_svl_ids.append(new_svl.id)
                
                # Add to FIFO queue
                fifo_queue.append({
                    'qty': move_qty,
                    'unit_cost': svl_vals['unit_cost'],
                    'origin_move': move,
                    'origin_svl': new_svl,
                    'date': move.date,
                })
                
                # Create journal entry if needed
                if self.rebuild_account_moves:
                    self._create_journal_entry_for_svl(new_svl)
                    
            elif move._is_out():
                # Outgoing move: consume from FIFO queue
                remaining_to_consume = move_qty
                total_value = 0.0
                layers_consumed = []
                
                # Consume from oldest layers first (FIFO)
                while remaining_to_consume > 0 and fifo_queue:
                    oldest_layer = fifo_queue[0]
                    
                    if oldest_layer['qty'] <= remaining_to_consume:
                        # Consume entire layer
                        qty_consumed = oldest_layer['qty']
                        value_consumed = qty_consumed * oldest_layer['unit_cost']
                        
                        layers_consumed.append({
                            'qty': qty_consumed,
                            'unit_cost': oldest_layer['unit_cost'],
                            'origin_svl': oldest_layer['origin_svl'],
                        })
                        
                        total_value += value_consumed
                        remaining_to_consume -= qty_consumed
                        
                        # Remove layer from queue
                        fifo_queue.pop(0)
                    else:
                        # Partially consume layer
                        qty_consumed = remaining_to_consume
                        value_consumed = qty_consumed * oldest_layer['unit_cost']
                        
                        layers_consumed.append({
                            'qty': qty_consumed,
                            'unit_cost': oldest_layer['unit_cost'],
                            'origin_svl': oldest_layer['origin_svl'],
                        })
                        
                        total_value += value_consumed
                        oldest_layer['qty'] -= qty_consumed
                        remaining_to_consume = 0
                
                # Calculate average unit cost for outgoing
                avg_unit_cost = total_value / move_qty if move_qty else 0
                
                # Create outgoing SVL
                svl_vals = {
                    'product_id': product.id,
                    'company_id': self.company_id.id,
                    'quantity': -move_qty,
                    'unit_cost': avg_unit_cost,
                    'value': -total_value,
                    'remaining_qty': 0,
                    'stock_move_id': move.id,
                    'description': f"FIFO Out: {move.reference or move.name} (consumed {len(layers_consumed)} layer(s))",
                    'create_date': move.date,
                }
                
                new_svl = svl_obj.create(svl_vals)
                new_svl_ids.append(new_svl.id)
                
                # Update remaining qty in consumed origin SVLs
                for layer_info in layers_consumed:
                    origin_svl = layer_info['origin_svl']
                    if origin_svl:
                        new_remaining = origin_svl.remaining_qty - layer_info['qty']
                        origin_svl.write({'remaining_qty': max(0, new_remaining)})
                
                # Create journal entry if needed
                if self.rebuild_account_moves:
                    self._create_journal_entry_for_svl(new_svl)
        
        return new_svl_ids
    
    def _recompute_avco_valuation(self, product):
        """Recompute AVCO valuation for a specific product"""
        svl_obj = self.env['stock.valuation.layer']
        new_svl_ids = []
        
        # Get stock moves for the product within the date range
        moves_domain = [
            ('product_id', '=', product.id),
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ]
        
        if self.date_from:
            moves_domain.append(('date', '>=', self.date_from))
        if self.date_to:
            moves_domain.append(('date', '<=', self.date_to))
        
        stock_moves = self.env['stock.move'].search(moves_domain, order='date, id')
        
        # Calculate running totals for AVCO (Average Cost)
        total_qty = 0.0
        total_value = 0.0
        average_cost = 0.0
        
        # Currency rounding precision
        currency = self.company_id.currency_id
        
        # Process each stock move to create appropriate SVLs with AVCO
        for move in stock_moves:
            # Skip moves that don't affect valuation
            if not move._should_be_valued():
                continue
            
            move_qty = move.product_uom._compute_quantity(move.product_uom_qty, product.uom_id)
            
            # Create SVL based on move type and AVCO logic
            svl_vals = {
                'product_id': product.id,
                'company_id': self.company_id.id,
                'stock_move_id': move.id,
                'create_date': move.date,
            }
            
            # For AVCO, we need to calculate the average cost after each transaction
            if move._is_in():
                # Incoming move: add to inventory at move's price
                unit_cost = move.price_unit or product.standard_price
                move_value = move_qty * unit_cost
                
                # Apply landed costs if applicable
                if self.include_landed_cost_layers:
                    landed_cost_adjustment = self._get_landed_cost_adjustment(move)
                    if landed_cost_adjustment:
                        move_value += landed_cost_adjustment
                        unit_cost = move_value / move_qty if move_qty else unit_cost
                
                # Update running totals
                total_value += move_value
                total_qty += move_qty
                
                # Recalculate average
                if total_qty > 0:
                    average_cost = total_value / total_qty
                else:
                    average_cost = unit_cost
                
                svl_vals.update({
                    'quantity': move_qty,
                    'unit_cost': currency.round(unit_cost),
                    'value': currency.round(move_value),
                    'remaining_qty': move_qty,
                    'description': f"AVCO In: {move.reference or move.name} (Avg: {currency.round(average_cost):.2f})",
                })
            else:
                # Outgoing move: calculate cost based on current average
                if total_qty <= 0:
                    # No stock available, use standard price
                    average_cost = product.standard_price
                    _logger.warning(
                        f"AVCO Outgoing move for {product.display_name} but no stock available. "
                        f"Using standard price: {average_cost}"
                    )
                
                move_value = move_qty * average_cost
                
                svl_vals.update({
                    'quantity': -move_qty,
                    'unit_cost': currency.round(average_cost),
                    'value': currency.round(-move_value),
                    'remaining_qty': 0,
                    'description': f"AVCO Out: {move.reference or move.name} (Avg: {currency.round(average_cost):.2f})",
                })
                
                # Subtract from total inventory
                total_qty -= move_qty
                total_value -= move_value
                
                # Prevent negative values due to rounding
                if total_qty < 0.001:
                    total_qty = 0.0
                    total_value = 0.0
                    average_cost = 0.0
            
            # Create the new SVL
            new_svl = svl_obj.create(svl_vals)
            new_svl_ids.append(new_svl.id)
            
            # Generate corresponding journal entries if required
            if self.rebuild_account_moves:
                self._create_journal_entry_for_svl(new_svl)
        
        return new_svl_ids

    def _get_landed_cost_adjustment(self, move):
        """Get the total landed cost adjustment for a stock move"""
        if not self.include_landed_cost_layers:
            return 0.0
        
        total_adjustment = 0.0
        
        # Find landed costs that apply to this move
        landed_costs = self.env['stock.landed.cost'].search([
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
        ])
        
        for landed_cost in landed_costs:
            for adj_line in landed_cost.valuation_adjustment_lines:
                if adj_line.move_id.id == move.id:
                    total_adjustment += adj_line.additional_landed_cost
        
        return total_adjustment




class ValuationRegenerateWizardLinePreview(models.TransientModel):
    _name = 'valuation.regenerate.wizard.line.preview'
    _description = 'Valuation Regenerate Wizard Line Preview'

    wizard_id = fields.Many2one('valuation.regenerate.wizard', string='Wizard')
    svl_id = fields.Many2one('stock.valuation.layer', string='Stock Valuation Layer')
    move_id = fields.Many2one('account.move', string='Journal Entry')
    product_id = fields.Many2one('product.product', string='Product')
    date = fields.Date('Date')
    old_value = fields.Float('Old Value')
    old_unit_cost = fields.Float('Old Unit Cost')
    description = fields.Char('Description')
    def _create_journal_entry_for_svl(self, svl):
        """Create a journal entry corresponding to a stock valuation layer"""
        if not self.rebuild_account_moves or not svl or svl.value == 0:
            return
        
        account_move_obj = self.env['account.move']
        company = self.company_id
        currency = company.currency_id
        
        # Get the accounts to use for this product/category
        accounts_data = svl.product_id.product_tmpl_id.get_product_accounts()
        
        # Determine journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id)
        ], limit=1)
        
        if not journal:
            _logger.warning(f"No general journal found for company {company.name}")
            return
        
        # Determine debit/credit accounts based on the type of SVL and move direction
        stock_valuation_account = accounts_data.get('stock_valuation')
        stock_input_account = accounts_data.get('stock_input')
        stock_output_account = accounts_data.get('stock_output')
        
        if not stock_valuation_account:
            _logger.warning(
                f"Missing stock valuation account for product {svl.product_id.display_name}, "
                f"skipping JE creation"
            )
            return
        
        # Determine the counterpart account based on move type
        move = svl.stock_move_id
        if move and move._is_in():
            # Incoming: Debit Stock Valuation, Credit Stock Input (or Vendor/Expense)
            debit_account = stock_valuation_account
            credit_account = stock_input_account or accounts_data.get('expense')
        elif move and move._is_out():
            # Outgoing: Debit COGS/Expense, Credit Stock Valuation
            debit_account = stock_output_account or accounts_data.get('expense')
            credit_account = stock_valuation_account
        else:
            # Internal/Adjustment: depends on sign of value
            if svl.value > 0:
                debit_account = stock_valuation_account
                credit_account = stock_input_account or accounts_data.get('expense')
            else:
                debit_account = stock_output_account or accounts_data.get('expense')
                credit_account = stock_valuation_account
        
        if not debit_account or not credit_account:
            _logger.warning(
                f"Missing account configuration for product {svl.product_id.display_name}, "
                f"skipping JE creation"
            )
            return
        
        # Absolute value for accounting entries
        abs_value = abs(svl.value)
        
        # Round amounts
        debit_amount = currency.round(abs_value)
        credit_amount = currency.round(abs_value)
        
        # Create the journal entry
        move_vals = {
            'journal_id': journal.id,
            'date': svl.create_date.date() if svl.create_date else fields.Date.today(),
            'ref': f"SVL-{svl.id}: {svl.description[:100] if svl.description else 'Inventory Valuation'}",
            'company_id': company.id,
            'line_ids': [
                (0, 0, {
                    'name': svl.description or f'Inventory Valuation - {svl.product_id.display_name}',
                    'account_id': debit_account.id,
                    'debit': debit_amount,
                    'credit': 0.0,
                    'product_id': svl.product_id.id,
                    'quantity': abs(svl.quantity),
                }),
                (0, 0, {
                    'name': svl.description or f'Inventory Valuation - {svl.product_id.display_name}',
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': credit_amount,
                    'product_id': svl.product_id.id,
                    'quantity': abs(svl.quantity),
                })
            ]
        }
        
        # Create the account move
        account_move = account_move_obj.create(move_vals)
        
        # Link the SVL to the account move
        svl.write({'account_move_id': account_move.id})
        
        return account_move


class ValuationRegenerateWizardLinePreview(models.TransientModel):
    _name = 'valuation.regenerate.wizard.line.preview'
    _description = 'Valuation Regenerate Wizard Line Preview'

    wizard_id = fields.Many2one('valuation.regenerate.wizard', string='Wizard')
    svl_id = fields.Many2one('stock.valuation.layer', string='Stock Valuation Layer')
    move_id = fields.Many2one('account.move', string='Journal Entry')
    product_id = fields.Many2one('product.product', string='Product')
    date = fields.Date('Date')
    old_value = fields.Float('Old Value')
    old_unit_cost = fields.Float('Old Unit Cost')
    description = fields.Char('Description')