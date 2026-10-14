from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestBGForecast(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.second_warehouse = cls.env['stock.warehouse'].create({
            'name': 'BG Forecast Second', 'code': 'BGF2',
            'company_id': cls.company.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'BG Forecast Product', 'type': 'product',
        })
        cls.other_product = cls.env['product.product'].create({
            'name': 'BG Forecast Other Product', 'type': 'product',
        })
        cls.user = cls.env['res.users'].create({
            'name': 'BG Forecast Stock User', 'login': 'bg_forecast_stock_user',
            'company_id': cls.company.id,
            'company_ids': [Command.set(cls.company.ids)],
            'groups_id': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('stock.group_stock_user').id,
            ])],
        })
        cls.wizard = cls.env['buz.loan.return.create.wizard'].with_user(cls.user)
        cls.values = {
            'product_id': cls.product.id,
            'company_id': cls.company.id,
            'location_id': cls.warehouse.lot_stock_id.id,
            'operation_type_id': cls.second_warehouse.int_type_id.id,
        }

    def test_unsaved_forecast_is_read_only_and_source_takes_precedence(self):
        models = ('buz.loan.return.create.wizard', 'buz.loan.return.document',
                  'stock.picking', 'stock.move')
        counts = {model: self.env[model].search_count([]) for model in models}
        action = self.wizard.action_bg_forecast(**self.values)
        self.assertEqual(action['tag'], 'stock_forecasted')
        self.assertEqual(action['context']['active_id'], self.product.id)
        self.assertEqual(action['context']['active_model'], 'product.product')
        self.assertEqual(action['context']['warehouse'], self.warehouse.id)
        self.assertEqual(action['context']['allowed_company_ids'], self.company.ids)
        for model in models:
            self.assertEqual(self.env[model].search_count([]), counts[model])

    def test_latest_product_location_and_operation_fallback(self):
        action = self.wizard.action_bg_forecast(**{
            **self.values, 'product_id': self.other_product.id,
            'location_id': self.second_warehouse.lot_stock_id.id,
        })
        self.assertEqual(action['context']['active_id'], self.other_product.id)
        self.assertEqual(action['context']['warehouse'], self.second_warehouse.id)
        action = self.wizard.action_bg_forecast(**{**self.values, 'location_id': False})
        self.assertEqual(action['context']['warehouse'], self.second_warehouse.id)

    def test_missing_warehouse_and_non_storable_product(self):
        with self.assertRaises(ValidationError):
            self.wizard.action_bg_forecast(**{
                **self.values, 'location_id': False, 'operation_type_id': False,
            })
        self.product.type = 'consu'
        with self.assertRaises(ValidationError):
            self.wizard.action_bg_forecast(**self.values)

    def test_company_and_access_boundaries(self):
        other_company = self.env['res.company'].create({'name': 'BG Forecast Other Company'})
        with self.assertRaises(ValidationError):
            self.wizard.action_bg_forecast(**{**self.values, 'company_id': other_company.id})
        self.user.groups_id = [Command.set([self.env.ref('base.group_user').id])]
        with self.assertRaises(AccessError):
            self.wizard.action_bg_forecast(**self.values)

    def test_line_product_type_without_saving(self):
        line = self.env['buz.loan.return.create.wizard.line'].new({
            'product_id': self.product.id,
        })
        self.assertEqual(line.product_type, 'product')

    def test_create_bg_and_open_transfer_still_work(self):
        self.warehouse.int_type_id.reservation_method = 'at_confirm'
        wizard = self.wizard.create({
            'document_kind': 'loan',
            'company_id': self.company.id,
            'partner_id': self.user.partner_id.id,
            'operation_type_id': self.warehouse.int_type_id.id,
            'location_id': self.warehouse.lot_stock_id.id,
            'location_dest_id': self.second_warehouse.lot_stock_id.id,
            'line_ids': [Command.create({
                'product_id': self.product.id,
                'product_uom_id': self.product.uom_id.id,
                'quantity': 1,
            })],
        })
        action = wizard.action_create_document()
        document = self.env['buz.loan.return.document'].browse(action['res_id'])
        self.assertEqual(document.picking_id.move_ids.product_id, self.product)
        transfer_action = document.action_open_picking()
        self.assertEqual(transfer_action['res_model'], 'stock.picking')
        self.assertEqual(transfer_action['res_id'], document.picking_id.id)
