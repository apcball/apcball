from datetime import timedelta

from odoo import api, fields, models

ACTIVE_STATES = ("reserved", "partially_released")


class BuzReservationDashboard(models.AbstractModel):
    _name = "buz.reservation.dashboard"
    _description = "Reservation Dashboard Data"

    @api.model
    def get_dashboard_data(self, period="week"):
        Reservation = self.env["buz.stock.reservation"]
        now = fields.Datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        company_domain = [("company_id", "in", self.env.companies.ids)]

        active = Reservation.search(company_domain + [("state", "in", ACTIVE_STATES)])
        active_yesterday = Reservation.search_count(
            company_domain
            + [
                ("state", "in", ACTIVE_STATES),
                ("reserved_date", "<", today_start),
            ]
        )
        expiring_today = Reservation.search_count(
            company_domain
            + [
                ("state", "in", ACTIVE_STATES),
                ("expiry_date", ">=", today_start),
                ("expiry_date", "<", today_end),
            ]
        )
        expired = Reservation.search_count(
            company_domain + [("state", "=", "expired")]
        )

        return {
            "kpi": {
                "active_count": len(active),
                "active_delta": len(active) - active_yesterday,
                "reserved_units": sum(active.mapped("remaining_qty")),
                "expiring_today": expiring_today,
                "expired_count": expired,
                "products_reserved": len(active.line_ids.product_id),
            },
            "trend": self._get_trend(period),
            "status_distribution": self._get_status_distribution(),
            "expiring_soon": self._get_expiring_soon(),
            "recent": self._get_recent(),
        }

    @api.model
    def _get_trend(self, period):
        days = 30 if period == "month" else 7
        now = fields.Datetime.now()
        start = (now - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        groups = self.env["buz.stock.reservation"].read_group(
            [
                ("company_id", "in", self.env.companies.ids),
                ("reserved_date", ">=", start),
                ("state", "!=", "cancel"),
            ],
            ["id:count"],
            ["reserved_date:day"],
        )
        counts = {
            g["reserved_date:day"]: g["reserved_date_count"] for g in groups
        }
        labels, values = [], []
        for i in range(days):
            day = (start + timedelta(days=i)).date()
            label = day.strftime("%d %b")
            labels.append(label)
            values.append(counts.get(label, 0))
        return {"labels": labels, "values": values}

    @api.model
    def _get_status_distribution(self):
        Reservation = self.env["buz.stock.reservation"]
        domain = [("company_id", "in", self.env.companies.ids)]
        expiring_soon = Reservation.search_count(
            domain + [("expiring_soon", "=", True)]
        )
        groups = Reservation.read_group(
            domain + [("state", "!=", "cancel")],
            ["id:count"],
            ["state"],
        )
        by_state = {g["state"]: g["state_count"] for g in groups}
        reserved = max(by_state.get("reserved", 0) - expiring_soon, 0)
        return [
            {"label": "Reserved", "value": reserved, "color": "#7367f0"},
            {
                "label": "Partially Released",
                "value": by_state.get("partially_released", 0),
                "color": "#ff9f43",
            },
            {"label": "Expiring Soon", "value": expiring_soon, "color": "#ffc107"},
            {"label": "Expired", "value": by_state.get("expired", 0), "color": "#ea5455"},
            {"label": "Draft", "value": by_state.get("draft", 0), "color": "#82868b"},
        ]

    @api.model
    def _get_expiring_soon(self, limit=5):
        records = self.env["buz.stock.reservation"].search(
            [
                ("company_id", "in", self.env.companies.ids),
                ("expiring_soon", "=", True),
            ],
            order="expiry_date asc",
            limit=limit,
        )
        return [
            {
                "id": rec.id,
                "name": rec.name,
                "customer": rec.partner_id.display_name,
                "reference": rec.reference or "",
                "days_to_expiry": rec.days_to_expiry,
            }
            for rec in records
        ]

    @api.model
    def _get_recent(self, limit=8):
        state_labels = dict(
            self.env["buz.stock.reservation"]
            ._fields["state"]
            ._description_selection(self.env)
        )
        records = self.env["buz.stock.reservation"].search(
            [("company_id", "in", self.env.companies.ids)],
            order="reserved_date desc",
            limit=limit,
        )
        result = []
        for rec in records:
            state = (
                "expiring_soon"
                if rec.expiring_soon
                else rec.state
            )
            label = (
                "Expiring Soon" if rec.expiring_soon else state_labels[rec.state]
            )
            result.append(
                {
                    "id": rec.id,
                    "name": rec.name,
                    "customer": rec.partner_id.display_name,
                    "reference": rec.reference or "",
                    "warehouse": rec.warehouse_id.display_name,
                    "reserved_date": fields.Datetime.to_string(rec.reserved_date),
                    "expiry_date": fields.Datetime.to_string(rec.expiry_date),
                    "state": state,
                    "state_label": label,
                    "reserved_qty": rec.total_reserved_qty,
                }
            )
        return result
