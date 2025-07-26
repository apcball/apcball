# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    # Tax Invoice Sequence (keep for backward compatibility)
    taxinv_sequence_id = fields.Many2one(
        comodel_name="ir.sequence",
        string="Tax Invoice Sequence",
        help="Optional sequence as Tax Invoice number",
        copy=False,
    )
    sequence_number_next = fields.Integer(
        string="Next Number",
        help="The next sequence number will be used for the next tax invoice.",
        compute="_compute_seq_number_next",
        inverse="_inverse_seq_number_next",
    )
    
    # Withholding Tax fields (adapted for Odoo 17)
    is_withholding_tax = fields.Boolean(
        string="Is Withholding Tax",
        help="Check this if this tax is a withholding tax",
        default=False,
    )
    withholding_tax_type = fields.Selection([
        ('income', 'Income Tax'),
        ('vat', 'VAT Withholding'),
        ('pit', 'Personal Income Tax'),
    ], string="Withholding Tax Type")
    
    withholding_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Withholding Account",
        help="Account for withholding tax payable",
    )
    
    wht_cert_income_type = fields.Selection([
        ('1', 'เงินเดือน ค่าจ้าง เบี้ยเลี้ยง โบนัส ฯลฯ ตามมาตรา 40(1)'),
        ('2', 'ค่าธรรมเนียม ค่านายหน้า ค่าบริการ ค่าเช่า'),
        ('3', 'ค่าขนส่ง ค่าโฆษณา ค่าเบี้ยประกัน'),
        ('4', 'ดอกเบี้ย เงินปันผล'),
        ('5', 'ค่าสินค้า ค่าบริการอื่นๆ'),
    ], string="WHT Certificate Income Type")

    @api.depends(
        "taxinv_sequence_id.use_date_range", "taxinv_sequence_id.number_next_actual"
    )
    def _compute_seq_number_next(self):
        for tax in self:
            tax.sequence_number_next = 1
            if tax.taxinv_sequence_id:
                sequence = tax.taxinv_sequence_id._get_current_sequence()
                tax.sequence_number_next = sequence.number_next_actual

    def _inverse_seq_number_next(self):
        for tax in self:
            if tax.taxinv_sequence_id and tax.sequence_number_next:
                sequence = tax.taxinv_sequence_id._get_current_sequence()
                sequence.sudo().number_next = tax.sequence_number_next
