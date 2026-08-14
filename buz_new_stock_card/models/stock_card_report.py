from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


DOC_TYPE_LABELS = {
    "incoming": "ใบรับสินค้า",
    "outgoing": "ใบส่งสินค้า",
    "internal": "โอนสินค้า",
    "mrp_produce": "ผลิตสินค้า",
    "mrp_consume": "เบิกวัตถุดิบผลิต",
    "inventory": "ปรับปรุงสินค้า",
    "pos": "ขายหน้าร้าน",
    "unbuild": "แยกส่วนประกอบ",
}


class StockCardReport(models.AbstractModel):
    _name = "buz.stock.card.report"
    _description = "Interactive Stock Card Calculation Engine"

    # ------------------------------------------------------------------
    # Domain / date helpers
    # ------------------------------------------------------------------

    def _scope_domain(self, scope_location_ids):
        """Moves that cross the boundary of scope_location_ids exactly once.

        Excludes moves where both source and destination are inside scope
        (net-zero from the scope's point of view) and moves that never
        touch scope at all.
        """
        scope_location_ids = list(scope_location_ids)
        return [
            "|",
            "&", ("location_dest_id", "in", scope_location_ids),
            ("location_id", "not in", scope_location_ids),
            "&", ("location_id", "in", scope_location_ids),
            ("location_dest_id", "not in", scope_location_ids),
        ]

    def _date_range_utc(self, date_from, date_to):
        """Convert user-tz Date bounds to a half-open UTC datetime interval.

        stock.move.line.date is a Datetime field; date_to must include the
        entire local day, so the upper bound is midnight of the next day.
        """
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        tz_name = self.env.user.tz or "UTC"
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC

        start_local = tz.localize(datetime.combine(date_from, time.min))
        end_local = tz.localize(datetime.combine(date_to + timedelta(days=1), time.min))

        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)
        return start_utc, end_utc

    def _to_user_tz_str(self, naive_utc_dt):
        """Format a naive UTC datetime (as returned by search_read) in the
        current user's timezone, matching the format the client expects."""
        if not naive_utc_dt:
            return naive_utc_dt
        tz_name = self.env.user.tz or "UTC"
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.UTC
        local_dt = pytz.UTC.localize(naive_utc_dt).astimezone(tz)
        return local_dt.strftime("%d/%m/%y %H:%M:%S")

    def _direction_qty(self, line_vals, scope_location_ids):
        """Return (in_qty, out_qty) for one move-line dict against scope."""
        dest_in = line_vals["location_dest_id"][0] in scope_location_ids
        src_in = line_vals["location_id"][0] in scope_location_ids
        qty = line_vals["_qty_base_uom"]
        if dest_in and not src_in:
            return qty, 0.0
        if src_in and not dest_in:
            return 0.0, qty
        return 0.0, 0.0

    def _read_lines_with_base_qty(self, domain, order=None, limit=None, offset=0):
        """search_read stock.move.line, converting quantity to product base UoM."""
        fields_ = [
            "quantity", "product_uom_id", "product_id",
            "location_id", "location_dest_id", "date",
            "picking_id", "reference", "move_id", "production_id",
        ]
        lines = self.env["stock.move.line"].search_read(
            domain, fields_, order=order, limit=limit, offset=offset
        )
        uom_obj = self.env["uom.uom"]
        product_obj = self.env["product.product"]
        for line in lines:
            src_uom = uom_obj.browse(line["product_uom_id"][0])
            product = product_obj.browse(line["product_id"][0])
            line["_qty_base_uom"] = src_uom._compute_quantity(
                line["quantity"], product.uom_id
            )
        return lines

    # ------------------------------------------------------------------
    # Opening balance
    # ------------------------------------------------------------------

    def _get_opening_balance(self, product_id, scope_location_ids, start_utc):
        domain = [
            ("state", "=", "done"),
            ("product_id", "=", product_id),
            ("date", "<", start_utc),
        ] + self._scope_domain(scope_location_ids)
        lines = self._read_lines_with_base_qty(domain)
        balance = 0.0
        for line in lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            balance += in_qty - out_qty
        return balance

    def _get_prefix_delta(self, detail_domain, order, offset, scope_location_ids):
        if offset <= 0:
            return 0.0
        lines = self._read_lines_with_base_qty(detail_domain, order=order, limit=offset)
        delta = 0.0
        for line in lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            delta += in_qty - out_qty
        return delta

    # ------------------------------------------------------------------
    # Document resolution
    # ------------------------------------------------------------------

    def _resolve_document(self, line_vals):
        """Return (doc_type_label, doc_number, res_model, res_id, source_document)."""
        picking_id = line_vals.get("picking_id")
        if picking_id:
            picking = self.env["stock.picking"].browse(picking_id[0])
            pos_order = picking.pos_order_id if "pos_order_id" in picking._fields else False
            if pos_order:
                return DOC_TYPE_LABELS["pos"], pos_order.name, "pos.order", pos_order.id, picking.origin or ""
            code = picking.picking_type_id.code
            label = {
                "incoming": DOC_TYPE_LABELS["incoming"],
                "outgoing": DOC_TYPE_LABELS["outgoing"],
                "internal": DOC_TYPE_LABELS["internal"],
            }.get(code, picking.picking_type_id.name or "")
            doc_number = picking.name
            if "buz_dispatch_document_name" in picking._fields and picking.buz_dispatch_document_name:
                doc_number = picking.buz_dispatch_document_name
            return label, doc_number, "stock.picking", picking.id, picking.origin or ""

        production_id = line_vals.get("production_id")
        if production_id:
            production = self.env["mrp.production"].browse(production_id[0])
            return (
                DOC_TYPE_LABELS["mrp_produce"], production.name, "mrp.production", production.id,
                production.origin or "",
            )

        move_id = line_vals.get("move_id")
        if move_id:
            move = self.env["stock.move"].browse(move_id[0])
            if "raw_material_production_id" in move._fields and move.raw_material_production_id:
                mo = move.raw_material_production_id
                return DOC_TYPE_LABELS["mrp_consume"], mo.name, "mrp.production", mo.id, mo.origin or ""
            if "production_id" in move._fields and move.production_id:
                mo = move.production_id
                return DOC_TYPE_LABELS["mrp_produce"], mo.name, "mrp.production", mo.id, mo.origin or ""
            if "unbuild_id" in move._fields and move.unbuild_id:
                unbuild = move.unbuild_id
                return (
                    DOC_TYPE_LABELS["unbuild"], unbuild.name, "mrp.unbuild", unbuild.id,
                    unbuild.mo_id.name or "",
                )
            if "is_inventory" in move._fields and move.is_inventory:
                name = move.reference or move.name or ""
                return DOC_TYPE_LABELS["inventory"], name, False, False, ""

        reference = line_vals.get("reference") or ""
        return "", reference, False, False, ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def get_stock_card_data(
        self, product_id, scope_location_ids, date_from, date_to,
        page_size=20, page=0, show_movements_only=False, company_ids=None,
    ):
        if not company_ids:
            company_ids = self.env.companies.ids
        scope_location_ids = list(scope_location_ids)

        start_utc, end_utc = self._date_range_utc(date_from, date_to)

        base_domain = [
            ("state", "=", "done"),
            ("product_id", "=", product_id),
            ("company_id", "in", company_ids),
        ] + self._scope_domain(scope_location_ids)

        opening_balance = self._get_opening_balance(product_id, scope_location_ids, start_utc)

        detail_domain = base_domain + [
            ("date", ">=", start_utc),
            ("date", "<", end_utc),
        ]
        if show_movements_only:
            detail_domain += [("quantity", "!=", 0)]

        order = "date, id"
        total_count = self.env["stock.move.line"].search_count(detail_domain)

        offset = page * page_size if page_size else 0
        prefix_delta = self._get_prefix_delta(detail_domain, order, offset, scope_location_ids)
        running_balance = opening_balance + prefix_delta

        limit = page_size or None
        lines = self._read_lines_with_base_qty(detail_domain, order=order, limit=limit, offset=offset)

        rows = []
        total_in = 0.0
        total_out = 0.0
        for idx, line in enumerate(lines):
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            row_opening = running_balance
            running_balance += in_qty - out_qty
            doc_type, doc_number, res_model, res_id, source_document = self._resolve_document(line)
            rows.append({
                "seq": offset + idx + 1,
                "date": self._to_user_tz_str(line["date"]),
                "doc_type": doc_type,
                "doc_number": doc_number,
                "reference": source_document,
                "res_model": res_model,
                "res_id": res_id,
                "opening": row_opening,
                "in": in_qty,
                "out": out_qty,
                "balance": running_balance,
            })
            total_in += in_qty
            total_out += out_qty

        # Totals for the whole filtered range (not just current page) are
        # derived from opening/closing so the summary cards stay correct
        # across pages: closing = opening + all_in - all_out over the range.
        all_lines = self._read_lines_with_base_qty(detail_domain, order=order)
        range_in = 0.0
        range_out = 0.0
        for line in all_lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            range_in += in_qty
            range_out += out_qty
        closing_balance = opening_balance + range_in - range_out

        return {
            "opening_balance": opening_balance,
            "closing_balance": closing_balance,
            "total_in": range_in,
            "total_out": range_out,
            "lines": rows,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "has_next": bool(page_size) and (offset + page_size) < total_count,
            "has_prev": page > 0,
        }

    @api.model
    def get_all_stock_card_lines(self, date_from, date_to, company_ids=None, show_movements_only=False):
        """Flat rows for every (product, internal location) pair that has a
        move line in the date range - one row per transaction, no per-scope
        grouping into sheets. Used when the export wizard is run with no
        product/warehouse/location selected."""
        if not company_ids:
            company_ids = self.env.companies.ids

        start_utc, end_utc = self._date_range_utc(date_from, date_to)

        location_domain = [
            ("usage", "=", "internal"),
            "|", ("company_id", "in", company_ids), ("company_id", "=", False),
        ]
        internal_location_ids = set(self.env["stock.location"].search(location_domain).ids)

        range_domain = [
            ("state", "=", "done"),
            ("company_id", "in", company_ids),
            ("date", ">=", start_utc),
            ("date", "<", end_utc),
        ]

        MoveLine = self.env["stock.move.line"]
        pairs = set()
        for field_name in ("location_id", "location_dest_id"):
            groups = MoveLine.read_group(
                range_domain + [(field_name, "in", list(internal_location_ids))],
                ["product_id", field_name], ["product_id", field_name], lazy=False,
            )
            for group in groups:
                product = group["product_id"]
                location = group[field_name]
                if product and location:
                    pairs.add((location[0], product[0]))

        Location = self.env["stock.location"]
        Product = self.env["product.product"]
        location_names = {}
        product_info = {}

        rows = []
        for location_id, product_id in pairs:
            if location_id not in location_names:
                location_names[location_id] = Location.browse(location_id).display_name
            if product_id not in product_info:
                product = Product.browse(product_id)
                product_info[product_id] = (product.default_code or "", product.name)

            scope_location_ids = [location_id]
            opening_balance = self._get_opening_balance(product_id, scope_location_ids, start_utc)

            detail_domain = [
                ("state", "=", "done"),
                ("product_id", "=", product_id),
                ("company_id", "in", company_ids),
                ("date", ">=", start_utc),
                ("date", "<", end_utc),
            ] + self._scope_domain(scope_location_ids)
            if show_movements_only:
                detail_domain += [("quantity", "!=", 0)]

            lines = self._read_lines_with_base_qty(detail_domain, order="date, id")
            running_balance = opening_balance
            for line in lines:
                in_qty, out_qty = self._direction_qty(line, scope_location_ids)
                row_opening = running_balance
                running_balance += in_qty - out_qty
                doc_type, doc_number, res_model, res_id, source_document = self._resolve_document(line)

                src_id = line["location_id"][0]
                dest_id = line["location_dest_id"][0]
                from_location = Location.browse(src_id).display_name if in_qty and src_id in internal_location_ids else ""
                to_location = Location.browse(dest_id).display_name if out_qty and dest_id in internal_location_ids else ""

                default_code, product_name = product_info[product_id]
                rows.append({
                    "location_label": location_names[location_id],
                    "product_default_code": default_code,
                    "product_name": product_name,
                    "date": self._to_user_tz_str(line["date"]),
                    "doc_type": doc_type,
                    "doc_number": doc_number,
                    "opening": row_opening,
                    "in": in_qty,
                    "out": out_qty,
                    "balance": running_balance,
                    "from_location": from_location,
                    "to_location": to_location,
                    "note": source_document,
                    "_sort_key": (location_names[location_id], default_code, line["date"], line["id"]),
                })

        rows.sort(key=lambda r: r["_sort_key"])
        for idx, row in enumerate(rows):
            row["seq"] = idx + 1
            del row["_sort_key"]
        return rows

    @api.model
    def get_location_tree(self, parent_id=None, company_ids=None):
        if not company_ids:
            company_ids = self.env.companies.ids
        domain = [
            ("usage", "in", ("internal", "view")),
            "|", ("company_id", "in", company_ids), ("company_id", "=", False),
        ]
        locations = self.env["stock.location"].search(domain, order="parent_path")
        by_parent = {}
        loc_map = {}
        for loc in locations:
            node = {
                "id": loc.id,
                "name": loc.name,
                "display_name": loc.display_name,
                "children": [],
                "move_count": 0,
                "selectable": loc.usage == "internal",
            }
            loc_map[loc.id] = node
            by_parent.setdefault(loc.location_id.id, []).append(node)

        roots = by_parent.get(parent_id or False, [])

        def attach(node):
            node["children"] = by_parent.get(node["id"], [])
            for child in node["children"]:
                attach(child)

        for root in roots:
            attach(root)

        return roots

    @api.model
    def get_warehouses(self, company_ids=None):
        if not company_ids:
            company_ids = self.env.companies.ids
        warehouses = self.env["stock.warehouse"].search([("company_id", "in", company_ids)])
        return [
            {"id": w.id, "name": w.name, "code": w.code, "view_location_id": w.view_location_id.id}
            for w in warehouses
        ]

    @api.model
    def get_product_locations_tree(self, product_id, date_from, date_to, company_ids=None, warehouse_id=None):
        """Location tree pruned to only locations relevant to this product:
        currently holding stock, or with a done movement in the date range.
        Ancestor 'view' folders are kept only to connect relevant nodes.
        """
        if not company_ids:
            company_ids = self.env.companies.ids

        start_utc, end_utc = self._date_range_utc(date_from, date_to)

        quants = self.env["stock.quant"].search_read(
            [
                ("product_id", "=", product_id),
                ("quantity", "!=", 0),
                ("location_id.usage", "=", "internal"),
                ("company_id", "in", company_ids),
            ],
            ["location_id"],
        )
        stock_location_ids = {q["location_id"][0] for q in quants}

        move_domain = [
            ("state", "=", "done"),
            ("product_id", "=", product_id),
            ("date", ">=", start_utc),
            ("date", "<", end_utc),
            ("company_id", "in", company_ids),
        ]
        move_counts = {}
        MoveLine = self.env["stock.move.line"]
        for field_name in ("location_id", "location_dest_id"):
            groups = MoveLine.read_group(move_domain, [field_name], [field_name])
            for group in groups:
                loc = group[field_name]
                if not loc:
                    continue
                loc_id = loc[0]
                move_counts[loc_id] = move_counts.get(loc_id, 0) + group[f"{field_name}_count"]

        relevant_ids = stock_location_ids | set(move_counts.keys())

        warehouse_view_location = False
        domain = [
            ("usage", "in", ("internal", "view")),
            "|", ("company_id", "in", company_ids), ("company_id", "=", False),
        ]
        if warehouse_id:
            warehouse_view_location = self.env["stock.warehouse"].browse(warehouse_id).view_location_id
            domain += [("id", "child_of", warehouse_view_location.id)]
        locations = self.env["stock.location"].search(domain, order="parent_path")
        by_parent = {}
        loc_map = {}
        for loc in locations:
            node = {
                "id": loc.id,
                "name": loc.name,
                "display_name": loc.display_name,
                "children": [],
                "move_count": move_counts.get(loc.id, 0),
                "selectable": loc.usage == "internal",
            }
            loc_map[loc.id] = node
            by_parent.setdefault(loc.location_id.id, []).append(node)

        root_key = warehouse_view_location.location_id.id if warehouse_view_location else False

        def build(parent_key):
            result = []
            for node in by_parent.get(parent_key, []):
                node["children"] = build(node["id"])
                if node["id"] in relevant_ids or node["children"]:
                    result.append(node)
            return result

        return build(root_key)

    @api.model
    def get_location_move_counts(self, location_ids, date_from, date_to, company_ids=None):
        if not location_ids:
            return {}
        if not company_ids:
            company_ids = self.env.companies.ids

        start_utc, end_utc = self._date_range_utc(date_from, date_to)
        base_domain = [
            ("state", "=", "done"),
            ("date", ">=", start_utc),
            ("date", "<", end_utc),
            ("company_id", "in", company_ids),
        ]

        counts = {}
        MoveLine = self.env["stock.move.line"]

        out_groups = MoveLine.read_group(
            base_domain + [("location_id", "in", location_ids)],
            ["location_id"], ["location_id"],
        )
        for group in out_groups:
            loc_id = group["location_id"][0]
            counts[loc_id] = counts.get(loc_id, 0) + group["location_id_count"]

        in_groups = MoveLine.read_group(
            base_domain + [("location_dest_id", "in", location_ids)],
            ["location_dest_id"], ["location_dest_id"],
        )
        for group in in_groups:
            loc_id = group["location_dest_id"][0]
            counts[loc_id] = counts.get(loc_id, 0) + group["location_dest_id_count"]

        return counts

    @api.model
    def resolve_multi_location_scope(self, location_ids=None, warehouse_ids=None):
        """Combine explicit locations and whole warehouses into one scope."""
        ids = set()
        Location = self.env["stock.location"]
        for loc_id in location_ids or []:
            location = Location.browse(loc_id)
            if location.exists():
                ids.add(location.id)
        for wh_id in warehouse_ids or []:
            warehouse = self.env["stock.warehouse"].browse(wh_id)
            if warehouse.exists():
                ids |= set(Location.search(
                    [("id", "child_of", warehouse.view_location_id.id), ("usage", "=", "internal")]
                ).ids)
        return list(ids)

    @api.model
    def resolve_location_scope(self, location_id, include_children):
        location = self.env["stock.location"].browse(location_id)
        if not location.exists():
            return []
        if include_children:
            return self.env["stock.location"].search(
                [("id", "child_of", location.id)]
            ).ids
        return [location.id]
