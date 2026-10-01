from odoo import _, models
from odoo.exceptions import UserError

# Reports that may only be printed for pickings in state done.
DONE_ONLY_REPORTS = {
    'buz_inventory_delivery_report.delivery_report_tem_document',
    'buz_inventory_delivery_report.borrow_equip_form_document',
}


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        report = self._get_report(report_ref)
        if report.report_name in DONE_ONLY_REPORTS and res_ids:
            pickings = self.env['stock.picking'].browse(res_ids).filtered(
                lambda p: p.state != 'done')
            if pickings:
                raise UserError(_(
                    "ไม่สามารถพิมพ์ได้ กรุณากด Validate เอกสารให้เป็นสถานะ Done ก่อน\n"
                    "เอกสารที่ยังไม่ Done: %s", ', '.join(pickings.mapped('name'))))
        return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)
