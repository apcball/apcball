from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestCreateLoanReturnOperationTypes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env['res.company'].search(
            [('id', '!=', cls.company.id)], limit=1,
        )
        if not cls.other_company:
            cls.other_company = cls.env['res.company'].create({
                'name': 'BG/RBG Operation Type Test Company',
            })
        cls.location = cls.env['stock.location'].search([
            ('usage', '=', 'internal'),
            '|', ('company_id', '=', False),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        if not cls.location:
            raise AssertionError('The test database must contain an internal stock location.')
        cls.partner = cls.env['res.partner'].create({
            'name': 'BG/RBG Operation Type Test Contact',
        })

    def _create_operation_type(
        self, suffix, code='internal', reservation='at_confirm',
        with_source=True, active=True, company=None,
    ):
        values = {
            'name': 'BG/RBG Test %s' % suffix,
            'sequence_code': 'BRT%s' % suffix,
            'code': code,
            'reservation_method': reservation,
            'company_id': (company or self.company).id,
            'create_backorder': 'ask',
            'active': active,
        }
        if with_source:
            values['default_location_src_id'] = self.location.id
            values['default_location_dest_id'] = self.location.id
        return self.env['stock.picking.type'].create(values)

    def test_eligible_operation_types_are_filtered_for_bg_and_rbg(self):
        valid_bg = self._create_operation_type('ValidBG')
        manual = self._create_operation_type('Manual', reservation='manual')
        without_source = self._create_operation_type('NoSource', with_source=False)
        inactive = self._create_operation_type('Inactive', active=False)
        outgoing = self._create_operation_type('Outgoing', code='outgoing')
        other_company = self._create_operation_type(
            'OtherCompany', company=self.other_company, with_source=False,
        )

        loan = self.env['buz.loan.return.create.wizard'].new({
            'company_id': self.company.id,
            'document_kind': 'loan',
        })
        rbg = self.env['buz.loan.return.create.wizard'].new({
            'company_id': self.company.id,
            'document_kind': 'return',
        })
        loan_ids = set(loan.allowed_operation_type_ids.ids)
        rbg_ids = set(rbg.allowed_operation_type_ids.ids)


        self.assertIn(valid_bg.id, loan_ids)
        self.assertNotIn(manual.id, loan_ids)
        self.assertNotIn(without_source.id, loan_ids)
        self.assertIn(manual.id, rbg_ids)
        self.assertIn(without_source.id, rbg_ids)
        for operation_type in (inactive, outgoing, other_company):
            self.assertNotIn(operation_type.id, loan_ids)
            self.assertNotIn(operation_type.id, rbg_ids)

    def test_company_change_clears_an_ineligible_selection(self):
        operation_type = self._create_operation_type('CompanyChange')
        wizard = self.env['buz.loan.return.create.wizard'].new({
            'company_id': self.company.id,
            'document_kind': 'loan',
            'operation_type_id': operation_type.id,
        })
        wizard.company_id = self.other_company
        wizard._onchange_operation_type_domain()

        self.assertFalse(wizard.operation_type_id)
        self.assertNotIn(
            operation_type.id, wizard.allowed_operation_type_ids.ids,
        )

    def test_create_rejects_an_ineligible_operation_type(self):
        operation_type = self._create_operation_type(
            'Forged', reservation='manual',
        )
        wizard = self.env['buz.loan.return.create.wizard'].create({
            'company_id': self.company.id,
            'document_kind': 'loan',
            'operation_type_id': operation_type.id,
            'partner_id': self.partner.id,
        })

        with self.assertRaises(ValidationError):
            wizard.action_create_document()