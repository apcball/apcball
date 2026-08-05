from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestConsumableStore(TransactionCase):

    def setUp(self):
        super().setUp()
        company = self.env.company
        self.category = self.env['buz.it.consumable.category'].create({
            'name': 'Test Category',
        })
        self.location_a = self.env['buz.it.stock.location'].create({
            'name': 'ตู้ IT ชั้น 1',
            'company_id': company.id,
        })
        self.location_b = self.env['buz.it.stock.location'].create({
            'name': 'ตู้ IT ชั้น 2',
            'company_id': company.id,
        })
        self.ink = self.env['buz.it.consumable'].create({
            'name': 'หมึก HP 85A',
            'unit': 'กล่อง',
            'category_id': self.category.id,
            'company_id': company.id,
        })
        self.mouse = self.env['buz.it.consumable'].create({
            'name': 'Mouse USB',
            'unit': 'ชิ้น',
            'category_id': self.category.id,
            'company_id': company.id,
        })
        self.requester = self._create_user(
            'requester_consumable_test',
            'buz_it_helpdesk.group_it_requester',
        )
        self.agent = self._create_user(
            'agent_consumable_test',
            'buz_it_helpdesk.group_it_support_agent',
        )

    def _create_user(self, login, group):
        return self.env['res.users'].with_context(
            no_reset_password=True,
        ).create({
            'name': login,
            'login': login,
            'email': login + '@example.com',
            'company_id': self.env.company.id,
            'company_ids': [fields.Command.set([self.env.company.id])],
            'groups_id': [fields.Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref(group).id,
            ])],
        })

    def _receive(self, consumable, location, qty):
        wizard = self.env['buz.it.stock.receive.wizard'].with_user(
            self.agent
        ).create({})
        self.env['buz.it.stock.receive.line'].with_user(self.agent).create({
            'wizard_id': wizard.id,
            'consumable_id': consumable.id,
            'qty': qty,
            'location_id': location.id,
        })
        wizard.action_receive()

    def _get_quant(self, consumable, location):
        return self.env['buz.it.stock.quant'].search([
            ('consumable_id', '=', consumable.id),
            ('location_id', '=', location.id),
        ], limit=1)

    def _add_to_cart(self, consumable, qty):
        wizard = self.env['buz.it.consumable.add.wizard'].with_user(
            self.requester
        ).create({
            'consumable_id': consumable.id,
            'qty': qty,
        })
        wizard.action_add()
        return self.env['buz.it.consumable.request'].search([
            ('requester_id', '=', self.requester.id),
            ('state', '=', 'draft'),
        ], limit=1)

    def test_full_flow(self):
        self._receive(self.ink, self.location_a, 10)
        self._receive(self.mouse, self.location_a, 5)

        request = self._add_to_cart(self.ink, 2)
        self._add_to_cart(self.ink, 1)
        self._add_to_cart(self.mouse, 1)
        self.assertEqual(len(request.line_ids), 2)
        ink_line = request.line_ids.filtered(
            lambda line: line.consumable_id == self.ink
        )
        self.assertEqual(ink_line.requested_qty, 3)

        request.with_user(self.requester).action_submit()
        self.assertEqual(request.state, 'confirmed')
        self.assertRegex(request.name, r'^REQ/\d{4}/\d{4}$')

        request.with_user(self.agent).action_deliver_all()
        self.assertEqual(request.state, 'done')
        self.assertEqual(
            self._get_quant(self.ink, self.location_a).qty, 7,
        )
        self.assertTrue(request.payer_id)
        self.assertTrue(request.pay_date)

    def test_short_stock_partial_then_complete(self):
        self._receive(self.ink, self.location_a, 5)
        request = self._add_to_cart(self.ink, 10)
        request.with_user(self.requester).action_submit()
        line = request.line_ids

        with self.assertRaises(UserError):
            line.with_user(self.agent)._do_deliver(10, self.location_a)

        line.with_user(self.agent)._do_deliver(5, self.location_a)
        self.assertEqual(line.state, 'partial')
        self.assertEqual(request.state, 'partial')

        self._receive(self.ink, self.location_a, 5)
        line.with_user(self.agent)._do_deliver(5, self.location_a)
        self.assertEqual(line.state, 'done')
        self.assertEqual(request.state, 'done')

    def test_reject_line(self):
        self._receive(self.ink, self.location_a, 2)
        request = self._add_to_cart(self.ink, 4)
        request.with_user(self.requester).action_submit()
        line = request.line_ids

        line.with_user(self.agent)._do_deliver(2, self.location_a)
        wizard = self.env['buz.it.consumable.reject.wizard'].with_user(
            self.agent
        ).create({
            'line_id': line.id,
            'reason': 'หมดสต็อก',
        })
        wizard.action_reject()
        self.assertEqual(line.state, 'rejected')
        self.assertEqual(request.state, 'rejected')

    def test_oversell_guard(self):
        self._receive(self.ink, self.location_a, 3)
        request = self._add_to_cart(self.ink, 5)
        request.with_user(self.requester).action_submit()

        with self.assertRaises(UserError):
            request.line_ids.with_user(self.agent)._do_deliver(5, self.location_a)
        self.assertEqual(
            self._get_quant(self.ink, self.location_a).qty, 3,
        )

    def test_max_per_request(self):
        self.ink.max_per_request = 5
        request = self._add_to_cart(self.ink, 4)
        with self.assertRaises(UserError):
            self._add_to_cart(self.ink, 2)
        self.assertEqual(request.line_ids.requested_qty, 4)

    def test_multi_location_requires_manual_choice(self):
        self._receive(self.ink, self.location_a, 6)
        self._receive(self.ink, self.location_b, 7)
        request = self._add_to_cart(self.ink, 5)
        request.with_user(self.requester).action_submit()
        line = request.line_ids

        locations = line.with_user(self.agent)._get_deliverable_locations()
        self.assertEqual(len(locations), 2)

        with self.assertRaises(UserError):
            request.with_user(self.agent).action_deliver_all()

        line.with_user(self.agent)._do_deliver(5, self.location_b)
        self.assertEqual(request.state, 'done')
        self.assertEqual(
            self._get_quant(self.ink, self.location_b).qty, 2,
        )

    def test_adjust_stock(self):
        self._receive(self.ink, self.location_a, 10)
        wizard = self.env['buz.it.stock.adjust.wizard'].with_user(
            self.agent
        ).create({
            'consumable_id': self.ink.id,
            'location_id': self.location_a.id,
            'new_qty': 7,
        })
        wizard.action_adjust()
        self.assertEqual(
            self._get_quant(self.ink, self.location_a).qty, 7,
        )
        history = self.env['buz.it.stock.history'].search([
            ('consumable_id', '=', self.ink.id),
            ('move_type', '=', 'adjust'),
        ])
        self.assertTrue(history)
