import json
import math

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import float_round


class SalesAnalyticsDashboard(models.TransientModel):
    _name = "buz.sales.analytics.dashboard"
    _description = "Sales Analytics Dashboard"

    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, readonly=True
    )
    date_from = fields.Date()
    date_to = fields.Date()
    salesperson_id = fields.Many2one("res.users")
    team_id = fields.Many2one("crm.team")
    category_id = fields.Many2one("product.category")
    partner_id = fields.Many2one("res.partner")
    period_type = fields.Selection(
        [
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
        ],
        default="monthly",
    )

    @api.model
    def _get_default_filters(self):
        today = fields.Date.context_today(self)
        return {
            "date_from": str(today.replace(day=1)),
            "date_to": str(today),
            "salesperson_id": False,
            "team_id": False,
            "category_id": False,
            "partner_id": False,
            "period_type": "monthly",
        }

    @api.model
    def _get_previous_period_filters(self):
        today = fields.Date.context_today(self)
        date_from = today.replace(day=1) - relativedelta(months=1)
        date_to = today.replace(day=1) - relativedelta(days=1)
        return {
            "date_from": str(date_from),
            "date_to": str(date_to),
            "salesperson_id": False,
            "team_id": False,
            "category_id": False,
            "partner_id": False,
            "period_type": "monthly",
        }

    @api.model
    def _get_sale_order_domain(self, filters):
        domain = [
            ("state", "in", ["sale", "done"]),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            domain.append(("team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def _get_quotation_domain(self, filters):
        domain = [
            ("state", "=", "draft"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            domain.append(("team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def _get_cancelled_domain(self, filters):
        domain = [
            ("state", "=", "cancel"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            domain.append(("team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def _get_order_line_domain(self, filters):
        so_domain = self._get_sale_order_domain(filters)
        so_domain[0] = ("order_id.state", "in", ["sale", "done"])
        if filters.get("category_id"):
            so_domain.append(("product_id.categ_id", "child_of", filters["category_id"]))
        line_domain = [("order_id.state", "in", ["sale", "done"])]
        for cond in so_domain[1:]:
            if isinstance(cond, (list, tuple)) and len(cond) >= 2:
                field = cond[0]
                if field.startswith("order_id."):
                    line_domain.append(cond)
                elif field == "date_order":
                    line_domain.append(("order_id." + field, cond[1], cond[2]))
                elif field in ("user_id", "team_id", "partner_id", "company_id"):
                    line_domain.append(("order_id." + field, cond[1], cond[2]))
        if filters.get("category_id"):
            line_domain.append(
                ("product_id.categ_id", "child_of", filters["category_id"])
            )
        return line_domain

    @api.model
    def _get_pos_order_domain(self, filters):
        domain = [
            ("state", "in", ["paid", "done"]),
            ("company_id", "=", self.env.company.id),
            ("is_return", "=", False),
        ]
        if filters.get("date_from"):
            domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(("employee_id.user_id", "=", filters["salesperson_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def _get_pos_order_line_domain(self, filters):
        domain = [
            ("order_id.state", "in", ["paid", "done"]),
            ("order_id.company_id", "=", self.env.company.id),
            ("order_id.is_return", "=", False),
        ]
        if filters.get("date_from"):
            domain.append(("order_id.date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("order_id.date_order", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(
                ("order_id.employee_id.user_id", "=", filters["salesperson_id"])
            )
        if filters.get("partner_id"):
            domain.append(("order_id.partner_id", "=", filters["partner_id"]))
        if filters.get("category_id"):
            domain.append(("product_id.categ_id", "child_of", filters["category_id"]))
        return domain

    @api.model
    def _get_pos_cancelled_domain(self, filters):
        domain = [
            ("state", "=", "cancelled"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(("employee_id.user_id", "=", filters["salesperson_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def _aggregate_pos(self, domain):
        pos_model = self.env["pos.lite.order"].sudo()
        agg = pos_model.read_group(domain, ["amount_total:sum"], [])[0]
        revenue = agg.get("amount_total") or 0.0
        count_agg = pos_model.read_group(domain, ["__count"], [])[0]
        count = count_agg.get("__count") or 0
        return {"revenue": revenue, "count": count}

    @api.model
    def _get_invoice_domain(self, filters):
        domain = [
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "!=", "cancel"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            domain.append(("invoice_date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            domain.append(("invoice_date", "<=", filters["date_to"]))
        if filters.get("salesperson_id"):
            domain.append(("invoice_user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            domain.append(("team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def _get_delivery_picking_domain(self, filters):
        domain = [
            ("picking_type_code", "=", "outgoing"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            domain.append(("scheduled_date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            domain.append(("scheduled_date", "<=", end))
        if filters.get("salesperson_id"):
            domain.append(("sale_id.user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            domain.append(("sale_id.team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", filters["partner_id"]))
        return domain

    @api.model
    def get_kpi_data(self, filters):
        so_domain = self._get_sale_order_domain(filters)
        so_model = self.env["sale.order"].sudo()
        inv_model = self.env["account.move"].sudo()
        cache_model = self.env["buz.sales.analytics.cache"]

        so_agg = so_model.read_group(so_domain, ["amount_total:sum"], [])[0]
        so_revenue = so_agg.get("amount_total") or 0.0
        so_count_agg = so_model.read_group(so_domain, ["__count"], [])[0]
        so_orders = so_count_agg.get("__count") or 0

        pos_domain = self._get_pos_order_domain(filters)
        pos_data = self._aggregate_pos(pos_domain)

        total_revenue = so_revenue + pos_data["revenue"]
        total_orders = so_orders + pos_data["count"]
        avg_order = total_revenue / total_orders if total_orders else 0.0

        prev_filters = dict(filters)
        today = fields.Date.context_today(self)
        if filters.get("date_from") and filters.get("date_to"):
            df = fields.Date.from_string(filters["date_from"])
            dt = fields.Date.from_string(filters["date_to"])
            span = (dt - df).days + 1
            prev_filters["date_from"] = str(df - relativedelta(days=span))
            prev_filters["date_to"] = str(df - relativedelta(days=1))

        prev_so_domain = self._get_sale_order_domain(prev_filters)
        prev_so_agg = so_model.read_group(prev_so_domain, ["amount_total:sum"], [])[0]
        prev_so_revenue = prev_so_agg.get("amount_total") or 0.0

        prev_pos_domain = self._get_pos_order_domain(prev_filters)
        prev_pos_data = self._aggregate_pos(prev_pos_domain)

        prev_revenue = prev_so_revenue + prev_pos_data["revenue"]
        growth_rate = (
            ((total_revenue - prev_revenue) / prev_revenue * 100.0)
            if prev_revenue
            else 0.0
        )

        target_achievement = self._get_target_achievement(filters)

        inv_domain = self._get_invoice_domain(filters)
        outstanding_domain = inv_domain + [
            ("payment_state", "in", ["not_paid", "partial"]),
        ]
        out_agg = inv_model.read_group(
            outstanding_domain, ["amount_residual:sum"], [])[0]
        outstanding_invoices = out_agg.get("amount_residual") or 0.0

        picking_model = self.env["stock.picking"].sudo()
        done_domain = [
            ("picking_type_code", "=", "outgoing"),
            ("state", "=", "done"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            done_domain.append(("date_done", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            done_domain.append(("date_done", "<=", end))
        if filters.get("salesperson_id"):
            done_domain.append(("sale_id.user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            done_domain.append(("sale_id.team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            done_domain.append(("partner_id", "=", filters["partner_id"]))
        done_pickings = picking_model.search(done_domain)
        total_delivered_qty = sum(
            done_pickings.move_ids.filtered(lambda m: m.state == "done").mapped("quantity")
        )

        return {
            "total_revenue": float_round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_order_value": float_round(avg_order, 2),
            "growth_rate": float_round(growth_rate, 2),
            "target_achievement": float_round(target_achievement, 2),
            "outstanding_invoices": float_round(outstanding_invoices, 2),
            "total_delivered_qty": float_round(total_delivered_qty, 2),
        }

    @api.model
    def _get_target_achievement(self, filters):
        target_model = self.env["sales.target"].sudo()
        today = fields.Date.context_today(self)
        target_domain = [
            ("state", "=", "confirmed"),
            ("date_start", "<=", today),
            ("date_end", ">=", today),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("salesperson_id"):
            target_domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            target_domain.append(("team_ids", "=", filters["team_id"]))

        targets = target_model.search(target_domain, limit=1)
        if not targets:
            return 0.0
        total_target = sum(targets.mapped("target_amount"))
        total_achieved = sum(targets.mapped("achieved_amount"))
        return (total_achieved / total_target * 100.0) if total_target else 0.0

    @api.model
    def get_revenue_trend(self, filters):
        so_model = self.env["sale.order"].sudo()
        pos_model = self.env["pos.lite.order"].sudo()
        so_domain = self._get_sale_order_domain(filters)
        pos_domain = self._get_pos_order_domain(filters)
        period_type = filters.get("period_type", "monthly")

        groupby_map = {
            "daily": "date_order:day",
            "weekly": "date_order:week",
            "monthly": "date_order:month",
            "quarterly": "date_order:quarter",
        }
        groupby = groupby_map.get(period_type, "date_order:month")

        so_groups = so_model.read_group(
            so_domain, ["amount_total:sum", "__count"], [groupby], lazy=False
        )
        pos_groups = pos_model.read_group(
            pos_domain, ["amount_total:sum", "__count"], [groupby], lazy=False
        )

        combined = {}
        for g in so_groups:
            key = g.get(groupby) or ""
            combined.setdefault(key, {"period": key, "revenue": 0.0, "order_count": 0})
            combined[key]["revenue"] += g.get("amount_total") or 0.0
            combined[key]["order_count"] += g.get("__count") or 0
        for g in pos_groups:
            key = g.get(groupby) or ""
            combined.setdefault(key, {"period": key, "revenue": 0.0, "order_count": 0})
            combined[key]["revenue"] += g.get("amount_total") or 0.0
            combined[key]["order_count"] += g.get("__count") or 0

        result = sorted(combined.values(), key=lambda x: x["period"])
        for r in result:
            r["revenue"] = float_round(r["revenue"], 2)
        return result

    @api.model
    def get_top_customers(self, filters, limit=10):
        so_model = self.env["sale.order"].sudo()
        pos_model = self.env["pos.lite.order"].sudo()
        so_domain = self._get_sale_order_domain(filters)
        pos_domain = self._get_pos_order_domain(filters)

        so_groups = so_model.read_group(
            so_domain, ["amount_total:sum", "__count"], ["partner_id"], lazy=False
        )
        pos_groups = pos_model.read_group(
            pos_domain, ["amount_total:sum", "__count"], ["partner_id"], lazy=False
        )

        combined = {}
        for g in so_groups:
            info = g.get("partner_id")
            pid = info[0] if info else -1
            pname = info[1] if info else "Unknown"
            key = pid if pid else -1
            combined.setdefault(key, {"partner_id": pid, "partner_name": pname, "total_revenue": 0.0, "order_count": 0})
            combined[key]["total_revenue"] += g.get("amount_total") or 0.0
            combined[key]["order_count"] += g.get("__count") or 0
        for g in pos_groups:
            info = g.get("partner_id")
            pid = info[0] if info else -1
            pname = info[1] if info else "Unknown"
            key = pid if pid else -1
            combined.setdefault(key, {"partner_id": pid, "partner_name": pname, "total_revenue": 0.0, "order_count": 0})
            combined[key]["total_revenue"] += g.get("amount_total") or 0.0
            combined[key]["order_count"] += g.get("__count") or 0

        result = sorted(combined.values(), key=lambda x: x["total_revenue"], reverse=True)
        for r in result[:limit]:
            r["total_revenue"] = float_round(r["total_revenue"], 2)
        return result[:limit]

    @api.model
    def get_top_products(self, filters, limit=10):
        sol_model = self.env["sale.order.line"].sudo()
        pol_model = self.env["pos.lite.order.line"].sudo()
        so_domain = self._get_order_line_domain(filters)
        pos_domain = self._get_pos_order_line_domain(filters)

        so_groups = sol_model.read_group(
            so_domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            ["product_id"],
            lazy=False,
        )
        pos_groups = pol_model.read_group(
            pos_domain,
            ["qty:sum", "price_subtotal:sum"],
            ["product_id"],
            lazy=False,
        )

        combined = {}
        for g in so_groups:
            info = g.get("product_id")
            pid = info[0] if info else -1
            pname = info[1] if info else "Unknown"
            combined.setdefault(pid, {"product_id": pid, "product_name": pname, "qty_sold": 0.0, "revenue": 0.0})
            combined[pid]["qty_sold"] += g.get("product_uom_qty") or 0.0
            combined[pid]["revenue"] += g.get("price_subtotal") or 0.0
        for g in pos_groups:
            info = g.get("product_id")
            pid = info[0] if info else -1
            pname = info[1] if info else "Unknown"
            combined.setdefault(pid, {"product_id": pid, "product_name": pname, "qty_sold": 0.0, "revenue": 0.0})
            combined[pid]["qty_sold"] += g.get("qty") or 0.0
            combined[pid]["revenue"] += g.get("price_subtotal") or 0.0

        result = sorted(combined.values(), key=lambda x: x["revenue"], reverse=True)
        for r in result[:limit]:
            r["qty_sold"] = float_round(r["qty_sold"], 2)
            r["revenue"] = float_round(r["revenue"], 2)
        return result[:limit]

    @api.model
    def get_sales_by_category(self, filters):
        sol_model = self.env["sale.order.line"].sudo()
        pol_model = self.env["pos.lite.order.line"].sudo()
        so_domain = self._get_order_line_domain(filters)
        pos_domain = self._get_pos_order_line_domain(filters)

        so_groups = sol_model.read_group(
            so_domain,
            ["price_subtotal:sum"],
            ["product_id"],
            lazy=False,
        )
        pos_groups = pol_model.read_group(
            pos_domain,
            ["price_subtotal:sum"],
            ["product_id"],
            lazy=False,
        )

        def _build_category_map(groups):
            cat_map = {}
            product_ids = [
                g["product_id"][0] for g in groups if g.get("product_id")
            ]
            if product_ids:
                products = self.env["product.product"].sudo().browse(product_ids)
                for p in products:
                    cat = p.categ_id
                    cat_map[p.id] = {
                        "category_id": cat.id if cat else False,
                        "category_name": cat.display_name if cat else "Uncategorized",
                        "revenue": 0.0,
                    }
            for g in groups:
                pid = g["product_id"][0] if g.get("product_id") else False
                if pid not in cat_map:
                    cat_map[pid] = {"category_id": False, "category_name": "Uncategorized", "revenue": 0.0}
                cat_map[pid]["revenue"] += g.get("price_subtotal") or 0.0
            return cat_map

        so_cat_map = _build_category_map(so_groups)
        pos_cat_map = _build_category_map(pos_groups)

        combined = {}
        for pid, info in so_cat_map.items():
            combined[info["category_id"]] = combined.get(info["category_id"], {
                "category_id": info["category_id"],
                "category_name": info["category_name"],
                "revenue": 0.0,
            })
            combined[info["category_id"]]["revenue"] += info["revenue"]
        for pid, info in pos_cat_map.items():
            combined[info["category_id"]] = combined.get(info["category_id"], {
                "category_id": info["category_id"],
                "category_name": info["category_name"],
                "revenue": 0.0,
            })
            combined[info["category_id"]]["revenue"] += info["revenue"]

        result = sorted(combined.values(), key=lambda x: x["revenue"], reverse=True)
        for r in result:
            r["revenue"] = float_round(r["revenue"], 2)
        return result

    @api.model
    def get_sales_by_salesperson(self, filters):
        so_model = self.env["sale.order"].sudo()
        pos_model = self.env["pos.lite.order"].sudo()
        so_domain = self._get_sale_order_domain(filters)
        pos_domain = self._get_pos_order_domain(filters)

        so_groups = so_model.read_group(
            so_domain, ["amount_total:sum", "__count"], ["user_id"], lazy=False
        )
        pos_groups = pos_model.read_group(
            pos_domain, ["amount_total:sum", "__count"], ["employee_id"], lazy=False
        )

        emp_ids = list(set(
            g["employee_id"][0] for g in pos_groups if g.get("employee_id")
        ))
        emp_map = {}
        if emp_ids:
            employees = self.env["hr.employee"].sudo().browse(emp_ids)
            emp_map = {e.id: (e.user_id.id, e.user_id.name) for e in employees}

        combined = {}
        for g in so_groups:
            info = g.get("user_id")
            uid = info[0] if info else False
            uname = info[1] if info else "Unassigned"
            key = uid if uid else -1
            combined.setdefault(key, {"user_id": uid, "user_name": uname, "revenue": 0.0, "order_count": 0})
            combined[key]["revenue"] += g.get("amount_total") or 0.0
            combined[key]["order_count"] += g.get("__count") or 0
        for g in pos_groups:
            emp_info = g.get("employee_id")
            eid = emp_info[0] if emp_info else False
            uid, uname = emp_map.get(eid, (False, "Unassigned"))
            key = uid if uid else -1
            combined.setdefault(key, {"user_id": uid, "user_name": uname, "revenue": 0.0, "order_count": 0})
            combined[key]["revenue"] += g.get("amount_total") or 0.0
            combined[key]["order_count"] += g.get("__count") or 0

        result = []
        today = fields.Date.context_today(self)
        for uid, data in combined.items():
            target_amount = 0.0
            if uid and uid > 0:
                target_domain = [
                    ("state", "=", "confirmed"),
                    ("date_start", "<=", today),
                    ("date_end", ">=", today),
                    ("user_id", "=", uid),
                    ("company_id", "=", self.env.company.id),
                ]
                targets = self.env["sales.target"].sudo().search(target_domain)
                target_amount = sum(targets.mapped("target_amount"))
            result.append({
                "user_id": data["user_id"],
                "user_name": data["user_name"],
                "revenue": float_round(data["revenue"], 2),
                "order_count": data["order_count"],
                "target_amount": float_round(target_amount, 2),
            })
        result.sort(key=lambda x: x["revenue"], reverse=True)
        return result

    @api.model
    def get_order_status(self, filters):
        so_model = self.env["sale.order"].sudo()
        pos_model = self.env["pos.lite.order"].sudo()

        base_domain = [
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            base_domain.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            base_domain.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            base_domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            base_domain.append(("team_id", "=", filters["team_id"]))
        if filters.get("partner_id"):
            base_domain.append(("partner_id", "=", filters["partner_id"]))
        if filters.get("category_id"):
            base_domain.append(
                ("order_line.product_id.categ_id", "child_of", filters["category_id"])
            )

        pos_base = [
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            pos_base.append(("date_order", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            pos_base.append(("date_order", "<=", end))
        if filters.get("salesperson_id"):
            pos_base.append(("employee_id.user_id", "=", filters["salesperson_id"]))
        if filters.get("partner_id"):
            pos_base.append(("partner_id", "=", filters["partner_id"]))

        status_data = []
        for state, label in [
            ("draft", "Quotation"),
            ("sent", "Quotation Sent"),
            ("sale", "Sales Order"),
            ("done", "Locked"),
            ("cancel", "Cancelled"),
        ]:
            state_domain = base_domain + [("state", "=", state)]
            agg = so_model.read_group(state_domain, ["amount_total:sum", "__count"], [])[0]
            so_count = agg.get("__count") or 0
            so_total = agg.get("amount_total") or 0.0
            status_data.append(
                {
                    "state": state,
                    "label": label,
                    "count": so_count,
                    "total": float_round(so_total, 2),
                }
            )

        pos_states = [
            ("draft", "POS Draft"),
            ("done", "POS Done"),
        ]
        for state, label in pos_states:
            state_domain = pos_base + [("state", "=", state)]
            agg = pos_model.read_group(state_domain, ["amount_total:sum", "__count"], [])[0]
            status_data.append(
                {
                    "state": "pos_" + state,
                    "label": label,
                    "count": agg.get("__count") or 0,
                    "total": float_round(agg.get("amount_total") or 0.0, 2),
                }
            )
        return status_data

    @api.model
    def get_delivery_status(self, filters):
        picking_model = self.env["stock.picking"].sudo()
        base_domain = self._get_delivery_picking_domain(filters)

        status_data = []
        for state, label in [
            ("draft", "Draft"),
            ("confirmed", "Waiting"),
            ("assigned", "Ready"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ]:
            state_domain = base_domain + [("state", "=", state)]
            agg = picking_model.read_group(state_domain, ["__count"], [])[0]
            status_data.append(
                {
                    "state": "del_" + state,
                    "label": label,
                    "count": agg.get("__count") or 0,
                }
            )
        return status_data

    @api.model
    def get_sales_funnel(self, filters):
        lead_model = self.env["crm.lead"].sudo()
        so_model = self.env["sale.order"].sudo()
        inv_model = self.env["account.move"].sudo()

        lead_domain = [
            ("type", "=", "opportunity"),
            ("company_id", "=", self.env.company.id),
        ]
        if filters.get("date_from"):
            lead_domain.append(("create_date", ">=", filters["date_from"]))
        if filters.get("date_to"):
            end = filters["date_to"]
            if len(end) == 10:
                end += " 23:59:59"
            lead_domain.append(("create_date", "<=", end))
        if filters.get("salesperson_id"):
            lead_domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            lead_domain.append(("team_id", "=", filters["team_id"]))

        lead_count = lead_model.search_count(lead_domain)
        lead_agg = lead_model.read_group(lead_domain, ["expected_revenue:sum"], [])[0]
        lead_value = lead_agg.get("expected_revenue") or 0.0

        won_domain = lead_domain + [("probability", "=", 100)]
        won_count = lead_model.search_count(won_domain)
        won_agg = lead_model.read_group(won_domain, ["expected_revenue:sum"], [])[0]
        won_value = won_agg.get("expected_revenue") or 0.0

        so_domain = self._get_sale_order_domain(filters)
        so_agg = so_model.read_group(so_domain, ["amount_total:sum", "__count"], [])[0]
        so_count = so_agg.get("__count") or 0
        so_value = so_agg.get("amount_total") or 0.0

        pos_domain = self._get_pos_order_domain(filters)
        pos_data = self._aggregate_pos(pos_domain)
        total_order_count = so_count + pos_data["count"]
        total_order_value = so_value + pos_data["revenue"]

        inv_domain = self._get_invoice_domain(filters)
        inv_agg = inv_model.read_group(inv_domain, ["amount_total_signed:sum", "__count"], [])[0]
        inv_count = inv_agg.get("__count") or 0
        inv_value = inv_agg.get("amount_total_signed") or 0.0

        paid_domain = inv_domain + [("payment_state", "in", ["paid", "in_payment"])]
        paid_agg = inv_model.read_group(
            paid_domain, ["amount_total_signed:sum", "__count"], [])[0]
        paid_count = paid_agg.get("__count") or 0
        paid_value = paid_agg.get("amount_total_signed") or 0.0

        stages = [
            {
                "name": "Leads/Opportunities",
                "count": lead_count,
                "value": float_round(lead_value, 2),
                "conversion": float_round(
                    (won_count / lead_count * 100.0) if lead_count else 0.0, 1
                ),
            },
            {
                "name": "Won Opportunities",
                "count": won_count,
                "value": float_round(won_value, 2),
                "conversion": float_round(
                    (total_order_count / won_count * 100.0) if won_count else 0.0, 1
                ),
            },
            {
                "name": "Confirmed Orders",
                "count": total_order_count,
                "value": float_round(total_order_value, 2),
                "conversion": float_round(
                    (inv_count / total_order_count * 100.0) if total_order_count else 0.0, 1
                ),
            },
            {
                "name": "Invoiced",
                "count": inv_count,
                "value": float_round(inv_value, 2),
                "conversion": float_round(
                    (paid_count / inv_count * 100.0) if inv_count else 0.0, 1
                ),
            },
            {
                "name": "Paid",
                "count": paid_count,
                "value": float_round(paid_value, 2),
                "conversion": 100.0,
            },
        ]
        return stages

    @api.model
    def get_forecast(self, filters):
        so_model = self.env["sale.order"].sudo()
        pos_model = self.env["pos.lite.order"].sudo()
        today = fields.Date.context_today(self)
        lookback = today - relativedelta(months=12)

        so_domain = [
            ("state", "in", ["sale", "done"]),
            ("company_id", "=", self.env.company.id),
            ("date_order", ">=", str(lookback)),
            ("date_order", "<=", str(today)),
        ]
        if filters.get("salesperson_id"):
            so_domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            so_domain.append(("team_id", "=", filters["team_id"]))

        pos_domain = [
            ("state", "in", ["paid", "done"]),
            ("company_id", "=", self.env.company.id),
            ("is_return", "=", False),
            ("date_order", ">=", str(lookback)),
            ("date_order", "<=", str(today)),
        ]
        if filters.get("salesperson_id"):
            pos_domain.append(("employee_id.user_id", "=", filters["salesperson_id"]))

        so_groups = so_model.read_group(
            so_domain, ["amount_total:sum"], ["date_order:month"], lazy=False
        )
        pos_groups = pos_model.read_group(
            pos_domain, ["amount_total:sum"], ["date_order:month"], lazy=False
        )

        combined = {}
        for g in so_groups:
            key = g.get("date_order:month") or ""
            combined[key] = combined.get(key, 0.0) + (g.get("amount_total") or 0.0)
        for g in pos_groups:
            key = g.get("date_order:month") or ""
            combined[key] = combined.get(key, 0.0) + (g.get("amount_total") or 0.0)

        historical = []
        for key in sorted(combined.keys()):
            historical.append(
                {
                    "period": key,
                    "revenue": float_round(combined[key], 2),
                }
            )

        if len(historical) < 2:
            return {"historical": historical, "forecast": [], "trend": 0.0}

        revenues = [h["revenue"] for h in historical]
        n = len(revenues)
        x_vals = list(range(n))
        sum_x = sum(x_vals)
        sum_y = sum(revenues)
        sum_xy = sum(x * y for x, y in zip(x_vals, revenues))
        sum_x2 = sum(x * x for x in x_vals)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            slope = 0.0
            intercept = sum_y / n
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n

        avg_revenue = sum(revenues) / n
        ss_res = sum((r - (slope * i + intercept)) ** 2 for i, r in enumerate(revenues))
        ss_tot = sum((r - avg_revenue) ** 2 for r in revenues)
        confidence = min(abs(ss_res / ss_tot) if ss_tot else 0.5, 0.5) * avg_revenue

        forecast = []
        for i in range(1, 4):
            future_date = today + relativedelta(months=i)
            future_period = future_date.strftime("%Y-%m")
            predicted = max(slope * (n + i - 1) + intercept, 0.0)
            forecast.append(
                {
                    "period": future_period,
                    "predicted": float_round(predicted, 2),
                    "upper_bound": float_round(predicted + confidence, 2),
                    "lower_bound": float_round(max(predicted - confidence, 0.0), 2),
                }
            )

        trend = float_round(slope, 2)
        return {
            "historical": historical,
            "forecast": forecast,
            "trend": trend,
        }

    @api.model
    def get_monthly_comparison(self, filters):
        so_model = self.env["sale.order"].sudo()
        pos_model = self.env["pos.lite.order"].sudo()
        today = fields.Date.context_today(self)

        months = []
        for i in range(5, -1, -1):
            month_start = today - relativedelta(months=i)
            month_start = month_start.replace(day=1)
            month_end = month_start + relativedelta(months=1) - relativedelta(days=1)

            so_domain = [
                ("state", "in", ["sale", "done"]),
                ("company_id", "=", self.env.company.id),
                ("date_order", ">=", str(month_start)),
                ("date_order", "<=", str(month_end) + " 23:59:59"),
            ]
            if filters.get("salesperson_id"):
                so_domain.append(("user_id", "=", filters["salesperson_id"]))
            if filters.get("team_id"):
                so_domain.append(("team_id", "=", filters["team_id"]))

            pos_domain = [
                ("state", "in", ["paid", "done"]),
                ("company_id", "=", self.env.company.id),
                ("is_return", "=", False),
                ("date_order", ">=", str(month_start)),
                ("date_order", "<=", str(month_end) + " 23:59:59"),
            ]
            if filters.get("salesperson_id"):
                pos_domain.append(("employee_id.user_id", "=", filters["salesperson_id"]))

            so_agg = so_model.read_group(so_domain, ["amount_total:sum", "__count"], [])[0]
            pos_agg = pos_model.read_group(pos_domain, ["amount_total:sum", "__count"], [])[0]

            revenue = (so_agg.get("amount_total") or 0.0) + (pos_agg.get("amount_total") or 0.0)
            count = (so_agg.get("__count") or 0) + (pos_agg.get("__count") or 0)
            months.append(
                {
                    "month": month_start.strftime("%b %Y"),
                    "revenue": float_round(revenue, 2),
                    "order_count": count,
                    "avg_order": float_round(revenue / count if count else 0.0, 2),
                }
            )

        for i in range(1, len(months)):
            prev = months[i - 1]["revenue"]
            curr = months[i]["revenue"]
            if prev:
                months[i]["change_pct"] = float_round(
                    (curr - prev) / prev * 100.0, 1
                )
            else:
                months[i]["change_pct"] = 0.0
        months[0]["change_pct"] = 0.0

        return months

    @api.model
    def _compute_dashboard_data(self, filters):
        return {
            "kpi": self.get_kpi_data(filters),
            "revenue_trend": self.get_revenue_trend(filters),
            "top_customers": self.get_top_customers(filters),
            "top_products": self.get_top_products(filters),
            "sales_by_category": self.get_sales_by_category(filters),
            "sales_by_salesperson": self.get_sales_by_salesperson(filters),
            "order_status": self.get_order_status(filters),
            "delivery_status": self.get_delivery_status(filters),
            "sales_funnel": self.get_sales_funnel(filters),
            "forecast": self.get_forecast(filters),
            "monthly_comparison": self.get_monthly_comparison(filters),
        }

    @api.model
    def _sanitize_filters(self, filters):
        sanitized = dict(filters)
        for key in ("team_id", "salesperson_id", "partner_id", "category_id"):
            val = sanitized.get(key)
            if val and isinstance(val, str) and val.isdigit():
                sanitized[key] = int(val)
        return sanitized

    @api.model
    def get_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
        filters = self._sanitize_filters(filters)
        cache_model = self.env["buz.sales.analytics.cache"]
        key = cache_model._make_key(filters)
        cached = cache_model.get_cached(key)
        if cached is not None:
            return cached
        data = self._compute_dashboard_data(filters)
        cache_model.set_cached(key, data, ttl=30)
        return data

    @api.model
    def get_filter_options(self):
        users = (
            self.env["res.users"]
            .sudo()
            .search([("share", "=", False)], order="name")
        )
        teams = self.env["crm.team"].sudo().search([], order="name")
        categories = self.env["product.category"].sudo().search([], order="name")
        return {
            "salespersons": [
                {"id": u.id, "name": u.display_name} for u in users
            ],
            "teams": [{"id": t.id, "name": t.name} for t in teams],
            "categories": [{"id": c.id, "name": c.display_name} for c in categories],
        }
