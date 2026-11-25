"""Lazada Seller Center order export -> buyer addresses; Odoo test runner only."""
import base64
import csv
import io
from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from ..models.lazada_api import LazadaAPI

HEADERS = [
    "orderItemId", "orderNumber", "createTime", "status", "customerName",
    "shippingName", "shippingAddress", "shippingAddress2", "shippingAddress3",
    "shippingAddress4", "shippingAddress5", "shippingPhone", "shippingCity",
    "shippingPostCode", "shippingCountry", "billingName", "billingAddr",
    "billingAddr3", "billingAddr4", "billingAddr5", "billingPhone", "billingCity",
    "billingPostCode", "billingCountry", "taxCode", "branchNumber",
    "taxInvoiceRequested", "unitPrice", "paidPrice", "sellerDiscountTotal",
    "platformDiscountTotal", "shippingFee",
]


class TestLazadaBuyerAddressImport(TransactionCase):
    def setUp(self):
        super().setUp()
        finance = patch.object(LazadaAPI, "get_finance_transactions", return_value=[])
        finance.start()
        self.addCleanup(finance.stop)
        self.env.user.tz = "Asia/Bangkok"
        self.product = self.env["product.product"].create({
            "name": "Lazada QA Export", "default_code": "LAZADA-QA-EXPORT-ADDR", "type": "product",
        })
        self.config = self.env["lazada.config"].create({
            "name": "Export Seller", "region": "th", "app_key": "1000001",
            "app_secret": "testkey", "seller_id": "444", "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
        })

    def _order(self, number, partner=None):
        order = {"order_id": number, "order_number": number, "statuses": ["pending"],
                 "customer_first_name": "*******%s" % number[-3:],
                 "address_shipping": {"first_name": "****", "phone": "****", "address1": "****"}}
        items = [{"sku": self.product.default_code, "name": "Widget", "item_price": "15490.00",
                  "status": "pending"}]
        with patch.object(LazadaAPI, "get_order", return_value=order), \
             patch.object(LazadaAPI, "get_order_items", return_value=items):
            return self.env["sale.order"].create_from_lazada(number, partner=partner, config=self.config)

    @staticmethod
    def _row(number, **values):
        row = {
            "orderItemId": "1%s" % number, "orderNumber": number,
            "createTime": "07 Oct 2026 21:14", "status": "pending", "customerName": "123456789",
            "shippingName": "Somchai Jaidee", "shippingAddress": "99/1 หมู่ 2 ถนนติวานนท์",
            "shippingAddress3": "นนทบุรี/ Nonthaburi", "shippingAddress4": "ปากเกร็ด/ Pak Kret",
            "shippingAddress5": "11120", "shippingPhone": "660812345678",
            "shippingCity": "ปากเกร็ด/ Pak Kret", "shippingPostCode": "11120",
            "shippingCountry": "Thailand", "billingName": "Somchai Jaidee",
            "billingAddr": "99/1 หมู่ 2 ถนนติวานนท์", "billingAddr3": "นนทบุรี/ Nonthaburi",
            "billingAddr4": "ปากเกร็ด/ Pak Kret", "billingAddr5": "11120",
            "billingPhone": "660812345678", "billingCity": "ปากเกร็ด/ Pak Kret",
            "billingPostCode": "11120", "billingCountry": "Thailand",
            "taxCode": "", "branchNumber": "", "taxInvoiceRequested": "false",
            "unitPrice": "15490.00", "paidPrice": "11990.00", "sellerDiscountTotal": "-500.00",
            "platformDiscountTotal": "-3000.00", "shippingFee": "0.00",
        }
        row.update(values)
        return row

    def _import(self, rows, headers=HEADERS, user=None):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        Wizard = self.env["lazada.buyer.address.import.wizard"]
        if user:
            Wizard = Wizard.with_user(user)
        wizard = Wizard.create({
            "file_name": "orders.csv",
            "file_data": base64.b64encode(stream.getvalue().encode("utf-8")),
        })
        wizard.action_import()
        return wizard

    def test_export_fills_masked_buyer_discount_and_delivery_date(self):
        order = self._order("77001")
        self.assertFalse(order.partner_id.street)
        wizard = self._import([self._row("77001")])

        partner = order.partner_id
        self.assertIn("Updated buyer address for 1 order(s)", wizard.result_message)
        self.assertEqual(partner.name, "Somchai Jaidee")
        self.assertEqual(partner.street, "99/1 หมู่ 2 ถนนติวานนท์")
        self.assertEqual(partner.city, "ปากเกร็ด")
        self.assertEqual(partner.zip, "11120")
        self.assertFalse(partner.street2)
        self.assertEqual(partner.phone, "0812345678")
        self.assertEqual(partner.country_id, self.env.ref("base.th"))
        if partner.state_id:
            self.assertEqual(partner.state_id.country_id, self.env.ref("base.th"))
        voucher = order.order_line.filtered(lambda l: l.lazada_line_type == "voucher")
        self.assertAlmostEqual(voucher.price_unit, -500 / 1.07, places=2)
        self.assertEqual(order.lazada_payment_source, "excel")
        # 21:14 Bangkok is after the 14:00 cut-off -> next day 14:00 = 07:00 UTC.
        self.assertEqual(order.commitment_date, datetime(2026, 10, 8, 7, 0))

    def test_tax_invoice_goes_to_buyer_and_recipient_to_delivery_contact(self):
        order = self._order("77002")
        wizard = self._import([self._row(
            "77002", taxCode="0105551234567", taxInvoiceRequested="true",
            billingName="QA Company Ltd", billingAddr="1 Billing Rd",
        )])
        if "failed" in wizard.result_message:
            self.skipTest("VAT number rejected by this database's VAT validation")
        buyer = order.partner_id
        self.assertEqual(buyer.vat, "0105551234567")
        self.assertEqual(buyer.name, "QA Company Ltd")
        self.assertEqual(buyer.street, "1 Billing Rd")
        self.assertEqual(order.partner_shipping_id.parent_id, buyer)
        self.assertEqual(order.partner_shipping_id.street, "99/1 หมู่ 2 ถนนติวานนท์")
        self.assertIn("Tax invoice data", wizard.result_message)

    def test_unknown_order_and_non_buyer_customer_are_reported(self):
        customer = self.env["res.partner"].with_context(skip_partner_required_fields=True).create({
            "name": "Walk-in customer",
        })
        self._order("77003", partner=customer)
        wizard = self._import([self._row("77003"), self._row("99999")])
        self.assertIn("not in Odoo yet", wizard.result_message)
        self.assertIn("99999", wizard.result_message)
        self.assertIn("not a Lazada buyer", wizard.result_message)
        self.assertFalse(customer.street)

    def test_finance_payment_is_not_overwritten(self):
        order = self._order("77004")
        order.lazada_payment_source = "finance"
        self._import([self._row("77004")])
        self.assertEqual(order.lazada_payment_source, "finance")
        self.assertFalse(order.order_line.filtered(lambda l: l.lazada_line_type == "voucher"))

    def test_other_file_is_rejected(self):
        with self.assertRaises(UserError):
            self._import([{"foo": "1", "bar": "2"}], headers=["foo", "bar"])

    def test_manager_without_finance_rights_can_import(self):
        """Other modules may touch models a Lazada Manager cannot access
        whenever a sales order is written (e.g. a finance delivery plan)."""
        manager = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Lazada QA Manager", "login": "lazada_qa_manager", "tz": "Asia/Bangkok",
            "groups_id": [fields.Command.set([
                self.env.ref("lazada_connector.group_lazada_manager").id,
                self.env.ref("base.group_partner_manager").id,  # Contact Creation
            ])],
        })
        order = self._order("77005")
        order.user_id = manager
        SaleOrder = type(self.env["sale.order"])
        original_write = SaleOrder.write

        def write_needing_admin_rights(records, vals):
            if not records.env.su:
                records.env["ir.config_parameter"].check_access_rights("read")
            return original_write(records, vals)

        with patch.object(SaleOrder, "write", write_needing_admin_rights):
            wizard = self._import([self._row("77005")], user=manager)
        self.assertIn("Updated buyer address for 1 order(s)", wizard.result_message)
        self.assertNotIn("failed", wizard.result_message)
        self.assertEqual(order.partner_id.street, "99/1 หมู่ 2 ถนนติวานนท์")
        self.assertTrue(order.commitment_date)

    def test_failed_order_is_not_reported_as_taxed(self):
        order = self._order("77006")
        SaleOrder = type(self.env["sale.order"])
        with patch.object(SaleOrder, "_lazada_apply_recipient",
                          side_effect=UserError("boom")):
            wizard = self._import([self._row(
                "77006", taxCode="0105551234567", taxInvoiceRequested="true",
            )])
        self.assertIn("1 order(s) failed", wizard.result_message)
        self.assertNotIn("Tax invoice data", wizard.result_message)
        self.assertFalse(order.partner_id.vat)
