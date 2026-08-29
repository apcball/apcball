from odoo.tests.common import TransactionCase


class TestResPartnerSearch(TransactionCase):
    def test_name_search_finds_generated_partner_code(self):
        partner = self.env['res.partner'].create({
            'name': 'Partner Code Search Customer',
            'customer_rank': 1,
        })

        self.assertRegex(partner.partner_code, r'^C\d{5}$')
        self.assertIn(
            partner.id,
            [partner_id for partner_id, _display_name in self.env['res.partner'].name_search(partner.partner_code)],
        )
        self.assertIn(
            partner.id,
            [partner_id for partner_id, _display_name in self.env['res.partner'].name_search(partner.name)],
        )
