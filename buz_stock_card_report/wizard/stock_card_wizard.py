from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockCardWizard(models.TransientModel):
    _name = "buz.stock.card.wizard"
    _description = "Stock Card Report Wizard"

    date_from = fields.Date(
        string="Date From",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Date To",
        required=True,
        default=fields.Date.context_today,
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Warehouses",
        help="Leave empty to include every warehouse, each as its own block.",
    )
    product_ids = fields.Many2many(
        "product.product",
        string="Products",
        help="Leave empty to include every product with moves in the period.",
    )
    location_ids = fields.Many2many(
        "stock.location",
        string="Locations",
        domain=[("usage", "=", "internal")],
        help="Leave empty to include every internal location of the selected "
        "warehouse(s). When set, only moves touching these locations (or "
        "their sub-locations) are counted.",
    )
    report_filename = fields.Char(
        string="Report Filename",
        compute="_compute_report_filename",
    )

    @api.depends("date_from", "date_to")
    def _compute_report_filename(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to:
                wizard.report_filename = "Stock_Card_%s_%s" % (
                    wizard.date_from.strftime("%Y%m%d"),
                    wizard.date_to.strftime("%Y%m%d"),
                )
            else:
                wizard.report_filename = "Stock_Card"

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError("Date From must be earlier than or equal to Date To.")

    def _get_warehouses(self):
        self.ensure_one()
        if self.warehouse_ids:
            return self.warehouse_ids
        return self.env["stock.warehouse"].search([])

    def _get_warehouse_location_ids(self, warehouse):
        locations = self.env["stock.location"].search(
            [("id", "child_of", warehouse.view_location_id.id)]
        )
        if self.location_ids:
            selected = self.env["stock.location"].search(
                [("id", "child_of", self.location_ids.ids)]
            )
            locations = locations & selected
        return set(locations.ids)

    def _get_products_for_warehouse(self, warehouse_loc_ids, date_to):
        if self.product_ids:
            return self.product_ids
        move_lines = self.env["stock.move.line"].search(
            [
                ("state", "=", "done"),
                ("date", "<=", date_to),
                "|",
                ("location_id", "in", list(warehouse_loc_ids)),
                ("location_dest_id", "in", list(warehouse_loc_ids)),
            ]
        )
        return move_lines.product_id

    def _line_direction_qty(self, move_line, warehouse_loc_ids):
        """Return (in_qty, out_qty) for a move line relative to one warehouse."""
        dest_in = move_line.location_dest_id.id in warehouse_loc_ids
        src_in = move_line.location_id.id in warehouse_loc_ids
        qty = move_line.product_uom_id._compute_quantity(
            move_line.quantity, move_line.product_id.uom_id
        )
        if dest_in and not src_in:
            return qty, 0.0
        if src_in and not dest_in:
            return 0.0, qty
        return 0.0, 0.0

    def get_stock_card_lines(self, warehouse, product):
        """Build the ordered ledger (opening balance + running rows) for one
        warehouse/product pair, scoped to the wizard's date range."""
        self.ensure_one()
        warehouse_loc_ids = self._get_warehouse_location_ids(warehouse)

        base_domain = [
            ("state", "=", "done"),
            ("product_id", "=", product.id),
            "|",
            ("location_id", "in", list(warehouse_loc_ids)),
            ("location_dest_id", "in", list(warehouse_loc_ids)),
        ]

        opening_lines = self.env["stock.move.line"].search(
            base_domain + [("date", "<", self.date_from)]
        )
        opening_balance = 0.0
        for line in opening_lines:
            in_qty, out_qty = self._line_direction_qty(line, warehouse_loc_ids)
            opening_balance += in_qty - out_qty

        detail_lines = self.env["stock.move.line"].search(
            base_domain
            + [("date", ">=", self.date_from), ("date", "<=", self.date_to)],
            order="date, id",
        )

        rows = []
        running_balance = opening_balance
        for seq, line in enumerate(detail_lines, start=1):
            in_qty, out_qty = self._line_direction_qty(line, warehouse_loc_ids)
            if not in_qty and not out_qty:
                continue
            opening_for_row = running_balance
            running_balance += in_qty - out_qty
            picking = line.picking_id
            rows.append(
                {
                    "seq": seq,
                    "date": line.date,
                    "doc_type": picking.picking_type_id.name if picking else (line.move_id.picking_type_id.name or ""),
                    "doc_number": picking.name if picking else (line.reference or line.move_id.reference or ""),
                    "opening": opening_for_row,
                    "in_qty": in_qty,
                    "out_qty": out_qty,
                    "balance": running_balance,
                }
            )
        return opening_balance, rows

    def action_export_excel(self):
        self.ensure_one()
        data = {
            "wizard_id": self.id,
        }
        return self.env.ref(
            "buz_stock_card_report.action_report_stock_card_xlsx"
        ).with_context(
            active_model=self._name,
            active_id=self.id,
            active_ids=self.ids,
        ).report_action(self, data=data)
