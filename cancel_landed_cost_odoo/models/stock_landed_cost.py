# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.tools.float_utils import float_is_zero, float_compare
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

    def _create_reversal_journal_entry(self):
        """Create a reversal journal entry that reverses the original JE.

        Creates reversal (flip debit/credit) and resets original JE to draft.
        """
        self.ensure_one()

        if not self.account_move_id:
            return self.env['account.move']

        original_move = self.account_move_id

        reversal_lines = []
        for line in original_move.line_ids:
            reversal_lines.append((0, 0, {
                'name': _('Reversal of: %s') % line.name,
                'account_id': line.account_id.id,
                'partner_id': line.partner_id.id,
                'debit': line.credit,
                'credit': line.debit,
                'quantity': line.quantity,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
            }))

        if not reversal_lines:
            return self.env['account.move']

        reversal_move = self.env['account.move'].create({
            'journal_id': original_move.journal_id.id,
            'date': fields.Date.today(),
            'ref': _('Reversal of Landed Cost: %s') % self.name,
            'move_type': 'entry',
            'line_ids': reversal_lines,
        })
        reversal_move.action_post()

        # Reset original JE to draft then delete
        if original_move.state == 'posted':
            original_move.button_draft()
        original_move.unlink()

        return reversal_move

    def _unlink_svl_layers(self):
        """Remove SVL layers created by this landed cost.

        Deletes LC SVL layers and recomputes parent chain remaining_qty.
        This allows re-validation to create fresh SVL layers.
        """
        self.ensure_one()

        # Collect parent layers before deleting
        parent_layer_ids = set()
        for layer in self.stock_valuation_layer_ids:
            if layer.stock_valuation_layer_id:
                parent_layer_ids.add(layer.stock_valuation_layer_id.id)

        # Delete SVL layers in reverse order (newest first)
        svl_layers = self.stock_valuation_layer_ids.sorted(key=lambda l: -l.id)
        for layer in svl_layers:
            # Delete linked account move first if exists
            if layer.account_move_id:
                if layer.account_move_id.state == 'posted':
                    layer.account_move_id.button_draft()
                layer.account_move_id.unlink()
            layer.sudo().unlink()

        # Recompute remaining_qty for affected parent layers
        self._recompute_parent_remaining_qty(parent_layer_ids)

    def _recompute_parent_remaining_qty(self, parent_layer_ids):
        """Recompute remaining_qty for parent SVL layers after LC SVL deletion."""
        if not parent_layer_ids:
            return

        parent_layers = self.env['stock.valuation.layer'].browse(parent_layer_ids).exists()
        for parent in parent_layers:
            # remaining_qty = parent.quantity - sum of child SVL quantities that are outgoing
            child_layers = self.env['stock.valuation.layer'].search([
                ('stock_valuation_layer_id', '=', parent.id),
            ])
            # Sum of value reduction from children (outgoing moves, other LCs, etc.)
            child_value_out = sum(
                c.value for c in child_layers if c.value < 0
            )
            # Original remaining should be restored by the LC SVL deletion
            # Simply recompute: remaining_qty = quantity - abs(outgoing from children)
            outgoing = parent.quantity + child_value_out  # child_value_out is negative
            new_remaining = parent.quantity - abs(outgoing) if outgoing < 0 else parent.quantity

            rounding = parent.product_id.uom_id.rounding or 0.01
            if float_compare(new_remaining, parent.remaining_qty, precision_rounding=rounding) != 0:
                parent.sudo().remaining_qty = max(new_remaining, 0.0)

    def _revert_vendor_bill_lines(self):
        """Remove landed cost lines from vendor bill and reset to draft."""
        self.ensure_one()
        if self.vendor_bill_id and self.vendor_bill_id.line_ids:
            if self.vendor_bill_id.state == 'posted':
                self.vendor_bill_id.button_draft()
            landed_cost_lines = self.vendor_bill_id.line_ids.filtered(
                lambda x: x.is_landed_costs_line is True)
            if landed_cost_lines:
                landed_cost_lines.unlink()

    def _revert_landed_cost_entries(self):
        """Revert all entries created by a landed cost.

        Order:
        1. Revert average cost price
        2. Create reversal JE + delete original JE
        3. Delete SVL layers + recompute parent chain
        4. Remove vendor bill landed cost lines
        5. Keep valuation_adjustment_lines — needed for re-validate
        6. Reset state to draft so user can validate again
        """
        self.ensure_one()

        # 1. Revert average cost price
        self._revert_average_cost()

        # 2. Create reversal JE + delete original
        self._create_reversal_journal_entry()

        # 3. Delete SVL layers + recompute parent
        self._unlink_svl_layers()

        # 4. Remove vendor bill LC lines
        self._revert_vendor_bill_lines()

        # 5. valuation_adjustment_lines kept — user can re-validate
        # Clear former_cost and additional_landed_cost so Odoo recalculates
        self.valuation_adjustment_lines.write({
            'former_cost': 0.0,
            'additional_landed_cost': 0.0,
        })

    def action_landed_cost_cancel(self):
        """Cancel landed cost → reset to draft for re-validation."""
        for rec in self:
            rec._revert_landed_cost_entries()
            rec.write({'state': 'draft', 'is_cancel': False})

    def action_landed_cost_reset_and_cancel(self):
        """Cancel landed cost → reset to draft."""
        for rec in self:
            rec._revert_landed_cost_entries()
            rec.write({'state': 'draft', 'is_cancel': False})

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
            # Reset to draft so user can re-validate
            self.write({'state': 'draft', 'is_cancel': False})
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
