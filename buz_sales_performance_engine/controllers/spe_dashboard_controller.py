from datetime import datetime

from odoo import http
from odoo.http import request


class SpeDashboardController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _base_result_domain(self, filters):
        domain = [("company_id", "in", request.env.company.ids)]
        if filters.get("date_from"):
            domain.append(("date_invoiced", ">=", self._to_datetime(filters["date_from"])))
        if filters.get("date_to"):
            domain.append(("date_invoiced", "<=",
                           self._to_datetime(filters["date_to"], end_of_day=True)))
        if filters.get("salesperson_id"):
            domain.append(("salesperson_id", "=", int(filters["salesperson_id"])))
        if filters.get("team_id"):
            domain.append(("team_id", "=", int(filters["team_id"])))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", int(filters["partner_id"])))
        if filters.get("product_id"):
            domain.append(("product_id", "=", int(filters["product_id"])))
        if filters.get("categ_id"):
            domain.append(("categ_id", "=", int(filters["categ_id"])))
        if filters.get("source") in ("sale", "pos"):
            domain.append(("source", "=", filters["source"]))
        return domain

    @staticmethod
    def _to_datetime(value, end_of_day=False):
        if isinstance(value, datetime):
            return value
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt

    @staticmethod
    def _round(value):
        return round(float(value or 0.0), 2)

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    @http.route("/spe/dashboard/filter_options", type="json", auth="user")
    def filter_options(self, **kw):
        Result = request.env["buz.sales.performance.result"].sudo()
        base = [("company_id", "in", request.env.company.ids)]
        def _opts(group_field, name_field):
            rows = Result.read_group(base, [group_field], [group_field])
            ids = [r[group_field][0] for r in rows if r[group_field]]
            if not ids:
                return []
            model = {
                "salesperson_id": "res.users",
                "team_id": "crm.team",
                "partner_id": "res.partner",
                "product_id": "product.product",
                "categ_id": "product.category",
            }[group_field]
            data = request.env[model].sudo().browse(ids).read(["id", name_field])
            return [{"id": d["id"], "name": d[name_field]} for d in data]
        return {
            "salespersons": _opts("salesperson_id", "name"),
            "teams": _opts("team_id", "name"),
            "partners": _opts("partner_id", "name"),
            "products": _opts("product_id", "name"),
            "categories": _opts("categ_id", "name"),
            "companies": [
                {"id": c.id, "name": c.name}
                for c in request.env["res.company"].sudo().browse(request.env.company.ids)
            ],
        }

    @http.route("/spe/dashboard/kpi", type="json", auth="user")
    def kpi(self, **kw):
        filters = kw.get("filters", {}) or {}
        Result = request.env["buz.sales.performance.result"].sudo()
        domain = self._base_result_domain(filters)
        agg = Result.read_group(
            domain,
            ["net_sales:sum", "invoice_amount:sum", "refund_amount:sum",
             "delivered_qty:sum", "invoiced_qty:sum"],
            [],
        )[0]
        net = self._round(agg["net_sales"])
        inv = self._round(agg["invoice_amount"])
        ref = self._round(agg["refund_amount"])
        delivered = self._round(agg["delivered_qty"])
        invoiced = self._round(agg["invoiced_qty"])

        # Target roll-up for the same scope & period.
        target_domain = [
            ("company_id", "in", request.env.company.ids),
            ("state", "=", "confirmed"),
        ]
        if filters.get("date_from"):
            target_domain.append(("date_end", ">=", filters["date_from"]))
        if filters.get("date_to"):
            target_domain.append(("date_start", "<=", filters["date_to"]))
        if filters.get("salesperson_id"):
            target_domain.append(("user_id", "=", int(filters["salesperson_id"])))
        if filters.get("team_id"):
            target_domain.append(("team_id", "=", int(filters["team_id"])))
        targets = request.env["buz.sales.performance.target"].sudo().search(target_domain)
        target_amount = self._round(sum(targets.mapped("target_amount")))

        avg_daily = 0.0
        days = 1
        if filters.get("date_from") and filters.get("date_to"):
            d_from = self._to_datetime(filters["date_from"]).date()
            d_to = self._to_datetime(filters["date_to"]).date()
            days = max(1, (d_to - d_from).days + 1)
            avg_daily = self._round(net / days)

        achievement = (net / target_amount * 100.0) if target_amount else 0.0
        remaining = max(0.0, target_amount - net)
        # Linear forecast at current daily run-rate.
        forecast = self._round(avg_daily * days) if days else 0.0
        return {
            "target": target_amount,
            "actual": net,
            "achievement": round(achievement, 1),
            "remaining": self._round(remaining),
            "invoice_amount": inv,
            "refund_amount": ref,
            "delivered_qty": delivered,
            "invoiced_qty": invoiced,
            "delivery_pct": round((delivered / invoiced * 100.0) if invoiced else 0.0, 1),
            "avg_daily": avg_daily,
            "forecast": forecast,
        }

    @http.route("/spe/dashboard/series", type="json", auth="user")
    def series(self, **kw):
        filters = kw.get("filters", {}) or {}
        kind = kw.get("kind")
        Result = request.env["buz.sales.performance.result"].sudo()
        domain = self._base_result_domain(filters)

        if kind in ("daily", "monthly"):
            interval = "day" if kind == "daily" else "month"
            rows = Result.read_group(
                domain, ["net_sales:sum", "invoice_amount:sum", "refund_amount:sum"],
                ["date_invoiced:" + interval],
            )
            rows.sort(key=lambda r: r["date_invoiced:" + interval])
            return [{
                "label": r["date_invoiced:" + interval],
                "net": self._round(r["net_sales"]),
                "invoice": self._round(r["invoice_amount"]),
                "refund": self._round(r["refund_amount"]),
            } for r in rows]

        if kind == "top":
            field = kw.get("field", "partner_id")
            limit = int(kw.get("limit", 8))
            rows = Result.read_group(domain, ["net_sales:sum"], [field], limit=limit)
            rows = [r for r in rows if r[field]]
            rows.sort(key=lambda r: r["net_sales"], reverse=True)
            return [{
                "id": r[field][0], "name": r[field][1], "value": self._round(r["net_sales"]),
            } for r in rows[:limit]]

        if kind == "delivery_trend":
            rows = Result.read_group(
                domain, ["delivered_qty:sum", "invoiced_qty:sum"],
                ["date_delivered:month"],
            )
            rows.sort(key=lambda r: r["date_delivered:month"])
            return [{
                "label": r["date_delivered:month"],
                "delivered": self._round(r["delivered_qty"]),
                "invoiced": self._round(r["invoiced_qty"]),
            } for r in rows if r["date_delivered:month"]]

        if kind == "leaderboard":
            field = kw.get("field", "salesperson_id")
            limit = int(kw.get("limit", 10))
            rows = Result.read_group(
                domain + [(field, "!=", False)],
                ["net_sales:sum", "invoice_amount:sum", "refund_amount:sum"],
                [field],
            )
            rows.sort(key=lambda r: r["net_sales"], reverse=True)
            return [{
                "id": r[field][0], "name": r[field][1],
                "net": self._round(r["net_sales"]),
                "invoice": self._round(r["invoice_amount"]),
                "refund": self._round(r["refund_amount"]),
            } for r in rows[:limit]]

        return []

    @http.route("/spe/dashboard/action_drill", type="json", auth="user")
    def action_drill(self, **kw):
        """Return an act_window action for a drill-down on the source model."""
        filters = kw.get("filters", {}) or {}
        kind = kw.get("kind")  # invoices | credit_notes | deliveries | results
        Result = request.env["buz.sales.performance.result"].sudo()
        domain = self._base_result_domain(filters)
        rows = Result.search_read(
            domain, ["sale_order_line_id", "sale_order_id", "pos_order_id"], limit=None,
        )
        sol_ids = [r["sale_order_line_id"][0] for r in rows if r["sale_order_line_id"]]
        so_ids = list({r["sale_order_id"][0] for r in rows if r["sale_order_id"]})
        pos_order_ids = list({r["pos_order_id"][0] for r in rows if r["pos_order_id"]})
        pos_orders = request.env["pos.lite.order"].sudo().browse(pos_order_ids)
        pos_invoice_ids = pos_orders.mapped("invoice_id").ids
        pos_picking_ids = pos_orders.mapped("picking_id").ids

        if kind == "invoices":
            return {
                "type": "ir.actions.act_window",
                "name": "Posted Invoices",
                "res_model": "account.move",
                "view_mode": "tree,form",
                "views": [[False, "list"], [False, "form"]],
                "domain": [
                    ("move_type", "=", "out_invoice"),
                    ("state", "=", "posted"),
                    "|",
                    ("line_ids.sale_line_ids", "in", sol_ids),
                    ("id", "in", pos_invoice_ids),
                ],
                "context": {"default_move_type": "out_invoice"},
            }
        if kind == "credit_notes":
            return {
                "type": "ir.actions.act_window",
                "name": "Credit Notes",
                "res_model": "account.move",
                "view_mode": "tree,form",
                "views": [[False, "list"], [False, "form"]],
                "domain": [
                    ("move_type", "=", "out_refund"),
                    ("state", "=", "posted"),
                    "|",
                    ("line_ids.sale_line_ids", "in", sol_ids),
                    ("id", "in", pos_invoice_ids),
                ],
                "context": {"default_move_type": "out_refund"},
            }
        if kind == "deliveries":
            return {
                "type": "ir.actions.act_window",
                "name": "Deliveries",
                "res_model": "stock.picking",
                "view_mode": "tree,form",
                "views": [[False, "list"], [False, "form"]],
                "domain": [
                    ("state", "=", "done"),
                    "|",
                    ("move_ids.sale_line_id", "in", sol_ids),
                    ("id", "in", pos_picking_ids),
                ],
            }
        if kind == "orders":
            if filters.get("source") == "pos":
                return {
                    "type": "ir.actions.act_window",
                    "name": "POS Orders",
                    "res_model": "pos.lite.order",
                    "view_mode": "tree,form",
                    "views": [[False, "list"], [False, "form"]],
                    "domain": [("id", "in", pos_order_ids)],
                }
            return {
                "type": "ir.actions.act_window",
                "name": "Sale Orders",
                "res_model": "sale.order",
                "view_mode": "tree,form",
                "views": [[False, "list"], [False, "form"]],
                "domain": [("id", "in", so_ids)],
            }
        if kind == "results":
            return {
                "type": "ir.actions.act_window",
                "name": "Performance Results",
                "res_model": "buz.sales.performance.result",
                "view_mode": "tree,pivot,graph,form",
                "views": [[False, "list"], [False, "pivot"], [False, "graph"], [False, "form"]],
                "domain": domain,
            }
        return {"type": "ir.actions.act_window_close"}
