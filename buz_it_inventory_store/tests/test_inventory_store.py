from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInventoryStore(TransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self.env['buz.it.consumable.category'].create({
            'name': 'Inventory Test Category',
        })
        self.location = self.env['buz.it.stock.location'].create({
            'name': 'Inventory Test Location',
            'company_id': self.env.company.id,
        })
        self.item = self.env['buz.it.consumable'].create({
            'name': 'Inventory Test Item',
            'unit': 'piece',
            'category_id': self.category.id,
            'company_id': self.env.company.id,
        })
        self.agent = self.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'inventory_test_agent',
            'login': 'inventory_test_agent',
            'email': 'inventory_test_agent@example.com',
            'company_id': self.env.company.id,
            'company_ids': [fields.Command.set([self.env.company.id])],
            'groups_id': [fields.Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref(
                    'buz_it_helpdesk.group_it_support_agent',
                ).id,
            ])],
        })

    def test_receive_and_adjust(self):
        receive = self.env['buz.it.stock.receive.wizard'].with_user(
            self.agent
        ).create({})
        self.env['buz.it.stock.receive.line'].with_user(self.agent).create({
            'wizard_id': receive.id,
            'consumable_id': self.item.id,
            'qty': 10,
            'location_id': self.location.id,
        })
        receive.action_receive()
        quant = self.env['buz.it.stock.quant'].search([
            ('consumable_id', '=', self.item.id),
            ('location_id', '=', self.location.id),
        ], limit=1)
        self.assertEqual(quant.qty, 10)
        adjust = self.env['buz.it.stock.adjust.wizard'].with_user(
            self.agent
        ).create({
            'consumable_id': self.item.id,
            'location_id': self.location.id,
            'new_qty': 7,
        })
        adjust.action_adjust()
        self.assertEqual(quant.qty, 7)
        self.assertEqual(
            self.env['buz.it.stock.history'].search_count([
                ('consumable_id', '=', self.item.id),
                ('move_type', '=', 'adjust'),
            ]),
            1,
        )

    def test_inventory_menu_is_under_it_management(self):
        stock_menu = self.env.ref(
            'buz_it_inventory_store.menu_consumable_stock',
        )
        root = self.env.ref('buz_it_helpdesk.menu_it_management')
        self.assertEqual(stock_menu.parent_id, root)
        self.assertIn(
            self.env.ref('buz_it_helpdesk.group_it_support_agent'),
            stock_menu.groups_id,
        )

