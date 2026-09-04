from odoo.tests import common, tagged


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
