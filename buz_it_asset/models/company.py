from psycopg2.errors import UniqueViolation

from odoo import api, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _ensure_it_asset_sequence(self, asset_type):
        """Return one yearly-resetting IT Asset sequence per company/type."""
        self.ensure_one()
        asset_type.ensure_one()
        sequence_model = self.env['ir.sequence'].sudo()
        code = 'buz.it.asset.type.%s' % asset_type.id
        sequence = sequence_model.search([
            ('code', '=', code),
            ('company_id', '=', self.id),
        ], limit=1)
        values = {
            'name': _('IT Asset - %s - %s') % (asset_type.name, self.name),
            'code': code,
            'prefix': '%s/%%(year)s/%%(month)s/' % asset_type.asset_prefix,
            'padding': 4,
            'company_id': self.id,
            'use_date_range': True,
        }
        if sequence:
            current_values = {
                'name': sequence.name,
                'code': sequence.code,
                'prefix': sequence.prefix,
                'padding': sequence.padding,
                'company_id': sequence.company_id.id,
                'use_date_range': sequence.use_date_range,
            }
            changes = {
                key: value for key, value in values.items()
                if current_values[key] != value
            }
            if changes:
                sequence.write(changes)
        else:
            sequence = sequence_model.create(values)
        return sequence

    def _next_it_asset_tag(self, asset_type, sequence_date):
        """Return the next tag and surface date-range races as retryable."""
        self.ensure_one()
        sequence = self._ensure_it_asset_sequence(asset_type)
        try:
            with self.env.cr.savepoint():
                return sequence._next(sequence_date=sequence_date)
        except UniqueViolation:
            # Odoo converts an IntegrityError to a validation error instead of
            # retrying the request. Raise a database serialization failure so
            # the standard request retry loop starts a transaction with a new
            # snapshot that can see the date range created by the winner.
            self.env.cr.execute("""
                DO $$
                BEGIN
                    RAISE EXCEPTION
                        'Concurrent IT Asset sequence date-range creation'
                        USING ERRCODE = '40001';
                END
                $$
            """)

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            for asset_type in self.env['buz.it.asset.type'].sudo().search([]):
                company._ensure_it_asset_sequence(asset_type)
        return companies
