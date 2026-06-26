from odoo.tests import common, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestReserveManagerCore(common.TransactionCase):
    """Test the Reserve Manager module."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Products – product_a starts with stock, product_b without
        cls.product_a = cls.env['product.product'].create({
            'name': 'Reserve Test A (with stock)',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
            'list_price': 100.0,
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Reserve Test B (no stock)',
            'type': 'product',
            'taxes_id': [(5, 0, 0)],
            'list_price': 200.0,
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Reserve Test Customer',
        })

        # Warehouse
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.env.company.id),
        ], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id

        # Stock for product_a only
        cls.env['stock.quant'].create({
            'product_id': cls.product_a.id,
            'location_id': cls.stock_location.id,
            'quantity': 50.0,
        })

        # -- SO with product_b (no stock → stays 'confirmed', no auto-assign) --
        cls.so_no_stock = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'partner_invoice_id': cls.partner.id,
            'partner_shipping_id': cls.partner.id,
            'warehouse_id': cls.warehouse.id,
            'order_line': [(0, 0, {
                'product_id': cls.product_b.id,
                'product_uom_qty': 10.0,
                'price_unit': 200.0,
            })],
        })
        cls.so_no_stock.action_confirm()
        cls.move_no_stock = cls.env['stock.move'].search([
            ('sale_line_id', 'in', cls.so_no_stock.order_line.ids),
        ], limit=1)

        # -- SO with product_a (has stock → auto-assigns) --
        cls.so_with_stock = cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'partner_invoice_id': cls.partner.id,
            'partner_shipping_id': cls.partner.id,
            'warehouse_id': cls.warehouse.id,
            'order_line': [(0, 0, {
                'product_id': cls.product_a.id,
                'product_uom_qty': 10.0,
                'price_unit': 100.0,
            })],
        })
        cls.so_with_stock.action_confirm()
        cls.move_with_stock = cls.env['stock.move'].search([
            ('sale_line_id', 'in', cls.so_with_stock.order_line.ids),
        ], limit=1)

        # Manager pointing at the no-stock SO (no auto-assigned moves)
        cls.manager = cls.env['buz.reserve.manager'].create({
            'sale_order_ids': [(6, 0, cls.so_no_stock.ids)],
        })
        cls.manager.write({'name': 'RM-TEST-001'})

        # Manager pointing at the with-stock SO
        cls.manager_full = cls.env['buz.reserve.manager'].create({
            'sale_order_ids': [(6, 0, cls.so_with_stock.ids)],
        })
        cls.manager_full.write({'name': 'RM-TEST-002'})

    # ========================================================================
    #  --- Manager Model ---
    # ========================================================================

    def test_01_manager_report_name(self):
        """Manager name_get works."""
        self.assertEqual(self.manager.name_get()[0][1], 'RM-TEST-001')

    def test_02_manager_initial_state_draft(self):
        self.assertEqual(self.manager.state, 'draft')

    def test_03_manager_load_lines_success(self):
        """Load pulls the SO's stock moves (no-stock SO → reserve_state = 'none')."""
        self.manager.action_load_lines()
        self.assertEqual(self.manager.state, 'loaded')
        self.assertGreater(len(self.manager.line_ids), 0)

        line = self.manager.line_ids[0]
        self.assertEqual(line.sale_order_id, self.so_no_stock)
        self.assertEqual(line.product_id, self.product_b)
        self.assertEqual(line.demand_qty, 10.0)
        self.assertEqual(line.reserve_state, 'none')

    def test_04_manager_load_lines_full(self):
        """Load with a stock → auto-assigned SO → reserve_state = 'full'."""
        self.manager_full.action_load_lines()
        self.assertEqual(self.manager_full.state, 'loaded')

        line = self.manager_full.line_ids[0]
        self.assertEqual(line.reserve_state, 'full')
        self.assertEqual(line.reserved_qty, 10.0)
        self.assertAlmostEqual(line.available_qty, 40.0, delta=0.01)

    def test_05_manager_load_lines_no_match_raises(self):
        """Load with no matching moves raises UserError."""
        empty = self.env['buz.reserve.manager'].create({
            'name': 'EMPTY',
            'product_ids': [(6, 0, [self.product_a.id])],
            'sale_order_ids': [(6, 0, self.so_no_stock.ids)],
        })
        with self.assertRaises(UserError):
            empty.action_load_lines()

    def test_06_manager_summary_computed(self):
        """Summary fields reflect loaded lines."""
        self.manager.action_load_lines()
        self.assertEqual(self.manager.line_count, len(self.manager.line_ids))
        self.assertEqual(self.manager.summary_demand_qty, 10.0)
        self.assertEqual(self.manager.summary_reserved_qty, 0.0)

    def test_07_manager_clear_lines(self):
        """Clear resets to draft and removes lines."""
        self.manager.action_load_lines()
        self.assertEqual(self.manager.state, 'loaded')
        self.manager.action_clear_lines()
        self.assertEqual(self.manager.state, 'draft')
        self.assertEqual(len(self.manager.line_ids), 0)

    def test_08_manager_reload(self):
        """Reload re-populates lines."""
        self.manager.action_load_lines()
        first_count = len(self.manager.line_ids)
        self.manager.action_reload()
        self.assertEqual(len(self.manager.line_ids), first_count)

    def test_09_manager_unreserve_all_no_reservations(self):
        """Unreserve all on unreserved lines raises."""
        self.manager.action_load_lines()
        with self.assertRaises(UserError):
            self.manager.action_unreserve_all()

    def test_10_manager_filter_by_product(self):
        """Product filter restricts loaded lines."""
        mgr = self.env['buz.reserve.manager'].create({
            'name': 'FILTER',
            'sale_order_ids': [(6, 0, self.so_no_stock.ids)],
            'product_ids': [(6, 0, [self.product_b.id])],
        })
        mgr.action_load_lines()
        self.assertGreater(len(mgr.line_ids), 0)
        for line in mgr.line_ids:
            self.assertEqual(line.product_id, self.product_b)

    def test_11_manager_filter_no_match_raises(self):
        """Non-matching product filter raises."""
        mgr = self.env['buz.reserve.manager'].create({
            'name': 'NO-MATCH',
            'sale_order_ids': [(6, 0, self.so_no_stock.ids)],
            'product_ids': [(6, 0, [self.product_a.id])],
        })
        with self.assertRaises(UserError):
            mgr.action_load_lines()

    # ========================================================================
    #  --- Stock Move – Manual Reserve ---
    # ========================================================================

    def test_20_manual_reserve_partial(self):
        """Reserve a partial qty on a confirmed move."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 20.0,
        })
        returned = self.move_no_stock.action_manual_reserve(5.0)
        self.assertEqual(returned, 5.0)
        total = sum(self.move_no_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, 5.0)

    def test_21_manual_reserve_full_demand(self):
        """Reserve full demand qty."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 20.0,
        })
        qty = self.move_no_stock.product_uom_qty
        returned = self.move_no_stock.action_manual_reserve(qty)
        self.assertEqual(returned, qty)
        total = sum(self.move_no_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, qty)

    def test_22_manual_reserve_capped_at_available(self):
        """Reserve is capped by available stock."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 3.0,
        })
        returned = self.move_no_stock.action_manual_reserve(10.0)
        self.assertEqual(returned, 3.0)
        total = sum(self.move_no_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, 3.0)

    def test_23_manual_reserve_zero_raises(self):
        """Zero qty raises UserError."""
        with self.assertRaises(UserError):
            self.move_no_stock.action_manual_reserve(0)

    def test_24_manual_reserve_no_stock_raises(self):
        """No available stock at all raises."""
        with self.assertRaises(UserError):
            self.move_no_stock.action_manual_reserve(5.0)

    def test_25_already_fully_reserved_raises(self):
        """Already fully reserved raises UserError."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 50.0,
        })
        self.move_no_stock.action_manual_reserve(10.0)
        with self.assertRaises(UserError):
            self.move_no_stock.action_manual_reserve(1.0)

    def test_26_done_move_cannot_reserve(self):
        """Done/cancelled move raises."""
        self.move_no_stock.write({'state': 'done'})
        with self.assertRaises(UserError):
            self.move_no_stock.action_manual_reserve(5.0)

    # ========================================================================
    #  --- Stock Move – Unreserve ---
    # ========================================================================

    def test_30_unreserve_after_manual_reserve(self):
        """Unreserve clears the reservation."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 50.0,
        })
        self.move_no_stock.action_manual_reserve(10.0)
        self.assertGreater(
            sum(self.move_no_stock.move_line_ids.mapped('quantity')), 0
        )
        result = self.move_no_stock.action_unreserve_single()
        self.assertTrue(result)
        total = sum(self.move_no_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, 0.0)

    def test_31_unreserve_confirmed_move_raises(self):
        """Unreserve on a confirmed (not reserved) move raises."""
        with self.assertRaises(UserError):
            self.move_no_stock.action_unreserve_single()

    def test_32_unreserve_auto_assigned_move(self):
        """Unreserve on an auto-assigned move works."""
        result = self.move_with_stock.action_unreserve_single()
        self.assertTrue(result)
        total = sum(self.move_with_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, 0.0)

    # ========================================================================
    #  --- Manager Line Actions ---
    # ========================================================================

    def test_40_line_action_reserve_creates_wizard(self):
        """Line action_reserve opens the wizard."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        result = line.action_reserve()
        self.assertEqual(result['res_model'], 'buz.reserve.manual.wizard')
        self.assertIn('res_id', result)

    def test_41_line_unreserve(self):
        """Line unreserve via the manager line model."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 50.0,
        })
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]

        self.move_no_stock.action_manual_reserve(10.0)
        line._refresh_line()
        self.assertEqual(line.reserve_state, 'full')

        result = line.action_unreserve()
        self.assertIn('ir.actions.client', result.get('type', ''))
        line._refresh_line()
        self.assertEqual(line.reserve_state, 'none')

    def test_42_line_unreserve_not_reserved_raises(self):
        """Unreserve on unreserved line raises."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        with self.assertRaises(UserError):
            line.action_unreserve()

    def test_43_line_unreserve_by_so(self):
        """Unreserve by SO releases all SO lines."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 50.0,
        })
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        self.move_no_stock.action_manual_reserve(10.0)
        line._refresh_line()

        result = line.action_unreserve_by_so()
        self.assertIn('ir.actions.client', result.get('type', ''))
        line._refresh_line()
        self.assertEqual(line.reserve_state, 'none')

    def test_44_line_unreserve_by_so_no_reservation_raises(self):
        """Unreserve by SO with no reservation raises."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        with self.assertRaises(UserError):
            line.action_unreserve_by_so()

    def test_45_line_stock_move_deleted(self):
        """_refresh_line handles deleted stock move."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        line.stock_move_id.unlink()
        result = line._refresh_line()
        self.assertIn('ir.actions.client', result.get('type', ''))

    # ========================================================================
    #  --- Manual Reserve Wizard ---
    # ========================================================================

    def test_50_wizard_compute_max(self):
        """Wizard correctly caps max_reserve_qty."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]

        wizard = self.env['buz.reserve.manual.wizard'].create({
            'line_id': line.id,
            'stock_move_id': line.stock_move_id.id,
            'product_id': line.product_id.id,
            'demand_qty': line.demand_qty,
            'reserved_qty': 0.0,
            'available_qty': 50.0,
        })
        self.assertEqual(wizard.max_reserve_qty, 10.0)

    def test_51_wizard_onchange_max(self):
        """Onchange sets reserve_qty when max is positive."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]

        wizard = self.env['buz.reserve.manual.wizard'].create({
            'line_id': line.id,
            'stock_move_id': line.stock_move_id.id,
            'product_id': line.product_id.id,
            'demand_qty': line.demand_qty,
            'reserved_qty': 0.0,
            'available_qty': 50.0,
            'reserve_qty': 0.0,
        })
        wizard._onchange_max_reserve_qty()
        self.assertEqual(wizard.reserve_qty, 10.0)

    def test_52_wizard_confirm_reserve(self):
        """Wizard create performs the reserve."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 50.0,
        })
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]

        wizard = self.env['buz.reserve.manual.wizard'].create({
            'line_id': line.id,
            'stock_move_id': line.stock_move_id.id,
            'product_id': line.product_id.id,
            'demand_qty': line.demand_qty,
            'reserved_qty': 0.0,
            'available_qty': 50.0,
            'reserve_qty': 5.0,
        })
        result = wizard.action_confirm()
        self.assertIn('ir.actions.client', result.get('type', ''))
        total = sum(self.move_no_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, 5.0)

    def test_53_wizard_confirm_zero_raises(self):
        """Wizard with 0 qty raises ValueError."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        wizard = self.env['buz.reserve.manual.wizard'].create({
            'line_id': line.id,
            'stock_move_id': line.stock_move_id.id,
            'product_id': line.product_id.id,
            'demand_qty': line.demand_qty,
            'reserved_qty': 0.0,
            'available_qty': 50.0,
            'reserve_qty': 0,
        })
        with self.assertRaises(ValueError):
            wizard.action_confirm()

    def test_54_wizard_confirm_exceeds_max_raises(self):
        """Wizard with qty > max raises ValueError."""
        self.manager.action_load_lines()
        line = self.manager.line_ids[0]
        wizard = self.env['buz.reserve.manual.wizard'].create({
            'line_id': line.id,
            'stock_move_id': line.stock_move_id.id,
            'product_id': line.product_id.id,
            'demand_qty': line.demand_qty,
            'reserved_qty': 0.0,
            'available_qty': 50.0,
            'reserve_qty': 100.0,
        })
        with self.assertRaises(ValueError):
            wizard.action_confirm()

    # ========================================================================
    #  --- Manager – Unreserve All ---
    # ========================================================================

    def test_60_manager_unreserve_all_with_reservations(self):
        """Unreserve all works when lines have reservations."""
        self.env['stock.quant'].create({
            'product_id': self.product_b.id,
            'location_id': self.stock_location.id,
            'quantity': 50.0,
        })
        self.manager.action_load_lines()
        self.move_no_stock.action_manual_reserve(10.0)
        self.manager.line_ids._refresh_line()

        result = self.manager.action_unreserve_all()
        self.assertIn('ir.actions.client', result.get('type', ''))
        total = sum(self.move_no_stock.move_line_ids.mapped('quantity'))
        self.assertEqual(total, 0.0)