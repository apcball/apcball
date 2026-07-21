from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBuzStockReservation(TransactionCase):
    """NOTE: reuses existing warehouse/products where possible because the
    DEV database rejects creates on stock.warehouse (orphaned columns)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.partner = cls.env["res.partner"].search(
            [("company_id", "in", (cls.company.id, False))], limit=1
        ) or cls.env["res.partner"].create({"name": "Test Reservation Partner"})
        cls.product = cls.env["product.product"].search(
            [("type", "=", "product"), ("company_id", "in", (cls.company.id, False))],
            limit=1,
        )
        if not cls.product:
            cls.product = cls.env["product.product"].create(
                {"name": "Test Reservation Product", "type": "product"}
            )
        cls.manager_group = cls.env.ref(
            "buz_stock_reservation.group_buz_reservation_manager"
        )
        cls.env.user.groups_id |= cls.manager_group

    def _create_reservation(self, qty=5.0):
        return self.env["buz.stock.reservation"].create(
            {
                "partner_id": self.partner.id,
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    fields.Command.create(
                        {"product_id": self.product.id, "reserved_qty": qty}
                    )
                ],
            }
        )

    def test_sequence_and_defaults(self):
        rsv = self._create_reservation()
        self.assertTrue(rsv.name.startswith("RSV-"))
        self.assertEqual(rsv.state, "draft")
        self.assertGreater(rsv.expiry_date, fields.Datetime.now())

    def test_reserve_and_totals(self):
        rsv = self._create_reservation(qty=5.0)
        rsv.action_reserve()
        self.assertEqual(rsv.state, "reserved")
        self.assertEqual(rsv.total_reserved_qty, 5.0)
        self.assertEqual(rsv.remaining_qty, 5.0)
        self.assertEqual(self.product.buz_reserved_qty, 5.0)

    def test_partial_and_full_release(self):
        rsv = self._create_reservation(qty=5.0)
        rsv.action_reserve()
        reason = self.env["buz.reservation.release.reason"].create(
            {"name": "Customer changed mind"}
        )
        wizard = (
            self.env["buz.reservation.release.wizard"]
            .with_context(default_reservation_id=rsv.id)
            .create({"release_reason_id": reason.id})
        )
        wizard.line_ids.release_qty = 2.0
        wizard.action_release()
        self.assertEqual(rsv.state, "partially_released")
        self.assertEqual(rsv.remaining_qty, 3.0)

        wizard2 = (
            self.env["buz.reservation.release.wizard"]
            .with_context(default_reservation_id=rsv.id)
            .create({"release_reason_id": reason.id})
        )
        wizard2.action_release()
        self.assertEqual(rsv.state, "released")
        self.assertEqual(rsv.remaining_qty, 0.0)

    def test_extend_expiry_revives_expired(self):
        rsv = self._create_reservation()
        rsv.action_reserve()
        rsv.expiry_date = fields.Datetime.now() - timedelta(days=1)
        self.env["buz.stock.reservation"]._cron_expire_reservations()
        self.assertEqual(rsv.state, "expired")
        wizard = (
            self.env["buz.reservation.extend.wizard"]
            .with_context(default_reservation_id=rsv.id)
            .create({"new_expiry_date": fields.Datetime.now() + timedelta(days=10)})
        )
        wizard.action_extend()
        self.assertEqual(rsv.state, "reserved")

    def test_over_reserve_blocked_for_non_manager(self):
        user = self.env["res.users"].search(
            [("id", "!=", self.env.user.id), ("share", "=", False)], limit=1
        )
        if not user:
            self.skipTest("No second internal user available.")
        user.groups_id -= self.manager_group
        user.groups_id |= self.env.ref(
            "buz_stock_reservation.group_buz_reservation_user"
        )
        available = self.product.with_context(warehouse=self.warehouse.id).free_qty
        rsv = self._create_reservation(qty=available + 1000.0)
        with self.assertRaises(UserError):
            rsv.with_user(user).action_reserve()

    def test_cancel_releases_availability(self):
        rsv = self._create_reservation(qty=4.0)
        rsv.action_reserve()
        rsv.action_cancel()
        self.assertEqual(rsv.state, "cancel")
        self.assertEqual(self.product.buz_reserved_qty, 0.0)

    def test_expiring_soon_flag(self):
        rsv = self._create_reservation()
        rsv.action_reserve()
        rsv.expiry_date = fields.Datetime.now() + timedelta(hours=12)
        self.assertTrue(rsv.expiring_soon)
        found = self.env["buz.stock.reservation"].search(
            [("expiring_soon", "=", True), ("id", "=", rsv.id)]
        )
        self.assertEqual(found, rsv)
