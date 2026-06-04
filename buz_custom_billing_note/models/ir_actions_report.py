from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _get_rendering_context(self, report, docids, data=None):
        """Override to use sudo() for billing note reports so cross-company printing works."""
        result = super()._get_rendering_context(report, docids, data=data)

        if report.model == 'billing.note' and docids:
            # sudo() bypasses ir.rules on company_id
            docs = self.env['billing.note'].sudo().browse(docids)
            result['docs'] = docs
            if 'doc' in result:
                result['doc'] = docs[:1]
            if docs:
                result['company'] = docs[0].company_id

        return result

    @api.model
    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        _logger.debug("Preparing PDF streams for report %s with res_ids: %s", report_ref, res_ids)
        try:
            collected_streams = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids)
            return collected_streams
        except Exception as e:
            _logger.error("Error preparing PDF streams for report %s with res_ids: %s: %s", report_ref, res_ids, e)
            raise
