from odoo import fields, models


class WarrantyCard(models.Model):
    _inherit = 'warranty.card'

    source = fields.Selection(
        [('manual', 'Manual / Office'),
         ('portal', 'Customer Portal')],
        string='Source', default='manual', tracking=True)
    dealer_name = fields.Char(string='Dealer / Shop')
    invoice_number = fields.Char(string='Invoice No.')
    serial_number_input = fields.Char(
        string='Serial (customer-entered)',
        help='Typed by customer on the portal; used when no matching stock.lot is found')
    proof_attachment_ids = fields.Many2many(
        'ir.attachment', 'warranty_card_proof_rel', 'card_id', 'attachment_id',
        string='Proof of Purchase')
    registration_date = fields.Datetime(
        string='Submitted On', readonly=True, copy=False)