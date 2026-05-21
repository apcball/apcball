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

    def _create_reversal_journal_entry(self):
        """Create a reversal journal entry that reverses the original JE.

        Instead of deleting the original JE, we create a reversal entry
        so the accounting remains correct and auditable.
        """
        self.ensure_one()

        if not self.account_move_id:
            return self.env['account.move']

        original_move = self.account_move_id

        # Build reversal move lines (flip debit/credit)
        reversal_lines = []
        for line in original_move.line_ids:
            reversal_lines.append((0, 0, {
                'name': _('Reversal of: %s') % line.name,
                'account_id': line.account_id.id,
                'partner_id': line.partner_id.id,
                'debit': line.credit,  # flip
                'credit': line.debit,  # flip
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

    def _revert_svl_layers(self):
        """Revert stock valuation layers by creating negative SVL entries.

        For real_time valuation products, also creates proper JE.
        """
        self.ensure_one()

        for layer in self.stock_valuation_layer_ids.filtered(lambda l: l.value):
            product = layer.product_id
            svl_vals = {
                'product_id': layer.product_id.id,
                'company_id': layer.company_id.id,
                'quantity': -(layer.quantity or 0),
                'remaining_qty': -(layer.remaining_qty or 0),
                'unit_cost': layer.unit_cost,
                'value': -layer.value,
                'description': _('Reversal of Landed Cost: %s') % self.name,
                'stock_valuation_layer_id': layer.id,
                'stock_landed_cost_id': self.id,
            }

            if product.valuation != 'real_time':
                # Manual valuation — just create SVL, no JE needed
                self.env['stock.valuation.layer'].create(svl_vals)
            else:
                # Real time valuation — create SVL + JE
                svl = self.env['stock.valuation.layer'].create(svl_vals)
                self._create_svl_reversal_move(svl, layer)

    def _create_svl_reversal_move(self, svl, original_layer):
        """Create account move for SVL reversal (real_time valuation)."""
        product = svl.product_id
        if product.valuation != 'real_time':
            return

        valuation_account = product.categ_id.property_stock_valuation_account_id
        expense_account = product.categ_id.property_stock_account_output_categ_id \
            or product.categ_id.property_account_expense_categ_id

        if not valuation_account or not expense_account:
            return

        journal = product.categ_id.property_stock_journal \
            or self.env['account.move'].with_company(self.company_id)._get_default_journal()

        amount = abs(svl.value)
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': _('Reversal of Landed Cost SVL: %s') % self.name,
            'move_type': 'entry',
            'line_ids': [
                (0, 0, {
                    'name': _('Reversal Landed Cost: %s') % product.display_name,
                    'account_id': valuation_account.id,
                    'product_id': product.id,
                    'quantity': abs(svl.quantity) if svl.quantity else 1,
                    'product_uom_id': product.uom_id.id,
                    'debit': 0,
                    'credit': amount,
                }),
                (0, 0, {
                    'name': _('Reversal Landed Cost: %s') % product.display_name,
                    'account_id': expense_account.id,
                    'product_id': product.id,
                    'quantity': abs(svl.quantity) if svl.quantity else 1,
                    'product_uom_id': product.uom_id.id,
                    'debit': amount,
                    'credit': 0,
                }),
            ],
        })
        move.action_post()
        svl.account_move_id = move

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
        3. Create reversal SVL + JE for each valuation layer
        4. Remove vendor bill landed cost lines
        5. DO NOT delete valuation_adjustment_lines — keep for audit & re-validate
        """
        self.ensure_one()

        # 1. Revert average cost price
        self._revert_average_cost()

        # 2. Create reversal journal entry for original JE
        self._create_reversal_journal_entry()

        # 3. Revert SVL layers with proper accounting
        self._revert_svl_layers()

        # 4. Remove vendor bill landed cost lines
        self._revert_vendor_bill_lines()

        # 5. Keep valuation_adjustment_lines for reference
        # (needed if user wants to re-validate the landed cost)

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
