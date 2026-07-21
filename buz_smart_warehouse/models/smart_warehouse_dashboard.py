import math
from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError


class SmartWarehouseDashboard(models.TransientModel):
    _name = "buz.smart.warehouse.dashboard"
    _description = "Smart Warehouse Dashboard"

    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, readonly=True
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _today_range(self):
        """Return (start, end) datetimes of today in the user's timezone,
        expressed in UTC naive datetimes for domain filtering."""
        today = fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(datetime.combine(today, time.min))
        end = fields.Datetime.to_datetime(datetime.combine(today, time.max))
        return start, end

    @api.model
    def _picking_domain_today(self, extra=None, warehouse_id=None):
        start, end = self._today_range()
        domain = [
            ("company_id", "=", self.env.company.id),
            ("scheduled_date", ">=", start),
            ("scheduled_date", "<=", end),
            ("state", "not in", ("cancel",)),
        ]
        if warehouse_id:
            domain.append(("picking_type_id.warehouse_id", "=", warehouse_id))
        return domain + (extra or [])

    @api.model
    def _internal_locations(self, warehouse_id=None, zone_id=None):
        domain = [
            ("usage", "=", "internal"),
            ("company_id", "in", (self.env.company.id, False)),
        ]
        if zone_id:
            domain.append(("id", "child_of", zone_id))
        elif warehouse_id:
            warehouse = self.env["stock.warehouse"].browse(warehouse_id).exists()
            if warehouse:
                domain.append(("id", "child_of", warehouse.view_location_id.id))
        return self.env["stock.location"].search(domain)

    @api.model
    def _picking_types_by_role(self, warehouse_id=None):
        """Map operation roles to picking types of the current company.

        Multi-step warehouses expose PICK/PACK via sequence_code; single-step
        warehouses only have IN/INT/OUT — missing roles return empty recordsets
        and the frontend hides panels with zero totals.
        """
        type_domain = [("company_id", "=", self.env.company.id)]
        if warehouse_id:
            type_domain.append(("warehouse_id", "=", warehouse_id))
        types = self.env["stock.picking.type"].search(type_domain)
        return {
            "receiving": types.filtered(lambda t: t.code == "incoming"),
            "put_away": types.filtered(
                lambda t: t.code == "internal" and t.sequence_code in ("INT", "STOR")
            ),
            "picking": types.filtered(
                lambda t: t.code == "internal" and t.sequence_code == "PICK"
            )
            or types.filtered(lambda t: t.code == "outgoing"),
            "packing": types.filtered(
                lambda t: t.code == "internal" and t.sequence_code == "PACK"
            ),
            "delivery": types.filtered(lambda t: t.code == "outgoing"),
        }

    @api.model
    def _count_done_total(self, picking_types):
        if not picking_types:
            return {"done": 0, "total": 0}
        domain = self._picking_domain_today(
            [("picking_type_id", "in", picking_types.ids)]
        )
        total = self.env["stock.picking"].search_count(domain)
        done = self.env["stock.picking"].search_count(
            domain + [("state", "=", "done")]
        )
        return {"done": done, "total": total}

    # ------------------------------------------------------------------
    # KPI cards
    # ------------------------------------------------------------------
    @api.model
    def get_filters(self):
        """Warehouses of the current company and their zones (direct internal
        children of each warehouse's stock location) for dashboard dropdowns."""
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)]
        )
        result = []
        for warehouse in warehouses:
            zones = self.env["stock.location"].search(
                [
                    ("location_id", "=", warehouse.lot_stock_id.id),
                    ("usage", "=", "internal"),
                ]
            )
            result.append(
                {
                    "id": warehouse.id,
                    "name": warehouse.name,
                    "code": warehouse.code,
                    "zones": [{"id": z.id, "name": z.name} for z in zones],
                }
            )
        return result

    @api.model
    def get_kpis(self, warehouse_id=None):
        Picking = self.env["stock.picking"]
        roles = self._picking_types_by_role(warehouse_id)

        receipts = Picking.search(
            self._picking_domain_today(
                [("picking_type_id", "in", roles["receiving"].ids)]
            )
        )
        po_count = len(set(receipts.mapped("origin")) - {False}) or len(receipts)

        ready_to_ship = Picking.search_count(
            self._picking_domain_today(
                [
                    ("picking_type_id", "in", roles["delivery"].ids),
                    ("state", "=", "assigned"),
                ]
            )
        )

        return {
            "receiving": {"value": po_count, "unit": "POs"},
            "put_away": {
                "value": self._count_done_total(roles["put_away"])["total"],
                "unit": "Tasks",
            },
            "picking": {
                "value": self._count_done_total(roles["picking"])["total"],
                "unit": "Tasks",
            },
            "packing": {
                "value": self._count_done_total(roles["packing"])["total"],
                "unit": "Tasks",
            },
            "ready_to_ship": {"value": ready_to_ship, "unit": "DOs"},
            "accuracy": {"value": self._inventory_accuracy(), "unit": "%"},
            "utilization": {
                "value": self._utilization(warehouse_id)["pct"],
                "unit": "%",
            },
        }

    @api.model
    def _inventory_accuracy(self):
        """Accuracy from inventory adjustment moves of the last 30 days:
        1 - (sum of absolute adjusted qty / on-hand qty). 100 if no counts."""
        since = fields.Datetime.now() - timedelta(days=30)
        adjustment_location = self.env["stock.location"].search(
            [("usage", "=", "inventory")], limit=1
        )
        if not adjustment_location:
            return 100.0
        moves = self.env["stock.move"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("state", "=", "done"),
                ("date", ">=", since),
                "|",
                ("location_id.usage", "=", "inventory"),
                ("location_dest_id.usage", "=", "inventory"),
            ]
        )
        adjusted = sum(abs(qty) for qty in moves.mapped("product_uom_qty"))
        quants = self.env["stock.quant"].search(
            [
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", (self.env.company.id, False)),
            ]
        )
        on_hand = sum(abs(qty) for qty in quants.mapped("quantity"))
        if not on_hand:
            return 100.0
        return round(max(0.0, (1 - adjusted / on_hand)) * 100, 2)

    @api.model
    def _utilization(self, warehouse_id=None, zone_id=None):
        locations = self._internal_locations(warehouse_id, zone_id).filtered(
            lambda l: l.max_capacity > 0
        )
        capacity = sum(locations.mapped("max_capacity"))
        if not capacity:
            return {"pct": 0.0, "used": 0.0, "capacity": 0.0}
        used = 0.0
        quant_groups = self.env["stock.quant"].read_group(
            [("location_id", "in", locations.ids)],
            ["quantity:sum"],
            ["location_id"],
        )
        for group in quant_groups:
            used += max(0.0, group["quantity"])
        pct = round(min(100.0, used / capacity * 100), 1)
        return {"pct": pct, "used": used, "capacity": capacity}

    # ------------------------------------------------------------------
    # Warehouse map
    # ------------------------------------------------------------------
    @api.model
    def _layout_dict(self, location):
        """Full designed footprint of a rack/dock location for the 2D/3D map."""
        return {
            "positioned": location.layout_positioned,
            "x": location.layout_x,
            "y": location.layout_y,
            "rotation": int(location.layout_rotation or "0"),
            "levels": max(1, location.layout_levels or 3),
            "width": location.layout_width or 4.0,
            "depth": location.layout_depth or 1.2,
            "height": location.layout_height or 5.5,
            "bays": max(1, location.layout_bays or 2),
            "rack_type": location.rack_type or "selective",
            "rack_code": location.rack_code or "",
            "zone_element_id": location.layout_zone_element_id.id or False,
        }

    @api.model
    def _map_elements(self, warehouse_id=None):
        """Free-drawn designer elements (zones, aisles, ...) for the map."""
        warehouse = self._designer_warehouse(warehouse_id)
        if not warehouse:
            return []
        return [
            {
                "id": element.id,
                "element_type": element.element_type,
                "zone_type": element.zone_type or "storage",
                "name": element.name,
                "x": element.pos_x,
                "y": element.pos_y,
                "width": element.width,
                "height": element.height,
                "rotation": int(element.rotation or "0"),
            }
            for element in self.env["buz.warehouse.layout.element"].search(
                [("warehouse_id", "=", warehouse.id)]
            )
        ]

    @api.model
    def _map_floor(self, racks, docks, elements):
        """Canvas size in meters shared by the designer and the 2D/3D map."""
        width, height = 70.0, 45.0
        margin = 8.0
        for rack in racks + docks:
            layout = rack["layout"]
            if not layout.get("positioned"):
                continue
            size = max(layout.get("width", 0.0), layout.get("depth", 0.0))
            width = max(width, layout["x"] + size + margin)
            height = max(height, layout["y"] + size + margin)
        for element in elements:
            size = max(element["width"], element["height"])
            width = max(width, element["x"] + size + margin)
            height = max(height, element["y"] + size + margin)
        return {
            "w": math.ceil(width / 10) * 10,
            "h": math.ceil(height / 10) * 10,
        }

    @api.model
    def get_map_data(self, warehouse_id=None, zone_id=None):
        """Internal locations grouped into racks by parent location.
        Locations directly under the warehouse stock location are grouped
        by the first letter block of their name as a fallback."""
        all_locations = self._internal_locations(warehouse_id, zone_id)
        quant_groups = self.env["stock.quant"].read_group(
            [("location_id", "in", all_locations.ids)],
            ["quantity:sum"],
            ["location_id"],
        )
        qty_by_location = {
            g["location_id"][0]: g["quantity"] for g in quant_groups
        }
        # leaf storage bins, plus parent locations that hold stock directly
        # (e.g. FG10/Stock with quants of its own next to its child zones)
        locations = all_locations.filtered(
            lambda l: not l.child_ids or qty_by_location.get(l.id)
        )

        racks = {}
        for location in locations:
            parent = location.location_id
            if location.child_ids:
                # parent holding direct stock: show it as a bin inside its
                # own rack group, next to its children
                rack_key = location.id
                rack_id = location.id
                rack_name = location.name
                layout = self._layout_dict(location)
            elif parent and parent.usage == "internal":
                rack_key = parent.id
                rack_id = parent.id
                rack_name = parent.name
                layout = self._layout_dict(parent)
            else:
                rack_name = (location.name or "?")[:1].upper()
                rack_key = "prefix_%s" % rack_name
                rack_id = None
                layout = {
                    "positioned": False,
                    "x": 0.0,
                    "y": 0.0,
                    "rotation": 0,
                    "levels": 3,
                    "width": 4.0,
                    "depth": 1.2,
                    "height": 5.5,
                    "bays": 2,
                    "rack_type": "selective",
                    "rack_code": "",
                    "zone_element_id": False,
                }
            qty = max(0.0, qty_by_location.get(location.id, 0.0))
            capacity = location.max_capacity
            pct = round(qty / capacity * 100, 1) if capacity else None
            racks.setdefault(
                rack_key,
                {"id": rack_id, "name": rack_name, "layout": layout, "locations": []},
            )["locations"].append(
                {
                    "id": location.id,
                    "name": location.name,
                    "qty": qty,
                    "capacity": capacity,
                    "pct": pct,
                }
            )

        rack_list = sorted(racks.values(), key=lambda r: r["name"])
        for rack in rack_list:
            rack["locations"].sort(key=lambda l: l["name"])
        docks = self._get_docks(warehouse_id)
        elements = self._map_elements(warehouse_id)
        return {
            "racks": rack_list,
            "docks": docks,
            "elements": elements,
            "floor": self._map_floor(rack_list, docks, elements),
            "utilization": self._utilization(warehouse_id, zone_id),
        }

    @api.model
    def _get_docks(self, warehouse_id=None):
        """Loading dock locations with the number of trucks (today's assigned
        receipts/deliveries) currently expected at each."""
        # child_ids filter: a location holding bins (e.g. FG10/Stock) is a
        # storage rack even if is_loading_dock was flagged by mistake
        domain = [
            ("is_loading_dock", "=", True),
            ("child_ids", "=", False),
            ("company_id", "in", (self.env.company.id, False)),
        ]
        if warehouse_id:
            warehouse = self.env["stock.warehouse"].browse(warehouse_id).exists()
            if warehouse:
                domain.append(("id", "child_of", warehouse.view_location_id.id))
        docks = self.env["stock.location"].search(domain)
        roles = self._picking_types_by_role(warehouse_id)
        Picking = self.env["stock.picking"]
        incoming = Picking.search_count(
            self._picking_domain_today(
                [
                    ("picking_type_id", "in", roles["receiving"].ids),
                    ("state", "=", "assigned"),
                ],
                warehouse_id,
            )
        )
        outgoing = Picking.search_count(
            self._picking_domain_today(
                [
                    ("picking_type_id", "in", roles["delivery"].ids),
                    ("state", "=", "assigned"),
                ],
                warehouse_id,
            )
        )
        result = []
        for dock in docks:
            # classify by name: Input/Receipt docks = in, Output/Ship = out
            name = (dock.complete_name or dock.name or "").lower()
            if any(k in name for k in ("input", "receipt", "receiv", "รับ")):
                kind = "in"
            else:
                kind = "out"
            result.append(
                {
                    "id": dock.id,
                    "name": dock.name,
                    "kind": kind,
                    "x": dock.layout_x,
                    "y": dock.layout_y,
                    "rotation": int(dock.layout_rotation or "0"),
                    "positioned": dock.layout_positioned,
                    "layout": self._layout_dict(dock),
                    "active_trucks": min(
                        3, incoming if kind == "in" else outgoing
                    ),
                }
            )
        return result

    # ------------------------------------------------------------------
    # Layout editing (Manager only)
    # ------------------------------------------------------------------
    @api.model
    def save_layout(self, positions):
        """Persist rack positions dragged on the 3D map.

        :param positions: [{"id": location_id, "x": float, "y": float,
                            "rotation": "0"|"90"|"180"|"270" (optional)}]
        """
        if not self.env.user.has_group(
            "buz_smart_warehouse.group_smart_warehouse_manager"
        ):
            raise AccessError(
                "Only Smart Warehouse managers can rearrange the layout."
            )
        Location = self.env["stock.location"]
        for pos in positions:
            location = Location.browse(int(pos["id"])).exists()
            if not location or location.usage != "internal":
                continue
            if location.company_id and location.company_id != self.env.company:
                continue
            values = {
                "layout_positioned": True,
                "layout_x": float(pos["x"]),
                "layout_y": float(pos["y"]),
            }
            rotation = str(pos.get("rotation", ""))
            if rotation in ("0", "90", "180", "270"):
                values["layout_rotation"] = rotation
            # group membership verified above; sudo limited to layout fields
            location.sudo().write(values)
        return True

    # ------------------------------------------------------------------
    # Layout Designer (full editor)
    # ------------------------------------------------------------------
    @api.model
    def _designer_warehouse(self, warehouse_id):
        warehouse = self.env["stock.warehouse"].browse(int(warehouse_id or 0)).exists()
        if not warehouse:
            warehouse = self.env["stock.warehouse"].search(
                [("company_id", "=", self.env.company.id)], limit=1
            )
        return warehouse

    @api.model
    def _location_designer_vals(self, location, pct_by_location):
        pcts = [
            pct_by_location[l.id]
            for l in location.child_ids
            if pct_by_location.get(l.id) is not None
        ]
        if pct_by_location.get(location.id) is not None:
            pcts.append(pct_by_location[location.id])
        return {
            "id": location.id,
            "kind": "dock"
            if location.is_loading_dock and not location.child_ids
            else "rack",
            "name": location.name,
            "rack_code": location.rack_code or "",
            "rack_type": location.rack_type or "selective",
            "x": location.layout_x,
            "y": location.layout_y,
            "rotation": int(location.layout_rotation or "0"),
            "positioned": location.layout_positioned,
            "width": location.layout_width or 4.0,
            "depth": location.layout_depth or 1.2,
            "height": location.layout_height or 5.5,
            "levels": max(1, location.layout_levels or 3),
            "bays": max(1, location.layout_bays or 2),
            "capacity_per_level": location.capacity_per_level,
            "capacity_uom": location.capacity_uom or "pallet",
            "zone_element_id": location.layout_zone_element_id.id or False,
            "notes": location.layout_notes or "",
            "active": location.active,
            "bins": len(location.child_ids),
            "pct": round(sum(pcts) / len(pcts), 1) if pcts else None,
        }

    @api.model
    def get_designer_data(self, warehouse_id=None):
        """Racks, docks and free-drawn elements for the layout designer."""
        warehouse = self._designer_warehouse(warehouse_id)
        racks, docks, elements = [], [], []
        if warehouse:
            locations = self.env["stock.location"].search(
                [
                    ("usage", "=", "internal"),
                    ("company_id", "in", (self.env.company.id, False)),
                    ("id", "child_of", warehouse.view_location_id.id),
                ]
            )
            pct_by_location = {}
            for group in self.env["stock.quant"].read_group(
                [("location_id", "in", locations.ids)],
                ["quantity:sum"],
                ["location_id"],
            ):
                location = locations.browse(group["location_id"][0])
                if location.max_capacity > 0:
                    pct_by_location[location.id] = round(
                        max(0.0, group["quantity"])
                        / location.max_capacity
                        * 100,
                        1,
                    )
            for location in locations:
                if location.is_loading_dock and not location.child_ids:
                    docks.append(
                        self._location_designer_vals(location, pct_by_location)
                    )
                elif location.child_ids or location.layout_positioned:
                    racks.append(
                        self._location_designer_vals(location, pct_by_location)
                    )
            for element in self.env["buz.warehouse.layout.element"].search(
                [("warehouse_id", "=", warehouse.id)]
            ):
                elements.append(
                    {
                        "id": element.id,
                        "element_type": element.element_type,
                        "zone_type": element.zone_type or "storage",
                        "name": element.name,
                        "x": element.pos_x,
                        "y": element.pos_y,
                        "width": element.width,
                        "height": element.height,
                        "rotation": int(element.rotation or "0"),
                        "notes": element.notes or "",
                        "active": element.active,
                    }
                )
        return {
            "warehouse_id": warehouse.id if warehouse else False,
            "racks": racks,
            "docks": docks,
            "elements": elements,
            "is_manager": self.env.user.has_group(
                "buz_smart_warehouse.group_smart_warehouse_manager"
            ),
        }

    @api.model
    def save_designer_layout(self, warehouse_id, payload):
        """Persist the full designer state: racks/docks (stock.location),
        free elements, and deletions. Manager only."""
        if not self.env.user.has_group(
            "buz_smart_warehouse.group_smart_warehouse_manager"
        ):
            raise AccessError(
                "Only Smart Warehouse managers can edit the layout."
            )
        warehouse = self._designer_warehouse(warehouse_id)
        if not warehouse:
            raise AccessError("No warehouse found for the current company.")
        Location = self.env["stock.location"]
        Element = self.env["buz.warehouse.layout.element"]

        rotation_ok = ("0", "90", "180", "270")
        element_by_tmp = {}

        for vals in payload.get("elements", []):
            values = {
                "name": vals.get("name") or "?",
                "element_type": vals.get("element_type") or "zone",
                "zone_type": vals.get("zone_type") or False,
                "warehouse_id": warehouse.id,
                "pos_x": float(vals.get("x") or 0.0),
                "pos_y": float(vals.get("y") or 0.0),
                "width": float(vals.get("width") or 0.0),
                "height": float(vals.get("height") or 0.0),
                "notes": vals.get("notes") or False,
                "active": bool(vals.get("active", True)),
            }
            rotation = str(vals.get("rotation", "0"))
            if rotation in rotation_ok:
                values["rotation"] = rotation
            element_id = vals.get("id")
            if element_id:
                element = Element.browse(int(element_id)).exists()
                if element and element.warehouse_id == warehouse:
                    element.write(values)
            else:
                element = Element.create(values)
                if vals.get("tmp_key"):
                    element_by_tmp[vals["tmp_key"]] = element.id

        for vals in payload.get("locations", []):
            zone_ref = vals.get("zone_element_id")
            if isinstance(zone_ref, str):
                zone_ref = element_by_tmp.get(zone_ref, False)
            values = {
                "name": vals.get("name") or "?",
                "rack_code": vals.get("rack_code") or False,
                "rack_type": vals.get("rack_type") or "selective",
                "layout_positioned": True,
                "layout_x": float(vals.get("x") or 0.0),
                "layout_y": float(vals.get("y") or 0.0),
                "layout_width": float(vals.get("width") or 4.0),
                "layout_depth": float(vals.get("depth") or 1.2),
                "layout_height": float(vals.get("height") or 5.5),
                "layout_levels": max(1, int(vals.get("levels") or 3)),
                "layout_bays": max(1, int(vals.get("bays") or 2)),
                "capacity_per_level": float(vals.get("capacity_per_level") or 0.0),
                "capacity_uom": vals.get("capacity_uom") or "pallet",
                "layout_zone_element_id": int(zone_ref) if zone_ref else False,
                "layout_notes": vals.get("notes") or False,
                "is_loading_dock": vals.get("kind") == "dock",
                "active": bool(vals.get("active", True)),
            }
            rotation = str(vals.get("rotation", "0"))
            if rotation in rotation_ok:
                values["layout_rotation"] = rotation
            location_id = vals.get("id")
            if location_id:
                location = Location.browse(int(location_id)).exists()
                if not location or location.usage != "internal":
                    continue
                if (
                    location.company_id
                    and location.company_id != self.env.company
                ):
                    continue
                if location.child_ids:
                    # a location holding bins is storage, never a dock
                    values["is_loading_dock"] = False
                # group membership verified above; sudo limited to layout data
                location.sudo().write(values)
            else:
                values.update(
                    {
                        "usage": "internal",
                        "location_id": warehouse.lot_stock_id.id,
                        "company_id": warehouse.company_id.id,
                    }
                )
                Location.sudo().create(values)

        for location_id in payload.get("deleted_location_ids", []):
            location = Location.browse(int(location_id)).exists()
            if not location or location.usage != "internal":
                continue
            if location.company_id and location.company_id != self.env.company:
                continue
            # archive only: the location may carry stock or move history
            location.sudo().write({"active": False})

        for element_id in payload.get("deleted_element_ids", []):
            element = Element.browse(int(element_id)).exists()
            if element and element.warehouse_id == warehouse:
                element.unlink()

        return self.get_designer_data(warehouse.id)

    # ------------------------------------------------------------------
    # Global search (SKU / Product / Lot / Serial / Location / Order)
    # ------------------------------------------------------------------
    @api.model
    def search_stock(self, term):
        term = (term or "").strip()
        if len(term) < 2:
            return []
        company_ids = (self.env.company.id, False)
        results = []

        products = self.env["product.product"].search(
            [
                ("type", "=", "product"),
                "|",
                ("name", "ilike", term),
                ("default_code", "ilike", term),
            ],
            limit=6,
        )
        for product in products:
            quants = self.env["stock.quant"].search(
                [
                    ("product_id", "=", product.id),
                    ("location_id.usage", "=", "internal"),
                    ("company_id", "in", company_ids),
                    ("quantity", ">", 0),
                ]
            )
            location_names = quants.mapped("location_id.name")
            results.append(
                {
                    "type": "product",
                    "icon": "fa-cube",
                    "id": product.id,
                    "label": product.display_name,
                    "sublabel": "%s ชิ้น @ %s"
                    % (
                        int(sum(quants.mapped("quantity"))),
                        ", ".join(location_names[:4]) or "ไม่มีสต็อก",
                    ),
                    "location_ids": quants.mapped("location_id").ids,
                }
            )

        lots = self.env["stock.lot"].search(
            [("name", "ilike", term), ("company_id", "in", company_ids)],
            limit=4,
        )
        for lot in lots:
            quants = lot.quant_ids.filtered(
                lambda q: q.location_id.usage == "internal" and q.quantity > 0
            )
            results.append(
                {
                    "type": "lot",
                    "icon": "fa-barcode",
                    "id": lot.id,
                    "label": "Lot %s" % lot.name,
                    "sublabel": lot.product_id.display_name,
                    "location_ids": quants.mapped("location_id").ids,
                }
            )

        locations = self.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("company_id", "in", company_ids),
                "|",
                ("name", "ilike", term),
                ("complete_name", "ilike", term),
            ],
            limit=4,
        )
        for location in locations:
            leaf_ids = (
                self.env["stock.location"]
                .search([("id", "child_of", location.id), ("child_ids", "=", False)])
                .ids
            )
            results.append(
                {
                    "type": "location",
                    "icon": "fa-map-marker",
                    "id": location.id,
                    "label": location.complete_name,
                    "sublabel": "Location",
                    "location_ids": leaf_ids or [location.id],
                }
            )

        pickings = self.env["stock.picking"].search(
            [
                ("company_id", "=", self.env.company.id),
                "|",
                ("name", "ilike", term),
                ("origin", "ilike", term),
            ],
            order="scheduled_date desc",
            limit=4,
        )
        for picking in pickings:
            results.append(
                {
                    "type": "picking",
                    "icon": "fa-file-text-o",
                    "id": picking.id,
                    "label": picking.name,
                    "sublabel": "%s · %s"
                    % (picking.origin or "-", picking.state),
                    "location_ids": [],
                }
            )
        return results

    # ------------------------------------------------------------------
    # Recommendations (rule based)
    # ------------------------------------------------------------------
    @api.model
    def get_recommendations(self, warehouse_id=None):
        Picking = self.env["stock.picking"]
        roles = self._picking_types_by_role(warehouse_id)
        now = fields.Datetime.now()
        recommendations = []

        # 1. Receipts ready to process
        arrived = Picking.search(
            [
                ("company_id", "=", self.env.company.id),
                ("picking_type_id", "in", roles["receiving"].ids),
                ("state", "=", "assigned"),
                ("scheduled_date", "<=", now),
            ],
            order="scheduled_date",
            limit=3,
        )
        for picking in arrived:
            recommendations.append(
                {
                    "icon": "receive",
                    "severity": "danger",
                    "title": "%s มาถึงแล้ว" % (picking.origin or picking.name),
                    "subtitle": "รอรับสินค้า %d รายการ" % len(picking.move_ids),
                    "action_label": "รับสินค้า",
                    "action": {"model": "stock.picking", "res_id": picking.id},
                }
            )

        # 2. Urgent deliveries (deadline today or late)
        _, end = self._today_range()
        urgent = Picking.search(
            [
                ("company_id", "=", self.env.company.id),
                ("picking_type_id", "in", roles["delivery"].ids),
                ("state", "in", ("assigned", "confirmed", "waiting")),
                ("date_deadline", "!=", False),
                ("date_deadline", "<=", end),
            ],
            order="date_deadline",
            limit=3,
        )
        for picking in urgent:
            recommendations.append(
                {
                    "icon": "pick",
                    "severity": "warning",
                    "title": "%s ควร Pick ก่อน" % (picking.origin or picking.name),
                    "subtitle": "ลูกค้าต้องการด่วน",
                    "action_label": "เริ่ม Pick",
                    "action": {"model": "stock.picking", "res_id": picking.id},
                }
            )

        # 3. Locations almost full
        full_locations = (
            self._internal_locations(warehouse_id)
            .filtered(lambda l: l.max_capacity > 0 and l.occupancy_pct >= 90)
            .sorted("occupancy_pct", reverse=True)[:3]
        )
        for location in full_locations:
            recommendations.append(
                {
                    "icon": "shelf",
                    "severity": "warning",
                    "title": "Shelf %s ใกล้เต็ม" % location.name,
                    "subtitle": "การใช้งาน %d%%" % round(location.occupancy_pct),
                    "action_label": "ดูรายละเอียด",
                    "action": {"model": "stock.location", "res_id": location.id},
                }
            )

        # 4. Cycle count due
        today = fields.Date.context_today(self)
        count_due = self.env["stock.quant"].search_count(
            [
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", (self.env.company.id, False)),
                ("inventory_date", "!=", False),
                ("inventory_date", "<=", today),
            ]
        )
        if count_due:
            recommendations.append(
                {
                    "icon": "count",
                    "severity": "danger",
                    "title": "Inventory Count %d รายการ" % count_due,
                    "subtitle": "ถึงรอบนับสต็อก",
                    "action_label": "เริ่มนับ",
                    "action": {
                        "model": "stock.quant",
                        "domain": [
                            ("location_id.usage", "=", "internal"),
                            ("inventory_date", "<=", str(today)),
                        ],
                        "context": {"inventory_mode": True},
                    },
                }
            )

        # 5. Open backorders
        backorder_domain = [
            ("company_id", "=", self.env.company.id),
            ("backorder_id", "!=", False),
            ("state", "not in", ("done", "cancel")),
        ]
        if warehouse_id:
            backorder_domain.append(
                ("picking_type_id.warehouse_id", "=", warehouse_id)
            )
        backorders = Picking.search_count(backorder_domain)
        if backorders:
            recommendations.append(
                {
                    "icon": "backorder",
                    "severity": "warning",
                    "title": "Backorder %d รายการ" % backorders,
                    "subtitle": "ต้องติดตาม",
                    "action_label": "ดูรายการ",
                    "action": {
                        "model": "stock.picking",
                        "domain": [
                            ("backorder_id", "!=", False),
                            ("state", "not in", ("done", "cancel")),
                        ],
                    },
                }
            )

        # 6. Putaway suggestions for arrived receipts
        for suggestion in self.get_putaway_suggestions(warehouse_id)[:3]:
            recommendations.append(
                {
                    "icon": "shelf",
                    "severity": "info",
                    "title": "Putaway: %s" % suggestion["product"],
                    "subtitle": "แนะนำเก็บที่ %s" % suggestion["location"],
                    "action_label": "เปิดใบรับ",
                    "action": {
                        "model": "stock.picking",
                        "res_id": suggestion["picking_id"],
                    },
                }
            )

        # 7. Replenishment below minimum
        replenish = self._replenishment_info(warehouse_id)
        if replenish["count"]:
            recommendations.append(
                {
                    "icon": "count",
                    "severity": "warning",
                    "title": "เติมสินค้า %d รายการ" % replenish["count"],
                    "subtitle": "ต่ำกว่าจุดสั่งซื้อ (Reordering Rule)",
                    "action_label": "ดูรายการ",
                    "action": replenish["action"],
                }
            )

        return recommendations

    @api.model
    def get_putaway_suggestions(self, warehouse_id=None):
        """Suggest a storage bin for each product on today's arrived receipts:
        prefer a bin already holding the product with free capacity, else the
        least-occupied bin that fits, else skip (no capacity data)."""
        roles = self._picking_types_by_role(warehouse_id)
        pickings = self.env["stock.picking"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("picking_type_id", "in", roles["receiving"].ids),
                ("state", "=", "assigned"),
            ],
            order="scheduled_date",
            limit=5,
        )
        bins = self._internal_locations(warehouse_id).filtered(
            lambda l: not l.child_ids and l.max_capacity > 0
        )
        if not bins:
            return []
        qty_by_bin = {}
        for group in self.env["stock.quant"].read_group(
            [("location_id", "in", bins.ids)], ["quantity:sum"], ["location_id"]
        ):
            qty_by_bin[group["location_id"][0]] = max(0.0, group["quantity"])

        suggestions = []
        seen_products = set()
        for picking in pickings:
            for move in picking.move_ids:
                product = move.product_id
                if product.id in seen_products or product.type != "product":
                    continue
                qty = move.product_uom_qty
                # bins already holding this product, with room
                holding = self.env["stock.quant"].search(
                    [
                        ("product_id", "=", product.id),
                        ("location_id", "in", bins.ids),
                        ("quantity", ">", 0),
                    ]
                ).mapped("location_id")
                target = None
                for candidate in holding:
                    free = candidate.max_capacity - qty_by_bin.get(candidate.id, 0.0)
                    if free >= qty:
                        target = candidate
                        break
                if not target:
                    fitting = bins.filtered(
                        lambda b, q=qty: b.max_capacity - qty_by_bin.get(b.id, 0.0)
                        >= q
                    )
                    if fitting:
                        target = min(
                            fitting,
                            key=lambda b: qty_by_bin.get(b.id, 0.0)
                            / b.max_capacity,
                        )
                if not target:
                    continue
                seen_products.add(product.id)
                suggestions.append(
                    {
                        "picking_id": picking.id,
                        "picking": picking.name,
                        "product": product.display_name,
                        "qty": qty,
                        "location_id": target.id,
                        "location": target.complete_name,
                    }
                )
                if len(suggestions) >= 5:
                    return suggestions
        return suggestions

    @api.model
    def _replenishment_info(self, warehouse_id=None):
        """Orderpoints below minimum; fallback to negative forecast products
        when the company uses no reordering rules."""
        Orderpoint = self.env["stock.warehouse.orderpoint"]
        domain = [("company_id", "=", self.env.company.id)]
        if warehouse_id:
            domain.append(("warehouse_id", "=", warehouse_id))
        orderpoints = Orderpoint.search(domain)
        below = orderpoints.filtered(
            lambda o: o.qty_forecast < o.product_min_qty
        )
        if orderpoints:
            return {
                "count": len(below),
                "action": {
                    "model": "stock.warehouse.orderpoint",
                    "domain": [("id", "in", below.ids)],
                    "name": "Replenishment",
                },
            }
        # no orderpoints configured: flag products forecast to go negative
        quants = self.env["stock.quant"].read_group(
            [
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", (self.env.company.id, False)),
            ],
            ["quantity:sum"],
            ["product_id"],
        )
        product_ids = [
            g["product_id"][0] for g in quants if g["quantity"] is not None
        ]
        negative_forecast = self.env["product.product"].browse(product_ids).filtered(
            lambda p: p.virtual_available < 0
        )
        return {
            "count": len(negative_forecast),
            "action": {
                "model": "product.product",
                "domain": [("id", "in", negative_forecast.ids)],
                "name": "Negative Forecast",
            },
        }

    @api.model
    def get_pick_queue(self, warehouse_id=None):
        """Today's outgoing pickings ranked by priority then deadline."""
        roles = self._picking_types_by_role(warehouse_id)
        pickings = self.env["stock.picking"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("picking_type_id", "in", roles["delivery"].ids),
                ("state", "in", ("assigned", "confirmed", "waiting")),
            ],
            order="priority desc, date_deadline asc, scheduled_date asc",
            limit=5,
        )
        rows = []
        for picking in pickings:
            deadline = picking.date_deadline or picking.scheduled_date
            rows.append(
                {
                    "id": picking.id,
                    "name": picking.name,
                    "origin": picking.origin or "",
                    "partner": picking.partner_id.display_name or "",
                    "priority": picking.priority == "1",
                    "state": picking.state,
                    "deadline": fields.Datetime.context_timestamp(
                        self, deadline
                    ).strftime("%d/%m %H:%M")
                    if deadline
                    else "",
                    "late": bool(deadline and deadline < fields.Datetime.now()),
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Today's tasks / picking progress
    # ------------------------------------------------------------------
    @api.model
    def get_tasks_today(self, warehouse_id=None):
        roles = self._picking_types_by_role(warehouse_id)
        today = fields.Date.context_today(self)
        count_done = self.env["stock.quant"].search_count(
            [
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", (self.env.company.id, False)),
                ("inventory_date", "=", today),
            ]
        )
        count_total = count_done + self.env["stock.quant"].search_count(
            [
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", (self.env.company.id, False)),
                ("inventory_date", "!=", False),
                ("inventory_date", "<", today),
            ]
        )
        tasks = [
            {"label": "Receiving", **self._count_done_total(roles["receiving"])},
            {"label": "Put Away", **self._count_done_total(roles["put_away"])},
            {"label": "Picking", **self._count_done_total(roles["picking"])},
            {"label": "Packing", **self._count_done_total(roles["packing"])},
            {"label": "Delivery", **self._count_done_total(roles["delivery"])},
            {"label": "Inventory Count", "done": count_done, "total": count_total},
        ]
        return [t for t in tasks if t["total"]]

    @api.model
    def get_picking_progress(self, warehouse_id=None):
        roles = self._picking_types_by_role(warehouse_id)
        domain = self._picking_domain_today(
            [("picking_type_id", "in", roles["delivery"].ids)]
        )
        Picking = self.env["stock.picking"]
        completed = Picking.search_count(domain + [("state", "=", "done")])
        in_progress = Picking.search_count(domain + [("state", "=", "assigned")])
        pending = Picking.search_count(
            domain + [("state", "in", ("confirmed", "waiting", "draft"))]
        )
        return {
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
        }

    # ------------------------------------------------------------------
    # Receiving today
    # ------------------------------------------------------------------
    @api.model
    def get_receiving_today(self, warehouse_id=None):
        roles = self._picking_types_by_role(warehouse_id)
        now = fields.Datetime.now()
        pickings = self.env["stock.picking"].search(
            self._picking_domain_today(
                [("picking_type_id", "in", roles["receiving"].ids)]
            ),
            order="scheduled_date",
            limit=10,
        )
        rows = []
        for picking in pickings:
            if picking.state == "done":
                status = "Received"
            elif picking.state == "assigned":
                status = "Arrived"
            elif picking.scheduled_date and picking.scheduled_date <= now:
                status = "In Transit"
            elif picking.scheduled_date and picking.scheduled_date.date() == now.date():
                status = "Pending"
            else:
                status = "Upcoming"
            rows.append(
                {
                    "id": picking.id,
                    "ref": picking.origin or picking.name,
                    "vendor": picking.partner_id.display_name or "",
                    "eta": fields.Datetime.context_timestamp(
                        self, picking.scheduled_date
                    ).strftime("%d/%m %H:%M")
                    if picking.scheduled_date
                    else "",
                    "status": status,
                }
            )
        return rows

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    @api.model
    def get_alerts(self, warehouse_id=None):
        Quant = self.env["stock.quant"]
        company_ids = (self.env.company.id, False)
        location_ids = self._internal_locations(warehouse_id).ids

        negative = Quant.search_count(
            [
                ("location_id", "in", location_ids),
                ("company_id", "in", company_ids),
                ("quantity", "<", 0),
            ]
        )
        shelf_full = len(
            self._internal_locations(warehouse_id).filtered(
                lambda l: l.max_capacity > 0 and l.occupancy_pct >= 95
            )
        )
        today = fields.Date.context_today(self)
        has_expiry = "expiration_date" in self.env["stock.lot"]._fields
        expired_lots = self.env["stock.lot"].search_count(
            [
                ("company_id", "in", company_ids),
                ("expiration_date", "!=", False),
                ("expiration_date", "<", fields.Datetime.now()),
                ("product_qty", ">", 0),
            ]
        ) if has_expiry else 0
        near_expiry_limit = fields.Datetime.now() + timedelta(days=30)
        near_expiry_lots = self.env["stock.lot"].search_count(
            [
                ("company_id", "in", company_ids),
                ("expiration_date", ">=", fields.Datetime.now()),
                ("expiration_date", "<=", near_expiry_limit),
                ("product_qty", ">", 0),
            ]
        ) if has_expiry else 0
        conflict_quants = Quant.search(
            [
                ("location_id", "in", location_ids),
                ("company_id", "in", company_ids),
                ("reserved_quantity", ">", 0),
            ]
        ).filtered(lambda q: q.reserved_quantity > q.quantity)
        conflicts = len(conflict_quants)

        alerts = [
            {
                "label": "Negative Stock",
                "count": negative,
                "severity": "danger",
                "action": {
                    "model": "stock.quant",
                    "domain": [
                        ("location_id.usage", "=", "internal"),
                        ("quantity", "<", 0),
                    ],
                },
            },
            {
                "label": "Shelf Full",
                "count": shelf_full,
                "severity": "warning",
                "action": {
                    "model": "stock.location",
                    "domain": [("usage", "=", "internal"), ("max_capacity", ">", 0)],
                },
            },
            {
                "label": "Expired Lot",
                "count": expired_lots,
                "severity": "danger",
                "action": {
                    "model": "stock.lot",
                    "domain": [("expiration_date", "<", str(today))],
                }
                if expired_lots
                else None,
            },
            {
                "label": "Near Expiry (30 วัน)",
                "count": near_expiry_lots,
                "severity": "warning",
                "action": {
                    "model": "stock.lot",
                    "domain": [
                        ("expiration_date", ">=", str(today)),
                        (
                            "expiration_date",
                            "<=",
                            str(fields.Date.context_today(self) + timedelta(days=30)),
                        ),
                    ],
                }
                if near_expiry_lots
                else None,
            },
            {
                "label": "Reservation Conflict",
                "count": conflicts,
                "severity": "warning",
                "action": {
                    "model": "stock.quant",
                    "domain": [("id", "in", conflict_quants.ids)],
                },
            },
        ]
        return [a for a in alerts if a["count"]]

    # ------------------------------------------------------------------
    # Rule-based warehouse data audit
    # ------------------------------------------------------------------
    @api.model
    def run_audit(self, warehouse_id=None):
        """On-demand data-quality audit. Returns categorized findings with
        actions to open the offending records."""
        Quant = self.env["stock.quant"]
        Picking = self.env["stock.picking"]
        company_ids = (self.env.company.id, False)
        locations = self._internal_locations(warehouse_id)
        location_ids = locations.ids
        now = fields.Datetime.now()
        findings = []

        def add(category, severity, count, description, action=None):
            if count:
                findings.append(
                    {
                        "category": category,
                        "severity": severity,
                        "count": count,
                        "description": description,
                        "action": action,
                    }
                )

        # 1. Negative stock
        negative_domain = [
            ("location_id", "in", location_ids),
            ("company_id", "in", company_ids),
            ("quantity", "<", 0),
        ]
        add(
            "Negative Stock",
            "danger",
            Quant.search_count(negative_domain),
            "Quant ติดลบ — เกิดจากการตัดสต็อกเกินหรือรับไม่ครบ",
            {"model": "stock.quant", "domain": negative_domain},
        )

        # 2. Reservation > on-hand
        conflict_quants = Quant.search(
            [
                ("location_id", "in", location_ids),
                ("company_id", "in", company_ids),
                ("reserved_quantity", ">", 0),
            ]
        ).filtered(lambda q: q.reserved_quantity > q.quantity)
        add(
            "Reservation Conflict",
            "danger",
            len(conflict_quants),
            "จองสินค้ามากกว่าของที่มีจริง",
            {"model": "stock.quant", "domain": [("id", "in", conflict_quants.ids)]},
        )

        # 3. Storage bins without capacity configured
        no_capacity = locations.filtered(
            lambda l: not l.child_ids and not l.max_capacity
        )
        add(
            "No Capacity Set",
            "info",
            len(no_capacity),
            "Location ไม่ได้ตั้ง Max Capacity — dashboard คำนวณ occupancy ไม่ได้",
            {
                "model": "stock.location",
                "domain": [("id", "in", no_capacity.ids)],
            },
        )

        # 4. Quants never counted
        never_counted_domain = [
            ("location_id", "in", location_ids),
            ("company_id", "in", company_ids),
            ("quantity", ">", 0),
            ("inventory_date", "=", False),
        ]
        add(
            "Never Counted",
            "warning",
            Quant.search_count(never_counted_domain),
            "สต็อกที่ไม่เคยกำหนดรอบนับเลย",
            {"model": "stock.quant", "domain": never_counted_domain},
        )

        # 5. Dead stock: on hand but no movement in 90 days
        active_product_ids = set()
        for group in self.env["stock.move"].read_group(
            [
                ("company_id", "=", self.env.company.id),
                ("state", "=", "done"),
                ("date", ">=", now - timedelta(days=90)),
            ],
            ["product_id"],
            ["product_id"],
        ):
            active_product_ids.add(group["product_id"][0])
        stocked = self.env["stock.quant"].read_group(
            [
                ("location_id", "in", location_ids),
                ("company_id", "in", company_ids),
                ("quantity", ">", 0),
            ],
            ["quantity:sum"],
            ["product_id"],
        )
        dead_ids = [
            g["product_id"][0]
            for g in stocked
            if g["product_id"][0] not in active_product_ids
        ]
        add(
            "Dead Stock (90 วัน)",
            "warning",
            len(dead_ids),
            "มีของค้างสต็อกแต่ไม่มี movement เกิน 90 วัน",
            {"model": "product.product", "domain": [("id", "in", dead_ids)]},
        )

        # 6. Stuck pickings (ready > 7 days)
        stuck_domain = [
            ("company_id", "=", self.env.company.id),
            ("state", "=", "assigned"),
            ("scheduled_date", "<", now - timedelta(days=7)),
        ]
        if warehouse_id:
            stuck_domain.append(("picking_type_id.warehouse_id", "=", warehouse_id))
        add(
            "Stuck Pickings",
            "warning",
            Picking.search_count(stuck_domain),
            "เอกสารพร้อมทำ (Ready) ค้างเกิน 7 วัน",
            {"model": "stock.picking", "domain": stuck_domain},
        )

        # 7. Deep backorder chains (backorder of a backorder)
        chain_domain = [
            ("company_id", "=", self.env.company.id),
            ("backorder_id.backorder_id", "!=", False),
            ("state", "not in", ("done", "cancel")),
        ]
        if warehouse_id:
            chain_domain.append(("picking_type_id.warehouse_id", "=", warehouse_id))
        add(
            "Backorder Chain",
            "warning",
            Picking.search_count(chain_domain),
            "Backorder ซ้อนกันเกิน 2 ชั้น — ควรตามของหรือยกเลิก",
            {"model": "stock.picking", "domain": chain_domain},
        )

        # 8. Over capacity
        over = locations.filtered(
            lambda l: l.max_capacity > 0 and l.occupancy_pct > 100
        )
        add(
            "Over Capacity",
            "danger",
            len(over),
            "ของจริงเกิน Max Capacity ที่ตั้งไว้",
            {"model": "stock.location", "domain": [("id", "in", over.ids)]},
        )

        return {
            "generated_at": fields.Datetime.context_timestamp(self, now).strftime(
                "%d/%m/%Y %H:%M"
            ),
            "findings": findings,
        }

    # ------------------------------------------------------------------
    # Single entry point for the frontend
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, warehouse_id=None, zone_id=None):
        warehouse_id = warehouse_id or False
        zone_id = zone_id or False
        return {
            "company": self.env.company.name,
            "is_manager": self.env.user.has_group(
                "buz_smart_warehouse.group_smart_warehouse_manager"
            ),
            "filters": self.get_filters(),
            "kpis": self.get_kpis(warehouse_id),
            "map": self.get_map_data(warehouse_id, zone_id),
            "recommendations": self.get_recommendations(warehouse_id),
            "tasks": self.get_tasks_today(warehouse_id),
            "picking_progress": self.get_picking_progress(warehouse_id),
            "pick_queue": self.get_pick_queue(warehouse_id),
            "receiving_today": self.get_receiving_today(warehouse_id),
            "alerts": self.get_alerts(warehouse_id),
        }
