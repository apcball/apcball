from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStoreRequestCart(TransactionCase):

    def setUp(self):
        super().setUp()
        self.location = self.env['buz.it.stock.location'].create({
            'name': 'Store Cart Test Location',
            'company_id': self.env.company.id,
        })
        self.item = self.env['buz.it.inventory.item'].create({
            'name': 'Store Cart Test Item',
            'unit': 'piece',
            'company_id': self.env.company.id,
            'max_per_request': 3,
        })
        self.requester = self.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': 'Store Cart Requester',
            'login': 'store_cart_requester',
            'email': 'store_cart_requester@example.com',
            'company_id': self.env.company.id,
            'company_ids': [fields.Command.set([self.env.company.id])],
            'groups_id': [fields.Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('buz_it_helpdesk.group_it_requester').id,
            ])],
        })
        self.env['buz.it.stock.quant'].with_context(
            buz_quant_write=True,
        ).create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'qty': 5,
        })

    def test_cart_creates_one_draft_with_multiple_lines(self):
        second = self.env['buz.it.inventory.item'].create({
            'name': 'Store Cart Second Item',
            'unit': 'box',
            'company_id': self.env.company.id,
        })
        self.env['buz.it.stock.quant'].with_context(
            buz_quant_write=True,
        ).create({
            'inventory_item_id': second.id,
            'location_id': self.location.id,
            'qty': 2,
        })

        action = self.env['buz.it.inventory.item'].with_user(
            self.requester,
        ).action_create_store_request([
            {'item_id': self.item.id, 'quantity': 2},
            {'item_id': second.id, 'quantity': 1},
        ])
        request = self.env['buz.it.issue.request'].browse(action['res_id'])
        self.assertEqual(request.state, 'draft')
        self.assertEqual(len(request.line_ids), 2)
        self.assertEqual(request.requester_id, self.requester)

    def test_cart_rechecks_maximum_quantity(self):
        with self.assertRaises(UserError):
            self.env['buz.it.inventory.item'].with_user(
                self.requester,
            ).action_create_store_request([
                {'item_id': self.item.id, 'quantity': 4},
            ])