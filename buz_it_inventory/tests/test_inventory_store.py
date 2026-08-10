from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInventoryStore(TransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self.env['buz.it.inventory.item.category'].create({
            'name': 'Inventory Test Category',
        })
        self.location = self.env['buz.it.stock.location'].create({
            'name': 'Inventory Test Location',
            'company_id': self.env.company.id,
        })
        self.item = self.env['buz.it.inventory.item'].create({
            'name': 'Inventory Test Item',
            'unit': 'piece',
            'category_id': self.category.id,
            'company_id': self.env.company.id,
        })
        self.agent = self._create_user(
            'inventory_test_agent', 'buz_it_helpdesk.group_it_support_agent'
        )
        self.manager = self._create_user(
            'inventory_test_manager',
            'buz_it_helpdesk.group_it_helpdesk_manager',
        )
        self.requester = self._create_user(
            'inventory_test_requester', 'buz_it_helpdesk.group_it_requester'
        )

    def _create_user(self, login, group_xmlid):
        return self.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': login,
            'login': login,
            'email': '%s@example.com' % login,
            'company_id': self.env.company.id,
            'company_ids': [fields.Command.set([self.env.company.id])],
            'groups_id': [fields.Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref(group_xmlid).id,
            ])],
        })

    def test_receive_and_adjust(self):
        receive = self.env['buz.it.stock.receive.wizard'].with_user(
            self.agent
        ).create({})
        self.env['buz.it.stock.receive.line'].with_user(self.agent).create({
            'wizard_id': receive.id,
            'inventory_item_id': self.item.id,
            'qty': 10,
            'location_id': self.location.id,
        })
        receive.action_receive()
        quant = self.env['buz.it.stock.quant'].search([
            ('inventory_item_id', '=', self.item.id),
            ('location_id', '=', self.location.id),
        ], limit=1)
        self.assertEqual(quant.qty, 10)
        adjust = self.env['buz.it.stock.adjust.wizard'].with_user(
            self.manager
        ).create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'new_qty': 7,
        })
        adjust.action_adjust()
        self.assertEqual(quant.qty, 7)
        self.assertEqual(
            self.env['buz.it.stock.history'].search_count([
                ('inventory_item_id', '=', self.item.id),
                ('move_type', '=', 'adjust'),
            ]),
            1,
        )

    def test_inventory_menu_is_under_it_management(self):
        store_menu = self.env.ref('buz_it_inventory.menu_it_store')
        root = self.env.ref('buz_it_helpdesk.menu_it_management')
        self.assertEqual(store_menu.parent_id, root)
        self.assertIn(
            self.env.ref('buz_it_helpdesk.group_it_requester'),
            store_menu.groups_id,
        )
        config_menu = self.env.ref('buz_it_inventory.menu_inventory_config')
        self.assertEqual(config_menu.parent_id, store_menu)
        adjust_menu = self.env.ref('buz_it_inventory.menu_inventory_adjust')
        self.assertEqual(adjust_menu.parent_id, config_menu)
        self.assertIn(
            self.env.ref('buz_it_helpdesk.group_it_helpdesk_manager'),
            adjust_menu.groups_id,
        )
        self.assertNotIn(
            self.env.ref('buz_it_helpdesk.group_it_support_agent'),
            adjust_menu.groups_id,
        )

    def test_adjust_same_quantity_does_not_create_history(self):
        quant = self.env['buz.it.stock.quant'].with_context(
            buz_quant_write=True,
        ).create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'qty': 10,
        })
        adjust = self.env['buz.it.stock.adjust.wizard'].with_user(
            self.manager
        ).create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'new_qty': 10,
        })

        adjust.action_adjust()

        self.assertEqual(quant.qty, 10)
        self.assertFalse(self.env['buz.it.stock.history'].search([
            ('inventory_item_id', '=', self.item.id),
            ('move_type', '=', 'adjust'),
        ]))

    def test_adjust_rejects_negative_quantity(self):
        adjust = self.env['buz.it.stock.adjust.wizard'].with_user(
            self.manager
        ).create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'new_qty': -1,
        })

        with self.assertRaises(UserError):
            adjust.action_adjust()

    def test_adjust_is_manager_only(self):
        for user in (self.requester, self.agent):
            with self.assertRaises(AccessError):
                self.env['buz.it.stock.adjust.wizard'].with_user(
                    user
                ).create({
                    'inventory_item_id': self.item.id,
                    'location_id': self.location.id,
                    'new_qty': 1,
                })

    def test_receive_is_agent_allowed_requester_blocked(self):
        with self.assertRaises(AccessError):
            self.env['buz.it.stock.receive.wizard'].with_user(
                self.requester
            ).create({})

    def test_quant_cannot_be_changed_directly(self):
        quant = self.env['buz.it.stock.quant'].with_context(
            buz_quant_write=True,
        ).create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'qty': 10,
        })
        with self.assertRaises(UserError):
            quant.with_context(buz_quant_write=False).qty = 5
        with self.assertRaises(UserError):
            quant.unlink()

    def test_stock_history_is_immutable(self):
        history = self.env['buz.it.stock.history'].create({
            'move_type': 'in',
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'qty': 1,
            'move_date': fields.Date.today(),
        })
        with self.assertRaises(UserError):
            history.write({'note': 'changed'})
        with self.assertRaises(UserError):
            history.unlink()

    def test_quant_and_history_reject_cross_company_records(self):
        other_company = self.env['res.company'].create({
            'name': 'Inventory Test Other Company',
        })
        other_location = self.env['buz.it.stock.location'].create({
            'name': 'Inventory Test Other Location',
            'company_id': other_company.id,
        })

        with self.assertRaises(ValidationError):
            self.env['buz.it.stock.quant'].with_context(
                buz_quant_write=True,
            ).create({
                'inventory_item_id': self.item.id,
                'location_id': other_location.id,
                'qty': 1,
            })

        with self.assertRaises(ValidationError):
            self.env['buz.it.stock.history'].create({
                'move_type': 'in',
                'inventory_item_id': self.item.id,
                'location_id': other_location.id,
                'qty': 1,
                'move_date': fields.Date.today(),
            })

    def test_receive_rejects_item_from_other_company(self):
        other_company = self.env['res.company'].create({
            'name': 'Inventory Test Receive Company',
        })
        other_item = self.env['buz.it.inventory.item'].create({
            'name': 'Inventory Test Other Item',
            'unit': 'piece',
            'company_id': other_company.id,
        })
        receive = self.env['buz.it.stock.receive.wizard'].create({
            'company_id': self.env.company.id,
        })
        self.env['buz.it.stock.receive.line'].create({
            'wizard_id': receive.id,
            'inventory_item_id': other_item.id,
            'qty': 1,
            'location_id': False,
        })

        with self.assertRaises(UserError):
            receive.action_receive()
