from odoo.exceptions import AccessError
from odoo.tests import common, tagged


@tagged('-at_install', 'post_install')
class TestAccessPosLiteUser(common.TransactionCase):
    """group_pos_lite_user ต้องใช้งาน function หลักของ pos_lite ได้ครบ:
    session -> order -> payment -> return -> exchange, โดยไม่โดน AccessError
    และ record rule ต้องจำกัดให้เห็นเฉพาะ session/order ของตัวเอง"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company = cls.env.company

        cls.category = cls.env['product.category'].create({
            'name': 'Test Category - Access',
        })
        cls.product_a = cls.env['product.product'].create({
            'name': 'Access Product A',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 200.0,
            'taxes_id': [(5, 0, 0)],
        })
        cls.product_b = cls.env['product.product'].create({
            'name': 'Access Product B',
            'type': 'service',
            'categ_id': cls.category.id,
            'sale_ok': True,
            'list_price': 150.0,
            'taxes_id': [(5, 0, 0)],
        })

        cls.partner = cls.env['res.partner'].create({
            'name': 'Access Customer',
            'customer_rank': 1,
        })
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Access Test Pricelist',
            'company_id': cls.company.id,
        })
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'Access Cash Journal',
            'type': 'cash',
            'code': 'ACJR',
            'company_id': cls.company.id,
        })
        cls.stock_location = cls.env['stock.location'].create({
            'name': 'Test Stock Location - Access',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'company_id': cls.company.id,
        })
        cls.config = cls.env['pos.lite.config'].create({
            'name': 'Access Test Config',
            'company_id': cls.company.id,
            'warehouse_id': cls.warehouse.id,
            'location_id': cls.stock_location.id,
            'pricelist_id': cls.pricelist.id,
            'journal_id': cls.cash_journal.id,
        })

        cls.env.cr.execute(
            "UPDATE ir_sequence SET number_next = 200000 WHERE code IN "
            "('pos.lite.session', 'pos.lite.order') AND number_next < 200000"
        )
        cls.env.invalidate_all()

        # POS Lite user (group_pos_lite_user only, no admin/manager rights)
        cls.pos_group = cls.env.ref('pos_lite.group_pos_lite_user')
        cls.pos_user = cls.env['res.users'].create({
            'name': 'POS Lite Line User',
            'login': 'pos_lite_line_user',
            'email': 'pos_lite_line_user@test.local',
            'groups_id': [(6, 0, [cls.pos_group.id])],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Access Emp',
            'company_id': cls.company.id,
            'user_id': cls.pos_user.id,
        })

        # A second, unrelated user+employee to check record-rule isolation.
        cls.other_user = cls.env['res.users'].create({
            'name': 'POS Lite Other User',
            'login': 'pos_lite_other_user',
            'email': 'pos_lite_other_user@test.local',
            'groups_id': [(6, 0, [cls.pos_group.id])],
        })
        cls.other_employee = cls.env['hr.employee'].create({
            'name': 'Other Emp',
            'company_id': cls.company.id,
            'user_id': cls.other_user.id,
        })

    def _as_pos_user(self, model):
        return self.env[model].with_user(self.pos_user)

    def test_user_can_create_session(self):
        session = self._as_pos_user('pos.lite.session').create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        self.assertTrue(session)

    def test_user_can_create_order_and_process_payment(self):
        session = self._as_pos_user('pos.lite.session').create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order = self._as_pos_user('pos.lite.order').create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': session.id,
            'employee_id': self.employee.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'qty': 1,
                'price_unit': 200.0,
            })],
        })
        order.with_user(self.pos_user).action_quick_pay_and_process()
        self.assertEqual(order.state, 'done')

    def test_user_can_create_and_confirm_return(self):
        session = self._as_pos_user('pos.lite.session').create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order = self._as_pos_user('pos.lite.order').create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': session.id,
            'employee_id': self.employee.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'qty': 1,
                'price_unit': 200.0,
            })],
        })
        order.with_user(self.pos_user).action_quick_pay_and_process()

        action = order.with_user(self.pos_user).action_create_return()
        self.assertEqual(action['res_model'], 'pos.lite.return.wizard')

        wizard = self._as_pos_user('pos.lite.return.wizard').create({
            'order_id': order.id,
        })
        wizard._onchange_order_id()
        wizard.action_confirm()

        return_order = self._as_pos_user('pos.lite.order').search([
            ('return_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(return_order)
        self.assertEqual(return_order.state, 'done')

    def test_user_can_create_and_confirm_exchange(self):
        session = self._as_pos_user('pos.lite.session').create({
            'config_id': self.config.id,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
        })
        order = self._as_pos_user('pos.lite.order').create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': session.id,
            'employee_id': self.employee.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'qty': 1,
                'price_unit': 200.0,
            })],
        })
        order.with_user(self.pos_user).action_quick_pay_and_process()

        action = order.with_user(self.pos_user).action_create_exchange()
        self.assertEqual(action['res_model'], 'pos.lite.return.wizard')

        wizard = self._as_pos_user('pos.lite.return.wizard').create({
            'order_id': order.id,
            'is_exchange': True,
        })
        wizard._onchange_order_id()
        exchange_line = self._as_pos_user('pos.lite.return.wizard.exchange.line').create({
            'wizard_id': wizard.id,
            'product_id': self.product_b.id,
            'qty': 1,
            'price_unit': 150.0,
        })
        wizard.with_user(self.pos_user).write({'exchange_line_ids': [(4, exchange_line.id)]})
        wizard.with_user(self.pos_user).action_confirm()

        exchange_order = self._as_pos_user('pos.lite.order').search([
            ('exchange_of_order_id', '=', order.id),
        ], limit=1)
        self.assertTrue(exchange_order)
        self.assertEqual(exchange_order.state, 'done')

    def test_user_can_read_config_but_not_write(self):
        config_as_user = self.config.with_user(self.pos_user)
        self.assertTrue(config_as_user.read(['name']))
        with self.assertRaises(AccessError):
            config_as_user.write({'name': 'Hacked Config Name'})

    def test_user_can_see_colleagues_order_same_company(self):
        """record rule: rule_pos_lite_order_multi_company (company-wide) is OR'd with
        rule_pos_lite_order_employee (own employee), so any group_pos_lite_user sees
        every order in their own company — not just orders tied to their own employee.
        This matches the shared-terminal workflow (any staff can look up any order)."""
        other_session = self.env['pos.lite.session'].with_user(self.other_user).create({
            'config_id': self.config.id,
            'employee_id': self.other_employee.id,
            'company_id': self.company.id,
        })
        other_order = self.env['pos.lite.order'].with_user(self.other_user).create({
            'company_id': self.company.id,
            'channel': 'phone',
            'partner_id': self.partner.id,
            'warehouse_id': self.warehouse.id,
            'pricelist_id': self.pricelist.id,
            'session_id': other_session.id,
            'employee_id': self.other_employee.id,
            'line_ids': [(0, 0, {
                'product_id': self.product_a.id,
                'qty': 1,
                'price_unit': 200.0,
            })],
        })

        found = self._as_pos_user('pos.lite.order').search([
            ('id', '=', other_order.id),
        ])
        self.assertTrue(found)
