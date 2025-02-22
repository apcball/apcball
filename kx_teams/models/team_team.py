# -*- coding: utf-8 -*-
from odoo import api, fields, models, _, exceptions


class Team(models.Model):
    _name = "team.team"

    name = fields.Char(string="Teams", required=True)
    user_id = fields.Many2one('res.users', string="Team Leader", required=True)
    sequence = fields.Integer('Sequence')
    model_ids = fields.Many2many('approval.model', string='Model')
    company_ids = fields.Many2many('res.company', default=lambda self: self.env.company.ids)
    member_ids = fields.Many2many('res.users')
    approvars_ids = fields.One2many('approvals.approvals', 'approver_id')
    active = fields.Boolean(string="Active", default=True)

    company_currency_id = fields.Many2one('res.currency', related='company_ids.currency_id', string="Company Currency", readonly=True)

    approval = fields.Boolean(
        "Based on amount", related='company_ids.approval', help="Apply approval for sales, invoice, purchase based on amount",
        readonly=False
    )

    approval_validation_amount = fields.Monetary(
        related='company_ids.approval_validation_amount',
        string="Minimum Amount",
        currency_field='company_currency_id',
        readonly=False,
    )

    def _reorder_sequence(self):
        records = self.approvars_ids.search([], order='sequence')
        sequence = 1
        for record in records:
            record.sequence = sequence
            sequence += 1

    def write(self, vals):
        res = super(Team, self).write(vals)
        if 'approvars_ids' in vals:
            self._reorder_sequence()
        return res

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id:
            existing_member_ids = [member.id for member in self.member_ids if member.id != self.user_id.id]
            existing_member_ids.append(self.user_id.id)
            self.member_ids = [(6, 0, existing_member_ids)]

    @api.model
    def create(self, vals):
        if 'model_ids' not in vals:
            model_ids = []

            # ตรวจสอบโมดูลที่เกี่ยวข้อง
            if self.env['ir.module.module'].search([('name', '=', 'purchase')]):
                purchase_model = self.env.ref('purchase.model_purchase_order', raise_if_not_found=False)
                if purchase_model:
                    model_ids.append(purchase_model.id)

            if self.env['ir.module.module'].search([('name', '=', 'sale')]):
                sale_model = self.env.ref('sale.model_sale_order', raise_if_not_found=False)
                if sale_model:
                    model_ids.append(sale_model.id)

            if self.env['ir.module.module'].search([('name', '=', 'account')]):
                account_model = self.env.ref('account.model_account_move', raise_if_not_found=False)
                if account_model:
                    model_ids.append(account_model.id)

            if model_ids:
                vals['model_ids'] = [(6, 0, model_ids)]

        return super(Team, self).create(vals)