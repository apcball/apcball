from datetime import timedelta
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, TransactionCase, tagged


@tagged("reservation")
class TestStockReservation(TransactionCase):
    """Test the core stock reservation model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Environment
        cls.env = cls.env(
            context={
                "tracking_disable": True,
                "no_reset_password": True,
                "mail_create_nolog": True,
                "mail_create_nosubscribe": True,
                "mail_notrack": True,
            }
        )

        # Test users
        cls.user = cls.env["res.users"].create(
            {
                "name": "Test User",
                "login": "test_user_res",
                "email": "test@example.com",
                "groups_id": [
                    (4, cls.env.ref("stock_reservation_management.group_reservation_user").id)
                ],
            }
        )
        cls.manager = cls.env["res.users"].create(
            {
                "name": "Test Manager",
                "login": "test_manager_res",
                "email": "manager@example.com",
                "groups_id": [
                    (
                        4,
                        cls.env.ref("stock_reservation_management.group_reservation_manager").id,
                    )
                ],
            }
        )
        cls.admin = cls.env["res.users"].create(
            {
                "name": "Test Admin",
                "login": "test_admin_res",
                "email": "admin@example.com",
                "groups_id": [
                    (
                        4,
                        cls.env.ref("stock_reservation_management.group_reservation_admin").id,
                    )
                ],
            }
        )

        # Test partner
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "email": "customer@example.com",
                "is_vip_customer": True,
            }
        )
        cls.non_vip_partner = cls.env["res.partner"].create(
            {
                "name": "Regular Customer",
                "email": "regular@example.com",
            }
        )

        # Test warehouse
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        if not cls.warehouse:
            cls.warehouse = cls.env["stock.warehouse"].create(
                {
                    "name": "Test Warehouse",
                    "code": "TWH",
                }
            )

        # Test products
        cls.product_1 = cls.env["product.product"].create(
            {
                "name": "Test Product A",
                "type": "product",
                "default_code": "TEST-A",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
            }
        )
        cls.product_2 = cls.env["product.product"].create(
            {
                "name": "Test Product B",
                "type": "product",
                "default_code": "TEST-B",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
            }
        )
        cls.service_product = cls.env["product.product"].create(
            {
                "name": "Test Service",
                "type": "service",
                "default_code": "TEST-SVC",
                "uom_id": cls.env.ref("uom.product_uom_unit").id,
            }
        )

        # Create initial stock for products
        cls._create_stock_quant(cls, cls.product_1, 100.0)
        cls._create_stock_quant(cls, cls.product_2, 50.0)

        # Create a sale order
        cls.sale_order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "warehouse_id": cls.warehouse.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_1.id,
                            "product_uom_qty": 10.0,
                            "product_uom": cls.product_1.uom_id.id,
                            "price_unit": 100.0,
                            "name": cls.product_1.name,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_2.id,
                            "product_uom_qty": 5.0,
                            "product_uom": cls.product_2.uom_id.id,
                            "price_unit": 200.0,
                            "name": cls.product_2.name,
                        },
                    ),
                ],
            }
        )

    @classmethod
    def _create_stock_quant(cls, product, qty):
        """Helper to create stock quant for a product."""
        location = cls.env.ref("stock.stock_location_stock")
        cls.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": location.id,
                "quantity": qty,
                "user_id": cls.env.user.id,
            }
        )

    # ── Model Tests ────────────────────────────────────────────────

    def test_01_create_reservation(self):
        """Test basic reservation creation."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "priority": "normal",
                "warehouse_id": self.warehouse.id,
                "user_id": self.user.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )
        self.assertEqual(reservation.state, "draft")
        self.assertTrue(reservation.name.startswith("RES/"))
        self.assertEqual(reservation.line_count, 1)
        self.assertEqual(reservation.total_reserve_qty, 10.0)

    def test_02_reservation_sequence(self):
        """Test sequence generation."""
        r1 = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 5.0,
                        },
                    ),
                ],
            }
        )
        self.assertTrue(r1.name, "Sequence should generate a name")
        self.assertNotEqual(r1.name, "New")

    def test_03_vip_reservation_type(self):
        """Test VIP customer gets VIP reservation type."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,  # VIP customer
                "reservation_type": "vip",
                "priority": "vip",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 5.0,
                        },
                    ),
                ],
            }
        )
        self.assertEqual(reservation.reservation_type, "vip")
        self.assertEqual(reservation.priority, "vip")
        self.assertEqual(reservation.priority_level, 80)

    def test_04_expire_date_computation(self):
        """Test expiration date based on reservation type."""
        r_sale = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        expected_sale = fields.Date.context_today(self) + relativedelta(days=7)
        self.assertEqual(r_sale.expire_date, expected_sale)

        r_vip = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "vip",
                "warehouse_id": self.warehouse.id,
            }
        )
        expected_vip = fields.Date.context_today(self) + relativedelta(days=30)
        self.assertEqual(r_vip.expire_date, expected_vip)

    # ── State Flow Tests ───────────────────────────────────────────

    def test_10_reservation_flow(self):
        """Test complete reservation lifecycle."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )

        # Draft -> Reserved
        reservation.action_reserve()
        self.assertEqual(reservation.state, "reserved")

        # Reserved -> Allocated
        reservation.action_allocate()
        self.assertEqual(reservation.state, "allocated")

        # Allocated -> Delivered
        reservation.action_deliver()
        self.assertEqual(reservation.state, "delivered")

    def test_11_reservation_release(self):
        """Test releasing a reservation."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )
        reservation.action_reserve()
        reservation.action_release()
        self.assertEqual(reservation.state, "released")
        # Check released_qty updated
        self.assertEqual(reservation.line_ids[0].released_qty, 10.0)

    def test_12_reservation_expire(self):
        """Test expiration flow."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )
        reservation.action_reserve()
        reservation.action_expire()
        self.assertEqual(reservation.state, "expired")
        self.assertEqual(reservation.line_ids[0].released_qty, 10.0)

    def test_13_reservation_cancel_from_draft(self):
        """Test cancel from draft state."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        reservation.action_cancel()
        self.assertEqual(reservation.state, "cancel")

    # ── Approval Flow Tests ────────────────────────────────────────

    def test_20_approval_flow(self):
        """Test approval workflow."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )
        # Request approval
        reservation.action_request_approval()
        self.assertEqual(reservation.state, "waiting_approval")

        # Approve
        reservation.action_approve()
        self.assertEqual(reservation.state, "reserved")

    def test_21_approve_and_allocate(self):
        """Test approve and allocate in one step."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )
        reservation.action_request_approval()
        reservation.action_approve_and_allocate()
        self.assertEqual(reservation.state, "allocated")

    # ── Validation Tests ──────────────────────────────────────────

    def test_30_invalid_state_transitions(self):
        """Test that invalid state transitions are blocked."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        # Cannot allocate from draft
        with self.assertRaises(UserError):
            reservation.action_allocate()

        # Cannot deliver from draft
        with self.assertRaises(UserError):
            reservation.action_deliver()

    def test_31_delete_protection(self):
        """Test that non-draft reservations cannot be deleted."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        reservation.action_reserve()
        with self.assertRaises(UserError):
            reservation.unlink()

    def test_32_negative_quantity(self):
        """Test negative quantity validation."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["stock.reservation.line"].create(
                {
                    "reservation_id": reservation.id,
                    "product_id": self.product_1.id,
                    "product_uom_id": self.product_1.uom_id.id,
                    "reserve_qty": -10.0,
                }
            )

    def test_33_allocated_exceeds_reserved(self):
        """Test that allocated qty cannot exceed reserved qty."""
        line = self.env["stock.reservation.line"].create(
            {
                "reservation_id": self.env["stock.reservation"]
                .create(
                    {
                        "customer_id": self.partner.id,
                        "reservation_type": "sale",
                        "warehouse_id": self.warehouse.id,
                    }
                )
                .id,
                "product_id": self.product_1.id,
                "product_uom_id": self.product_1.uom_id.id,
                "reserve_qty": 5.0,
            }
        )
        with self.assertRaises(ValidationError):
            line.allocated_qty = 10.0

    # ── Product Extension Tests ────────────────────────────────────

    def test_40_product_computed_fields(self):
        """Test product reservation computed fields."""
        # Create a reservation
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 10.0,
                        },
                    ),
                ],
            }
        )
        reservation.action_reserve()

        # Check product fields after reservation
        self.product_1.invalidate_recordset(["reserved_qty", "available_after_reserve"])
        self.assertEqual(self.product_1.reserved_qty, 10.0)
        self.assertEqual(
            self.product_1.available_after_reserve,
            max(0.0, self.product_1.qty_available - 10.0),
        )

    def test_41_vip_reserved_qty(self):
        """Test VIP reserved quantity on product."""
        self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "vip",
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 20.0,
                        },
                    ),
                ],
            }
        )

        self.product_1.invalidate_recordset(["vip_reserved_qty"])
        self.assertEqual(self.product_1.vip_reserved_qty, 20.0)

    # ── Sale Order Integration Tests ───────────────────────────────

    def test_50_create_reservation_from_sale_order(self):
        """Test creating reservation from sale order."""
        action = self.sale_order.action_create_reservation()
        reservation = self.env["stock.reservation"].browse(action["res_id"])
        self.assertTrue(reservation)
        self.assertEqual(reservation.customer_id, self.partner)
        self.assertEqual(reservation.sale_order_id, self.sale_order)
        # Should auto-set VIP for VIP customer
        self.assertEqual(reservation.reservation_type, "vip")

    def test_51_sale_order_reservation_state(self):
        """Test computed reservation state on sale order."""
        # Initially no reservation
        self.assertEqual(self.sale_order.reservation_state, "no")
        self.assertEqual(self.sale_order.reservation_count, 0)

        # Create reservation
        self.sale_order.action_create_reservation()
        self.sale_order.invalidate_recordset(["reservation_count", "reservation_state"])
        self.assertEqual(self.sale_order.reservation_count, 1)

    # ── Cron / Expiration Tests ────────────────────────────────────

    def test_60_cron_expire_reservations(self):
        """Test cron expiration job."""
        # Create a reservation with past expire date
        past_date = fields.Date.context_today(self) - timedelta(days=10)
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "expire_date": past_date,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 5.0,
                        },
                    ),
                ],
            }
        )
        reservation.action_reserve()

        # Run cron
        count = self.env["stock.reservation"]._cron_expire_reservations()
        self.assertEqual(count, 1)
        self.assertEqual(reservation.state, "expired")

    def test_61_cron_auto_release(self):
        """Test auto-release of expired reservations."""
        past_date = fields.Date.context_today(self) - timedelta(days=10)
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
                "expire_date": past_date,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_1.id,
                            "product_uom_id": self.product_1.uom_id.id,
                            "reserve_qty": 5.0,
                        },
                    ),
                ],
            }
        )
        reservation.action_reserve()
        reservation.action_expire()
        self.assertEqual(reservation.state, "expired")

        # Auto-release
        count = self.env["stock.reservation"]._cron_auto_release_expired()
        self.assertEqual(count, 1)
        self.assertEqual(reservation.state, "released")

    # ── Line Computed Field Tests ──────────────────────────────────

    def test_70_available_qty_computation(self):
        """Test available_qty computation on reservation line."""
        line = self.env["stock.reservation.line"].create(
            {
                "reservation_id": self.env["stock.reservation"]
                .create(
                    {
                        "customer_id": self.partner.id,
                        "reservation_type": "sale",
                        "warehouse_id": self.warehouse.id,
                    }
                )
                .id,
                "product_id": self.product_1.id,
                "product_uom_id": self.product_1.uom_id.id,
                "reserve_qty": 10.0,
            }
        )
        self.assertGreater(line.available_qty, 0)

    # ── Security Tests ─────────────────────────────────────────────

    def test_80_security_basic_user(self):
        """Test basic user permissions."""
        User = self.env["res.users"].with_user(self.user)
        Reservation = User["stock.reservation"]

        # User can create
        res = Reservation.create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        self.assertTrue(res)

        # User can read own
        self.assertTrue(res.with_user(self.user).read(["name"]))

    def test_81_security_manager(self):
        """Test manager can approve."""
        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        # Request approval as user
        reservation.with_user(self.user).action_request_approval()
        self.assertEqual(reservation.state, "waiting_approval")

        # Approve as manager
        reservation.with_user(self.manager).action_approve()
        self.assertEqual(reservation.state, "reserved")

    # ── Multi-Company Tests ────────────────────────────────────────

    def test_90_multi_company(self):
        """Test multi-company compatibility."""
        company_2 = self.env["res.company"].create({"name": "Test Company 2"})
        warehouse_2 = self.env["stock.warehouse"].create(
            {
                "name": "Test WH 2",
                "code": "TWH2",
                "company_id": company_2.id,
            }
        )
        reservation = self.env["stock.reservation"].with_context(
            allowed_company_ids=company_2.ids
        ).create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": warehouse_2.id,
                "company_id": company_2.id,
            }
        )
        self.assertEqual(reservation.company_id, company_2)

    # ── Partner Extension Tests ────────────────────────────────────

    def test_95_vip_partner(self):
        """Test VIP partner fields."""
        self.assertTrue(self.partner.is_vip_customer)
        self.assertFalse(self.non_vip_partner.is_vip_customer)

    def test_96_partner_reservation_count(self):
        """Test partner reservation count."""
        self.env["stock.reservation"].create(
            {
                "customer_id": self.partner.id,
                "reservation_type": "sale",
                "warehouse_id": self.warehouse.id,
            }
        )
        self.partner.invalidate_recordset(["reservation_count"])
        self.assertEqual(self.partner.reservation_count, 1)
