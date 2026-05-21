# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.tools.float_utils import float_is_zero
from collections import defaultdict
from odoo.exceptions import UserError


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    is_cancel = fields.Boolean(
        string='Cancel', default=False,
        help='If the user clicks the "Cancel" button once, '
             'it will hide the button and make it invisible.',
    )

    def _revert_average_cost(self):
        """Revert average cost price for products affected by this landed cost."""
        for cost in self:
            cost = cost.with_company(cost.company_id)
            cost_to_add_byproduct = defaultdict(lambda: 0.0)
            for line in cost.valuation_adjustment_lines.filtered(lambda l: l.move_id):
                remaining_qty = sum(
                    line.move_id.stock_valuation_layer_ids.mapped('remaining_qty'))
                move_qty = line.move_id.product_uom._compute_quantity(
                    line.move_id.quantity, line.move_id.product_id.uom_id)
                if not move_qty:
                    continue
                cost_to_add = (remaining_qty / move_qty) * line.additional_landed_cost
                product = line.move_id.product_id
                if product.cost_method in ('average', 'fifo'):
                    cost_to_add_byproduct[product] -= cost_to_add

            products = self.env['product.product'].browse(
                p.id for p in cost_to_add_byproduct.keys()
            ).with_company(cost.company_id)
            for product in products:
                if not float_is_zero(
                    product.quantity_svl,
                    precision_rounding=product.uom_id.rounding,
                ):
                    product.sudo().with_context(
                        disable_auto_svl=True
                    ).standard_price += (
                        cost_to_add_byproduct[product] / product.quantity_svl
                    )

    def _revert_landed_cost_entries(self):
        """Common logic to revert all entries created by a landed cost.

        Reverts:
        1. Average/FIFO cost price
        2. Vendor bill landed cost lines
        3. Journal entry (account.move)
        4. Stock valuation layers via revaluation
        5. Valuation adjustment lines
        """
        self.ensure_one()
        rec = self

        # 1. Revert average cost price
        rec._revert_average_cost()

        # 2. Revert vendor bill lines
        if rec.vendor_bill_id and rec.vendor_bill_id.line_ids:
            if rec.vendor_bill_id.state == 'posted':
                rec.vendor_bill_id.button_draft()
            landed_cost_lines = rec.vendor_bill_id.line_ids.filtered(
                lambda x: x.is_landed_costs_line is True)
            if landed_cost_lines:
                landed_cost_lines.unlink()

        # 3. Revert journal entry
        if rec.account_move_id:
            account_move = rec.account_move_id
            if account_move.state == 'posted':
                account_move.button_draft()
            account_move.line_ids.unlink()
            account_move.unlink()

        # 4. Revert stock valuation layers via revaluation
        for layer in rec.stock_valuation_layer_ids:
            self.env['stock.valuation.layer.revaluation'].create([{
                'product_id': layer.product_id.id,
                'company_id': layer.company_id.id,
                'added_value': -layer.value,
            }]).action_validate_revaluation()

        # 5. Remove valuation adjustment lines
        if rec.valuation_adjustment_lines:
            rec.valuation_adjustment_lines.unlink()

    def action_landed_cost_cancel(self):
        """Cancel landed cost → state = cancelled."""
        for rec in self:
            rec._revert_landed_cost_entries()
            rec.write({'state': 'cancel'})

    def action_landed_cost_reset_and_cancel(self):
        """Cancel landed cost → state = draft (reset)."""
        for rec in self:
            rec._revert_landed_cost_entries()
            rec.write({'state': 'draft'})

    def action_landed_cost_cancel_and_delete(self):
        """Cancel and delete the landed cost record."""
        for rec in self:
            rec._revert_landed_cost_entries()
            rec.unlink()

    def action_landed_cost_cancel_form(self):
        """Cancel from form view — uses config setting to determine mode."""
        for rec in self:
            rec._revert_landed_cost_entries()

        landed_mode = self.env['ir.config_parameter'].sudo().get_param(
            'cancel_landed_cost_odoo.land_cost_cancel_modes')

        if landed_mode == 'cancel':
            self.write({'state': 'cancel', 'is_cancel': True})
        elif landed_mode == 'cancel_draft':
            self.write({'state': 'draft', 'is_cancel': False})
        elif landed_mode == 'cancel_delete':
            self.unlink()
            return {
                'name': _('Landed Cost'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.landed.cost',
                'view_mode': 'tree,form',
                'target': 'current',
            }
