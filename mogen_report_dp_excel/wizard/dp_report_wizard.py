from datetime import datetime, time

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DPReportWizard(models.TransientModel):
    _name = "mogen.report.dp.excel.wizard"
    _description = "DP Excel Report Wizard"

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
    report_filename = fields.Char(
        string="Report Filename",
        compute="_compute_report_filename",
    )
    do_status = fields.Selection(
        [
            ("assigned", "Ready"),
            ("done", "Done"),
            ("cancel", "Cancel"),
            ("return", "Return"),
        ],
        string="DO Status",
    )

    @api.depends("date_from", "date_to")
    def _compute_report_filename(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                wizard.report_filename = "DP_Report_%s_%s" % (
                    wizard.date_from.strftime("%Y%m%d"),
                    wizard.date_to.strftime("%Y%m%d"),
                )
            else:
                wizard.report_filename = "DP_Report"

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError("Date From must be earlier than or equal to Date To.")

    def _get_sale_orders(self):
        self.ensure_one()
        date_from_dt = datetime.combine(self.date_from, time.min)
        date_to_dt = datetime.combine(self.date_to, time.max)
        picking_domain = [
            ("scheduled_date", ">=", fields.Datetime.to_string(date_from_dt)),
            ("scheduled_date", "<=", fields.Datetime.to_string(date_to_dt)),
            ("sale_id", "!=", False),
        ]
        if self.do_status:
            if self.do_status == 'return':
                picking_domain.append(('picking_type_id.code', '=', 'incoming'))
            else:
                picking_domain.append(('state', '=', self.do_status))
                picking_domain.append(('picking_type_id.code', '=', 'outgoing'))
        pickings = self.env["stock.picking"].search(
            picking_domain, order="scheduled_date, name"
        )
        sale_orders = pickings.mapped("sale_id")
        
        if self.do_status == 'done':
            return_pickings = self.env["stock.picking"].search([
                ("sale_id", "in", sale_orders.ids),
                ("picking_type_id.code", "=", "incoming"),
                ("state", "!=", "cancel"),
            ])
            sale_orders -= return_pickings.mapped("sale_id")

        return sale_orders.sorted(
            lambda order: (order.date_order or fields.Datetime.now(), order.name or "")
        )

    def action_export_excel(self):
        self.ensure_one()
        sale_orders = self._get_sale_orders()
        
        # Also find pickings WITHOUT sale_id (e.g. from buz_service_receipt)
        date_from_dt = datetime.combine(self.date_from, time.min)
        date_to_dt = datetime.combine(self.date_to, time.max)
        non_so_domain = [
            ("scheduled_date", ">=", fields.Datetime.to_string(date_from_dt)),
            ("scheduled_date", "<=", fields.Datetime.to_string(date_to_dt)),
            ("sale_id", "=", False),
        ]
        if self.do_status:
            if self.do_status == 'return':
                non_so_domain.append(('picking_type_id.code', '=', 'incoming'))
            else:
                non_so_domain.append(('state', '=', self.do_status))
                non_so_domain.append(('picking_type_id.code', '=', 'outgoing'))
        non_so_pickings = self.env["stock.picking"].search(
            non_so_domain, order="scheduled_date, name"
        )
        
        data = {
            "date_from": fields.Date.to_string(self.date_from),
            "date_to": fields.Date.to_string(self.date_to),
            "do_status": self.do_status,
            "sale_order_ids": sale_orders.ids,
            "service_receipt_picking_ids": non_so_pickings.ids,
        }
        return self.env.ref(
            "mogen_report_dp_excel.action_report_dp_excel_wizard"
        ).with_context(
            active_model=self._name,
            active_id=self.id,
            active_ids=self.ids,
        ).report_action(self, data=data)
