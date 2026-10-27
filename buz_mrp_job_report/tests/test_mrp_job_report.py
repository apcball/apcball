from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMrpJobReport(TransactionCase):
    def test_split_name(self):
        W = self.env["buz.mrp.job.report.wizard"]
        self.assertEqual(W._split_name("BLOJ003067/BOJ0003000"), ("BLOJ003067", "BOJ0003000"))
        self.assertEqual(W._split_name("LOJ0077691 / OJ00076804"), ("LOJ0077691", "OJ00076804"))
        self.assertEqual(W._split_name("WH/MO/00001"), ("WH/MO/00001", "WH/MO/00001"))
        self.assertEqual(W._split_name("MOF260900157-003"), ("MOF260900157-003", "MOF260900157-003"))

    def test_rows_for_done_mo(self):
        prod = self.env["product.product"].create({"name": "FG", "type": "product"})
        comp = self.env["product.product"].create({"name": "RM", "type": "product"})
        mo = self.env["mrp.production"].create({
            "product_id": prod.id, "product_qty": 2.0,
            "move_raw_ids": [(0, 0, {
                "name": "RM", "product_id": comp.id, "product_uom_qty": 4.0,
                "location_id": self.env.ref("stock.stock_location_stock").id,
                "location_dest_id": self.env["stock.location"].search([("usage", "=", "production")], limit=1).id,
            })],
        })
        mo.action_confirm()
        mo.qty_producing = 2.0
        mo.move_raw_ids.quantity = 4.0
        mo.move_raw_ids.picked = True
        mo.with_context(skip_consumption=True, skip_immediate=True).button_mark_done()
        wiz = self.env["buz.mrp.job.report.wizard"].create({
            "date_from": "2000-01-01", "date_to": "2999-12-31", "product_ids": [(6, 0, prod.ids)],
        })
        rows = wiz._get_rows()
        self.assertEqual(rows[0][0], mo.name)
        self.assertEqual(rows[1][8], 2.0)
        self.assertTrue(any(r[16] == 4.0 for r in rows), "issue row")
        self.assertTrue(any(r[25] == 2.0 for r in rows), "close row")
        self.assertTrue(wiz.action_export_xlsx()["url"].startswith("/web/content/"))

    def test_issue_rows_from_stock_request(self):
        prod = self.env["product.product"].create({"name": "FG2", "type": "product"})
        comp = self.env["product.product"].create({"name": "RM2", "type": "product"})
        mo = self.env["mrp.production"].create({"product_id": prod.id, "product_qty": 1.0})
        ptype = self.env.ref("stock.picking_type_internal")
        req = self.env["mrp.stock.request"].create({
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "mo_ids": [(6, 0, mo.ids)],
            "line_ids": [(0, 0, {"product_id": comp.id, "uom_id": comp.uom_id.id, "qty_requested": 3.0})],
        })
        req.line_ids.qty_issued = 3.0
        wiz = self.env["buz.mrp.job.report.wizard"].create({
            "date_from": "2000-01-01", "date_to": "2999-12-31", "state_filter": "all",
            "product_ids": [(6, 0, prod.ids)],
        })
        issues = [r for r in wiz._get_rows() if r[16] == 3.0]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0][15], comp.display_name)
        self.assertEqual(issues[0][18], req.name)

    def test_pooled_request_not_duplicated_per_mo(self):
        prod = self.env["product.product"].create({"name": "FG3", "type": "product"})
        comp = self.env["product.product"].create({"name": "RM3", "type": "product"})
        mos = self.env["mrp.production"].create([
            {"product_id": prod.id, "product_qty": 1.0} for _i in range(2)
        ])
        ptype = self.env.ref("stock.picking_type_internal")
        req = self.env["mrp.stock.request"].create({
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "mo_ids": [(6, 0, mos.ids)],
            "line_ids": [(0, 0, {"product_id": comp.id, "uom_id": comp.uom_id.id, "qty_requested": 10.0})],
        })
        req.line_ids.qty_issued = 10.0
        wiz = self.env["buz.mrp.job.report.wizard"].create({
            "date_from": "2000-01-01", "date_to": "2999-12-31", "state_filter": "all",
            "product_ids": [(6, 0, prod.ids)],
        })
        rows = wiz._get_rows()
        # request is pooled: whole-request qty (10) must NOT be repeated on each MO
        self.assertFalse([r for r in rows if r[16] == 10.0])
        self.assertFalse([r for r in rows if r[30] == 10.0])

    def _open_mo_with_request(self, name, qty_issued):
        prod = self.env["product.product"].create({"name": "FG" + name, "type": "product"})
        comp = self.env["product.product"].create({"name": "RM" + name, "type": "product"})
        mo = self.env["mrp.production"].create({"product_id": prod.id, "product_qty": 1.0})
        mo.action_confirm()
        ptype = self.env.ref("stock.picking_type_internal")
        req = self.env["mrp.stock.request"].create({
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "mo_ids": [(6, 0, mo.ids)],
            "line_ids": [(0, 0, {"product_id": comp.id, "uom_id": comp.uom_id.id, "qty_requested": 3.0})],
        })
        req.line_ids.qty_issued = qty_issued
        wiz = self.env["buz.mrp.job.report.wizard"].create({
            "date_from": "2000-01-01", "date_to": "2999-12-31", "state_filter": "open",
            "product_ids": [(6, 0, prod.ids)],
        })
        return mo, comp, wiz

    def test_open_mo_with_issue_listed(self):
        mo, comp, wiz = self._open_mo_with_request("O1", 3.0)
        rows = wiz._get_rows()
        self.assertEqual(rows[0][0], mo.name)
        self.assertEqual([r[16] for r in rows if r[16] != ""], [3.0])
        self.assertFalse([r for r in rows if r[25] != ""], "no close rows")
        self.assertTrue(wiz.action_export_xlsx()["url"].startswith("/web/content/"))

    def test_open_mo_without_issue_excluded(self):
        _mo, _comp, wiz = self._open_mo_with_request("O2", 0.0)
        self.assertFalse(wiz._get_rows())

    def test_done_mo_excluded_from_open(self):
        mo, _comp, wiz = self._open_mo_with_request("O3", 3.0)
        mo.state = "done"
        self.assertFalse(wiz._get_rows())

    def test_zero_issue_lines_hidden(self):
        prod = self.env["product.product"].create({"name": "FG4", "type": "product"})
        comp = self.env["product.product"].create({"name": "RM4", "type": "product"})
        mo = self.env["mrp.production"].create({"product_id": prod.id, "product_qty": 1.0})
        ptype = self.env.ref("stock.picking_type_internal")
        self.env["mrp.stock.request"].create({
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "mo_ids": [(6, 0, mo.ids)],
            "line_ids": [(0, 0, {"product_id": comp.id, "uom_id": comp.uom_id.id, "qty_requested": 5.0})],
        })
        wiz = self.env["buz.mrp.job.report.wizard"].create({
            "date_from": "2000-01-01", "date_to": "2999-12-31", "state_filter": "all",
            "product_ids": [(6, 0, prod.ids)],
        })
        self.assertFalse([r for r in wiz._get_rows() if r[15] == comp.display_name])
