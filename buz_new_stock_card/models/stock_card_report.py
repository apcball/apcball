from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import html2plaintext


GROUP_SEE_VALUE = "buz_new_stock_card.group_stock_card_see_value"

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
            "picking_id", "reference", "move_id",
        ]
        if "production_id" in self.env["stock.move.line"]._fields:
            fields_.append("production_id")
        lines = self.env["stock.move.line"].search_read(
            domain, fields_, order=order, limit=limit, offset=offset
        )
        if not lines:
            return lines

        # Batch: one browse for every UoM / product touched, instead of one
        # browse per line (this method is called once per product in the
        # scoped multi-product export - the per-line N+1 does not scale).
        uom_ids = {line["product_uom_id"][0] for line in lines if line["product_uom_id"]}
        product_ids = {line["product_id"][0] for line in lines if line["product_id"]}
        uoms = self.env["uom.uom"].browse(list(uom_ids))
        products = self.env["product.product"].browse(list(product_ids))
        uom_map = {uom.id: uom for uom in uoms}
        product_uom_map = {product.id: product.uom_id for product in products}

        for line in lines:
            src_uom = uom_map.get(line["product_uom_id"][0])
            target_uom = product_uom_map.get(line["product_id"][0])
            if src_uom and target_uom:
                line["_qty_base_uom"] = src_uom._compute_quantity(
                    line["quantity"], target_uom
                )
            else:
                line["_qty_base_uom"] = line["quantity"]
        return lines

    # ------------------------------------------------------------------
    # Opening balance
    # ------------------------------------------------------------------

    def _get_opening_balance(self, product_id, scope_location_ids, start_utc, company_ids=None):
        domain = [
            ("state", "=", "done"),
            ("product_id", "=", product_id),
            ("date", "<", start_utc),
            ("company_id", "in", company_ids or self.env.companies.ids),
        ] + self._scope_domain(scope_location_ids)
        lines = self._read_lines_with_base_qty(domain)
        balance = 0.0
        for line in lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            balance += in_qty - out_qty
        return balance

    def _get_opening_balances_by_product(self, product_ids, scope_location_ids, start_utc, company_ids):
        """Opening balance for many products at once: one search_read over all
        pre-range done moves that cross the scope boundary, aggregated per
        product in Python (keeps the base-UoM conversion the single-product
        path uses, without a query per product)."""
        if not product_ids:
            return {}
        domain = [
            ("state", "=", "done"),
            ("product_id", "in", list(product_ids)),
            ("company_id", "in", company_ids),
            ("date", "<", start_utc),
        ] + self._scope_domain(scope_location_ids)
        lines = self._read_lines_with_base_qty(domain)
        balances = dict.fromkeys(product_ids, 0.0)
        for line in lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            balances[line["product_id"][0]] = balances.get(line["product_id"][0], 0.0) + in_qty - out_qty
        return balances

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
    # Value ledger (มูลค่าสินค้า running balance)
    #
    # Reuses stock.valuation.layer.value (already signed/computed by Odoo)
    # instead of re-deriving unit cost per move line. A single stock.move can
    # carry two layers sharing one stock_move_id (an internal transfer with a
    # cost change books a negative out-leg + a positive in-leg), so value is
    # looked up per (move, direction) - never netted by move id alone. Gated
    # behind GROUP_SEE_VALUE and omitted entirely (not zeroed) for everyone
    # else - see security/security.xml.
    #
    # Period bucketing uses accounting_date (fallback create_date), matching
    # stock_fifo_valuation_report's ACCOUNTING_DATE_CTE, so opening values
    # agree with that report - EXCEPT where a layer's location_id (scoped
    # here, for sub-warehouse granularity) disagrees with its warehouse_id
    # (that report's scope key). That disagreement is a pre-existing data
    # defect on some layers, not something either report gets wrong on its
    # own - see project memory "type105-int-moveline-header-mismatch"; not
    # fixed here.
    # ------------------------------------------------------------------

    def _can_see_value(self):
        return self.env.user.has_group(GROUP_SEE_VALUE)

    def _accounting_date_before_domain(self, cutoff):
        """Layers whose accounting_date - falling back to create_date when
        null - is before `cutoff`. Matches stock_fifo_valuation_report's
        ACCOUNTING_DATE_CTE: accounting_date (not stock_move_id.date, not
        create_date) is the period-bucketing date, so a backdated move lands
        in the same period here as it does on that report."""
        return [
            "|",
            ("accounting_date", "<", cutoff),
            "&", ("accounting_date", "=", False), ("create_date", "<", cutoff),
        ]

    def _get_opening_value(self, product_id, scope_location_ids, start_utc, company_ids):
        Layer = self.env["stock.valuation.layer"]
        domain = [
            ("product_id", "=", product_id),
            ("location_id", "in", list(scope_location_ids)),
            ("company_id", "in", company_ids),
        ] + self._accounting_date_before_domain(start_utc)
        return sum(Layer.search(domain).mapped("value"))

    def _get_opening_values_by_product(self, product_ids, scope_location_ids, start_utc, company_ids):
        """Opening value for many products sharing the same scope at once -
        bulk analogue of _get_opening_value, mirroring
        _get_opening_balances_by_product."""
        if not product_ids:
            return {}
        Layer = self.env["stock.valuation.layer"]
        domain = [
            ("product_id", "in", list(product_ids)),
            ("location_id", "in", list(scope_location_ids)),
            ("company_id", "in", company_ids),
        ] + self._accounting_date_before_domain(start_utc)
        values = dict.fromkeys(product_ids, 0.0)
        for group in Layer.read_group(domain, ["value:sum"], ["product_id"]):
            product = group.get("product_id")
            if product:
                values[product[0]] = group["value"]
        return values

    def _get_value_deltas_by_move(self, move_ids, scope_location_ids, company_ids):
        """(value_in_by_move, value_out_by_move) dicts: signed layer value
        summed per stock_move_id, split by direction (quantity > 0 / < 0) so a
        move with a matched in/out layer pair keeps both legs distinct."""
        if not move_ids:
            return {}, {}
        Layer = self.env["stock.valuation.layer"]
        base_domain = [
            ("stock_move_id", "in", list(move_ids)),
            ("location_id", "in", list(scope_location_ids)),
            ("company_id", "in", company_ids),
        ]
        value_in_by_move = {}
        for group in Layer.read_group(base_domain + [("quantity", ">", 0)], ["value:sum"], ["stock_move_id"]):
            move = group.get("stock_move_id")
            if move:
                value_in_by_move[move[0]] = value_in_by_move.get(move[0], 0.0) + group["value"]
        value_out_by_move = {}
        for group in Layer.read_group(base_domain + [("quantity", "<", 0)], ["value:sum"], ["stock_move_id"]):
            move = group.get("stock_move_id")
            if move:
                value_out_by_move[move[0]] = value_out_by_move.get(move[0], 0.0) + abs(group["value"])
        return value_in_by_move, value_out_by_move

    def _get_move_qty_totals(self, lines, scope_location_ids):
        """(move_in_qty, move_out_qty) dicts: total in/out base-uom qty per
        move id across `lines` - the pro-rata denominator for splitting a
        move's layer value across its (possibly multi-lot) move lines. Must
        be built from the full move-line set for the domain in play, never
        from a single page, or a move split across a page boundary gets
        inconsistent shares."""
        move_in_qty, move_out_qty = {}, {}
        for line in lines:
            move_id = line["move_id"][0] if line.get("move_id") else None
            if not move_id:
                continue
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            if in_qty:
                move_in_qty[move_id] = move_in_qty.get(move_id, 0.0) + in_qty
            if out_qty:
                move_out_qty[move_id] = move_out_qty.get(move_id, 0.0) + out_qty
        return move_in_qty, move_out_qty

    def _line_value_delta(self, line, scope_location_ids, value_context):
        """Signed value delta for one move-line row, pro-rated from its
        move's layer value by this line's share of the move's total in/out
        qty (value_context = {value_in_by_move, value_out_by_move,
        move_in_qty, move_out_qty})."""
        move_id = line["move_id"][0] if line.get("move_id") else None
        if not move_id:
            return 0.0
        in_qty, out_qty = self._direction_qty(line, scope_location_ids)
        if in_qty:
            total_qty = value_context["move_in_qty"].get(move_id) or 0.0
            if not total_qty:
                return 0.0
            return value_context["value_in_by_move"].get(move_id, 0.0) * (in_qty / total_qty)
        if out_qty:
            total_qty = value_context["move_out_qty"].get(move_id) or 0.0
            if not total_qty:
                return 0.0
            return -(value_context["value_out_by_move"].get(move_id, 0.0) * (out_qty / total_qty))
        return 0.0

    def _get_prefix_value(
        self, detail_domain, order, offset, scope_location_ids, value_context,
    ):
        if offset <= 0:
            return 0.0
        lines = self._read_lines_with_base_qty(detail_domain, order=order, limit=offset)
        return sum(self._line_value_delta(line, scope_location_ids, value_context) for line in lines)

    # ------------------------------------------------------------------
    # Document resolution
    # ------------------------------------------------------------------

    def _prefetch_documents(self, lines):
        """Warm the ORM cache for every picking / production / move referenced
        by ``lines`` so the per-line _resolve_document calls do not each fire
        their own browse (matters for the multi-product scoped export)."""
        picking_ids = {l["picking_id"][0] for l in lines if l.get("picking_id")}
        production_ids = {l["production_id"][0] for l in lines if l.get("production_id")}
        move_ids = {l["move_id"][0] for l in lines if l.get("move_id")}
        if picking_ids:
            self.env["stock.picking"].browse(list(picking_ids)).mapped("picking_type_id")
        if production_ids:
            self.env["mrp.production"].browse(list(production_ids)).mapped("name")
        if move_ids:
            self.env["stock.move"].browse(list(move_ids)).mapped("reference")

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
    def resolve_report_scope(self, company_id, warehouse_ids=None, location_ids=None, include_children=True):
        """Validate and resolve the same scope for the screen and Excel."""
        if company_id not in self.env.companies.ids:
            raise AccessError("บริษัทที่เลือกไม่อยู่ในบริษัทที่อนุญาต")
        warehouses = self.env["stock.warehouse"].search([
            ("company_id", "=", company_id),
        ] + ([("id", "in", warehouse_ids)] if warehouse_ids else []))
        if warehouse_ids and set(warehouses.ids) != set(warehouse_ids):
            raise ValidationError("คลังสินค้าไม่อยู่ในบริษัทที่เลือก")
        Location = self.env["stock.location"]
        warehouse_domain = [("id", "child_of", warehouses.mapped("view_location_id").ids)]
        company_domain = [("company_id", "in", [False, company_id])]
        if location_ids:
            locations = Location.search([
                ("id", "in", location_ids), ("usage", "in", ["view", "internal"]),
            ] + company_domain + warehouse_domain)
            if set(locations.ids) != set(location_ids):
                raise ValidationError("Location ไม่อยู่ในคลังสินค้าและบริษัทที่เลือก")
            scope_domain = [("id", "child_of" if include_children else "in", locations.ids)]
            label = ", ".join(locations.mapped("display_name"))
        else:
            scope_domain = warehouse_domain
            label = ", ".join(warehouses.mapped("name")) if warehouse_ids else "คลังสินค้าทั้งหมด"
        scope = Location.search(scope_domain + company_domain + [("usage", "=", "internal")])
        return {"location_ids": scope.ids, "label": label}

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

        opening_balance = self._get_opening_balance(product_id, scope_location_ids, start_utc, company_ids)

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
        self._prefetch_documents(lines)

        # Value ledger: full-range move-line set is needed up front to build
        # the pro-rata denominators (_get_move_qty_totals) correctly - a move
        # split across a page boundary must not get inconsistent shares per
        # page. Also reused below for the qty range totals, so only one
        # unlimited fetch happens regardless of group membership.
        can_see_value = self._can_see_value()
        all_lines = self._read_lines_with_base_qty(detail_domain, order=order)
        if all_lines is not lines:
            self._prefetch_documents(all_lines)

        value_context = None
        opening_value = 0.0
        running_value = 0.0
        if can_see_value:
            move_ids = {l["move_id"][0] for l in all_lines if l.get("move_id")}
            value_in_by_move, value_out_by_move = self._get_value_deltas_by_move(
                move_ids, scope_location_ids, company_ids,
            )
            move_in_qty, move_out_qty = self._get_move_qty_totals(all_lines, scope_location_ids)
            value_context = {
                "value_in_by_move": value_in_by_move,
                "value_out_by_move": value_out_by_move,
                "move_in_qty": move_in_qty,
                "move_out_qty": move_out_qty,
            }
            opening_value = self._get_opening_value(product_id, scope_location_ids, start_utc, company_ids)
            prefix_value = self._get_prefix_value(detail_domain, order, offset, scope_location_ids, value_context)
            running_value = opening_value + prefix_value

        rows = []
        total_in = 0.0
        total_out = 0.0
        for idx, line in enumerate(lines):
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            row_opening = running_balance
            running_balance += in_qty - out_qty
            doc_type, doc_number, res_model, res_id, source_document = self._resolve_document(line)
            row = {
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
                "location_name": line["location_dest_id"][1] if in_qty else line["location_id"][1],
            }
            if can_see_value:
                delta = self._line_value_delta(line, scope_location_ids, value_context)
                running_value += delta
                row["value"] = running_value
                row["value_in"] = delta if delta >= 0 else 0.0
                row["value_out"] = -delta if delta < 0 else 0.0
            rows.append(row)
            total_in += in_qty
            total_out += out_qty

        # Totals for the whole filtered range (not just current page) are
        # derived from opening/closing so the summary cards stay correct
        # across pages: closing = opening + all_in - all_out over the range.
        range_in = 0.0
        range_out = 0.0
        range_in_value = 0.0
        range_out_value = 0.0
        for line in all_lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            range_in += in_qty
            range_out += out_qty
            if can_see_value:
                delta = self._line_value_delta(line, scope_location_ids, value_context)
                if delta >= 0:
                    range_in_value += delta
                else:
                    range_out_value += -delta
        closing_balance = opening_balance + range_in - range_out

        result = {
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
            "can_see_value": can_see_value,
        }
        if can_see_value:
            result.update({
                "opening_value": opening_value,
                "closing_value": opening_value + range_in_value - range_out_value,
                "total_in_value": range_in_value,
                "total_out_value": range_out_value,
            })
        return result

    def _build_product_scope_rows(
        self, scope_location_ids, product_id, opening_balance,
        start_utc, end_utc, company_ids, show_movements_only,
        internal_location_ids, location_label, default_code, product_name,
        include_value=False, opening_value=0.0,
    ):
        """Flat ledger rows for one product over one scope (a list of location
        ids). Shared by get_all_stock_card_lines (scope = one location) and
        get_scoped_stock_card_lines (scope = a whole warehouse/location).

        include_value=True adds a "value" (running มูลค่าสินค้า) key to each
        row, computed from stock.valuation.layer - caller must have already
        checked GROUP_SEE_VALUE (see _can_see_value)."""
        Location = self.env["stock.location"]
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
        self._prefetch_documents(lines)

        # Batch the counterpart-location names (one browse, not one per row).
        counterpart_ids = set()
        for line in lines:
            counterpart_ids.add(line["location_id"][0])
            counterpart_ids.add(line["location_dest_id"][0])
        loc_names = {
            loc.id: loc.display_name
            for loc in Location.browse(list(counterpart_ids))
        }

        value_context = None
        running_value = opening_value
        if include_value:
            move_ids = {l["move_id"][0] for l in lines if l.get("move_id")}
            value_in_by_move, value_out_by_move = self._get_value_deltas_by_move(
                move_ids, scope_location_ids, company_ids,
            )
            move_in_qty, move_out_qty = self._get_move_qty_totals(lines, scope_location_ids)
            value_context = {
                "value_in_by_move": value_in_by_move,
                "value_out_by_move": value_out_by_move,
                "move_in_qty": move_in_qty,
                "move_out_qty": move_out_qty,
            }

        rows = []
        running_balance = opening_balance
        for line in lines:
            in_qty, out_qty = self._direction_qty(line, scope_location_ids)
            row_opening = running_balance
            running_balance += in_qty - out_qty
            doc_type, doc_number, _res_model, _res_id, source_document = self._resolve_document(line)

            src_id = line["location_id"][0]
            dest_id = line["location_dest_id"][0]
            from_location = loc_names.get(src_id, "") if in_qty and src_id in internal_location_ids else ""
            to_location = loc_names.get(dest_id, "") if out_qty and dest_id in internal_location_ids else ""

            row = {
                "location_label": location_label,
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
                "_sort_key": (location_label, default_code or "", product_name or "", str(line["date"]), line["id"]),
            }
            if include_value:
                delta = self._line_value_delta(line, scope_location_ids, value_context)
                running_value += delta
                row["value"] = running_value
                row["value_in"] = delta if delta >= 0 else 0.0
                row["value_out"] = -delta if delta < 0 else 0.0
            rows.append(row)
        return rows, running_balance

    @api.model
    def get_all_stock_card_lines(self, date_from, date_to, company_ids=None, show_movements_only=False):
        """Flat rows for every (product, internal location) pair that has a
        move line in the date range - one row per transaction, no per-scope
        grouping into sheets. Used when the export wizard is run with no
        product/warehouse/location selected."""
        if not company_ids:
            company_ids = self.env.companies.ids
        can_see_value = self._can_see_value()

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

        # Group pairs by location so the opening balance/value for every
        # product sharing that location is fetched with one bulk query
        # (_get_opening_balances_by_product / _get_opening_values_by_product)
        # instead of one query per (location, product) pair - the pair count
        # can run into the thousands on a no-filter export-all.
        pairs_by_location = {}
        for location_id, product_id in pairs:
            pairs_by_location.setdefault(location_id, set()).add(product_id)

        all_product_ids = {product_id for _loc, product_id in pairs}
        location_names = {
            loc.id: loc.display_name for loc in Location.browse(list(pairs_by_location.keys()))
        }
        product_info = {
            p.id: (p.default_code or "", p.name) for p in Product.browse(list(all_product_ids))
        }

        rows = []
        for location_id, product_ids in pairs_by_location.items():
            scope_location_ids = [location_id]
            opening_by_product = self._get_opening_balances_by_product(
                product_ids, scope_location_ids, start_utc, company_ids,
            )
            opening_value_by_product = (
                self._get_opening_values_by_product(product_ids, scope_location_ids, start_utc, company_ids)
                if can_see_value else {}
            )
            for product_id in product_ids:
                default_code, product_name = product_info[product_id]
                product_rows, _closing = self._build_product_scope_rows(
                    scope_location_ids, product_id, opening_by_product.get(product_id, 0.0),
                    start_utc, end_utc, company_ids, show_movements_only,
                    internal_location_ids, location_names[location_id],
                    default_code, product_name,
                    include_value=can_see_value,
                    opening_value=opening_value_by_product.get(product_id, 0.0),
                )
                rows.extend(product_rows)

        rows.sort(key=lambda r: r["_sort_key"])
        for idx, row in enumerate(rows):
            row["seq"] = idx + 1
            del row["_sort_key"]
        return rows

    @api.model
    def get_product_all_locations_lines(
        self, product_id, date_from, date_to,
        company_ids=None, show_movements_only=False,
    ):
        """Flat rows for one product across every internal location where it has
        a done move in the date range OR currently holds non-zero qty. One sheet,
        one row per transaction, grouped/sorted by location (same row shape as
        ``get_all_stock_card_lines``). Used when the export wizard is run with a
        product but no warehouse/location."""
        if not company_ids:
            company_ids = self.env.companies.ids
        can_see_value = self._can_see_value()

        start_utc, end_utc = self._date_range_utc(date_from, date_to)

        internal_location_ids = set(self.env["stock.location"].search([
            ("usage", "=", "internal"),
            "|", ("company_id", "in", company_ids), ("company_id", "=", False),
        ]).ids)

        MoveLine = self.env["stock.move.line"]
        range_domain = [
            ("state", "=", "done"),
            ("product_id", "=", product_id),
            ("company_id", "in", company_ids),
            ("date", ">=", start_utc),
            ("date", "<", end_utc),
        ]
        moved_location_ids = set()
        for field_name in ("location_id", "location_dest_id"):
            groups = MoveLine.read_group(
                range_domain + [(field_name, "in", list(internal_location_ids))],
                [field_name], [field_name],
            )
            for group in groups:
                loc = group[field_name]
                if loc:
                    moved_location_ids.add(loc[0])

        onhand_location_ids = {
            q["location_id"][0]
            for q in self.env["stock.quant"].search_read([
                ("product_id", "=", product_id),
                ("quantity", "!=", 0),
                ("location_id", "in", list(internal_location_ids)),
                ("company_id", "in", company_ids),
            ], ["location_id"])
            if q["location_id"]
        }

        location_ids = moved_location_ids | onhand_location_ids
        if not location_ids:
            return []

        product = self.env["product.product"].browse(product_id)
        default_code, product_name = product.default_code or "", product.name
        Location = self.env["stock.location"]
        location_names = {
            loc.id: loc.display_name for loc in Location.browse(list(location_ids))
        }

        rows = []
        for location_id in location_ids:
            scope_location_ids = [location_id]
            location_label = location_names[location_id]
            opening_balance = self._get_opening_balance(
                product_id, scope_location_ids, start_utc, company_ids,
            )
            opening_value = (
                self._get_opening_value(product_id, scope_location_ids, start_utc, company_ids)
                if can_see_value else 0.0
            )
            product_rows, _closing = self._build_product_scope_rows(
                scope_location_ids, product_id, opening_balance,
                start_utc, end_utc, company_ids, show_movements_only,
                internal_location_ids, location_label, default_code, product_name,
                include_value=can_see_value, opening_value=opening_value,
            )
            if product_rows:
                rows.extend(product_rows)
            elif not show_movements_only:
                marker_row = {
                    "location_label": location_label,
                    "product_default_code": default_code,
                    "product_name": product_name,
                    "date": "",
                    "doc_type": "",
                    "doc_number": "",
                    "opening": opening_balance,
                    "in": 0.0,
                    "out": 0.0,
                    "balance": opening_balance,
                    "from_location": "",
                    "to_location": "",
                    "note": "",
                    "_sort_key": (location_label, default_code or "", product_name or "", "", 0),
                }
                if can_see_value:
                    marker_row["value"] = opening_value
                rows.append(marker_row)

        rows.sort(key=lambda r: r["_sort_key"])
        for idx, row in enumerate(rows):
            row["seq"] = idx + 1
            del row["_sort_key"]
        return rows

    @api.model
    def get_scoped_stock_card_lines(
        self, scope_location_ids, date_from, date_to, scope_label=None,
        company_ids=None, show_movements_only=False,
    ):
        """Flat rows for every product that moved through ``scope_location_ids``
        in the date range OR currently holds non-zero qty there. One row per
        transaction; products with stock but no movement in range get a single
        opening=closing row. Used when the export wizard is run with a
        warehouse/location but no product."""
        if not company_ids:
            company_ids = self.env.companies.ids
        can_see_value = self._can_see_value()
        scope_location_ids = list(scope_location_ids)
        if not scope_location_ids:
            return []

        start_utc, end_utc = self._date_range_utc(date_from, date_to)
        internal_location_ids = set(self.env["stock.location"].search([
            ("usage", "=", "internal"),
            "|", ("company_id", "in", company_ids), ("company_id", "=", False),
        ]).ids)

        MoveLine = self.env["stock.move.line"]
        range_domain = [
            ("state", "=", "done"),
            ("company_id", "in", company_ids),
            ("date", ">=", start_utc),
            ("date", "<", end_utc),
        ] + self._scope_domain(scope_location_ids)

        moved_product_ids = {
            g["product_id"][0]
            for g in MoveLine.read_group(range_domain, ["product_id"], ["product_id"])
            if g["product_id"]
        }
        onhand_product_ids = {
            q["product_id"][0]
            for q in self.env["stock.quant"].search_read([
                ("location_id", "in", scope_location_ids),
                ("quantity", "!=", 0),
                ("company_id", "in", company_ids),
            ], ["product_id"])
            if q["product_id"]
        }
        product_ids = moved_product_ids | onhand_product_ids
        if not product_ids:
            return []

        opening_by_product = self._get_opening_balances_by_product(
            product_ids, scope_location_ids, start_utc, company_ids,
        )
        opening_value_by_product = (
            self._get_opening_values_by_product(product_ids, scope_location_ids, start_utc, company_ids)
            if can_see_value else {}
        )

        Product = self.env["product.product"]
        products = Product.browse(list(product_ids))
        product_info = {p.id: (p.default_code or "", p.name) for p in products}
        label = scope_label or ""

        rows = []
        for product_id in product_ids:
            default_code, product_name = product_info.get(product_id, ("", ""))
            opening_balance = opening_by_product.get(product_id, 0.0)
            opening_value = opening_value_by_product.get(product_id, 0.0)
            product_rows, _closing = self._build_product_scope_rows(
                scope_location_ids, product_id, opening_balance,
                start_utc, end_utc, company_ids, show_movements_only,
                internal_location_ids, label, default_code, product_name,
                include_value=can_see_value, opening_value=opening_value,
            )
            if product_rows:
                rows.extend(product_rows)
            elif not show_movements_only:
                # No movement in range: single marker row so the product still
                # appears on the sheet. With no in-range lines, closing == opening.
                marker_row = {
                    "location_label": label,
                    "product_default_code": default_code,
                    "product_name": product_name,
                    "date": "",
                    "doc_type": "",
                    "doc_number": "",
                    "opening": opening_balance,
                    "in": 0.0,
                    "out": 0.0,
                    "balance": opening_balance,
                    "from_location": "",
                    "to_location": "",
                    "note": "",
                    "_sort_key": (label, default_code or "", product_name or "", "", 0),
                }
                if can_see_value:
                    marker_row["value"] = opening_value
                rows.append(marker_row)

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
        else:
            warehouse_roots = self.env["stock.warehouse"].search([
                ("company_id", "in", company_ids),
            ]).mapped("view_location_id")
            domain += [("id", "child_of", warehouse_roots.ids)]
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

        if warehouse_view_location:
            return build(root_key)
        roots = []
        for parent_id in by_parent:
            if parent_id not in loc_map:
                roots.extend(build(parent_id))
        return roots

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
                ids |= set(Location.search(
                    [("id", "child_of", location.id), ("usage", "=", "internal")]
                ).ids)
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

    # ------------------------------------------------------------------
    # Valuation (cost + lot) ledger
    #
    # Reads stock.valuation.layer directly instead of stock.move.line: the
    # stock_by_locations module already splits every move into a
    # location-scoped IN/OUT layer carrying real unit_cost/value, which is a
    # much better cost source than re-deriving cost from move lines. Opening
    # balance is decomposed into still-outstanding FIFO layers (one row per
    # layer), matching the pattern in buz_stock_card_report's
    # _get_open_document_rows. remaining_qty reflects the layer's *current*
    # remaining quantity, not a snapshot as-of date_from - same known
    # simplification buz_stock_card_report already accepts.
    # ------------------------------------------------------------------

    def _resolve_layer_lot_splits(self, layer, layer_qty):
        """Split layer_qty across the lots on its move, proportional to each
        move line's share of quantity. Returns [(lot_name, qty), ...]."""
        move = layer.stock_move_id
        if not move:
            return [("", layer_qty)]
        lines = move.move_line_ids.filtered(
            lambda l: l.product_id.id == layer.product_id.id
        )
        if not lines:
            return [("", layer_qty)]
        if len(lines) == 1:
            return [(lines.lot_id.name or "", layer_qty)]
        total_qty = sum(lines.mapped("quantity"))
        if not total_qty:
            return [("", layer_qty)]
        return [
            (line.lot_id.name or "", layer_qty * (line.quantity / total_qty))
            for line in lines
        ]

    def _valuation_rows_for_layer(self, layer, layer_qty, fallback_remark):
        move = layer.stock_move_id
        unit_cost = layer.unit_cost
        line_vals = {
            "picking_id": (move.picking_id.id, "") if move and move.picking_id else False,
            "move_id": (move.id, "") if move else False,
            "reference": (move.reference if move else "") or layer.description or "",
        }
        doc_type, doc_number, _res_model, _res_id, _source = self._resolve_document(line_vals)
        sort_dt = move.date if move and move.date else datetime(1970, 1, 1)
        date_str = self._to_user_tz_str(move.date) if move and move.date else ""
        product = layer.product_id
        # หมายเหตุ: the picking's own note, when there is one - falls back to
        # the opening/receipt/issue label when there's no picking or no note.
        picking_note = (
            html2plaintext(move.picking_id.note).strip()
            if move and move.picking_id and move.picking_id.note else ""
        )
        remark = picking_note or fallback_remark

        rows = []
        for lot_name, qty in self._resolve_layer_lot_splits(layer, layer_qty):
            row = {
                "product_default_code": product.default_code or "",
                "product_name": product.name,
                "lot_name": lot_name,
                "warehouse_name": layer.location_id.warehouse_id.name or "",
                "location_label": layer.location_id.display_name,
                "doc_type": doc_type,
                "doc_number": doc_number,
                "date": date_str,
                "qty_in": 0.0, "unitcost_in": 0.0, "cost_in": 0.0,
                "qty_out": 0.0, "unitcost_out": 0.0, "cost_out": 0.0,
                "remark": remark,
                "_sort_dt": sort_dt,
            }
            if qty >= 0:
                row["qty_in"] = qty
                row["unitcost_in"] = unit_cost
                row["cost_in"] = qty * unit_cost
            else:
                row["qty_out"] = -qty
                row["unitcost_out"] = unit_cost
                row["cost_out"] = -qty * unit_cost
            rows.append(row)
        return rows

    def _get_opening_valuation_rows(self, product_id, scope_location_ids, date_from, company_ids):
        Layer = self.env["stock.valuation.layer"]
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        domain = [
            ("product_id", "=", product_id),
            ("location_id", "in", list(scope_location_ids)),
            ("company_id", "in", company_ids),
            ("remaining_qty", ">", 0),
            ("stock_move_id.date", "<", date_from),
        ]
        layers = Layer.search(domain, order="create_date, id")
        rows = []
        for layer in layers:
            rows.extend(self._valuation_rows_for_layer(layer, layer.remaining_qty, "ยอดยกมา"))
        return rows

    def _get_period_valuation_rows(self, product_id, scope_location_ids, date_from, date_to, company_ids):
        Layer = self.env["stock.valuation.layer"]
        start_utc, end_utc = self._date_range_utc(date_from, date_to)
        domain = [
            ("product_id", "=", product_id),
            ("location_id", "in", list(scope_location_ids)),
            ("company_id", "in", company_ids),
            ("stock_move_id.date", ">=", start_utc),
            ("stock_move_id.date", "<", end_utc),
        ]
        layers = Layer.search(domain)
        rows = []
        for layer in layers:
            if layer.quantity > 0:
                rows.extend(self._valuation_rows_for_layer(layer, layer.quantity, "เอกสารรับในปี"))
            elif layer.quantity < 0:
                rows.extend(self._valuation_rows_for_layer(layer, layer.quantity, "เอกสารจ่ายในปี"))
        return rows

    def _product_scope_valuation_rows(self, product_id, scope_location_ids, date_from, date_to, company_ids):
        opening_rows = self._get_opening_valuation_rows(product_id, scope_location_ids, date_from, company_ids)
        period_rows = self._get_period_valuation_rows(product_id, scope_location_ids, date_from, date_to, company_ids)
        return opening_rows + period_rows

    def _get_valuation_layers_bulk(self, product_ids, location_ids, date_from, date_to, company_ids):
        """Opening (still-outstanding) and in-period layers for the full
        product_ids x location_ids id sets, in 2 queries total - grouped by
        (location_id, product_id) in Python - instead of one opening query +
        one period query per product or per location in a loop. Mirrors the
        domains of _get_opening_valuation_rows / _get_period_valuation_rows."""
        Layer = self.env["stock.valuation.layer"]
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        start_utc, end_utc = self._date_range_utc(date_from, date_to)
        product_ids = list(product_ids)
        location_ids = list(location_ids)

        opening_layers = Layer.search([
            ("product_id", "in", product_ids),
            ("location_id", "in", location_ids),
            ("company_id", "in", company_ids),
            ("remaining_qty", ">", 0),
            ("stock_move_id.date", "<", date_from),
        ], order="create_date, id")
        period_layers = Layer.search([
            ("product_id", "in", product_ids),
            ("location_id", "in", location_ids),
            ("company_id", "in", company_ids),
            ("stock_move_id.date", ">=", start_utc),
            ("stock_move_id.date", "<", end_utc),
        ])

        opening_by_key = {}
        for layer in opening_layers:
            opening_by_key.setdefault((layer.location_id.id, layer.product_id.id), []).append(layer)
        period_by_key = {}
        for layer in period_layers:
            period_by_key.setdefault((layer.location_id.id, layer.product_id.id), []).append(layer)
        return opening_by_key, period_by_key

    def _valuation_rows_for_key(self, location_id, product_id, opening_by_key, period_by_key):
        """Row list for one (location_id, product_id) key from the bulk-fetched
        layer dicts, in the same opening-then-period order/fallback labels as
        _product_scope_valuation_rows."""
        rows = []
        for layer in opening_by_key.get((location_id, product_id), []):
            rows.extend(self._valuation_rows_for_layer(layer, layer.remaining_qty, "ยอดยกมา"))
        for layer in period_by_key.get((location_id, product_id), []):
            if layer.quantity > 0:
                rows.extend(self._valuation_rows_for_layer(layer, layer.quantity, "เอกสารรับในปี"))
            elif layer.quantity < 0:
                rows.extend(self._valuation_rows_for_layer(layer, layer.quantity, "เอกสารจ่ายในปี"))
        return rows

    def _discover_valuation_pairs(self, domain_extra, date_from, date_to, company_ids):
        """(location_id, product_id) pairs with a layer touching the period,
        or with a still-outstanding opening layer, matching domain_extra."""
        Layer = self.env["stock.valuation.layer"]
        start_utc, end_utc = self._date_range_utc(date_from, date_to)
        domain_period = domain_extra + [
            ("company_id", "in", company_ids),
            ("stock_move_id.date", ">=", start_utc),
            ("stock_move_id.date", "<", end_utc),
        ]
        domain_open = domain_extra + [
            ("company_id", "in", company_ids),
            ("remaining_qty", ">", 0),
        ]
        pairs = set()
        for domain in (domain_period, domain_open):
            groups = Layer.read_group(
                domain, ["location_id", "product_id"], ["location_id", "product_id"], lazy=False,
            )
            for group in groups:
                location = group.get("location_id")
                product = group.get("product_id")
                if location and product:
                    pairs.add((location[0], product[0]))
        return pairs

    @staticmethod
    def _finalize_valuation_rows(rows, sort_key):
        """Sort, then add a running ยอดยกมา (opening_qty/opening_value) and
        ยอดคงเหลือ/มูลค่าสินค้าคงเหลือ (balance_qty/balance_value) per row,
        tracked separately per (location, product) group so mixed-scope
        exports (all products / all locations) don't cross-contaminate
        balances between products."""
        rows.sort(key=sort_key)
        running = {}
        for row in rows:
            key = (row["location_label"], row["product_default_code"], row["product_name"])
            qty, value = running.get(key, (0.0, 0.0))
            row["opening_qty"] = qty
            row["opening_value"] = value
            qty += row["qty_in"] - row["qty_out"]
            value += row["cost_in"] - row["cost_out"]
            running[key] = (qty, value)
            row["balance_qty"] = qty
            row["balance_value"] = value
        for idx, row in enumerate(rows, start=1):
            row["seq"] = idx
            del row["_sort_dt"]
        return rows

    @api.model
    def get_stock_card_valuation_lines(self, product_id, scope_location_ids, date_from, date_to, company_ids=None):
        """Flat cost+lot ledger for one product in one scope: opening layers
        (ยอดยกมา) followed by in-period receipts (เอกสารรับในปี) and issues
        (เอกสารจ่ายในปี), one row per layer (split further per lot)."""
        if not self._can_see_value():
            raise AccessError("คุณไม่มีสิทธิ์ดูข้อมูลมูลค่าสินค้า")
        if not company_ids:
            company_ids = self.env.companies.ids
        scope_location_ids = list(scope_location_ids)
        rows = self._product_scope_valuation_rows(
            product_id, scope_location_ids, date_from, date_to, company_ids,
        )
        return self._finalize_valuation_rows(rows, sort_key=lambda r: r["_sort_dt"])

    @api.model
    def get_product_all_locations_valuation_lines(self, product_id, date_from, date_to, company_ids=None):
        """Cost+lot ledger for one product across every location where it has
        a layer touching the period or a still-outstanding opening layer."""
        if not self._can_see_value():
            raise AccessError("คุณไม่มีสิทธิ์ดูข้อมูลมูลค่าสินค้า")
        if not company_ids:
            company_ids = self.env.companies.ids
        pairs = self._discover_valuation_pairs(
            [("product_id", "=", product_id)], date_from, date_to, company_ids,
        )
        location_ids = {loc_id for loc_id, _prod_id in pairs}
        if not location_ids:
            return []
        opening_by_key, period_by_key = self._get_valuation_layers_bulk(
            [product_id], location_ids, date_from, date_to, company_ids,
        )
        rows = []
        for location_id in location_ids:
            rows.extend(self._valuation_rows_for_key(location_id, product_id, opening_by_key, period_by_key))
        return self._finalize_valuation_rows(
            rows, sort_key=lambda r: (r["location_label"], r["_sort_dt"]),
        )

    @api.model
    def get_scoped_stock_card_valuation_lines(self, scope_location_ids, date_from, date_to, company_ids=None):
        """Cost+lot ledger for every product with a layer in scope_location_ids
        touching the period, or a still-outstanding opening layer there."""
        if not self._can_see_value():
            raise AccessError("คุณไม่มีสิทธิ์ดูข้อมูลมูลค่าสินค้า")
        if not company_ids:
            company_ids = self.env.companies.ids
        scope_location_ids = list(scope_location_ids)
        if not scope_location_ids:
            return []
        pairs = self._discover_valuation_pairs(
            [("location_id", "in", scope_location_ids)], date_from, date_to, company_ids,
        )
        product_ids = {prod_id for _loc_id, prod_id in pairs}
        if not product_ids:
            return []
        opening_by_key, period_by_key = self._get_valuation_layers_bulk(
            product_ids, scope_location_ids, date_from, date_to, company_ids,
        )
        rows = []
        for product_id in product_ids:
            for location_id in scope_location_ids:
                rows.extend(self._valuation_rows_for_key(location_id, product_id, opening_by_key, period_by_key))
        return self._finalize_valuation_rows(
            rows, sort_key=lambda r: (r["location_label"], r["product_default_code"], r["_sort_dt"]),
        )

    @api.model
    def get_all_stock_card_valuation_lines(self, date_from, date_to, company_ids=None):
        """Cost+lot ledger for every (location, product) pair with a layer
        touching the period, or a still-outstanding opening layer."""
        if not self._can_see_value():
            raise AccessError("คุณไม่มีสิทธิ์ดูข้อมูลมูลค่าสินค้า")
        if not company_ids:
            company_ids = self.env.companies.ids
        pairs = self._discover_valuation_pairs([], date_from, date_to, company_ids)
        pairs_by_location = {}
        for location_id, product_id in pairs:
            pairs_by_location.setdefault(location_id, set()).add(product_id)

        rows = []
        for location_id, product_ids in pairs_by_location.items():
            opening_by_key, period_by_key = self._get_valuation_layers_bulk(
                product_ids, [location_id], date_from, date_to, company_ids,
            )
            for product_id in product_ids:
                rows.extend(self._valuation_rows_for_key(location_id, product_id, opening_by_key, period_by_key))
        return self._finalize_valuation_rows(
            rows, sort_key=lambda r: (r["location_label"], r["product_default_code"], r["_sort_dt"]),
        )
