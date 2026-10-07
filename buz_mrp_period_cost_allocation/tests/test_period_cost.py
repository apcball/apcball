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
        stock = env['stock.location'].search(
            [('usage', '=', 'internal'), ('company_id', '=', cls.company.id)], limit=1)
        env['stock.quant']._update_available_quantity(cls.comp, stock, qty * 2)
        mo = env['mrp.production'].create({
            'product_id': product.id, 'product_qty': qty, 'bom_id': bom.id,
        })
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
