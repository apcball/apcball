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
        # Map invoice -> POS employee name / signature for report display
        pos_employee_map = {}
        pos_signature_map = {}
        # Map invoice -> POS order totals. POS computes tax per-line then sums,
        # which can differ from the invoice's aggregate tax by a few cents
        # (e.g. 4,620.00 vs 4,619.98). The receipt must match the POS document.
        pos_totals_map = {}
        for order in orders:
            if order.invoice_id and order.employee_id:
                pos_employee_map[order.invoice_id.id] = order.employee_id.name
                pos_signature_map[order.invoice_id.id] = order.authorized_signature
            if order.invoice_id:
                pos_totals_map[order.invoice_id.id] = {
                    'amount_untaxed': order.amount_untaxed,
                    'amount_tax': order.amount_tax,
                    'amount_total': order.amount_total,
                }
        return {
            'doc_ids': invoices.ids,
            'doc_model': 'account.move',
            'docs': invoices,
            'data': data or {},
            'pos_employee_map': pos_employee_map,
            'pos_signature_map': pos_signature_map,
            'pos_totals_map': pos_totals_map,
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
