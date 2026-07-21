from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    max_capacity = fields.Float(
        string="Max Capacity",
        help="Maximum storage capacity of this location in product units. "
        "Used by the Smart Warehouse dashboard to compute occupancy.",
    )
    layout_x = fields.Float(
        string="Layout X (m)",
        help="Position of this rack on the warehouse floor, in meters from "
        "the left edge. Leave 0/unset on all racks for automatic layout.",
    )
    layout_y = fields.Float(
        string="Layout Y (m)",
        help="Position of this rack on the warehouse floor, in meters from "
        "the top edge.",
    )
    layout_rotation = fields.Selection(
        [("0", "0°"), ("90", "90°"), ("180", "180°"), ("270", "270°")],
        string="Rotation",
        default="0",
    )
    layout_levels = fields.Integer(
        string="Shelf Levels",
        default=3,
        help="Number of vertical shelf levels drawn for this rack in the 3D view.",
    )
    is_loading_dock = fields.Boolean(
        string="Loading Dock",
        help="Show this location as a loading dock area (with trucks) on the "
        "Smart Warehouse 3D map. Position it with Layout X/Y.",
    )
    layout_positioned = fields.Boolean(
        string="Manual Position",
        help="Place this rack at Layout X/Y instead of the automatic grid.",
    )
    rack_code = fields.Char(
        string="Rack Code",
        help="Short code shown on the warehouse layout, e.g. RA-01.",
    )
    rack_type = fields.Selection(
        [
            ("selective", "Selective Rack"),
            ("drive_in", "Drive-in Rack"),
            ("double_deep", "Double Deep"),
            ("push_back", "Push Back Rack"),
            ("cantilever", "Cantilever Rack"),
            ("pallet_flow", "Pallet Flow Rack"),
            ("shelf", "Shelf"),
        ],
        string="Rack Type",
        default="selective",
    )
    layout_width = fields.Float(
        string="Layout Width (m)",
        default=4.0,
        help="Footprint width of this rack on the layout designer, in meters.",
    )
    layout_depth = fields.Float(
        string="Layout Depth (m)",
        default=1.2,
        help="Footprint depth of this rack on the layout designer, in meters.",
    )
    layout_height = fields.Float(
        string="Layout Height (m)",
        default=5.5,
        help="Physical rack height, in meters (informational).",
    )
    layout_bays = fields.Integer(
        string="Bays / Level",
        default=2,
        help="Number of bays per level, drawn as columns on the layout.",
    )
    capacity_per_level = fields.Float(
        string="Capacity / Level",
        help="Storage capacity of one level, in the capacity unit below.",
    )
    capacity_uom = fields.Selection(
        [("pallet", "Pallet"), ("box", "Box"), ("unit", "Unit")],
        string="Capacity Unit",
        default="pallet",
    )
    layout_notes = fields.Text(string="Layout Notes")
    layout_zone_element_id = fields.Many2one(
        "buz.warehouse.layout.element",
        string="Layout Zone",
        domain=[("element_type", "=", "zone")],
        ondelete="set null",
        help="Designer zone this rack belongs to (visual grouping only).",
    )
    occupancy_pct = fields.Float(
        string="Occupancy (%)",
        compute="_compute_occupancy_pct",
    )

    @api.depends("max_capacity", "quant_ids.quantity")
    def _compute_occupancy_pct(self):
        for location in self:
            if location.max_capacity > 0:
                on_hand = sum(location.quant_ids.mapped("quantity"))
                location.occupancy_pct = max(
                    0.0, on_hand / location.max_capacity * 100.0
                )
            else:
                location.occupancy_pct = 0.0
