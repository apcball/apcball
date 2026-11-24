from odoo import models


class AgedReceivableXlsx(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_aged_receivable_xlsx'
    _inherit = 'report.buz_gl_report_excel.report_aged_partner_xlsx'

    _report_model = 'report.buz_gl_report_excel.report_aged_receivable'
    _sheet_title = 'Aged Receivable'
    _show_type = False
