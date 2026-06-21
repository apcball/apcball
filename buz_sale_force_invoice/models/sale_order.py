from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    force_invoice = fields.Boolean(
        string="Force Invoiced",
        copy=False,
        readonly=True,
    )
    force_invoice_reason = fields.Selection([
        ('bill_exchange', 'Bill Exchange'),
        ('advance_billing', 'Advance Billing'),
        ('customer_request', 'Customer Request'),
        ('other', 'Other'),
    ])
    force_invoice_note = fields.Text()
    force_invoice_user_id = fields.Many2one('res.users')
    force_invoice_date = fields.Datetime()

    def action_open_force_invoice_wizard(self):
        self.ensure_one()
        return {
            'name': _('Force Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.force.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    def action_force_create_invoice(self, reason, note=False):
        self.ensure_one()
        if self.state != 'sale':
            raise UserError(_(
                "Cannot force invoice a Sales Order in '%s' state."
            ) % self.state)
        existing = self.invoice_ids.filtered(lambda i: i.state != 'cancel')
        if existing:
            raise UserError(_(
                "An invoice already exists for this Sales Order."
            ))
        invoice_vals = self.with_context(
            default_move_type='out_invoice',
        )._prepare_invoice()
        line_vals = []
        for line in self.order_line.filtered(lambda l: not l.display_type):
            if line.product_uom_qty <= line.qty_invoiced:
                continue
            qty = line.product_uom_qty - line.qty_invoiced
            vals = line._prepare_invoice_line()
            vals['quantity'] = qty
            line_vals.append(fields.Command.create(vals))
        if not line_vals:
            raise UserError(_(
                "No invoiceable lines found. All lines may already be fully invoiced."
            ))
        invoice_vals['invoice_line_ids'] = line_vals
        move = self.env['account.move'].create(invoice_vals)
        reason_label = dict(
            self._fields['force_invoice_reason']._description_selection(self.env)
        ).get(reason, reason)
        self.write({
            'force_invoice': True,
            'force_invoice_reason': reason,
            'force_invoice_note': note or False,
            'force_invoice_user_id': self.env.user.id,
            'force_invoice_date': fields.Datetime.now(),
        })
        msg = _(
            "Force Invoice created by %(user)s.\n"
            "Reason: %(reason)s.\n"
            "Invoice: %(invoice)s."
        ) % {
            'user': self.env.user.name,
            'reason': reason_label,
            'invoice': move.name,
        }
        self.message_post(body=msg)
        return {
            'name': _('Force Invoice'),
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': move.id,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }
