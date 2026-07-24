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

    def _recommendation(self, plan, recommendation_type, warehouse, quantity):
        recommendation = self.env["mogen.sop.recommendation"].create(
            {
                "name": "S&OP supply source",
                "plan_id": plan.id,
                "recommendation_type": recommendation_type,
                "product_id": self.product.id,
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
