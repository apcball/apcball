from odoo import api, models


class ReportPosLiteReceipt(models.AbstractModel):
    _name = 'report.pos_lite.report_receipt_document'
    _description = 'POS Lite Receipt Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['pos.lite.order'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pos.lite.order',
            'docs': docs,
            'data': data or {},
        }


class ReportPosLiteInvoice(models.AbstractModel):
    _name = 'report.pos_lite.report_pos_lite_invoice'
    _description = 'POS Lite Invoice Report (via account.move)'

    @api.model
    def _get_report_values(self, docids, data=None):
        orders = self.env['pos.lite.order'].browse(docids)
        invoices = orders.mapped('invoice_id')
        # Map invoice -> POS employee name for report display
        pos_employee_map = {}
        for order in orders:
            if order.invoice_id and order.employee_id:
                pos_employee_map[order.invoice_id.id] = order.employee_id.name
        return {
            'doc_ids': invoices.ids,
            'doc_model': 'account.move',
            'docs': invoices,
            'data': data or {},
            'pos_employee_map': pos_employee_map,
        }


class ReportPosLiteSession(models.AbstractModel):
    _name = 'report.pos_lite.report_session_document'
    _description = 'POS Lite Session Summary Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['pos.lite.session'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'pos.lite.session',
            'docs': docs,
            'data': data or {},
        }
