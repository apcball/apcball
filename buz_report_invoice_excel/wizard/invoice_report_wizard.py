from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InvoiceReportWizard(models.TransientModel):
    _name = "buz.invoice.report.excel.wizard"
    _description = "Invoice Excel Report Wizard"

    date_from = fields.Date(
        string="Date From",
        required=True,
        default=fields.Date.context_today,
    )
    date_to = fields.Date(
        string="Date To",
        required=True,
        default=fields.Date.context_today,
    )
    invoice_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("posted", "Posted"),
            ("cancel", "Cancelled"),
        ],
        string="Invoice State",
    )
    report_filename = fields.Char(
        string="Report Filename",
        compute="_compute_report_filename",
    )

    @api.depends("date_from", "date_to")
    def _compute_report_filename(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                wizard.report_filename = "Invoice_Report_%s_%s" % (
                    wizard.date_from.strftime("%Y%m%d"),
                    wizard.date_to.strftime("%Y%m%d"),
                )
            else:
                wizard.report_filename = "Invoice_Report"

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError("Date From must be earlier than or equal to Date To.")

    def _get_invoices(self):
        self.ensure_one()
        domain = [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
            ("state", "!=", "cancel"),
        ]
        if self.invoice_state:
            domain.append(("state", "=", self.invoice_state))
        else:
            domain.append(("state", "=", "posted"))

        return self.env["account.move"].search(
            domain, order="invoice_date, name"
        )

    def action_export_excel(self):
        self.ensure_one()
        invoices = self._get_invoices()
        data = {
            "date_from": fields.Date.to_string(self.date_from),
            "date_to": fields.Date.to_string(self.date_to),
            "invoice_state": self.invoice_state,
            "invoice_ids": invoices.ids,
        }
        return self.env.ref(
            "buz_report_invoice_excel.action_report_invoice_excel_wizard"
        ).with_context(
            active_model=self._name,
            active_id=self.id,
            active_ids=self.ids,
        ).report_action(self, data=data)
