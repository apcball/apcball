# -*- coding: utf-8 -*-
"""
Tests for: Receipt → Full Transfer → Apply Landed Cost on Receipt.

Bug: "You cannot apply landed costs on the chosen Transfers(s).
     Landed costs can only be applied for products with FIFO or average costing method."

Root cause: After transfer, receipt layer has remaining_qty=0 (consumed by _run_fifo).
            get_valuation_lines() filtered out the move because no layer had remaining_qty > 0.
            Fix: use origin_remaining_qty to detect that goods still exist (Transfer ≠ Consumption).

These tests use real_time valuation to exercise get_valuation_lines() properly.
"""

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


def _get_stock_account_properties(env):
    """Return or create the stock journal + stock input/output accounts for real_time tests."""
    journal = env['account.journal'].search([
        ('company_id', '=', env.company.id),
        ('type', '=', 'general'),
    ], limit=1)
    if not journal:
        journal = env['account.journal'].create({
            'name': 'Stock Journal',
            'code': 'STK',
            'type': 'general',
            'company_id': env.company.id,
        })

    account_model = env['account.account']
    # Odoo 17 uses account_type field directly (no need for xml id refs)

    stock_input = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.input.test'),
    ], limit=1)
    if not stock_input:
        stock_input = account_model.create({
            'name': 'Stock Input Test',
            'code': 'stock.input.test',
            'account_type': 'liability_current',
            'company_id': env.company.id,
        })

    stock_output = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.output.test'),
    ], limit=1)
    if not stock_output:
        stock_output = account_model.create({
            'name': 'Stock Output Test',
            'code': 'stock.output.test',
            'account_type': 'asset_current',
            'company_id': env.company.id,
        })

    stock_valuation = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.val.test'),
    ], limit=1)
    if not stock_valuation:
        stock_valuation = account_model.create({
            'name': 'Stock Valuation Test',
            'code': 'stock.val.test',
            'account_type': 'asset_current',
            'company_id': env.company.id,
        })

    expense = account_model.search([
        ('company_id', '=', env.company.id),
        ('code', '=', 'stock.exp.test'),
    ], limit=1)
    if not expense:
        expense = account_model.create({
            'name': 'Stock Expense Test',
            'code': 'stock.exp.test',
            'account_type': 'expense',
            'company_id': env.company.id,
        })

    return {
        'journal': journal,
        'stock_input': stock_input,
        'stock_output': stock_output,
        'stock_valuation': stock_valuation,
        'expense': expense,
    }


@tagged('post_install', '-at_install')
class TestLandedCostAfterTransfer(TransactionCase):
    """Test landed cost on receipt after goods have been fully transferred to another warehouse."""

    def setUp(self):
        super().setUp()
        self.layer_model = self.env['stock.valuation.layer']
        self.landed_cost_model = self.env['stock.landed.cost']
        self.landed_cost_line_model = self.env['stock.landed.cost.lines']
        self.val_adj_line_model = self.env['stock.valuation.adjustment.lines']
        self.company = self.env.company

        # ── Stock accounts for real_time valuation ──
        accounts = _get_stock_account_properties(self.env)

        self.product_category = self.env['product.category'].create({
            'name': 'Test LC After Transfer',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
            'property_stock_account_input_categ_id': accounts['stock_input'].id,
            'property_stock_account_output_categ_id': accounts['stock_output'].id,
            'property_stock_valuation_account_id': accounts['stock_valuation'].id,
            'property_stock_journal': accounts['journal'].id,
        })

        self.product = self.env['product.product'].create({
            'name': 'Test LC Transfer Product',
            'type': 'product',
            'categ_id': self.product_category.id,
            'standard_price': 100.0,
        })

        self.warehouse_1 = self.env['stock.warehouse'].search(
            [('company_id', '=', self.company.id)], limit=1
        )
        self.warehouse_2 = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company.id),
            ('id', '!=', self.warehouse_1.id),
        ], limit=1)
        if not self.warehouse_2:
            self.warehouse_2 = self.env['stock.warehouse'].create({
                'name': 'LC Test WH2',
                'code': 'LCW2',
                'company_id': self.company.id,
            })
        self.warehouse_3 = self.env['stock.warehouse'].search([
            ('company_id', '=', self.company.id),
            ('id', 'not in', [self.warehouse_1.id, self.warehouse_2.id]),
        ], limit=1)
        if not self.warehouse_3:
            self.warehouse_3 = self.env['stock.warehouse'].create({
                'name': 'LC Test WH3',
                'code': 'LCW3',
                'company_id': self.company.id,
            })

        self.supplier_location = self.env.ref('stock.stock_location_suppliers')
        self.customer_location = self.env.ref('stock.stock_location_customers')

    # ── Helpers ──

    def _validate_picking(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for ml in picking.move_line_ids:
            ml.quantity = ml.move_id.product_uom_qty
        picking.button_validate()

    def _create_receipt(self, warehouse, qty, unit_cost):
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': f'Receipt {warehouse.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.supplier_location.id,
            'location_dest_id': warehouse.lot_stock_id.id,
            'price_unit': unit_cost,
        })
        self._validate_picking(picking)
        return picking

    def _create_transfer(self, source_wh, dest_wh, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': source_wh.int_type_id.id,
            'location_id': source_wh.lot_stock_id.id,
            'location_dest_id': dest_wh.lot_stock_id.id,
        })
        self.env['stock.move'].create({
            'name': f'Transfer {source_wh.name}->{dest_wh.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': source_wh.lot_stock_id.id,
            'location_dest_id': dest_wh.lot_stock_id.id,
        })
        self._validate_picking(picking)
        return picking

    def _create_delivery(self, warehouse, qty):
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        self.env['stock.move'].create({
            'name': f'Sale {warehouse.name}',
            'product_id': self.product.id,
            'product_uom_qty': qty,
            'product_uom': self.product.uom_id.id,
            'picking_id': picking.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.customer_location.id,
        })
        self._validate_picking(picking)
        return picking

    def _get_receipt_layer(self, receipt_picking):
        return self.layer_model.search([
            ('stock_move_id', '=', receipt_picking.move_ids[:1].id),
            ('quantity', '>', 0),
        ], limit=1)

    def _get_position_layers(self, warehouse):
        return self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', warehouse.id),
            ('remaining_qty', '>', 0),
        ])

    # ═══════════════════════════════════════════
    # Tests
    # ═══════════════════════════════════════════

    def test_01_receipt_full_transfer_then_landed_cost_no_error(self):
        """
        THE BUG SCENARIO:
        1. Receipt 100 units @ 100 → WH1
        2. Transfer ALL 100 → WH2
        3. Apply Landed Cost on the receipt picking
        
        Before fix: UserError "You cannot apply landed costs..."
        After fix: Landed cost created successfully
        """
        # 1. Receipt
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        receipt_layer = self._get_receipt_layer(receipt_picking)
        self.assertEqual(receipt_layer.remaining_qty, 100.0)
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0)

        # 2. Full transfer
        self._create_transfer(self.warehouse_1, self.warehouse_2, 100.0)

        receipt_layer.invalidate_recordset(['remaining_qty', 'origin_remaining_qty'])
        self.assertEqual(receipt_layer.remaining_qty, 0.0, "All consumed from WH1")
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0, "Origin NOT consumed (Transfer ≠ Consumption)")

        # 3. Apply landed cost on receipt — should NOT raise
        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })

        # get_valuation_lines must succeed (no UserError)
        lines = landed_cost.get_valuation_lines()
        self.assertTrue(lines, "Should produce valuation lines even after full transfer")

    def test_02_receipt_partial_transfer_landed_cost(self):
        """
        1. Receipt 100 → WH1
        2. Transfer 60 → WH2
        3. Apply Landed Cost on receipt
        
        Should find BOTH remaining at WH1 (40) and position at WH2 (60).
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        self._create_transfer(self.warehouse_1, self.warehouse_2, 60.0)

        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })
        lines = landed_cost.get_valuation_lines()
        self.assertTrue(lines, "Should produce valuation lines after partial transfer")
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(lines[0]['quantity'], 100.0, places=2)

    def test_03_receipt_split_transfer_landed_cost_distribution(self):
        """
        1. Receipt 100 → WH1
        2. Transfer 60 → WH2
        3. Transfer 40 → WH3
        4. Apply Landed Cost 2000 on receipt
        
        Should distribute: WH2=1200, WH3=800
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        receipt_layer = self._get_receipt_layer(receipt_picking)

        self._create_transfer(self.warehouse_1, self.warehouse_2, 60.0)
        self._create_transfer(self.warehouse_1, self.warehouse_3, 40.0)

        receipt_layer.invalidate_recordset(['remaining_qty', 'origin_remaining_qty'])
        self.assertEqual(receipt_layer.remaining_qty, 0.0)
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0)

        # Create landed cost
        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })
        lines = landed_cost.get_valuation_lines()
        self.assertTrue(lines)

        # Add cost line
        self.landed_cost_line_model.create({
            'name': 'Freight',
            'split_method': 'by_quantity',
            'price_unit': 2000.0,
            'cost_id': landed_cost.id,
            'product_id': self.product.id,
        })

        # Compute valuation adjustment lines then validate
        landed_cost.compute_landed_cost()
        account_journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id),
            ('type', '=', 'general'),
        ], limit=1)
        landed_cost.account_journal_id = account_journal
        landed_cost.button_validate()

        # Verify distribution to position layers
        receipt_layer.invalidate_recordset(['origin_remaining_value'])
        self.assertAlmostEqual(receipt_layer.origin_remaining_value, 12000.0, places=0,
                               msg="10000 base + 2000 landed cost")

        # Check per-warehouse landed cost records
        lc_location_model = self.env['stock.valuation.layer.landed.cost']
        wh2_lcs = lc_location_model.search([
            ('warehouse_id', '=', self.warehouse_2.id),
            ('landed_cost_id', '=', landed_cost.id),
        ])
        wh3_lcs = lc_location_model.search([
            ('warehouse_id', '=', self.warehouse_3.id),
            ('landed_cost_id', '=', landed_cost.id),
        ])
        wh2_total = sum(wh2_lcs.mapped('landed_cost_value'))
        wh3_total = sum(wh3_lcs.mapped('landed_cost_value'))
        self.assertAlmostEqual(wh2_total, 1200.0, places=0,
                               msg="WH2 gets 60% of 2000 = 1200")
        self.assertAlmostEqual(wh3_total, 800.0, places=0,
                               msg="WH3 gets 40% of 2000 = 800")

    def test_04_receipt_transfer_sale_then_landed_cost_on_receipt(self):
        """
        1. Receipt 100 @ 100 → WH1
        2. Transfer 60 → WH2
        3. Sale 30 from WH2
        4. Apply Landed Cost on receipt
        
        origin_remaining_qty should be 70 (100 - 30 sold).
        Landed cost should distribute based on current positions.
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        receipt_layer = self._get_receipt_layer(receipt_picking)

        self._create_transfer(self.warehouse_1, self.warehouse_2, 60.0)
        self._create_delivery(self.warehouse_2, 30.0)

        receipt_layer.invalidate_recordset(['origin_remaining_qty'])
        self.assertEqual(receipt_layer.origin_remaining_qty, 70.0,
                         "origin reduced only by external out (30)")

        # Apply landed cost
        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })
        lines = landed_cost.get_valuation_lines()
        self.assertTrue(lines, "Should work even after sale from another warehouse")

    def test_05_receipt_no_transfer_landed_cost(self):
        """
        Baseline: Landed cost on receipt WITHOUT any transfer.
        This should still work (no regression).
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 50.0, 200.0)

        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })
        lines = landed_cost.get_valuation_lines()
        self.assertTrue(lines)
        self.assertAlmostEqual(lines[0]['quantity'], 50.0, places=2)

    def test_06_origin_remaining_qty_preserved_across_transfers(self):
        """
        Verify origin_remaining_qty is the invariant:
        - Never reduced by internal transfers
        - Only reduced by external out
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        receipt_layer = self._get_receipt_layer(receipt_picking)
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0)

        # Multiple transfers
        self._create_transfer(self.warehouse_1, self.warehouse_2, 30.0)
        receipt_layer.invalidate_recordset(['origin_remaining_qty'])
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0)

        self._create_transfer(self.warehouse_1, self.warehouse_3, 20.0)
        receipt_layer.invalidate_recordset(['origin_remaining_qty'])
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0)

        # Transfer back WH2 → WH1
        self._create_transfer(self.warehouse_2, self.warehouse_1, 10.0)
        receipt_layer.invalidate_recordset(['origin_remaining_qty'])
        self.assertEqual(receipt_layer.origin_remaining_qty, 100.0,
                         "Return transfer also preserves origin")

        # Now external out
        self._create_delivery(self.warehouse_1, 10.0)
        receipt_layer.invalidate_recordset(['origin_remaining_qty'])
        self.assertEqual(receipt_layer.origin_remaining_qty, 90.0,
                         "Only external out reduces origin")

    def test_07_valuation_total_unchanged_by_transfer(self):
        """
        sum(remaining_value) across ALL warehouses must stay constant after transfers.
        """
        self._create_receipt(self.warehouse_1, 100.0, 100.0)

        total_before = sum(self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('remaining_qty', '>', 0),
        ]).mapped('remaining_value'))
        self.assertAlmostEqual(total_before, 10000.0, places=2)

        self._create_transfer(self.warehouse_1, self.warehouse_2, 60.0)

        total_after = sum(self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('remaining_qty', '>', 0),
        ]).mapped('remaining_value'))
        self.assertAlmostEqual(total_after, 10000.0, places=2)

        self._create_transfer(self.warehouse_2, self.warehouse_3, 30.0)

        total_final = sum(self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('remaining_qty', '>', 0),
        ]).mapped('remaining_value'))
        self.assertAlmostEqual(total_final, 10000.0, places=2,
                               msg="Valuation stays constant across transfers")

    def test_08_landed_cost_after_multi_hop_transfer(self):
        """
        1. Receipt → WH1
        2. WH1 → WH2 → WH3 (multi-hop)
        3. Apply landed cost on original receipt
        
        Should resolve through origin chain to find position at WH3.
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 50.0, 200.0)

        self._create_transfer(self.warehouse_1, self.warehouse_2, 50.0)
        self._create_transfer(self.warehouse_2, self.warehouse_3, 50.0)

        # All stock should be at WH3
        wh3_layers = self._get_position_layers(self.warehouse_3)
        self.assertAlmostEqual(sum(wh3_layers.mapped('remaining_qty')), 50.0, places=2)

        # Apply landed cost
        landed_cost = self.landed_cost_model.create({
            'target_model': 'picking',
            'picking_ids': [(6, 0, [receipt_picking.id])],
        })
        lines = landed_cost.get_valuation_lines()
        self.assertTrue(lines, "Should work after multi-hop transfer")

    def test_09_position_layer_origin_link_after_transfer(self):
        """
        Verify position layer has origin_valuation_layer_id set correctly.
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        receipt_layer = self._get_receipt_layer(receipt_picking)

        self._create_transfer(self.warehouse_1, self.warehouse_2, 100.0)

        pos_layers = self.layer_model.search([
            ('product_id', '=', self.product.id),
            ('warehouse_id', '=', self.warehouse_2.id),
            ('quantity', '>', 0),
        ])
        self.assertTrue(pos_layers, "Position layer must exist at WH2")
        
        pos = pos_layers[0]
        self.assertTrue(pos.origin_valuation_layer_id,
                        "Position layer must link to origin")
        self.assertEqual(pos.origin_valuation_layer_id.id, receipt_layer.id,
                         "Position layer origin must be the receipt layer")
        self.assertTrue(pos.is_position_layer, "Must be flagged as position layer")

    def test_10_sale_after_transfer_uses_origin_cost(self):
        """
        After transfer, sale from dest warehouse should consume from position layer
        and reduce origin_remaining_qty on the receipt layer.
        """
        receipt_picking = self._create_receipt(self.warehouse_1, 100.0, 100.0)
        receipt_layer = self._get_receipt_layer(receipt_picking)

        self._create_transfer(self.warehouse_1, self.warehouse_2, 100.0)
        self._create_delivery(self.warehouse_2, 40.0)

        receipt_layer.invalidate_recordset(['origin_remaining_qty'])
        self.assertEqual(receipt_layer.origin_remaining_qty, 60.0,
                         "Sale reduces origin by 40")

        # Remaining at WH2 should be 60
        wh2_layers = self._get_position_layers(self.warehouse_2)
        self.assertAlmostEqual(sum(wh2_layers.mapped('remaining_qty')), 60.0, places=2)
