"""Margin tests — POS Lite must pull standard cost from the same Standard Cost
Pricelist as Sales Orders and compute margin the same way.

Covers:
  * standard_cost_price / margin on pos.lite.order.line
  * margin / margin_percent on pos.lite.order
  * parity with sale.order.line + sale.order (the "เหมือนกับ SO" requirement)
  * no-cost-pricelist and return-order edge cases
"""

from odoo.tests import common, tagged


class MarginTestBase(common.TransactionCase):
    """Shared setup: a Standard Cost Pricelist priced at 60 for the product."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        cls.category = cls.env['product.category'].create({'name': 'Margin Cat'})
        cls.product = cls.env['product.product'].create({
            'name': 'Margin Widget',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 100.0,
            'taxes_id': [(5, 0, 0)],  # no tax → predictable subtotals
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Margin Customer',
            'customer_rank': 1,
        })

        # Sales pricelist — explicit fixed price so SO and POS both see 100.
        cls.sales_pricelist = cls.env['product.pricelist'].create({
            'name': 'Margin Sales PL',
            'company_id': cls.company.id,
        })
        cls.env['product.pricelist.item'].create({
            'pricelist_id': cls.sales_pricelist.id,
            'applied_on': '1_product',
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'compute_price': 'fixed',
            'fixed_price': 100.0,
        })

        # Standard Cost Pricelist — the single source of standard cost.
        # Clear any pre-existing one for this company (MOG_DEV data) first.
        existing = cls.env['product.pricelist'].search([
            ('is_standard_cost_pricelist', '=', True),
            ('company_id', '=', cls.company.id),
        ])
        existing.sudo().write({'is_standard_cost_pricelist': False})

        cls.cost_pricelist = cls.env['product.pricelist'].create({
            'name': 'Margin Standard Cost PL',
            'company_id': cls.company.id,
        })
        cls.env['product.pricelist.item'].create({
            'pricelist_id': cls.cost_pricelist.id,
            'applied_on': '1_product',
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'compute_price': 'fixed',
            'fixed_price': 60.0,
        })
        # Marking requires Pricing Admin — sudo() sets is_superuser() → bypass.
        cls.cost_pricelist.sudo().write({'is_standard_cost_pricelist': True})

        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Margin Cash',
            'type': 'cash',
            'code': 'MCSH',
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Margin Emp',
            'company_id': cls.company.id,
        })
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Margin Cfg',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.sales_pricelist.id,
            'journal_id': cls.cash_journal.id,
        })
        cls.env.cr.execute(
            "UPDATE ir_sequence SET number_next = 100000 "
            "WHERE code IN ('pos.lite.session', 'pos.lite.order') AND number_next < 100000"
        )
        cls.env.invalidate_all()
        cls.session = cls.env['pos.lite.session'].create({
            'config_id': cls.config.id,
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
        })

    # ── helpers ────────────────────────────────────────────────

    def _draft_pos_order(self, lines):
        line_cmds = [(0, 0, {
            'product_id': pid, 'qty': qty, 'price_unit': price,
        }) for pid, qty, price in lines]
        return self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.sales_pricelist.id,
            'session_id': self.session.id,
            'line_ids': line_cmds,
        })

    def _sale_order(self, lines):
        line_cmds = [(0, 0, {
            'product_id': pid, 'product_uom_qty': qty, 'price_unit': price,
        }) for pid, qty, price in lines]
        so = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'pricelist_id': self.sales_pricelist.id,
            'company_id': self.company.id,
            'order_line': line_cmds,
        })
        so.flush_recordset()
        so.order_line.flush_recordset()
        return so


@tagged('-at_install', 'post_install')
class TestStandardCostMargin(MarginTestBase):

    def test_line_standard_cost_and_margin(self):
        """std cost = 60, qty 2 @ 100 → subtotal 200, margin 80."""
        order = self._draft_pos_order([(self.product.id, 2, 100.0)])
        line = order.line_ids[0]
        self.assertAlmostEqual(line.standard_cost_price, 60.0, places=2)
        # margin = subtotal - (cost * qty) = 200 - 120 = 80
        self.assertAlmostEqual(line.margin, 80.0, places=2)

    def test_order_margin_and_percent(self):
        """order.margin = 80, margin_percent = 80/200 = 0.4 (fraction)."""
        order = self._draft_pos_order([(self.product.id, 2, 100.0)])
        order.invalidate_recordset()
        self.assertAlmostEqual(order.margin, 80.0, places=2)
        # Stored as a fraction (margin / amount_untaxed) → pairs with the
        # percentage widget, identical to buz_sale_pricelist_standard_cost's SO.
        self.assertAlmostEqual(order.margin_percent, 0.4, places=4)

    def test_parity_with_sale_order(self):
        """POS Lite margin must equal the equivalent SO margin (เหมือนกับ SO)."""
        pos = self._draft_pos_order([(self.product.id, 2, 100.0)])
        pos.invalidate_recordset()
        so = self._sale_order([(self.product.id, 2, 100.0)])

        # Same standard cost source
        self.assertAlmostEqual(
            pos.line_ids[0].standard_cost_price,
            so.order_line[0].purchase_price, places=2,
        )
        self.assertAlmostEqual(so.order_line[0].purchase_price, 60.0, places=2)

        # Same line margin
        self.assertAlmostEqual(
            pos.line_ids[0].margin, so.order_line[0].margin, places=2,
        )
        # Same order-level margin
        self.assertAlmostEqual(pos.margin, so.margin, places=2)
        self.assertAlmostEqual(so.margin, 80.0, places=2)

    def test_discount_reduces_margin(self):
        """A discount cuts revenue but not cost → margin drops."""
        order = self._draft_pos_order([(self.product.id, 1, 100.0)])
        line = order.line_ids[0]
        line.discount = 10.0  # percent → 10% off
        line.discount_type = 'percent'
        order.invalidate_recordset()
        # subtotal = 100 * 0.9 = 90 ; cost = 60 ; margin = 30
        self.assertAlmostEqual(line.price_subtotal, 90.0, places=2)
        self.assertAlmostEqual(line.standard_cost_price, 60.0, places=2)
        self.assertAlmostEqual(line.margin, 30.0, places=2)
        self.assertAlmostEqual(order.margin, 30.0, places=2)

    def test_no_standard_cost_pricelist_means_zero_cost(self):
        """Without a cost pricelist, cost = 0 and margin = full subtotal."""
        self.cost_pricelist.sudo().write({'is_standard_cost_pricelist': False})
        order = self._draft_pos_order([(self.product.id, 1, 100.0)])
        order.invalidate_recordset()
        self.assertAlmostEqual(order.line_ids[0].standard_cost_price, 0.0, places=2)
        self.assertAlmostEqual(order.line_ids[0].margin, 100.0, places=2)
        self.assertAlmostEqual(order.margin, 100.0, places=2)
        # Restore for other tests in the same TransactionCase they'd rollback,
        # but be explicit to avoid bleed if a future test reuses the cursor.
        self.cost_pricelist.sudo().write({'is_standard_cost_pricelist': True})

    def test_product_without_cost_rule_matches_so(self):
        """A product with no rule on the cost pricelist is costed identically on
        POS Lite and SO — the shared helper guarantees parity (Odoo falls back
        to list_price, so the cost is the same value on both sides)."""
        other = self.env['product.product'].create({
            'name': 'No Cost Product',
            'type': 'service',
            'categ_id': self.category.id,
            'sale_ok': True,
            'list_price': 50.0,
            'taxes_id': [(5, 0, 0)],
        })
        pos = self._draft_pos_order([(other.id, 1, 50.0)])
        pos.invalidate_recordset()
        so = self._sale_order([(other.id, 1, 50.0)])
        # Same source + same helper → identical cost regardless of fallback.
        self.assertAlmostEqual(
            pos.line_ids[0].standard_cost_price,
            so.order_line[0].purchase_price, places=2,
        )
        self.assertAlmostEqual(pos.margin, so.margin, places=2)

    def test_return_order_negates_margin(self):
        """Returns reverse the profit impact, mirroring the negated amount_untaxed."""
        order = self._draft_pos_order([(self.product.id, 1, 100.0)])
        order.invalidate_recordset()
        self.assertAlmostEqual(order.margin, 40.0, places=2)  # 100 - 60

        return_order = self.env['pos.lite.order'].create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.sales_pricelist.id,
            'is_return': True,
            'return_of_order_id': order.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'qty': 1,
                'price_unit': 100.0,
                'returned_from_line_id': order.line_ids[0].id,
            })],
        })
        return_order.invalidate_recordset()
        # Line margin is the item's gross margin (positive), but the order
        # negates it so profit reporting matches the negative amount_untaxed.
        self.assertAlmostEqual(return_order.line_ids[0].margin, 40.0, places=2)
        self.assertAlmostEqual(return_order.margin, -40.0, places=2)
        # amount_untaxed is negative for returns, margin is negative → rate stays positive
        self.assertAlmostEqual(return_order.margin_percent, 0.4, places=4)
