from odoo.tests.common import TransactionCase


class TestOrderPartnerCode(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({
            'name': 'Customer Code Lookup',
            'customer_rank': 1,
        })
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Vendor Code Lookup',
            'supplier_rank': 1,
        })

    def test_sale_order_partner_code_selects_customer(self):
        order = self.env['sale.order'].new({
            'partner_code': self.customer.partner_code,
        })
        order._onchange_partner_code()
        self.assertEqual(order.partner_id, self.customer)

    def test_purchase_order_partner_code_selects_vendor(self):
        order = self.env['purchase.order'].new({
            'partner_code': self.vendor.partner_code,
        })
        order._onchange_partner_code()
        self.assertEqual(order.partner_id, self.vendor)
