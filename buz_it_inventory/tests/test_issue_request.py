from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestIssueRequest(TransactionCase):

    def setUp(self):
        super().setUp()
        self.category = self.env['buz.it.inventory.item.category'].create({
            'name': 'Issue Test Category',
        })
        self.location = self.env['buz.it.stock.location'].create({
            'name': 'Issue Test Location',
            'company_id': self.env.company.id,
        })
        self.item = self.env['buz.it.inventory.item'].create({
            'name': 'Issue Test Item',
            'unit': 'ชิ้น',
            'category_id': self.category.id,
            'company_id': self.env.company.id,
        })
        self.env['buz.it.stock.quant'].create({
            'inventory_item_id': self.item.id,
            'location_id': self.location.id,
            'qty': 10,
        })
        self.requester = self._create_user(
            'issue_test_requester', 'buz_it_helpdesk.group_it_requester'
        )
        self.agent = self._create_user(
            'issue_test_agent', 'buz_it_helpdesk.group_it_support_agent'
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

    def _make_request(self, user, item, qty, extra_lines=None):
        lines = [fields.Command.create({
            'item_id': item.id,
            'requested_qty': qty,
        })]
        if extra_lines:
            lines.extend(extra_lines)
        return self.env['buz.it.issue.request'].with_user(user).create({
            'line_ids': lines,
        })

    def test_submit_reserves_quantity(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()

        self.assertEqual(request.state, 'submitted')
        self.item.invalidate_recordset(['on_hand_qty'])
        self.assertEqual(self.item.on_hand_qty, 10)
        self.assertEqual(self.item.reserved_qty, 5)
        self.assertEqual(self.item.available_qty, 5)

    def test_submit_rejects_over_available(self):
        request = self._make_request(self.requester, self.item, 15)
        with self.assertRaises(UserError):
            request.with_user(self.requester).action_submit()
        self.assertEqual(request.state, 'draft')

    def test_submit_aggregates_same_item_lines(self):
        request = self._make_request(self.requester, self.item, 6, extra_lines=[
            fields.Command.create({
                'item_id': self.item.id,
                'requested_qty': 6,
            }),
        ])
        with self.assertRaises(UserError):
            request.with_user(self.requester).action_submit()
        self.assertEqual(request.state, 'draft')

    def test_reject_releases_reservation(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        request.with_user(self.agent).write({
            'rejection_reason': 'out of stock',
        })
        request.with_user(self.agent).action_reject()

        self.assertEqual(request.state, 'rejected')
        self.assertEqual(self.item.reserved_qty, 0)
        self.assertEqual(self.item.available_qty, 10)

    def test_cancel_releases_reservation(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        request.with_user(self.requester).action_cancel()

        self.assertEqual(request.state, 'cancelled')
        self.assertEqual(self.item.reserved_qty, 0)
        self.assertEqual(self.item.available_qty, 10)

    def test_approve_partial_releases_unreserved(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        self.assertEqual(self.item.reserved_qty, 5)

        request.line_ids.with_user(self.agent).approved_qty = 3
        request.with_user(self.agent).action_approve()

        self.assertEqual(request.state, 'approved')
        self.assertEqual(self.item.reserved_qty, 3)
        self.assertEqual(self.item.available_qty, 7)

    def test_reject_requires_reason(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        with self.assertRaises(UserError):
            request.with_user(self.agent).action_reject()

    def test_issue_deducts_stock_and_creates_history(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        request.with_user(self.agent).action_approve()
        request.with_user(self.agent).action_issue()

        self.assertEqual(request.state, 'issued')
        self.assertEqual(request.issued_by, self.agent)
        self.item.invalidate_recordset(['on_hand_qty'])
        self.assertEqual(self.item.on_hand_qty, 5)
        self.assertEqual(self.item.reserved_qty, 0)
        self.assertEqual(self.item.available_qty, 5)
        self.assertTrue(self.env['buz.it.stock.history'].search([
            ('inventory_item_id', '=', self.item.id),
            ('move_type', '=', 'out'),
            ('reference', '=', request.name),
        ]))

    def test_issue_over_stock_raises(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        request.with_user(self.agent).action_approve()
        quant = self.env['buz.it.stock.quant'].search([
            ('inventory_item_id', '=', self.item.id),
            ('location_id', '=', self.location.id),
        ], limit=1)
        quant.qty = 2
        with self.assertRaises(UserError):
            request.with_user(self.agent).action_issue()
        self.assertEqual(request.state, 'approved')

    def test_requester_sees_only_own_requests(self):
        other = self._create_user(
            'issue_test_other', 'buz_it_helpdesk.group_it_requester'
        )
        own = self._make_request(self.requester, self.item, 1)
        other_request = self._make_request(other, self.item, 1)

        visible = self.env['buz.it.issue.request'].with_user(
            self.requester
        ).search([])
        self.assertIn(own, visible)
        self.assertNotIn(other_request, visible)

        visible_agent = self.env['buz.it.issue.request'].with_user(
            self.agent
        ).search([])
        self.assertIn(own, visible_agent)
        self.assertIn(other_request, visible_agent)

    def test_request_item_button_creates_draft(self):
        action = self.item.with_user(self.requester).action_request_item()
        request = self.env['buz.it.issue.request'].browse(action['res_id'])
        self.assertEqual(request.state, 'draft')
        self.assertEqual(request.requester_id, self.requester)
        self.assertEqual(len(request.line_ids), 1)
        self.assertEqual(request.line_ids.item_id, self.item)

    def test_request_item_rejects_out_of_stock(self):
        empty_item = self.env['buz.it.inventory.item'].create({
            'name': 'Empty Item',
            'unit': 'ชิ้น',
            'company_id': self.env.company.id,
        })
        with self.assertRaises(UserError):
            empty_item.with_user(self.requester).action_request_item()

    def test_non_draft_request_cannot_be_deleted(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        with self.assertRaises(UserError):
            request.unlink()
        self.assertTrue(request.exists())

    def test_requester_cannot_edit_after_submit(self):
        request = self._make_request(self.requester, self.item, 5)
        request.with_user(self.requester).action_submit()
        with self.assertRaises(UserError):
            request.with_user(self.requester).write({'reason': 'changed'})
        with self.assertRaises(UserError):
            request.line_ids.with_user(self.requester).requested_qty = 9
