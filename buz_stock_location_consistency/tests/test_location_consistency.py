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

    # ---- stock.move.line guard (line must stay within its move header) ----

    def _draft_move(self, name, src=None, dest=None, qty=1.0, seed_locs=None):
        src = src or self.stock
        dest = dest or self.sub
        product = self.env["product.product"].create({
            "name": name, "type": "product"})
        # buz_stock_reservation_guard blocks a move-line create at a source
        # with no on-hand stock; seed every location a test will pick from.
        for loc in (seed_locs or [src]):
            self.env["stock.quant"]._update_available_quantity(
                product, loc, qty + 10.0)
        move = self.env["stock.move"].create({
            "name": product.name, "product_id": product.id,
            "product_uom_qty": qty, "product_uom": product.uom_id.id,
            "location_id": src.id, "location_dest_id": dest.id,
        })
        move._action_confirm()
        return move, product

    def test_move_line_dest_outside_header_dest_blocked(self):
        """POJ0012387 shape: a produce/transfer move line whose destination
        sits in a different warehouse than the move header destination."""
        move, product = self._draft_move("ML_DEST_BAD")
        with self.assertRaises(ValidationError):
            self.env["stock.move.line"].create({
                "move_id": move.id, "product_id": product.id,
                "quantity": 1.0,
                "location_id": self.stock.id,
                "location_dest_id": self.other.id,
            })

    def test_move_line_source_outside_header_source_blocked(self):
        move, product = self._draft_move(
            "ML_SRC_BAD", seed_locs=[self.stock, self.other])
        with self.assertRaises(ValidationError):
            self.env["stock.move.line"].create({
                "move_id": move.id, "product_id": product.id,
                "quantity": 1.0,
                "location_id": self.other.id,
                "location_dest_id": self.sub.id,
            })

    def test_move_line_dest_child_of_header_dest_allowed(self):
        """A putaway split to a sub-location of the header dest is legit."""
        subsub = self.Location.create({
            "name": "CONSISTENCY_SUBSUB", "location_id": self.sub.id})
        move, product = self._draft_move("ML_DEST_OK", dest=self.sub)
        ml = self.env["stock.move.line"].create({
            "move_id": move.id, "product_id": product.id,
            "quantity": 1.0,
            "location_id": self.stock.id,
            "location_dest_id": subsub.id,
        })
        self.assertEqual(ml.location_dest_id, subsub)

    def test_move_line_divergence_bypass_allows(self):
        move, product = self._draft_move("ML_BYPASS")
        ml = self.env["stock.move.line"].with_context(
            skip_location_consistency_check=True).create({
                "move_id": move.id, "product_id": product.id,
                "quantity": 1.0,
                "location_id": self.stock.id,
                "location_dest_id": self.other.id,
            })
        self.assertEqual(ml.location_dest_id, self.other)

    def test_move_line_write_dest_outside_header_blocked(self):
        move, product = self._draft_move("ML_WRITE_BAD")
        move._action_assign()
        ml = move.move_line_ids[:1] or self.env["stock.move.line"].create({
            "move_id": move.id, "product_id": product.id, "quantity": 1.0,
            "location_id": self.stock.id, "location_dest_id": self.sub.id})
        with self.assertRaises(ValidationError):
            ml.write({"location_dest_id": self.other.id})

    # ---- stock.move header dest guard ----------------------------------

    def test_done_move_dest_change_orphaning_lines_blocked(self):
        move = self._make_done_internal_move(src=self.stock, dest=self.sub)
        with self.assertRaises(ValidationError):
            move.write({"location_dest_id": self.other.id})

    # ---- mismatch report: destination axis ---------------------------

    def test_mismatch_view_lists_dest_axis_row(self):
        move = self._make_done_internal_move(src=self.stock, dest=self.sub)
        move.move_line_ids.with_context(
            skip_location_consistency_check=True).write(
                {"location_dest_id": self.other.id})
        self.env.flush_all()
        rows = self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])
        self.assertTrue(rows)
        self.assertEqual(rows[0].ml_location_dest_id, self.other)

    def test_mismatch_cross_warehouse_flag_true(self):
        """Line lands in a different warehouse than the header - the case
        that actually desyncs FIFO valuation from physical stock."""
        move = self._make_done_internal_move(src=self.stock, dest=self.sub)
        move.move_line_ids.with_context(
            skip_location_consistency_check=True).write(
                {"location_dest_id": self.other.id})
        self.env.flush_all()
        row = self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])
        self.assertTrue(row.cross_warehouse)

    # ---- clearance tag ---------------------------------------------

    def _one_mismatch(self):
        move = self._make_done_internal_move(src=self.stock, dest=self.sub)
        move.move_line_ids.with_context(
            skip_location_consistency_check=True).write(
                {"location_dest_id": self.other.id})
        self.env.flush_all()
        return self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])

    def _reload(self, move):
        self.env.flush_all()
        self.env["buz.stock.location.mismatch"].invalidate_model()
        return self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])

    def test_mark_cleared_then_reopen(self):
        rows = self._one_mismatch()
        self.assertTrue(rows)
        self.assertFalse(any(rows.mapped("cleared")))
        rows.action_mark_cleared()
        after = self._reload(rows.move_id)
        self.assertTrue(all(after.mapped("cleared")))
        self.assertEqual(after[0].cleared_by, self.env.user)
        self.assertTrue(after[0].cleared_date)
        after.action_reopen()
        self.assertFalse(any(self._reload(rows.move_id).mapped("cleared")))

    def test_mark_cleared_idempotent(self):
        rows = self._one_mismatch()
        rows.action_mark_cleared()
        rows.action_mark_cleared()
        self.assertEqual(
            self.env["buz.stock.location.mismatch.clearance"].search_count(
                [("move_id", "=", rows.move_id.id)]), 1)

    def test_open_filter_excludes_cleared(self):
        rows = self._one_mismatch()
        rows.action_mark_cleared()
        self.env.flush_all()
        self.env["buz.stock.location.mismatch"].invalidate_model()
        still_open = self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", rows.move_id.id), ("cleared", "=", False)])
        self.assertFalse(still_open)

    # ---- unbuild: line destination is the operator's choice ----------

    def _production_loc(self):
        loc = self.env["stock.location"].search(
            [("usage", "=", "production")], limit=1)
        return loc or self.env["stock.location"].create({
            "name": "CONSISTENCY_PROD_LOC", "usage": "production",
            "location_id": self.env.ref(
                "stock.stock_location_locations_virtual").id})

    def _unbuild_move(self, header_dest):
        """A confirmed unbuild produce move (Production -> header_dest)."""
        fg = self.env["product.product"].create({
            "name": "UB_FG", "type": "product"})
        comp = self.env["product.product"].create({
            "name": "UB_COMP", "type": "product"})
        bom = self.env["mrp.bom"].create({
            "product_tmpl_id": fg.product_tmpl_id.id,
            "product_qty": 1.0, "type": "normal",
            "bom_line_ids": [(0, 0, {
                "product_id": comp.id, "product_qty": 1.0})],
        })
        ub = self.env["mrp.unbuild"].create({
            "product_id": fg.id, "product_qty": 1.0, "bom_id": bom.id,
            "location_id": self.stock.id,
            "location_dest_id": header_dest.id,
        })
        move = self.env["stock.move"].create({
            "name": "UB", "product_id": comp.id, "product_uom_qty": 1.0,
            "product_uom": comp.uom_id.id,
            "location_id": self._production_loc().id,
            "location_dest_id": header_dest.id,
            "unbuild_id": ub.id,
        })
        move._action_confirm()
        return move, comp

    def _unbuild_line(self, move, comp):
        """The move's operation line (auto-created once assigned), or a
        fresh one if none exists."""
        ml = move.move_line_ids[:1]
        if ml:
            return ml
        return self.env["stock.move.line"].with_context(
            skip_location_consistency_check=True).create({
                "move_id": move.id, "product_id": comp.id, "quantity": 1.0,
                "location_id": self._production_loc().id,
                "location_dest_id": move.location_dest_id.id,
            })

    def test_unbuild_produce_line_dest_realigns_header(self):
        if "mrp.unbuild" not in self.env:
            self.skipTest("mrp not installed")
        move, comp = self._unbuild_move(self.sub)
        self._unbuild_line(move, comp).write(
            {"location_dest_id": self.other.id})
        self.assertEqual(move.location_dest_id, self.other,
                         "unbuild move header should follow the line")

    def test_unbuild_move_lines_in_two_locations_blocked(self):
        if "mrp.unbuild" not in self.env:
            self.skipTest("mrp not installed")
        move, comp = self._unbuild_move(self.sub)
        self._unbuild_line(move, comp).write(
            {"location_dest_id": self.other.id})
        with self.assertRaises(ValidationError):
            self.env["stock.move.line"].create({
                "move_id": move.id, "product_id": comp.id, "quantity": 1.0,
                "location_id": self._production_loc().id,
                "location_dest_id": self.sub.id,
            })

    def test_unbuild_done_move_line_divergence_blocked(self):
        if "mrp.unbuild" not in self.env:
            self.skipTest("mrp not installed")
        move, comp = self._unbuild_move(self.sub)
        ml = self._unbuild_line(move, comp)
        move.write({"state": "done"})
        with self.assertRaises(ValidationError):
            ml.write({"location_dest_id": self.other.id})

    def test_mismatch_cross_warehouse_flag_false_same_wh_subtree(self):
        """Line in a sibling sub-location of the same warehouse - a header /
        line divergence, but no valuation impact."""
        sib = self.Location.create({
            "name": "CONSISTENCY_SIB", "location_id": self.stock.id})
        move = self._make_done_internal_move(src=self.stock, dest=self.sub)
        move.move_line_ids.with_context(
            skip_location_consistency_check=True).write(
                {"location_dest_id": sib.id})
        self.env.flush_all()
        row = self.env["buz.stock.location.mismatch"].search(
            [("move_id", "=", move.id)])
        self.assertTrue(row)
        self.assertFalse(row.cross_warehouse)
