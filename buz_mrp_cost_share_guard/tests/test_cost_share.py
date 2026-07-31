# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestByproductCostShare(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        # Reuse existing internal locations / warehouse where possible
        # (avoid creating a new stock.warehouse: dev DB has orphaned
        # columns on that model).
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)

        category = cls.env.ref("product.product_category_all")

        def make_product(name, code):
            return cls.env["product.product"].create({
                "name": name,
                "default_code": code,
                "detailed_type": "product",
                "categ_id": category.id,
                "uom_id": cls.uom_unit.id,
                "uom_po_id": cls.uom_unit.id,
            })

        cls.raw1 = make_product("Cost Share Raw 1", "CSG-RAW1")
        cls.raw2 = make_product("Cost Share Raw 2", "CSG-RAW2")
        cls.finished = make_product("Cost Share Finished", "CSG-FIN")
        cls.byproduct = make_product("Cost Share Byproduct", "CSG-BYP")

        cls.bom = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.finished.product_tmpl_id.id,
            "product_qty": 1.0,
            "product_uom_id": cls.uom_unit.id,
            "type": "normal",
            "bom_line_ids": [
                (0, 0, {
                    "product_id": cls.raw1.id,
                    "product_qty": 1.0,
                    "product_uom_id": cls.uom_unit.id,
                }),
                (0, 0, {
                    "product_id": cls.raw2.id,
                    "product_qty": 1.0,
                    "product_uom_id": cls.uom_unit.id,
                }),
            ],
            "byproduct_ids": [
                (0, 0, {
                    "product_id": cls.byproduct.id,
                    "product_qty": 1.0,
                    "product_uom_id": cls.uom_unit.id,
                    "cost_share": 10.0,
                }),
            ],
        })

    def _stock_raw_materials(self, raw1_cost=1000.0, raw2_cost=200.0):
        self.env["stock.quant"]._update_available_quantity(
            self.raw1, self.warehouse.lot_stock_id, 1.0)
        self.env["stock.quant"]._update_available_quantity(
            self.raw2, self.warehouse.lot_stock_id, 1.0)
        self.raw1.sudo().write({"standard_price": raw1_cost})
        self.raw2.sudo().write({"standard_price": raw2_cost})

    def _create_mo(self):
        mo = self.env["mrp.production"].create({
            "product_id": self.finished.id,
            "product_qty": 1.0,
            "product_uom_id": self.uom_unit.id,
            "bom_id": self.bom.id,
            "company_id": self.company.id,
        })
        mo.action_confirm()
        mo.action_assign()
        return mo

    def test_01_staggered_consumption_full_cost_split(self):
        """Raw material consumed in two separate steps (one component
        marked done before the final "Mark as Done") must still split
        the by-product cost against the FULL raw total, not just the
        component that turned 'done' in the final step."""
        self._stock_raw_materials(raw1_cost=1000.0, raw2_cost=200.0)
        mo = self._create_mo()

        raw_move_1 = mo.move_raw_ids.filtered(
            lambda m: m.product_id == self.raw1)
        raw_move_1.picked = True
        raw_move_1.quantity = 1.0
        raw_move_1._action_done()
        self.assertEqual(raw_move_1.state, "done")

        mo.qty_producing = 1.0
        raw_move_2 = mo.move_raw_ids.filtered(
            lambda m: m.product_id == self.raw2)
        raw_move_2.picked = True
        raw_move_2.quantity = 1.0
        mo.with_context(skip_backorder=True).button_mark_done()
        self.assertEqual(mo.state, "done")

        finished_move = mo.move_finished_ids.filtered(
            lambda m: m.product_id == self.finished)
        byproduct_move = mo.move_byproduct_ids

        finished_value = sum(
            finished_move.stock_valuation_layer_ids.mapped("value"))
        byproduct_value = sum(
            byproduct_move.stock_valuation_layer_ids.mapped("value"))
        total_value = finished_value + byproduct_value

        self.assertAlmostEqual(total_value, 1200.0, places=2)
        self.assertAlmostEqual(byproduct_value, 120.0, places=2)  # 10%
        self.assertAlmostEqual(finished_value, 1080.0, places=2)  # 90%

    def test_02_single_step_consumption_still_correct(self):
        """Regression: normal (non-staggered) consumption in one shot
        must keep working exactly as before."""
        self._stock_raw_materials(raw1_cost=1000.0, raw2_cost=200.0)
        mo = self._create_mo()
        mo.qty_producing = 1.0
        for move in mo.move_raw_ids:
            move.picked = True
            move.quantity = 1.0
        mo.with_context(skip_backorder=True).button_mark_done()
        self.assertEqual(mo.state, "done")

        finished_move = mo.move_finished_ids.filtered(
            lambda m: m.product_id == self.finished)
        byproduct_move = mo.move_byproduct_ids
        finished_value = sum(
            finished_move.stock_valuation_layer_ids.mapped("value"))
        byproduct_value = sum(
            byproduct_move.stock_valuation_layer_ids.mapped("value"))

        self.assertAlmostEqual(byproduct_value, 120.0, places=2)
        self.assertAlmostEqual(finished_value, 1080.0, places=2)

    def test_03_zero_cost_share_blocks_mark_done(self):
        """Existing guard: a by-product left at 0% cost share must
        block Mark as Done with a clear error."""
        self._stock_raw_materials()
        self.bom.byproduct_ids.cost_share = 0.0
        mo = self._create_mo()
        mo.qty_producing = 1.0
        for move in mo.move_raw_ids:
            move.picked = True
            move.quantity = 1.0
        with self.assertRaises(UserError):
            mo.with_context(skip_backorder=True).button_mark_done()

    def test_04_balance_check_flags_corrupted_valuation(self):
        """Safety net: if a by-product's valuation layer is corrupted
        after the fact (e.g. by another module, manual edit, or a
        future regression), `_check_byproduct_cost_balance` must post
        a warning instead of staying silent."""
        self._stock_raw_materials(raw1_cost=1000.0, raw2_cost=200.0)
        mo = self._create_mo()
        mo.qty_producing = 1.0
        for move in mo.move_raw_ids:
            move.picked = True
            move.quantity = 1.0
        mo.with_context(skip_backorder=True).button_mark_done()

        message_count_before = len(mo.message_ids)
        mo._check_byproduct_cost_balance()
        self.assertEqual(
            len(mo.message_ids), message_count_before,
            "correct valuation must not raise a warning")

        mo.move_byproduct_ids.stock_valuation_layer_ids.sudo().write(
            {"value": 1.0})
        mo._check_byproduct_cost_balance()
        messages = mo.message_ids.filtered(
            lambda m: m.body and "By-product" in m.body)
        self.assertTrue(
            messages, "corrupted valuation must trigger a warning message")
