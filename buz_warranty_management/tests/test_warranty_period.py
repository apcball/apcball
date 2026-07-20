from datetime import date

from dateutil.relativedelta import relativedelta

from odoo.tests.common import TransactionCase


class TestWarrantyPeriod(TransactionCase):
    def setUp(self):
        super().setUp()
        self.category = self.env['product.category'].create({
            'name': 'Warranty Test Category',
            'warranty_duration': 18,
            'warranty_period_unit': 'month',
        })
        self.product = self.env['product.template'].create({
            'name': 'Warranty Test Product',
            'categ_id': self.category.id,
        })

    def test_product_inherits_category_period_without_override(self):
        self.assertFalse(self.product.warranty_period_override)
        self.assertEqual(self.product.warranty_duration, 18)
        self.assertEqual(self.product.warranty_period_unit, 'month')

    def test_product_override_takes_precedence_over_category(self):
        self.product.write({
            'warranty_period_override': True,
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        self.category.write({
            'warranty_duration': 24,
            'warranty_period_unit': 'month',
        })

        self.assertEqual(self.product.warranty_duration, 2)
        self.assertEqual(self.product.warranty_period_unit, 'year')

    def test_disabling_product_override_restores_category_period(self):
        self.product.write({
            'warranty_period_override': True,
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        self.product.write({'warranty_period_override': False})

        self.assertEqual(self.product.warranty_duration, 18)
        self.assertEqual(self.product.warranty_period_unit, 'month')

    def test_card_snapshots_month_period_and_is_unchanged_by_configuration(self):
        start_date = date(2026, 1, 31)
        card = self._create_card(start_date)

        self.assertEqual(card.warranty_duration, 18)
        self.assertEqual(card.warranty_period_unit, 'month')
        self.assertEqual(card.end_date, start_date + relativedelta(months=18))

        self.category.write({'warranty_duration': 6, 'warranty_period_unit': 'year'})
        self.product.write({
            'warranty_period_override': True,
            'warranty_duration_override': 3,
            'warranty_period_unit_override': 'year',
        })
        card.invalidate_recordset()

        self.assertEqual(card.warranty_duration, 18)
        self.assertEqual(card.warranty_period_unit, 'month')
        self.assertEqual(card.end_date, start_date + relativedelta(months=18))

    def test_card_snapshots_year_period(self):
        self.product.write({
            'warranty_period_override': True,
            'warranty_duration_override': 2,
            'warranty_period_unit_override': 'year',
        })
        start_date = date(2024, 2, 29)
        card = self._create_card(start_date)

        self.assertEqual(card.warranty_duration, 2)
        self.assertEqual(card.warranty_period_unit, 'year')
        self.assertEqual(card.end_date, start_date + relativedelta(years=2))

    def _create_card(self, start_date):
        return self.env['warranty.card'].create({
            'partner_id': self.env['res.partner'].create({
                'name': 'Warranty Test Customer',
            }).id,
            'product_id': self.product.product_variant_id.id,
            'start_date': start_date,
        })
