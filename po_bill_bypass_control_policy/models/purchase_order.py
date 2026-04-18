import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    allow_bill_bypass = fields.Boolean(
        string="Allow Bill Before Receive",
        copy=False,
        tracking=True
    )
    bill_bypass_reason = fields.Text(
        string="Bypass Reason",
        copy=False,
        tracking=True
    )
    bill_bypass_user_id = fields.Many2one(
        'res.users',
        string="Bypass Approved By",
        copy=False,
        tracking=True
    )
    bill_bypass_date = fields.Datetime(
        string="Bypass Date",
        copy=False,
        tracking=True
    )

    @api.onchange('partner_id')
    def _onchange_partner_id_bypass(self):
        for order in self:
            if order.partner_id:
                order.allow_bill_bypass = order.partner_id.default_allow_bill_bypass

    @api.depends('allow_bill_bypass')
    def _get_invoiced(self):
        super()._get_invoiced()
        for order in self:
            if order.allow_bill_bypass and order.state in ('purchase', 'done'):
                if any(line.qty_to_invoice > 0 for line in order.order_line.filtered(lambda l: not l.display_type)):
                    order.invoice_status = 'to invoice'

    def write(self, vals):
        if 'allow_bill_bypass' in vals and vals.get('allow_bill_bypass'):
            vals['bill_bypass_user_id'] = self.env.user.id
            vals['bill_bypass_date'] = fields.Datetime.now()
            
        res = super().write(vals)

        if 'allow_bill_bypass' in vals and vals.get('allow_bill_bypass'):
            for order in self:
                msg = _("Bill bypass enabled by %s on %s<br/>Reason: %s") % (
                    order.bill_bypass_user_id.name or '',
                    order.bill_bypass_date.strftime('%Y-%m-%d %H:%M:%S') if order.bill_bypass_date else '',
                    order.bill_bypass_reason or ''
                )
                order.message_post(body=msg)
                
        return res

    def action_create_invoice(self):
        for order in self:
            if order.allow_bill_bypass and not self.env.context.get('bypass_bill_confirm_wizard'):
                total_received = sum(order.order_line.mapped('qty_received'))
                if total_received <= 0.0:
                    return {
                        'name': _('Create Vendor Bill Before Receipt?'),
                        'type': 'ir.actions.act_window',
                        'res_model': 'bill.bypass.confirm.wizard',
                        'view_mode': 'form',
                        'target': 'new',
                        'context': {
                            'default_purchase_order_id': order.id,
                        }
                    }

        if self.env.context.get('bypass_bill_confirm_wizard'):
            for order in self:
                # Forcefully inject the bypass quantities directly to DB to bypass compute restrictions
                self.env.cr.execute(
                    "UPDATE purchase_order SET invoice_status = 'to invoice' WHERE id = %s",
                    (order.id,)
                )
                for line in order.order_line:
                    qty = max(0.0, line.product_qty - line.qty_invoiced)
                    self.env.cr.execute(
                        "UPDATE purchase_order_line SET qty_to_invoice = %s WHERE id = %s",
                        (qty, line.id)
                    )
            # Ensure the ORM reads the injected values
            self.invalidate_recordset(['invoice_status'])
            self.order_line.invalidate_recordset(['qty_to_invoice'])

        res = super().action_create_invoice()

        if self.env.context.get('bypass_bill_confirm_wizard'):
            for order in self:
                order.message_post(body=_("Vendor Bill created using bypass control policy."))

        return res
