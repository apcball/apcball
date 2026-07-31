# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestUnbuildComponentLines(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        # Reuse existing internal locations where possible (avoid creating
        # warehouses: dev DB has orphaned columns on stock.warehouse).
        cls.dest_a = cls.env["stock.location"].create({
            "name": "Unbuild Return A",
            "usage": "internal",
            "location_id": cls.stock_location.id,
            "company_id": cls.company.id,
        })
        cls.dest_b = cls.env["stock.location"].create({
            "name": "Unbuild Return B",
            "usage": "internal",
            "location_id": cls.stock_location.id,
            "company_id": cls.company.id,
        })
        cls.supplier_location = cls.env.ref("stock.stock_location_suppliers")

        category = cls.env.ref("product.product_category_all")
        cls.finished = cls.env["product.product"].create({
            "name": "Enh Unbuild Finished",
            "detailed_type": "product",
            "categ_id": category.id,
        })
        cls.panel = cls.env["product.product"].create({
            "name": "Enh Unbuild Panel",
            "detailed_type": "product",
            "categ_id": category.id,
        })
        cls.screw = cls.env["product.product"].create({
            "name": "Enh Unbuild Screw",
            "detailed_type": "product",
            "categ_id": category.id,
        })

        cls.bom = cls.env["mrp.bom"].create({
            "product_tmpl_id": cls.finished.product_tmpl_id.id,
            "product_qty": 1.0,
            "bom_line_ids": [
                Command.create({
                    "product_id": cls.panel.id,
                    "product_qty": 2.0,
                    "product_uom_id": cls.panel.uom_id.id,
                }),
                Command.create({
                    "product_id": cls.screw.id,
                    "product_qty": 20.0,
                    "product_uom_id": cls.screw.uom_id.id,
                }),
            ],
        })
        cls.env["stock.quant"]._update_available_quantity(
            cls.finished, cls.stock_location, 10.0)

    def _create_unbuild(self, qty=2.0, generate=True):
        unbuild = self.env["mrp.unbuild"].create({
            "product_id": self.finished.id,
            "bom_id": self.bom.id,
            "product_qty": qty,
            "product_uom_id": self.finished.uom_id.id,
            "location_id": self.stock_location.id,
            "location_dest_id": self.stock_location.id,
            "company_id": self.company.id,
        })
        if generate:
            unbuild.action_generate_component_lines()
        return unbuild

    def _line(self, unbuild, product):
        return unbuild.component_line_ids.filtered(
            lambda l: l.product_id == product)

    def test_01_generate_lines_from_bom(self):
        unbuild = self._create_unbuild(qty=2.0)
        self.assertEqual(len(unbuild.component_line_ids), 2)
        panel_line = self._line(unbuild, self.panel)
        screw_line = self._line(unbuild, self.screw)
        self.assertEqual(panel_line.quantity, 4.0)  # 2 per unit x 2
        self.assertEqual(screw_line.quantity, 40.0)  # 20 per unit x 2
        self.assertEqual(panel_line.expected_qty, 4.0)
        self.assertTrue(panel_line.receive)
        self.assertEqual(
            panel_line.destination_location_id, self.stock_location)

    def test_02_edited_quantity_drives_move(self):
        unbuild = self._create_unbuild(qty=2.0)
        screw_line = self._line(unbuild, self.screw)
        screw_line.quantity = 38.0
        unbuild.action_unbuild()
        move = unbuild.produce_line_ids.filtered(
            lambda m: m.product_id == self.screw)
        self.assertEqual(move.product_uom_qty, 38.0)
        self.assertEqual(unbuild.state, "done")

    def test_03_bom_line_default_return_location(self):
        self.bom.bom_line_ids.filtered(
            lambda l: l.product_id == self.panel
        ).default_return_location_id = self.dest_a
        unbuild = self._create_unbuild()
        panel_line = self._line(unbuild, self.panel)
        screw_line = self._line(unbuild, self.screw)
        self.assertEqual(panel_line.destination_location_id, self.dest_a)
        self.assertEqual(
            screw_line.destination_location_id, self.stock_location)

    def test_04_receive_false_skips_move(self):
        unbuild = self._create_unbuild()
        self._line(unbuild, self.panel).receive = False
        unbuild.action_unbuild()
        products = unbuild.produce_line_ids.mapped("product_id")
        self.assertNotIn(self.panel, products)
        self.assertIn(self.screw, products)

    def test_05_scrap_qty_creates_validated_scrap(self):
        unbuild = self._create_unbuild()
        screw_line = self._line(unbuild, self.screw)
        screw_line.write({
            "quantity": 10.0,
            "scrap_qty": 2.0,
            "destination_location_id": self.dest_a.id,
        })
        unbuild.action_unbuild()
        self.assertEqual(len(unbuild.scrap_ids), 1)
        scrap = unbuild.scrap_ids
        self.assertEqual(scrap.state, "done")
        self.assertEqual(scrap.scrap_qty, 2.0)
        self.assertEqual(scrap.location_id, self.dest_a)
        # Move receives the full 10; net on hand after scrap = 8
        move = unbuild.produce_line_ids.filtered(
            lambda m: m.product_id == self.screw)
        self.assertEqual(move.product_uom_qty, 10.0)
        on_hand = self.env["stock.quant"]._get_available_quantity(
            self.screw, self.dest_a)
        self.assertEqual(on_hand, 8.0)

    def test_06_per_line_destination(self):
        unbuild = self._create_unbuild()
        self._line(unbuild, self.panel).destination_location_id = self.dest_a
        self._line(unbuild, self.screw).destination_location_id = self.dest_b
        unbuild.action_unbuild()
        panel_move = unbuild.produce_line_ids.filtered(
            lambda m: m.product_id == self.panel)
        screw_move = unbuild.produce_line_ids.filtered(
            lambda m: m.product_id == self.screw)
        self.assertEqual(panel_move.location_dest_id, self.dest_a)
        self.assertEqual(screw_move.location_dest_id, self.dest_b)

    def test_07_non_internal_destination_raises(self):
        unbuild = self._create_unbuild()
        with self.assertRaises(ValidationError):
            self._line(unbuild, self.panel).destination_location_id = (
                self.supplier_location)

    def test_08_scrap_exceeds_quantity_raises(self):
        unbuild = self._create_unbuild()
        line = self._line(unbuild, self.screw)
        with self.assertRaises(ValidationError):
            line.write({"quantity": 5.0, "scrap_qty": 6.0})

    def test_09_all_lines_skipped_raises(self):
        unbuild = self._create_unbuild()
        unbuild.component_line_ids.write({"receive": False})
        with self.assertRaises(ValidationError):
            unbuild.action_unbuild()

    def test_10_no_lines_falls_back_to_core(self):
        unbuild = self._create_unbuild(generate=False)
        self.assertFalse(unbuild.component_line_ids)
        unbuild.action_unbuild()
        self.assertEqual(unbuild.state, "done")
        # Core behavior: component moves target the common destination
        # (produce_line_ids also holds the finished-product consume move
        # whose destination is the virtual production location).
        component_moves = unbuild.produce_line_ids.filtered(
            lambda m: m.product_id in (self.panel | self.screw))
        self.assertTrue(component_moves)
        for move in component_moves:
            self.assertEqual(move.location_dest_id, self.stock_location)

    def test_11_summary_posted_and_counts(self):
        unbuild = self._create_unbuild()
        self._line(unbuild, self.panel).receive = False
        screw_line = self._line(unbuild, self.screw)
        screw_line.scrap_qty = 2.0
        unbuild.action_unbuild()
        self.assertEqual(unbuild.component_line_count, 2)
        self.assertEqual(unbuild.returned_move_count, 1)
        self.assertEqual(unbuild.scrap_count, 1)
        messages = unbuild.message_ids.filtered(
            lambda m: m.body and "Unbuild completed" in m.body)
        self.assertTrue(messages)

    def test_12_tracked_component_requires_mo(self):
        tracked = self.env["product.product"].create({
            "name": "Enh Tracked Component",
            "detailed_type": "product",
            "tracking": "lot",
            "categ_id": self.env.ref("product.product_category_all").id,
        })
        self.bom.bom_line_ids = [Command.create({
            "product_id": tracked.id,
            "product_qty": 1.0,
            "product_uom_id": tracked.uom_id.id,
        })]
        unbuild = self._create_unbuild()
        with self.assertRaises(ValidationError):
            unbuild.action_unbuild()
