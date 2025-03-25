from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        # Log the report reference and document IDs
        _logger.info(f"Rendering PDF for report {report_ref} with res_ids: {res_ids}")

        try:
            # Call the super method to render the PDF
            pdf = super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
            return pdf
        except Exception as e:
            # Log the exception and the document IDs
            _logger.error(f"Error rendering PDF for report {report_ref} with res_ids: {res_ids}")
            _logger.error(f"Exception: {e}")
            raise

    @api.model
    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        # Log the report reference and document IDs
        _logger.info(f"Preparing PDF streams for report {report_ref} with res_ids: {res_ids}")

        try:
            # Call the super method to prepare the PDF streams
            collected_streams = super()._render_qweb_pdf_prepare_streams(report_ref, data, res_ids=res_ids)
            return collected_streams
        except Exception as e:
            # Log the exception and the document IDs
            _logger.error(f"Error preparing PDF streams for report {report_ref} with res_ids: {res_ids}")
            _logger.error(f"Exception: {e}")
            raise