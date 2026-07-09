"""Tests for POS Lite x Marketplace Settlement trade_channel integration."""

from odoo.tests import common, tagged
from odoo.exceptions import UserError


@tagged('-at_install', 'post_install')
class TestTradeChannel(common.TransactionCase):
    """Test trade_channel propagation from POS Lite → invoices."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company

        cls.category = cls.env['product.category'].create({
            'name': 'Test Cat - Channel',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test SVC Channel',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 100.0,
            'taxes_id': [(5, 0, 0)],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Cust Channel',
            'customer_rank': 1,
        })
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'PL Channel',
            'company_id': cls.company.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Cash J Channel',
            'type': 'cash',
            'code': 'CJCH',
            'company_id': cls.company.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Emp Channel',
            'company_id': cls.company.id,
        })
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Cfg Channel',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'pricelist_id': cls.pricelist.id,
            'journal_id': cls.cash_journal.id,
        })
        # Advance sequences to avoid conflict with existing data
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 100000 WHERE code = 'pos.lite.session' AND number_next < 100000")
        cls.env.cr.execute("UPDATE ir_sequence SET number_next = 100000 WHERE code = 'pos.lite.order' AND number_next < 100000")
        cls.env.invalidate_all()
        cls.session = cls.env['pos.lite.session'].create({
            'config_id': cls.config.id,
            'employee_id': cls.employee.id,
            'company_id': cls.company.id,
        })

    def _draft_order(self, channel='walkin', trade_channel=None, **kw):
        line_cmds = [(0, 0, {
            'product_id': self.product.id,
            'qty': 1,
            'price_unit': 100.0,
        })]
        vals = {
            'company_id': self.company.id,
            'channel': channel,
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': self.session.id,
            'line_ids': line_cmds,
        }
        if trade_channel:
            vals['trade_channel'] = trade_channel
        vals.update(kw)
        return self.env['pos.lite.order'].create(vals)

    def _process_order(self, **kw):
        order = self._draft_order(**kw)
        order.action_quick_pay_and_process()
        self.assertEqual(order.state, 'done')
        return order

    # ─── Auto-mapping ─────────────────────────────────────

    def test_channel_walkin_maps_to_offline(self):
        """walkin → auto-mapped to offline_mogen_outlet"""
        order = self._draft_order(channel='walkin')
        self.assertEqual(order.trade_channel, 'offline_mogen_outlet')

    def test_channel_phone_maps_to_online(self):
        """phone → auto-mapped to online_line_fb"""
        order = self._draft_order(channel='phone')
        self.assertEqual(order.trade_channel, 'online_line_fb')

    def test_channel_line_maps_to_online(self):
        """line → auto-mapped to online_line_fb"""
        order = self._draft_order(channel='line')
        self.assertEqual(order.trade_channel, 'online_line_fb')

    def test_channel_other_maps_to_other(self):
        """other → auto-mapped to other"""
        order = self._draft_order(channel='other')
        self.assertEqual(order.trade_channel, 'other')

    def test_explicit_trade_channel_not_overridden(self):
        """Explicit trade_channel is preserved, not auto-overridden"""
        order = self._draft_order(channel='phone', trade_channel='shopee')
        self.assertEqual(order.trade_channel, 'shopee')

    # ─── Propagation to invoice ───────────────────────────

    def test_invoice_gets_trade_channel(self):
        """Posted invoice must have the same trade_channel as the POS order"""
        order = self._process_order(channel='walkin', trade_channel='shopee')
        self.assertTrue(order.invoice_id)
        self.assertEqual(order.invoice_id.trade_channel, 'shopee')

    def test_invoice_trade_channel_phone_to_online(self):
        """phone order → invoice trade_channel = online_line_fb"""
        order = self._process_order(channel='phone')
        self.assertEqual(order.invoice_id.trade_channel, 'online_line_fb')

    # ─── Reorder ──────────────────────────────────────────

    def test_reorder_preserves_trade_channel(self):
        """Re-order must copy trade_channel from original"""
        original = self._process_order(channel='walkin', trade_channel='lazada')
        result = original.action_reorder()
        new_order = self.env['pos.lite.order'].browse(result['res_id'])
        self.assertEqual(new_order.trade_channel, 'lazada')

    # ─── Config default ───────────────────────────────────

    def test_config_default_trade_channel_on_change(self):
        """Config default_trade_channel flows to order via onchange_company_id"""
        self.config.default_trade_channel = 'tiktok'
        # Simulate the onchange
        order = self.env['pos.lite.order'].new({
            'company_id': self.company.id,
            'channel': 'walkin',
        })
        order._onchange_company_id()
        self.assertEqual(order.trade_channel, 'tiktok')

    def test_config_profile_sets_default_trade_channel(self):
        """Setting marketplace_profile_id auto-sets default_trade_channel via onchange"""
        if 'marketplace.settlement.profile' not in self.env:
            self.skipTest('marketplace_settlement module not installed')

        profile = self.env['marketplace.settlement.profile'].create({
            'name': 'Shopee Test',
            'trade_channel': 'shopee',
        })
        # Simulate onchange — direct write doesn't trigger onchange
        self.config.write({'marketplace_profile_id': profile.id})
        self.config._onchange_marketplace_profile_id()
        self.assertEqual(self.config.default_trade_channel, 'shopee')

    # ─── Return preserves trade_channel ───────────────────

    def test_return_preserves_trade_channel(self):
        """Return order must carry the same trade_channel as original"""
        original = self._process_order(channel='line', trade_channel='shopee')
        wizard = self.env['pos.lite.return.wizard'].create({
            'order_id': original.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()
        return_order = self.env['pos.lite.order'].search([
            ('return_of_order_id', '=', original.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertEqual(return_order.trade_channel, 'shopee')
