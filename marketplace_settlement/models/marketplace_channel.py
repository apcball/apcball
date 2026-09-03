from odoo import api, fields, models


def trade_channel_selection(env):
    """Dynamic selection provider for every ``trade_channel`` field.

    Returns the list of ``(code, name)`` tuples from active ``marketplace.channel``
    records so users can add channels without a code change.
    """
    return env['marketplace.channel'].get_selection()


class MarketplaceChannel(models.Model):
    _name = 'marketplace.channel'
    _description = 'Marketplace Trade Channel'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help='Stored key on Trade Channel fields. Lowercase, no spaces.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Trade Channel code must be unique.'),
    ]

    @api.model
    def get_selection(self):
        return [(c.code, c.name) for c in self.search([])]
