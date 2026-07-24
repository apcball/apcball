from datetime import timedelta

from odoo import Command, fields
from odoo.tests.common import TransactionCase


class TestSopSupplyPlan(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.second_warehouse = cls.env["stock.warehouse"].create(
            {"name": "S&OP Supply Source", "code": "SSS", "company_id": cls.company.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "S&OP Supply Product", "detailed_type": "product"}
        )
        cls.vendor = cls.env["res.partner"].create({"name": "S&OP Supply Vendor"})
        cls.manager = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "S&OP Supply Manager",
                "login": "sop_supply_manager_%s" % cls.env.cr.dbname,
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "groups_id": [Command.link(cls.env.ref("mogen_sop_core.group_sop_manager").id)],
            }
        )

    def _sop_plan(self):
        return self.env["mogen.sop.plan"].create(
            {
                "name": "S&OP Supply",
                "company_id": self.company.id,
                "warehouse_ids": [Command.set([self.warehouse.id, self.second_warehouse.id])],
                "date_start": fields.Date.today(),
                "date_end": fields.Date.today() + timedelta(days=30),
            }
        )

    def _recommendation(self, plan, recommendation_type, warehouse, quantity, product=None):
        recommendation = self.env["mogen.sop.recommendation"].create(
            {
                "name": "S&OP supply source",
                "plan_id": plan.id,
                "recommendation_type": recommendation_type,
                "product_id": (product or self.product).id,
                "warehouse_id": warehouse.id,
                "quantity": quantity,
                "required_date": fields.Date.today() + timedelta(days=10),
            }
        )
        recommendation.with_user(self.manager).action_approve()
        return recommendation

    def test_purchase_plan_selects_supplier_rounds_moq_and_creates_draft_po(self):
        plan = self._sop_plan()
        supplierinfo = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "min_qty": 10.0,
                "price": 8.0,
                "delay": 3,
            }
        )
        self._recommendation(plan, "purchase", self.warehouse, 7.0)
        purchase_plan = self.env["mogen.sop.purchase.plan"].create(
            {
                "sop_plan_id": plan.id,
                "company_id": self.company.id,
                "warehouse_id": self.warehouse.id,
                "date_start": plan.date_start,
                "date_end": plan.date_end,
            }
        )

        purchase_plan.action_calculate_purchase()

        line = purchase_plan.line_ids
        self.assertEqual(line.supplierinfo_id, supplierinfo)
        self.assertEqual(line.proposed_qty, 10.0)
        self.assertEqual(line.unit_price, 8.0)
        purchase_plan.action_create_draft_pos()
        self.assertEqual(line.generated_po_id.state, "draft")
        self.assertEqual(line.generated_po_line_id.product_qty, 10.0)
        purchase_plan.action_create_draft_pos()
        self.assertEqual(len(purchase_plan.line_ids.mapped("generated_po_id")), 1)

    def test_purchase_plan_uses_applicable_price_break_and_dates(self):
        plan = self._sop_plan()
        standard_price = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "min_qty": 0.0,
                "price": 10.0,
                "delay": 2,
            }
        )
        price_break = self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "min_qty": 10.0,
                "price": 8.0,
                "delay": 4,
            }
        )
        recommendation = self._recommendation(plan, "purchase", self.warehouse, 12.0)
        purchase_plan = self.env["mogen.sop.purchase.plan"].create(
            {
                "sop_plan_id": plan.id,
                "company_id": self.company.id,
                "warehouse_id": self.warehouse.id,
                "date_start": plan.date_start,
                "date_end": plan.date_end,
            }
        )

        purchase_plan.action_calculate_purchase()

        line = purchase_plan.line_ids
        self.assertNotEqual(standard_price, price_break)
        self.assertEqual(line.supplierinfo_id, price_break)
        self.assertEqual(line.unit_price, 8.0)
        self.assertEqual(line.supplier_lead_time, 4)
        self.assertEqual(line.planned_order_date, recommendation.required_date - timedelta(days=4))
        self.assertEqual(line.expected_arrival_date, recommendation.required_date)

    def test_purchase_plan_groups_compatible_lines_in_one_draft_po(self):
        plan = self._sop_plan()
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "min_qty": 1.0,
                "price": 8.0,
            }
        )
        self._recommendation(plan, "purchase", self.warehouse, 2.0)
        self._recommendation(plan, "purchase", self.warehouse, 3.0)
        purchase_plan = self.env["mogen.sop.purchase.plan"].create(
            {
                "sop_plan_id": plan.id,
                "company_id": self.company.id,
                "warehouse_id": self.warehouse.id,
                "date_start": plan.date_start,
                "date_end": plan.date_end,
            }
        )

        purchase_plan.action_calculate_purchase()
        purchase_plan.action_create_draft_pos()

        orders = purchase_plan.line_ids.mapped("generated_po_id")
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(orders.order_line), 2)
        self.assertEqual(orders.state, "draft")
        self.assertEqual(orders.sop_purchase_plan_id, purchase_plan)
        self.assertEqual(
            purchase_plan.line_ids.mapped("generated_po_line_id.sop_purchase_line_id"),
            purchase_plan.line_ids,
        )
        purchase_plan.action_create_draft_pos()
        self.assertEqual(len(purchase_plan.line_ids.mapped("generated_po_id")), 1)

    def test_purchase_plan_converts_supplier_currency_to_plan_currency(self):
        foreign_currency = self.env["res.currency"].create(
            {"name": "SOP", "symbol": "SOP", "rounding": 0.01}
        )
        self.env["res.currency.rate"].create(
            {
                "name": fields.Date.today(),
                "currency_id": foreign_currency.id,
                "rate": 2.0,
                "company_id": self.company.id,
            }
        )
        product = self.env["product.product"].create(
            {"name": "S&OP Foreign Currency Product", "detailed_type": "product"}
        )
        plan = self._sop_plan()
        self.env["product.supplierinfo"].create(
            {
                "partner_id": self.vendor.id,
                "product_tmpl_id": product.product_tmpl_id.id,
                "min_qty": 1.0,
                "price": 20.0,
                "currency_id": foreign_currency.id,
            }
        )
        self._recommendation(plan, "purchase", self.warehouse, 2.0, product=product)
        purchase_plan = self.env["mogen.sop.purchase.plan"].create(
            {
                "sop_plan_id": plan.id,
                "company_id": self.company.id,
                "warehouse_id": self.warehouse.id,
                "date_start": plan.date_start,
                "date_end": plan.date_end,
            }
        )

        purchase_plan.action_calculate_purchase()

        self.assertEqual(
            purchase_plan.line_ids.unit_price,
            foreign_currency._convert(
                20.0,
                purchase_plan.currency_id,
                self.company,
                fields.Date.today(),
            ),
        )

    def test_transfer_plan_protects_source_safety_and_creates_draft_picking(self):
        plan = self._sop_plan()
        self._recommendation(plan, "transfer", self.warehouse, 8.0)
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.second_warehouse.lot_stock_id, 15.0
        )
        self.env["stock.warehouse.orderpoint"].create(
            {
                "warehouse_id": self.second_warehouse.id,
                "location_id": self.second_warehouse.lot_stock_id.id,
                "product_id": self.product.id,
                "product_min_qty": 5.0,
            }
        )
        transfer_plan = self.env["mogen.sop.transfer.plan"].create(
            {
                "sop_plan_id": plan.id,
                "company_id": self.company.id,
                "destination_warehouse_id": self.warehouse.id,
            }
        )

        transfer_plan.action_calculate_transfers()

        line = transfer_plan.line_ids
        self.assertEqual(line.source_warehouse_id, self.second_warehouse)
        self.assertEqual(line.proposed_qty, 8.0)
        transfer_plan.action_create_draft_pickings()
        self.assertEqual(line.generated_picking_id.state, "draft")
        self.assertEqual(line.generated_picking_id.location_id, self.second_warehouse.lot_stock_id)
        self.assertEqual(line.generated_picking_id.location_dest_id, self.warehouse.lot_stock_id)

        transfer_plan.action_create_draft_pickings()
        self.assertEqual(len(transfer_plan.line_ids.mapped("generated_picking_id")), 1)
        move = line.generated_picking_id.move_ids
        self.assertEqual(move.sop_transfer_plan_id, transfer_plan)
        self.assertEqual(move.sop_transfer_line_id, line)

    def test_transfer_plan_does_not_allocate_source_surplus_twice(self):
        plan = self._sop_plan()
        self._recommendation(plan, "transfer", self.warehouse, 8.0)
        self._recommendation(plan, "transfer", self.warehouse, 8.0)
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.second_warehouse.lot_stock_id, 15.0
        )
        self.env["stock.warehouse.orderpoint"].create(
            {
                "warehouse_id": self.second_warehouse.id,
                "location_id": self.second_warehouse.lot_stock_id.id,
                "product_id": self.product.id,
                "product_min_qty": 5.0,
            }
        )
        transfer_plan = self.env["mogen.sop.transfer.plan"].create(
            {
                "sop_plan_id": plan.id,
                "company_id": self.company.id,
                "destination_warehouse_id": self.warehouse.id,
            }
        )

        transfer_plan.action_calculate_transfers()

        self.assertEqual(sum(transfer_plan.line_ids.mapped("proposed_qty")), 10.0)
        self.assertGreaterEqual(
            15.0 - sum(transfer_plan.line_ids.mapped("proposed_qty")), 5.0
        )
