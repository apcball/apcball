from odoo import api, models


class AgedReceivableReport(models.AbstractModel):
    """Aged Receivable: aged partner report restricted to customer accounts."""
    _name = 'report.buz_gl_report_excel.report_aged_receivable'
    _inherit = 'report.buz_gl_report_excel.report_aged_partner'
    _description = 'Aged Receivable Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = dict(data or {})
        data['form'] = dict(data.get('form') or {}, result_selection='customer')
        return super()._get_report_values(docids, data=data)
