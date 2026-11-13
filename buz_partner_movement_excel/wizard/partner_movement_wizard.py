from odoo import fields, models


class PartnerMovementWizard(models.TransientModel):
    _name = 'partner.movement.excel.wizard'
    _description = 'Partner Movement Excel Report'

    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(string='End Date', required=True, default=fields.Date.context_today)
    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], required=True, default='posted')
    direction = fields.Selection([
        ('receivable', 'Receivable'),
        ('payable', 'Payable'),
        ('both', 'Receivable and Payable'),
    ], required=True, default='both')
    partner_ids = fields.Many2many('res.partner')
    account_ids = fields.Many2many(
        'account.account', string='Accounts',
        domain="[('company_id', '=', company_id), ('account_type', 'in', direction == 'receivable' and ['asset_receivable'] or direction == 'payable' and ['liability_payable', 'liability_current'] or ['asset_receivable', 'liability_payable', 'liability_current'])]",
    )
    with_currency = fields.Boolean(string='With Currency?')
    reconciled = fields.Boolean(string='Reconciled Entries', default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    def action_export_xlsx(self):
        self.ensure_one()
        data = {'form': self.read([
            'date_from', 'date_to', 'target_move', 'direction', 'partner_ids',
            'account_ids', 'with_currency', 'reconciled', 'company_id',
        ])[0]}
        return self.env.ref(
            'buz_partner_movement_excel.action_partner_movement_xlsx'
        ).report_action(self, data=data)
