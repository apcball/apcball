from datetime import datetime

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'mrp_period_cost')
class TestMrpPeriodCost(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.env.user.groups_id = [(4, cls.env.ref(
            'buz_mrp_period_cost_allocation.group_period_cost_reverse').id)]
        cls.wc = cls.env['mrp.workcenter'].create({
            'name': 'WC Test',
            'dl_per_hour': 100.0,
            'idl_per_hour': 50.0,
            'oh_per_hour': 30.0,
        })
        cls.comp = cls._product('Comp', 10.0)
        cls.fg1 = cls._product('FG1', 0.0)
        cls.fg2 = cls._product('FG2', 0.0)
        cls.mo1 = cls._done_mo(cls.fg1, 10.0, 60)   # 60 min
        cls.mo2 = cls._done_mo(cls.fg2, 10.0, 180)  # 180 min

    @classmethod
    def _product(cls, name, cost):
        return cls.env['product.product'].create({
            'name': name,
            'type': 'product',
            'standard_price': cost,
            'list_price': cost * 3 or 50.0,
        })

    @classmethod
    def _done_mo(cls, product, qty, minutes):
        env = cls.env
        bom = env['mrp.bom'].create({
            'product_tmpl_id': product.product_tmpl_id.id,
            'product_qty': 1.0,
            'bom_line_ids': [(0, 0, {'product_id': cls.comp.id, 'product_qty': 1.0})],
            'operation_ids': [(0, 0, {'name': 'Op', 'workcenter_id': cls.wc.id,
                                      'time_cycle_manual': 10})],
        })
        mo = env['mrp.production'].create({
            'product_id': product.id, 'product_qty': qty, 'bom_id': bom.id,
        })
        stock = mo.location_src_id
        env['stock.quant']._update_available_quantity(cls.comp, stock, qty * 2)
        mo.action_confirm()
        mo.action_assign()
        wo = mo.workorder_ids[0]
        wo.button_start()
        wo.time_ids.write({
            'date_start': datetime(2026, 3, 10, 8, 0, 0),
            'date_end': datetime(2026, 3, 10, 8, 0, 0) + __import__('datetime').timedelta(minutes=minutes),
        })
        wo.button_finish()
        mo.qty_producing = qty
        mo.button_mark_done()
        mo.write({'date_finished': datetime(2026, 3, 10, 12, 0, 0)})
        return mo

    def _period(self, **kw):
        vals = {
            'date_from': '2026-03-01', 'date_to': '2026-03-31',
            'allocation_base': 'time',
            'actual_dl': 1000.0, 'actual_idl': 500.0, 'actual_oh': 300.0,
        }
        vals.update(kw)
        return self.env['mrp.period.cost'].create(vals)

    def _loaded(self, **kw):
        p = self._period(**kw)
        p.action_load_mos()
        return p

    # ---- basics -------------------------------------------------------
    def test_sequence(self):
        self.assertRegex(self._period().name, r'^MPC/\d{4}/\d{5}$')

    def test_load_mos_std_costs(self):
        p = self._loaded()
        lines = p.line_ids.filtered(lambda l: l.mo_id in (self.mo1 | self.mo2))
        self.assertEqual(len(lines), 2)
        l1 = lines.filtered(lambda l: l.mo_id == self.mo1)
        l2 = lines.filtered(lambda l: l.mo_id == self.mo2)
        self.assertAlmostEqual(l1.total_duration, 60.0, 2)
        self.assertAlmostEqual(l1.standard_dl, 100.0, 2)
        self.assertAlmostEqual(l1.standard_idl, 50.0, 2)
        self.assertAlmostEqual(l1.standard_oh, 30.0, 2)
        self.assertAlmostEqual(l2.standard_dl, 300.0, 2)
        self.assertGreater(l1.standard_material, 0)
        self.assertAlmostEqual(
            p.total_std_dl, sum(p.line_ids.mapped('standard_dl')), 2)

    def test_load_without_period_fails(self):
        p = self._period()
        p.date_from = False if False else p.date_from
        p2 = self.env['mrp.period.cost'].new({})
        with self.assertRaises(UserError):
            p2.action_load_mos()

    def test_load_excludes_outside_period(self):
        p = self._loaded(date_from='2026-04-01', date_to='2026-04-30')
        self.assertFalse(p.line_ids.filtered(lambda l: l.mo_id in (self.mo1 | self.mo2)))

    def test_preview_requires_lines(self):
        with self.assertRaises(UserError):
            self._period().action_preview_allocation()

    # ---- allocation ---------------------------------------------------
    def _assert_alloc_sums(self, p):
        self.assertAlmostEqual(sum(p.line_ids.mapped('allocation_weight')), 100.0, 2)
        self.assertAlmostEqual(sum(p.line_ids.mapped('allocated_dl')), p.diff_dl, 2)
        self.assertAlmostEqual(sum(p.line_ids.mapped('allocated_idl')), p.diff_idl, 2)
        self.assertAlmostEqual(sum(p.line_ids.mapped('allocated_oh')), p.diff_oh, 2)

    def test_allocation_time(self):
        p = self._loaded(allocation_base='time')
        p.action_preview_allocation()
        self._assert_alloc_sums(p)
        w = {l.mo_id: l.allocation_weight for l in p.line_ids}
        self.assertAlmostEqual(w[self.mo1] / w[self.mo2], 60.0 / 180.0, 3)

    def test_allocation_standard_cost(self):
        p = self._loaded(allocation_base='standard_cost')
        p.action_preview_allocation()
        self._assert_alloc_sums(p)

    def test_allocation_sale_price(self):
        p = self._loaded(allocation_base='sale_price')
        p.action_preview_allocation()
        self._assert_alloc_sums(p)

    def test_allocation_manual(self):
        p = self._loaded(allocation_base='manual')
        l1 = p.line_ids.filtered(lambda l: l.mo_id == self.mo1)
        l2 = p.line_ids.filtered(lambda l: l.mo_id == self.mo2)
        (p.line_ids - l1 - l2).write({'manual_cost': 0.0})
        l1.manual_cost = 100.0
        l2.manual_cost = 300.0
        p.action_preview_allocation()
        self._assert_alloc_sums(p)
        self.assertAlmostEqual(l1.allocation_weight, 25.0, 2)

    def test_allocation_zero_base_no_crash(self):
        p = self._loaded(allocation_base='manual')
        p.action_preview_allocation()
        self.assertFalse(any(p.line_ids.mapped('allocated_dl')))

    def test_inventory_split_adds_up(self):
        p = self._loaded()
        p.action_preview_allocation()
        for l in p.line_ids:
            self.assertAlmostEqual(
                l.allocated_inventory_total + l.allocated_period_expense,
                l.allocated_dl + l.allocated_idl + l.allocated_oh, 2)
            self.assertLessEqual(l.qty_on_hand, l.quantity_produced)

    # ---- posting ------------------------------------------------------
    def _svls(self, p):
        return self.env['stock.valuation.layer'].search([
            ('description', 'like', 'Period Cost Allocation: %s' % p.name)])

    def test_post_requires_lines(self):
        with self.assertRaises(UserError):
            self._period().action_post()

    def test_post_requires_accounts_when_accounting(self):
        p = self._loaded(inventory_only=False)
        p.action_preview_allocation()
        with self.assertRaises(UserError):
            p.action_post()

    def test_post_creates_svl_total_matches(self):
        p = self._loaded()
        p.action_preview_allocation()
        p.action_post()
        self.assertEqual(p.state, 'posted')
        svls = self._svls(p)
        self.assertTrue(svls)
        self.assertTrue(all(s.quantity == 0 for s in svls))
        total = sum(p.line_ids.mapped('allocated_inventory_total'))
        self.assertAlmostEqual(sum(svls.mapped('value')), total, 2)

    def test_post_twice_blocked(self):
        p = self._loaded()
        p.action_preview_allocation()
        p.action_post()
        with self.assertRaises(UserError):
            p.action_post()

    def test_cancel_posted_blocked(self):
        """cancelling a posted record must be blocked or reverse SVLs."""
        p = self._loaded()
        p.action_preview_allocation()
        p.action_post()
        with self.assertRaises(UserError):
            p.action_cancel()

    def test_unlink_posted_blocked(self):
        """deleting a posted record leaves orphan SVLs."""
        p = self._loaded()
        p.action_preview_allocation()
        p.action_post()
        with self.assertRaises(UserError):
            p.unlink()

    def test_overlap_blocked(self):
        """#2 same MO in two overlapping periods must be rejected."""
        p1 = self._loaded()
        p1.action_preview_allocation()
        p1.action_post()
        p2 = self._period()
        with self.assertRaises(ValidationError):
            p2.action_load_mos()

    def test_date_range_validated(self):
        """#3 date_from > date_to must be rejected."""
        with self.assertRaises(ValidationError):
            self._period(date_from='2026-03-31', date_to='2026-03-01')

    def test_cancelled_period_frees_mo(self):
        p1 = self._loaded()
        p1.action_cancel()
        p2 = self._loaded()
        self.assertIn(self.mo1, p2.line_ids.mo_id)
        with self.assertRaises(ValidationError):
            p1.action_draft()

    def test_cancel_and_unlink_draft_allowed(self):
        p = self._period()
        p.action_cancel()
        self.assertEqual(p.state, 'cancel')
        p.action_draft()
        p.unlink()
        self.assertFalse(p.exists())

    def test_mo_on_date_to_included(self):
        """MO finished on date_to afternoon is included (Odoo expands Date to end of day)."""
        p = self._loaded(date_from='2026-03-10', date_to='2026-03-10')
        self.assertIn(self.mo1, p.line_ids.mo_id)

    def test_post_only_capitalises_inventory_share(self):
        p = self._loaded()
        p.action_preview_allocation()
        # simulate goods already sold: nothing left in inventory
        p.line_ids.write({'allocated_inventory_total': 0.0, 'allocated_period_expense': 1.0})
        p.action_post()
        self.assertFalse(self._svls(p))

    def test_post_updates_origin_remaining_value(self):
        p = self._loaded()
        p.action_preview_allocation()
        base = p.line_ids.mo_id.move_finished_ids.stock_valuation_layer_ids.filtered(
            lambda l: l.quantity > 0)
        before = sum(base.mapped('remaining_value'))
        p.action_post()
        base.invalidate_recordset()
        svls = self._svls(p)
        self.assertTrue(svls)
        self.assertAlmostEqual(
            sum(base.mapped('remaining_value')) - before, sum(svls.mapped('value')), 2)
        self.assertTrue(all(s.stock_valuation_layer_id for s in svls))

    def test_post_dates_use_period_end(self):
        p = self._posted()
        svls = self._svls(p)
        if 'accounting_date' not in svls._fields:
            self.skipTest("accounting_date not installed")
        self.assertTrue(all(s.accounting_date.date() == p.date_to for s in svls))

    def test_adjustment_date_defaults_to_date_to(self):
        p = self._period()
        self.assertEqual(p.adjustment_date, p.date_to)

    def test_adjustment_date_not_before_date_from(self):
        with self.assertRaises(ValidationError):
            self._period(adjustment_date='2026-02-28')

    def test_post_uses_adjustment_date(self):
        p = self._loaded(adjustment_date='2026-04-15')
        p.action_preview_allocation()
        p.action_post()
        svls = self._svls(p)
        self.assertTrue(svls)
        if 'accounting_date' in svls._fields:
            self.assertTrue(all(s.accounting_date.date().isoformat() == '2026-04-15' for s in svls))

    def test_lock_date_warning_only_warns(self):
        p = self._loaded(adjustment_date='2026-03-31')
        self.assertFalse(p._lock_date_warning())
        self.company.sudo().tax_lock_date = '2026-03-31'
        self.assertIn('2026-03-31', p._lock_date_warning())
        wizard = self.env['mrp.period.cost.post.wizard'].create({'period_id': p.id})
        self.assertIn('locked', wizard.warning_text)
        wizard.confirm_checked = True
        wizard.action_confirm()   # warn only: inventory-only post still goes through
        self.assertEqual(p.state, 'posted')

    def _simulate_transfer(self, p):
        """Base layers' stock moves to a position layer (like an inter-warehouse transfer)."""
        Layer = self.env['stock.valuation.layer']
        if 'origin_valuation_layer_id' not in Layer._fields:
            self.skipTest("stock_fifo_by_location not installed")
        base = self._base_layers(p)
        positions = Layer
        for b in base:
            vals = {
                'company_id': b.company_id.id, 'product_id': b.product_id.id,
                'quantity': b.remaining_qty, 'value': b.remaining_value,
                'remaining_qty': b.remaining_qty, 'remaining_value': b.remaining_value,
                'origin_valuation_layer_id': b.id, 'description': 'test transfer',
            }
            if 'warehouse_id' in Layer._fields:
                vals['warehouse_id'] = self.env['stock.warehouse'].search([], limit=1).id
            positions |= Layer.create(vals)
            out_vals = {
                'company_id': b.company_id.id, 'product_id': b.product_id.id,
                'quantity': -b.remaining_qty, 'value': -b.remaining_value,
                'description': 'test transfer out',
            }
            if 'warehouse_id' in Layer._fields:
                out_vals['warehouse_id'] = b.warehouse_id.id
            Layer.create(out_vals)
            b.write({'remaining_qty': 0.0, 'remaining_value': 0.0})
        return base, positions

    def test_transferred_stock_still_gets_variance(self):
        p = self._loaded()
        base, positions = self._simulate_transfer(p)
        p.action_preview_allocation()
        for line in p.line_ids:
            self.assertAlmostEqual(line.qty_on_hand, line.quantity_produced, 2)
            self.assertAlmostEqual(line.allocated_period_expense, 0.0, 2)
        before = sum(positions.mapped('remaining_value'))
        p.action_post()
        total = sum(p.line_ids.mapped('allocated_inventory_total'))
        self.assertAlmostEqual(sum(self._svls(p).mapped('value')), total, 2)
        self.assertAlmostEqual(sum(positions.mapped('remaining_value')) - before, total, 2)
        if 'origin_remaining_value' in base._fields:
            self.assertTrue(all(b.origin_remaining_value for b in base))

    def test_fifo_replay_agrees_after_post(self):
        """The recalculation wizard replays qty-0 layers per warehouse; it must not undo our uplift."""
        p = self._loaded()
        base, positions = self._simulate_transfer(p)
        p.action_preview_allocation()
        p.action_post()
        Layer = self.env['stock.valuation.layer']
        self.env.flush_all()
        for adj in self._svls(p):
            self.assertEqual(adj.warehouse_id, adj.stock_valuation_layer_id.warehouse_id)
        for product in p.line_ids.product_id:
            for wh in (base | positions).mapped('warehouse_id'):
                result = Layer._fifo_replay_remaining(product.id, wh.id, self.company.id)
                for layer in Layer.browse(list(result['expected'])):
                    qty, value = result['expected'][layer.id]
                    self.assertAlmostEqual(layer.remaining_value, value, 2, "layer %s" % layer.id)

    def test_reverse_after_transfer_restores_values(self):
        p = self._loaded()
        base, positions = self._simulate_transfer(p)
        p.action_preview_allocation()
        before = sum(positions.mapped('remaining_value'))
        origin_before = sum(base.mapped('origin_remaining_value')) if 'origin_remaining_value' in base._fields else 0
        p.action_post()
        p.action_reverse_to_draft('undo')
        self.assertAlmostEqual(sum(positions.mapped('remaining_value')), before, 2)
        if 'origin_remaining_value' in base._fields:
            self.assertAlmostEqual(sum(base.mapped('origin_remaining_value')), origin_before, 2)

    # ---- reverse & reset to draft ---------------------------------------
    def _posted(self):
        p = self._loaded()
        p.action_preview_allocation()
        p.action_post()
        return p

    def _base_layers(self, p):
        return p.line_ids.mo_id.move_finished_ids.stock_valuation_layer_ids.filtered(
            lambda l: l.quantity > 0)

    def test_reverse_restores_valuation_and_draft(self):
        p = self._loaded()
        p.action_preview_allocation()
        base = self._base_layers(p)
        before = sum(base.mapped('remaining_value'))
        p.action_post()
        self.assertNotAlmostEqual(sum(base.mapped('remaining_value')), before, 2)
        p.action_reverse_to_draft('wrong actual cost')
        self.assertEqual(p.state, 'draft')
        self.assertAlmostEqual(sum(base.mapped('remaining_value')), before, 2)
        self.assertAlmostEqual(sum(self._svls(p).mapped('value')), 0.0, 2)
        self.assertTrue(p.message_ids.filtered(lambda m: 'wrong actual cost' in (m.body or '')))

    def test_reverse_then_repost(self):
        p = self._posted()
        p.action_reverse_to_draft('fix numbers')
        p.actual_dl = 2000.0
        p.action_preview_allocation()
        p.action_post()
        self.assertEqual(p.state, 'posted')
        expected = sum(p.line_ids.mapped('allocated_inventory_total'))
        self.assertAlmostEqual(sum(self._svls(p).mapped('value')), expected, 2)
        # a second reversal only touches the new allocations
        p.action_reverse_to_draft('again')
        self.assertAlmostEqual(sum(self._svls(p).mapped('value')), 0.0, 2)

    def test_reverse_blocked_when_stock_sold(self):
        p = self._posted()
        base = self._base_layers(p)[:1]
        base.remaining_qty = base.remaining_qty - 1.0   # simulate a sale
        with self.assertRaises(UserError):
            p.action_reverse_to_draft('too late')
        self.assertEqual(p.state, 'posted')
        self.assertTrue(self._svls(p))

    def test_reverse_requires_reason_and_posted(self):
        p = self._posted()
        with self.assertRaises(UserError):
            p.action_reverse_to_draft('   ')
        with self.assertRaises(UserError):
            self._period().action_reverse_to_draft('not posted')

    def test_reverse_requires_reverse_group(self):
        p = self._posted()
        user = self.env['res.users'].create({
            'name': 'MRP only', 'login': 'mrp_only_mpc',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('mrp.group_mrp_manager').id])],
        })
        group = self.env.ref('buz_mrp_period_cost_allocation.group_period_cost_reverse')
        self.assertFalse(user.has_group('buz_mrp_period_cost_allocation.group_period_cost_reverse'))
        with self.assertRaises(UserError):
            p.with_user(user).action_reverse_to_draft('no rights')
        self.assertEqual(p.state, 'posted')
        # with the group (and nothing on valuation layers) it works
        user.groups_id = [(4, group.id)]
        p.with_user(user).action_reverse_to_draft('allowed')
        self.assertEqual(p.state, 'draft')
        self.assertFalse(any(self._svls(p).mapped('value')) and
                         sum(self._svls(p).mapped('value')))

    def test_wizard_access_for_group(self):
        group = self.env.ref('buz_mrp_period_cost_allocation.group_period_cost_reverse')
        user = self.env['res.users'].create({
            'name': 'Reverser', 'login': 'mpc_reverser',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('mrp.group_mrp_manager').id, group.id])],
        })
        p = self._posted()
        wiz = self.env['mrp.period.cost.reverse.wizard'].with_user(user).create(
            {'period_id': p.id, 'reason': 'wizard access'})
        wiz.action_confirm()
        self.assertEqual(p.state, 'draft')

    def test_reverse_wizard(self):
        p = self._posted()
        self.env['mrp.period.cost.reverse.wizard'].create(
            {'period_id': p.id, 'reason': 'via wizard'}).action_confirm()
        self.assertEqual(p.state, 'draft')

    def test_reverse_blocked_for_untracked_legacy_post(self):
        p = self._posted()
        self.env['mrp.period.cost.alloc'].search([('period_id', '=', p.id)]).unlink()
        with self.assertRaises(UserError):
            p.action_reverse_to_draft('legacy')
        self.assertEqual(p.state, 'posted')
        self.assertTrue(self._svls(p))

    def test_menu_visible_only_to_group(self):
        group = self.env.ref('buz_mrp_period_cost_allocation.group_period_cost_reverse')
        menu = self.env.ref('buz_mrp_period_cost_allocation.menu_mrp_period_cost')
        self.assertEqual(menu.groups_id, group)

    # ---- post confirmation wizard ----------------------------------------
    def _post_wizard(self, p):
        action = p.action_post_wizard()
        self.assertEqual(action['res_model'], 'mrp.period.cost.post.wizard')
        return self.env['mrp.period.cost.post.wizard'].browse(action['res_id'])

    def test_post_wizard_refreshes_preview_and_summarises(self):
        p = self._loaded()          # not previewed yet
        wiz = self._post_wizard(p)
        self.assertEqual(wiz.line_count, len(p.line_ids))
        self.assertAlmostEqual(wiz.total_inventory,
                               sum(p.line_ids.mapped('allocated_inventory_total')), 2)
        self.assertAlmostEqual(wiz.total_variance, p.diff_dl + p.diff_idl + p.diff_oh, 2)
        self.assertEqual(p.state, 'draft')

    def test_post_wizard_requires_tick(self):
        p = self._loaded()
        wiz = self._post_wizard(p)
        with self.assertRaises(UserError):
            wiz.action_confirm()
        self.assertEqual(p.state, 'draft')
        wiz.confirm_checked = True
        wiz.action_confirm()
        self.assertEqual(p.state, 'posted')

    def test_post_wizard_warns_when_nothing_in_stock(self):
        p = self._loaded()
        wiz = self._post_wizard(p)
        wiz.period_id.line_ids.write({'allocated_inventory_total': 0.0})
        wiz.invalidate_recordset()
        self.assertTrue(wiz.warning_text)

    def test_post_wizard_only_for_draft(self):
        p = self._posted()
        with self.assertRaises(UserError):
            p.action_post_wizard()
