from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestStockReservationGuard(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.internal_type = self.env.ref("stock.picking_type_internal")
        self.parent_location = self.env.ref("stock.stock_location_locations")
        self.dest_location = self.env.ref("stock.stock_location_stock")
        self.source_with_stock = self.env["stock.location"].create(
            {
                "name": "With Stock",
                "location_id": self.parent_location.id,
                "usage": "internal",
            }
        )
        self.source_empty = self.env["stock.location"].create(
            {
                "name": "Empty Source",
                "location_id": self.parent_location.id,
                "usage": "internal",
            }
        )
        self.product = self.env.ref("product.product_delivery_01")
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.source_with_stock, 5.0
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
