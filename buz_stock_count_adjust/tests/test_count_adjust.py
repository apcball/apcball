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
                               78956.2345 - v0, places=2)
        for b in self.SVL.browse(res['bucket_ids']):
            self.assertAlmostEqual(b.quantity, b.remaining_qty, places=4)
            self.assertAlmostEqual(b.value, b.remaining_value, places=2)

        # report ending at cutoff now equals target
        again = self.engine._baseline(doc)
        q1, v1 = again[(self.p.id, self.wh.id)]
        self.assertAlmostEqual(q1, 217.0, places=2)
        self.assertAlmostEqual(v1, 78956.2345, places=2)

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

    def test_apply_requires_preview_and_unchanged_lines(self):
        doc = self._fixture_229_target_217()
        with self.assertRaises(Exception):
            doc.action_apply()               # not previewed yet
        doc.action_preview()
        doc.line_ids[0].target_qty = 300.0   # mutate -> hash reset to draft
        with self.assertRaises(Exception):
            doc.action_apply()


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
        self.assertTrue(self.engine._check_category(self.prt))
        self.assertFalse(self.engine._check_category(self.pmp))


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
