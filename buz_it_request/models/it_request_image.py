from odoo import fields, models


class ITRequestImage(models.Model):
    _name = 'it.request.image'
    _description = 'IT Request Image'
    _order = 'sequence, id'

    name = fields.Char(string='Description')
    image = fields.Binary(
        string='Image',
        attachment=True,
        required=True,
    )
    it_request_id = fields.Many2one(
        comodel_name='it.request',
        string='IT Request',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)