from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

# Odoo 17 mrp.production state values. "In Progress" (UI label) maps to both
# 'progress' and 'to_close' since either means raw materials are being
# consumed but the MO isn't finished yet.
MO_STATE_LABELS = {
    "draft": "Draft",
    "confirmed": "Confirmed",
    "progress": "In Progress",
    "to_close": "In Progress",
    "done": "Done",
    "cancel": "Cancelled",
}

DEFAULT_STATUS_LIST = ["progress", "to_close", "done"]

# Raw-material stock.move states considered "consumed" for WIP purposes.
# Cancelled moves are always excluded regardless of this list.
CONSUMED_MOVE_STATES = ("assigned", "partially_available", "done")

COST_SOURCES = [
    {"value": "svl", "label": "Stock Valuation"},
    {"value": "move_unit_cost", "label": "Move Unit Cost"},
    {"value": "standard_price", "label": "Standard Cost"},
]


class WipManufacturingReport(models.AbstractModel):
    _name = "buz.wip.manufacturing.report"
    _description = "WIP Manufacturing Report Calculation Engine"

    # ------------------------------------------------------------------
    # Date helpers
    # ------------------------------------------------------------------

    def _date_range_utc(self, date_from, date_to):
        """Convert user-tz Date bounds to a half-open UTC datetime interval."""
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def get_mo_statuses(self):
        return [
            {"value": "draft", "label": "Draft"},
            {"value": "confirmed", "label": "Confirmed"},
            {"value": "progress", "label": "In Progress"},
            {"value": "done", "label": "Done"},
            {"value": "cancel", "label": "Cancelled"},
        ]

    @api.model
    def get_cost_sources(self):
        return COST_SOURCES

    @api.model
    def get_wip_data(
        self,
        mo_ids=None,
        date_from=None,
        date_to=None,
        product_ids=None,
        component_ids=None,
        location_ids=None,
        status_list=None,
        show_valuation_detail=False,
        cost_source="svl",
        company_ids=None,
        page_size=50,
        page=0,
    ):
        if not company_ids:
            company_ids = self.env.companies.ids
        if not status_list:
            # UI-facing "In Progress" maps to both progress + to_close states.
            status_list = list(DEFAULT_STATUS_LIST)
        else:
            status_list = list(status_list)
            if "progress" in status_list and "to_close" not in status_list:
                status_list.append("to_close")

        start_utc, end_utc = (None, None)
        if date_from and date_to:
            start_utc, end_utc = self._date_range_utc(date_from, date_to)

        mo_domain = [("company_id", "in", company_ids), ("state", "in", status_list)]
        if mo_ids:
            mo_domain.append(("id", "in", list(mo_ids)))
        if product_ids:
            mo_domain.append(("product_id", "in", list(product_ids)))

        # Candidate MOs matching state/company/mo/product filters, in display
        # order. The date/component/location filters are move-level, so the
        # *actual* MO set for this report is derived from the moves query
        # below (an MO with no qualifying move in range simply has no row) —
        # this keeps summary, pagination and detail all reading one dataset.
        order = "date_start desc, id desc"
        candidate_mo_ids = self.env["mrp.production"].search(mo_domain, order=order).ids

        move_domain = self._move_domain(
            candidate_mo_ids, start_utc, end_utc, component_ids, location_ids, company_ids,
        )
        moves = self._fetch_moves_with_cost(move_domain, cost_source)

        moves_by_mo = {}
        for move in moves:
            moves_by_mo.setdefault(move["raw_material_production_id"][0], []).append(move)

        # Preserve candidate_mo_ids order (already sorted) while filtering to
        # MOs that actually have a qualifying move.
        filtered_mo_ids = [mo_id for mo_id in candidate_mo_ids if mo_id in moves_by_mo]
        total_count = len(filtered_mo_ids)

        summary = {
            "total_mos": total_count,
            "total_items": len({m["product_id"][0] for m in moves}),
            "total_quantity": sum(abs(m["quantity"]) for m in moves),
            "total_wip_value": sum(m["amount"] for m in moves),
        }

        offset = page * page_size if page_size else 0
        page_mo_ids = filtered_mo_ids[offset: offset + page_size] if page_size else filtered_mo_ids

        data = self._build_mo_rows(page_mo_ids, moves_by_mo, show_valuation_detail)

        grand_qty = sum(mo["subtotal_qty"] for mo in data)
        grand_amount = sum(mo["subtotal_amount"] for mo in data)

        return {
            "summary": summary,
            "data": data,
            "grand_total": {"quantity": grand_qty, "amount": grand_amount},
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "has_next": bool(page_size) and (offset + page_size) < total_count,
            "has_prev": page > 0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _move_domain(self, mo_ids, start_utc, end_utc, component_ids, location_ids, company_ids):
        if not mo_ids:
            return [("id", "=", 0)]
        domain = [
            ("raw_material_production_id", "in", mo_ids),
            ("state", "in", CONSUMED_MOVE_STATES),
            ("company_id", "in", company_ids),
        ]
        if start_utc and end_utc:
            domain += [("date", ">=", start_utc), ("date", "<", end_utc)]
        if component_ids:
            domain.append(("product_id", "in", list(component_ids)))
        if location_ids:
            domain.append(("location_id", "in", list(location_ids)))
        return domain

    def _fetch_moves_with_cost(self, move_domain, cost_source):
        """search_read matching raw moves once, aggregate SVLs once via
        read_group (keyed by stock_move_id), join in Python. Avoids N+1
        queries per move/MO."""
        moves = self.env["stock.move"].search_read(
            move_domain,
            [
                "id", "raw_material_production_id", "product_id", "quantity",
                "price_unit", "location_id", "date", "product_uom",
            ],
        )
        if not moves:
            return []

        move_ids = [m["id"] for m in moves]
        svl_groups = self.env["stock.valuation.layer"].read_group(
            [("stock_move_id", "in", move_ids)],
            ["value:sum", "quantity:sum"],
            ["stock_move_id"],
        )
        svl_by_move = {
            g["stock_move_id"][0]: {
                "value": g["value"], "qty": g["quantity"],
                "count": g["stock_move_id_count"],
            }
            for g in svl_groups
        }

        product_ids = {m["product_id"][0] for m in moves}
        products_by_id = {
            p.id: p for p in self.env["product.product"].browse(list(product_ids))
        }

        for move in moves:
            svl_data = svl_by_move.get(move["id"])
            product = products_by_id.get(move["product_id"][0])
            actual_cost_source = cost_source
            if cost_source == "standard_price":
                unit_cost = product.standard_price if product else 0.0
            elif cost_source == "move_unit_cost":
                unit_cost = move["price_unit"]
            else:  # 'svl' (default): Stock Valuation, fallback to price_unit
                if svl_data and svl_data["qty"]:
                    unit_cost = abs(svl_data["value"]) / abs(svl_data["qty"])
                else:
                    unit_cost = move["price_unit"]
                    actual_cost_source = "move_unit_cost"

            move["unit_cost"] = unit_cost
            move["cost_source"] = actual_cost_source
            move["amount"] = abs(move["quantity"]) * unit_cost
            move["product_code"] = (product.default_code or "") if product else ""
            move["product_name"] = product.name if product else move["product_id"][1]
            move["svl_count"] = svl_data["count"] if svl_data else 0
            move["svl_total_value"] = svl_data["value"] if svl_data else 0.0
            move["svl_total_qty"] = svl_data["qty"] if svl_data else 0.0

        return moves

    def _build_mo_rows(self, mo_ids, moves_by_mo, show_valuation_detail):
        if not mo_ids:
            return []

        productions = self.env["mrp.production"].browse(mo_ids)
        rows = []
        for mo in productions:
            mo_moves = moves_by_mo.get(mo.id, [])
            materials = []
            for move in mo_moves:
                material = {
                    "move_id": move["id"],
                    "product_id": move["product_id"][0],
                    "product_code": move["product_code"],
                    "product_name": move["product_name"],
                    "location_id": move["location_id"][0] if move["location_id"] else False,
                    "location_name": move["location_id"][1] if move["location_id"] else "",
                    "quantity": abs(move["quantity"]),
                    "uom": move["product_uom"][1] if move["product_uom"] else "",
                    "unit_cost": move["unit_cost"],
                    "amount": move["amount"],
                    "cost_source": move["cost_source"],
                }
                if show_valuation_detail:
                    material["svl_count"] = move["svl_count"]
                    material["svl_total_value"] = move["svl_total_value"]
                    material["svl_total_qty"] = move["svl_total_qty"]
                materials.append(material)

            rows.append({
                "mo_id": mo.id,
                "mo_name": mo.name,
                "mo_date": fields.Date.to_string(mo.date_start) if mo.date_start else "",
                "mo_state": mo.state,
                "mo_state_label": MO_STATE_LABELS.get(mo.state, mo.state),
                "product_id": mo.product_id.id,
                "product_code": mo.product_id.default_code or "",
                "product_name": mo.product_id.name,
                "mo_qty": mo.product_qty,
                "mo_uom": mo.product_uom_id.name,
                "materials": materials,
                "subtotal_qty": sum(m["quantity"] for m in materials),
                "subtotal_amount": sum(m["amount"] for m in materials),
            })
        return rows
