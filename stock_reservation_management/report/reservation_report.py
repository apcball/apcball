from odoo import api, fields, models, _


class ReportReservation(models.AbstractModel):
    """Reservation Report (PDF)."""

    _name = "report.stock_reservation_management.report_reservation"
    _description = "Reservation Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["stock.reservation"].browse(docids)
        return {
            "doc_ids": docids,
            "doc_model": "stock.reservation",
            "docs": docs,
            "data": data,
            "compute_totals": self._compute_totals,
        }

    @api.model
    def _compute_totals(self, lines):
        """Compute total quantities for report footer."""
        return {
            "reserve_qty": sum(lines.mapped("reserve_qty")),
            "allocated_qty": sum(lines.mapped("allocated_qty")),
            "released_qty": sum(lines.mapped("released_qty")),
        }


class ReportReservationAging(models.AbstractModel):
    """Reservation Aging Report."""

    _name = "report.stock_reservation_management.report_reservation_aging"
    _description = "Reservation Aging Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        if data and data.get("reservation_ids"):
            docs = self.env["stock.reservation"].browse(data["reservation_ids"])
        else:
            docs = self.env["stock.reservation"].browse(docids)
        return {
            "doc_ids": docs.ids,
            "doc_model": "stock.reservation",
            "docs": docs,
            "data": data,
            "aging_data": self._compute_aging(docs),
        }

    @api.model
    def _compute_aging(self, reservations):
        """Compute aging buckets for reservations."""
        from datetime import date, timedelta

        today = date.today()
        buckets = {
            "0-7 days": [],
            "8-15 days": [],
            "16-30 days": [],
            "31-60 days": [],
            "60+ days": [],
        }

        for res in reservations:
            if not res.reserve_date or res.state in ("released", "cancel", "delivered"):
                continue
            age_days = (today - res.reserve_date).days
            if age_days <= 7:
                buckets["0-7 days"].append(res)
            elif age_days <= 15:
                buckets["8-15 days"].append(res)
            elif age_days <= 30:
                buckets["16-30 days"].append(res)
            elif age_days <= 60:
                buckets["31-60 days"].append(res)
            else:
                buckets["60+ days"].append(res)

        # Compute counts and totals per bucket
        result = []
        for label, items in buckets.items():
            if items:
                result.append(
                    {
                        "label": label,
                        "count": len(items),
                        "total_qty": sum(items.mapped("total_reserve_qty")),
                        "reservations": items,
                    }
                )
        return result


class ReportVIPAllocation(models.AbstractModel):
    """VIP Allocation Report."""

    _name = "report.stock_reservation_management.report_vip_allocation"
    _description = "VIP Allocation Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        if data and data.get("reservation_ids"):
            docs = self.env["stock.reservation"].browse(data["reservation_ids"])
        else:
            domain = [("reservation_type", "=", "vip")]
            if data and data.get("customer_ids"):
                domain.append(("customer_id", "in", data["customer_ids"]))
            docs = self.env["stock.reservation"].search(domain)
        return {
            "doc_ids": docs.ids,
            "doc_model": "stock.reservation",
            "docs": docs,
            "data": data,
            "total_vip_reserved": sum(docs.mapped("total_reserve_qty")),
            "total_vip_allocated": sum(docs.mapped("total_allocated_qty")),
        }


class ReportCustomerReservation(models.AbstractModel):
    """Customer Reservation Report."""

    _name = "report.stock_reservation_management.report_customer_reservation"
    _description = "Customer Reservation Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        if data and data.get("customer_id"):
            domain = [("customer_id", "=", data["customer_id"])]
            if data.get("state"):
                domain.append(("state", "=", data["state"]))
            docs = self.env["stock.reservation"].search(domain)
        else:
            docs = self.env["stock.reservation"].search([])
        return {
            "doc_ids": docs.ids,
            "doc_model": "stock.reservation",
            "docs": docs,
            "data": data,
            "group_by_customer": self._group_by_customer(docs),
        }

    @api.model
    def _group_by_customer(self, reservations):
        """Group reservations by customer for report."""
        grouped = {}
        for res in reservations:
            customer = res.customer_id
            if customer not in grouped:
                grouped[customer] = {
                    "customer": customer,
                    "total_reserved": 0.0,
                    "total_allocated": 0.0,
                    "total_released": 0.0,
                    "active_count": 0,
                    "reservations": self.env["stock.reservation"],
                }
            grouped[customer]["total_reserved"] += res.total_reserve_qty
            grouped[customer]["total_allocated"] += res.total_allocated_qty
            grouped[customer]["total_released"] += res.total_released_qty
            grouped[customer]["active_count"] += 1
            grouped[customer]["reservations"] |= res
        return sorted(grouped.values(), key=lambda x: x["total_reserved"], reverse=True)
