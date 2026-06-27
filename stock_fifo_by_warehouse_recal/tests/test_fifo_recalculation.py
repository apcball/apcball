# -*- coding: utf-8 -*-
"""
Tests for stock_fifo_by_warehouse_recal module.

Covers:
- Module loading and basic model registration
- Warehouse assignment logic (_get_move_warehouse)
- IWT cost propagation in _classify_move_and_get_cost (preview path)
- Cost_cache mechanism for apply phase
- _build_cost_cache correctness
"""

from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError

@tagged('post_install', '-at_install')
class TestModuleStructure(TransactionCase):
    """Module loads without duplicate-model crash."""

    def test_models_registered(self):
        """All expected models exist in the registry."""
        models = [
            'fifo.recalculation.wizard',
            'fifo.recalculation.wizard.line',
            'fifo.recalculation.backup',
            'fifo.recalculation.backup.line',
            'fifo.recalculation.config',
        ]
        for name in models:
            self.assertIn(name, self.env, f'Model {name} not registered')

    def test_wizard_core_fields(self):
        """Wizard has required fields for operation."""
        Wizard = self.env['fifo.recalculation.wizard']
        for field in ('date_from', 'date_to', 'company_id', 'warehouse_ids',
                      'clear_old_layers', 'dry_run', 'lock_after_recal',
                      'batch_size', 'state', 'line_ids', 'backup_id',
                      'log_text', 'progress_percent', 'progress_message'):
            self.assertTrue(hasattr(Wizard, field), f'Missing field: {field}')

    def test_backup_model_fields(self):
        """Backup model has restore action."""
        Backup = self.env['fifo.recalculation.backup']
        self.assertTrue(hasattr(Backup, 'action_restore'))
        self.assertTrue(hasattr(Backup, 'line_ids'))

    def test_config_model_fields(self):
        """Config model has scheduled-action fields."""
        Config = self.env['fifo.recalculation.config']
        for field in ('name', 'active', 'is_default', 'date_from', 'date_to',
                      'warehouse_ids', 'product_ids', 'batch_size',
                      'auto_apply', 'notification_user_ids'):
            self.assertTrue(hasattr(Config, field), f'Missing config field: {field}')


@tagged('post_install', '-at_install')
class TestWarehouseAssignment(TransactionCase):
    """_get_move_warehouse correctly determines warehouse for different move types."""

    def setUp(self):
        super().setUp()
        self.warehouse_a = self.env['stock.warehouse'].create({
            'name': 'Test WH A',
            'code': 'TWA',
            'company_id': self.env.company.id,
        })
        self.warehouse_b = self.env['stock.warehouse'].create({
            'name': 'Test WH B',
            'code': 'TWB',
            'company_id': self.env.company.id,
        })
        # Find an actual transit location on the DB (may be created by stock_fifo_by_location routes)
        self.transit_loc = self.env['stock.location'].search([
            ('usage', '=', 'transit'),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        self.supplier = self.env.ref('stock.stock_location_suppliers')
        self.customer = self.env.ref('stock.stock_location_customers')
        self.Wizard = self.env['fifo.recalculation.wizard']

    def _make_move(self, src, dest):
        """Create a simple done stock move."""
        move = self.env['stock.move'].create({
            'name': 'Test move',
            'product_id': self.env['product.product'].create({
                'name': 'Test Product',
                'type': 'product',
                'categ_id': self.env.ref('product.product_category_all').id,
            }).id,
            'product_uom_qty': 1.0,
            'product_uom': self.env.ref('uom.product_uom_unit').id,
            'location_id': src.id,
            'location_dest_id': dest.id,
        })
        move.state = 'done'
        move.date = fields.Datetime.now()
        return move

    def test_supplier_to_internal_uses_dest(self):
        """Supplier → Internal: use destination warehouse."""
        move = self._make_move(self.supplier, self.warehouse_a.lot_stock_id)
        wh = self.Wizard._get_move_warehouse(move)
        self.assertTrue(wh, 'Should return a warehouse')
        self.assertEqual(wh.id, move.location_dest_id.warehouse_id.id)
    
    def test_internal_to_customer_uses_source(self):
        """Internal → Customer: use source warehouse."""
        move = self._make_move(self.warehouse_a.lot_stock_id, self.customer)
        wh = self.Wizard._get_move_warehouse(move)
        self.assertTrue(wh, 'Should return a warehouse')
        self.assertEqual(wh.id, move.location_id.warehouse_id.id)
    
    def test_same_warehouse_internal_returns_none(self):
        """Internal → Internal (same WH): returns None (no new layer)."""
        move = self._make_move(
            self.warehouse_a.lot_stock_id,
            self.warehouse_a.lot_stock_id,
        )
        wh = self.Wizard._get_move_warehouse(move)
        self.assertIsNone(wh)
    
    def test_internal_to_transit_uses_source(self):
        """Internal → Transit: use source warehouse (IWT shipment)."""
        if not self.transit_loc:
            self.skipTest('No transit location found on this DB')
        move = self._make_move(self.warehouse_a.lot_stock_id, self.transit_loc)
        wh = self.Wizard._get_move_warehouse(move)
        self.assertTrue(wh, 'Should return a warehouse')
        self.assertEqual(wh.id, move.location_id.warehouse_id.id)
    
    def test_transit_to_internal_uses_dest(self):
        """Transit → Internal: use destination warehouse (IWT receipt)."""
        if not self.transit_loc:
            self.skipTest('No transit location found on this DB')
        move = self._make_move(self.transit_loc, self.warehouse_b.lot_stock_id)
        wh = self.Wizard._get_move_warehouse(move)
        self.assertTrue(wh, 'Should return a warehouse')
        self.assertEqual(wh.id, move.location_dest_id.warehouse_id.id)


@tagged('post_install', '-at_install')
class TestIWTCostPropagation(TransactionCase):
    """IWT receipt cost is correctly calculated from shipment move's SVL.
    
    Tests P1 fixes using direct SVL creation — no move processing dependencies
    (stock accounts, button_validate, parent-module timing). Creates SVLs
    directly as the parent would, then tests the recal module's logic.
    """
    
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.warehouse_a = self.env['stock.warehouse'].create({
            'name': 'Test WH A', 'code': 'TWA', 'company_id': self.company.id,
        })
        self.warehouse_b = self.env['stock.warehouse'].create({
            'name': 'Test WH B', 'code': 'TWB', 'company_id': self.company.id,
        })
        self.product = self.env['product.product'].create({
            'name': 'IWT Test Product',
            'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id,
            'standard_price': 100.0,
        })
        self.uom_unit = self.env.ref('uom.product_uom_unit')
        self.Wizard = self.env['fifo.recalculation.wizard']
        self.SVL = self.env['stock.valuation.layer']
    
    def _make_iwt_receipt_move(self):
        """Create a minimal IWT receipt move (state='done', no processing)."""
        return self.env['stock.move'].create({
            'name': 'IWT A→B',
            'product_id': self.product.id,
            'product_uom_qty': 6.0,
            'product_uom': self.uom_unit.id,
            'location_id': self.warehouse_a.lot_stock_id.id,
            'location_dest_id': self.warehouse_b.lot_stock_id.id,
            'state': 'done',
        })
    
    def test_iwt_receipt_uses_own_svl(self):
        """Direct internal→internal IWT: _classify_move_and_get_cost reads the
        move's own negative SVL (Priority 1) for correct cost."""
        move = self._make_iwt_receipt_move()
        # Create the negative SVL at source WH (as parent would for direct IWT)
        self.SVL.create({
            'stock_move_id': move.id,
            'product_id': self.product.id,
            'warehouse_id': self.warehouse_a.id,
            'quantity': -6.0,
            'unit_cost': 50.0,
            'value': -300.0,
            'remaining_qty': 0.0,
            'company_id': self.company.id,
        })
        wizard = self.Wizard.create({
            'date_from': '2020-01-01', 'date_to': '2030-12-31',
            'company_id': self.company.id, 'dry_run': True,
        })
        mt, qty, uc, val = wizard._classify_move_and_get_cost(move, self.warehouse_b.id)
        self.assertEqual(mt, 'in', 'IWT receipt should be classified "in"')
        self.assertEqual(uc, 50.0, f'Cost should be 50 (from own SVL), got {uc}')
    def test_iwt_receipt_no_svl_falls_back_to_standard_price(self):
        """When no negative SVL exists, falls back to product.standard_price."""
        move = self._make_iwt_receipt_move()
        # No SVL created for this move
        wizard = self.Wizard.create({
            'date_from': '2020-01-01', 'date_to': '2030-12-31',
            'company_id': self.company.id, 'dry_run': True,
        })
        mt, qty, uc, val = wizard._classify_move_and_get_cost(move, self.warehouse_b.id)
        self.assertEqual(mt, 'in', 'IWT receipt should be "in"')
        self.assertEqual(uc, 100.0, 'Should fall back to standard_price (100)')
    
    def test_cost_cache_overrides_svl_search(self):
        """With cost_cache provided, _classify_move_and_get_cost returns cached cost."""
        move = self._make_iwt_receipt_move()
        wizard = self.Wizard.create({
            'date_from': '2020-01-01', 'date_to': '2030-12-31',
            'company_id': self.company.id, 'dry_run': True,
        })
        mt, qty, uc, val = wizard._classify_move_and_get_cost(
            move, self.warehouse_b.id, cost_cache={move.id: 75.0}
        )
        self.assertEqual(mt, 'in', 'IWT receipt should be "in"')
        self.assertEqual(uc, 75.0, 'Should use cached cost 75.0, not SVL search')
    
    def test_build_cost_cache_populates_from_existing_svls(self):
        """_build_cost_cache caches costs from existing SVLs before deletion."""
        move = self._make_iwt_receipt_move()
        self.SVL.create({
            'stock_move_id': move.id,
            'product_id': self.product.id,
            'warehouse_id': self.warehouse_a.id,
            'quantity': -6.0,
            'unit_cost': 50.0,
            'value': -300.0,
            'remaining_qty': 0.0,
            'company_id': self.company.id,
        })
        wizard = self.Wizard.create({
            'date_from': '2020-01-01', 'date_to': '2030-12-31',
            'company_id': self.company.id, 'dry_run': True,
        })
        groups = {(self.product.id, self.warehouse_b.id): [move]}
        cache = wizard._build_cost_cache(groups)
        self.assertIn(move.id, cache, 'Cache should contain the IWT move')
        self.assertEqual(cache[move.id], 50.0,
                         f'Cached cost should be 50, got {cache.get(move.id)}')
    
    def test_full_apply_rebuilds_svls_with_correct_cost(self):
        """End-to-end: delete old SVLs, recreate using cost_cache → cost preserved."""
        move = self._make_iwt_receipt_move()
        # Create both SVLs (negative at source, positive at dest) as parent does
        self.SVL.create({
            'stock_move_id': move.id,
            'product_id': self.product.id,
            'warehouse_id': self.warehouse_a.id,
            'quantity': -6.0,
            'unit_cost': 50.0,
            'value': -300.0,
            'remaining_qty': 0.0,
            'company_id': self.company.id,
        })
        pos_svl_before = self.SVL.create({
            'stock_move_id': move.id,
            'product_id': self.product.id,
            'warehouse_id': self.warehouse_b.id,
            'quantity': 6.0,
            'unit_cost': 50.0,
            'value': 300.0,
            'remaining_qty': 6.0,
            'remaining_value': 300.0,
            'company_id': self.company.id,
        })
        wizard = self.Wizard.create({
            'date_from': '2020-01-01', 'date_to': '2030-12-31',
            'company_id': self.company.id, 'dry_run': False,
            'clear_old_layers': 'range',
        })
        # Run preview to populate line_ids
        _ = wizard.action_preview()
        self.assertEqual(wizard.state, 'preview',
                         f'Preview should succeed, got state={wizard.state}')
        # Build groups for _delete_old_layers + _recreate_layers_for_groups
        group_key = (self.product.id, self.warehouse_b.id)
        groups = {group_key: [move]}
        log = []
        # Delete old layers for this group
        deleted = wizard._delete_old_layers([group_key], log)
        self.assertGreater(deleted, 0, 'Should delete at least the positive SVL')
        # Verify the old SVL is gone
        self.assertFalse(pos_svl_before.exists(),
                         'Old positive SVL should be deleted')
        # Build cost cache and recreate
        cost_cache = wizard._build_cost_cache(groups)
        created = wizard._recreate_layers_for_groups(groups, log, cost_cache=cost_cache)
        self.assertGreater(created, 0, 'Should recreate layers')
        # Verify recreated positive SVL at WH-B has correct cost
        pos_svls_after = self.SVL.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_b.id),
            ('quantity', '>', 0),
        ])
        self.assertTrue(pos_svls_after, 'Recreated position SVLs should exist')
        for svl in pos_svls_after:
            self.assertEqual(
                svl.unit_cost, 50.0,
                f'Recreated SVL cost should be 50 (cached from original), got {svl.unit_cost}'
            )


@tagged('post_install', '-at_install')
class TestDateValidation(TransactionCase):
    """Wizard date validation works correctly."""

    def test_date_from_before_date_to_passes(self):
        """date_from <= date_to should not raise."""
        wizard = self.env['fifo.recalculation.wizard'].create({
            'date_from': '2026-01-01 00:00:00',
            'date_to': '2026-01-31 23:59:59',
        })
        # No exception
        self.assertTrue(wizard)

    def test_date_from_after_date_to_raises(self):
        """date_from > date_to should raise UserError."""
        with self.assertRaises(UserError):
            self.env['fifo.recalculation.wizard'].create({
                'date_from': '2026-02-01 00:00:00',
                'date_to': '2026-01-31 23:59:59',
            })

    def test_batch_size_minimum(self):
        """batch_size < 1 should raise."""
        with self.assertRaises(UserError):
            self.env['fifo.recalculation.wizard'].create({
                'date_from': '2026-01-01 00:00:00',
                'date_to': '2026-01-31 23:59:59',
                'batch_size': 0,
            })

    def test_batch_size_maximum(self):
        """batch_size > 1000 should raise."""
        with self.assertRaises(UserError):
            self.env['fifo.recalculation.wizard'].create({
                'date_from': '2026-01-01 00:00:00',
                'date_to': '2026-01-31 23:59:59',
                'batch_size': 1001,
            })
