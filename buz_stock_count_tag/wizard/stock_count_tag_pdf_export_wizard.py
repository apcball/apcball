from odoo import _, fields, models
from odoo.exceptions import UserError


class StockCountTagPdfExportWizard(models.TransientModel):
    _name = "buz.stock.count.tag.pdf.export.wizard"
    _description = "Export Stock Count Tag PDF"

    tag_id = fields.Many2one("buz.stock.count.tag", required=True)
    doc_no_from = fields.Char(string="Tag No. From")
    doc_no_to = fields.Char(string="Tag No. To")

    def action_export(self):
        self.ensure_one()
        if bool(self.doc_no_from) != bool(self.doc_no_to):
            raise UserError(_("Fill in both Tag No. From and Tag No. To, or leave both blank."))
        return self.tag_id.action_generate_pdf(self.doc_no_from or None, self.doc_no_to or None)
