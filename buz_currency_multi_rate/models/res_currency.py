# -*- coding: utf-8 -*-
from odoo import models, api, fields

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    # Adding rate_type to depends_context to ensure cache is correct when context changes
    rate = fields.Float(
        compute='_compute_current_rate', 
        string='Current Rate', 
        digits=(12, 12),
        help='The rate of the currency to the currency of the company'
    )

    @api.depends_context('company', 'date', 'rate_type', 'move_type', 'default_move_type')
    def _compute_current_rate(self):
        super(ResCurrency, self)._compute_current_rate()

    def _get_rates(self, company, date):
        """
        Overriding _get_rates to support Buy and Sell rates.
        We check the context for 'rate_type'.
        If not found, we try to infer it from 'move_type' (for accounting).
        """
        if not self:
            return {}
            
        rate_type = self._context.get('rate_type')
        
        # Auto-infer rate_type if not explicitly provided
        if not rate_type:
            move_type = self._context.get('move_type') or self._context.get('default_move_type')
            if move_type in ['in_invoice', 'in_refund', 'in_receipt']:
                rate_type = 'buy'
            elif move_type in ['out_invoice', 'out_refund', 'out_receipt']:
                rate_type = 'sell'
        
        if rate_type not in ['buy', 'sell']:
            return super(ResCurrency, self)._get_rates(company, date)

        # Map rate_type to field name
        rate_field = 'buy_rate' if rate_type == 'buy' else 'sell_rate'
        
        # Ensure fields are flushed to the DB for the query
        self.env['res.currency.rate'].flush_model([rate_field, 'rate', 'currency_id', 'company_id', 'name'])
        
        # The query logic:
        # 1. Try to find the latest record for this currency with name <= date.
        # 2. If the specific rate_field is defined (> 0), use it.
        # 3. Otherwise, fallback to the standard 'rate' field.
        # 4. If no record at all, fallback to 1.0.
        
        query = f"""SELECT c.id,
                          COALESCE((SELECT 
                                        CASE 
                                            WHEN r.{rate_field} > 0 THEN r.{rate_field} 
                                            ELSE r.rate 
                                        END
                                  FROM res_currency_rate r
                                  WHERE r.currency_id = c.id AND r.name <= %s
                                    AND (r.company_id IS NULL OR r.company_id = %s)
                               ORDER BY r.company_id DESC, r.name DESC
                                  LIMIT 1), 1.0) AS rate
                   FROM res_currency c
                   WHERE c.id IN %s"""
        
        self._cr.execute(query, (date, company.id, tuple(self.ids)))
        currency_rates = dict(self._cr.fetchall())
        return currency_rates
