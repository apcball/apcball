from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleForceInvoiceWizard(models.TransientModel):
    _name = 'sale.force.invoice.wizard'
    _description = 'Force Invoice Wizard'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        readonly=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        required=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    reason = fields.Selection([
        ('bill_exchange', 'Bill Exchange'),
        ('advance_billing', 'Advance Billing'),
        ('customer_request', 'Customer Request'),
        ('other', 'Other'),
    ], string='Reason', required=True)
    note = fields.Text(string='Note')

    def action_confirm(self):
        self.ensure_one()
        return self.sale_order_id.action_force_create_invoice(
            self.reason, self.note,
        )
