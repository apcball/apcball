from odoo import fields, models


class WarrantyCard(models.Model):
    _inherit = 'warranty.card'

    source = fields.Selection(
        [
            ('manual', 'Manual / Office'),
            ('portal', 'Customer Portal'),
        ],
        string='Source',
        default='manual',
        tracking=True,
    )
    serial_number_input = fields.Char(
        string='Serial (customer-entered)',
        help='Serial number supplied by the external website when no stock lot is linked.',
    )
    product_model_input = fields.Char(
        string='Product Model / Code',
        help='Product model or code supplied by the external website.',
    )
    registration_date = fields.Datetime(
        string='Submitted On',
        readonly=True,
        copy=False,
    )
    external_request_id = fields.Char(
        string='External Request ID',
        index=True,
        copy=False,
    )

    _sql_constraints = [
        (
            'warranty_card_external_request_id_uniq',
            'unique(external_request_id)',
            'A warranty card can only be imported once for an external request.',
        ),
    ]
