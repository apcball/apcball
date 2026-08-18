# Copyright 2020 Tecnativa - Carlos Dauden
# Copyright 2020 Tecnativa - Sergio Teruel
# Copyright 2025 Tecnativa - Víctor Martínez
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestAgreementRebateBase(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for model_name in ("sale.order", "sale.order.line", "stock.picking", "stock.move"):
            if model_name not in cls.env:
                cls.skipTest("Model %s not available; sale_stock is not installed" % model_name)
        cls.env.user.groups_id += cls.env.ref(
            "agreement_rebate.group_rebate_approver"
        )
        cls.Partner = cls.env["res.partner"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.Product = cls.env["product.product"]
        cls.ProductCategory = cls.env["product.category"]
        cls.AccountInvoice = cls.env["account.move"]
        cls.AccountInvoiceLine = cls.env["account.move.line"]
        cls.AccountJournal = cls.env["account.journal"]
        cls.Agreement = cls.env["agreement"]
        cls.AgreementType = cls.env["agreement.type"]
        cls.ProductAttribute = cls.env["product.attribute"]
        cls.ProductAttributeValue = cls.env["product.attribute.value"]
        cls.ProductTmplAttributeValue = cls.env["product.template.attribute.value"]
        cls.AgreementSettlement = cls.env["agreement.rebate.settlement"]
        cls.AgreementSettlementCreateWiz = cls.env["agreement.settlement.create.wiz"]
        cls.category_all = cls.env.ref("product.product_category_all")
        cls.categ_1 = cls.ProductCategory.create(
            {"parent_id": cls.category_all.id, "name": "Category 1"}
        )
        cls.categ_2 = cls.ProductCategory.create(
            {"parent_id": cls.category_all.id, "name": "Category 2"}
        )
        cls.product_1 = cls._create_product(
            name="Product test 1",
            categ_id=cls.categ_1.id,
            lst_price=1000.00,
        )
        cls.product_2 = cls._create_product(
            name="Product test 2",
            categ_id=cls.categ_2.id,
            lst_price=2000.00,
        )
        # Create a product with variants
        cls.product_attribute = cls.ProductAttribute.create(
            {"name": "Test", "create_variant": "always"}
        )
        cls.product_attribute_value_test_1 = cls.ProductAttributeValue.create(
            {"name": "Test v1", "attribute_id": cls.product_attribute.id}
        )
        cls.product_attribute_value_test_2 = cls.ProductAttributeValue.create(
            {"name": "Test v2", "attribute_id": cls.product_attribute.id}
        )
        cls.product_template = cls.ProductTemplate.create(
            {
                "name": "Product template with variant test",
                "type": "consu",
                "list_price": 100.0,
                "attribute_line_ids": [
                    Command.create(
                        {
                            "attribute_id": cls.product_attribute.id,
                            "value_ids": [
                                Command.link(cls.product_attribute_value_test_1.id),
                                Command.link(cls.product_attribute_value_test_2.id),
                            ],
                        },
                    ),
                ],
            }
        )
        cls.partner_1 = cls.partner_a
        cls.partner_1.ref = "TST-001"
        cls.partner_2 = cls.partner_b
        cls.partner_2.ref = "TST-002"
        cls.partner_3 = cls.env["res.partner"].create(
            {
                "name": "Test Customer 3",
                "property_account_receivable_id": cls.partner_a.property_account_receivable_id.id,
                "property_account_payable_id": cls.partner_a.property_account_payable_id.id,
            }
        )
        cls.partner_4 = cls.env["res.partner"].create(
            {
                "name": "Test Customer 4",
                "property_account_receivable_id": cls.partner_a.property_account_receivable_id.id,
                "property_account_payable_id": cls.partner_a.property_account_payable_id.id,
            }
        )
        cls.partner_5 = cls.env["res.partner"].create(
            {
                "name": "Test Customer 5",
                "property_account_receivable_id": cls.partner_a.property_account_receivable_id.id,
                "property_account_payable_id": cls.partner_a.property_account_payable_id.id,
            }
        )
        cls.invoice_partner_1 = cls.create_invoice(cls.partner_1)
        cls.invoice_partner_2 = cls.create_invoice(cls.partner_2)
        cls.agreement_type = cls.AgreementType.create(
            {"name": "Rebate", "domain": "sale", "is_rebate": True}
        )
        # Product to use when we create invoices from settlements
        cls.product_rappel = cls._create_product(
            name="Rappel sales",
            categ_id=cls.categ_1.id,
            lst_price=1.0,
        )
        cls.sale_journal = cls.company_data["default_journal_sale"]

    @classmethod
    def _product_price(cls, product):
        variants = cls.product_template.product_variant_ids
        if product == variants[0]:
            return 300.0
        if product == variants[1]:
            return 500.0
        return product.list_price

    @classmethod
    def _create_delivered_sale(cls, partner, items, do_date="2022-01-15", deliver=True):
        """Create a sale order with the given items.

        items: list of (product, qty, price).
        Returns the confirmed sale order. When deliver is True the delivery
        order is validated and date_done is set.
        """
        order = cls.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "date_order": "2022-01-01",
            }
        )
        for product, qty, price in items:
            cls.env["sale.order.line"].create(
                {
                    "order_id": order.id,
                    "name": product.display_name,
                    "product_id": product.id,
                    "product_uom_qty": qty,
                    "price_unit": price,
                }
            )
        order.action_confirm()
        if deliver:
            for picking in order.picking_ids:
                picking.action_assign()
                for move in picking.move_ids:
                    move.quantity = move.product_uom_qty
                picking.button_validate()
                picking.date_done = fields.Datetime.to_datetime(do_date)
        return order

    @classmethod
    def _create_sold_invoice(cls, partner, items, do_date="2022-01-15", deliver=True, post=True):
        """Create and post a customer invoice linked to delivered sales orders."""
        order = cls._create_delivered_sale(
            partner, items, do_date=do_date, deliver=deliver
        )
        invoice = order._create_invoices()
        if post:
            invoice.action_post()
        return invoice

    # Create some invoices for partner, linked to delivered sale orders
    @classmethod
    def create_invoice(cls, partner, do_date="2022-01-15"):
        products = (
            cls.product_template.product_variant_ids + cls.product_1 + cls.product_2
        )
        items = [(product, 1, cls._product_price(product)) for product in products]
        return cls._create_sold_invoice(partner, items, do_date=do_date)

    @classmethod
    def _create_direct_invoice(cls, partner, product, price, date="2022-01-10", post=True):
        """Posted/ draft customer invoice without sale order lines."""
        invoice = cls.env["account.move"].create(
            {
                "partner_id": partner.id,
                "move_type": "out_invoice",
                "invoice_date": date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": product.name,
                            "product_id": product.id,
                            "quantity": 1,
                            "price_unit": price,
                        }
                    )
                ],
            }
        )
        if post:
            invoice.action_post()
        return invoice

    @classmethod
    def _create_multi_do_invoice(cls, partner, orders, product, price):
        """Posted invoice whose single line links the sale lines of several orders."""
        sale_lines = cls.env["sale.order.line"]
        for order in orders:
            sale_lines |= order.order_line
        invoice = cls.env["account.move"].create(
            {
                "partner_id": partner.id,
                "move_type": "out_invoice",
                "invoice_date": "2022-01-10",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": sale_lines[0].name,
                            "product_id": product.id,
                            "quantity": sum(sale_lines.mapped("product_uom_qty")),
                            "price_unit": price,
                            "sale_line_ids": [Command.set(sale_lines.ids)],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    @classmethod
    def _create_refund(cls, invoice, invoice_lines=False, post=True):
        """Create an out_refund directly linked to given invoice lines."""
        if not invoice_lines:
            invoice_lines = invoice.invoice_line_ids.filtered(
                lambda line: line.display_type == "product"
            )
        lines_cmd = []
        for line in invoice_lines:
            lines_cmd.append(
                Command.create(
                    {
                        "name": line.name,
                        "product_id": line.product_id.id,
                        "quantity": line.quantity,
                        "price_unit": line.price_unit,
                        "origin_line_id": line.id,
                        "account_id": line.account_id.id,
                    }
                )
            )
        refund = cls.env["account.move"].create(
            {
                "partner_id": invoice.partner_id.id,
                "move_type": "out_refund",
                "invoice_date": "2022-06-01",
                "invoice_line_ids": lines_cmd,
            }
        )
        if post:
            refund.action_post()
        return refund

    def _create_return(self, picking):
        """Create and validate a return for a delivered picking."""
        wizard = self.env["stock.return.picking"].with_context(
            active_id=picking.id,
            active_model="stock.picking",
        ).create({})
        return_picking_id, _return_type_id = wizard._create_returns()
        return_picking = self.env["stock.picking"].browse(return_picking_id)
        for move in return_picking.move_ids:
            move.quantity = move.product_uom_qty
        return_picking.button_validate()
        return return_picking

    # Create Agreements rebates for customers for all available types
    def create_agreements_rebate(self, rebate_type, partner):
        return self.Agreement.create(
            {
                "domain": "sale",
                "start_date": "2022-01-01",
                "rebate_type": rebate_type,
                "name": f"A discount {rebate_type} for all lines for {partner.name}",
                "code": f"R-{rebate_type}-{partner.ref}",
                "partner_id": partner.id,
                "agreement_type_id": self.agreement_type.id,
                "rebate_discount": 10,
                "rebate_line_ids": [
                    Command.create(
                        {
                            "rebate_target": "product",
                            "rebate_product_ids": [Command.set(self.product_1.ids)],
                            "rebate_discount": 20,
                        },
                    ),
                    Command.create(
                        {
                            "rebate_target": "product",
                            "rebate_product_ids": [
                                Command.set(
                                    self.product_template.product_variant_ids[0].ids
                                )
                            ],
                            "rebate_discount": 30,
                        },
                    ),
                    Command.create(
                        {
                            "rebate_target": "product_tmpl",
                            "rebate_product_tmpl_ids": [
                                Command.set(self.product_2.product_tmpl_id.ids)
                            ],
                            "rebate_discount": 40,
                        },
                    ),
                    Command.create(
                        {
                            "rebate_target": "category",
                            "rebate_category_ids": [Command.set(self.category_all.ids)],
                            "rebate_discount": 40,
                        },
                    ),
                ],
                "rebate_section_ids": [
                    Command.create(
                        {
                            "amount_from": 0.00,
                            "amount_to": 100.00,
                            "rebate_discount": 10,
                        },
                    ),
                    Command.create(
                        {
                            "amount_from": 100.01,
                            "amount_to": 300.00,
                            "rebate_discount": 20,
                        },
                    ),
                    Command.create(
                        {
                            "amount_from": 300.01,
                            "amount_to": 6000.00,
                            "rebate_discount": 30,
                        },
                    ),
                ],
            }
        )

    def _approve_agreement(self, agreement):
        agreement.action_submit_rebate()
        agreement.action_review_rebate()
        agreement.action_approve_rebate()
        return agreement

    def _global_agreement(self, partner, discount=10.0):
        agreement = self.Agreement.create(
            {
                "domain": "sale",
                "start_date": "2022-01-01",
                "rebate_type": "global",
                "rebate_discount": discount,
                "name": f"A global for {partner.name}",
                "code": f"G-{partner.id}",
                "partner_id": partner.id,
                "agreement_type_id": self.agreement_type.id,
            }
        )
        return self._approve_agreement(agreement)

    def _section_total_agreement(self, partner, sections):
        agreement = self.Agreement.create(
            {
                "domain": "sale",
                "start_date": "2022-01-01",
                "rebate_type": "section_total",
                "name": f"A section total for {partner.name}",
                "code": f"ST-{partner.id}",
                "partner_id": partner.id,
                "agreement_type_id": self.agreement_type.id,
                "rebate_section_ids": [Command.create(section) for section in sections],
            }
        )
        return self._approve_agreement(agreement)

    def _run_settlement_for_partner(
        self, partner, agreement, date_from="2022-01-01", date_to="2022-12-31"
    ):
        wizard = self.AgreementSettlementCreateWiz.create(
            {
                "date_from": date_from,
                "date_to": date_to,
                "agreement_ids": [Command.set(agreement.ids)],
            }
        )
        action = wizard.action_create_settlement()
        return self.get_settlements_from_action(action)

    def get_settlements_from_action(self, action):
        if action.get("res_id", False):
            return self.AgreementSettlement.browse(action["res_id"])
        else:
            return self.AgreementSettlement.search(action["domain"])

    def create_settlement_wizard(self, agreements=False):
        vals = {
            "date_from": "2022-01-01",
            "date_to": "2022-12-31",
        }
        if agreements:
            vals["agreement_ids"] = [Command.set(agreements.ids)]
        return self.AgreementSettlementCreateWiz.create(vals)


@tagged("-at_install", "post_install")
class TestAgreementRebate(TestAgreementRebateBase):
    def test_create_settlement_wo_filters_global(self):
        # Invoice Lines:
        # Product template variants: 300, 500
        # Product 1: 1000
        # Product 2: 2000
        # Total by invoice: 3800 amount invoiced

        # Global rebate without filters
        agreement_global = self.create_agreements_rebate("global", self.partner_1)
        agreement_global.rebate_line_ids = False
        agreement_global = self._approve_agreement(agreement_global)
        settlement_wiz = self.create_settlement_wizard(agreement_global)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 3800)
        self.assertEqual(settlements.amount_rebate, 380)

    def test_create_settlement_wo_filters_line(self):
        # Line rebate without filters
        agreement = self.create_agreements_rebate("line", self.partner_1)
        agreement.rebate_line_ids = False
        agreement = self._approve_agreement(agreement)
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 0)

    def test_create_settlement_wo_filters_section_total(self):
        # section_total rebate without filters
        agreement = self.create_agreements_rebate("section_total", self.partner_1)
        agreement.rebate_line_ids = False
        agreement = self._approve_agreement(agreement)
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 3800)
        self.assertEqual(settlements.amount_rebate, 1140)

    def test_create_settlement_wo_filters_section_prorated(self):
        # section_prorated rebate without filters
        agreement = self.create_agreements_rebate("section_prorated", self.partner_1)
        agreement.rebate_line_ids = False
        agreement = self._approve_agreement(agreement)
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 3800)
        self.assertAlmostEqual(settlements.amount_rebate, 1120.00, 2)

    def _create_agreement_product_filter(self, agreement_type):
        agreement = self.create_agreements_rebate(agreement_type, self.partner_1)
        agreement.rebate_line_ids = [
            Command.clear(),
            Command.create(
                {
                    "rebate_target": "product",
                    "rebate_product_ids": [Command.set(self.product_1.ids)],
                    "rebate_discount": 20,
                },
            ),
        ]
        return self._approve_agreement(agreement)

    def test_create_settlement_products_filters_global(self):
        # Invoice Lines:
        # Product template variants: 300, 500
        # Product 1: 1000
        # Product 2: 2000
        # Total by invoice: 3800 amount invoiced
        agreement = self._create_agreement_product_filter("global")
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 1000)
        self.assertEqual(settlements.amount_rebate, 100)

    def test_create_settlement_products_filters_line(self):
        agreement = self._create_agreement_product_filter("line")
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 1000)
        self.assertEqual(settlements.amount_rebate, 200)

    def test_create_settlement_products_filters_section_total(self):
        agreement = self._create_agreement_product_filter("section_total")
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 1000)
        self.assertEqual(settlements.amount_rebate, 300)

    def test_create_settlement_products_filters_section_prorated(self):
        agreement = self._create_agreement_product_filter("section_prorated")
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 1000)
        self.assertAlmostEqual(settlements.amount_rebate, 280, 2)

    def _create_invoice_wizard(self):
        wiz_create_invoice_form = Form(self.env["agreement.invoice.create.wiz"])
        wiz_create_invoice_form.date_from = "2022-01-01"
        wiz_create_invoice_form.date_to = "2022-12-31"
        wiz_create_invoice_form.invoice_type = "out_invoice"
        wiz_create_invoice_form.journal_id = self.sale_journal
        wiz_create_invoice_form.product_id = self.product_rappel
        wiz_create_invoice_form.agreement_type_ids.add(self.agreement_type)
        return wiz_create_invoice_form.save()

    @mute_logger("odoo.models.unlink")
    def test_invoice_agreements(self):
        # Create some rebate settlements
        agreement = self._create_agreement_product_filter("section_total")
        settlement_wiz = self.create_settlement_wizard(agreement)
        settlements = self.get_settlements_from_action(
            settlement_wiz.action_create_settlement()
        )
        wiz_create_invoice = self._create_invoice_wizard()
        wiz_create_invoice.agreement_ids = [Command.set(agreement.ids)]
        wiz_create_invoice.settlements_ids = [Command.set(settlements.ids)]
        action = wiz_create_invoice.action_create_invoice()
        invoices = self.env["account.move"].search(action["domain"])
        self.assertTrue(invoices)
        # Force invoice to partner
        invoices.unlink()
        wiz_create_invoice.invoice_partner_id = self.partner_2
        action = wiz_create_invoice.action_create_invoice()
        invoices = self.env["account.move"].search(action["domain"])
        self.assertEqual(invoices.partner_id, self.partner_2)
        self.assertEqual(
            invoices.invoice_line_ids.name,
            f"{self.product_rappel.name} - Period: 01/01/2022 - 12/31/2022",
        )

    def test_rebate_approval_workflow(self):
        agreement = self.Agreement.create({
            "domain": "sale",
            "name": "Approval workflow",
            "code": "APPROVAL-001",
            "partner_id": self.partner_1.id,
            "agreement_type_id": self.agreement_type.id,
            "rebate_type": "global",
            "rebate_discount": 3.0,
        })
        self.assertEqual(agreement.rebate_approval_state, "draft")
        agreement.action_submit_rebate()
        self.assertEqual(agreement.rebate_approval_state, "submitted")
        agreement.action_review_rebate()
        self.assertEqual(agreement.rebate_approval_state, "reviewed")
        agreement.action_approve_rebate()
        self.assertEqual(agreement.rebate_approval_state, "approved")
        self.assertEqual(agreement.rebate_approver_id, self.env.user)

    def test_section_total_supports_open_ended_upper_bound(self):
        agreement = self.Agreement.create({
            "domain": "sale",
            "name": "Open ended section",
            "code": "SECTION-001",
            "partner_id": self.partner_1.id,
            "agreement_type_id": self.agreement_type.id,
            "rebate_type": "section_total",
            "rebate_section_ids": [
                (0, 0, {"amount_from": 0.0, "amount_to": 100000.0, "rebate_discount": 1.0}),
                (0, 0, {"amount_from": 100000.0, "amount_to": 0.0, "rebate_discount": 3.0}),
            ],
        })
        wizard = self.AgreementSettlementCreateWiz.new({"date_to": "2022-12-31"})
        section = wizard._get_matching_section(agreement, 150000.0)
        self.assertEqual(section.rebate_discount, 3.0)

    def test_settlement_excludes_already_settled_invoice_lines(self):
        agreement = self.create_agreements_rebate("global", self.partner_1)
        invoice_line = self.invoice_partner_1.invoice_line_ids[:1]
        self.AgreementSettlement.create({
            "date": "2022-01-31",
            "date_from": "2022-01-01",
            "date_to": "2022-01-31",
            "partner_id": self.partner_1.id,
            "line_ids": [
                Command.create({
                    "agreement_id": agreement.id,
                    "partner_id": self.partner_1.id,
                    "source_invoice_line_ids": [Command.set(invoice_line.ids)],
                })
            ],
        })
        wizard = self.AgreementSettlementCreateWiz.new({
            "date_from": "2022-01-01",
            "date_to": "2022-01-31",
        })
        self.assertIn(
            invoice_line.id,
            wizard._get_settled_invoice_line_ids(),
        )


@tagged("-at_install", "post_install")
class TestAgreementRebateSales(TestAgreementRebateBase):
    """Delivery based sale settlement rules."""

    def test_draft_invoice_not_counted(self):
        partner = self.partner_3
        self._create_sold_invoice(
            partner, [(self.product_1, 1, 1000.0)], post=False
        )
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_posted_invoice_without_sale_line_not_counted(self):
        partner = self.partner_3
        self._create_direct_invoice(partner, self.product_1, 1000.0)
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_posted_invoice_without_delivery_not_counted(self):
        partner = self.partner_3
        self._create_sold_invoice(
            partner, [(self.product_1, 1, 1000.0)], deliver=False
        )
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_waiting_delivery_not_counted(self):
        partner = self.partner_3
        order = self._create_delivered_sale(
            partner, [(self.product_1, 1, 1000.0)], deliver=False
        )
        invoice = order._create_invoices()
        invoice.action_post()
        # picking is assigned but not done -> not eligible yet
        pickings = order.picking_ids
        self.assertTrue(pickings)
        self.assertNotEqual(pickings.state, "done")
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_cancelled_delivery_not_counted(self):
        partner = self.partner_3
        self._create_sold_invoice(partner, [(self.product_1, 1, 1000.0)])
        cancelled_order = self._create_delivered_sale(
            partner, [(self.product_2, 1, 2000.0)], deliver=False
        )
        cancelled_order.picking_ids.action_cancel()
        cancelled_invoice = cancelled_order._create_invoices()
        cancelled_invoice.action_post()
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 1000)
        self.assertEqual(settlements.amount_rebate, 100)

    def test_multiple_do_wait_all_done(self):
        partner = self.partner_3
        order_1 = self._create_delivered_sale(partner, [(self.product_1, 1, 500.0)])
        order_2 = self._create_delivered_sale(
            partner, [(self.product_2, 1, 1500.0)], deliver=False
        )
        self._create_multi_do_invoice(
            partner, [order_1, order_2], self.product_1, 2000.0
        )
        agreement = self._global_agreement(partner)
        # One delivery still open -> not eligible yet
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)
        # Complete the last delivery order
        for picking in order_2.picking_ids:
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            picking.button_validate()
            picking.date_done = fields.Datetime.to_datetime("2022-03-10")
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 4000)
        self.assertEqual(settlements.amount_rebate, 400)

    def test_ipv_use_last_delivery_date_for_period(self):
        partner = self.partner_3
        order_1 = self._create_delivered_sale(
            partner, [(self.product_1, 1, 500.0)], do_date="2022-01-15"
        )
        order_2 = self._create_delivered_sale(
            partner, [(self.product_2, 1, 1500.0)], do_date="2022-03-10"
        )
        self._create_multi_do_invoice(
            partner, [order_1, order_2], self.product_1, 2000.0
        )
        agreement = self._global_agreement(partner)
        # Last delivery (2022-03-10) is outside the period -> excluded
        settlements = self._run_settlement_for_partner(
            partner, agreement, date_from="2022-01-01", date_to="2022-02-28"
        )
        self.assertEqual(len(settlements), 0)
        # Last delivery falls inside the period -> included
        settlements = self._run_settlement_for_partner(
            partner, agreement, date_from="2022-02-01", date_to="2022-12-31"
        )
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 4000)

    def test_invoice_line_counted_once_with_multiple_do(self):
        partner = self.partner_3
        order_1 = self._create_delivered_sale(
            partner, [(self.product_1, 1, 500.0)], do_date="2022-01-15"
        )
        order_2 = self._create_delivered_sale(
            partner, [(self.product_1, 1, 500.0)], do_date="2022-02-15"
        )
        self._create_multi_do_invoice(
            partner, [order_1, order_2], self.product_1, 1000.0
        )
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 2000)
        self.assertEqual(settlements.amount_rebate, 200)


@tagged("-at_install", "post_install")
class TestAgreementRebateCreditNotes(TestAgreementRebateBase):
    """Credit note and return handling."""

    def test_posted_refund_with_origin_deducts(self):
        partner = self.partner_3
        invoice = self._create_sold_invoice(
            partner,
            [(self.product_1, 1, 1000.0), (self.product_2, 1, 2000.0)],
        )
        refund = self._create_refund(invoice)
        self.assertTrue(refund)
        # Both lines refunded -> net is zero, no settlement is created
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_partial_refund_with_origin_deducts(self):
        partner = self.partner_3
        invoice = self._create_sold_invoice(
            partner,
            [(self.product_1, 1, 1000.0), (self.product_2, 1, 2000.0)],
        )
        product_1_line = invoice.invoice_line_ids.filtered(
            lambda line: line.product_id == self.product_1
        )
        self._create_refund(invoice, product_1_line)
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 2000)
        self.assertEqual(settlements.amount_rebate, 200)

    def test_draft_refund_not_deducted(self):
        partner = self.partner_3
        invoice = self._create_sold_invoice(
            partner,
            [(self.product_1, 1, 1000.0), (self.product_2, 1, 2000.0)],
        )
        refund = self._create_refund(invoice, post=False)
        self.assertEqual(refund.state, "draft")
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 3000)
        self.assertEqual(settlements.amount_rebate, 300)

    def test_refund_without_origin_line_not_deducted(self):
        partner = self.partner_3
        invoice = self._create_sold_invoice(
            partner,
            [(self.product_1, 1, 1000.0), (self.product_2, 1, 2000.0)],
        )
        # Standalone credit note without origin_line_id
        self.env["account.move"].create(
            {
                "partner_id": partner.id,
                "move_type": "out_refund",
                "invoice_date": "2022-06-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Standalone credit",
                            "product_id": self.product_1.id,
                            "quantity": 1,
                            "price_unit": 1000.0,
                        }
                    )
                ],
            }
        ).action_post()
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 3000)
        self.assertEqual(settlements.amount_rebate, 300)

    def test_reversal_wizard_refund_deducts(self):
        # Credit notes created through the reversal wizard keep the origin link
        partner = self.partner_3
        invoice = self._create_sold_invoice(partner, [(self.product_1, 1, 1000.0)])
        reversal = self.env["account.move.reversal"].with_context(
            active_ids=invoice.ids, active_model="account.move"
        ).create(
            {
                "reason": "Test refund",
                "journal_id": self.sale_journal.id,
            }
        )
        reversal.reverse_moves(is_modify=False)
        refund = invoice.refund_invoice_ids[-1]
        if refund.state == "draft":
            refund.action_post()
        self.assertTrue(refund.invoice_line_ids.mapped("origin_line_id"))
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_return_done_without_refund_blocks(self):
        partner = self.partner_3
        invoice = self._create_sold_invoice(partner, [(self.product_1, 1, 1000.0)])
        picking = invoice.invoice_line_ids.sale_line_ids.move_ids.picking_id
        self._create_return(picking)
        agreement = self._global_agreement(partner)
        with self.assertRaises(UserError) as err:
            self._run_settlement_for_partner(partner, agreement)
        message = str(err.exception)
        self.assertIn(invoice.name, message)
        self.assertIn(picking.name, message)

    def test_return_done_with_refund_passes(self):
        partner = self.partner_3
        invoice = self._create_sold_invoice(partner, [(self.product_1, 1, 1000.0)])
        picking = invoice.invoice_line_ids.sale_line_ids.move_ids.picking_id
        self._create_return(picking)
        product_1_line = invoice.invoice_line_ids.filtered(
            lambda line: line.product_id == self.product_1
        )
        self._create_refund(invoice, product_1_line)
        agreement = self._global_agreement(partner)
        # The return is covered by a posted credit note so the settlement is not
        # blocked; the net amount is zero so no settlement line is created.
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)


@tagged("-at_install", "post_install")
class TestAgreementRebateDuplicatePrevention(TestAgreementRebateBase):
    """Duplicate prevention at invoice / credit note line level."""

    def _create_delivered_invoice(self, partner, price=1000.0):
        return self._create_sold_invoice(
            partner, [(self.product_1, 1, price)], do_date="2022-01-15"
        )

    def test_rerun_does_not_duplicate(self):
        partner = self.partner_3
        self._create_delivered_invoice(partner)
        agreement = self._global_agreement(partner)
        first = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(first), 1)
        second = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(second), 0)

    def test_overlapping_period_no_duplicate(self):
        partner = self.partner_4
        self._create_delivered_invoice(partner)
        agreement = self._global_agreement(partner)
        first = self._run_settlement_for_partner(
            partner, agreement, date_from="2022-01-01", date_to="2022-01-31"
        )
        self.assertEqual(len(first), 1)
        second = self._run_settlement_for_partner(
            partner, agreement, date_from="2022-01-01", date_to="2022-12-31"
        )
        self.assertEqual(len(second), 0)

    def test_archived_settlement_still_blocks(self):
        partner = self.partner_5
        self._create_delivered_invoice(partner)
        agreement = self._global_agreement(partner)
        first = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(first), 1)
        first.action_archive()
        second = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(second), 0)

    def test_no_new_items_no_empty_settlement(self):
        partner = self.partner_3
        agreement = self._global_agreement(partner)
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)


@tagged("-at_install", "post_install")
class TestAgreementRebateTiers(TestAgreementRebateBase):
    """Cumulative tier selection for section_total."""

    def test_tier_lower_boundary(self):
        partner = self.partner_3
        self._create_sold_invoice(partner, [(self.product_1, 1, 100.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 100.0, "rebate_discount": 10.0},
                {"amount_from": 100.01, "amount_to": 300.0, "rebate_discount": 20.0},
                {"amount_from": 300.01, "amount_to": 0.0, "rebate_discount": 30.0},
            ],
        )
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 100)
        self.assertEqual(settlements.amount_rebate, 10)

    def test_tier_upper_boundary(self):
        partner = self.partner_4
        self._create_sold_invoice(partner, [(self.product_1, 1, 300.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 100.0, "rebate_discount": 10.0},
                {"amount_from": 100.01, "amount_to": 300.0, "rebate_discount": 20.0},
                {"amount_from": 300.01, "amount_to": 0.0, "rebate_discount": 30.0},
            ],
        )
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 300)
        self.assertEqual(settlements.amount_rebate, 60)

    def test_open_ended_tier_supports_amount_above(self):
        partner = self.partner_5
        self._create_sold_invoice(partner, [(self.product_1, 1, 1500.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 1000.0, "rebate_discount": 10.0},
                {"amount_from": 1000.0, "amount_to": 0.0, "rebate_discount": 30.0},
            ],
        )
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 1500)
        self.assertEqual(settlements.amount_rebate, 450)

    def test_single_tier_single_percent_on_whole_amount(self):
        partner = self.partner_3
        self._create_sold_invoice(
            partner, [(self.product_1, 1, 1000.0), (self.product_2, 1, 2000.0)]
        )
        agreement = self._section_total_agreement(
            partner, [{"amount_from": 0.0, "amount_to": 10000.0, "rebate_discount": 15.0}]
        )
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 1)
        self.assertEqual(settlements.amount_invoiced, 3000)
        self.assertEqual(settlements.amount_rebate, 450)

    def test_overlapping_tiers_rejected(self):
        partner = self.partner_3
        self._create_sold_invoice(partner, [(self.product_1, 1, 800.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 500.0, "rebate_discount": 10.0},
                {"amount_from": 400.0, "amount_to": 1000.0, "rebate_discount": 20.0},
            ],
        )
        with self.assertRaises(UserError):
            self._run_settlement_for_partner(partner, agreement)

    def test_amount_in_gap_rejected(self):
        partner = self.partner_4
        self._create_sold_invoice(partner, [(self.product_1, 1, 300.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 100.0, "rebate_discount": 10.0},
                {"amount_from": 500.0, "amount_to": 0.0, "rebate_discount": 20.0},
            ],
        )
        with self.assertRaises(UserError):
            self._run_settlement_for_partner(partner, agreement)

    def test_no_matching_tier_rejected(self):
        partner = self.partner_5
        self._create_sold_invoice(partner, [(self.product_1, 1, 500.0)])
        agreement = self._section_total_agreement(
            partner, [{"amount_from": 0.0, "amount_to": 100.0, "rebate_discount": 10.0}]
        )
        with self.assertRaises(UserError):
            self._run_settlement_for_partner(partner, agreement)

    def test_multiple_open_ended_tiers_rejected(self):
        partner = self.partner_3
        self._create_sold_invoice(partner, [(self.product_1, 1, 800.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 0.0, "rebate_discount": 10.0},
                {"amount_from": 0.0, "amount_to": 0.0, "rebate_discount": 20.0},
            ],
        )
        with self.assertRaises(UserError):
            self._run_settlement_for_partner(partner, agreement)

    def test_more_than_one_matching_tier_rejected(self):
        partner = self.partner_4
        self._create_sold_invoice(partner, [(self.product_1, 1, 100.0)])
        agreement = self._section_total_agreement(
            partner,
            [
                {"amount_from": 0.0, "amount_to": 100.0, "rebate_discount": 10.0},
                {"amount_from": 100.0, "amount_to": 0.0, "rebate_discount": 20.0},
            ],
        )
        with self.assertRaises(UserError):
            self._run_settlement_for_partner(partner, agreement)


@tagged("-at_install", "post_install")
class TestAgreementRebateApproval(TestAgreementRebateBase):
    """Approved state locking."""

    def test_draft_agreement_editable(self):
        agreement = self.Agreement.create(
            {
                "domain": "sale",
                "name": "Editable",
                "code": "ED-001",
                "partner_id": self.partner_1.id,
                "agreement_type_id": self.agreement_type.id,
                "rebate_type": "global",
                "rebate_discount": 5.0,
            }
        )
        agreement.write(
            {
                "rebate_discount": 6.0,
                "rebate_line_ids": [
                    Command.create(
                        {
                            "rebate_target": "product",
                            "rebate_product_ids": [Command.set(self.product_1.ids)],
                            "rebate_discount": 8.0,
                        }
                    )
                ],
            }
        )
        self.assertEqual(agreement.rebate_discount, 6.0)

    def test_unapproved_agreement_not_used_for_settlement(self):
        partner = self.partner_3
        self._create_sold_invoice(partner, [(self.product_1, 1, 1000.0)])
        agreement = self.Agreement.create(
            {
                "domain": "sale",
                "start_date": "2022-01-01",
                "rebate_type": "global",
                "rebate_discount": 10.0,
                "name": "Not approved",
                "code": "NA-001",
                "partner_id": partner.id,
                "agreement_type_id": self.agreement_type.id,
            }
        )
        self.assertEqual(agreement.rebate_approval_state, "draft")
        settlements = self._run_settlement_for_partner(partner, agreement)
        self.assertEqual(len(settlements), 0)

    def test_approved_agreement_write_blocked(self):
        agreement = self._global_agreement(self.partner_1)
        locked_fields = [
            "partner_id",
            "agreement_type_id",
            "domain",
            "signature_date",
            "start_date",
            "end_date",
            "rebate_type",
            "rebate_discount",
            "rebate_line_ids",
            "rebate_section_ids",
        ]
        other_partner = self.partner_2
        other_type = self.AgreementType.create(
            {"name": "Other", "domain": "sale", "is_rebate": True}
        )
        values = {
            "partner_id": other_partner.id,
            "agreement_type_id": other_type.id,
            "domain": "purchase",
            "signature_date": "2022-02-01",
            "start_date": "2022-02-01",
            "end_date": "2023-01-01",
            "rebate_type": "line",
            "rebate_discount": 50.0,
            "rebate_line_ids": [Command.clear()],
            "rebate_section_ids": [Command.clear()],
        }
        for field_name in locked_fields:
            with self.assertRaises(UserError, msg=field_name):
                agreement.write({field_name: values[field_name]})

    def test_approved_agreement_reset_context_cannot_unlock_business(self):
        agreement = self._global_agreement(self.partner_1)
        with self.assertRaises(UserError):
            agreement.with_context(agreement_rebate_reset=True).write(
                {"rebate_discount": 9.0}
            )

    def test_approved_rebate_line_locked(self):
        agreement = self._global_agreement(self.partner_1)
        with self.assertRaises(UserError):
            self.env["agreement.rebate.line"].create(
                {
                    "agreement_id": agreement.id,
                    "rebate_target": "product",
                    "rebate_product_ids": [Command.set(self.product_1.ids)],
                    "rebate_discount": 5.0,
                }
            )
        against_agreement = self.Agreement.create(
            {
                "domain": "sale",
                "name": "With lines",
                "code": "WL-001",
                "partner_id": self.partner_1.id,
                "agreement_type_id": self.agreement_type.id,
                "rebate_type": "line",
                "rebate_line_ids": [
                    Command.create(
                        {
                            "rebate_target": "product",
                            "rebate_product_ids": [Command.set(self.product_1.ids)],
                            "rebate_discount": 5.0,
                        }
                    )
                ],
            }
        )
        self._approve_agreement(against_agreement)
        with self.assertRaises(UserError):
            against_agreement.rebate_line_ids.write({"rebate_discount": 99.0})
        with self.assertRaises(UserError):
            against_agreement.rebate_line_ids[0].unlink()

    def test_approved_rebate_section_locked(self):
        agreement = self._global_agreement(self.partner_1)
        with self.assertRaises(UserError):
            self.env["agreement.rebate.section"].create(
                {
                    "agreement_id": agreement.id,
                    "amount_from": 0.0,
                    "amount_to": 100.0,
                    "rebate_discount": 5.0,
                }
            )
        against_agreement = self.Agreement.create(
            {
                "domain": "sale",
                "name": "With sections",
                "code": "WS-001",
                "partner_id": self.partner_1.id,
                "agreement_type_id": self.agreement_type.id,
                "rebate_type": "section_total",
                "rebate_section_ids": [
                    Command.create(
                        {
                            "amount_from": 0.0,
                            "amount_to": 100.0,
                            "rebate_discount": 5.0,
                        }
                    )
                ],
            }
        )
        self._approve_agreement(against_agreement)
        with self.assertRaises(UserError):
            against_agreement.rebate_section_ids.write({"rebate_discount": 99.0})
        with self.assertRaises(UserError):
            against_agreement.rebate_section_ids[0].unlink()

    def test_reset_unlocks_agreement(self):
        agreement = self._global_agreement(self.partner_1)
        agreement.action_reset_rebate()
        self.assertEqual(agreement.rebate_approval_state, "draft")
        agreement.write({"rebate_discount": 6.0})
        self.assertEqual(agreement.rebate_discount, 6.0)

    def test_import_style_write_rejected(self):
        agreement = self._global_agreement(self.partner_1)
        with self.assertRaises(UserError):
            agreement.write({"rebate_discount": 3.0, "rebate_approval_state": "draft"})