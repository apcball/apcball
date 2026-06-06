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
    def get_kpi_data(self, filters):
        so_domain = self._get_sale_order_domain(filters)
        so_model = self.env["sale.order"].sudo()
        inv_model = self.env["account.move"].sudo()
        cache_model = self.env["buz.sales.analytics.cache"]

        so_agg = so_model.read_group(so_domain, ["amount_total:sum"], [])[0]
        total_revenue = so_agg.get("amount_total") or 0.0

        so_count_agg = so_model.read_group(so_domain, ["__count"], [])[0]
        total_orders = so_count_agg.get("__count") or 0

        avg_order = total_revenue / total_orders if total_orders else 0.0

        prev_filters = dict(filters)
        today = fields.Date.context_today(self)
        if filters.get("date_from") and filters.get("date_to"):
            df = fields.Date.from_string(filters["date_from"])
            dt = fields.Date.from_string(filters["date_to"])
            span = (dt - df).days + 1
            prev_filters["date_from"] = str(df - relativedelta(days=span))
            prev_filters["date_to"] = str(df - relativedelta(days=1))

        prev_domain = self._get_sale_order_domain(prev_filters)
        prev_agg = so_model.read_group(prev_domain, ["amount_total:sum"], [])[0]
        prev_revenue = prev_agg.get("amount_total") or 0.0
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

        return {
            "total_revenue": float_round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_order_value": float_round(avg_order, 2),
            "growth_rate": float_round(growth_rate, 2),
            "target_achievement": float_round(target_achievement, 2),
            "outstanding_invoices": float_round(outstanding_invoices, 2),
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
        domain = self._get_sale_order_domain(filters)
        period_type = filters.get("period_type", "monthly")

        groupby_map = {
            "daily": "date_order:day",
            "weekly": "date_order:week",
            "monthly": "date_order:month",
            "quarterly": "date_order:quarter",
        }
        groupby = groupby_map.get(period_type, "date_order:month")

        groups = so_model.read_group(
            domain, ["amount_total:sum"], [groupby], lazy=False
        )
        return [
            {
                "period": g.get(groupby) or "",
                "revenue": float_round(g.get("amount_total") or 0.0, 2),
                "order_count": g.get("__count") or 0,
            }
            for g in sorted(groups, key=lambda x: x.get(groupby) or "")
        ]

    @api.model
    def get_top_customers(self, filters, limit=10):
        so_model = self.env["sale.order"].sudo()
        domain = self._get_sale_order_domain(filters)

        groups = so_model.read_group(
            domain, ["amount_total:sum", "__count"], ["partner_id"], lazy=False
        )
        groups.sort(key=lambda g: g.get("amount_total") or 0.0, reverse=True)
        result = []
        for g in groups[:limit]:
            partner_info = g.get("partner_id")
            result.append(
                {
                    "partner_id": partner_info[0] if partner_info else False,
                    "partner_name": partner_info[1] if partner_info else "Unknown",
                    "total_revenue": float_round(g.get("amount_total") or 0.0, 2),
                    "order_count": g.get("__count") or 0,
                }
            )
        return result

    @api.model
    def get_top_products(self, filters, limit=10):
        sol_model = self.env["sale.order.line"].sudo()
        domain = self._get_order_line_domain(filters)

        groups = sol_model.read_group(
            domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            ["product_id"],
            lazy=False,
        )
        groups.sort(key=lambda g: g.get("price_subtotal") or 0.0, reverse=True)
        result = []
        for g in groups[:limit]:
            prod_info = g.get("product_id")
            result.append(
                {
                    "product_id": prod_info[0] if prod_info else False,
                    "product_name": prod_info[1] if prod_info else "Unknown",
                    "qty_sold": float_round(g.get("product_uom_qty") or 0.0, 2),
                    "revenue": float_round(g.get("price_subtotal") or 0.0, 2),
                }
            )
        return result

    @api.model
    def get_sales_by_category(self, filters):
        sol_model = self.env["sale.order.line"].sudo()
        domain = self._get_order_line_domain(filters)

        groups = sol_model.read_group(
            domain,
            ["price_subtotal:sum"],
            ["product_id"],
            lazy=False,
        )
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
                }
        for g in groups:
            pid = g["product_id"][0] if g.get("product_id") else False
            info = cat_map.get(pid, {"category_id": False, "category_name": "Uncategorized"})
            info["revenue"] = info.get("revenue", 0.0) + (g.get("price_subtotal") or 0.0)
            cat_map[pid] = info

        result = [
            {
                "category_id": v["category_id"],
                "category_name": v["category_name"],
                "revenue": float_round(v["revenue"], 2),
            }
            for v in cat_map.values()
        ]
        result.sort(key=lambda x: x["revenue"], reverse=True)
        return result

    @api.model
    def get_sales_by_salesperson(self, filters):
        so_model = self.env["sale.order"].sudo()
        domain = self._get_sale_order_domain(filters)

        groups = so_model.read_group(
            domain, ["amount_total:sum", "__count"], ["user_id"], lazy=False
        )
        result = []
        for g in groups:
            user_info = g.get("user_id")
            uid = user_info[0] if user_info else False
            uname = user_info[1] if user_info else "Unassigned"
            target_amount = 0.0
            if uid:
                today = fields.Date.context_today(self)
                target_domain = [
                    ("state", "=", "confirmed"),
                    ("date_start", "<=", today),
                    ("date_end", ">=", today),
                    ("user_id", "=", uid),
                    ("company_id", "=", self.env.company.id),
                ]
                targets = self.env["sales.target"].sudo().search(target_domain)
                target_amount = sum(targets.mapped("target_amount"))
            result.append(
                {
                    "user_id": uid,
                    "user_name": uname,
                    "revenue": float_round(g.get("amount_total") or 0.0, 2),
                    "order_count": g.get("__count") or 0,
                    "target_amount": float_round(target_amount, 2),
                }
            )
        result.sort(key=lambda x: x["revenue"], reverse=True)
        return result

    @api.model
    def get_order_status(self, filters):
        so_model = self.env["sale.order"].sudo()
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
            status_data.append(
                {
                    "state": state,
                    "label": label,
                    "count": agg.get("__count") or 0,
                    "total": float_round(agg.get("amount_total") or 0.0, 2),
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
                    (so_count / won_count * 100.0) if won_count else 0.0, 1
                ),
            },
            {
                "name": "Confirmed Orders",
                "count": so_count,
                "value": float_round(so_value, 2),
                "conversion": float_round(
                    (inv_count / so_count * 100.0) if so_count else 0.0, 1
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
        today = fields.Date.context_today(self)
        lookback = today - relativedelta(months=12)
        domain = [
            ("state", "in", ["sale", "done"]),
            ("company_id", "=", self.env.company.id),
            ("date_order", ">=", str(lookback)),
            ("date_order", "<=", str(today)),
        ]
        if filters.get("salesperson_id"):
            domain.append(("user_id", "=", filters["salesperson_id"]))
        if filters.get("team_id"):
            domain.append(("team_id", "=", filters["team_id"]))

        groups = so_model.read_group(
            domain, ["amount_total:sum"], ["date_order:month"], lazy=False
        )

        historical = []
        for g in sorted(groups, key=lambda x: x.get("date_order:month") or ""):
            historical.append(
                {
                    "period": g.get("date_order:month") or "",
                    "revenue": float_round(g.get("amount_total") or 0.0, 2),
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
        today = fields.Date.context_today(self)

        months = []
        for i in range(5, -1, -1):
            month_start = today - relativedelta(months=i)
            month_start = month_start.replace(day=1)
            month_end = month_start + relativedelta(months=1) - relativedelta(days=1)

            current_domain = [
                ("state", "in", ["sale", "done"]),
                ("company_id", "=", self.env.company.id),
                ("date_order", ">=", str(month_start)),
                ("date_order", "<=", str(month_end) + " 23:59:59"),
            ]
            if filters.get("salesperson_id"):
                current_domain.append(("user_id", "=", filters["salesperson_id"]))
            if filters.get("team_id"):
                current_domain.append(("team_id", "=", filters["team_id"]))

            agg = so_model.read_group(
                current_domain, ["amount_total:sum", "__count"], [])[0]
            revenue = agg.get("amount_total") or 0.0
            count = agg.get("__count") or 0
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
            "sales_funnel": self.get_sales_funnel(filters),
            "forecast": self.get_forecast(filters),
            "monthly_comparison": self.get_monthly_comparison(filters),
        }

    @api.model
    def get_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
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
