"""Thai buyers, prices, delivery date, cancellations and payment details."""
from datetime import datetime
from unittest.mock import patch

import pytz

from odoo.tests import TransactionCase

from ..models.lazada_api import LazadaAPI


class TestLazadaThaiOrders(TransactionCase):
    def setUp(self):
        super().setUp()
        self.product = self.env["product.product"].create({
            "name": "Lazada QA Thai", "default_code": "LAZADA-QA-TH", "type": "product",
        })
        self.sku = self.product.default_code
        self.config = self.env["lazada.config"].create({
            "name": "Thai Seller", "region": "th", "app_key": "1000001",
            "app_secret": "testkey", "seller_id": "333", "access_token": "tok",
            "token_expires_at": "2999-01-01 00:00:00",
        })
        self.thailand = self.env.ref("base.th")
        self.finance = patch.object(LazadaAPI, "get_finance_transactions", return_value=[])
        self.finance.start()
        self.addCleanup(self.finance.stop)

    def _import(self, order, items):
        order = dict({"order_id": "TH-1", "statuses": ["pending"]}, **order)
        with patch.object(LazadaAPI, "get_order", return_value=order), \
             patch.object(LazadaAPI, "get_order_items", return_value=items):
            return self.env["sale.order"].create_from_lazada(order["order_id"], config=self.config)

    def _item(self, **values):
        return dict({"sku": self.sku, "name": "Widget", "item_price": "107.00",
                     "status": "pending"}, **values)

    # ------------------------------------------------------------------
    # Buyers
    # ------------------------------------------------------------------
    def test_masked_buyer_gets_no_company_data(self):
        self.config.company_id.partner_id.with_context(skip_partner_required_fields=True).write({
            "street": "1 Company Rd", "city": "Bang Rak", "zip": "10500", "phone": "021234567",
        })
        partner = self.env["res.partner"].find_or_create_lazada_buyer(self.config, {
            "order_id": "MASKED-1", "customer_first_name": "naokibee",
            "address_shipping": {
                "first_name": "*****", "phone": "66******78", "address1": "****",
                "address3": "****", "address4": "****", "address5": "****",
                "post_code": "****", "country": "****",
            },
        })
        self.assertEqual(partner.name, "naokibee")
        self.assertEqual(partner.country_id, self.thailand)
        for field_name in ("street", "street2", "city", "zip", "state_id", "phone"):
            self.assertFalse(partner[field_name], field_name)

    def test_masked_buyers_are_not_merged(self):
        Partner = self.env["res.partner"]
        first = Partner.find_or_create_lazada_buyer(self.config, {
            "order_id": "M-1", "customer_first_name": "S***",
        })
        second = Partner.find_or_create_lazada_buyer(self.config, {
            "order_id": "M-2", "customer_first_name": "S***",
        })
        self.assertNotEqual(first, second)

    def test_real_thai_address_is_mapped(self):
        state = self.env["res.country.state"].search(
            [("country_id", "=", self.thailand.id)], limit=1
        )
        if not state:
            self.skipTest("No Thai provinces loaded")
        partner = self.env["res.partner"].find_or_create_lazada_buyer(self.config, {
            "order_id": "REAL-1", "customer_first_name": "Somchai",
            "address_shipping": {
                "first_name": "Somchai", "last_name": "Jaidee", "phone": "66812345678",
                "address1": "99 Sukhumvit", "address3": state.name,
                "address4": "Khlong Toei", "address5": "Khlong Tan",
                "post_code": "10110", "country": "Thailand",
            },
        })
        self.assertEqual(partner.name, "Somchai Jaidee")
        self.assertEqual(partner.street, "99 Sukhumvit")
        self.assertEqual(partner.street2, "Khlong Tan")
        self.assertEqual(partner.city, "Khlong Toei")
        self.assertEqual(partner.zip, "10110")
        self.assertEqual(partner.country_id, self.thailand)
        self.assertEqual(partner.state_id, state)
        self.assertEqual(partner.phone, "0812345678")

    def test_detailed_address_drops_repeated_parts(self):
        values = self.env["res.partner"]._lazada_address_values({
            "address1": "เลขที่ 63/50 หมู่ที่ 5 ตำบลบ่อผุด อำเภอเกาะสมุย จังหวัดสุราษฎร์ธานี 84320",
            "address3": "จังหวัดสุราษฎร์ธานี", "address4": "อำเภอเกาะสมุย",
            "address5": "ตำบลบ่อผุด", "post_code": "84320",
        }, self.config)
        self.assertEqual(values["street"], "เลขที่ 63/50 หมู่ที่ 5")
        self.assertEqual(values["street2"], "ตำบลบ่อผุด")
        self.assertEqual(values["city"], "อำเภอเกาะสมุย")

    def test_masked_update_keeps_real_buyer_data(self):
        Partner = self.env["res.partner"]
        order = {"order_id": "KEEP-1", "customer_first_name": "Real", "customer_last_name": "Buyer",
                 "address_shipping": {"first_name": "Real", "last_name": "Buyer",
                                      "phone": "0899999999", "address1": "5 Real St"}}
        partner = Partner.find_or_create_lazada_buyer(self.config, order)
        masked = dict(order, order_id="KEEP-2", address_shipping={
            "first_name": "****", "phone": "****", "address1": "****",
        })
        same = Partner.find_or_create_lazada_buyer(self.config, masked)
        self.assertEqual(same, partner)
        self.assertEqual(partner.street, "5 Real St")
        self.assertEqual(partner.phone, "0899999999")

    def test_thai_phone_format(self):
        to_thai = self.env["res.partner"]._lazada_thai_phone
        self.assertEqual(to_thai("66819283179"), "0819283179")
        self.assertEqual(to_thai("+66 81 928 3179"), "0819283179")
        self.assertEqual(to_thai("0819283179"), "0819283179")
        self.assertEqual(to_thai("021509710"), "021509710")

    def test_tax_invoice_buyer_gets_delivery_contact(self):
        order = self._import({
            "order_id": "TH-TAX", "customer_first_name": "QA Company",
            "tax_code": "0105551234567", "branch_number": "0",
            "address_billing": {"first_name": "QA Company Ltd", "address1": "1 Billing Rd"},
            "address_shipping": {"first_name": "Receiver", "phone": "0811111111",
                                 "address1": "2 Delivery Rd"},
        }, [self._item()])
        buyer = order.partner_id
        if not buyer.vat:
            self.skipTest("VAT number rejected by this database's VAT validation")
        self.assertEqual(buyer.vat, "0105551234567")
        self.assertEqual(buyer.street, "1 Billing Rd")
        self.assertEqual(order.partner_shipping_id.parent_id, buyer)
        self.assertEqual(order.partner_shipping_id.street, "2 Delivery Rd")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def test_price_excludes_vat_and_units_are_grouped(self):
        self.assertEqual(self.config.lazada_price_vat_rate, 7.0)
        order = self._import({"order_number": "300001"}, [
            self._item(item_price="963.00", order_item_id=1),
            self._item(item_price="963.00", order_item_id=2),
            self._item(item_price="963.00", order_item_id=3, status="canceled"),
        ])
        line = order.order_line.filtered(lambda l: not l.lazada_line_type)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.product_uom_qty, 2)
        self.assertAlmostEqual(line.price_unit, 900.0, places=2)
        self.assertEqual(order.client_order_ref, "300001")

    def test_free_item_stays_free(self):
        order = self._import({}, [self._item(item_price="0.00", paid_price="0.00")])
        self.assertEqual(order.order_line.filtered(lambda l: not l.lazada_line_type).price_unit, 0)

    def test_cancelled_order_imported_as_cancelled(self):
        order = self._import({"statuses": ["canceled"]}, [self._item(status="canceled")])
        self.assertEqual(order.lazada_order_status, "canceled")
        self.assertEqual(order.state, "cancel")

    def test_status_sync_cancels_open_quotation_and_tags_confirmed(self):
        quotation = self._import({"order_id": "TH-Q"}, [self._item()])
        quotation.update_lazada_status("canceled")
        self.assertEqual(quotation.state, "cancel")

        confirmed = self._import({"order_id": "TH-C"}, [self._item()])
        confirmed.action_confirm()
        confirmed.update_lazada_status("canceled")
        self.assertEqual(confirmed.state, "sale")
        self.assertIn(self.env.ref("lazada_connector.tag_lazada_cancelled_after_confirm"),
                      confirmed.tag_ids)

    def test_status_sync_fills_address_and_delivery_date_once_paid(self):
        order = self._import({
            "order_id": "TH-UNPAID", "statuses": ["unpaid"], "customer_first_name": "Cake",
            "created_at": "2026-09-21 09:00:00 +0700",
            "address_shipping": {"first_name": "****", "phone": "****", "address1": "****"},
        }, [self._item(status="unpaid")])
        self.assertFalse(order.commitment_date)
        self.assertFalse(order.partner_id.street)

        self.env.user.tz = "Asia/Bangkok"
        order.apply_lazada_detail({
            "order_id": "TH-UNPAID", "statuses": ["pending"],
            "created_at": "2026-09-21 09:00:00 +0700",
            "updated_at": "2026-09-21 15:30:00 +0700",
            "address_shipping": {"first_name": "เค้ก", "phone": "66644976555",
                                 "address1": "เลขที่ 63/50 หมู่ที่ 5", "address5": "ตำบลบ่อผุด",
                                 "address4": "อำเภอเกาะสมุย", "post_code": "84320"},
        })
        partner = order.partner_id
        self.assertEqual(order.lazada_order_status, "pending")
        self.assertEqual(partner.name, "เค้ก")
        self.assertEqual(partner.phone, "0644976555")
        self.assertEqual(partner.zip, "84320")
        # Paid 15:30 (after the 14:00 cut-off) -> ships next day 14:00 = 07:00 UTC.
        self.assertEqual(order.commitment_date, datetime(2026, 9, 22, 7, 0))

    def test_commitment_date_follows_cutoff(self):
        SaleOrder = self.env["sale.order"]
        self.env.user.tz = "Asia/Bangkok"
        bkk = pytz.timezone("Asia/Bangkok")
        before = bkk.localize(datetime(2026, 9, 21, 13, 59))
        after = bkk.localize(datetime(2026, 9, 21, 14, 0))
        self.assertEqual(SaleOrder._lazada_commitment_date(before, self.config),
                         datetime(2026, 9, 21, 7, 0))
        self.assertEqual(SaleOrder._lazada_commitment_date(after, self.config),
                         datetime(2026, 9, 22, 7, 0))
        self.assertEqual(
            SaleOrder._lazada_parse_datetime("2026-09-21 13:59:00 +0700"), before,
        )

    def test_trade_channel_set_on_import(self):
        SaleOrder = self.env["sale.order"]
        if not SaleOrder._lazada_trade_channel_values():
            self.skipTest("marketplace_settlement 'lazada' channel not available")
        order = self._import({}, [self._item()])
        self.assertEqual(order.trade_channel, "lazada")
        order.trade_channel = False
        SaleOrder._lazada_backfill_trade_channel()
        self.assertEqual(order.trade_channel, "lazada")

    # ------------------------------------------------------------------
    # Payment details
    # ------------------------------------------------------------------
    def test_import_adds_shipping_and_seller_voucher(self):
        order = self._import({"shipping_fee": "40.00", "voucher_seller": "10.00"},
                             [self._item(voucher_code_seller="MOGEN083")])
        shipping = order.order_line.filtered(lambda l: l.lazada_line_type == "shipping")
        voucher = order.order_line.filtered(lambda l: l.lazada_line_type == "voucher")
        self.assertAlmostEqual(shipping.price_unit, 40 / 1.07, places=2)
        self.assertEqual(shipping.product_id.default_code, "Service04")
        self.assertAlmostEqual(voucher.price_unit, -10 / 1.07, places=2)
        self.assertIn("MOGEN083", voucher.name)
        self.assertEqual(order.lazada_payment_source, "order")

    def test_finance_rows_add_fees_and_net_income(self):
        order = self._import({"order_id": "TH-FIN", "statuses": ["delivered"], "shipping_fee": "40"},
                             [self._item(status="delivered")])
        rows = [
            {"fee_type": "13", "fee_name": "Item Price Credit", "amount": "107.00"},
            {"fee_type": "8", "fee_name": "Shipping Fee (Paid By Customer)", "amount": "40.00"},
            {"fee_type": "16", "fee_name": "Commission", "amount": "-5.35"},
            {"fee_type": "3", "fee_name": "Payment Fee", "amount": "-3.21"},
        ]
        api = self.config._get_api()
        with patch.object(LazadaAPI, "get_finance_transactions", return_value=rows):
            order._lazada_fetch_finance(api, "tok")
            order._lazada_fetch_finance(api, "tok")  # already from Finance API: skipped
        self.assertEqual(order.lazada_payment_source, "finance")
        self.assertAlmostEqual(order.lazada_net_income, 138.44, places=2)
        self.assertIn("Commission", str(order.note))
        self.assertIn("138.44", str(order.note))
        self.assertEqual(len(order.order_line.filtered(lambda l: l.lazada_line_type == "shipping")), 1)

    def test_payment_is_reapplied_without_duplicates(self):
        order = self._import({"shipping_fee": "40.00"}, [self._item()])
        payment = order._lazada_payment_from_order({"shipping_fee": "50"}, [self._item()])
        order._lazada_apply_payment(payment)
        order._lazada_apply_payment(payment)
        shipping = order.order_line.filtered(lambda l: l.lazada_line_type == "shipping")
        self.assertEqual(len(shipping), 1)
        self.assertAlmostEqual(shipping.price_unit, 50 / 1.07, places=2)
