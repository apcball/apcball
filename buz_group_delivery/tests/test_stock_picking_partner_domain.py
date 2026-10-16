from lxml import etree

from odoo.tests import TransactionCase
from odoo.tools.safe_eval import safe_eval


class TestStockPickingPartnerDomain(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env['res.partner']
        cls.company_partner = Partner.create({
            'name': 'Group Delivery Test Company',
            'is_company': True,
            'type': 'contact',
        })
        cls.contact_partner = Partner.create({
            'name': 'Group Delivery Test Contact',
            'parent_id': cls.company_partner.id,
            'type': 'contact',
        })
        cls.delivery_partner = Partner.create({
            'name': 'Group Delivery Test Delivery',
            'parent_id': cls.company_partner.id,
            'type': 'delivery',
        })
        cls.nested_delivery_partner = Partner.create({
            'name': 'Group Delivery Test Nested Delivery',
            'parent_id': cls.contact_partner.id,
            'type': 'delivery',
        })
        cls.invoice_partner = Partner.create({
            'name': 'Group Delivery Test Invoice',
            'parent_id': cls.company_partner.id,
            'type': 'invoice',
        })
        cls.other_partner = Partner.create({
            'name': 'Group Delivery Test Other',
            'parent_id': cls.company_partner.id,
            'type': 'other',
        })
        cls.unrelated_partner = Partner.create({
            'name': 'Group Delivery Test Unrelated Company',
            'is_company': True,
            'type': 'contact',
        })

    def _picking_partner_domain_expression(self):
        view = self.env['stock.picking'].get_view(view_type='form')
        arch = etree.fromstring(view['arch'].encode())
        partner_fields = arch.xpath(
            "//field[@name='partner_id' and contains(@context, 'default_type')]"
        )
        self.assertEqual(len(partner_fields), 1)
        return partner_fields[0].get('domain')

    def test_selected_partner_limits_domain_to_commercial_entity(self):
        domain_expression = self._picking_partner_domain_expression()
        domain = safe_eval(domain_expression, {
            'parent_partner_id': self.company_partner.id,
        })
        partners = self.env['res.partner'].search(domain)

        self.assertIn(self.company_partner, partners)
        self.assertIn(self.contact_partner, partners)
        self.assertIn(self.delivery_partner, partners)
        self.assertIn(self.nested_delivery_partner, partners)
        self.assertIn(self.invoice_partner, partners)
        self.assertIn(self.other_partner, partners)
        self.assertNotIn(self.unrelated_partner, partners)

    def test_empty_partner_uses_type_filter_without_preloading_ids(self):
        domain_expression = self._picking_partner_domain_expression()
        domain = safe_eval(domain_expression, {'parent_partner_id': False})
        partners = self.env['res.partner'].search(domain)

        self.assertIn(self.delivery_partner, partners)
        self.assertIn(self.invoice_partner, partners)
        self.assertIn(self.other_partner, partners)
        self.assertNotIn('grouped_partner_ids', self.env['stock.picking']._fields)

    def test_parent_partner_is_commercial_root_for_child_contact(self):
        picking = self.env['stock.picking'].new({
            'partner_id': self.contact_partner.id,
        })

        self.assertEqual(picking.parent_partner_id, self.company_partner)

    def test_parent_partner_is_empty_when_picking_has_no_partner(self):
        picking = self.env['stock.picking'].new({})

        self.assertFalse(picking.parent_partner_id)