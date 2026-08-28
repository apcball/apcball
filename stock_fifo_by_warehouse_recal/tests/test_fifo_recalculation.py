# -*- coding: utf-8 -*-
"""Tests for the FIFO replay and the repair wizard built on it.

These construct valuation layers directly rather than driving stock moves: the
subject under test is the replay of a layer history, and building it by hand is
the only way to express a history that is deliberately wrong.

Run them against a scratch database, never MOG_DEV or MOG_LIVE. Odoo's
--test-enable runs against whatever -d names, and while TransactionCase rolls
back, nothing here is worth the risk of a stray commit on a live valuation
table.
"""

from odoo.tests import common, tagged
from odoo.exceptions import UserError


@tagged('post_install', '-at_install')
class TestFifoReplay(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'FIFO Replay Test Product',
            'type': 'product',
            'categ_id': cls.env.ref('product.product_category_all').id,
        })
        cls.SVL = cls.env['stock.valuation.layer']

    def _layer(self, quantity, value, **kwargs):
        """Create a layer with the remaining state it would hold when fresh."""
        vals = {
            'product_id': self.product.id,
            'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'quantity': quantity,
            'value': value,
            'unit_cost': value / quantity if quantity else 0.0,
            'remaining_qty': quantity if quantity > 0 else 0.0,
            'remaining_value': value if quantity > 0 else 0.0,
            'description': 'test',
        }
        vals.update(kwargs)
        return self.SVL.create(vals)

    def _replay(self):
        return self.SVL._fifo_replay_remaining(
            self.product.id, self.warehouse.id, self.company.id)

    # -- the replay itself ------------------------------------------------

    def test_consumes_oldest_first(self):
        first = self._layer(10, 100.0)      # 10 @ 10
        second = self._layer(10, 200.0)     # 10 @ 20
        out = self._layer(-15, -0.0)

        result = self._replay()

        # The first layer is gone, the second is down to 5 units at 20.
        self.assertEqual(result['expected'][first.id], (0.0, 0.0))
        rem_qty, rem_value = result['expected'][second.id]
        self.assertAlmostEqual(rem_qty, 5.0, places=4)
        self.assertAlmostEqual(rem_value, 100.0, places=2)
        self.assertEqual(result['expected'][out.id], (0.0, 0.0))
        # COGS: all of the cheap layer plus 5 of the dear one.
        self.assertAlmostEqual(result['cogs'][out.id], -200.0, places=2)
        self.assertFalse(result['shortage'])

    def test_landed_cost_reaches_cogs(self):
        """A landed cost layer tops up its target and the next issue pays for it."""
        incoming = self._layer(10, 100.0)
        self._layer(0, 50.0, stock_valuation_layer_id=incoming.id,
                    unit_cost=0.0)
        out = self._layer(-10, -0.0)

        result = self._replay()

        self.assertEqual(result['expected'][incoming.id], (0.0, 0.0))
        # 100 of goods + 50 of landing cost, all consumed.
        self.assertAlmostEqual(result['cogs'][out.id], -150.0, places=2)

    def test_landed_cost_after_partial_consumption(self):
        """A late landed cost only lands on what is still in the queue.

        This is why landed cost is replayed at its own create_date instead of
        being folded into the opening seed.
        """
        incoming = self._layer(10, 100.0)
        first_out = self._layer(-6, -0.0)
        self._layer(0, 40.0, stock_valuation_layer_id=incoming.id, unit_cost=0.0)
        second_out = self._layer(-4, -0.0)

        result = self._replay()

        # The first issue paid the pre-landing rate.
        self.assertAlmostEqual(result['cogs'][first_out.id], -60.0, places=2)
        # The remaining 4 units carry 40 of goods plus all 40 of landing cost.
        self.assertAlmostEqual(result['cogs'][second_out.id], -80.0, places=2)

    def test_shortage_is_reported_not_invented(self):
        self._layer(5, 50.0)
        self._layer(-8, -0.0)

        result = self._replay()

        self.assertAlmostEqual(result['shortage'], 3.0, places=4)

    def test_scope_is_per_warehouse(self):
        """Layers at another warehouse are a different queue and must not leak."""
        other = self.env['stock.warehouse'].create({
            'name': 'Replay Test WH', 'code': 'RPT',
            'company_id': self.company.id,
        })
        self._layer(10, 100.0, warehouse_id=other.id)
        here = self._layer(4, 80.0)

        result = self._replay()

        self.assertNotIn(other.id, [l.warehouse_id.id for l in self.SVL.browse(
            list(result['expected']))])
        self.assertEqual(set(result['expected']), {here.id})


@tagged('post_install', '-at_install')
class TestFifoRepairWizard(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1)
        cls.product = cls.env['product.product'].create({
            'name': 'FIFO Repair Test Product',
            'type': 'product',
            'categ_id': cls.env.ref('product.product_category_all').id,
        })
        cls.SVL = cls.env['stock.valuation.layer']

    def _layer(self, quantity, value, **kwargs):
        vals = {
            'product_id': self.product.id,
            'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'quantity': quantity,
            'value': value,
            'unit_cost': value / quantity if quantity else 0.0,
            'remaining_qty': quantity if quantity > 0 else 0.0,
            'remaining_value': value if quantity > 0 else 0.0,
        }
        vals.update(kwargs)
        return self.SVL.create(vals)

    def _wizard(self, **kwargs):
        vals = {
            'company_id': self.company.id,
            'warehouse_ids': [(6, 0, self.warehouse.ids)],
            'product_ids': [(6, 0, self.product.ids)],
            'dry_run': True,
            'max_mismatch_percent': 100.0,
        }
        vals.update(kwargs)
        return self.env['fifo.recalculation.wizard'].create(vals)

    def test_dry_run_writes_nothing(self):
        layer = self._layer(10, 100.0)
        layer.write({'remaining_qty': 99.0, 'remaining_value': 999.0})

        wizard = self._wizard()
        wizard.action_preview()

        self.assertTrue(wizard.layers_changed)
        self.assertAlmostEqual(layer.remaining_qty, 99.0, places=4)
        self.assertAlmostEqual(layer.remaining_value, 999.0, places=2)

    def test_apply_corrects_remaining_and_leaves_value_alone(self):
        layer = self._layer(10, 100.0)
        layer.write({'remaining_qty': 99.0, 'remaining_value': 999.0})

        wizard = self._wizard(dry_run=False)
        wizard.action_preview()
        wizard.action_apply()
        layer.invalidate_recordset()

        self.assertAlmostEqual(layer.remaining_qty, 10.0, places=4)
        self.assertAlmostEqual(layer.remaining_value, 100.0, places=2)
        self.assertAlmostEqual(layer.value, 100.0, places=2)
        self.assertTrue(wizard.backup_id)

    def test_rollback_restores_exactly(self):
        layer = self._layer(10, 100.0)
        layer.write({'remaining_qty': 99.0, 'remaining_value': 999.0})

        wizard = self._wizard(dry_run=False)
        wizard.action_preview()
        wizard.action_apply()
        wizard.backup_id.action_restore()
        layer.invalidate_recordset()

        self.assertAlmostEqual(layer.remaining_qty, 99.0, places=4)
        self.assertAlmostEqual(layer.remaining_value, 999.0, places=2)

    def test_apply_refused_while_dry_run(self):
        layer = self._layer(10, 100.0)
        layer.write({'remaining_qty': 99.0})

        wizard = self._wizard()
        wizard.action_preview()
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_mismatch_gate_blocks_apply(self):
        """Too much disagreement means the replay is wrong, not the data."""
        layer = self._layer(10, 100.0)
        layer.write({'remaining_qty': 99.0})

        wizard = self._wizard(dry_run=False, max_mismatch_percent=0.5)
        wizard.action_preview()

        self.assertTrue(wizard.block_reason)
        self.assertFalse(wizard.can_apply)
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_locked_layers_skip_the_whole_pair(self):
        layer = self._layer(10, 100.0)
        layer.write({'remaining_qty': 99.0, 'locked': True})

        wizard = self._wizard(dry_run=False)
        wizard.action_preview()

        self.assertEqual(wizard.layers_changed, 0)
        self.assertEqual(wizard.pairs_blocked, 1)
        layer.invalidate_recordset()
        self.assertAlmostEqual(layer.remaining_qty, 99.0, places=4)

    def test_pair_with_wrong_outgoing_value_is_skipped(self):
        """The gate that matters.

        Per product/warehouse the book is SUM(value) and the queue is
        SUM(remaining_value); the two differ by exactly COGS_stored -
        COGS_replay. So repairing remaining_value on a pair whose outgoing
        value is wrong desyncs the queue from the book by that amount — which
        is the divergence this tool exists to close.
        """
        incoming = self._layer(10, 100.0)
        outgoing = self._layer(-4, -40.0)
        incoming.write({'remaining_qty': 99.0, 'remaining_value': 999.0})
        # Corrupt the stored COGS without touching the queue.
        self.env.cr.execute(
            'UPDATE stock_valuation_layer SET value = -777.0 WHERE id = %s',
            (outgoing.id,))
        self.SVL.invalidate_model()

        wizard = self._wizard(dry_run=False)
        wizard.action_preview()

        self.assertEqual(wizard.pairs_blocked, 1)
        self.assertEqual(wizard.layers_changed, 0)
        self.assertIn('Outgoing value disagrees',
                      wizard.line_ids.skip_reason or '')
        incoming.invalidate_recordset()
        self.assertAlmostEqual(incoming.remaining_qty, 99.0, places=4)

    def test_pair_with_correct_outgoing_value_is_repaired(self):
        """Control for the test above: same shape, honest COGS, gets fixed."""
        incoming = self._layer(10, 100.0)
        self._layer(-4, -40.0)
        incoming.write({'remaining_qty': 99.0, 'remaining_value': 999.0})

        wizard = self._wizard(dry_run=False)
        wizard.action_preview()
        wizard.action_apply()
        incoming.invalidate_recordset()

        self.assertAlmostEqual(incoming.remaining_qty, 6.0, places=4)
        self.assertAlmostEqual(incoming.remaining_value, 60.0, places=2)

    def test_shortage_pair_is_skipped(self):
        incoming = self._layer(5, 50.0)
        self._layer(-8, -0.0)
        incoming.write({'remaining_qty': 5.0, 'remaining_value': 50.0})

        wizard = self._wizard(dry_run=False)
        wizard.action_preview()

        self.assertEqual(wizard.pairs_blocked, 1)
        self.assertEqual(wizard.layers_changed, 0)

    def test_warehouse_scope_is_required(self):
        with self.assertRaises(Exception):
            self.env['fifo.recalculation.wizard'].create({
                'company_id': self.company.id,
            }).action_preview()
