import json

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class LandedCostReportWizard(models.TransientModel):
    _name = 'buz.landed.cost.report.wizard'
    _description = 'Landed Cost Report Export Wizard'

    domain_json = fields.Text(string='Domain', readonly=True, default='[]')
    record_count = fields.Integer(string='Rows to Export', compute='_compute_record_count')
    include_summary = fields.Boolean(string='Summary', default=True)
    include_breakdown = fields.Boolean(string='Cost Breakdown', default=True)
    include_audit = fields.Boolean(string='Audit', default=True)

    def _get_domain(self):
        self.ensure_one()
        try:
            domain = json.loads(self.domain_json or '[]')
        except ValueError:
            raise UserError(_('Invalid filter received from the report view.'))
        if not isinstance(domain, list):
            raise UserError(_('Invalid filter received from the report view.'))
        # JSON turns tuples into lists; the ORM accepts both for leaves
        return [tuple(leaf) if isinstance(leaf, list) else leaf for leaf in domain]

    @api.depends('domain_json')
    def _compute_record_count(self):
        report = self.env['buz.landed.cost.report']
        for rec in self:
            try:
                rec.record_count = report.search_count(rec._get_domain())
            except UserError:
                rec.record_count = 0

    def action_export_excel(self):
        self.ensure_one()
        sheets = [name for name, flag in (
            ('summary', self.include_summary),
            ('breakdown', self.include_breakdown),
            ('audit', self.include_audit),
        ) if flag]
        if not sheets:
            raise UserError(_('Select at least one sheet to export.'))
        domain = self._get_domain()
        if not self.env['buz.landed.cost.report'].search_count(domain):
            raise UserError(_('Nothing to export for the current filters.'))
        data = {'domain': domain, 'sheets': sheets}
        return self.env.ref('buz_landed_cost_report.action_report_landed_cost_xlsx').report_action(self, data=data)
