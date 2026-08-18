from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWipManufacturingReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env["buz.wip.manufacturing.report"]
        cls.company = cls.env.company
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.location = cls.env.ref("stock.stock_location_stock")
        cls.category = cls.env.ref("product.product_category_all")

        cls.finished = cls._make_product("WIP Test Finished")
        cls.comp_a = cls._make_product("WIP Test Component A")
        cls.comp_b = cls._make_product("WIP Test Component B")

    @classmethod
    def _make_product(cls, name):
        return cls.env["product.product"].create({
            "name": name,
            "type": "product",
            "categ_id": cls.category.id,
            "uom_id": cls.uom_unit.id,
            "uom_po_id": cls.uom_unit.id,
            "standard_price": 100.0,
        })

    def _make_mo(self, product, state="done", date_start=None):
        return self.env["mrp.production"].create({
            "product_id": product.id,
            "product_qty": 10.0,
            "product_uom_id": self.uom_unit.id,
            "state": state,
            "date_start": date_start or "2026-08-01 00:00:00",
            "company_id": self.company.id,
        })

    def _make_raw_move(self, mo, product, qty, state="done", price_unit=0.0, date=None):
        return self.env["stock.move"].create({
            "name": product.name,
            "raw_material_production_id": mo.id,
            "product_id": product.id,
            "product_uom_qty": qty,
            "quantity": qty,
            "product_uom": self.uom_unit.id,
            "location_id": self.location.id,
            "location_dest_id": self.env.ref("stock.stock_location_locations_production").id,
            "state": state,
            "price_unit": price_unit,
            "date": date or "2026-08-05 00:00:00",
            "company_id": self.company.id,
        })

    def _make_svl(self, move, product, qty, value):
        return self.env["stock.valuation.layer"].create({
            "product_id": product.id,
            "quantity": qty,
            "value": value,
            "unit_cost": abs(value / qty) if qty else 0.0,
            "stock_move_id": move.id,
            "company_id": self.company.id,
            "description": "test",
        })

    # ------------------------------------------------------------------

    def test_01_multi_component_mo_aggregation(self):
        mo = self._make_mo(self.finished)
        move_a = self._make_raw_move(mo, self.comp_a, 5.0)
        move_b = self._make_raw_move(mo, self.comp_b, 3.0)
        self._make_svl(move_a, self.comp_a, -5.0, -500.0)
        self._make_svl(move_b, self.comp_b, -3.0, -450.0)

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        self.assertEqual(len(data["data"]), 1)
        row = data["data"][0]
        self.assertEqual(len(row["materials"]), 2)
        self.assertAlmostEqual(row["subtotal_qty"], 8.0)
        self.assertAlmostEqual(row["subtotal_amount"], 950.0)

    def test_02_multi_mo_grand_total(self):
        mo1 = self._make_mo(self.finished)
        mo2 = self._make_mo(self.finished)
        m1 = self._make_raw_move(mo1, self.comp_a, 5.0)
        m2 = self._make_raw_move(mo2, self.comp_a, 7.0)
        self._make_svl(m1, self.comp_a, -5.0, -500.0)
        self._make_svl(m2, self.comp_a, -7.0, -700.0)

        data = self.engine.get_wip_data(mo_ids=[mo1.id, mo2.id], status_list=["done"])
        grand = data["grand_total"]
        self.assertAlmostEqual(grand["amount"], sum(r["subtotal_amount"] for r in data["data"]))
        self.assertAlmostEqual(grand["amount"], 1200.0)

    def test_03_in_progress_mo_fallback_cost(self):
        mo = self._make_mo(self.finished, state="progress")
        self._make_raw_move(mo, self.comp_a, 4.0, state="assigned", price_unit=120.0)
        # no SVL created: in-progress consumption has no valuation layer yet

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["progress"])
        row = data["data"][0]
        self.assertEqual(row["materials"][0]["cost_source"], "move_unit_cost")
        self.assertAlmostEqual(row["materials"][0]["unit_cost"], 120.0)
        self.assertAlmostEqual(row["materials"][0]["amount"], 480.0)

    def test_04_fifo_multi_svl_weighted_cost(self):
        mo = self._make_mo(self.finished)
        move = self._make_raw_move(mo, self.comp_a, 10.0)
        self._make_svl(move, self.comp_a, -4.0, -600.0)
        self._make_svl(move, self.comp_a, -6.0, -948.0)

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        material = data["data"][0]["materials"][0]
        # weighted unit cost = |600+948| / |4+6| = 154.8
        self.assertAlmostEqual(material["unit_cost"], 154.8, places=2)
        self.assertAlmostEqual(material["amount"], 1548.0, places=2)

    def test_05_partial_consumption_uses_actual_quantity(self):
        mo = self._make_mo(self.finished)
        move = self._make_raw_move(mo, self.comp_a, 7.0)  # BOM might demand more; move.quantity=7 is actual
        self._make_svl(move, self.comp_a, -7.0, -700.0)

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        self.assertAlmostEqual(data["data"][0]["materials"][0]["quantity"], 7.0)

    def test_06_cancelled_move_excluded(self):
        mo = self._make_mo(self.finished)
        self._make_raw_move(mo, self.comp_a, 5.0, state="cancel")

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        self.assertEqual(data["data"], [])

    def test_07_multi_company_access(self):
        other_company = self.env["res.company"].create({"name": "WIP Test Co 2"})
        mo = self._make_mo(self.finished)
        mo.company_id = other_company.id
        move = self._make_raw_move(mo, self.comp_a, 5.0)
        move.company_id = other_company.id
        self._make_svl(move, self.comp_a, -5.0, -500.0)

        data = self.engine.get_wip_data(
            mo_ids=[mo.id], status_list=["done"], company_ids=[self.company.id],
        )
        self.assertEqual(data["data"], [])

    def test_08_svl_sign_handling(self):
        mo = self._make_mo(self.finished)
        move = self._make_raw_move(mo, self.comp_a, 5.0)
        self._make_svl(move, self.comp_a, -5.0, -500.0)

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        material = data["data"][0]["materials"][0]
        self.assertGreater(material["unit_cost"], 0)
        self.assertGreater(data["summary"]["total_wip_value"], 0)

    def test_09_summary_reflects_whole_filtered_set(self):
        mos = [self._make_mo(self.finished) for _ in range(3)]
        for mo in mos:
            move = self._make_raw_move(mo, self.comp_a, 2.0)
            self._make_svl(move, self.comp_a, -2.0, -200.0)

        data = self.engine.get_wip_data(
            mo_ids=[m.id for m in mos], status_list=["done"], page_size=1, page=0,
        )
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["summary"]["total_mos"], 3)
        self.assertAlmostEqual(data["summary"]["total_wip_value"], 600.0)

    def test_10_progress_only_status_excludes_done(self):
        mo_progress = self._make_mo(self.finished, state="progress")
        mo_done = self._make_mo(self.finished, state="done")
        self._make_raw_move(mo_progress, self.comp_a, 4.0, state="assigned", price_unit=120.0)
        move_done = self._make_raw_move(mo_done, self.comp_a, 5.0)
        self._make_svl(move_done, self.comp_a, -5.0, -500.0)

        data = self.engine.get_wip_data(
            mo_ids=[mo_progress.id, mo_done.id], status_list=["progress", "to_close"],
        )
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["mo_id"], mo_progress.id)

    def test_11_stock_requests_key_present(self):
        mo = self._make_mo(self.finished)
        move = self._make_raw_move(mo, self.comp_a, 5.0)
        self._make_svl(move, self.comp_a, -5.0, -500.0)

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        row = data["data"][0]
        self.assertEqual(row["stock_requests"], [])
        self.assertEqual(row["stock_requests_count"], 0)

    def test_12_material_carries_mrp_request_allocation(self):
        mo = self._make_mo(self.finished)
        move = self._make_raw_move(mo, self.comp_a, 5.0)
        self._make_svl(move, self.comp_a, -5.0, -500.0)

        picking_type = self.env["stock.picking.type"].search(
            [("code", "=", "internal"), ("company_id", "=", self.company.id)], limit=1,
        )
        stock_request = self.env["mrp.stock.request"].create({
            "picking_type_id": picking_type.id,
            "location_id": self.location.id,
            "location_dest_id": self.env.ref("stock.stock_location_locations_production").id,
            "mo_ids": [(6, 0, [mo.id])],
        })
        request_line = self.env["mrp.stock.request.line"].create({
            "request_id": stock_request.id,
            "product_id": self.comp_a.id,
            "uom_id": self.uom_unit.id,
            "qty_requested": 5.0,
            "move_ids": [(6, 0, [move.id])],
        })
        self.env["mrp.stock.request.allocation"].create({
            "request_line_id": request_line.id,
            "mo_id": mo.id,
            "uom_id": self.uom_unit.id,
            "qty_consumed": 3.0,
        })

        data = self.engine.get_wip_data(mo_ids=[mo.id], status_list=["done"])
        material = data["data"][0]["materials"][0]
        self.assertEqual(material["mrp_request_name"], stock_request.name)
        self.assertAlmostEqual(material["qty_allocated_to_job"], 3.0)
