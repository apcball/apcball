# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestUnbuildStateGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.production_location = cls.env.ref("stock.stock_location_production")

        cls.product = cls.env["product.product"].create(
            {
                "name": "Guarded Unbuild Product",
                "detailed_type": "product",
                "categ_id": cls.env.ref("product.product_category_all").id,
            }
        )
        cls.component = cls.env["product.product"].create(
            {
                "name": "Guarded Unbuild Component",
                "detailed_type": "product",
                "categ_id": cls.env.ref("product.product_category_all").id,
            }
        )
        # Put product in stock so unbuild can consume it
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 10.0
        )

        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.product.product_tmpl_id.id,
                "product_qty": 1.0,
                "bom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.component.id,
                            "product_qty": 1.0,
                            "product_uom_id": cls.component.uom_id.id,
                        },
                    )
                ],
            }
        )

    def _create_unbuild(self):
        vals = {
            "product_id": self.product.id,
            "bom_id": self.bom.id,
            "product_qty": 1.0,
            "company_id": self.company.id,
            "location_id": self.stock_location.id,
            "location_dest_id": self.production_location.id,
        }
        if "product_uom_id" in self.env["mrp.unbuild"]._fields:
            vals["product_uom_id"] = self.product.uom_id.id
        return self.env["mrp.unbuild"].create(vals)

    def test_01_create_picking_moves_to_picking(self):
        """Draft → Picking when creating picking."""
        unbuild = self._create_unbuild()

        self.assertEqual(unbuild.state, "draft")
        action = unbuild.action_create_picking()

        self.assertEqual(unbuild.state, "picking")
        self.assertTrue(unbuild.picking_id)
        self.assertEqual(unbuild.picking_count, 1)
        self.assertEqual(unbuild.picking_id.state, "draft")
        self.assertEqual(action["res_id"], unbuild.picking_id.id)

    def test_02_validate_picking_moves_to_confirm(self):
        """Validating picking moves unbuild to 'confirm' (not done)."""
        unbuild = self._create_unbuild()
        unbuild.action_create_picking()

        picking = unbuild.picking_id
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()

        self.assertEqual(picking.state, "done")
        self.assertEqual(unbuild.state, "confirm")

    def test_03_confirm_done_triggers_bom_explosion(self):
        """Confirm Done triggers standard BOM explosion: component returns to location_dest."""
        unbuild = self._create_unbuild()
        unbuild.action_create_picking()

        picking = unbuild.picking_id
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()

        self.assertEqual(unbuild.state, "confirm")

        # location_id is synced to picking destination before unbuild runs
        self.assertEqual(unbuild.location_id, picking.location_dest_id)

        # Confirm done — triggers standard action_unbuild (BOM explosion)
        unbuild.action_confirm_done()

        self.assertEqual(unbuild.state, "done")

        # Component is produced at location_dest_id (production_location)
        component_qty = self.env["stock.quant"]._get_available_quantity(
            self.component, self.production_location
        )
        self.assertEqual(
            component_qty, 1.0,
            "Component should be produced at location_dest after BOM explosion",
        )

        # Product was consumed from the picking destination (where it was moved to)
        product_qty = self.env["stock.quant"]._get_available_quantity(
            self.product, self.production_location
        )
        # After picking: product moved to production_location (qty 1)
        # After unbuild: product consumed from production_location (qty -1)
        # Net = 0 at production_location, 9 left at stock_location
        self.assertEqual(
            product_qty, 0.0,
            "Product should be consumed from production_location after unbuild",
        )

        # Original stock should have 9 left (10 - 1 moved out by picking)
        product_stock_qty = self.env["stock.quant"]._get_available_quantity(
            self.product, self.stock_location
        )
        self.assertEqual(
            product_stock_qty, 9.0,
            "Product stock should be 9 after 1 was moved and consumed",
        )

    def test_04_direct_unbuild_is_blocked(self):
        """Direct action_unbuild is blocked — must go through picking flow."""
        unbuild = self._create_unbuild()

        with self.assertRaises(UserError):
            unbuild.action_unbuild()

    def test_05_direct_done_is_blocked(self):
        """Direct action_done is blocked — must go through picking flow."""
        unbuild = self._create_unbuild()

        with self.assertRaises(UserError):
            unbuild.action_done()

    def test_06_cancel_picking_returns_to_draft(self):
        """Cancel from picking state returns to draft."""
        unbuild = self._create_unbuild()
        unbuild.action_create_picking()

        self.assertEqual(unbuild.state, "picking")

        unbuild.action_cancel_picking()

        self.assertEqual(unbuild.state, "draft")

    def test_07_confirm_done_blocked_from_wrong_state(self):
        """Confirm Done can only be called from 'confirm' state."""
        unbuild = self._create_unbuild()

        with self.assertRaises(UserError):
            unbuild.action_confirm_done()
