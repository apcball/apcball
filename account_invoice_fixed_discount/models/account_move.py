# Copyright 2017 ForgeFlow S.L.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    fixed_discount_tax_exact = fields.Boolean(default=False, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        # เอกสารเดิมไม่มี flag นี้ จึงคงวิธีคำนวณเดิมแม้มีการคำนวณภาษีซ้ำ
        invoice_types = {
            "out_invoice", "out_refund", "in_invoice", "in_refund",
            "out_receipt", "in_receipt",
        }
        default_move_type = self.default_get(["move_type"]).get("move_type")
        for vals in vals_list:
            if vals.get("move_type", default_move_type) in invoice_types:
                vals.setdefault("fixed_discount_tax_exact", True)
        return super().create(vals_list)
