from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    mo_filter_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
    )
    mo_filter_date_from = fields.Date(string='MO Date From')
    mo_filter_date_to = fields.Date(string='MO Date To')
    mo_filter_state = fields.Selection(
        selection=[
            ('confirmed', 'Confirmed'),
            ('progress', 'In Progress'),
            ('to_close', 'To Close'),
            ('done', 'Done'),
        ],
        string='MO Status',
        default='done',
    )
    mo_filter_mode = fields.Selection(
        selection=[
            ('replace', 'Replace Existing MOs'),
            ('add', 'Add to Existing MOs'),
        ],
        string='Selection Mode',
        default='replace',
        required=True,
    )

    @api.model
    def _get_mo_filter_date_field(self):
        """Return the production date field used by the search helper."""
        return 'date_finished'

    def _mo_filter_boundary_utc(self, value, end=False):
        """Convert a user's local date boundary to an Odoo UTC-naive datetime."""
        boundary = datetime.combine(value, time.max if end else time.min)
        timezone = pytz.timezone(self.env.context.get('tz') or self.env.user.tz or 'UTC')
        localized = timezone.localize(boundary)
        if end:
            # Date To is exclusive: use the next local midnight.
            next_day = datetime.combine(value, time.min) + timedelta(days=1)
            localized = timezone.localize(next_day)
        return localized.astimezone(pytz.UTC).replace(tzinfo=None)

    def action_search_manufacturing_orders(self):
        """Find accessible MOs and put them into the existing Landed Cost field."""
        self.ensure_one()
        if self.state != 'draft' or self.target_model != 'manufacturing':
            raise UserError(_(
                'Manufacturing Orders can only be searched on a draft manufacturing Landed Cost.'
            ))
        if not self.mo_filter_analytic_account_id:
            raise UserError(_(
                'Please select an Analytic Account before searching for manufacturing orders.'
            ))
        if not self.mo_filter_date_from or not self.mo_filter_date_to:
            raise UserError(_('Please specify both MO Date From and MO Date To.'))
        if self.mo_filter_date_from > self.mo_filter_date_to:
            raise ValidationError(_('MO Date From cannot be later than MO Date To.'))

        date_field = self._get_mo_filter_date_field()
        productions = self.env['mrp.production'].search([
            ('company_id', '=', self.company_id.id),
            ('analytic_account_ids', 'in', self.mo_filter_analytic_account_id.id),
            ('state', '=', self.mo_filter_state),
            (
                date_field,
                '>=',
                self._mo_filter_boundary_utc(self.mo_filter_date_from),
            ),
            (
                date_field,
                '<',
                self._mo_filter_boundary_utc(self.mo_filter_date_to, end=True),
            ),
        ], order=f'{date_field} asc, name asc')

        if not productions:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Manufacturing Orders Found'),
                    'message': _(
                        'No manufacturing orders matched the selected analytic account and date range.'
                    ),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        if self.mo_filter_mode == 'add':
            productions |= self.mrp_production_ids
        self.mrp_production_ids = [fields.Command.set(productions.ids)]
        # The object method updates the record on the server, but the form view
        # still holds the old one2many cache. Reload it so selected MOs appear
        # immediately after clicking Search.
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
