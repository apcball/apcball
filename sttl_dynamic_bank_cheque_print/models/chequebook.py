from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class ChequeBook(models.Model):
    _name = 'cheque.book'
    _description = "Bank Cheque Book"

    @api.constrains('account_number')
    def _check_account_number_numeric(self):
        for record in self:
            if record.account_number and not record.account_number.isdigit():
                raise ValidationError("account number must contain only digits.")

    name = fields.Char(string="Name", required=True)
    bank_id = fields.Many2one('bank.cheque', string="Bank Cheque", required=True)
    account_number = fields.Char(string="Account Number", required=True)
    total_leaves = fields.Integer(string="Total Leaves", required=True)
    cheque_background = fields.Binary("Cheque Background Image", attachment=True)
    bank_cheque = fields.Char("Bank Cheque")
    pay_to = fields.Char("Pay To")
    cheque_from = fields.Integer(string="Cheque Number From")
    cheque_to = fields.Integer(string="Cheque Number To", compute="_compute_cheque_to", store=True)

    cheque_date = fields.Date("Date")

    is_from_date_readonly = fields.Boolean("From Date Readonly")
    is_to_date_readonly = fields.Boolean("To Date Readonly")

    cheque_leaf_ids = fields.One2many('cheque.leaf', 'cheque_book_id', string="Cheque Leaves")

    issued_cheques = fields.Integer(string="Issued Cheques", compute="_compute_issued_cheques", store=True)
    is_total_leaves_read_only = fields.Boolean("Read only leaves")

    @api.constrains('cheque_from')
    def _check_cheque_from_required(self):
        for record in self:
            if not record.cheque_from:
                raise ValidationError("Please fill in the 'Cheque Number From' field before saving.")

    @api.depends('cheque_from', 'total_leaves')
    def _compute_cheque_to(self):
        """ Auto-sets the cheque_to field based on total_leaves """
        for record in self:
            if record.cheque_from and record.total_leaves:
                record.cheque_to = record.cheque_from + record.total_leaves - 1

    @api.model
    def create(self, vals):
        """ Automatically create cheque leaves when a cheque book is created """
        cheque_book = super(ChequeBook, self).create(vals)
        # cheque_book.is_total_leaves_read_only = True
        cheque_book.write({
            'is_total_leaves_read_only': True,
            'is_from_date_readonly': True,
            'is_to_date_readonly': True
        })
        if cheque_book.cheque_from and cheque_book.total_leaves:
            cheque_leaves = []
            for number in range(cheque_book.cheque_from, cheque_book.cheque_to + 1):
                cheque_leaves.append({
                    'name': f'Cheque {number}',
                    'number': str(number),
                    'cheque_book_id': cheque_book.id,
                })
            cheque_book.cheque_leaf_ids = [(0, 0, leaf) for leaf in cheque_leaves]

        return cheque_book

    @api.depends('cheque_leaf_ids')
    def _compute_issued_cheques(self):
        """ Compute the number of issued cheques """
        for record in self:
            record.issued_cheques = len(record.cheque_leaf_ids.filtered(lambda c: c.pay_to))


class BankChequeLeaf(models.Model):
    _name = 'cheque.leaf'
    _description = "Bank Cheque Leaf"
    _rec_name = 'number'

    name = fields.Char(string="Name", required=True)
    number = fields.Char(string="Cheque Number", required=True)
    payee_name = fields.Char(string="Payee Name", default=False)
    amount = fields.Float(string="Amount")
    date = fields.Date(string="Date", default=False)
    is_used = fields.Boolean(string="Used", default=False)
    pay_to = fields.Char("Pay To")
    cheque_book_id = fields.Many2one('cheque.book', string="Cheque Book", ondelete='cascade')
