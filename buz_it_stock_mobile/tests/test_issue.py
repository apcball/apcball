import base64
import io
import uuid
from unittest.mock import patch

from PIL import Image, ImageDraw

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tests.common import new_test_user


@tagged('post_install', '-at_install')
class TestITIssue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id = [fields.Command.link(cls.env.ref('buz_it_stock_mobile.group_it_manager').id)]
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.config = cls.env['buz.it.config'].create({
            'company_id': cls.company.id, 'warehouse_id': cls.warehouse.id,
            'location_id': cls.warehouse.lot_stock_id.id,
        })
        cls.config.action_prepare_locations()
        cls.config.accounting_reviewed = True
        cls.employee = cls.env['hr.employee'].create({'name': 'Somchai IT Test', 'company_id': cls.company.id})
        cls.category = cls.env.ref('buz_it_stock_mobile.category_keyboard')
        cls.product = cls.env['product.product'].create({
            'name': 'IT Test Keyboard', 'detailed_type': 'product',
            'it_issue_enabled': True, 'it_category_id': cls.category.id,
        })
        cls.serial_product = cls.env['product.product'].create({
            'name': 'IT Serial Monitor', 'tracking': 'serial', 'detailed_type': 'product',
            'it_issue_enabled': True, 'it_category_id': cls.category.id,
        })
        cls.lot_product = cls.env['product.product'].create({
            'name': 'IT Lot Cable', 'tracking': 'lot', 'detailed_type': 'product',
            'it_issue_enabled': True, 'it_category_id': cls.category.id,
        })
        cls.serial = cls.env['stock.lot'].create({
            'name': 'IT-SN-001', 'product_id': cls.serial_product.id, 'company_id': cls.company.id,
        })
        cls.lot = cls.env['stock.lot'].create({
            'name': 'IT-LOT-001', 'product_id': cls.lot_product.id, 'company_id': cls.company.id,
        })
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.config.location_id, 10)
        cls.env['stock.quant']._update_available_quantity(cls.serial_product, cls.config.location_id, 1, lot_id=cls.serial)
        cls.env['stock.quant']._update_available_quantity(cls.lot_product, cls.config.location_id, 10, lot_id=cls.lot)
        cls.user = new_test_user(cls.env, login='it_issue_operator', groups='buz_it_stock_mobile.group_it_user')
        cls.other_user = new_test_user(cls.env, login='it_issue_other', groups='buz_it_stock_mobile.group_it_user')
        cls.outsider = new_test_user(cls.env, login='it_issue_outsider', groups='base.group_user')
        image = Image.new('RGB', (800, 320), 'white')
        ImageDraw.Draw(image).line([(80, 230), (220, 60), (150, 250), (470, 130), (650, 210)], fill='black', width=5)
        data = io.BytesIO()
        image.save(data, format='PNG')
        cls.signature = base64.b64encode(data.getvalue()).decode()

    def _issue(self, lines=None, user=None, key=None):
        return self.env['buz.it.issue'].with_user(user or self.user).save_request({
            'request_key': key or str(uuid.uuid4()), 'employee_id': self.employee.id,
            'lines': lines or [{'product_id': self.product.id, 'quantity': 2}],
        })

    def _record(self, detail, user=None):
        return self.env['buz.it.issue'].with_user(user or self.user).browse(detail['id'])

    def test_signature_creates_one_completed_picking(self):
        detail = self._issue()
        issue = self._record(detail)
        self.assertEqual(issue.state, 'awaiting')
        self.assertFalse(issue.picking_id)
        self.assertEqual(self.product.with_context(location=self.config.location_id.id).free_qty, 10)
        result = issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertEqual(result['state'], 'done')
        self.assertEqual(issue.picking_id.state, 'done')
        self.assertEqual(self.product.with_context(location=self.config.location_id.id).qty_available, 8)
        self.assertEqual(issue.action_sign(self.signature, issue.get_detail()['revision'])['picking_id'], result['picking_id'])
        self.assertEqual(self.product.with_context(location=self.config.location_id.id).qty_available, 8)
        self.assertTrue(issue.signature)

    def test_request_retry_reuses_document(self):
        key = str(uuid.uuid4())
        first = self._issue(key=key)
        self.assertEqual(self._issue(key=key)['id'], first['id'])
        issue = self._record(first)
        issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertEqual(self._issue(key=key)['state'], 'done')
        self.assertEqual(self.env['buz.it.issue'].with_user(self.user).request_status(key)['id'], issue.id)

    def test_serial_and_lot(self):
        detail = self._issue([
            {'product_id': self.serial_product.id, 'quantity': 1, 'lot_id': self.serial.id},
            {'product_id': self.lot_product.id, 'quantity': 3, 'lot_id': self.lot.id},
        ])
        issue = self._record(detail)
        issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertEqual(set(issue.picking_id.move_line_ids.lot_id.ids), {self.serial.id, self.lot.id})
        self.assertEqual(sum(issue.picking_id.move_line_ids.mapped('quantity')), 4)

    def test_multiple_lots_same_product(self):
        lot2 = self.lot.copy({'name': 'IT-LOT-002'})
        self.env['stock.quant']._update_available_quantity(self.lot_product, self.config.location_id, 4, lot_id=lot2)
        issue = self._record(self._issue([
            {'product_id': self.lot_product.id, 'quantity': 3, 'lot_id': self.lot.id},
            {'product_id': self.lot_product.id, 'quantity': 2, 'lot_id': lot2.id},
        ]))
        issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertEqual(len(issue.picking_id.move_ids), 2)

    def test_insufficient_stock_rolls_back_all_lines(self):
        issue = self._record(self._issue([
            {'product_id': self.product.id, 'quantity': 2},
            {'product_id': self.lot_product.id, 'quantity': 30, 'lot_id': self.lot.id},
        ]))
        with self.assertRaises(UserError):
            issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertFalse(issue.picking_id)
        self.assertFalse(issue.signature)
        self.assertEqual(issue.state, 'awaiting')
        self.assertFalse(self.env['stock.picking'].search([('origin', '=', issue.name)]))
        self.assertEqual(self.product.with_context(location=self.config.location_id.id).free_qty, 10)

    def test_stock_consumed_between_confirmation_and_signature(self):
        issue1 = self._record(self._issue([{'product_id': self.serial_product.id, 'quantity': 1, 'lot_id': self.serial.id}]))
        issue2 = self._record(self._issue([{'product_id': self.serial_product.id, 'quantity': 1, 'lot_id': self.serial.id}], user=self.other_user), self.other_user)
        issue1.action_sign(self.signature, issue1.get_detail()['revision'])
        with self.assertRaises(UserError):
            issue2.action_sign(self.signature, issue2.get_detail()['revision'])
        self.assertFalse(issue2.picking_id)

    def test_validation_wizard_rolls_back(self):
        issue = self._record(self._issue())
        with patch.object(type(self.env['stock.picking']), 'button_validate', return_value={'type': 'ir.actions.act_window'}):
            with self.assertRaises(UserError):
                issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertEqual(issue.state, 'awaiting')
        self.assertFalse(self.env['stock.picking'].search([('origin', '=', issue.name)]))

    def test_blank_and_invalid_signatures(self):
        issue = self._record(self._issue())
        data = io.BytesIO()
        Image.new('RGB', (800, 320), 'white').save(data, format='PNG')
        for signature in ['', 'not-an-image', base64.b64encode(data.getvalue()).decode()]:
            with self.assertRaises(ValidationError):
                issue.action_sign(signature, issue.get_detail()['revision'])
        self.assertFalse(issue.picking_id)

    def test_invalid_quantities_and_tracking(self):
        cases = [
            {'product_id': self.product.id, 'quantity': 0},
            {'product_id': self.product.id, 'quantity': -1},
            {'product_id': self.product.id, 'quantity': self.product.uom_id.rounding / 2},
            {'product_id': self.serial_product.id, 'quantity': 1},
            {'product_id': self.serial_product.id, 'quantity': 2, 'lot_id': self.serial.id},
            {'product_id': self.lot_product.id, 'quantity': 1, 'lot_id': self.serial.id},
        ]
        for line in cases:
            with self.assertRaises(ValidationError), self.env.cr.savepoint():
                self._issue([line])

    def test_duplicate_serial(self):
        line = {'product_id': self.serial_product.id, 'quantity': 1, 'lot_id': self.serial.id}
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._issue([line, line])

    def test_completed_document_and_lines_are_immutable(self):
        issue = self._record(self._issue())
        issue.action_sign(self.signature, issue.get_detail()['revision'])
        for callback in [lambda: issue.write({'note': 'changed'}),
                         lambda: issue.line_ids.write({'quantity': 1}),
                         lambda: issue.line_ids.unlink(), lambda: issue.action_cancel()]:
            with self.assertRaises(UserError):
                callback()
        with self.assertRaises(AccessError):
            issue.write({'state': 'draft'})

    def test_edit_requires_confirmation_again(self):
        issue = self._record(self._issue())
        issue.line_ids.write({'quantity': 3})
        self.assertEqual(issue.state, 'draft')
        with self.assertRaises(UserError):
            issue.action_sign(self.signature, issue.get_detail()['revision'])
        issue.action_submit()
        issue.action_sign(self.signature, issue.get_detail()['revision'])

    def test_operator_access_and_employee_privacy(self):
        issue = self._record(self._issue())
        with self.assertRaises(AccessError):
            issue.with_user(self.other_user).action_sign(self.signature, issue.with_user(self.other_user).get_detail()['revision'])
        with self.assertRaises(AccessError):
            self.env['buz.it.issue'].with_user(self.outsider).get_people()
        people = self.env['buz.it.issue'].with_user(self.user).get_people('Somchai IT Test')
        self.assertEqual(set(people[0]), {'id', 'name', 'department', 'location_id', 'image'})
        issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertEqual(issue.with_user(self.other_user).get_detail()['state'], 'done')

    def test_cross_company_receiver_rejected(self):
        company2 = self.env['res.company'].create({'name': 'IT Other Company'})
        employee2 = self.env['hr.employee'].create({'name': 'Other Employee', 'company_id': company2.id})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.env['buz.it.issue'].with_user(self.user).save_request({
                'request_key': str(uuid.uuid4()), 'employee_id': employee2.id,
                'lines': [{'product_id': self.product.id, 'quantity': 1}],
            })

    def test_no_unreviewed_consumption(self):
        self.config.accounting_reviewed = False
        with self.assertRaises(ValidationError):
            self._issue()

    def test_cancel_has_no_stock_effect(self):
        issue = self._record(self._issue())
        issue.action_cancel()
        self.assertEqual(issue.state, 'cancel')
        self.assertFalse(issue.picking_id)
        with self.assertRaises(UserError):
            issue.action_sign(self.signature, issue.get_detail()['revision'])

    def test_stale_summary_requires_new_signature(self):
        detail = self._issue()
        issue = self._record(detail)
        issue.write({'note': 'Updated in another tab'})
        issue.action_submit()
        with self.assertRaises(UserError):
            issue.action_sign(self.signature, detail['revision'])
        self.assertFalse(issue.picking_id)

    def test_partial_reservation_rolls_back(self):
        issue = self._record(self._issue())
        with patch.object(type(self.env['stock.move']), '_update_reserved_quantity', return_value=1):
            with self.assertRaises(UserError):
                issue.action_sign(self.signature, issue.get_detail()['revision'])
        self.assertFalse(self.env['stock.picking'].search([('origin', '=', issue.name)]))

    def test_direct_line_insert_requires_confirmation(self):
        issue = self._record(self._issue())
        self.env['buz.it.issue.line'].with_user(self.user).create({
            'issue_id': issue.id, 'product_id': self.lot_product.id,
            'lot_id': self.lot.id, 'quantity': 1,
        })
        self.assertEqual(issue.state, 'draft')

    def test_context_cannot_forge_completed_issue(self):
        issue = self.env['buz.it.issue'].with_user(self.user).with_context(
            default_state='done', default_name='Forged', default_signature=self.signature,
        ).create({'employee_id': self.employee.id})
        self.assertEqual(issue.state, 'draft')
        self.assertEqual(issue.name, 'New')
        self.assertFalse(issue.signature)
