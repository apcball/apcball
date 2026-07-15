from datetime import date, datetime, timedelta

from odoo import http
from odoo.http import request

# ----------------------------------------------------------------------
# Measure definitions (single source of truth)
#
#   Stage        Model               Domain                                Amount                          Date
#   -----        -----               ------                                ------                          ----
#   Quotation    sale.order          state in draft/sent/sale/done         amount_untaxed                  date_order
#   Sales Order  sale.order          state in sale/done                    amount_untaxed                  date_order
#                pos.lite.order      state done                            amount_untaxed (signed)         date_order
#   Delivery     stock.move (done)   linked sale.order.line                quantity x price_unit           picking date_done
#                pos.lite.order      state done + picking done             amount_untaxed (signed)         picking date_done
#   Invoice      account.move        out_invoice/out_refund posted         amount_untaxed_signed           invoice_date
#   Payment      account.move        out_invoice/out_refund posted         total_signed - residual_signed  invoice_date (collection basis)
#   Backlog      sale.order.line     order state=sale, delivered < ordered remaining x price_unit          date_order
#   Overdue      account.move        posted, residual > 0, due < today     amount_residual_signed          invoice_date_due
#
# Salesperson / team / customer filters map to user_id / team_id /
# partner_id on sale.order and invoice_user_id / team_id / partner_id
# on account.move.  POS orders resolve salesperson via employee user.
# ----------------------------------------------------------------------


class SpeDashboardController(http.Controller):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
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

    def _company_ids(self, filters):
        if filters.get("company_id"):
            return [int(filters["company_id"])]
        return request.env.companies.ids

    def _dates(self, filters):
        return (
            self._to_datetime(filters.get("date_from")),
            self._to_datetime(filters.get("date_to"), end_of_day=True),
        )

    def _prev_filters(self, filters):
        """Same filters shifted back by an equal-length period."""
        d_from, d_to = self._dates(filters)
        if not d_from or not d_to:
            return None
        span = d_to - d_from + timedelta(seconds=1)
        return dict(
            filters,
            date_from=(d_from - span).strftime("%Y-%m-%d"),
            date_to=(d_to - span).strftime("%Y-%m-%d"),
        )

    def _pos_invoice_move_ids(self, filters):
        """account.move ids created by done POS Lite orders (company scope)."""
        rows = request.env["pos.lite.order"].sudo().search_read(
            [("state", "=", "done"),
             ("company_id", "in", self._company_ids(filters)),
             ("invoice_id", "!=", False)],
            ["invoice_id"],
        )
        return [r["invoice_id"][0] for r in rows]

    # -------------------- ORM domains --------------------
    def _so_domain(self, filters, states=("sale", "done")):
        d_from, d_to = self._dates(filters)
        domain = [
            ("company_id", "in", self._company_ids(filters)),
            ("state", "in", list(states)),
        ]
        if d_from:
            domain.append(("date_order", ">=", d_from))
        if d_to:
            domain.append(("date_order", "<=", d_to))
        if filters.get("salesperson_id"):
            domain.append(("user_id", "=", int(filters["salesperson_id"])))
        if filters.get("team_id"):
            domain.append(("team_id", "=", int(filters["team_id"])))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", int(filters["partner_id"])))
        return domain

    def _pos_domain(self, filters, with_dates=True):
        domain = [
            ("state", "=", "done"),
            ("company_id", "in", self._company_ids(filters)),
        ]
        if with_dates:
            d_from, d_to = self._dates(filters)
            if d_from:
                domain.append(("date_order", ">=", d_from))
            if d_to:
                domain.append(("date_order", "<=", d_to))
        if filters.get("salesperson_id"):
            domain.append(("employee_id.user_id", "=", int(filters["salesperson_id"])))
        if filters.get("team_id"):
            domain.append(("employee_id.user_id.sale_team_id", "=", int(filters["team_id"])))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", int(filters["partner_id"])))
        return domain

    def _move_domain(self, filters, date_field="invoice_date"):
        d_from, d_to = self._dates(filters)
        domain = [
            ("company_id", "in", self._company_ids(filters)),
            ("move_type", "in", ["out_invoice", "out_refund"]),
            ("state", "=", "posted"),
        ]
        if d_from:
            domain.append((date_field, ">=", d_from.date()))
        if d_to:
            domain.append((date_field, "<=", d_to.date()))
        if filters.get("salesperson_id"):
            domain.append(("invoice_user_id", "=", int(filters["salesperson_id"])))
        if filters.get("team_id"):
            domain.append(("team_id", "=", int(filters["team_id"])))
        if filters.get("partner_id"):
            domain.append(("partner_id", "=", int(filters["partner_id"])))
        source = filters.get("source")
        if source in ("sale", "pos"):
            pos_ids = self._pos_invoice_move_ids(filters)
            if source == "pos":
                domain.append(("id", "in", pos_ids or [0]))
            else:
                domain.append(("id", "not in", pos_ids or [0]))
        return domain

    # -------------------- SQL filter fragments --------------------
    def _sql_so_filters(self, filters, alias="so", date_col=None):
        """WHERE fragments + params for a sale_order alias."""
        clauses, params = [], []
        clauses.append(f"{alias}.company_id IN %s")
        params.append(tuple(self._company_ids(filters)))
        d_from, d_to = self._dates(filters)
        if date_col:
            if d_from:
                clauses.append(f"{date_col} >= %s")
                params.append(d_from)
            if d_to:
                clauses.append(f"{date_col} <= %s")
                params.append(d_to)
        if filters.get("salesperson_id"):
            clauses.append(f"{alias}.user_id = %s")
            params.append(int(filters["salesperson_id"]))
        if filters.get("team_id"):
            clauses.append(f"{alias}.team_id = %s")
            params.append(int(filters["team_id"]))
        if filters.get("partner_id"):
            clauses.append(f"{alias}.partner_id = %s")
            params.append(int(filters["partner_id"]))
        return clauses, params

    def _sql_pos_filters(self, filters, date_col=None):
        clauses, params = [], []
        clauses.append("po.state = 'done'")
        clauses.append("po.company_id IN %s")
        params.append(tuple(self._company_ids(filters)))
        d_from, d_to = self._dates(filters)
        if date_col:
            if d_from:
                clauses.append(f"{date_col} >= %s")
                params.append(d_from)
            if d_to:
                clauses.append(f"{date_col} <= %s")
                params.append(d_to)
        if filters.get("salesperson_id"):
            clauses.append("emp.user_id = %s")
            params.append(int(filters["salesperson_id"]))
        if filters.get("team_id"):
            clauses.append("ru.sale_team_id = %s")
            params.append(int(filters["team_id"]))
        if filters.get("partner_id"):
            clauses.append("po.partner_id = %s")
            params.append(int(filters["partner_id"]))
        return clauses, params

    # ------------------------------------------------------------------
    # Measure primitives - each returns list of dicts
    # [{key, amount, count}] grouped by `group` in
    # (None, "bucket:<day|month>", "user", "company", "partner").
    # ------------------------------------------------------------------
    def _so_rows(self, filters, group=None, bucket="day", states=("sale", "done")):
        """Confirmed sale orders (+ POS done orders unless source='sale')."""
        rows = {}
        source = filters.get("source")
        if source != "pos":
            group_sql = {
                None: "1",
                "bucket": f"date_trunc('{bucket}', so.date_order)::date",
                "user": "so.user_id",
                "company": "so.company_id",
                "partner": "so.partner_id",
            }[group]
            clauses, params = self._sql_so_filters(filters, "so", "so.date_order")
            clauses.append("so.state IN %s")
            params.append(tuple(states))
            request.env.cr.execute(
                f"""
                SELECT {group_sql} AS key,
                       COALESCE(SUM(so.amount_untaxed), 0) AS amount,
                       COUNT(*) AS cnt
                FROM sale_order so
                WHERE {' AND '.join(clauses)}
                GROUP BY 1
                """,
                tuple(params),
            )
            for r in request.env.cr.dictfetchall():
                rows[r["key"]] = {"amount": r["amount"], "count": r["cnt"]}
        if source != "sale":
            self._merge_pos_rows(rows, filters, group, bucket, "po.date_order")
        return self._rows_out(rows)

    def _merge_pos_rows(self, rows, filters, group, bucket, date_col):
        group_sql = {
            None: "1",
            "bucket": f"date_trunc('{bucket}', {date_col})::date",
            "user": "emp.user_id",
            "company": "po.company_id",
            "partner": "po.partner_id",
        }[group]
        clauses, params = self._sql_pos_filters(filters, date_col)
        joins = """
            LEFT JOIN hr_employee emp ON emp.id = po.employee_id
            LEFT JOIN res_users ru ON ru.id = emp.user_id
        """
        if date_col.startswith("sp."):
            joins += " JOIN stock_picking sp ON sp.id = po.picking_id AND sp.state = 'done'"
        request.env.cr.execute(
            f"""
            SELECT {group_sql} AS key,
                   COALESCE(SUM(CASE WHEN po.is_return THEN -po.amount_untaxed
                                     ELSE po.amount_untaxed END), 0) AS amount,
                   COUNT(*) AS cnt
            FROM pos_lite_order po
            {joins}
            WHERE {' AND '.join(clauses)}
            GROUP BY 1
            """,
            tuple(params),
        )
        for r in request.env.cr.dictfetchall():
            cur = rows.setdefault(r["key"], {"amount": 0.0, "count": 0})
            cur["amount"] += r["amount"]
            cur["count"] += r["cnt"]

    def _delivery_rows(self, filters, group=None, bucket="day"):
        """Value delivered = done move qty x SO line unit price (+ POS)."""
        rows = {}
        source = filters.get("source")
        if source != "pos":
            group_sql = {
                None: "1",
                "bucket": f"date_trunc('{bucket}', sp.date_done)::date",
                "user": "so.user_id",
                "company": "so.company_id",
                "partner": "so.partner_id",
            }[group]
            clauses, params = self._sql_so_filters(filters, "so", "sp.date_done")
            request.env.cr.execute(
                f"""
                SELECT {group_sql} AS key,
                       COALESCE(SUM(sm.quantity * sol.price_unit
                                    * (1 - COALESCE(sol.discount, 0) / 100.0)), 0) AS amount,
                       COUNT(DISTINCT sp.id) AS cnt
                FROM stock_move sm
                JOIN stock_picking sp ON sp.id = sm.picking_id
                JOIN sale_order_line sol ON sol.id = sm.sale_line_id
                JOIN sale_order so ON so.id = sol.order_id
                WHERE sm.state = 'done'
                  AND sp.state = 'done'
                  AND {' AND '.join(clauses)}
                GROUP BY 1
                """,
                tuple(params),
            )
            for r in request.env.cr.dictfetchall():
                rows[r["key"]] = {"amount": r["amount"], "count": r["cnt"]}
        if source != "sale":
            self._merge_pos_rows(rows, filters, group, bucket, "sp.date_done")
        return self._rows_out(rows)

    def _invoice_rows(self, filters, group=None, bucket="day", measure="invoice"):
        """measure='invoice' -> net untaxed; 'payment' -> collected amount."""
        group_sql = {
            None: "1",
            "bucket": f"date_trunc('{bucket}', am.invoice_date)::date",
            "user": "am.invoice_user_id",
            "company": "am.company_id",
            "partner": "am.partner_id",
        }[group]
        amount_sql = (
            "SUM(am.amount_untaxed_signed)" if measure == "invoice"
            else "SUM(am.amount_total_signed - am.amount_residual_signed)"
        )
        clauses, params = self._move_sql_filters(filters, "am.invoice_date")
        request.env.cr.execute(
            f"""
            SELECT {group_sql} AS key,
                   COALESCE({amount_sql}, 0) AS amount,
                   COUNT(*) AS cnt
            FROM account_move am
            WHERE {' AND '.join(clauses)}
            GROUP BY 1
            """,
            tuple(params),
        )
        return self._rows_out({
            r["key"]: {"amount": r["amount"], "count": r["cnt"]}
            for r in request.env.cr.dictfetchall()
        })

    def _move_sql_filters(self, filters, date_col):
        clauses = [
            "am.state = 'posted'",
            "am.move_type IN ('out_invoice', 'out_refund')",
            "am.company_id IN %s",
        ]
        params = [tuple(self._company_ids(filters))]
        d_from, d_to = self._dates(filters)
        if d_from:
            clauses.append(f"{date_col} >= %s")
            params.append(d_from.date())
        if d_to:
            clauses.append(f"{date_col} <= %s")
            params.append(d_to.date())
        if filters.get("salesperson_id"):
            clauses.append("am.invoice_user_id = %s")
            params.append(int(filters["salesperson_id"]))
        if filters.get("team_id"):
            clauses.append("am.team_id = %s")
            params.append(int(filters["team_id"]))
        if filters.get("partner_id"):
            clauses.append("am.partner_id = %s")
            params.append(int(filters["partner_id"]))
        source = filters.get("source")
        if source in ("sale", "pos"):
            pos_ids = tuple(self._pos_invoice_move_ids(filters)) or (0,)
            clauses.append("am.id IN %s" if source == "pos" else "am.id NOT IN %s")
            params.append(pos_ids)
        return clauses, params

    def _backlog(self, filters):
        """Confirmed-not-delivered value (sale orders only)."""
        if filters.get("source") == "pos":
            return {"amount": 0.0, "count": 0}
        clauses, params = self._sql_so_filters(filters, "so", "so.date_order")
        request.env.cr.execute(
            f"""
            SELECT COALESCE(SUM((sol.product_uom_qty - COALESCE(sol.qty_delivered, 0))
                                * sol.price_unit
                                * (1 - COALESCE(sol.discount, 0) / 100.0)), 0) AS amount,
                   COUNT(DISTINCT so.id) AS cnt
            FROM sale_order_line sol
            JOIN sale_order so ON so.id = sol.order_id
            WHERE so.state = 'sale'
              AND sol.display_type IS NULL
              AND COALESCE(sol.qty_delivered, 0) < sol.product_uom_qty
              AND {' AND '.join(clauses)}
            """,
            tuple(params),
        )
        r = request.env.cr.dictfetchall()[0]
        return {"amount": self._round(r["amount"]), "count": r["cnt"]}

    def _overdue(self, filters):
        """Posted invoices past due with open residual (due date in range ignored)."""
        clauses, params = self._move_sql_filters(dict(filters, date_from=False, date_to=False),
                                                 "am.invoice_date")
        request.env.cr.execute(
            f"""
            SELECT COALESCE(SUM(am.amount_residual_signed), 0) AS amount,
                   COUNT(*) AS cnt
            FROM account_move am
            WHERE am.amount_residual > 0
              AND am.invoice_date_due < %s
              AND {' AND '.join(clauses)}
            """,
            tuple([date.today()] + params),
        )
        r = request.env.cr.dictfetchall()[0]
        return {"amount": self._round(r["amount"]), "count": r["cnt"]}

    @staticmethod
    def _rows_out(rows):
        out = []
        for key, val in rows.items():
            out.append({
                "key": key.isoformat() if isinstance(key, (date, datetime)) else key,
                "amount": round(float(val["amount"] or 0.0), 2),
                "count": val["count"],
            })
        out.sort(key=lambda r: (r["key"] is None, str(r["key"])))
        return out

    @staticmethod
    def _total(rows):
        return {
            "amount": round(sum(r["amount"] for r in rows), 2),
            "count": sum(r["count"] for r in rows),
        }

    def _all_measures(self, filters):
        return {
            "so": self._total(self._so_rows(filters)),
            "delivery": self._total(self._delivery_rows(filters)),
            "invoice": self._total(self._invoice_rows(filters, measure="invoice")),
            "payment": self._total(self._invoice_rows(filters, measure="payment")),
            "backlog": self._backlog(filters),
            "overdue": self._overdue(filters),
        }

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    @http.route("/spe/dashboard/filter_options", type="json", auth="user")
    def filter_options(self, **kw):
        env = request.env
        companies = [{"id": c.id, "name": c.name} for c in env.companies]
        teams = env["crm.team"].search_read(
            [("company_id", "in", env.companies.ids + [False])], ["name"])
        salespersons = env["res.users"].search_read(
            [("share", "=", False)], ["name"], order="name")
        partners = env["res.partner"].search_read(
            [("customer_rank", ">", 0)], ["name"], order="name", limit=500)
        return {
            "companies": companies,
            "teams": teams,
            "salespersons": salespersons,
            "partners": partners,
        }

    @http.route("/spe/dashboard/overview", type="json", auth="user")
    def overview(self, **kw):
        filters = kw.get("filters", {}) or {}
        cur = self._all_measures(filters)
        prev_filters = self._prev_filters(filters)
        prev = self._all_measures(prev_filters) if prev_filters else {}

        quotation = self._total(self._so_rows(
            filters, states=("draft", "sent", "sale", "done")))

        def _pct(stage_amount, base_amount):
            return round(stage_amount / base_amount * 100.0, 1) if base_amount else 0.0

        funnel = []
        chain = [
            ("quotation", "Quotation", quotation["amount"]),
            ("so", "Sales Order", cur["so"]["amount"]),
            ("delivery", "Delivery Order", cur["delivery"]["amount"]),
            ("invoice", "Invoice", cur["invoice"]["amount"]),
            ("payment", "Payment", cur["payment"]["amount"]),
        ]
        for i, (key, label, amount) in enumerate(chain):
            funnel.append({
                "key": key, "label": label, "amount": amount,
                "pct": _pct(amount, chain[i - 1][2]) if i else 100.0,
            })

        # This month vs last month (independent of the filter dates).
        today = date.today()
        m_start = today.replace(day=1)
        lm_end = m_start - timedelta(days=1)
        lm_start = lm_end.replace(day=1)
        this_m = dict(filters, date_from=m_start.isoformat(), date_to=today.isoformat())
        last_m = dict(filters, date_from=lm_start.isoformat(), date_to=lm_end.isoformat())
        comparison = {}
        for key, fn in (
            ("so", lambda f: self._total(self._so_rows(f))),
            ("delivery", lambda f: self._total(self._delivery_rows(f))),
            ("invoice", lambda f: self._total(self._invoice_rows(f, measure="invoice"))),
            ("payment", lambda f: self._total(self._invoice_rows(f, measure="payment"))),
        ):
            cur_v = fn(this_m)["amount"]
            prev_v = fn(last_m)["amount"]
            delta = ((cur_v - prev_v) / abs(prev_v) * 100.0) if prev_v else 0.0
            comparison[key] = {
                "current": cur_v, "previous": prev_v, "delta": round(delta, 1),
            }
        # Daily sparkline data for this month.
        spark = {
            "so": self._so_rows(this_m, group="bucket", bucket="day"),
            "delivery": self._delivery_rows(this_m, group="bucket", bucket="day"),
            "invoice": self._invoice_rows(this_m, group="bucket", bucket="day"),
            "payment": self._invoice_rows(this_m, group="bucket", bucket="day",
                                          measure="payment"),
        }
        return {"kpi": cur, "kpi_prev": prev, "funnel": funnel,
                "comparison": comparison, "spark": spark}

    @http.route("/spe/dashboard/charts", type="json", auth="user")
    def charts(self, **kw):
        filters = kw.get("filters", {}) or {}
        d_from, d_to = self._dates(filters)
        bucket = "day"
        if d_from and d_to and (d_to - d_from).days > 62:
            bucket = "month"

        trend = {
            "bucket": bucket,
            "so": self._so_rows(filters, group="bucket", bucket=bucket),
            "delivery": self._delivery_rows(filters, group="bucket", bucket=bucket),
            "invoice": self._invoice_rows(filters, group="bucket", bucket=bucket),
            "payment": self._invoice_rows(filters, group="bucket", bucket=bucket,
                                          measure="payment"),
        }

        companies = {c.id: c.name for c in request.env.companies}
        by_company = {}
        for key, rows in (
            ("so", self._so_rows(filters, group="company")),
            ("delivery", self._delivery_rows(filters, group="company")),
            ("invoice", self._invoice_rows(filters, group="company")),
            ("payment", self._invoice_rows(filters, group="company", measure="payment")),
        ):
            for r in rows:
                cid = r["key"]
                if cid not in companies:
                    continue
                entry = by_company.setdefault(
                    cid, {"name": companies[cid], "so": 0, "delivery": 0,
                          "invoice": 0, "payment": 0})
                entry[key] = r["amount"]

        top_rows = self._so_rows(filters, group="partner")
        top_rows.sort(key=lambda r: r["amount"], reverse=True)
        top_rows = [r for r in top_rows if r["key"]][:10]
        partner_names = {
            p.id: p.name
            for p in request.env["res.partner"].browse([r["key"] for r in top_rows])
        }
        top_customers = [
            {"id": r["key"], "name": partner_names.get(r["key"], "?"),
             "amount": r["amount"]}
            for r in top_rows
        ]

        by_category = self._by_category(filters)

        return {
            "trend": trend,
            "by_company": list(by_company.values()),
            "top_customers": top_customers,
            "by_category": by_category,
        }

    def _by_category(self, filters, limit=8):
        """Confirmed order value grouped by product category (sale + POS)."""
        totals = {}
        source = filters.get("source")
        if source != "pos":
            clauses, params = self._sql_so_filters(filters, "so", "so.date_order")
            request.env.cr.execute(
                f"""
                SELECT pt.categ_id AS key, SUM(sol.price_subtotal) AS amount
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                JOIN product_product pp ON pp.id = sol.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE so.state IN ('sale', 'done')
                  AND sol.display_type IS NULL
                  AND {' AND '.join(clauses)}
                GROUP BY 1
                """,
                tuple(params),
            )
            for r in request.env.cr.dictfetchall():
                totals[r["key"]] = totals.get(r["key"], 0.0) + float(r["amount"] or 0)
        if source != "sale":
            clauses, params = self._sql_pos_filters(filters, "po.date_order")
            request.env.cr.execute(
                f"""
                SELECT pt.categ_id AS key,
                       SUM(CASE WHEN po.is_return THEN -pol.price_subtotal
                                ELSE pol.price_subtotal END) AS amount
                FROM pos_lite_order_line pol
                JOIN pos_lite_order po ON po.id = pol.order_id
                LEFT JOIN hr_employee emp ON emp.id = po.employee_id
                LEFT JOIN res_users ru ON ru.id = emp.user_id
                JOIN product_product pp ON pp.id = pol.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE {' AND '.join(clauses)}
                GROUP BY 1
                """,
                tuple(params),
            )
            for r in request.env.cr.dictfetchall():
                totals[r["key"]] = totals.get(r["key"], 0.0) + float(r["amount"] or 0)
        items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
        head, tail = items[:limit], items[limit:]
        names = {
            c.id: c.display_name
            for c in request.env["product.category"].browse(
                [k for k, _ in head if k])
        }
        out = [{"name": names.get(k, "Undefined"), "amount": round(v, 2)}
               for k, v in head]
        if tail:
            out.append({"name": "Others", "amount": round(sum(v for _, v in tail), 2)})
        return out

    @http.route("/spe/dashboard/salesperson_table", type="json", auth="user")
    def salesperson_table(self, **kw):
        filters = kw.get("filters", {}) or {}
        merged = {}

        def _merge(key, rows):
            for r in rows:
                uid = r["key"]
                if not uid:
                    continue
                entry = merged.setdefault(
                    uid, {"so": 0, "delivery": 0, "invoice": 0, "payment": 0,
                          "target": 0})
                entry[key] += r["amount"]

        _merge("so", self._so_rows(filters, group="user"))
        _merge("delivery", self._delivery_rows(filters, group="user"))
        _merge("invoice", self._invoice_rows(filters, group="user"))
        _merge("payment", self._invoice_rows(filters, group="user", measure="payment"))

        # Targets overlapping the filter period.
        target_domain = [
            ("company_id", "in", self._company_ids(filters)),
            ("state", "=", "confirmed"),
            ("user_id", "!=", False),
        ]
        if filters.get("date_from"):
            target_domain.append(("date_end", ">=", filters["date_from"]))
        if filters.get("date_to"):
            target_domain.append(("date_start", "<=", filters["date_to"]))
        targets = request.env["buz.sales.performance.target"].read_group(
            target_domain, ["target_amount:sum"], ["user_id"])
        for t in targets:
            if t["user_id"]:
                merged.setdefault(
                    t["user_id"][0],
                    {"so": 0, "delivery": 0, "invoice": 0, "payment": 0, "target": 0},
                )["target"] = t["target_amount"] or 0

        users = {
            u.id: u.name
            for u in request.env["res.users"].sudo().browse(list(merged))
        }
        rows = []
        for uid, vals in merged.items():
            target = vals["target"]
            rows.append({
                "id": uid,
                "name": users.get(uid, "?"),
                "so": self._round(vals["so"]),
                "delivery": self._round(vals["delivery"]),
                "invoice": self._round(vals["invoice"]),
                "payment": self._round(vals["payment"]),
                "target": self._round(target),
                "achieve": round(vals["invoice"] / target * 100.0, 1) if target else 0.0,
            })
        rows.sort(key=lambda r: r["so"], reverse=True)
        return rows[:20]

    @http.route("/spe/dashboard/followups", type="json", auth="user")
    def followups(self, **kw):
        filters = kw.get("filters", {}) or {}
        kind = kw.get("kind", "so_follow_up")
        limit = int(kw.get("limit", 20))
        env = request.env
        rows = []

        if kind == "so_follow_up":
            orders = env["sale.order"].search(
                self._so_domain(filters, states=("sale",))
                + [("picking_ids.state", "in", ("waiting", "confirmed", "assigned"))],
                limit=limit, order="date_order desc")
            rows = [{
                "res_model": "sale.order", "id": o.id, "name": o.name,
                "partner": o.partner_id.display_name,
                "date": o.date_order and o.date_order.date().isoformat(),
                "salesperson": o.user_id.name or "",
                "company": o.company_id.name,
                "amount": self._round(o.amount_total),
                "status": "Waiting Delivery",
                "status_class": "warning",
            } for o in orders]

        elif kind == "deliveries":
            pickings = env["stock.picking"].search([
                ("company_id", "in", self._company_ids(filters)),
                ("picking_type_code", "=", "outgoing"),
                ("state", "in", ("waiting", "confirmed", "assigned")),
            ], limit=limit, order="scheduled_date")
            rows = [{
                "res_model": "stock.picking", "id": p.id, "name": p.name,
                "partner": p.partner_id.display_name or "",
                "date": p.scheduled_date and p.scheduled_date.date().isoformat(),
                "salesperson": p.sale_id.user_id.name or "",
                "company": p.company_id.name,
                "amount": 0.0,
                "status": dict(p._fields["state"]._description_selection(env)).get(
                    p.state, p.state),
                "status_class": "info" if p.state == "assigned" else "warning",
            } for p in pickings]

        elif kind == "invoices_to_process":
            orders = env["sale.order"].search(
                self._so_domain(filters, states=("sale", "done"))
                + [("invoice_status", "=", "to invoice")],
                limit=limit, order="date_order desc")
            rows = [{
                "res_model": "sale.order", "id": o.id, "name": o.name,
                "partner": o.partner_id.display_name,
                "date": o.date_order and o.date_order.date().isoformat(),
                "salesperson": o.user_id.name or "",
                "company": o.company_id.name,
                "amount": self._round(o.amount_total),
                "status": "To Invoice",
                "status_class": "warning",
            } for o in orders]

        elif kind == "overdue":
            moves = env["account.move"].search([
                ("company_id", "in", self._company_ids(filters)),
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("amount_residual", ">", 0),
                ("invoice_date_due", "<", date.today().isoformat()),
            ], limit=limit, order="invoice_date_due")
            today = date.today()
            rows = [{
                "res_model": "account.move", "id": m.id, "name": m.name,
                "partner": m.partner_id.display_name,
                "date": m.invoice_date_due and m.invoice_date_due.isoformat(),
                "salesperson": m.invoice_user_id.name or "",
                "company": m.company_id.name,
                "amount": self._round(m.amount_residual),
                "status": "%d Days Overdue" % (today - m.invoice_date_due).days
                if m.invoice_date_due else "Overdue",
                "status_class": "danger",
            } for m in moves]

        # Next activity per record.
        if rows:
            model = rows[0]["res_model"]
            acts = env["mail.activity"].search_read(
                [("res_model", "=", model),
                 ("res_id", "in", [r["id"] for r in rows])],
                ["res_id", "summary", "activity_type_id", "date_deadline"],
                order="date_deadline",
            )
            by_res = {}
            for a in acts:
                by_res.setdefault(a["res_id"], a)
            for r in rows:
                act = by_res.get(r["id"])
                r["activity"] = (
                    act and (act["summary"]
                             or (act["activity_type_id"] and act["activity_type_id"][1])
                             or "")) or ""
                r["activity_date"] = (
                    act and act["date_deadline"] and act["date_deadline"].isoformat()
                    or "")
        return rows

    @http.route("/spe/dashboard/action_drill", type="json", auth="user")
    def action_drill(self, **kw):
        filters = kw.get("filters", {}) or {}
        kind = kw.get("kind")

        def _act(name, model, domain, view_mode="tree,form"):
            views = [[False, v if v != "tree" else "list"] for v in view_mode.split(",")]
            return {
                "type": "ir.actions.act_window",
                "name": name, "res_model": model,
                "view_mode": view_mode, "views": views,
                "domain": domain,
            }

        if kind == "so":
            if filters.get("source") == "pos":
                return _act("POS Orders", "pos.lite.order", self._pos_domain(filters))
            return _act("Sales Orders", "sale.order", self._so_domain(filters))
        if kind == "do":
            d_from, d_to = self._dates(filters)
            domain = [
                ("company_id", "in", self._company_ids(filters)),
                ("picking_type_code", "=", "outgoing"),
                ("state", "=", "done"),
            ]
            if d_from:
                domain.append(("date_done", ">=", d_from))
            if d_to:
                domain.append(("date_done", "<=", d_to))
            return _act("Deliveries", "stock.picking", domain)
        if kind == "invoice":
            return _act("Posted Invoices", "account.move", self._move_domain(filters))
        if kind == "payment":
            return _act("Invoices with Payments", "account.move",
                        self._move_domain(filters)
                        + [("payment_state", "in",
                            ("paid", "partial", "in_payment", "reversed"))])
        if kind == "backlog":
            return _act("Backlog Orders", "sale.order",
                        self._so_domain(filters, states=("sale",))
                        + [("picking_ids.state", "in",
                            ("waiting", "confirmed", "assigned"))])
        if kind == "overdue":
            f = dict(filters, date_from=False, date_to=False)
            return _act("Overdue Invoices", "account.move",
                        self._move_domain(f)
                        + [("move_type", "=", "out_invoice"),
                           ("amount_residual", ">", 0),
                           ("invoice_date_due", "<", date.today().isoformat())])
        return {"type": "ir.actions.act_window_close"}
