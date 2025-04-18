from odoo import models, fields, tools

class BillingNotePaymentSummary(models.Model):
    _name = 'billing.note.payment.summary'
    _description = 'Billing Note Payment Summary'
    _auto = False
    _order = 'date desc'

    date = fields.Date(string='Date', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Partner', readonly=True)
    billing_note_id = fields.Many2one('billing.note', string='Billing Note', readonly=True)
    payment_id = fields.Many2one('account.payment', string='Payment', readonly=True)
    amount = fields.Monetary(string='Amount', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    note_type = fields.Selection([
        ('receivable', 'Customer Invoice'),
        ('payable', 'Vendor Bill')
    ], string='Type', readonly=True)
    payment_method_id = fields.Many2one('account.payment.method', string='Payment Method', readonly=True)
    journal_id = fields.Many2one('account.journal', string='Journal', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    bnp.id,
                    bn.date,
                    bn.partner_id,
                    bn.id as billing_note_id,
                    bnp.payment_id,
                    bnp.amount,
                    COALESCE(bn.currency_id, c.currency_id) as currency_id,
                    bn.company_id,
                    bn.note_type,
                    pml.payment_method_id as payment_method_id,
                    pml.journal_id
                FROM billing_note_payment bnp
                JOIN billing_note bn ON bn.id = bnp.billing_note_id
                JOIN res_company c ON c.id = bn.company_id
                LEFT JOIN account_payment p ON p.id = bnp.payment_id
                LEFT JOIN account_payment_method_line pml ON pml.id = p.payment_method_line_id
                WHERE bn.state != 'cancel'
            )
        """ % self._table)