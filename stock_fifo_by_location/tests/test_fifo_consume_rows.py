from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestFifoConsumeRows(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.SVL = self.env['stock.valuation.layer']

    def test_consume_rows_matches_inline_replay(self):
        # rows: 10 @ 10, then 10 @ 20, then out 15
        rows = [
            (1, 10.0, 100.0, None, None),
            (2, 10.0, 200.0, None, None),
            (3, -15.0, 0.0, None, None),
        ]
        result = self.SVL._fifo_consume_rows(rows)
        self.assertEqual(result['expected'][1], (0.0, 0.0))
        rq, rv = result['expected'][2]
        self.assertAlmostEqual(rq, 5.0, places=4)
        self.assertAlmostEqual(rv, 100.0, places=2)
        self.assertAlmostEqual(result['cogs'][3], -200.0, places=2)
        self.assertFalse(result['shortage'])

    def test_seed_primes_the_pool(self):
        # Seed a bucket of 5 @ 50, then an outgoing 3 walks it.
        rows = [(9, -3.0, 0.0, None, None)]
        result = self.SVL._fifo_consume_rows(rows, seed=[(7, 5.0, 50.0)])
        self.assertAlmostEqual(result['expected'][7][0], 2.0, places=4)
        self.assertAlmostEqual(result['expected'][7][1], 20.0, places=2)
        self.assertAlmostEqual(result['cogs'][9], -30.0, places=2)

    def test_replay_remaining_still_works(self):
        p = self.env['product.product'].create({
            'name': 'consume-rows probe', 'type': 'product',
            'categ_id': self.env.ref('product.product_category_all').id})
        wh = self.env['stock.warehouse'].search([], limit=1)
        for qty, val in [(10, 100.0), (-4, 0.0)]:
            self.SVL.create({
                'product_id': p.id, 'company_id': self.env.company.id,
                'warehouse_id': wh.id, 'quantity': qty, 'value': val,
                'unit_cost': val / qty if qty else 0.0,
                'remaining_qty': qty if qty > 0 else 0.0,
                'remaining_value': val if qty > 0 else 0.0,
            })
        result = self.SVL._fifo_replay_remaining(p.id, wh.id, self.env.company.id)
        self.assertAlmostEqual(result['shortage'], 0.0, places=4)
