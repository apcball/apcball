# -*- coding: utf-8 -*-

from odoo import _, fields, models
from odoo.exceptions import UserError


class ServiceClaimXlsxWizard(models.TransientModel):
    _name = 'buz.service.claim.xlsx.wizard'
    _description = 'Claims Excel Report Wizard'

    date_from = fields.Date(string='Date From', help='Matches either Request Date or Service Date.')
    date_to = fields.Date(string='Date To', help='Matches either Request Date or Service Date.')
    partner_id = fields.Many2one('res.partner', string='Customer')
    technician_id = fields.Many2one('res.users', string='Technician')

    def _build_date_leg(self, field_name):
        leg = []
        if self.date_from:
            leg.append((field_name, '>=', self.date_from))
        if self.date_to:
            leg.append((field_name, '<=', self.date_to))
        return ['&'] + leg if len(leg) == 2 else leg

    def _get_domain(self):
        domain = [('service_case_type', '=', 'replacement')]
        if self.date_from or self.date_to:
            # Match claims whose Request Date OR Service Date falls in range —
            # many claims only have one of the two dates filled in.
            domain += ['|'] + self._build_date_leg('request_date') + self._build_date_leg('service_date')
        if self.partner_id:
            domain.append(('partner_id', '=', self.partner_id.id))
        if self.technician_id:
            domain.append(('technician_id', '=', self.technician_id.id))
        return domain

    def action_print_xlsx(self):
        self.ensure_one()
        claims = self.env['service.receipt'].search(self._get_domain())
        if not claims:
            raise UserError(_('No claims found for the selected filters.'))
        return self.env.ref('buz_service_receipt.action_report_service_claim_xlsx').report_action(claims)
