# -*- coding: utf-8 -*-
from odoo import models, api, fields

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.depends(
        'currency_id',
        'company_id',
        'move_id.date',
        'move_id.move_type',
        'move_id.payment_id',
        'move_id.payment_id.payment_type',
    )
    def _compute_currency_rate(self):
        """
        Override _compute_currency_rate to inject the correct rate_type context:
          - Vendor Bills / Purchase docs  → 'buy'
          - Customer Invoices / Sale docs → 'sell'
          - Outbound Payments (vendor)    → 'buy'   ← KEY FIX: must match bill rate type
          - Inbound Payments (customer)   → 'sell'  ← KEY FIX: must match invoice rate type
          - Everything else               → standard Odoo behaviour

        Without this, Exchange Difference is calculated from mismatched rates
        (buy on bill date vs standard on payment date) → wrong account / wrong amount.
        """
        for line in self:
            # Same currency → always 1.0, no query needed
            if not line.currency_id or line.currency_id == line.company_currency_id:
                line.currency_rate = 1.0
                continue

            rate_type = 'standard'

            if line.move_id:
                if line.move_id.is_sale_document():
                    # Customer Invoice / Credit Note / Receipt
                    rate_type = 'sell'

                elif line.move_id.is_purchase_document():
                    # Vendor Bill / Refund / Purchase Receipt
                    rate_type = 'buy'

                elif line.move_id.payment_id:
                    # Payment journal entry (move_type = 'entry'):
                    # Derive rate_type from the payment direction so it stays
                    # consistent with the invoice it will reconcile against.
                    payment_type = line.move_id.payment_id.payment_type
                    if payment_type == 'outbound':
                        # Paying a vendor → same as vendor bill → buy rate
                        rate_type = 'buy'
                    elif payment_type == 'inbound':
                        # Receiving from a customer → same as customer invoice → sell rate
                        rate_type = 'sell'

            context = {
                'rate_type': rate_type,
                'move_type': line.move_id.move_type if line.move_id else False,
            }
            from_currency = line.company_currency_id.with_context(**context)
            to_currency = line.currency_id.with_context(**context)

            try:
                line.currency_rate = self.env['res.currency']._get_conversion_rate(
                    from_currency=from_currency,
                    to_currency=to_currency,
                    company=line.company_id,
                    date=line._get_rate_date(),
                )
            except Exception:
                # Graceful fallback: use standard rate if custom lookup fails
                line.currency_rate = self.env['res.currency']._get_conversion_rate(
                    from_currency=line.company_currency_id,
                    to_currency=line.currency_id,
                    company=line.company_id,
                    date=line._get_rate_date(),
                )
