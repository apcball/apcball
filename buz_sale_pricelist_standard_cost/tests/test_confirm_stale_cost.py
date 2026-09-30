from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConfirmStaleCost(TransactionCase):
    """Cost added to the Standard Cost Pricelist after the SO line was created
    must not block action_confirm (stored purchase_price is otherwise stale)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.std_pricelist = cls.env['product.pricelist']._get_standard_cost_pricelist(cls.company)
        if not cls.std_pricelist:
            cls.std_pricelist = cls.env['product.pricelist'].create({
                'name': 'TEST STANDARD COST',
                'is_standard_cost_pricelist': True,
                'company_id': cls.company.id,
                'currency_id': cls.company.currency_id.id,
            })
        # Drop any generic rule so a product without its own rule has no cost
        # (rolled back with the test transaction).
        cls.std_pricelist.item_ids.unlink()
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], order='id', limit=1)
        # Neutralise margin gates so only the missing-cost check is exercised.
        params = cls.env['ir.config_parameter'].sudo()
        params.set_param('sale_pricelist_standard_cost.minimum_margin_percent', '0')
        params.set_param('sale_pricelist_standard_cost.block_negative_margin', 'False')

        # Reuse the company partner: other addons enforce required partner fields on create.
        cls.partner = cls.company.partner_id
        cls.product = cls.env['product.product'].create({
            'name': 'Stale Cost Test Product',
            'type': 'consu',
            'list_price': 100.0,
        })
        # Explicit zero rule = "no cost yet" (with no rule at all, Odoo falls
        # back to list price, which is not what happens for blocked products).
        cls.cost_rule = cls.env['product.pricelist.item'].create({
            'pricelist_id': cls.std_pricelist.id,
            'applied_on': '0_product_variant',
            'product_id': cls.product.id,
            'compute_price': 'fixed',
            'fixed_price': 0.0,
        })

    def _make_order(self):
        return self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 1.0,
                'price_unit': 100.0,
            })],
        })

    def _add_cost_rule(self, price):
        self.cost_rule.fixed_price = price

    def _confirm(self, order):
        # Stock procurement is irrelevant here and depends on DEV warehouse routes.
        with patch.object(
            self.env.registry['sale.order.line'], '_action_launch_stock_rule',
            return_value=True,
        ):
            order.action_confirm()

    def test_still_blocked_without_cost(self):
        order = self._make_order()
        self.assertEqual(order.order_line.purchase_price, 0.0)
        with self.assertRaises(ValidationError):
            self._confirm(order)
        self.assertEqual(order.state, 'draft')

    def test_cost_added_after_line_created_allows_confirm(self):
        order = self._make_order()
        self.assertEqual(order.order_line.purchase_price, 0.0)
        self._add_cost_rule(50.0)
        # Stored value stays stale until confirm refreshes it.
        self.assertEqual(order.order_line.purchase_price, 0.0)
        self._confirm(order)
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.order_line.purchase_price, 50.0)
        self.assertEqual(order.order_line.standard_cost_price, 50.0)
