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

        # Reset original JE to draft (keep for audit trail)
        if original_move.state == 'posted':
            original_move.button_draft()

        return reversal_move

    def _unlink_svl_layers(self):
        """Remove SVL layers created by this landed cost.

        Instead of creating negative SVL (which doesn't update remaining_qty chain),
        we directly delete the LC SVL layers and recompute parent chain.

        This is the correct approach because:
        - LC SVL has stock_valuation_layer_id pointing to parent move SVL
        - Deleting LC SVL will allow parent SVL remaining_qty to be correct
        - Odoo will recompute the chain automatically
        """
        self.ensure_one()

        # Delete SVL layers in reverse order (newest first)
        svl_layers = self.stock_valuation_layer_ids.sorted(key=lambda l: -l.id)
        for layer in svl_layers:
            # Delete linked account move first if exists
            if layer.account_move_id:
                if layer.account_move_id.state == 'posted':
                    layer.account_move_id.button_draft()
                layer.account_move_id.unlink()

            # Remember parent layer to recompute remaining_qty later
            parent_layer = layer.stock_valuation_layer_id

            # Delete the SVL
            layer.sudo().unlink()

        # Recompute remaining_qty for affected parent layers
        self._recompute_parent_remaining_qty()

    def _recompute_parent_remaining_qty(self):
        """Recompute remaining_qty for parent SVL layers affected by this LC.

        After deleting LC SVL, the parent move SVL's remaining_qty
        needs to be recalculated based on its remaining child SVLs.
        """
        self.ensure_one()

        # Find all move SVLs that were referenced by this LC's valuation lines
        parent_layer_ids = set()
        for line in self.valuation_adjustment_lines.filtered(lambda l: l.move_id):
            for svl in line.move_id.stock_valuation_layer_ids:
                parent_layer_ids.add(svl.id)

        if not parent_layer_ids:
            return

        parent_layers = self.env['stock.valuation.layer'].browse(parent_layer_ids)
        for parent in parent_layers:
            # Sum remaining_qty of all child SVLs
            child_layers = self.env['stock.valuation.layer'].search([
                ('stock_valuation_layer_id', '=', parent.id),
            ])
            child_remaining = sum(child_layers.mapped('remaining_qty'))

            # parent remaining_qty = parent quantity - sum of child outgoing quantities
            # But LC SVL is now deleted, so remaining_qty should increase
            # Recalculate: remaining = quantity - (quantity consumed by children)
            outgoing_qty = parent.quantity - child_remaining
            new_remaining = parent.quantity - outgoing_qty

            # Only update if different
            if float_compare(
                new_remaining, parent.remaining_qty,
                precision_rounding=parent.product_id.uom_id.rounding or 0.01
            ) != 0:
                parent.sudo().remaining_qty = new_remaining

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

        Order matters:
        1. Revert average cost price (product.standard_price)
        2. Create reversal JE for the original account_move
        3. Delete SVL layers created by LC + recompute parent chain
        4. Remove vendor bill landed cost lines
        5. Keep valuation_adjustment_lines for re-validate reference
        """
        self.ensure_one()

        # 1. Revert average cost price
        self._revert_average_cost()

        # 2. Create reversal journal entry for original JE
        self._create_reversal_journal_entry()

        # 3. Delete SVL layers + recompute parent remaining_qty
        self._unlink_svl_layers()

        # 4. Remove vendor bill landed cost lines
        self._revert_vendor_bill_lines()

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

