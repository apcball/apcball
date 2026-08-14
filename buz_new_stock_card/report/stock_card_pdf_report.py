from odoo import fields, models


class StockCardPdfReport(models.AbstractModel):
    _name = "report.buz_new_stock_card.report_stock_card_pdf"
    _description = "Stock Card PDF Report"

    def _get_report_values(self, docids, data=None):
        data = data or {}
        product = self.env["product.product"].browse(docids)
        engine = self.env["buz.stock.card.report"]

        location_id = int(data.get("location_id"))
        include_children = bool(data.get("include_children"))
        date_from = fields.Date.from_string(data.get("date_from"))
        date_to = fields.Date.from_string(data.get("date_to"))
        company_id = data.get("company_id")
        company_ids = [int(company_id)] if company_id else None

        location = self.env["stock.location"].browse(location_id)
        scope_ids = engine.resolve_location_scope(location_id, include_children)

        card_data = engine.get_stock_card_data(
            product.id, scope_ids, date_from, date_to,
            page_size=0, page=0,
            show_movements_only=data.get("show_movements_only", False),
            company_ids=company_ids,
        )

        return {
            "doc_ids": docids,
            "doc_model": "product.product",
            "docs": product,
            "location_name": location.display_name,
            "date_from": date_from,
            "date_to": date_to,
            "card_data": card_data,
            "generated_at": fields.Datetime.now(),
        }
