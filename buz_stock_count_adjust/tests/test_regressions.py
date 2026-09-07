from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .test_count_adjust import TestEngineRunIntegration, TestReconcileAndFix


@tagged('post_install', '-at_install')
class TestCountAdjustmentRegressions(TestEngineRunIntegration):

    def test_failed_apply_leaves_no_reseed_or_backup(self):
        doc = self._fixture_229_target_217()
        doc.action_preview()
        before = self._svl_snapshot(self.p, self.wh)
        backups = self.env['stock.count.adjustment.backup'].search_count([])
        # Fail after reseed has executed, as a real FIFO shortage would.
        with patch.object(type(self.engine), '_scoped_replay',
                          side_effect=UserError('Injected FIFO shortage')):
            with self.assertRaises(UserError):
                doc.action_apply()
        self.assertEqual(self._svl_snapshot(self.p, self.wh), before)
        self.assertEqual(self.env['stock.count.adjustment.backup'].search_count([]),
                         backups)
        self.assertEqual(doc.state, 'previewed')

    def test_preview_failure_is_reported_without_stock_writes(self):
        doc = self._fixture_229_target_217()
        before = self._svl_snapshot(self.p, self.wh)
        with patch.object(type(self.engine), '_scoped_replay',
                          side_effect=UserError('Injected FIFO shortage')):
            doc.action_preview()
        self.assertEqual(doc.line_ids.state, 'error')
        self.assertEqual(self._svl_snapshot(self.p, self.wh), before)

    def test_cutoff_edit_invalidates_preview(self):
        doc = self._fixture_229_target_217()
        doc.action_preview()
        doc.cutoff_date = '2026-06-30'
        self.assertEqual(doc.state, 'draft')
        self.assertFalse(doc.line_hash)
        with self.assertRaises(UserError):
            doc.action_apply()

    def test_backdated_receipt_crossing_cutoff_is_refused(self):
        doc = self._fixture_229_target_217()
        layer = self.SVL.search([('product_id', '=', self.p.id)], limit=1)
        self.env.cr.execute(
            'UPDATE stock_valuation_layer SET create_date=%s WHERE id=%s',
            ('2026-06-15 00:00:00', layer.id))
        layer.invalidate_recordset()
        before = self._svl_snapshot(self.p, self.wh)
        doc.action_preview()
        self.assertEqual(doc.line_ids.state, 'error')
        self.assertIn('Backdated', doc.line_ids.result_note)
        with self.assertRaises(UserError):
            doc.action_apply()
        self.assertEqual(self._svl_snapshot(self.p, self.wh), before)

    def test_restore_refuses_later_quant_changes(self):
        doc = self._apply_fixture()
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh.lot_stock_id.id)], limit=1)
        quant.quantity -= 5
        before = self._svl_snapshot(self.p, self.wh)
        with self.assertRaises(UserError):
            doc.action_rollback()
        self.assertEqual(quant.quantity, 212)
        self.assertEqual(doc.state, 'applied')
        self.assertEqual(self._svl_snapshot(self.p, self.wh), before)

    def test_restore_refuses_later_reservation(self):
        doc = self._apply_fixture()
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh.lot_stock_id.id)], limit=1)
        quant.reserved_quantity = 1
        with self.assertRaises(UserError):
            doc.action_rollback()

    def test_legacy_backup_cannot_restore_without_post_image(self):
        doc = self._apply_fixture()
        doc.backup_id.stock_fingerprint = False
        with self.assertRaises(UserError):
            doc.action_rollback()

    def test_restore_includes_inventory_counterpart_quant(self):
        doc = self._fixture_229_target_217()
        Quant = self.env['stock.quant']
        before = {q.id: q.quantity for q in Quant.search([
            ('product_id', '=', self.p.id)])}
        doc.action_preview()
        doc.action_apply()
        doc.action_rollback()
        for quant in Quant.search([('product_id', '=', self.p.id)]):
            self.assertAlmostEqual(quant.quantity, before.get(quant.id, 0), places=4)

    def test_value_deltas_match_final_layers(self):
        doc = self._fixture_229_target_217()
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -2, 'value': -1,
            'unit_cost': 0.5, 'remaining_qty': 0, 'remaining_value': 0})
        out.flush_recordset()
        self.env.cr.execute(
            'UPDATE stock_valuation_layer SET create_date=%s, accounting_date=%s '
            'WHERE id=%s', ('2026-06-15', '2026-06-15', out.id))
        out.invalidate_recordset()
        layers = self.SVL.search([('product_id', '=', self.p.id)])
        before_value = sum(layers.mapped('value'))
        before_cogs = out.value
        doc.action_preview()
        doc.action_apply()
        after_value = sum(self.SVL.search([
            ('product_id', '=', self.p.id)]).mapped('value'))
        self.assertAlmostEqual(doc.valuation_delta, after_value - before_value,
                               places=2)
        self.assertAlmostEqual(doc.cogs_delta, out.value - before_cogs, places=2)
        self.assertNotEqual(doc.cogs_delta, 0)

    def test_mixed_uom_receipt_does_not_remove_eleven_units(self):
        doc = self._fixture_229_target_217()
        doc.line_ids.write({'target_qty': 229, 'target_value': 229 * 344})
        dozen = self.env.ref('uom.product_uom_dozen')
        move = self.env['stock.move'].create({
            'name': 'Count mixed UoM receipt', 'product_id': self.p.id,
            'company_id': self.env.company.id, 'product_uom_qty': 1,
            'product_uom': dozen.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': self.wh.lot_stock_id.id})
        move._action_confirm()
        self.env['stock.move.line'].create({
            'move_id': move.id, 'product_id': self.p.id,
            'product_uom_id': dozen.id, 'quantity': 1, 'picked': True,
            'location_id': move.location_id.id,
            'location_dest_id': move.location_dest_id.id})
        move._action_done()
        self.assertEqual(move.state, 'done')
        self.assertEqual(sum(move.move_line_ids.mapped('quantity_product_uom')), 12)
        doc.action_preview()
        doc.action_apply()
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh.lot_stock_id.id)])
        self.assertAlmostEqual(sum(quant.mapped('quantity')), 241, places=3)
        self.assertFalse(doc.mismatch_ids)

    def test_company_rules_and_backup_write_protection(self):
        doc = self._apply_fixture()
        other = self.env['res.company'].create({'name': 'Count restricted company'})
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Count restricted user', 'login': 'count-restricted-user',
            'company_id': other.id,
            'company_ids': [fields.Command.set(other.ids)],
            'groups_id': [fields.Command.set([
                self.env.ref('buz_stock_count_adjust.group_stock_count_adjustment').id])]})
        restricted = doc.with_user(user).with_context(allowed_company_ids=other.ids)
        self.assertFalse(restricted.search([('id', '=', doc.id)]))
        backup = doc.backup_id.with_user(user).with_context(
            allowed_company_ids=other.ids)
        self.assertFalse(backup.search([('id', '=', backup.id)]))
        with self.assertRaises(AccessError):
            backup.action_restore()
        with self.assertRaises(AccessError):
            backup.write({'stock_fingerprint': 'forged'})

    def test_authorized_user_can_apply_and_restore_but_not_edit_backup(self):
        doc = self._fixture_229_target_217()
        company = self.env.company
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Count authorized user', 'login': 'count-authorized-user',
            'company_id': company.id,
            'company_ids': [fields.Command.set(company.ids)],
            'groups_id': [fields.Command.set([
                self.env.ref('buz_stock_count_adjust.group_stock_count_adjustment').id])]})
        doc = doc.with_user(user).with_context(allowed_company_ids=company.ids)
        self.assertFalse(doc.env.su)
        doc.action_preview()
        doc.action_apply()
        with self.assertRaises(AccessError):
            doc.backup_id.write({'stock_fingerprint': 'forged'})
        doc.action_rollback()
        self.assertEqual(doc.state, 'rolled_back')

    def test_default_parent_cannot_add_lines_to_applied_document(self):
        doc = self._apply_fixture()
        with self.assertRaises(UserError):
            self.env['stock.count.adjustment.line'].with_context(
                default_adjustment_id=doc.id).create({
                    'product_id': self.p.id, 'warehouse_id': self.wh.id,
                    'bucket_seq': 999, 'target_qty': 1, 'target_value': 1})


@tagged('post_install', '-at_install')
class TestMismatchBackupRegressions(TestReconcileAndFix):

    def test_fix_keeps_first_quant_preimage_and_restores_it(self):
        doc = self._fixture_with_corrupted_transfer()
        doc.action_preview()
        doc.action_apply()
        backup = doc.backup_id
        before = {b.quant_id.id: b.quantity for b in backup.quant_line_ids}
        doc.mismatch_ids.action_fix_move_line()
        quant_ids = backup.quant_line_ids.mapped('quant_id').ids
        self.assertEqual(len(quant_ids), len(backup.quant_line_ids))
        for line in backup.quant_line_ids:
            if line.quant_id.id in before:
                self.assertEqual(line.quantity, before[line.quant_id.id])
        doc.action_rollback()
        for quant_id, qty in before.items():
            self.assertAlmostEqual(self.env['stock.quant'].browse(quant_id).quantity,
                                   qty, places=4)
