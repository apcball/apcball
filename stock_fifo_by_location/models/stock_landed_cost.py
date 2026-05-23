# -*- coding: utf-8 -*-
"""
Stock Landed Cost Model Extension

This module extends stock.landed.cost to support per-location landed cost allocation.
When landed costs are applied to inventory at a specific location, the module ensures
that these costs are properly tracked and allocated proportionally during internal
transfers.
"""

from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round, float_compare, float_is_zero


class StockLandedCost(models.Model):
    """
    Extension of stock.landed.cost to support per-warehouse tracking.
    
    When a landed cost is posted, it creates allocations in 
    stock.valuation.layer.landed.cost to track the cost at each warehouse.
    """
    
    _inherit = 'stock.landed.cost'
    
    location_landed_cost_ids = fields.One2many(
        'stock.valuation.layer.landed.cost',
        'landed_cost_id',
        string='Warehouse-based Landed Costs',
        help='Per-warehouse breakdown of this landed cost.',
        readonly=True
    )
    
    @api.model
    def create(self, vals):
        """Create landed cost record."""
        record = super().create(vals)
        return record
    
    def button_validate(self):
        """
        Override validation so landed costs follow cost origin / current positions.
        """
        self._check_can_validate()
        cost_without_adjustment_lines = self.filtered(lambda c: not c.valuation_adjustment_lines)
        if cost_without_adjustment_lines:
            cost_without_adjustment_lines.compute_landed_cost()
        if not self._check_sum():
            raise UserError(_('Cost and adjustments lines do not match. You should maybe recompute the landed costs.'))

        for cost in self:
            move = self.env['account.move']
            move_vals = {
                'journal_id': cost.account_journal_id.id,
                'date': cost.date,
                'ref': cost.name,
                'line_ids': [],
                'move_type': 'entry',
            }
            valuation_layer_ids = []
            cost_to_add_byproduct = defaultdict(lambda: 0.0)

            for line in cost.valuation_adjustment_lines.filtered(lambda line: line.move_id):
                origin_layer, linked_layers, remaining_qty, move_qty = cost._get_landed_cost_targets(line.move_id)
                cost_to_add = (remaining_qty / move_qty) * line.additional_landed_cost if move_qty else 0.0
                product = line.move_id.product_id

                if not cost.company_id.currency_id.is_zero(cost_to_add):
                    vals_list = []
                    layer_total_qty = sum(linked_layers.mapped('remaining_qty')) or remaining_qty or 1.0
                    for target_layer in linked_layers:
                        layer_qty = target_layer.remaining_qty or 0.0
                        if float_compare(layer_qty, 0.0, precision_digits=6) <= 0:
                            continue
                        layer_cost_to_add = cost_to_add * (layer_qty / layer_total_qty)
                        vals_list.append({
                            'value': layer_cost_to_add,
                            'unit_cost': 0,
                            'quantity': 0,
                            'remaining_qty': 0,
                            'remaining_value': 0,
                            'stock_valuation_layer_id': target_layer.id,
                            'description': cost.name,
                            'stock_move_id': line.move_id.id,
                            'product_id': product.id,
                            'stock_landed_cost_id': cost.id,
                            'company_id': cost.company_id.id,
                            'warehouse_id': target_layer.warehouse_id.id,
                            'origin_valuation_layer_id': origin_layer.id if origin_layer else False,
                        })
                        target_layer.remaining_value += layer_cost_to_add
                    if vals_list:
                        valuation_layer = self.env['stock.valuation.layer'].create(vals_list)
                        valuation_layer_ids += valuation_layer.ids

                cost_to_add_byproduct[product] += cost_to_add

                if product.valuation != "real_time":
                    continue

                qty_out = max(move_qty - remaining_qty, 0.0) if line.move_id._is_in() else move_qty
                move_vals['line_ids'] += line._create_accounting_entries(move, qty_out)

            products = self.env['product.product'].browse(p.id for p in cost_to_add_byproduct.keys()).with_company(
                cost.company_id
            )
            for product in products:
                if not float_is_zero(product.quantity_svl, precision_rounding=product.uom_id.rounding):
                    product.sudo().with_context(disable_auto_svl=True).standard_price += (
                        cost_to_add_byproduct[product] / product.quantity_svl
                    )

            move_vals['stock_valuation_layer_ids'] = [(6, None, valuation_layer_ids)]
            cost_vals = {'state': 'done'}
            if move_vals.get("line_ids"):
                move = move.create(move_vals)
                cost_vals.update({'account_move_id': move.id})
            cost.write(cost_vals)
            cost._allocate_landed_costs_by_location()
            if cost.account_move_id:
                move._post()
            cost.reconcile_landed_cost()
        return True

    def get_valuation_lines(self):
        """Build valuation lines from cost origin and current warehouse positions."""
        self.ensure_one()
        lines = []

        for move in self._get_targeted_move_ids():
            product = move.product_id
            cost_method = self._get_effective_cost_method(product)
            if (
                cost_method not in ('fifo', 'average')
                or move.state == 'cancel'
                or not move.quantity
            ):
                continue

            origin_layer, position_layers, remaining_qty, move_qty = self._get_landed_cost_targets(move)
            if not origin_layer:
                continue

            former_cost = sum(position_layers.mapped('position_valuation')) if position_layers else 0.0
            qty = move.product_uom._compute_quantity(move.quantity, product.uom_id)

            lines.append({
                'product_id': product.id,
                'move_id': move.id,
                'quantity': qty,
                'former_cost': former_cost,
                'weight': product.weight * qty,
                'volume': product.volume * qty,
            })

        if not lines:
            target_model_descriptions = dict(self._fields['target_model']._description_selection(self.env))
            raise UserError(
                _("You cannot apply landed costs on the chosen %s(s). Landed costs can only be applied for products with FIFO or average costing method.",
                  target_model_descriptions[self.target_model]))
        return lines

    def _get_effective_cost_method(self, product):
        """Return the effective cost method."""
        # product.cost_method is a related field → categ_id.property_cost_method (stock_account)
        return getattr(product, 'cost_method', False) or getattr(product.categ_id, 'property_cost_method', False) or False

    def _get_effective_valuation_method(self, product):
        """Return the effective valuation method."""
        # product.valuation is a related field → categ_id.property_valuation (stock_account)
        return getattr(product, 'valuation', False) or getattr(product.categ_id, 'property_valuation', False) or False

    def _get_landed_cost_targets(self, move):
        """Return origin layer, current position layers, remaining qty, and original move qty.
        
        Transfer ≠ Consumption: Use origin_remaining_qty to check if goods still exist.
        remaining_qty may be 0 after transfers, but origin_remaining_qty tracks real consumption.
        """
        qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
        move_layers = move.stock_valuation_layer_ids
        if not move_layers:
            move_layers = self.env['stock.valuation.layer'].search([
                ('stock_move_id', '=', move.id),
            ])

        positive_layers = move_layers.filtered(lambda layer: layer.quantity > 0)
        negative_layers = move_layers.filtered(lambda layer: layer.quantity < 0)

        # Resolve origin layers from this move's layers
        origin_layers = positive_layers.mapped('origin_valuation_layer_id')
        if positive_layers:
            origin_layers |= positive_layers.filtered(lambda layer: not layer.origin_valuation_layer_id)
        if not origin_layers:
            origin_layers = negative_layers.mapped('origin_valuation_layer_id')

        origin_layer = origin_layers[:1]
        position_layers = self.env['stock.valuation.layer']
        if origin_layers:
            # Collect ALL layers in the origin chain (including intermediate transfer layers)
            # so we can find position layers that link to any of them.
            # e.g., Receipt(365) → TransferOut(366) → Position(367, ovid=366)
            # We need to find 367 even though it links to 366, not 365 directly.
            all_chain_ids = set(origin_layers.ids)
            # Include negative layers from this move — their position layers link to them
            if negative_layers:
                all_chain_ids.update(negative_layers.ids)
            # Also include negative layers that consumed from origin_layers
            consuming_layers = self.env['stock.valuation.layer'].search([
                ('origin_valuation_layer_id', 'in', list(all_chain_ids)),
            ])
            if consuming_layers:
                all_chain_ids.update(consuming_layers.ids)

            # Find all position layers linked to any layer in the chain
            position_layers = self.env['stock.valuation.layer'].search([
                ('origin_valuation_layer_id', 'in', list(all_chain_ids)),
                ('warehouse_id', '!=', False),
                ('quantity', '>', 0),
            ])
            # Transfer ≠ Consumption: origin layer itself may have remaining_qty=0
            # but origin_remaining_qty > 0 (goods transferred but not consumed)
            direct_origin_positions = origin_layers.filtered(
                lambda layer: layer.origin_remaining_qty > 0
            )
            position_layers |= direct_origin_positions

        # Use remaining_qty from position layers for distribution
        remaining_qty = sum(position_layers.mapped('remaining_qty')) if position_layers else 0.0
        # Fallback: use origin_remaining_qty as source of truth
        if remaining_qty <= 0 and origin_layers:
            remaining_qty = sum(origin_layers.mapped('origin_remaining_qty'))
        return origin_layer, position_layers, remaining_qty, qty
    
    def _allocate_landed_costs_by_location(self):
        """
        Create per-warehouse landed cost allocations.
        
        For each valuation adjustment line with a landed cost, create or update
        stock.valuation.layer.landed.cost records to track the cost at the
        specific warehouse where the goods are received.
        """
        lc_location_model = self.env['stock.valuation.layer.landed.cost']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        for landed_cost in self:
            if landed_cost.state != 'done':
                continue
            
            for val_adj_line in landed_cost.valuation_adjustment_lines:
                if not val_adj_line.move_id:
                    continue
                
                move = val_adj_line.move_id
                product = move.product_id
                location = move.location_dest_id  # Where the goods arrived
                warehouse = location.warehouse_id if location else None
                company = landed_cost.company_id
                lc_value = val_adj_line.additional_landed_cost
                qty = move.product_uom._compute_quantity(
                    move.quantity, move.product_id.uom_id
                )
                
                if not warehouse:
                    # Skip if no warehouse found
                    continue
                
                # Find or create valuation layer for this move at the warehouse
                # The valuation layer should exist if landed costs are applied after receipt
                svl_records = self.env['stock.valuation.layer'].search([
                    ('stock_move_id', '=', move.id),
                    ('warehouse_id', '=', warehouse.id),
                ], limit=1)
                
                if svl_records:
                    svl = svl_records[0]
                    origin_layer = self._resolve_origin_cost_layer_from_svl(svl)
                    self._allocate_landed_cost_to_current_positions(
                        lc_location_model, origin_layer, landed_cost, val_adj_line,
                        lc_value, qty, precision
                    )

    def _resolve_origin_cost_layer_from_svl(self, svl):
        """Resolve the true cost-origin layer even when landed cost is posted on a transfer move."""
        if svl.origin_valuation_layer_id:
            return svl.origin_valuation_layer_id
        return svl

    def _allocate_landed_cost_to_current_positions(self, lc_location_model, origin_layer,
                                                   landed_cost, val_adj_line,
                                                   lc_value, qty, precision):
        """Allocate landed cost to current warehouse positions of the origin layer.
        
        Transfer ≠ Consumption: position layers at other warehouses have remaining_qty > 0.
        The origin layer itself may have remaining_qty=0 but origin_remaining_qty > 0.
        """
        # Ensure latest data from DB (origin_valuation_layer_id may have just been set)
        origin_layer.invalidate_recordset(['position_layer_ids'])
        
        position_layers = origin_layer.position_layer_ids.filtered(
            lambda layer: layer.remaining_qty > 0 and layer.warehouse_id
        )
        
        # Build allocation targets: position layers at other warehouses + origin layer itself
        # For partial transfers, both can have remaining_qty > 0
        allocation_targets = self.env['stock.valuation.layer']
        
        # Add position layers at other warehouses (transferred stock)
        allocation_targets |= position_layers
        
        # Add origin layer itself if it still has stock at its own warehouse
        if origin_layer.remaining_qty > 0 and origin_layer.warehouse_id:
            allocation_targets |= origin_layer
        
        # Fallback: if nothing found, use origin layer
        if not allocation_targets:
            allocation_targets = origin_layer
        
        total_qty = sum(allocation_targets.mapped('remaining_qty')) or qty
        if total_qty <= 0:
            total_qty = qty

        for target_layer in allocation_targets:
            target_qty = target_layer.remaining_qty if target_layer.remaining_qty > 0 else qty
            proportion = target_qty / total_qty if total_qty else 0.0
            allocated_value = float_round(lc_value * proportion, precision_digits=precision)

            existing = lc_location_model.search([
                ('valuation_layer_id', '=', target_layer.id),
                ('warehouse_id', '=', target_layer.warehouse_id.id),
                ('landed_cost_id', '=', landed_cost.id),
            ], limit=1)

            if existing:
                existing.landed_cost_value = allocated_value
                existing.quantity = target_qty
            else:
                lc_location_model.create({
                    'valuation_layer_id': target_layer.id,
                    'warehouse_id': target_layer.warehouse_id.id,
                    'landed_cost_id': landed_cost.id,
                    'valuation_adjustment_line_id': val_adj_line.id,
                    'landed_cost_value': allocated_value,
                    'quantity': target_qty,
                })

        origin_layer.write({
            'origin_remaining_value': origin_layer.origin_remaining_value + float_round(lc_value, precision_digits=precision)
        })

    def action_cancel(self):
        """
        Override cancel to also remove location-based allocations.
        """
        # Remove location-based allocations before canceling
        for landed_cost in self:
            landed_cost.location_landed_cost_ids.unlink()
        
        # Call parent cancel
        return super().action_cancel()


class StockValuationAdjustmentLines(models.Model):
    """
    Extension of stock.valuation.adjustment.lines.
    
    Adds reference to location-specific landed cost allocations.
    """
    
    _inherit = 'stock.valuation.adjustment.lines'
    
    location_based_allocations = fields.One2many(
        'stock.valuation.layer.landed.cost',
        'valuation_adjustment_line_id',
        string='Warehouse-based Allocations',
        help='Breakdown of this landed cost by warehouse.',
        readonly=True
    )
    
    def unlink(self):
        """Override unlink to cascade delete location-based allocations."""
        # The CASCADE constraint will handle this automatically,
        # but we explicitly unlink to ensure clean deletion
        for line in self:
            if line.location_based_allocations:
                line.location_based_allocations.unlink()
        return super(StockValuationAdjustmentLines, self).unlink()
