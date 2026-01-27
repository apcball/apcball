from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    po_reviewer_id = fields.Many2one('res.users', string='Default PO Reviewer')
    po_approver_id = fields.Many2one('res.users', string='PO Approver (Standard)')
    po_approver_limit = fields.Monetary(string='PO Approval Limit', default=50000.0)
    po_approver_above_limit_id = fields.Many2one('res.users', string='PO Approver (Above Limit)')
