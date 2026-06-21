from odoo import fields, models


class ITRequestCategory(models.Model):
    _name = 'it.request.category'
    _description = 'IT Request Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    sub_category_ids = fields.One2many(
        comodel_name='it.request.sub.category',
        inverse_name='category_id',
        string='Sub-categories',
    )


class ITRequestSubCategory(models.Model):
    _name = 'it.request.sub.category'
    _description = 'IT Request Sub-Category'
    _order = 'sequence, name'

    name = fields.Char(string='Sub-Category', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    category_id = fields.Many2one(
        comodel_name='it.request.category',
        string='Category',
        required=True,
        ondelete='cascade',
        index=True,
    )


class ITRequestTeam(models.Model):
    _name = 'it.request.team'
    _description = 'IT Request Team'
    _order = 'sequence, name'

    name = fields.Char(string='Team', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    member_ids = fields.Many2many(
        comodel_name='res.users',
        relation='it_request_team_user_rel',
        column1='team_id',
        column2='user_id',
        string='Members',
    )
    leader_id = fields.Many2one(
        comodel_name='res.users',
        string='Team Leader',
    )
