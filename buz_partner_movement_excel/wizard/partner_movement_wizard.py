from odoo import fields, models


class PartnerMovementWizard(models.TransientModel):
    _name = 'partner.movement.excel.wizard'
    _description = 'Partner Movement Excel Report'

    date_as_of = fields.Date(required=True, default=fields.Date.context_today)
    direction = fields.Selection([
        ('receivable', 'Receivable'),
        ('payable', 'Payable'),
        ('both', 'Receivable and Payable'),
    ], required=True, default='both')
    partner_ids = fields.Many2many('res.partner')
    accrual_account_ids = fields.Many2many(
        'account.account', domain="[('company_id', '=', company_id), ('account_type', '=', 'liability_current')]"
    )
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)

    def action_export_xlsx(self):
        self.ensure_one()
        data = {'form': self.read([
            'date_as_of', 'direction', 'partner_ids', 'accrual_account_ids', 'company_id',
        ])[0]}
        return self.env.ref(
            'buz_partner_movement_excel.action_partner_movement_xlsx'
        ).report_action(self, data=data)
