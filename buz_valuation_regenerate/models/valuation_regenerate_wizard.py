from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
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
    
    # Location filter
    location_ids = fields.Many2many(
        'stock.location', 
        string='Locations',
        domain="[('usage', 'in', ['internal', 'transit'])]",
        help='Filter by specific stock locations. Leave empty to process all locations.'
    )
    auto_detect_products = fields.Boolean(
        'Auto-detect Products with Valuation Issues',
        default=False,
        help='Automatically find and select products with potential valuation issues in selected locations'
    )
    auto_detect_ran = fields.Boolean(
        'Auto-detect Has Run',
        default=False,
        help='Internal flag to track if auto-detect has already run'
    )
    check_missing_account_moves = fields.Boolean(
        'Check Missing Account Moves',
        default=False,
        help='Include check for SVLs without account moves (disable for manual valuation)'
    )
    
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
    
    @api.onchange('company_id')
    def _onchange_company_id(self):
        # Clear location_ids when company changes
        if self.location_ids:
            self.location_ids = False
        # Update location domain based on company
        return {
            'domain': {
                'location_ids': [
                    ('usage', 'in', ['internal', 'transit']),
                    '|',
                    ('company_id', '=', False),
                    ('company_id', '=', self.company_id.id)
                ]
            }
        }
    
    def action_clear_selection(self):
        """Clear selected products and preview lines"""
        self.ensure_one()
        self.write({
            'product_ids': [(5, 0, 0)],  # Clear all products
            'line_preview_ids': [(5, 0, 0)],  # Clear all preview lines
            'auto_detect_ran': False,  # Reset auto-detect flag
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Selection Cleared',
                'message': 'Product selection and preview have been cleared. You can now run Compute Plan again.',
                'type': 'success',
                'sticky': False
            }
        }
    
    def _auto_detect_products_with_issues(self):
        """Auto-detect products with potential valuation issues in selected locations
        
        Returns:
            recordset of product.product with potential issues
        """
        self.ensure_one()
        
        if not self.location_ids:
            return self.env['product.product']
        
        _logger.info(f"Auto-detecting products with valuation issues in {len(self.location_ids)} location(s)...")
        
        # Find all stock moves in selected locations within date range
        domain = [
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('product_id.type', '=', 'product'),
            '|',
            ('location_id', 'in', self.location_ids.ids),
            ('location_dest_id', 'in', self.location_ids.ids),
        ]
        
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))
        
        stock_moves = self.env['stock.move'].search(domain)
        
        if not stock_moves:
            _logger.info("No stock moves found in selected locations")
            return self.env['product.product']
        
        # Get unique products from these moves
        products_with_moves = stock_moves.mapped('product_id')
        _logger.info(f"Found {len(products_with_moves)} products with moves in selected locations")
        
        # Check for products with potential valuation issues
        products_with_issues = self.env['product.product']
        
        # Get products that have been recently regenerated (within last 5 minutes) to exclude them
        recent_logs = self.env['valuation.regenerate.log'].search([
            ('company_id', '=', self.company_id.id),
            ('executed_at', '>=', fields.Datetime.now() - timedelta(minutes=5)),
            ('dry_run', '=', False),
        ])
        recently_processed_products = recent_logs.mapped('scope_products')
        
        for product in products_with_moves:
            # Skip products that were recently processed
            if product in recently_processed_products:
                _logger.info(f"Product {product.display_name}: Skipping - recently processed")
                continue
            
            # Get SVLs for this product in the locations
            product_moves = stock_moves.filtered(lambda m: m.product_id == product)
            svls = self.env['stock.valuation.layer'].search([
                ('product_id', '=', product.id),
                ('company_id', '=', self.company_id.id),
                ('stock_move_id', 'in', product_moves.ids),
            ])
            
            if self.date_from:
                svls = svls.filtered(lambda s: s.create_date >= self.date_from)
            if self.date_to:
                svls = svls.filtered(lambda s: s.create_date <= self.date_to)
            
            # Check for negative valuation (ค่า value ติดลบ)
            # This checks the cumulative value across all SVLs
            total_value = sum(svls.mapped('value'))
            total_qty = sum(svls.mapped('quantity'))
            
            if total_qty != 0 and total_value < 0:
                _logger.info(
                    f"Product {product.display_name}: "
                    f"Found negative valuation - Qty: {total_qty}, Value: {total_value}"
                )
                products_with_issues |= product
                continue
            
            # Check for individual SVLs with negative value when quantity is positive
            negative_value_svls = svls.filtered(lambda s: s.quantity > 0 and s.value < 0)
            if negative_value_svls:
                _logger.info(
                    f"Product {product.display_name}: "
                    f"Found {len(negative_value_svls)} SVLs with negative value but positive quantity"
                )
                products_with_issues |= product
                continue
            
            # Check for missing SVLs (this applies to all products regardless of valuation method)
            moves_with_svl = svls.mapped('stock_move_id')
            moves_without_svl = product_moves - moves_with_svl
            
            if moves_without_svl:
                _logger.info(
                    f"Product {product.display_name}: "
                    f"Found {len(moves_without_svl)} moves without SVL"
                )
                products_with_issues |= product
                continue
            
            # Check for SVLs with zero or incorrect values (this applies to all products)
            zero_value_svls = svls.filtered(lambda s: s.quantity != 0 and s.value == 0)
            if zero_value_svls:
                _logger.info(
                    f"Product {product.display_name}: "
                    f"Found {len(zero_value_svls)} SVLs with zero value but non-zero quantity"
                )
                products_with_issues |= product
                continue
            
            # Check for missing account moves if enabled (only applies to real_time valuation)
            if self.check_missing_account_moves and product.categ_id.property_valuation == 'real_time':
                svls_without_accounting = svls.filtered(
                    lambda s: s.value != 0 and not s.account_move_id
                )
                if svls_without_accounting:
                    _logger.info(
                        f"Product {product.display_name}: "
                        f"Found {len(svls_without_accounting)} SVLs without account moves"
                    )
                    products_with_issues |= product
                    continue
            
            # Check for back-date issues (วันที่ไม่สอดคล้องกัน)
            # Case 1: SVL create_date ไม่ตรงกับ stock move date
            svls_with_date_mismatch = svls.filtered(
                lambda s: s.stock_move_id and s.create_date and s.stock_move_id.date and
                abs((s.create_date.date() - fields.Date.to_date(s.stock_move_id.date)).days) > 1
            )
            if svls_with_date_mismatch:
                _logger.info(
                    f"Product {product.display_name}: "
                    f"Found {len(svls_with_date_mismatch)} SVLs with date mismatch (back-date issue)"
                )
                products_with_issues |= product
                continue
            
            # Case 2: Check SVL ordering vs move ordering (FIFO/AVCO specific)
            if product.categ_id.property_cost_method in ['fifo', 'average']:
                # Get SVLs sorted by create_date
                svls_by_create = svls.sorted(lambda s: s.create_date or fields.Datetime.now())
                # Get moves sorted by date
                product_moves_by_date = product_moves.sorted(lambda m: (m.date, m.id))
                
                # Check if the order matches
                svl_move_ids = [s.stock_move_id.id for s in svls_by_create if s.stock_move_id]
                move_ids = product_moves_by_date.ids
                
                # Compare the order (allowing for some tolerance)
                if len(svl_move_ids) > 1 and len(move_ids) > 1:
                    # Check if there are any SVLs that are significantly out of order
                    for i, svl in enumerate(svls_by_create):
                        if not svl.stock_move_id:
                            continue
                        
                        # Find the position of this move in the sorted moves
                        try:
                            move_position = move_ids.index(svl.stock_move_id.id)
                            
                            # Check if there's a significant order mismatch
                            # (more than 3 positions difference suggests back-dating)
                            if abs(i - move_position) > 3:
                                _logger.info(
                                    f"Product {product.display_name}: "
                                    f"Found SVL order mismatch (position {i} vs {move_position}) - possible back-date issue"
                                )
                                products_with_issues |= product
                                break
                        except ValueError:
                            # Move not found in list, skip
                            continue
                    
                    if product in products_with_issues:
                        continue
            
            # Case 3: Check for out-of-sequence valuation
            # For FIFO: check if outgoing moves use costs from later incoming moves
            if product.categ_id.property_cost_method == 'fifo':
                svls_sorted = svls.sorted(lambda s: (s.create_date or fields.Datetime.now(), s.id))
                
                for svl in svls_sorted:
                    if not svl.stock_move_id:
                        continue
                    
                    # Check if this is an outgoing move
                    if svl.quantity < 0:
                        # Get the date of this outgoing
                        out_date = fields.Date.to_date(svl.stock_move_id.date)
                        
                        # Find any incoming SVLs that were created later but have earlier dates
                        later_incoming = svls.filtered(
                            lambda s: s.quantity > 0 and 
                            s.create_date > svl.create_date and
                            s.stock_move_id and
                            fields.Date.to_date(s.stock_move_id.date) < out_date
                        )
                        
                        if later_incoming:
                            _logger.info(
                                f"Product {product.display_name}: "
                                f"Found FIFO sequence issue - {len(later_incoming)} incoming SVL(s) "
                                f"created later but dated earlier (back-date issue)"
                            )
                            products_with_issues |= product
                            break
        
        _logger.info(f"Auto-detection complete: Found {len(products_with_issues)} products with issues")
        return products_with_issues

    def action_compute_plan(self):
        """Compute the plan for regeneration without actually modifying data"""
        self.ensure_one()
        
        # Validate permissions
        if not self.user_has_groups('stock.group_stock_manager,account.group_account_manager'):
            raise UserError("You need Inventory or Accounting Manager permissions to use this feature.")
        
        # Validate date range
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValidationError("Date from must be earlier than or equal to date to.")
        
        # Auto-detect products with valuation issues if enabled
        if self.auto_detect_products and self.location_ids and not self.auto_detect_ran:
            detected_products = self._auto_detect_products_with_issues()
            if detected_products:
                self.write({
                    'product_ids': [(6, 0, detected_products.ids)],
                    'auto_detect_products': False,
                    'auto_detect_ran': True,
                })
                _logger.info(f"Auto-detected {len(detected_products)} products with potential valuation issues")
                
                # Continue with normal compute plan flow
                # This allows the preview to be generated in the same action
            else:
                # No products found with issues
                self.auto_detect_products = False
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'No Issues Found',
                        'message': f'No products with valuation issues found in selected locations.',
                        'type': 'success',
                        'sticky': False
                    }
                }
        
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
        
        # Add auto-detect info to message if it was used
        if self.auto_detect_ran:
            message = f"✓ Auto-detected {len(products)} product(s) with valuation issues.\n\n" + message
        
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
        
        # Collect stock moves that need to be reprocessed
        # These are the moves that created the SVLs we're about to delete
        stock_moves_to_reprocess = svls_to_delete.mapped('stock_move_id').filtered(lambda m: m)
        
        _logger.info(
            f"Regeneration scope: {len(svls_to_delete)} SVLs, "
            f"{len(moves_to_delete)} Journal Entries, "
            f"{len(stock_moves_to_reprocess)} Stock Moves to reprocess"
        )
        
        # Create backup of existing data
        backup_log = self._create_backup_log(svls_to_delete, moves_to_delete)
        
        # Store data before deletion for CSV report (read data before records are deleted)
        old_svls_data = []
        for svl in svls_to_delete:
            old_svls_data.append({
                'product_name': svl.product_id.display_name,
                'date': svl.create_date,
                'value': svl.value,
                'quantity': svl.quantity,
                'unit_cost': svl.unit_cost,
                'description': svl.description or '',
            })
        
        old_moves_data = []
        for move in moves_to_delete:
            old_moves_data.append({
                'name': move.name,
                'date': move.date,
                'ref': move.ref,
            })
        
        try:
            # Delete journal entries first (before SVLs since JEs are linked to SVLs)
            if self.rebuild_account_moves and moves_to_delete:
                # Unreconcile all lines in these moves first
                _logger.info(f"Unreconciling {len(moves_to_delete)} journal entries before deletion...")
                for move in moves_to_delete:
                    if move.state == 'posted':
                        # Find all reconciled lines
                        reconciled_lines = move.line_ids.filtered(lambda l: l.reconciled)
                        if reconciled_lines:
                            # Unreconcile them
                            reconciled_lines.remove_move_reconcile()
                        # Reset to draft
                        move.button_draft()
                
                # Use no recomputation context to prevent triggers during deletion
                moves_to_delete.with_context(no_recompute=True).unlink()
                # Flush and invalidate cache to prevent reference errors
                self.env.flush_all()
                self.env.invalidate_all()
                
            # Delete SVLs
            if self.rebuild_valuation_layers and svls_to_delete:
                # Unlink account moves from SVLs if not already handled
                _logger.info(f"Unlinking account moves from {len(svls_to_delete)} SVLs...")
                svl_account_moves = svls_to_delete.mapped('account_move_id').filtered(lambda m: m)
                if svl_account_moves and not self.rebuild_account_moves:
                    # If we're not rebuilding account moves, we need to handle them separately
                    _logger.warning(f"Found {len(svl_account_moves)} account moves linked to SVLs that will be orphaned")
                    # Unlink the relationship
                    svls_to_delete.write({'account_move_id': False})
                
                # Use no recomputation context and valuation_regeneration context
                # to prevent triggers during deletion and cleanup usage records
                svls_to_delete.with_context(
                    no_recompute=True,
                    valuation_regeneration=True
                ).unlink()
                # Flush and invalidate cache to prevent reference errors
                self.env.flush_all()
                self.env.invalidate_all()
            
            # Recompute valuation layers and journal entries
            new_svl_ids = []
            new_move_ids = []
            
            if self.rebuild_valuation_layers or self.rebuild_account_moves:
                new_svl_ids, new_move_ids = self._recompute_valuation(products, stock_moves_to_reprocess)
            
            # Post new moves if required
            if self.post_new_moves and new_move_ids:
                new_moves = self.env['account.move'].browse(new_move_ids)
                new_moves.action_post()
            
            # Create log entry with pre-saved data
            self._create_execution_log(backup_log, old_svls_data, old_moves_data, new_svl_ids, new_move_ids)
            
        except Exception as e:
            # Log the error
            _logger.error(f"Error during valuation regeneration: {str(e)}", exc_info=True)
            # Mark the log as failed
            backup_log.write({
                'notes': f"Error: {str(e)}\n\nOriginal notes:\n{self.notes or ''}",
            })
            # Re-raise to trigger rollback
            raise
        
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

    def _generate_csv_report(self, old_svls_data, old_moves_data, new_svl_ids, new_move_ids):
        """Generate a CSV report comparing old and new data
        
        Args:
            old_svls_data: List of dicts with SVL data (already read before deletion)
            old_moves_data: List of dicts with move data (already read before deletion)
            new_svl_ids: List of new SVL IDs
            new_move_ids: List of new move IDs
        """
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Add header
        writer.writerow([
            'Type', 'Product', 'Date', 'Old Value', 'New Value', 
            'Old Quantity', 'New Quantity', 'Old Unit Cost', 'New Unit Cost', 
            'Description', 'Status'
        ])
        
        # Add old SVLs info from pre-saved data
        for svl_data in old_svls_data:
            writer.writerow([
                'SVL',
                svl_data.get('product_name', ''),
                svl_data.get('date', ''),
                svl_data.get('value', 0),
                '',  # New value
                svl_data.get('quantity', 0),
                '',  # New quantity
                svl_data.get('unit_cost', 0),
                '',  # New unit cost
                svl_data.get('description', ''),
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
            
        # Add old moves info from pre-saved data
        for move_data in old_moves_data:
            writer.writerow([
                'Journal Entry',
                '',  # Product not applicable to JE
                move_data.get('date', ''),
                '',  # Old value (not stored)
                '',  # New value
                '',  # Quantity not applicable
                '',  # New quantity
                '',  # Unit cost not applicable
                '',  # New unit cost
                move_data.get('name', '') or move_data.get('ref', ''),
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
        import base64
        
        # Convert string to base64
        csv_bytes = csv_data.encode('utf-8')
        csv_base64 = base64.b64encode(csv_bytes)
        
        attachment = self.env['ir.attachment'].create({
            'name': f'valuation_regeneration_report_{log_record.id}.csv',
            'type': 'binary',
            'datas': csv_base64,
            'res_model': 'valuation.regenerate.log',
            'res_id': log_record.id,
        })
        return attachment

    def _get_products_to_process(self):
        """Get products based on the selected scope"""
        if self.mode == 'product':
            if not self.product_ids:
                # Allow empty products if auto-detect is enabled (will be populated by auto-detect)
                if not self.auto_detect_products:
                    raise ValidationError("Please select at least one product, or enable 'Auto-detect Products'.")
                # Return empty recordset, will be populated by auto-detect
                return self.env['product.product']
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
        
        # Filter by location if specified
        if self.location_ids:
            # Filter SVLs by checking their related stock moves' locations
            svls = svls.filtered(lambda svl: 
                svl.stock_move_id and (
                    svl.stock_move_id.location_id.id in self.location_ids.ids or
                    svl.stock_move_id.location_dest_id.id in self.location_ids.ids
                )
            )
        
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
            'scope_location_ids': [(6, 0, self.location_ids.ids)] if self.location_ids else False,
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

    def _recompute_valuation(self, products, stock_moves_to_reprocess):
        """Recompute valuation layers and journal entries for the selected products
        
        Args:
            products: Products to reprocess
            stock_moves_to_reprocess: Stock moves that had SVLs deleted and need regeneration
        """
        new_svl_ids = []
        new_move_ids = []
        
        for product in products:
            # Filter stock moves for this product
            product_moves = stock_moves_to_reprocess.filtered(lambda m: m.product_id == product)
            
            # Determine the costing method to use
            cost_method = self._get_costing_method(product)
            
            if cost_method == 'fifo':
                svl_ids = self._recompute_fifo_valuation(product, product_moves)
                new_svl_ids.extend(svl_ids)
            elif cost_method == 'avco':
                svl_ids = self._recompute_avco_valuation(product, product_moves)
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
    
    def _recompute_fifo_valuation(self, product, stock_moves_to_reprocess):
        """Recompute FIFO valuation for a specific product
        
        Args:
            product: Product to reprocess
            stock_moves_to_reprocess: Specific stock moves to regenerate SVLs for
        """
        svl_obj = self.env['stock.valuation.layer']
        new_svl_ids = []
        
        # Use provided stock moves or search for all moves in date range
        if stock_moves_to_reprocess:
            # Use the specific moves that had their SVLs deleted
            stock_moves = stock_moves_to_reprocess.sorted(lambda m: (m.date, m.id))
            
            # Filter by location if specified
            if self.location_ids:
                stock_moves = stock_moves.filtered(lambda m:
                    m.location_id.id in self.location_ids.ids or
                    m.location_dest_id.id in self.location_ids.ids
                )
            
            _logger.info(
                f"FIFO Regeneration for product {product.display_name}: "
                f"Reprocessing {len(stock_moves)} specific stock moves"
            )
        else:
            # Fallback: search for moves in date range
            moves_domain = [
                ('product_id', '=', product.id),
                ('state', '=', 'done'),
                ('company_id', '=', self.company_id.id),
            ]
            
            if self.date_from:
                moves_domain.append(('date', '>=', self.date_from))
            if self.date_to:
                moves_domain.append(('date', '<=', self.date_to))
            
            # Add location filter if specified
            if self.location_ids:
                moves_domain.extend([
                    '|',
                    ('location_id', 'in', self.location_ids.ids),
                    ('location_dest_id', 'in', self.location_ids.ids)
                ])
            
            stock_moves = self.env['stock.move'].search(moves_domain, order='date, id')
            
            # Log for debugging
            _logger.info(f"FIFO Regeneration for product {product.display_name}: Found {len(stock_moves)} stock moves in date range")
            if not stock_moves:
                _logger.warning(
                    f"No stock moves found for product {product.display_name}. "
                    f"Date range: {self.date_from} to {self.date_to}"
                )
        
        if not stock_moves:
            _logger.warning(f"No stock moves to process for product {product.display_name}")
            return new_svl_ids
        
        # FIFO Inventory Queue: stores incoming stock layers
        # Format: [{'qty': remaining_qty, 'unit_cost': cost, 'origin_move': move, 'date': date}, ...]
        fifo_queue = []
        
        # Process each stock move to create appropriate SVLs
        for move in stock_moves:
            # Skip moves that don't affect valuation
            # NOTE: We regenerate even if current valuation is manual_periodic, 
            # because these moves originally had SVLs (which we just deleted)
            if move.state != 'done':
                _logger.info(f"Skipping move {move.id} {move.name}: state is {move.state}, not 'done'")
                continue
            if move.product_id.type != 'product':
                _logger.info(f"Skipping move {move.id} {move.name}: product type is {move.product_id.type}, not 'product'")
                continue
            # Don't check valuation method here - we're regenerating SVLs that existed before
            
            _logger.info(f"Processing move {move.id} {move.name}: state={move.state}, valuation={move.product_id.valuation}, type={move.product_id.type}")
            
            move_qty = move.product_uom._compute_quantity(move.product_uom_qty, product.uom_id)
            
            _logger.info(f"Move {move.id} quantity: {move_qty}, is_in={move._is_in()}, is_out={move._is_out()}")
            
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
                }
                
                # Apply landed costs if applicable
                if self.include_landed_cost_layers:
                    landed_cost_adjustment = self._get_landed_cost_adjustment(move)
                    if landed_cost_adjustment:
                        svl_vals['value'] += landed_cost_adjustment
                        svl_vals['unit_cost'] = svl_vals['value'] / move_qty if move_qty else 0
                
                # Create SVL with valuation_regeneration context
                new_svl = svl_obj.with_context(valuation_regeneration=True).create(svl_vals)
                new_svl_ids.append(new_svl.id)
                
                # Update create_date to match the original move date
                # We need to use SQL because create_date is a magic field
                self.env.cr.execute(
                    "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
                    (move.date, new_svl.id)
                )
                # Invalidate cache so the updated date is reflected
                new_svl.invalidate_recordset(['create_date'])
                
                # Add to FIFO queue (only store values, not record references)
                fifo_queue.append({
                    'qty': move_qty,
                    'unit_cost': svl_vals['unit_cost'],
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
                }
                
                # Create SVL with valuation_regeneration context
                new_svl = svl_obj.with_context(valuation_regeneration=True).create(svl_vals)
                new_svl_ids.append(new_svl.id)
                
                # Update create_date to match the original move date
                self.env.cr.execute(
                    "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
                    (move.date, new_svl.id)
                )
                # Invalidate cache so the updated date is reflected
                new_svl.invalidate_recordset(['create_date'])
                
                # Note: We don't update remaining_qty on origin_svl because those are old SVLs
                # that have been deleted. The FIFO queue tracking is done in memory only.
                
                # Create journal entry if needed
                if self.rebuild_account_moves:
                    self._create_journal_entry_for_svl(new_svl)
        
        return new_svl_ids
    
    def _recompute_avco_valuation(self, product, stock_moves_to_reprocess):
        """Recompute AVCO valuation for a specific product
        
        Args:
            product: Product to reprocess
            stock_moves_to_reprocess: Specific stock moves to regenerate SVLs for
        """
        svl_obj = self.env['stock.valuation.layer']
        new_svl_ids = []
        
        # Use provided stock moves or search for all moves in date range
        if stock_moves_to_reprocess:
            # Use the specific moves that had their SVLs deleted
            stock_moves = stock_moves_to_reprocess.sorted(lambda m: (m.date, m.id))
            
            # Filter by location if specified
            if self.location_ids:
                stock_moves = stock_moves.filtered(lambda m:
                    m.location_id.id in self.location_ids.ids or
                    m.location_dest_id.id in self.location_ids.ids
                )
        else:
            # Fallback: search for moves in date range
            moves_domain = [
                ('product_id', '=', product.id),
                ('state', '=', 'done'),
                ('company_id', '=', self.company_id.id),
            ]
            
            if self.date_from:
                moves_domain.append(('date', '>=', self.date_from))
            if self.date_to:
                moves_domain.append(('date', '<=', self.date_to))
            
            # Add location filter if specified
            if self.location_ids:
                moves_domain.extend([
                    '|',
                    ('location_id', 'in', self.location_ids.ids),
                    ('location_dest_id', 'in', self.location_ids.ids)
                ])
            
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
            # NOTE: We regenerate even if current valuation is manual_periodic,
            # because these moves originally had SVLs (which we just deleted)
            if move.state != 'done':
                continue
            if move.product_id.type != 'product':
                continue
            # Don't check valuation method here - we're regenerating SVLs that existed before
            
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
            new_svl = svl_obj.with_context(valuation_regeneration=True).create(svl_vals)
            new_svl_ids.append(new_svl.id)
            
            # Update create_date to match the original move date
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
                (move.date, new_svl.id)
            )
            # Invalidate cache so the updated date is reflected
            new_svl.invalidate_recordset(['create_date'])
            
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