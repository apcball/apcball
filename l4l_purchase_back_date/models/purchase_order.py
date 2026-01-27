# -*- coding: utf-8 -*-
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2023 Leap4Logic Solutions PVT LTD
#    Email : sales@leap4logic.com
#################################################

from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def button_confirm(self):
        if self.company_id.l4l_allow_back_date:
            date_order = self.date_order
            # Set context for both accounting entries and currency rate
            ctx = dict(self.env.context)
            ctx.update({
                'force_period_date': date_order,
                'date': date_order,
                'force_company': self.company_id.id,
            })
            # Force currency rate date on purchase order
            if self.currency_id and self.currency_id != self.company_id.currency_id:
                ctx.update({'force_rate_date': date_order})
            
            # Override the button_confirm with forced date
            self_with_context = self.with_context(ctx)
            
            # Temporarily store the date_order
            original_date = self.date_order
            
            # Call super with context
            rec = super(PurchaseOrder, self_with_context).button_confirm()
            
            # Force set date_approve to our desired date using SQL
            if self.state == 'purchase':
                self.env.cr.execute("""
                    UPDATE purchase_order 
                    SET date_approve = %s 
                    WHERE id = %s
                """, (original_date, self.id))
                self.env.cr.commit()
                
                # Clear cache
                self.invalidate_recordset(['date_approve'])
            
            return rec
        else:
            return super().button_confirm()

    @api.onchange('date_order')
    def onchange_date_planned(self):
        if self.company_id.l4l_allow_back_date:
            self.order_line.date_planned = self.date_order

    def write(self, vals):
        # If backdating is enabled and we're setting date_approve, use date_order instead
        if self.company_id.l4l_allow_back_date and 'date_approve' in vals and self.date_order:
            vals['date_approve'] = self.date_order
        return super().write(vals)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: