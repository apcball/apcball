from odoo import models


class ChequePrintPreviewReport(models.AbstractModel):
    _name = 'report.dynamic_cheque_print.cheque_print_preview_template'
    _description = 'Cheque Print Preview Report'

    def _get_report_values(self, docids, data=None):
        docs = self.env['cheque.print'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'cheque.print',
            'docs': docs,
            'data': data,
            'amount_in_words_1': data.get('amount_in_words_1', ''),
            'amount_in_words_2': data.get('amount_in_words_2', '')
        }
