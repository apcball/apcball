from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestStockFreeze(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

        # Some deployments enforce required partner fields on every create;
        # bypass that for the throw-away test users if the group exists.
        bypass_group = cls.env.ref(
            "buz_partner_required_fields.group_partner_required_fields_bypass",
            raise_if_not_found=False,
        )
        if bypass_group:
            cls.env.user.groups_id = [(4, bypass_group.id)]
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.supplier_location = cls.env.ref("stock.stock_location_suppliers")
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.scrap_location = cls.env["stock.location"].search(
            [("scrap_location", "=", True), ("company_id", "in", (False, cls.company.id))],
            limit=1,
        )

        cls.loc_a = cls.env["stock.location"].create(
            {"name": "FZ-A", "usage": "internal", "location_id": cls.stock_location.id}
        )
        cls.loc_b = cls.env["stock.location"].create(
            {"name": "FZ-B", "usage": "internal", "location_id": cls.stock_location.id}
        )

        cls.product = cls.env["product.product"].create(
            {"name": "FZ Product", "type": "product"}
        )
        cls.consu = cls.env["product.product"].create(
            {"name": "FZ Consu", "type": "consu"}
        )

        cls.override_user = cls.env["res.users"].create(
            {
                "name": "FZ Override",
                "login": "fz_override",
                # production profile: a plain stock user + the override group
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("stock.group_stock_user").id,
                            cls.env.ref(
                                "buz_stock_freeze.group_stock_freeze_override"
                            ).id,
                        ],
                    )
                ],
            }
        )
        # This deployment restricts stock.valuation.layer access; real stock
        # operators carry the FIFO-recalculation group. Mirror that so the
        # override path can complete the underlying move.
        fifo_group = cls.env.ref(
            "stock_fifo_by_warehouse_recal.group_fifo_recalculation",
            raise_if_not_found=False,
        )
        if fifo_group:
            cls.override_user.groups_id = [(4, fifo_group.id)]

        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "FZ Plain",
                "login": "fz_plain",
                "groups_id": [(6, 0, [cls.env.ref("stock.group_stock_manager").id])],
            }
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _seed(self, location, qty=100.0, product=None):
        product = product or self.product
        self.env["stock.quant"]._update_available_quantity(product, location, qty)

    def _make_period(self, **kw):
        vals = {
            "name": "Count",
            "company_id": self.company.id,
            "date_start": fields.Datetime.now() - timedelta(hours=1),
            "date_end": fields.Datetime.now() + timedelta(hours=4),
        }
        vals.update(kw)
        return self.env["stock.freeze.period"].create(vals)

    def _do_move(self, src, dest, qty=5.0, user=None, product=None):
        product = product or self.product
        env = self.env(user=user) if user else self.env
        move = env["stock.move"].create(
            {
                "name": product.name,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": qty,
                "location_id": src.id,
                "location_dest_id": dest.id,
            }
        )
        move._action_confirm()
        move._action_assign()
        if move.move_line_ids:
            move.move_line_ids.quantity = qty
        else:
            move.quantity = qty
        move.picked = True
        return move._action_done()

    # ------------------------------------------------------------------
    # Tests 1-4 : basic scope
    # ------------------------------------------------------------------
    def test_01_delivery_blocked(self):
        self._seed(self.stock_location)
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._do_move(self.stock_location, self.customer_location)

    def test_02_receipt_blocked(self):
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._do_move(self.supplier_location, self.stock_location)

    def test_03_internal_blocked(self):
        self._seed(self.loc_a)
        p = self._make_period(location_ids=[(6, 0, [self.stock_location.id])])
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._do_move(self.loc_a, self.loc_b)

    def test_04_sibling_allowed(self):
        self._seed(self.loc_b)
        p = self._make_period(location_ids=[(6, 0, [self.loc_a.id])])
        p.action_start_freeze()
        # WH/Stock/B -> Customers, only FZ-A frozen
        res = self._do_move(self.loc_b, self.customer_location)
        self.assertTrue(res)

    # ------------------------------------------------------------------
    # Tests 5-6 : inventory adjustment
    # ------------------------------------------------------------------
    def _apply_adjustment(self, location, new_qty):
        quant = (
            self.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": self.product.id,
                    "location_id": location.id,
                    "inventory_quantity": new_qty,
                }
            )
        )
        quant.with_context(
            inventory_mode=True, set_inventory_quantity_auto_apply=True
        ).action_apply_inventory()

    def test_05_inventory_adjustment_allowed(self):
        self._seed(self.stock_location, 10.0)
        p = self._make_period(
            warehouse_id=self.warehouse.id, allow_inventory_adjustment=True
        )
        p.action_start_freeze()
        self._apply_adjustment(self.stock_location, 25.0)
        self.assertEqual(
            self.env["stock.quant"]._get_available_quantity(
                self.product, self.stock_location
            ),
            25.0,
        )

    def test_06_inventory_adjustment_blocked(self):
        self._seed(self.stock_location, 10.0)
        p = self._make_period(
            warehouse_id=self.warehouse.id, allow_inventory_adjustment=False
        )
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._apply_adjustment(self.stock_location, 25.0)

    # ------------------------------------------------------------------
    # Tests 7-8 : override
    # ------------------------------------------------------------------
    def test_07_override_allowed(self):
        self._seed(self.stock_location)
        p = self._make_period(
            warehouse_id=self.warehouse.id, allow_manager_override=True
        )
        p.action_start_freeze()
        msg_count = len(p.message_ids)
        res = self._do_move(
            self.stock_location,
            self.customer_location,
            user=self.override_user,
        )
        self.assertTrue(res)
        self.assertGreater(len(p.message_ids), msg_count)

    def test_08_override_denied_when_flag_off(self):
        self._seed(self.stock_location)
        p = self._make_period(
            warehouse_id=self.warehouse.id, allow_manager_override=False
        )
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._do_move(
                self.stock_location,
                self.customer_location,
                user=self.override_user,
            )

    # ------------------------------------------------------------------
    # Tests 9-11 : company / time scope
    # ------------------------------------------------------------------
    def test_09_other_company_allowed(self):
        other_company = self.env["res.company"].create({"name": "FZ Co B"})
        wh_b = self.env["stock.warehouse"].search(
            [("company_id", "=", other_company.id)], limit=1
        )
        self.env["stock.quant"].with_context(
            allowed_company_ids=[self.company.id, other_company.id]
        )._update_available_quantity(self.product, wh_b.lot_stock_id, 50.0)
        p = self._make_period(
            warehouse_id=self.warehouse.id, company_id=self.company.id
        )
        p.action_start_freeze()
        move = (
            self.env["stock.move"]
            .with_company(other_company)
            .create(
                {
                    "name": self.product.name,
                    "product_id": self.product.id,
                    "product_uom": self.product.uom_id.id,
                    "product_uom_qty": 3.0,
                    "location_id": wh_b.lot_stock_id.id,
                    "location_dest_id": self.customer_location.id,
                    "company_id": other_company.id,
                }
            )
        )
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = 3.0
        move.picked = True
        self.assertTrue(move._action_done())

    def test_10_expired_period_allowed(self):
        self._seed(self.stock_location)
        p = self._make_period(
            warehouse_id=self.warehouse.id,
            date_start=fields.Datetime.now() - timedelta(hours=5),
            date_end=fields.Datetime.now() - timedelta(hours=1),
        )
        p.state = "active"
        self.assertTrue(self._do_move(self.stock_location, self.customer_location))

    def test_11_draft_before_start_allowed(self):
        self._seed(self.stock_location)
        self._make_period(
            warehouse_id=self.warehouse.id,
            date_start=fields.Datetime.now() + timedelta(hours=1),
            date_end=fields.Datetime.now() + timedelta(hours=5),
        )
        self.assertTrue(self._do_move(self.stock_location, self.customer_location))

    # ------------------------------------------------------------------
    # Test 12 : overlap
    # ------------------------------------------------------------------
    def test_12_overlap_parent_child(self):
        p1 = self._make_period(location_ids=[(6, 0, [self.stock_location.id])])
        p1.action_start_freeze()
        # A child-location period overlapping in time conflicts already at
        # creation (draft periods are checked against active ones).
        with self.assertRaises(ValidationError):
            self._make_period(location_ids=[(6, 0, [self.loc_a.id])])

    # ------------------------------------------------------------------
    # Tests 13-14 : manufacturing
    # ------------------------------------------------------------------
    def _build_mo(self):
        component = self.env["product.product"].create(
            {"name": "FZ Comp", "type": "product"}
        )
        finished = self.env["product.product"].create(
            {"name": "FZ Finished", "type": "product"}
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "type": "normal",
                "bom_line_ids": [(0, 0, {"product_id": component.id, "product_qty": 1.0})],
            }
        )
        self._seed(self.stock_location, 50.0, product=component)
        mo = self.env["mrp.production"].create(
            {
                "product_id": finished.id,
                "product_qty": 2.0,
                "bom_id": bom.id,
            }
        )
        mo.action_confirm()
        mo.action_assign()
        return mo

    def _mark_mo_done(self, mo):
        mo.qty_producing = mo.product_qty
        mo.move_raw_ids.picked = True
        mo.move_finished_ids.picked = True
        return mo.button_mark_done()

    def test_13_mrp_consume_blocked(self):
        mo = self._build_mo()
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._mark_mo_done(mo)

    def test_14_mrp_produce_blocked(self):
        # Freezing the stock location covers the finished-goods produce leg
        # (core routes both move_raw_ids and move_finished_ids through the same
        # stock.move._action_done boundary in mrp._post_inventory).
        mo = self._build_mo()
        p = self._make_period(location_ids=[(6, 0, [self.stock_location.id])])
        p.action_start_freeze()
        with self.assertRaises(UserError):
            self._mark_mo_done(mo)

    # ------------------------------------------------------------------
    # Test 15 : scrap
    # ------------------------------------------------------------------
    def test_15_scrap_blocked(self):
        self._seed(self.stock_location, 20.0)
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        scrap = self.env["stock.scrap"].create(
            {
                "product_id": self.product.id,
                "product_uom_id": self.product.uom_id.id,
                "scrap_qty": 5.0,
                "location_id": self.stock_location.id,
            }
        )
        with self.assertRaises(UserError):
            scrap.do_scrap()

    # ------------------------------------------------------------------
    # Test 16 : unbuild
    # ------------------------------------------------------------------
    def test_16_unbuild_blocked(self):
        component = self.env["product.product"].create(
            {"name": "FZ UB Comp", "type": "product"}
        )
        finished = self.env["product.product"].create(
            {"name": "FZ UB Finished", "type": "product"}
        )
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": finished.product_tmpl_id.id,
                "product_qty": 1.0,
                "type": "normal",
                "bom_line_ids": [(0, 0, {"product_id": component.id, "product_qty": 1.0})],
            }
        )
        self._seed(self.stock_location, 10.0, product=finished)
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        unbuild = self.env["mrp.unbuild"].create(
            {
                "product_id": finished.id,
                "bom_id": bom.id,
                "product_qty": 1.0,
                "product_uom_id": finished.uom_id.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.stock_location.id,
            }
        )
        with self.assertRaises(UserError):
            unbuild.action_unbuild()

    # ------------------------------------------------------------------
    # Extra : delete / edit restrictions
    # ------------------------------------------------------------------
    def test_17_delete_restricted(self):
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        with self.assertRaises(UserError):
            p.unlink()
        p.action_end_freeze()
        with self.assertRaises(UserError):
            p.unlink()

    def test_18_edit_locked_when_active(self):
        p = self._make_period(warehouse_id=self.warehouse.id)
        p.action_start_freeze()
        with self.assertRaises(UserError):
            p.date_start = fields.Datetime.now()

    def test_19_end_date_before_start_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_period(
                warehouse_id=self.warehouse.id,
                date_start=fields.Datetime.now(),
                date_end=fields.Datetime.now() - timedelta(hours=1),
            )
