from odoo import api, models


class AgedPayableReport(models.AbstractModel):
    """Aged Payable: aged partner report restricted to supplier accounts."""
    _name = 'report.buz_gl_report_excel.report_aged_payable'
    _inherit = 'report.buz_gl_report_excel.report_aged_partner'
    _description = 'Aged Payable Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = dict(data or {})
        data['form'] = dict(data.get('form') or {}, result_selection='supplier')
        return super()._get_report_values(docids, data=data)
