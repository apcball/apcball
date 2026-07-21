from odoo import fields, models


class WarehouseLayoutElement(models.Model):
    _name = "buz.warehouse.layout.element"
    _description = "Warehouse Layout Element"
    _order = "sequence, id"

    name = fields.Char(required=True)
    element_type = fields.Selection(
        [
            ("zone", "Zone"),
            ("aisle", "Aisle"),
            ("obstacle", "Obstacle"),
            ("forklift", "Forklift"),
            ("text", "Text Label"),
        ],
        required=True,
        default="zone",
    )
    zone_type = fields.Selection(
        [
            ("receiving", "Receiving"),
            ("storage", "Storage"),
            ("picking", "Picking"),
            ("packing", "Packing"),
            ("shipping", "Shipping"),
            ("finished_goods", "Finished Goods"),
        ],
        help="Functional zone type — drives the color on the layout designer.",
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="warehouse_id.company_id", store=True, readonly=True
    )
    pos_x = fields.Float(string="X (m)")
    pos_y = fields.Float(string="Y (m)")
    width = fields.Float(string="Width (m)", default=20.0)
    height = fields.Float(string="Depth (m)", default=10.0)
    rotation = fields.Selection(
        [("0", "0°"), ("90", "90°"), ("180", "180°"), ("270", "270°")],
        default="0",
    )
    notes = fields.Text()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
