
# -*- coding: utf-8 -*-
import logging
from odoo import models

_logger = logging.getLogger(__name__)

class StockMove(models.Model):
    _inherit = "stock.move"

    @staticmethod
    def _first_segment(loc):
        try:
            return (loc.complete_name or loc.display_name or "").split("/")[0].strip()
        except Exception:
            return ""

    @staticmethod
    def _endswith(loc, tail):
        try:
            return (loc.complete_name or loc.display_name or "").strip().endswith(tail)
        except Exception:
            return False

    def _is_input_to_stock_same_wh(self, m):
        if not (m.location_id and m.location_dest_id):
            return False
        if not (m.location_id.usage == "internal" and m.location_dest_id.usage == "internal"):
            return False
        same_wh = self._first_segment(m.location_id) == self._first_segment(m.location_dest_id) != ""
        return same_wh and self._endswith(m.location_id, "Input") and self._endswith(m.location_dest_id, "Stock")

    def _policy_skip_moves(self):
        # Check if force_valuation is enabled in context - this overrides everything
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation enabled - not skipping any moves for: %s", self.mapped('name'))
            return self.env['stock.move']  # Return empty recordset to not skip any moves
        
        # Original logic but use the new method
        skip_moves = self.filtered(lambda m:
            (m.location_id and m.location_id._should_skip_valuation()) or
            (m.location_dest_id and m.location_dest_id._should_skip_valuation()) or
            self._is_input_to_stock_same_wh(m)
        )
        if skip_moves:
            _logger.info("[tqt] Skipping valuation for moves: %s", skip_moves.mapped('name'))
        return skip_moves

    def _should_valuate(self):
        self.ensure_one()
        _logger.info("[tqt] _should_valuate called for move: %s", self.name)
        
        # FORCE OVERRIDE: If force_valuation context is True, always return True
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] FORCE VALUATION - Always True for move: %s", self.name)
            return True
        
        # Continue with normal logic
        result = super()._should_valuate()
        _logger.info("[tqt] Normal _should_valuate returned: %s for %s", result, self.name)
        return result

    def _is_out(self):
        # Override to ensure OUT moves are recognized properly with force_valuation
        if self.env.context.get('force_valuation', False):
            result = super()._is_out()
            _logger.info("[tqt] Force valuation - _is_out for %s: %s", self.name, result)
            return result
        return super()._is_out()

    def _is_in(self):
        # Override to ensure IN moves are recognized properly with force_valuation
        if self.env.context.get('force_valuation', False):
            result = super()._is_in()
            _logger.info("[tqt] Force valuation - _is_in for %s: %s", self.name, result)
            return result
        return super()._is_in()

    def _is_dropshipped(self):
        # Override to ensure dropship detection works with force_valuation
        if self.env.context.get('force_valuation', False):
            # With force valuation, treat as regular stock move, not dropshipped
            _logger.info("[tqt] Force valuation - treating %s as non-dropshipped", self.name)
            return False
        return super()._is_dropshipped()

    def _is_dropshipped_returned(self):
        # Override to ensure dropship return detection works with force_valuation
        if self.env.context.get('force_valuation', False):
            # With force valuation, treat as regular stock move
            _logger.info("[tqt] Force valuation - treating %s as non-dropshipped return", self.name)
            return False
        return super()._is_dropshipped_returned()

    def _get_valuation_lines_data(self, *args, **kwargs):
        # Check force_valuation context first
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation enabled - creating accounting lines for %s", self.mapped("name"))
            return super()._get_valuation_lines_data(*args, **kwargs)
            
        lines = super()._get_valuation_lines_data(*args, **kwargs)
        if not self._policy_skip_moves():
            return lines
        _logger.info("[tqt] Skip accounting lines for moves: %s", self.mapped("name"))
        # Return an empty list to indicate no valuation lines
        return []

    def _generate_valuation_lines_data(self, partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description):
        # Override to ensure valuation lines are generated when force_valuation is True
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - generating valuation lines for %s", self.name)
            return super()._generate_valuation_lines_data(partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description)
        
        # Use the policy check
        if self._policy_skip_moves():
            _logger.info("[tqt] Skip valuation lines generation for %s (policy)", self.name)
            return {}
        
        return super()._generate_valuation_lines_data(partner_id, qty, debit_value, credit_value, debit_account_id, credit_account_id, svl_id, description)

    def _create_in_svl(self, forced_quantity=None):
        # Check force_valuation context first
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] FORCE VALUATION - Creating IN SVL for all moves: %s", self.mapped('name'))
            res = self.env['stock.valuation.layer']
            for move in self:
                try:
                    svl = super(StockMove, move)._create_in_svl(forced_quantity=forced_quantity)
                    _logger.info("[tqt] Created IN SVL for move %s: %s", move.name, svl.ids if svl else "None")
                    res |= svl
                except Exception as e:
                    _logger.error("[tqt] Error creating IN SVL for move %s: %s", move.name, e)
            return res
            
        moves_to_value = self - self._policy_skip_moves()
        if not moves_to_value:
            _logger.info("[tqt] Skip IN SVL for all moves (policy)")
            return self.env['stock.valuation.layer']
        res = self.env['stock.valuation.layer']
        for move in moves_to_value:
            res |= super(StockMove, move)._create_in_svl(forced_quantity=forced_quantity)
        return res

    def _create_out_svl(self, forced_quantity=None):
        # Check force_valuation context first
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] FORCE VALUATION - Creating OUT SVL for all moves: %s", self.mapped('name'))
            res = self.env['stock.valuation.layer']
            for move in self:
                try:
                    svl = super(StockMove, move)._create_out_svl(forced_quantity=forced_quantity)
                    _logger.info("[tqt] Created OUT SVL for move %s: %s", move.name, svl.ids if svl else "None")
                    res |= svl
                except Exception as e:
                    _logger.error("[tqt] Error creating OUT SVL for move %s: %s", move.name, e)
            return res
            
        moves_to_value = self - self._policy_skip_moves()
        if not moves_to_value:
            _logger.info("[tqt] Skip OUT SVL for all moves (policy)")
            return self.env['stock.valuation.layer']
        res = self.env['stock.valuation.layer']
        for move in moves_to_value:
            res |= super(StockMove, move)._create_out_svl(forced_quantity=forced_quantity)
        return res

    def _get_price_unit(self):
        # Override to use price from PO when available and force_valuation is enabled
        if self.env.context.get('force_valuation', False):
            # Try to get price from purchase order line first
            if self.purchase_line_id and self.purchase_line_id.price_unit:
                _logger.info("[tqt] Using PO price %s for move %s", self.purchase_line_id.price_unit, self.name)
                return self.purchase_line_id.price_unit
            
            # Try to get price from move's price_unit if set
            if hasattr(self, 'price_unit') and self.price_unit:
                _logger.info("[tqt] Using move price_unit %s for move %s", self.price_unit, self.name)
                return self.price_unit
                
            # Fallback to product standard price
            if self.product_id.standard_price:
                _logger.info("[tqt] Using product standard price %s for move %s", self.product_id.standard_price, self.name)
                return self.product_id.standard_price
                
        return super()._get_price_unit()

    def _prepare_common_svl_vals(self):
        # Override to ensure SVL preparation works with force_valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - preparing SVL vals for %s", self.name)
            vals = super()._prepare_common_svl_vals()
            # Ensure unit cost is set
            if not vals.get('unit_cost'):
                vals['unit_cost'] = self._get_price_unit()
            _logger.info("[tqt] SVL vals for %s: %s", self.name, vals)
            return vals
        return super()._prepare_common_svl_vals()

    def product_price_update_before_done(self, forced_qty=None):
        # Override to ensure product price updates work with force_valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - product price update for %s", self.name)
            return super().product_price_update_before_done(forced_qty=forced_qty)
        return super().product_price_update_before_done(forced_qty=forced_qty)

    def _get_accounting_data_for_valuation(self):
        # Override to ensure accounting data is retrieved with force_valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - getting accounting data for %s", self.name)
            result = super()._get_accounting_data_for_valuation()
            _logger.info("[tqt] Accounting data for %s: %s", self.name, result)
            return result
        return super()._get_accounting_data_for_valuation()

    def _get_src_account(self, accounts_data):
        # Override to ensure source account is found with force_valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - getting source account for %s", self.name)
            result = super()._get_src_account(accounts_data)
            _logger.info("[tqt] Source account for %s: %s", self.name, result)
            return result
        return super()._get_src_account(accounts_data)

    def _get_dest_account(self, accounts_data):
        # Override to ensure destination account is found with force_valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation - getting destination account for %s", self.name)
            result = super()._get_dest_account(accounts_data)
            _logger.info("[tqt] Destination account for %s: %s", self.name, result)
            return result
        return super()._get_dest_account(accounts_data)

    def _create_valuation_layers(self, forced_quantity=None, forced_unit_price=None):
        # Check force_valuation context first
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation enabled - creating valuation layers for all moves")
            res = self.env['stock.valuation.layer']
            for move in self:
                # Use price from PO if available
                unit_price = forced_unit_price
                if not unit_price:
                    unit_price = move._get_price_unit()
                
                res |= super(StockMove, move)._create_valuation_layers(
                    forced_quantity=forced_quantity, forced_unit_price=unit_price
                )
            return res
            
        moves_to_value = self - self._policy_skip_moves()
        if not moves_to_value:
            _logger.info("[tqt] Skip _create_valuation_layers (policy)")
            return self.env['stock.valuation.layer']
        res = self.env['stock.valuation.layer']
        for move in moves_to_value:
            res |= super(StockMove, move)._create_valuation_layers(
                forced_quantity=forced_quantity, forced_unit_price=forced_unit_price
            )
        return res

    def _account_entry_move(self, *args, **kwargs):
        # Check force_valuation context first
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] Force valuation enabled - creating account entries for all moves")
            res = self.env['account.move']
            for move in self:
                try:
                    result = super(StockMove, move)._account_entry_move(*args, **kwargs)
                    res |= result
                    _logger.info("[tqt] Created account entry for move %s: %s", move.name, result.ids if result else "None")
                except Exception as e:
                    _logger.error("[tqt] Error creating account entry for move %s: %s", move.name, e)
            return res
            
        moves_to_post = self - self._policy_skip_moves()
        if not moves_to_post:
            _logger.info("[tqt] Skip _account_entry_move (policy)")
            return self.env['account.move']
        res = self.env['account.move']
        for move in moves_to_post:
            res |= super(StockMove, move)._account_entry_move(*args, **kwargs)
        return res

    def _action_done(self, cancel_backorder=False):
        # Add comprehensive logging and force valuation
        if self.env.context.get('force_valuation', False):
            _logger.info("[tqt] FORCE VALUATION ENABLED - Processing moves: %s", self.mapped('name'))
            
            # Force create valuation layers manually if needed
            for move in self:
                _logger.info("[tqt] Processing move: %s", move.name)
                _logger.info("[tqt] Product: %s, Type: %s", move.product_id.name, move.product_id.type)
                _logger.info("[tqt] Quantity: %s, Price Unit: %s", move.product_uom_qty, getattr(move, 'price_unit', 0))
                
                # Check product valuation settings
                if move.product_id.type == 'product':
                    if move.product_id.categ_id.property_valuation != 'real_time':
                        _logger.warning("[tqt] Product %s has manual valuation! Setting to real_time temporarily", move.product_id.name)
                        # Temporarily change to real_time valuation
                        move.product_id.categ_id.with_context(force_valuation=True).write({'property_valuation': 'real_time'})
                    
                    if not move.product_id.categ_id.property_cost_method:
                        _logger.warning("[tqt] Product %s has no cost method! Setting to standard", move.product_id.name)
                        move.product_id.categ_id.with_context(force_valuation=True).write({'property_cost_method': 'standard'})
        
        # Continue with parent method
        result = super()._action_done(cancel_backorder=cancel_backorder)
        
        # After parent processing, manually create valuation if needed
        if self.env.context.get('force_valuation', False):
            for move in self.filtered(lambda m: m.state == 'done' and m.product_id.type == 'product'):
                # Check if SVL was created
                existing_svl = self.env['stock.valuation.layer'].search([('stock_move_id', '=', move.id)])
                if not existing_svl:
                    _logger.warning("[tqt] No SVL found for move %s, attempting manual creation", move.name)
                    # Try to manually trigger valuation layer creation
                    try:
                        if move._is_in():
                            move._create_in_svl()
                        elif move._is_out():
                            move._create_out_svl()
                        else:
                            move._create_valuation_layers()
                    except Exception as e:
                        _logger.error("[tqt] Failed to manually create SVL for move %s: %s", move.name, e)
                else:
                    _logger.info("[tqt] SVL already exists for move %s: %s", move.name, existing_svl.ids)
        
        return result
