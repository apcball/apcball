from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestStockReservationGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.internal_type = cls.env.ref("stock.picking_type_internal")
        cls.parent_location = cls.env.ref("stock.stock_location_locations")
        cls.dest_location = cls.env.ref("stock.stock_location_stock")
        cls.source_with_stock = cls.env["stock.location"].create(
            {
                "name": "Guard Stock",
                "location_id": cls.parent_location.id,
                "usage": "internal",
            }
        )
        cls.source_empty = cls.env["stock.location"].create(
            {
                "name": "Guard Empty",
                "location_id": cls.parent_location.id,
                "usage": "internal",
            }
        )
        cls.product = cls.env["product.product"].search([("type", "=", "product")], limit=1)
        if cls.product:
            cls.env["stock.quant"]._update_available_quantity(
                cls.product, cls.source_with_stock, 5.0
            )

    def _create_picking(self, source_location):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.internal_type.id,
                "location_id": source_location.id,
                "location_dest_id": self.dest_location.id,
            }
        )
        move = self.env["stock.move"].create(
            {
                "name": self.product.display_name,
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "product_uom": self.product.uom_id.id,
                "picking_id": picking.id,
                "location_id": source_location.id,
                "location_dest_id": self.dest_location.id,
            }
        )
        picking.action_confirm()
        return picking, move

    def test_block_create_reserved_line_from_empty_location(self):
        picking, move = self._create_picking(self.source_empty)

        with self.assertRaises(UserError):
            self.env["stock.move.line"].create(
                {
                    "picking_id": picking.id,
                    "move_id": move.id,
                    "product_id": self.product.id,
                    "location_id": self.source_empty.id,
                    "location_dest_id": self.dest_location.id,
                    "quantity": 1.0,
                }
            )

        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.source_empty.id),
            ]
        )
        self.assertFalse(quant, "Guard should prevent reserved-only quant creation")

    def test_allow_create_reserved_line_from_stocked_location(self):
        picking, move = self._create_picking(self.source_with_stock)

        move_line = self.env["stock.move.line"].create(
            {
                "picking_id": picking.id,
                "move_id": move.id,
                "product_id": self.product.id,
                "location_id": self.source_with_stock.id,
                "location_dest_id": self.dest_location.id,
                "quantity": 1.0,
            }
        )

        self.assertEqual(move_line.quantity, 1.0)

    def test_block_write_when_moving_reservation_to_empty_location(self):
        picking, _move = self._create_picking(self.source_with_stock)
        picking.action_assign()
        move_line = picking.move_line_ids
        self.assertTrue(move_line, "Expected a reserved line after assignment")

        with self.assertRaises(UserError):
            move_line.write({"location_id": self.source_empty.id})

        self.assertEqual(move_line.location_id, self.source_with_stock)
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.source_empty.id),
            ]
        )
        self.assertFalse(quant, "Failed write should not create a phantom quant")

    def test_block_action_assign_from_empty_location(self):
        picking, _move = self._create_picking(self.source_empty)

        with self.assertRaises(UserError):
            picking.action_assign()

        self.assertEqual(picking.state, "confirmed")
        self.assertFalse(picking.move_line_ids)

    def test_block_validate_from_empty_location(self):
        picking, move = self._create_picking(self.source_empty)
        move.write({"quantity": 1.0})

        with self.assertRaises(UserError):
            picking.button_validate()

    def test_bypass_with_flag_allows_validation(self):
        picking, move = self._create_picking(self.source_empty)
        move.write({"quantity": 1.0})

        with self.assertRaises(UserError):
            picking.button_validate()

        picking.write({"bypass_reservation_guard": True})
        self.assertTrue(picking.bypass_reservation_guard)

    def test_force_unreserve_sets_bypass_flag(self):
        picking, move = self._create_picking(self.source_empty)
        move.write({"quantity": 1.0})

        with self.assertRaises(UserError):
            picking.button_validate()

        picking.force_unreserve()
        self.assertTrue(picking.bypass_reservation_guard)

    def test_allow_validate_when_already_reserved_covers_demand(self):
        """A move already assigned (reserved_quantity == quantity, free pool == 0)
        must still validate: physical on-hand covers the move's own reservation."""
        picking, move = self._create_picking(self.source_with_stock)
        move.write({"product_uom_qty": 5.0})
        picking.action_assign()
        self.assertEqual(picking.state, "assigned")

        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product.id),
                ("location_id", "=", self.source_with_stock.id),
            ]
        )
        self.assertEqual(quant.quantity, 5.0)
        self.assertEqual(quant.reserved_quantity, 5.0)

        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_block_validate_when_physical_stock_below_demand(self):
        """Genuine shortage: physical on-hand less than demand must still block."""
        picking, move = self._create_picking(self.source_with_stock)
        move.write({"product_uom_qty": 10.0})
        picking.action_confirm()

        with self.assertRaises(UserError):
            picking.button_validate()
