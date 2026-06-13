from odoo import models, api


class DispatchDocumentReport(models.AbstractModel):
    _name = 'report.buz_dispatch_management.report_dispatch_document'
    _description = 'Dispatch Document Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['buz.dispatch.document'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'buz.dispatch.document',
            'docs': docs,
        }
