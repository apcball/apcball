from odoo import models


class AgedPayableXlsx(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_aged_payable_xlsx'
    _inherit = 'report.buz_gl_report_excel.report_aged_partner_xlsx'

    _report_model = 'report.buz_gl_report_excel.report_aged_payable'
    _sheet_title = 'Aged Payable'
    _show_type = False
