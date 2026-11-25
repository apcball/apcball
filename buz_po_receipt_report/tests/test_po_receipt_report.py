from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPoReceiptReport(TransactionCase):
    def _receive(self, currency, price=10.0, qty=5.0, batch=False):
        partner = self.env["res.partner"].with_context(
            skip_partner_required_fields=True
        ).create({"name": "PoRpt Vendor"})
        product = self.env["product.product"].create(
            {"name": "PoRpt Prod", "type": "product"}
        )
        po = self.env["purchase.order"].create(
            {
                "partner_id": partner.id,
                "currency_id": currency.id,
                "order_line": [
                    (0, 0, {
                        "product_id": product.id,
                        "name": product.name,
                        "product_qty": qty,
                        "product_uom": product.uom_id.id,
                        "price_unit": price,
                    })
                ],
            }
        )
        if "approval_state" in po._fields:
            po.approval_state = "approved"
        po.with_context(bypass_budget_check=True).button_confirm()
        picking = po.picking_ids
        if batch:
            self.env["stock.picking.batch"].create(
                {"picking_ids": [(4, picking.id)], "company_id": picking.company_id.id}
            )
        picking.move_ids.quantity = qty
        if currency != self.env.company.currency_id:
            picking.exchange_rate_date = fields.Date.today()
            picking.exchange_rate = 30.0
        picking.with_context(skip_backorder=True).button_validate()
        return picking

    def test_foreign_vs_domestic(self):
        thb = self.env.company.currency_id
        usd = self.env["res.currency"].with_context(active_test=False).search(
            [("name", "=", "USD" if thb.name != "USD" else "EUR")], limit=1
        )
        usd.active = True
        dom = self._receive(thb)
        frg = self._receive(usd, batch=True)
        wiz = self.env["buz.po.receipt.report.wizard"].create(
            {"receipt_type": "all", "date_from": "2000-01-01", "date_to": "2999-12-31"}
        )
        rows = {r["doc_no"]: r for r in wiz._prepare_rows()}
        self.assertFalse(rows[dom.name]["foreign"])
        self.assertTrue(rows[frg.name]["foreign"])
        svl_total = sum(
            self.env["stock.valuation.layer"].search(
                [("stock_move_id", "=", frg.move_ids.id)]
            ).mapped("value")
        )
        self.assertTrue(svl_total)
        self.assertAlmostEqual(rows[frg.name]["cost_baht"], svl_total, places=2)
        self.assertAlmostEqual(
            rows[frg.name]["rate"] * rows[frg.name]["cost"],
            rows[frg.name]["cost_baht"],
            places=2,
        )
        self.assertAlmostEqual(rows[dom.name]["rate"], 1.0)
        self.assertAlmostEqual(rows[dom.name]["cost_baht"], rows[dom.name]["cost"])
        batch = frg.batch_id
        rows = {r["doc_no"]: r for r in wiz._prepare_rows()}
        self.assertEqual(rows[frg.name]["batch_no"], batch.name)
        self.assertEqual(rows[dom.name]["batch_no"], "")
        wiz.receipt_type = "foreign"
        names = {r["doc_no"] for r in wiz._prepare_rows()}
        self.assertIn(frg.name, names)
        self.assertNotIn(dom.name, names)
        wiz.receipt_type = "domestic"
        names = {r["doc_no"] for r in wiz._prepare_rows()}
        self.assertIn(dom.name, names)
        self.assertNotIn(frg.name, names)

    def _export_strings(self, wiz):
        import base64
        import io
        import zipfile

        action = wiz.action_export_xlsx()
        att_id = int(action["url"].split("/web/content/")[1].split("?")[0])
        data = base64.b64decode(self.env["ir.attachment"].browse(att_id).datas)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return z.read("xl/sharedStrings.xml").decode()

    def test_export_columns(self):
        thb = self.env.company.currency_id
        dom = self._receive(thb)
        wiz = self.env["buz.po.receipt.report.wizard"].create(
            {"receipt_type": "domestic", "date_from": "2000-01-01", "date_to": "2999-12-31"}
        )
        strings = self._export_strings(wiz)
        self.assertIn("BatchNo", strings)
        self.assertIn(dom.name, strings)
        for hidden in (">Rate<", ">Exp<", ">Labor<", ">Tax<", ">Transit<"):
            self.assertNotIn(hidden, strings)
        wiz.receipt_type = "all"
        strings = self._export_strings(wiz)
        for shown in (">Rate<", ">Exp<", ">Labor<", ">Tax<", ">Transit<"):
            self.assertIn(shown, strings)

    def test_date_is_move_effective_date(self):
        dom = self._receive(self.env.company.currency_id)
        dom.move_ids.date = "2020-05-10 03:00:00"
        wiz = self.env["buz.po.receipt.report.wizard"].create(
            {"receipt_type": "domestic", "date_from": "2020-05-01", "date_to": "2020-05-31"}
        )
        rows = {r["doc_no"]: r for r in wiz._prepare_rows()}
        self.assertEqual(str(rows[dom.name]["date"]), "2020-05-10 03:00:00")

    def test_landed_cost_uses_booked_svl(self):
        frg = self._receive(self.env.company.currency_id, price=10.0, qty=5.0)
        move = frg.move_ids
        lc_product = self.env["product.product"].create(
            {"name": "PoRpt LC", "type": "service", "landed_cost_ok": True,
             "split_method_landed_cost": "equal"}
        )
        lc = self.env["stock.landed.cost"].create(
            {
                "picking_ids": [(4, frg.id)],
                "cost_lines": [
                    (0, 0, {"product_id": lc_product.id, "name": "freight",
                            "price_unit": 100.0, "split_method": "equal"})
                ],
            }
        )
        lc.compute_landed_cost()
        lc.button_validate()
        booked = sum(
            self.env["stock.valuation.layer"].search(
                [("stock_move_id", "=", move.id), ("stock_landed_cost_id", "=", lc.id)]
            ).mapped("value")
        )
        self.assertTrue(booked, "landed cost layer should exist")
        wiz = self.env["buz.po.receipt.report.wizard"].create({})
        res = wiz._get_landed_costs(move)
        self.assertAlmostEqual(sum(res[move.id].values()), booked)
        self.assertAlmostEqual(res[move.id]["expense"], booked)

    def test_lc_not_in_stock(self):
        frg = self._receive(self.env.company.currency_id, price=10.0, qty=5.0)
        move = frg.move_ids
        # 2 of 5 units still on hand when the landed cost is validated
        move.stock_valuation_layer_ids.filtered(
            lambda l: not l.stock_landed_cost_id
        ).remaining_qty = 2.0
        lc_product = self.env["product.product"].create(
            {"name": "PoRpt LC2", "type": "service", "landed_cost_ok": True,
             "split_method_landed_cost": "equal"}
        )
        lc = self.env["stock.landed.cost"].create(
            {
                "picking_ids": [(4, frg.id)],
                "cost_lines": [
                    (0, 0, {"product_id": lc_product.id, "name": "freight",
                            "price_unit": 100.0, "split_method": "equal"})
                ],
            }
        )
        lc.compute_landed_cost()
        lc.button_validate()
        wiz = self.env["buz.po.receipt.report.wizard"].create({})
        self.assertAlmostEqual(wiz._get_landed_costs(move)[move.id]["expense"], 40.0)
        self.assertAlmostEqual(wiz._get_lc_not_in_stock(move)[move.id], 60.0)
