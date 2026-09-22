from odoo import models


class BomExcelWizard(models.TransientModel):
    _name = "buz.mrp.bom.excel.wizard"
    _description = "BOM Excel Report Wizard"

    def action_export(self):
        self.ensure_one()
        return self.env.ref(
            "buz_mrp_bom_excel_report.action_bom_excel_report"
        ).report_action(self)
