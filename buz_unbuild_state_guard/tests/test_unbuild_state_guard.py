# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestUnbuildStateGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.production_location = cls.env["stock.location"].search(
            [("usage", "=", "production"), ("company_id", "in", [False, cls.company.id])],
            limit=1,
        )
        # Destination for produced components: must be distinct from both the
        # source stock location AND property_stock_production, otherwise the
        # BOM-line produce move has location_id == location_dest_id (both
        # resolve to the product's own production location) and nets to zero.
        cls.destination_location = cls.env["stock.location"].search(
            [
                ("usage", "=", "internal"),
                ("company_id", "in", [False, cls.company.id]),
                ("id", "!=", cls.stock_location.id),
            ],
            limit=1,
        )
        if not cls.destination_location:
            cls.destination_location = cls.env["stock.location"].create(
                {
                    "name": "Guarded Unbuild Destination",
                    "usage": "internal",
                    "location_id": cls.stock_location.location_id.id,
                    "company_id": cls.company.id,
                }
            )

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
                "standard_price": 10.0,
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
            "location_dest_id": self.destination_location.id,
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

        # Confirm done — triggers standard action_unbuild (BOM explosion)
        unbuild.action_confirm_done()

        self.assertEqual(unbuild.state, "done")

        # location_id was synced to picking destination before unbuild ran
        self.assertEqual(unbuild.location_id, picking.location_dest_id)

        # Component is produced at location_dest_id (destination_location)
        component_qty = self.env["stock.quant"]._get_available_quantity(
            self.component, self.destination_location
        )
        self.assertEqual(
            component_qty, 1.0,
            "Component should be produced at location_dest after BOM explosion",
        )

        # The unbuild's finished-product consume move deposits the product into
        # the virtual Production location (Odoo core behavior, not real stock) —
        # it does not net back to zero there.
        product_qty = self.env["stock.quant"]._get_available_quantity(
            self.product, self.production_location
        )
        self.assertEqual(
            product_qty, 1.0,
            "Product consume move lands in the virtual Production location",
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

    def test_08_direct_unbuild_from_draft_succeeds(self):
        """Draft → Done directly when stock is available and no picking was created."""
        unbuild = self._create_unbuild()

        unbuild.action_direct_unbuild()

        self.assertEqual(unbuild.state, "done")
        component_qty = self.env["stock.quant"]._get_available_quantity(
            self.component, self.destination_location
        )
        self.assertEqual(component_qty, 1.0)

    def test_09_direct_unbuild_blocked_with_open_picking(self):
        """Direct unbuild is blocked once a (non-cancelled) picking is linked."""
        unbuild = self._create_unbuild()
        unbuild.action_create_picking()

        with self.assertRaises(UserError):
            unbuild.action_direct_unbuild()

    def test_10_component_zero_cost_blocks_confirm_done(self):
        """Zero-cost component blocks the picking-confirm route."""
        self.component.standard_price = 0.0
        unbuild = self._create_unbuild()
        unbuild.action_create_picking()

        picking = unbuild.picking_id
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate()

        with self.assertRaises(UserError):
            unbuild.action_confirm_done()

    def test_11_component_zero_cost_blocks_direct_unbuild(self):
        """Zero-cost component blocks the direct-unbuild route."""
        self.component.standard_price = 0.0
        unbuild = self._create_unbuild()

        with self.assertRaises(UserError):
            unbuild.action_direct_unbuild()
