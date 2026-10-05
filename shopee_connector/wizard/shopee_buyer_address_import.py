import re
import unicodedata
from datetime import datetime

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError

# Seller Center "Order to ship" export headers, as (header, occurrence).
# Province/district/zip appear twice: first for the shipping address, then
# for the tax invoice address.
ORDER_SN = ("หมายเลขคำสั่งซื้อ", 0)
SHIPPING = {
    "name": ("ชื่อผู้รับ", 0),
    "phone": ("หมายเลขโทรศัพท์", 0),
    "full_address": ("ที่อยู่ในการจัดส่ง", 0),
    "region": ("ประเทศ", 0),
    "state": ("จังหวัด", 0),
    "city": ("เขต/อำเภอ", 0),
    "zipcode": ("รหัสไปรษณีย์", 0),
}
TAX_REQUESTED = ("ผู้ซื้อร้องขอใบกำกับภาษี", 0)
PAID_AT = ("เวลาการชำระสินค้า", 0)
TAX = {
    "type": ("ประเภทใบกำกับภาษี", 0),
    "name": ("ชื่อ", 0),
    "branch_type": ("ประเภทสาขา", 0),
    "branch_code": ("รหัสประจำสาขา", 0),
    "street": ("รายละเอียดที่อยู่", 0),
    "subdistrict": ("แขวง/ตำบล", 0),
    "district": ("เขต/อำเภอ", 1),
    "state": ("จังหวัด", 1),
    "zipcode": ("รหัสไปรษณีย์", 1),
    "vat": ("หมายเลขประจำตัวผู้เสียภาษี", 0),
    "phone": ("หมายเลขโทรศัพท์สำหรับออกใบกำกับภาษี", 0),
    "email": ("อีเมลสำหรับรับใบกำกับภาษี", 0),
}
# Order-level money columns (repeated on every product row of the order).
MONEY = {
    "shipping": ("ค่าจัดส่งที่ชำระโดยผู้ซื้อ", 0),
    "voucher_amount": ("โค้ดส่วนลดชำระโดยผู้ขาย", 0),
    "commission": ("ค่าคอมมิชชั่น", 0),
    "service_fee": ("ค่าบริการ", 0),
    "transaction_fee": ("Transaction Fee", 0),
    "infra_fee": ("ค่าธรรมเนียมโครงสร้างพื้นฐานแพลตฟอร์ม", 0),
}
LINE_TOTAL = ("ราคาขายสุทธิ", 0)
VOUCHER_CODES = ("โค้ดส่วนลด", 0)
REQUIRED = (ORDER_SN, SHIPPING["full_address"])
_MAX_LISTED = 20


class ShopeeBuyerAddressImportWizard(models.TransientModel):
    _name = "shopee.buyer.address.import.wizard"
    _inherit = "shopee.file.import.mixin"
    _description = "Import Shopee Buyer Addresses"

    file_data = fields.Binary(string="Seller Center Order File", required=True)
    file_name = fields.Char(string="Filename")
    state = fields.Selection(
        [("upload", "Upload"), ("done", "Done")], default="upload"
    )
    result_message = fields.Text(readonly=True)

    @staticmethod
    def _cell(value):
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip()

    @staticmethod
    def _header_key(value):
        """Compare headers ignoring Unicode form, invisible chars and spaces."""
        text = unicodedata.normalize("NFC", str(value or ""))
        text = re.sub(r"[​-‍﻿]", "", text)
        return re.sub(r"\s+", "", text)

    @classmethod
    def _column_indexes(cls, headers):
        """Return {header_key: [index, ...]} (all occurrences, in order)."""
        indexes = {}
        for index, header in enumerate(headers):
            indexes.setdefault(cls._header_key(header), []).append(index)
        missing = [name for name, _occ in REQUIRED if cls._header_key(name) not in indexes]
        if missing:
            found = [str(h).strip() for h in headers if str(h or "").strip()]
            raise UserError(
                _("This is not a Seller Center order export. Missing column(s): %s\n"
                  "The file has %s column(s): %s")
                % (", ".join(missing), len(found), ", ".join(found[:15])
                   + (" …" if len(found) > 15 else ""))
            )
        return indexes

    def _parse_local_datetime(self, text):
        """Seller Center times ("2026-09-12 23:41") are shop-local."""
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                naive = datetime.strptime(text, fmt)
            except (TypeError, ValueError):
                continue
            return self.env["sale.order"]._shopee_local_tz().localize(naive)
        return False

    @staticmethod
    def _amount(text):
        try:
            return float(str(text).replace(",", "")) if text not in ("", None) else None
        except ValueError:
            return None

    def _payment_from_row(self, get, row, prefix):
        payment = {key: self._amount(get(row, col)) for key, col in MONEY.items()}
        if payment["shipping"] is None and payment["commission"] is None:
            return False  # export without money columns
        codes = [c.strip() for c in get(row, VOUCHER_CODES).split(";") if c.strip()]
        if prefix:
            codes = [c for c in codes if c.upper().startswith(prefix.upper())]
        payment.update({"source": "excel", "voucher_codes": codes, "products_total": 0.0})
        return payment

    def _orders_from_file(self):
        """Return {order_sn: shopee-like order detail} from the upload."""
        headers, rows = self._read_rows()
        indexes = self._column_indexes(headers)

        def get(row, column):
            header, occurrence = column
            positions = indexes.get(self._header_key(header)) or []
            if occurrence >= len(positions) or positions[occurrence] >= len(row):
                return ""
            return self._cell(row[positions[occurrence]])

        prefix = self.env["shopee.config"].search([], limit=1).shopee_voucher_prefix
        orders = {}
        for row in rows:
            row = list(row)
            order_sn = get(row, ORDER_SN)
            if not order_sn:
                continue
            if order_sn in orders:
                # one row per product line; only the line totals add up
                payment = orders[order_sn]["payment"]
                if payment:
                    payment["products_total"] += self._amount(get(row, LINE_TOTAL)) or 0.0
                continue
            address = {key: get(row, column) for key, column in SHIPPING.items()}
            tax = False
            if get(row, TAX_REQUESTED).lower() in ("yes", "y", "ใช่"):
                tax = {key: get(row, column) for key, column in TAX.items()}
                if not tax["vat"]:
                    tax = False
            orders[order_sn] = {
                "order_sn": order_sn,
                "region": address["region"],
                "recipient_address": address,
                "tax_invoice": tax,
                "paid_at": self._parse_local_datetime(get(row, PAID_AT)),
                "payment": self._payment_from_row(get, row, prefix),
            }
            if orders[order_sn]["payment"]:
                orders[order_sn]["payment"]["products_total"] = (
                    self._amount(get(row, LINE_TOTAL)) or 0.0
                )
        for detail in orders.values():
            payment = detail["payment"]
            if payment:
                fees = sum(payment[k] or 0.0 for k in (
                    "commission", "service_fee", "transaction_fee", "infra_fee"))
                payment["net_income"] = (
                    payment["products_total"] + (payment["shipping"] or 0.0)
                    - (payment["voucher_amount"] or 0.0) - fees
                )
        if not orders:
            raise UserError(_("No orders were found in the file."))
        return orders

    def action_import(self):
        self.ensure_one()
        orders = self._orders_from_file()
        SaleOrder = self.env["sale.order"]
        updated, taxed, not_found, skipped, failed, paid = [], [], [], [], [], []
        for order_sn, detail in orders.items():
            sale_orders = SaleOrder.search([
                ("is_shopee_order", "=", True),
                ("shopee_order_sn", "=", order_sn),
            ])
            if not sale_orders:
                not_found.append(order_sn)
                continue
            for sale_order in sale_orders:
                try:
                    with self.env.cr.savepoint():
                        if detail["tax_invoice"] and sale_order.partner_id.shopee_config_id:
                            sale_order.partner_id._shopee_apply_tax_invoice(
                                detail["tax_invoice"]
                            )
                            taxed.append(order_sn)
                        if not sale_order._shopee_apply_recipient(detail):
                            skipped.append(order_sn)
                            continue
                        sale_order._shopee_set_commitment_date(detail["paid_at"])
                        if (
                            detail["payment"]
                            and sale_order.shopee_payment_source != "escrow"
                            and sale_order._shopee_apply_payment(detail["payment"])
                        ):
                            paid.append(order_sn)
                except (UserError, ValidationError) as exc:
                    failed.append(f"{order_sn} ({exc})")
                    continue
                updated.append(order_sn)

        self.write({
            "state": "done",
            "result_message": self._result_message(
                updated, taxed, not_found, skipped, failed, paid
            ),
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    @staticmethod
    def _listed(order_sns):
        shown = ", ".join(order_sns[:_MAX_LISTED])
        if len(order_sns) > _MAX_LISTED:
            shown += f" … (+{len(order_sns) - _MAX_LISTED})"
        return shown

    def _result_message(self, updated, taxed, not_found, skipped, failed, paid=()):
        lines = [_("Updated buyer address for %s order(s).") % len(updated)]
        if paid:
            lines.append(
                _("Payment details (shipping, shop voucher, Shopee fees) applied "
                  "for %s order(s).") % len(paid)
            )
        if taxed:
            lines.append(
                _("Tax invoice data (Tax ID, invoice address) applied for %s "
                  "order(s): %s") % (len(taxed), self._listed(taxed))
            )
        if not_found:
            lines.append(
                _("%s order(s) are not in Odoo yet (import them first): %s")
                % (len(not_found), self._listed(not_found))
            )
        if skipped:
            lines.append(
                _("%s order(s) skipped because the customer is not a Shopee "
                  "buyer contact: %s") % (len(skipped), self._listed(skipped))
            )
        if failed:
            lines.append(
                _("%s order(s) failed: %s") % (len(failed), self._listed(failed))
            )
        return "\n".join(lines)
