# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        """Override to update amount_used in budget when vendor bill is posted."""
        res = super().action_post()
        self._trigger_budget_recompute()
        return res

    def button_cancel(self):
        """Override to update amount_used in budget when vendor bill is canceled."""
        res = super().button_cancel()
        self._trigger_budget_recompute()
        return res

    def button_draft(self):
        """Override to update budget when vendor bill is reset to draft."""
        res = super().button_draft()
        self._trigger_budget_recompute()
        return res

    def write(self, vals):
        """Trigger budget recompute if due date changes on a posted bill."""
        old_dates = {rec.id: rec.invoice_date_due for rec in self if rec.move_type in ('in_invoice', 'in_refund') and rec.state == 'posted'}
        res = super().write(vals)
        if 'invoice_date_due' in vals or 'amount_total' in vals or 'state' in vals:
            self._trigger_budget_recompute(old_dates=old_dates)
        return res

    def _trigger_budget_recompute(self, old_dates=None):
        """Trigger budget recompute for affected budget lines."""
        BudgetLine = self.env['weekly.budget.line'].sudo()
        vendor_bills = self.filtered(lambda m: m.move_type in ('in_invoice', 'in_refund'))
        if not vendor_bills:
            return

        dates_to_update = set()
        for bill in vendor_bills:
            if bill.invoice_date_due:
                dates_to_update.add(bill.invoice_date_due)
            if old_dates and old_dates.get(bill.id):
                dates_to_update.add(old_dates[bill.id])
            # For POs linked to these bills, we also might need to recompute amount_reserved
            # because remaining_to_bill changes
            for line in bill.invoice_line_ids:
                if line.purchase_line_id and line.purchase_line_id.order_id:
                    po = line.purchase_line_id.order_id
                    if po.payment_date:
                        dates_to_update.add(po.payment_date)
                    elif po.date_order:
                        dates_to_update.add(fields.Date.to_date(po.date_order))

        for target_date in dates_to_update:
            # We don't have company specific filter easily from here without checking each company
            # so we just recompute all active lines covering this date.
            budget_lines = BudgetLine.search([
                ('plan_state', '=', 'confirmed'),
                ('date_from', '<=', target_date),
                ('date_to', '>=', target_date),
            ])
            if budget_lines:
                budget_lines._compute_amount_used()
                budget_lines._compute_amount_reserved()
