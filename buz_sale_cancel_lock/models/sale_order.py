from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    has_posted_invoice = fields.Boolean(
        string='Has Posted Invoice',
        compute='_compute_has_posted_invoice',
    )

    @api.depends('invoice_ids.state')
    def _compute_has_posted_invoice(self):
        for order in self:
            order.has_posted_invoice = bool(order._get_posted_invoices())

    def _get_posted_invoices(self):
        self.ensure_one()
        return self.invoice_ids.filtered(lambda move: move.state == 'posted')

    def _action_cancel(self):
        posted = {order: order._get_posted_invoices() for order in self}
        locked = {order: invoices for order, invoices in posted.items() if invoices}
        if locked:
            lines = [
                _("%(order)s (invoice: %(invoices)s)",
                  order=order.name,
                  invoices=', '.join(invoices.mapped('name')))
                for order, invoices in locked.items()
            ]
            raise UserError(_(
                "Cannot cancel a Sales Order that already has a posted invoice. "
                "Cancel or reset the invoice first.\n%s", '\n'.join(lines)))
        return super()._action_cancel()
