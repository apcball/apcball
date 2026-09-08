from odoo.exceptions import UserError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestEngineVoidReseed(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ = self.env['product.category'].create({
            'name': 'MP', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'vr probe', 'type': 'product', 'categ_id': self.categ.id})
        for qty, val, acct in [(441, 157416.65, '2026-05-10'),
                               (-212, -75758.94, '2026-05-20')]:
            svl = self.SVL.create({
                'product_id': self.p.id, 'company_id': self.env.company.id,
                'warehouse_id': self.wh.id, 'quantity': qty, 'value': val,
                'unit_cost': abs(val / qty),
                'remaining_qty': qty if qty > 0 else 0.0,
                'remaining_value': val if qty > 0 else 0.0})
            # stock_fifo_by_location's create() override sets accounting_date =
            # create_date as a deferred ORM write; flush it before the raw UPDATE
            # so our backdated accounting_date wins.
            svl.flush_recordset()
            # backdate create_date too: create_date is the FIFO ordering key
            # (_fifo_consume_rows walks ORDER BY create_date, id), so these two
            # layers must sort as pre-cutoff history for _scoped_replay.
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET accounting_date = %s, "
                "create_date = %s WHERE id = %s",
                (acct + ' 00:00:00', acct + ' 00:00:00', svl.id))
        self.SVL.invalidate_model()

    def _doc(self):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 211,
                        'target_value': 76851.3771}),
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 20, 'target_qty': 1,
                        'target_value': 352.9183}),
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 30, 'target_qty': 5,
                        'target_value': 1751.9391}),
            ]})

    def test_void_reseed_hits_target_ending_and_invariant(self):
        doc = self._doc()
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.p.id, self.wh.id)]      # expect 229 / 81658.26
        group = doc._line_groups()[0]
        res = self.engine._void_and_reseed(group, q0, v0, doc.cutoff_date)

        self.SVL.invalidate_model()   # raw INSERTs — drop stale ORM cache first
        inserted = self.SVL.browse([res['counter_id']] + res['bucket_ids'])
        self.assertAlmostEqual(sum(inserted.mapped('quantity')),
                               217 - q0, places=3)
        self.assertAlmostEqual(sum(inserted.mapped('value')),
                               sum(doc.line_ids.mapped('target_value')) - v0,
                               places=2)
        for b in self.SVL.browse(res['bucket_ids']):
            self.assertAlmostEqual(b.quantity, b.remaining_qty, places=4)
            self.assertAlmostEqual(b.value, b.remaining_value, places=2)

        # report ending at cutoff now equals target
        again = self.engine._baseline(doc)
        q1, v1 = again[(self.p.id, self.wh.id)]
        self.assertAlmostEqual(q1, 217.0, places=2)
        self.assertAlmostEqual(v1, sum(doc.line_ids.mapped('target_value')), places=2)

    def test_scoped_replay_reprices_post_cutoff_out_no_shortage(self):
        doc = self._doc()  # reuse TestEngineVoidReseed._doc
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.p.id, self.wh.id)]
        group = doc._line_groups()[0]
        reseed = self.engine._void_and_reseed(group, q0, v0, doc.cutoff_date)

        # a post-cutoff delivery of 20 units, priced wrong on purpose
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -20, 'value': -1.0,
            'unit_cost': 0.05, 'remaining_qty': 0.0, 'remaining_value': 0.0})
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', out.id))
        self.SVL.invalidate_model()

        res = self.engine._scoped_replay(group, reseed, doc.cutoff_date)
        self.assertAlmostEqual(res['shortage'], 0.0, places=3)
        out.invalidate_recordset()
        # 20 units at bucket-1 rate 364.2245 -> value ~ -7284.49
        self.assertAlmostEqual(out.value, -20 * (76851.3771 / 211), places=1)
        b1 = self.SVL.browse(reseed['bucket_ids'][0])
        self.assertAlmostEqual(b1.remaining_qty, 191.0, places=3)

    def test_scoped_replay_shortage_raises(self):
        doc = self._doc()
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.p.id, self.wh.id)]
        group = doc._line_groups()[0]
        reseed = self.engine._void_and_reseed(group, q0, v0, doc.cutoff_date)
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -500, 'value': -1.0,
            'unit_cost': 0.002, 'remaining_qty': 0.0, 'remaining_value': 0.0})
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', out.id))
        self.SVL.invalidate_model()
        with self.assertRaises(Exception):
            self.engine._scoped_replay(group, reseed, doc.cutoff_date)


@tagged('post_install', '-at_install')
class TestBackupRollback(common.TransactionCase):

    PRE = ['remaining_qty', 'remaining_value', 'value', 'unit_cost']

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ = self.env['product.category'].create({
            'name': 'MP-bk', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'bk probe', 'type': 'product', 'categ_id': self.categ.id})

    def _seed(self, qty, val, when):
        svl = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': qty, 'value': val,
            'unit_cost': abs(val / qty),
            'remaining_qty': qty if qty > 0 else 0.0,
            'remaining_value': val if qty > 0 else 0.0})
        # stock_fifo_by_location defers accounting_date = create_date; flush
        # before the raw UPDATE so our backdate wins. create_date is the FIFO
        # ordering key, so backdate it too.
        svl.flush_recordset()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET accounting_date = %s, "
            "create_date = %s WHERE id = %s", (when, when, svl.id))
        self.SVL.invalidate_model()
        return svl.id

    def _doc(self):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 211,
                        'target_value': 76851.3771}),
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 20, 'target_qty': 1,
                        'target_value': 352.9183}),
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 30, 'target_qty': 5,
                        'target_value': 1751.9391}),
            ]})

    def _capture(self, ids):
        out = {}
        for sid in ids:
            self.env.cr.execute(
                "SELECT %s FROM stock_valuation_layer WHERE id = %%s"
                % ', '.join(self.PRE), (sid,))
            out[sid] = dict(zip(self.PRE, self.env.cr.fetchone()))
        return out

    def _apply_and_capture_preimage(self):
        self._seed(441, 157416.65, '2026-05-10 00:00:00')
        self._seed(-212, -75758.94, '2026-05-20 00:00:00')
        # one post-cutoff delivery, deliberately mispriced
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -20, 'value': -1.0,
            'unit_cost': 0.05, 'remaining_qty': 0.0, 'remaining_value': 0.0})
        out.flush_recordset()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', out.id))
        self.SVL.invalidate_model()

        doc = self._doc()
        base = self.engine._baseline(doc)
        scope = self.engine._touch_scope(doc, base)
        preimage = {'stock_valuation_layer': self._capture(scope['svl_ids'])}

        backup = self.engine._snapshot(doc, scope)
        for group in doc._line_groups():
            self.assertEqual(self.engine._locked_layer_count(group), 0)
            q0, v0 = base[(group.product_id.id, group.warehouse_id.id)]
            reseed = self.engine._void_and_reseed(
                group, q0, v0, doc.cutoff_date, backup=backup)
            self.engine._scoped_replay(group, reseed, doc.cutoff_date)
        doc.backup_id = backup
        doc.state = 'applied'
        backup._seal_stock_state()
        return doc, preimage

    def test_rollback_restores_every_touched_row(self):
        doc, pre = self._apply_and_capture_preimage()
        doc.action_rollback()
        self.assertEqual(doc.state, 'rolled_back')
        self.assertEqual(doc.backup_id.state, 'restored')
        for table, rows in pre.items():
            for pk, cols in rows.items():
                self.env.cr.execute(
                    "SELECT %s FROM %s WHERE id = %%s" % (
                        ', '.join(cols), table), (pk,))
                current = self.env.cr.fetchone()
                self.assertEqual(
                    current, tuple(cols.values()),
                    "%s#%s not restored" % (table, pk))
        self.env.cr.execute(
            "SELECT count(*) FROM stock_valuation_layer WHERE description LIKE %s",
            ('count-adjust %s%%' % doc.name,))
        self.assertEqual(self.env.cr.fetchone()[0], 0)


@tagged('post_install', '-at_install')
class TestEngineRunIntegration(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ = self.env['product.category'].create({
            'name': 'MP-run', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'run probe', 'type': 'product', 'categ_id': self.categ.id,
            'standard_price': 344.0})

    def _svl_snapshot(self, product, warehouse):
        self.SVL.flush_model()
        self.env.cr.execute(
            "SELECT id, remaining_qty, remaining_value, value, unit_cost "
            "FROM stock_valuation_layer "
            "WHERE product_id = %s AND warehouse_id = %s ORDER BY id",
            (product.id, warehouse.id))
        return tuple(tuple(r) for r in self.env.cr.fetchall())

    def _fixture_229_target_217(self):
        """On-hand quant = 229 (backdated inventory adjustment), but the doc's
        counted target is 217 and there are no post-cutoff moves -> _quant_adjust
        must drive the quant down by 12."""
        quant = self.env['stock.quant'].with_context(
            skip_warehouse_consistency_check=True).create({
                'product_id': self.p.id,
                'location_id': self.wh.lot_stock_id.id,
                'company_id': self.env.company.id, 'quantity': 0.0})
        quant.write({'inventory_quantity': 229.0})
        quant.with_context(
            skip_warehouse_consistency_check=True)._apply_inventory()

        self.env['stock.move'].flush_model()
        self.env['stock.move.line'].flush_model()
        self.SVL.flush_model()
        self.env.cr.execute(
            "UPDATE stock_move SET date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', self.p.id))
        self.env.cr.execute(
            "UPDATE stock_move_line SET date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', self.p.id))
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s, "
            "accounting_date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', '2026-05-10 00:00:00', self.p.id))
        self.env['stock.move'].invalidate_model()
        self.env['stock.move.line'].invalidate_model()
        self.SVL.invalidate_model()

        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 217.0,
                        'target_value': 78956.2345})]})

    def test_quant_adjust_hits_target_and_neutralises_svl(self):
        doc = self._fixture_229_target_217()
        last_svl = self.env['stock.valuation.layer'].search(
            [], order='id desc', limit=1).id
        self.env['count.adjust.engine'].run(doc, dry_run=False)
        quant = self.env['stock.quant'].search([
            ('product_id', '=', self.p.id),
            ('location_id', 'child_of', self.wh.lot_stock_id.id)])
        self.assertAlmostEqual(sum(quant.mapped('quantity')), 217.0, places=2)
        gen_svl = self.env['stock.valuation.layer'].search([
            ('product_id', '=', self.p.id), ('id', '>', last_svl),
            ('description', 'ilike', 'Product Quantity Updated')], limit=1)
        self.assertTrue(
            gen_svl, "expected _quant_adjust to generate an inventory SVL")
        self.assertEqual((gen_svl.quantity, gen_svl.value,
                          gen_svl.remaining_qty, gen_svl.remaining_value),
                         (0.0, 0.0, 0.0, 0.0))
        # the ending FIFO queue (bucket layers) must survive the -12 physical
        # adjustment intact -- this is the module's reported output
        self.SVL.invalidate_model()
        buckets = self.SVL.search([
            ('product_id', '=', self.p.id), ('quantity', '>', 0),
            ('description', 'like', 'count-adjust %s%%' % doc.name)])
        self.assertAlmostEqual(sum(buckets.mapped('remaining_qty')), 217.0,
                               places=2)
        self.assertAlmostEqual(sum(buckets.mapped('remaining_value')),
                               78956.2345, places=2)

    def test_preview_writes_nothing_to_svl(self):
        doc = self._fixture_229_target_217()
        before = self._svl_snapshot(self.p, self.wh)
        doc.action_preview()
        self.assertEqual(doc.state, 'previewed')
        self.assertEqual(self._svl_snapshot(self.p, self.wh), before)
        self.assertTrue(doc.preview_log)

    def test_no_post_cutoff_layers_is_noop(self):
        doc = self._fixture_229_target_217()
        res = self.env['count.adjust.engine'].run(doc, dry_run=True)
        g = res['groups'][0]
        self.assertEqual(g['state'], 'previewed')
        self.assertNotIn('shortage', (g.get('note') or '').lower())

    def test_apply_requires_preview_and_unchanged_lines(self):
        doc = self._fixture_229_target_217()
        with self.assertRaises(Exception):
            doc.action_apply()               # not previewed yet
        doc.action_preview()
        doc.line_ids[0].target_qty = 300.0   # mutate -> hash reset to draft
        with self.assertRaises(Exception):
            doc.action_apply()

    def _apply_fixture(self):
        doc = self._fixture_229_target_217()
        doc.action_preview()
        doc.action_apply()
        self.assertEqual(doc.state, 'applied')
        return doc

    def test_line_edit_on_applied_doc_refused(self):
        # C1: a line edit on an applied doc must NOT demote it to draft, or the
        # rollback path (state == 'applied') is permanently lost.
        doc = self._apply_fixture()
        self.assertTrue(doc.backup_id)
        with self.assertRaises(UserError):
            doc.line_ids[0].target_qty = 999.0
        self.assertEqual(doc.state, 'applied')
        self.assertTrue(doc.backup_id)
        doc.action_rollback()
        self.assertEqual(doc.state, 'rolled_back')

    def test_preview_refused_on_applied(self):
        # C2: preview on an applied doc would overwrite backup_id on re-apply.
        doc = self._apply_fixture()
        with self.assertRaises(Exception):
            doc.action_preview()

    def test_delete_applied_adjustment_refused(self):
        # C3: deleting an applied doc cascades its backup away.
        doc = self._apply_fixture()
        with self.assertRaises(Exception):
            doc.unlink()
        doc.action_rollback()
        with self.assertRaises(Exception):
            doc.unlink()

    def test_rollback_restores_quant_adjust_generated_rows(self):
        # C4 / I5: _quant_adjust drives the quant down by 12 and generates an
        # inventory move + SVL; rollback must undo all of it.
        Quant = self.env['stock.quant']

        def _onhand():
            Quant.invalidate_model()
            return sum(Quant.search([
                ('product_id', '=', self.p.id),
                ('location_id', 'child_of', self.wh.lot_stock_id.id),
            ]).mapped('quantity'))

        doc = self._fixture_229_target_217()
        self.assertAlmostEqual(_onhand(), 229.0, places=2)
        self.SVL.flush_model()
        self.env['stock.move'].flush_model()
        max_svl = self.SVL.search([], order='id desc', limit=1).id
        max_move = self.env['stock.move'].search(
            [], order='id desc', limit=1).id

        doc.action_preview()
        doc.action_apply()
        self.assertAlmostEqual(_onhand(), 217.0, places=2)

        doc.action_rollback()
        self.assertEqual(doc.state, 'rolled_back')
        self.assertAlmostEqual(_onhand(), 229.0, places=2)

        self.env.cr.execute(
            "SELECT count(*) FROM stock_valuation_layer "
            "WHERE id > %s AND product_id = %s", (max_svl, self.p.id))
        self.assertEqual(self.env.cr.fetchone()[0], 0,
                         "generated / bucket SVL rows survived rollback")
        self.env.cr.execute(
            "SELECT count(*) FROM stock_move WHERE id > %s AND product_id = %s",
            (max_move, self.p.id))
        self.assertEqual(self.env.cr.fetchone()[0], 0,
                         "generated inventory move survived rollback")
        self.env.cr.execute(
            "SELECT count(*) FROM stock_valuation_layer WHERE description LIKE %s",
            ('count-adjust %s%%' % doc.name,))
        self.assertEqual(self.env.cr.fetchone()[0], 0)


@tagged('post_install', '-at_install')
class TestEngineBaseline(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ_rt = self.env['product.category'].create({
            'name': 'RT', 'property_valuation': 'real_time',
            'property_cost_method': 'fifo'})
        self.categ_mp = self.env['product.category'].create({
            'name': 'MP', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.prt = self.env['product.product'].create({
            'name': 'rt probe', 'type': 'product', 'categ_id': self.categ_rt.id})
        self.pmp = self.env['product.product'].create({
            'name': 'mp probe', 'type': 'product', 'categ_id': self.categ_mp.id})

    def _seed_layers(self, product, rows, cutoff='2026-05-31'):
        SVL = self.env['stock.valuation.layer']
        for i, (qty, val) in enumerate(rows):
            svl = SVL.create({
                'product_id': product.id, 'company_id': self.env.company.id,
                'warehouse_id': self.wh.id, 'quantity': qty, 'value': val,
                'unit_cost': val / qty if qty else 0.0,
                'remaining_qty': qty if qty > 0 else 0.0,
                'remaining_value': val if qty > 0 else 0.0})
            # stock_fifo_by_location's create() override sets accounting_date =
            # create_date as a deferred ORM write; flush it before the raw UPDATE
            # so our backdated accounting_date wins.
            svl.flush_recordset()
            # accounting_date on cutoff day so the report buckets it as pre-cutoff
            self.env.cr.execute(
                "UPDATE stock_valuation_layer SET accounting_date = %s WHERE id = %s",
                ('2026-05-20 00:00:00', svl.id))
        SVL.invalidate_model(['accounting_date'])

    def test_baseline_matches_report_wizard(self):
        self._seed_layers(self.pmp, [(100, 1000.0), (-30, -300.0)])
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [(0, 0, {'product_id': self.pmp.id,
                                 'warehouse_id': self.wh.id,
                                 'bucket_seq': 10, 'target_qty': 70,
                                 'target_value': 700.0})]})
        base = self.engine._baseline(doc)
        q0, v0 = base[(self.pmp.id, self.wh.id)]
        self.assertAlmostEqual(q0, 70.0, places=2)
        self.assertAlmostEqual(v0, 700.0, places=2)

    def test_real_time_category_flagged(self):
        self.assertTrue(
            self.engine._check_category(self.prt, self.env.company))
        self.assertFalse(
            self.engine._check_category(self.pmp, self.env.company))

    def test_real_time_category_skipped(self):
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [(0, 0, {'product_id': self.prt.id,
                                 'warehouse_id': self.wh.id,
                                 'bucket_seq': 10, 'target_qty': 5.0,
                                 'target_value': 50.0})]})
        doc.action_preview()
        line = doc.line_ids[0]
        self.assertEqual(line.state, 'skipped')
        self.assertIn('real-time', (line.result_note or '').lower())


@tagged('post_install', '-at_install')
class TestReconcileAndFix(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.wh2 = self.env['stock.warehouse'].create({
            'name': 'CA reconcile WH2', 'code': 'CAR2'})
        self.categ = self.env['product.category'].create({
            'name': 'MP-rec', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'rec probe', 'type': 'product', 'categ_id': self.categ.id,
            'standard_price': 100.0})

    def _fixture_with_corrupted_transfer(self):
        """5 units seeded at wh.lot_stock_id (backdated inventory adjustment),
        then a post-cutoff done inter-warehouse move of 1 unit
        wh.lot_stock_id -> wh2.lot_stock_id which books a post-cutoff out-layer
        (-1) at wh. The move line's source is then raw-corrupted to
        wh2.lot_stock_id so it no longer references the wh subtree: the layer
        booked -1 leaving wh but the move now shows net 0 there."""
        Quant = self.env['stock.quant']
        quant = Quant.with_context(skip_warehouse_consistency_check=True).create({
            'product_id': self.p.id,
            'location_id': self.wh.lot_stock_id.id,
            'company_id': self.env.company.id, 'quantity': 0.0})
        quant.write({'inventory_quantity': 5.0})
        quant.with_context(skip_warehouse_consistency_check=True)._apply_inventory()

        # backdate the seeding move + layer to well before the cutoff
        self.env['stock.move'].flush_model()
        self.env['stock.move.line'].flush_model()
        self.SVL.flush_model()
        self.env.cr.execute(
            "UPDATE stock_move SET date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', self.p.id))
        self.env.cr.execute(
            "UPDATE stock_move_line SET date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', self.p.id))
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s, "
            "accounting_date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', '2026-05-10 00:00:00', self.p.id))
        self.env['stock.move'].invalidate_model()
        self.env['stock.move.line'].invalidate_model()
        self.SVL.invalidate_model()

        move = self.env['stock.move'].create({
            'name': 'CA bad transfer',
            'product_id': self.p.id,
            'product_uom_qty': 1.0,
            'product_uom': self.p.uom_id.id,
            'location_id': self.wh.lot_stock_id.id,
            'location_dest_id': self.wh2.lot_stock_id.id,
            'company_id': self.env.company.id,
        })
        move._action_confirm()
        move._action_assign()
        if not move.move_line_ids:
            self.env['stock.move.line'].create({
                'move_id': move.id,
                'product_id': self.p.id,
                'product_uom_id': self.p.uom_id.id,
                'location_id': move.location_id.id,
                'location_dest_id': move.location_dest_id.id,
                'company_id': self.env.company.id,
            })
        # Odoo 17 only VALUES a move for move-lines with picked=True; an
        # unpicked line gives _get_valued_qty()==0 and no SVL is booked.
        move.move_line_ids.write({'quantity': 1.0, 'picked': True})
        move._action_done()
        self.transfer_move = move
        self.bad_move_line = move.move_line_ids[0]

        # the inter-warehouse out-layer at wh, booked with this move
        self.SVL.flush_model()
        self.env.cr.execute("""
            SELECT id FROM stock_valuation_layer
            WHERE stock_move_id = %s AND warehouse_id = %s AND quantity < 0
        """, (move.id, self.wh.id))
        row = self.env.cr.fetchone()
        self.assertTrue(
            row, "fixture produced no post-cutoff out-layer at wh for the move")
        self.out_svl_id = row[0]
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', self.out_svl_id))
        self.env.cr.execute(
            "UPDATE stock_move SET date = %s WHERE id = %s",
            ('2026-06-15 03:00:00', move.id))
        self.env.cr.execute(
            "UPDATE stock_move_line SET date = %s WHERE move_id = %s",
            ('2026-06-15 03:00:00', move.id))

        # corrupt the move line's source: point it away from the wh subtree
        self.env.cr.execute(
            "UPDATE stock_move_line SET location_id = %s WHERE id = %s",
            (self.wh2.lot_stock_id.id, self.bad_move_line.id))
        self.env['stock.move'].invalidate_model()
        self.env['stock.move.line'].invalidate_model()
        self.SVL.invalidate_model()

        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 5.0,
                        'target_value': 500.0})]})

    def test_reconcile_detects_corrupted_move_line(self):
        # plant a done inter-warehouse move whose line reads RM01->RM01
        # instead of FG10->RM01, so the source quant was never decremented
        doc = self._fixture_with_corrupted_transfer()
        res = self.env['count.adjust.engine'].run(doc, dry_run=False)
        self.assertEqual(len(doc.mismatch_ids), 1)
        m = doc.mismatch_ids
        self.assertEqual(m.move_line_id, self.bad_move_line)
        self.assertAlmostEqual(abs(m.diff), 1.0, places=3)
        self.assertEqual(m.state, 'open')

    def test_mismatch_fix_button_corrects_locations_and_quants(self):
        doc = self._fixture_with_corrupted_transfer()
        res = self.env['count.adjust.engine'].run(doc, dry_run=False)
        doc.backup_id = res['backup_id']       # exercise the self-backup branch
        doc.write({'state': 'applied'})        # fix is a post-apply action
        m = doc.mismatch_ids
        diff = m.diff
        Quant = self.env['stock.quant']
        q_to_before = sum(Quant.search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh.lot_stock_id.id)]).mapped('quantity'))
        q_from_before = sum(Quant.search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh2.lot_stock_id.id)]).mapped('quantity'))

        doc.mismatch_ids.action_fix_move_line()
        self.assertEqual(doc.mismatch_ids.state, 'fixed')
        self.assertEqual(self.bad_move_line.location_id,
                         self.wh.lot_stock_id)

        Quant.invalidate_model()
        q_to_after = sum(Quant.search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh.lot_stock_id.id)]).mapped('quantity'))
        q_from_after = sum(Quant.search([
            ('product_id', '=', self.p.id),
            ('location_id', '=', self.wh2.lot_stock_id.id)]).mapped('quantity'))
        self.assertAlmostEqual(q_to_after - q_to_before, diff, places=3)
        self.assertAlmostEqual(q_from_after - q_from_before, -diff, places=3)

    def test_reconcile_clean_transfer_no_mismatch(self):
        Quant = self.env['stock.quant']
        quant = Quant.with_context(skip_warehouse_consistency_check=True).create({
            'product_id': self.p.id, 'location_id': self.wh.lot_stock_id.id,
            'company_id': self.env.company.id, 'quantity': 0.0})
        quant.write({'inventory_quantity': 5.0})
        quant.with_context(skip_warehouse_consistency_check=True)._apply_inventory()
        self.SVL.flush_model()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s, "
            "accounting_date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', '2026-05-10 00:00:00', self.p.id))
        self.env.cr.execute(
            "UPDATE stock_move SET date = %s WHERE product_id = %s",
            ('2026-05-10 00:00:00', self.p.id))
        self.SVL.invalidate_model()
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 5.0,
                        'target_value': 500.0})]})
        group = doc._line_groups()[0]
        self.assertEqual(self.engine._reconcile(group, doc.cutoff_date), [])

    def test_fix_move_line_refused_when_not_applied(self):
        # I2: action_fix_move_line must not write into a doc that is not
        # applied (or whose backup has already been restored).
        doc = self._fixture_with_corrupted_transfer()
        res = self.env['count.adjust.engine'].run(doc, dry_run=False)
        doc.backup_id = res['backup_id']
        self.assertEqual(doc.state, 'draft')
        with self.assertRaises(Exception):
            doc.mismatch_ids.action_fix_move_line()
        # applied but backup restored -> still refused
        doc.write({'state': 'applied'})
        doc.backup_id.state = 'restored'
        with self.assertRaises(Exception):
            doc.mismatch_ids.action_fix_move_line()


@tagged('post_install', '-at_install')
class TestCountAdjustSkeleton(common.TransactionCase):

    def test_models_and_group_exist(self):
        self.assertIn('stock.count.adjustment', self.env)
        self.assertIn('stock.count.adjustment.line', self.env)
        self.assertIn('stock.count.adjustment.mismatch', self.env)
        self.assertIn('stock.count.adjustment.backup', self.env)
        self.assertIn('count.adjust.engine', self.env)
        self.assertTrue(self.env.ref('buz_stock_count_adjust.group_stock_count_adjustment'))

    def test_create_document_gets_sequence_name(self):
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id,
            'cutoff_date': '2026-05-31',
        })
        self.assertNotEqual(doc.name, '/')
        self.assertEqual(doc.state, 'draft')


@tagged('post_install', '-at_install')
class TestCountAdjustModel(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.p1 = self.env['product.product'].create({
            'name': 'SCA probe 1', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        self.p2 = self.env['product.product'].create({
            'name': 'SCA probe 2', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})

    def _doc(self):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 211.0,
                        'target_value': 76851.3771}),
                (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 20, 'target_qty': 1.0,
                        'target_value': 352.9183}),
                (0, 0, {'product_id': self.p2.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': 5.0,
                        'target_value': 100.0}),
            ]})

    def test_line_groups_splits_by_product_warehouse(self):
        doc = self._doc()
        groups = doc._line_groups()
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(g) for g in groups], [2, 1])
        self.assertEqual(groups[0].mapped('bucket_seq'), [10, 20])

    def test_editing_lines_after_preview_resets_state(self):
        doc = self._doc()
        doc.write({'state': 'previewed', 'line_hash': doc._line_hash()})
        doc.line_ids[0].target_qty = 999.0
        self.assertEqual(doc.state, 'draft')
        self.assertFalse(doc.line_hash)

    def test_duplicate_bucket_seq_rejected(self):
        with self.assertRaises(Exception):
            self.env['stock.count.adjustment'].create({
                'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
                'line_ids': [
                    (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                            'bucket_seq': 10, 'target_qty': 1, 'target_value': 1}),
                    (0, 0, {'product_id': self.p1.id, 'warehouse_id': self.wh.id,
                            'bucket_seq': 10, 'target_qty': 2, 'target_value': 2}),
                ]})


@tagged('post_install', '-at_install')
class TestImportWizard(common.TransactionCase):

    def _doc(self):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31'})

    def test_csv_import_buckets_by_file_order(self):
        import base64, io, csv
        wh = self.env['stock.warehouse'].search([], limit=1)
        p = self.env['product.product'].create({
            'name': 'imp probe', 'default_code': 'IMP001', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31'})
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['product_code', 'warehouse_code', 'target_qty',
                    'target_value', 'note'])
        w.writerow(['IMP001', wh.code + '/Stock', '211', '76851.3771', 'b1'])
        w.writerow(['IMP001', wh.code, '1', '352.9183', 'b2'])
        w.writerow(['NOPE', wh.code, '5', '10', 'bad'])
        wiz = self.env['stock.count.adjustment.import'].create({
            'adjustment_id': doc.id, 'file_format': 'csv',
            'data_file': base64.b64encode(buf.getvalue().encode()),
            'filename': 'x.csv', 'import_valid_only': True})
        wiz.action_do_import()
        self.assertEqual(len(doc.line_ids), 2)
        self.assertEqual(doc.line_ids.mapped('bucket_seq'), [10, 20])
        self.assertIn('NOPE', wiz.result_log)

    def test_import_all_or_nothing_when_not_valid_only(self):
        import base64, io, csv
        wh = self.env['stock.warehouse'].search([], limit=1)
        self.env['product.product'].create({
            'name': 'imp probe2', 'default_code': 'IMP002', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        doc = self._doc()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['product_code', 'warehouse_code', 'target_qty',
                    'target_value', 'note'])
        w.writerow(['IMP002', wh.code, '10', '100', 'ok'])
        w.writerow(['BADCODE', wh.code, '5', '50', 'bad'])
        wiz = self.env['stock.count.adjustment.import'].create({
            'adjustment_id': doc.id, 'file_format': 'csv',
            'data_file': base64.b64encode(buf.getvalue().encode()),
            'filename': 'x.csv', 'import_valid_only': False})
        wiz.action_do_import()
        self.assertEqual(len(doc.line_ids), 0)
        self.assertIn('BADCODE', wiz.result_log)
        self.assertIn('Row 3', wiz.result_log)

    def test_xlsx_round_trip(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest('openpyxl not available')
        import base64, io
        wh = self.env['stock.warehouse'].search([], limit=1)
        self.env['product.product'].create({
            'name': 'imp probe3', 'default_code': 'IMP003', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        doc = self._doc()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['product_code', 'warehouse_code', 'target_qty',
                   'target_value', 'note'])
        ws.append(['IMP003', wh.code + '/Stock', 12, 480.5, 'x1'])
        ws.append(['IMP003', wh.code, 3, 120.0, 'x2'])
        bio = io.BytesIO()
        wb.save(bio)
        wiz = self.env['stock.count.adjustment.import'].create({
            'adjustment_id': doc.id, 'file_format': 'xlsx',
            'data_file': base64.b64encode(bio.getvalue()),
            'filename': 'x.xlsx', 'import_valid_only': False})
        wiz.action_do_import()
        self.assertEqual(len(doc.line_ids), 2)
        self.assertEqual(doc.line_ids.mapped('bucket_seq'), [10, 20])


@tagged('post_install', '-at_install')
class TestEngineEdgeCases(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ = self.env['product.category'].create({
            'name': 'MP-edge', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'edge probe', 'type': 'product', 'categ_id': self.categ.id})
        svl = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': 100, 'value': 1000.0,
            'unit_cost': 10.0, 'remaining_qty': 100, 'remaining_value': 1000.0})
        svl.flush_recordset()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET accounting_date = %s, "
            "create_date = %s WHERE id = %s",
            ('2026-05-10 00:00:00', '2026-05-10 00:00:00', svl.id))
        self.SVL.invalidate_model()

    def _simple_doc(self, target_qty=100.0, target_value=1000.0):
        return self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [
                (0, 0, {'product_id': self.p.id, 'warehouse_id': self.wh.id,
                        'bucket_seq': 10, 'target_qty': target_qty,
                        'target_value': target_value})]})

    def _svl_snapshot(self):
        self.SVL.flush_model()
        self.env.cr.execute(
            "SELECT id, remaining_qty, remaining_value, value, unit_cost "
            "FROM stock_valuation_layer WHERE product_id = %s ORDER BY id",
            (self.p.id,))
        return tuple(tuple(r) for r in self.env.cr.fetchall())

    def _locked_column_exists(self):
        self.env.cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'stock_valuation_layer' AND column_name = 'locked'
        """)
        return bool(self.env.cr.fetchone())

    def test_preview_then_edit_resets_state(self):
        doc = self._simple_doc()
        doc.action_preview()
        self.assertEqual(doc.state, 'previewed')
        doc.line_ids[0].target_qty += 1
        self.assertEqual(doc.state, 'draft')
        with self.assertRaises(Exception):
            doc.action_apply()

    def test_apply_refused_when_not_previewed(self):
        doc = self._simple_doc()
        with self.assertRaises(Exception):
            doc.action_apply()

    def test_locked_layer_skips_pair(self):
        if not self._locked_column_exists():
            self.skipTest('stock_valuation_layer.locked column absent')
        doc = self._simple_doc()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET locked = TRUE "
            "WHERE product_id = %s AND warehouse_id = %s",
            (self.p.id, self.wh.id))
        self.env['stock.valuation.layer'].invalidate_model(['locked'])
        doc.action_preview()
        line = doc.line_ids[0]
        self.assertEqual(line.state, 'skipped')
        self.assertIn('locked', (line.result_note or '').lower())

    def test_reserved_gt_target_errors(self):
        doc = self._simple_doc(target_qty=1.0, target_value=10.0)
        quant = self.env['stock.quant'].with_context(
            skip_warehouse_consistency_check=True).create({
                'product_id': self.p.id,
                'location_id': self.wh.lot_stock_id.id,
                'company_id': self.env.company.id, 'quantity': 100.0})
        self.env.cr.execute(
            "UPDATE stock_quant SET reserved_quantity = 50 WHERE id = %s",
            (quant.id,))
        self.env['stock.quant'].invalidate_model(['reserved_quantity'])
        before = self._svl_snapshot()
        res = self.engine.run(doc, dry_run=True)
        g = res['groups'][0]
        self.assertEqual(g['state'], 'error')
        self.assertIn('reserved', g['note'].lower())
        self.assertEqual(self._svl_snapshot(), before)

    def test_negative_target_sum_warns_not_blocks(self):
        doc = self._simple_doc(target_qty=-5.0, target_value=-50.0)
        res = self.engine.run(doc, dry_run=True)
        g = res['groups'][0]
        self.assertEqual(g['state'], 'previewed')
        self.assertIn('negative', (g.get('note') or '').lower())


@tagged('post_install', '-at_install')
class TestGlBackedGuard(common.TransactionCase):
    """C5b: a post-cutoff layer that already carries a journal entry must
    stop the group -- _scoped_replay would rewrite `value` and desync the GL."""

    def setUp(self):
        super().setUp()
        self.engine = self.env['count.adjust.engine']
        self.SVL = self.env['stock.valuation.layer']
        self.wh = self.env['stock.warehouse'].search([], limit=1)
        self.categ = self.env['product.category'].create({
            'name': 'MP-gl', 'property_valuation': 'manual_periodic',
            'property_cost_method': 'fifo'})
        self.p = self.env['product.product'].create({
            'name': 'gl probe', 'type': 'product', 'categ_id': self.categ.id})
        svl = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': 100, 'value': 1000.0,
            'unit_cost': 10.0, 'remaining_qty': 100, 'remaining_value': 1000.0})
        svl.flush_recordset()
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET accounting_date = %s, "
            "create_date = %s WHERE id = %s",
            ('2026-05-10 00:00:00', '2026-05-10 00:00:00', svl.id))
        out = self.SVL.create({
            'product_id': self.p.id, 'company_id': self.env.company.id,
            'warehouse_id': self.wh.id, 'quantity': -10, 'value': -100.0,
            'unit_cost': 10.0, 'remaining_qty': 0.0, 'remaining_value': 0.0})
        out.flush_recordset()
        am = self.env['account.move'].create({'move_type': 'entry'})
        self.env.cr.execute(
            "UPDATE stock_valuation_layer SET create_date = %s, "
            "account_move_id = %s WHERE id = %s",
            ('2026-06-15 03:00:00', am.id, out.id))
        self.SVL.invalidate_model()

    def _snap(self):
        self.SVL.flush_model()
        self.env.cr.execute(
            "SELECT id, remaining_qty, remaining_value, value FROM "
            "stock_valuation_layer WHERE product_id = %s ORDER BY id",
            (self.p.id,))
        return tuple(tuple(r) for r in self.env.cr.fetchall())

    def test_gl_backed_layer_skips_group(self):
        doc = self.env['stock.count.adjustment'].create({
            'company_id': self.env.company.id, 'cutoff_date': '2026-05-31',
            'line_ids': [(0, 0, {'product_id': self.p.id,
                                 'warehouse_id': self.wh.id,
                                 'bucket_seq': 10, 'target_qty': 90.0,
                                 'target_value': 900.0})]})
        before = self._snap()
        res = self.engine.run(doc, dry_run=True)
        g = res['groups'][0]
        self.assertEqual(g['state'], 'error')
        self.assertIn('journal', g['note'].lower())
        self.assertEqual(self._snap(), before)
