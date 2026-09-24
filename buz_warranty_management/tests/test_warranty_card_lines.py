from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command
from odoo.tests.common import TransactionCase


class TestWarrantyCardLines(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Multi Product Customer'})
        self.prod_12m = self._product('Prod 12M', 12, 'month')
        self.prod_2y = self._product('Prod 2Y', 2, 'year')

    def _product(self, name, duration, unit):
        category = self.env['product.category'].create({
            'name': 'Cat %s' % name,
            'warranty_duration': duration,
            'warranty_period_unit': unit,
        })
        return self.env['product.template'].create({
            'name': name,
            'categ_id': category.id,
        }).product_variant_id

    def test_multiple_lines_and_end_date_is_latest(self):
        start = date(2026, 1, 1)
        card = self.env['warranty.card'].create({
            'partner_id': self.partner.id,
            'start_date': start,
            'line_ids': [
                Command.create({'product_id': self.prod_12m.id}),
                Command.create({'product_id': self.prod_2y.id}),
            ],
        })
        self.assertEqual(len(card.line_ids), 2)
        self.assertEqual(card.line_ids[0].end_date, start + relativedelta(months=12))
        self.assertEqual(card.line_ids[1].end_date, start + relativedelta(years=2))
        self.assertEqual(card.end_date, start + relativedelta(years=2))
        self.assertEqual(card.product_id, self.prod_12m)

    def test_legacy_product_id_creates_single_line(self):
        card = self.env['warranty.card'].create({
            'partner_id': self.partner.id,
            'product_id': self.prod_12m.id,
            'start_date': date(2026, 3, 1),
        })
        self.assertEqual(len(card.line_ids), 1)
        self.assertEqual(card.line_ids.product_id, self.prod_12m)
        self.assertEqual(card.end_date, date(2027, 3, 1))

    def test_card_start_date_change_moves_lines(self):
        card = self.env['warranty.card'].create({
            'partner_id': self.partner.id,
            'start_date': date(2026, 1, 1),
            'line_ids': [Command.create({'product_id': self.prod_12m.id})],
        })
        card.start_date = date(2026, 6, 1)
        self.assertEqual(card.line_ids.end_date, date(2027, 6, 1))
        self.assertEqual(card.end_date, date(2027, 6, 1))

    def test_add_line_to_existing_card(self):
        card = self.env['warranty.card'].create({
            'partner_id': self.partner.id,
            'start_date': date(2026, 1, 1),
            'line_ids': [Command.create({'product_id': self.prod_12m.id})],
        })
        card.write({'line_ids': [Command.create({'product_id': self.prod_2y.id})]})
        self.assertEqual(card.end_date, date(2028, 1, 1))
