# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.tests import tagged
from odoo.exceptions import ValidationError

from odoo.addons.buz_stock_location_consistency.models.location_helpers import (
    loc_contained,
)


@tagged("post_install", "-at_install")
class TestLocationConsistency(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # bypass env-specific guards from sibling custom modules
        grp = cls.env.ref(
            "buz_validate_control.group_validate_privileged", raise_if_not_found=False)
        if grp:
            cls.env.user.groups_id = [(4, grp.id)]
        cls.Location = cls.env["stock.location"]
        cls.stock = cls.env.ref("stock.stock_location_stock")
        cls.sub = cls.Location.create({
            "name": "CONSISTENCY_SUB", "location_id": cls.stock.id,
        })
        cls.other = cls.Location.create({
            "name": "CONSISTENCY_OTHER",
            "location_id": cls.env.ref("stock.stock_location_locations_virtual").id,
        })
        cls.internal_type = cls.env.ref("stock.picking_type_internal")

    # ---- helper -------------------------------------------------------

    def _make_done_internal_move(self, src=None, dest=None, qty=5.0):
        """Create + validate a same-warehouse internal transfer, return the move."""
        src = src or self.stock
        dest = dest or self.sub
        product = self.env["product.product"].create({
            "name": "CONSISTENCY_PROD", "type": "product",
        })
        self.env["stock.quant"]._update_available_quantity(product, src, qty)
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.internal_type.id,
            "location_id": src.id,
            "location_dest_id": dest.id,
            "bypass_reservation_guard": True,
            "bypass_location_lock": True,
            "move_ids": [(0, 0, {
                "name": product.name, "product_id": product.id,
                "product_uom_qty": qty, "product_uom": product.uom_id.id,
                "location_id": src.id, "location_dest_id": dest.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_ids.move_line_ids:
            ml.quantity = ml.quantity_product_uom or qty
        picking.button_validate()
        self.assertEqual(picking.state, "done")
        return picking.move_ids

    # ---- containment helper ----------------------------------------

    def test_loc_contained_true_cases(self):
        self.assertTrue(loc_contained(self.stock, self.stock))
        self.assertTrue(loc_contained(self.sub, self.stock))
        self.assertTrue(loc_contained(self.env["stock.location"], self.stock))

    def test_loc_contained_false_case(self):
        self.assertFalse(loc_contained(self.other, self.stock))

    # ---- stock.move guard ----------------------------------------

    def test_done_move_source_change_blocked(self):
        move = self._make_done_internal_move()
        with self.assertRaises(ValidationError):
            move.write({"location_id": self.other.id})

    def test_done_move_source_change_orm_bulk_blocked(self):
        move = self._make_done_internal_move()
        with self.assertRaises(ValidationError):
            self.env["stock.move"].browse(move.id).write({"location_id": self.other.id})

    def test_done_move_bypass_flag_allows(self):
        move = self._make_done_internal_move()
        move.with_context(skip_location_consistency_check=True).write(
            {"location_id": self.other.id})
        self.assertEqual(move.location_id, self.other)

    def test_legacy_divergent_move_unrelated_write_allowed(self):
        move = self._make_done_internal_move()
        move.with_context(skip_location_consistency_check=True).write(
            {"location_id": self.other.id})
        move.write({"date_deadline": move.date})

    def test_unreserved_move_source_change_repoints_lines(self):
        product = self.env["product.product"].create({
            "name": "CONSISTENCY_UNRES", "type": "product"})
        self.env["stock.quant"]._update_available_quantity(product, self.stock, 3.0)
        self.env["stock.quant"]._update_available_quantity(product, self.sub, 3.0)
        p2 = self.env["stock.picking"].create({
            "picking_type_id": self.internal_type.id,
            "location_id": self.stock.id, "location_dest_id": self.sub.id,
            "bypass_reservation_guard": True,
            "bypass_location_lock": True,
            "move_ids": [(0, 0, {
                "name": product.name, "product_id": product.id,
                "product_uom_qty": 3.0, "product_uom": product.uom_id.id,
                "location_id": self.stock.id, "location_dest_id": self.sub.id,
            })],
        })
        p2.action_confirm()
        p2.move_ids.write({"location_id": self.sub.id})
        self.assertEqual(p2.move_ids.location_id, self.sub)
        self.assertFalse(p2.move_ids.move_line_ids.filtered(
            lambda l: not loc_contained(l.location_id, self.sub)))

    def test_reserved_pickingless_move_source_change_no_crash(self):
        """A picking-less reserved move whose reassign fails must not raise
        (message_post would ensure_one() on an empty picking_id)."""
        product = self.env["product.product"].create({
            "name": "CONSISTENCY_NOPICK", "type": "product"})
        self.env["stock.quant"]._update_available_quantity(product, self.stock, 2.0)
        move = self.env["stock.move"].create({
            "name": product.name, "product_id": product.id,
            "product_uom_qty": 2.0, "product_uom": product.uom_id.id,
            "location_id": self.stock.id, "location_dest_id": self.sub.id,
        })
        move._action_confirm()
        move._action_assign()
        self.assertEqual(move.state, "assigned")
        self.assertFalse(move.picking_id)
        # new source (self.sub) has no stock -> reassign can't cover
        move.write({"location_id": self.sub.id})
        self.assertEqual(move.location_id, self.sub)

    # ---- stock.picking guard ----------------------------------------

    def test_picking_source_change_on_done_blocked(self):
        move = self._make_done_internal_move()
        with self.assertRaises(ValidationError):
            move.picking_id.write({"location_id": self.other.id})

    def test_picking_source_change_on_reserved_follows(self):
        product = self.env["product.product"].create({
            "name": "CONSISTENCY_RES", "type": "product"})
        self.env["stock.quant"]._update_available_quantity(product, self.stock, 4.0)
        self.env["stock.quant"]._update_available_quantity(product, self.sub, 4.0)
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.internal_type.id,
            "location_id": self.stock.id, "location_dest_id": self.other.id,
            "bypass_reservation_guard": True,
            "bypass_location_lock": True,
            "move_ids": [(0, 0, {
                "name": product.name, "product_id": product.id,
                "product_uom_qty": 4.0, "product_uom": product.uom_id.id,
                "location_id": self.stock.id, "location_dest_id": self.other.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        self.assertEqual(picking.move_ids.state, "assigned")
        svl_before = self.env["stock.valuation.layer"].search_count([])
        picking.write({"location_id": self.sub.id})
        self.assertEqual(
            self.env["stock.valuation.layer"].search_count([]), svl_before)
        self.assertEqual(picking.move_ids.location_id, self.sub)
        self.assertFalse(picking.move_ids.move_line_ids.filtered(
            lambda l: not loc_contained(l.location_id, self.sub)))

    # ---- mismatch report ----------------------------------------

    def test_mismatch_view_lists_out_of_subtree_row(self):
        move = self._make_done_internal_move()
        move.with_context(skip_location_consistency_check=True).write(
            {"location_id": self.other.id})
        self.env.flush_all()  # SQL view can't see un-flushed ORM writes
        rows = self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])
        self.assertTrue(rows)
        self.assertEqual(rows[0].header_location_id, self.other)

    def test_mismatch_view_ignores_child_of_split(self):
        move = self._make_done_internal_move(src=self.stock, dest=self.sub)
        self.env.flush_all()
        rows = self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])
        self.assertFalse(rows)
