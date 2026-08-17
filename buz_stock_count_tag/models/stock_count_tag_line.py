from odoo import models, fields


class StockCountTagLine(models.Model):
    _name = "buz.stock.count.tag.line"
    _description = "Stock Count Tag Line"
    _order = "sequence, id"

    tag_id = fields.Many2one(
        "buz.stock.count.tag", string="Stock Count Tag", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)

    product_code = fields.Char(required=True)
    product_name = fields.Char(required=True)
    product_status = fields.Char()
    warehouse = fields.Char(required=True)
    layout = fields.Char()
    lac = fields.Char()
    quantity = fields.Float(required=True)

    actual_quantity = fields.Float(
        help="Filled by hand during the physical count. Never written by the system."
    )

    counted_by = fields.Char()
    checked_by = fields.Char()
    audited_by = fields.Char()
    counted_date = fields.Date()
    checked_date = fields.Date()
    audited_date = fields.Date()

    import_status = fields.Selection(
        [("ok", "OK"), ("warning", "Warning"), ("error", "Error")],
        default="ok",
        readonly=True,
    )
    import_message = fields.Char(readonly=True)
