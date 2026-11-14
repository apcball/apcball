from odoo import fields, models


class PartnerMovementWizard(models.TransientModel):
    _name = 'partner.movement.excel.wizard'
    _description = 'Partner Movement Excel Report'

    date_from = fields.Date(string='วันที่เริ่มต้น')
    date_to = fields.Date(string='วันที่สิ้นสุด', required=True, default=fields.Date.context_today)
    target_move = fields.Selection([
        ('posted', 'รายการลงบัญชีแล้ว'),
        ('all', 'รวมรายการร่างและลงบัญชีแล้ว'),
    ], string='สถานะรายการ', required=True, default='posted')
    direction = fields.Selection([
        ('receivable', 'ลูกหนี้'),
        ('payable', 'เจ้าหนี้'),
        ('both', 'ลูกหนี้และเจ้าหนี้'),
    ], string='ทิศทาง', required=True, default='both')
    partner_ids = fields.Many2many('res.partner', string='คู่ค้า')
    account_ids = fields.Many2many(
        'account.account', string='บัญชี',
        domain="[('company_id', '=', company_id), ('account_type', 'in', direction == 'receivable' and ['asset_receivable'] or direction == 'payable' and ['liability_payable', 'liability_current'] or ['asset_receivable', 'liability_payable', 'liability_current'])]",
    )
    with_currency = fields.Boolean(string='แสดงยอดสกุลเงินต่างประเทศ')
    reconciled = fields.Boolean(string='รวมเอกสารที่ชำระครบแล้ว', default=True)
    company_id = fields.Many2one('res.company', string='บริษัท', required=True, default=lambda self: self.env.company)

    @staticmethod
    def _get_export_filename(date_from, date_to):
        return f"Partner Movement_{date_from or 'all'}_to_{date_to}"

    def get_export_filename(self):
        self.ensure_one()
        return self._get_export_filename(self.date_from, self.date_to)

    def action_export_xlsx(self):
        self.ensure_one()
        data = {'form': self.read([
            'date_from', 'date_to', 'target_move', 'direction', 'partner_ids',
            'account_ids', 'with_currency', 'reconciled', 'company_id',
        ])[0]}
        return self.env.ref(
            'buz_partner_movement_excel.action_partner_movement_xlsx'
        ).report_action(self, data=data)
