from odoo import api, fields, models


class PosLiteConfig(models.Model):
    _name = 'pos.lite.config'
    _description = 'POS Lite Configuration'
    _order = 'id desc'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        required=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        help='Default cash/bank journal for POS Lite refund records',
        check_company=True,
    )
    branch_number = fields.Char(
        string='Branch Number',
        help='Thai tax branch number (e.g. 00000 for head office). Shown on receipts.',
    )
    phone = fields.Char(string='Phone', help='Phone number shown on receipt')
    vat_number = fields.Char(
        string='Tax ID Override',
        help='Override company VAT for receipt. Leave empty to use company VAT.',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Default Employee',
        domain="[('company_id', '=', company_id)]",
        check_company=True,
        help='Default employee for new sessions created from this config.',
    )
    out_picking_type_id = fields.Many2one(
        'stock.picking.type', string='Delivery Operation Type',
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
        check_company=True,
        help='Stock operation type used for POS delivery orders. '
             'Leave empty to use the default outgoing type from the warehouse.',
    )
    return_picking_type_id = fields.Many2one(
        'stock.picking.type', string='Return Operation Type',
        domain="[('code', '=', 'incoming'), ('company_id', '=', company_id)]",
        check_company=True,
        help='Stock operation type used for POS return orders. '
             'Leave empty to use the default incoming type from the warehouse.',
    )

    @api.model
    def get_default_config(self, company=None):
        company = company or self.env.company
        return self.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], order='id desc', limit=1)
