from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosLiteConfig(models.Model):
    _name = 'pos.lite.config'
    _description = 'POS Lite Configuration'
    _order = 'id desc'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        required=True,
        domain="[('company_id', '=', company_id)]",
        check_company=True,
    )
    location_id = fields.Many2one(
        'stock.location',
        string='Product Stock Location',
        domain="[('usage', '=', 'internal'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
        help='Location driven by this configuration: the POS Lite terminal reads '
             'product stock from here, and pickings source/return to this location. '
             'One config per (company, location). Leave empty only for legacy '
             'records — new/edited configs must set a location.',
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        help='Default cash/bank journal for POS Lite refund records',
        check_company=True,
    )
    branch_number = fields.Char(
        string='Branch Number',
        help='Thai tax branch number (e.g. 00000 for head office). Shown on receipts.',
    )
    phone = fields.Char(string='Phone', help='Phone number shown on receipt')
    vat_number = fields.Char(
        string='Tax ID Override',
        help='Override company VAT for receipt. Leave empty to use company VAT.',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Default Employee',
        domain="[('company_id', '=', company_id)]",
        check_company=True,
        help='Default employee for new sessions created from this config.',
    )
    out_picking_type_id = fields.Many2one(
        'stock.picking.type', string='Delivery Operation Type',
        domain="[('code', '=', 'outgoing'), ('company_id', '=', company_id)]",
        check_company=True,
        help='Stock operation type used for POS delivery orders. '
             'Leave empty to use the default outgoing type from the warehouse.',
    )
    return_picking_type_id = fields.Many2one(
        'stock.picking.type', string='Return Operation Type',
        domain="[('code', '=', 'incoming'), ('company_id', '=', company_id)]",
        check_company=True,
        help='Stock operation type used for POS return orders. '
             'Leave empty to use the default incoming type from the warehouse.',
    )
    default_trade_channel = fields.Selection(
        selection='_selection_trade_channel',
        string='Default Trade Channel',
        help='Default marketplace trade channel for new orders.',
    )
    marketplace_profile_id = fields.Many2one(
        'marketplace.settlement.profile',
        string='Marketplace Profile',
        domain="[('company_id', '=', company_id), ('active', '=', True)]",
        check_company=True,
        help='Marketplace profile to auto-set trade channel and accounting defaults.',
    )

    @api.model
    def _selection_trade_channel(self):
        """Dynamic selection mirroring sale.order.trade_channel (injected by marketplace_settlement)."""
        from .pos_order import _get_trade_channel_selection
        return _get_trade_channel_selection(self)

    @api.onchange('marketplace_profile_id')
    def _onchange_marketplace_profile_id(self):
        if self.marketplace_profile_id:
            self.default_trade_channel = self.marketplace_profile_id.trade_channel

    @api.model
    def get_default_config(self, company=None):
        company = company or self.env.company
        return self.search([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ], order='id desc', limit=1)

    @api.model
    def get_config_for_location(self, location_id, company=None):
        """Return the active config bound to a given stock.location.

        With per-location configuration, the location is the primary key of a
        config; this helper resolves it for sessions/orders that already know
        which location they operate from.
        """
        if not location_id:
            return self.env['pos.lite.config']
        company = company or self.env.company
        return self.search([
            ('company_id', '=', company.id),
            ('location_id', '=', location_id),
            ('active', '=', True),
        ], order='id desc', limit=1)

    @api.constrains('company_id', 'location_id')
    def _check_location_required(self):
        """A config must be bound to exactly one stock.location.

        Enforced at the application layer (not as a NOT NULL column) so legacy
        rows without a location keep loading until they are edited/backfilled.
        """
        for config in self:
            if not config.location_id:
                raise ValidationError(_(
                    'POS Lite Configuration "%(name)s" must specify a Product Stock '
                    'Location. Each location requires its own configuration.'
                ) % {'name': config.name or config.display_name})

    @api.constrains('company_id', 'location_id')
    def _check_location_unique(self):
        """At most one config per (company, location).

        Enforced in Python (rather than via `_sql_constraints`) so the failure
        surfaces as a clean, translated ValidationError instead of a raw
        psycopg2 UniqueViolation. Runs after the INSERT but before commit, so
        the duplicate create still rolls back.
        """
        for config in self:
            if not config.location_id:
                continue
            duplicate = self.sudo().search([
                ('id', '!=', config.id),
                ('company_id', '=', config.company_id.id),
                ('location_id', '=', config.location_id.id),
            ], limit=1)
            if duplicate:
                raise ValidationError(_(
                    'A POS Lite Configuration already exists for location '
                    '"%(location)s" in company %(company)s. '
                    'Each location may have only one configuration.'
                ) % {
                    'location': config.location_id.display_name,
                    'company': config.company_id.display_name,
                })
