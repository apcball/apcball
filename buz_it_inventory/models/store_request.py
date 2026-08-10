from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class BuzItInventoryStoreRequest(models.Model):
    _inherit = 'buz.it.inventory.item'

    @api.model
    def action_create_store_request(self, lines):
        """Create one Draft issue request from the Store cart."""
        if not isinstance(lines, list) or not lines:
            raise UserError(_('Please add at least one item to the request.'))

        quantities = {}
        for line in lines:
            if not isinstance(line, dict):
                raise ValidationError(_('Invalid Store request line.'))
            try:
                item_id = int(line.get('item_id'))
                quantity = float(line.get('quantity'))
            except (TypeError, ValueError):
                raise ValidationError(_('Invalid Store request quantity.'))
            if item_id <= 0 or float_compare(quantity, 0.0, precision_digits=0) <= 0:
                raise ValidationError(_('Requested quantity must be greater than 0.'))
            quantities[item_id] = quantities.get(item_id, 0.0) + quantity

        items = self.browse(list(quantities)).exists()
        if len(items) != len(quantities):
            raise UserError(_('One or more selected items no longer exist.'))

        request_lines = []
        for item in items:
            if item.company_id != self.env.company:
                raise UserError(_('%s is not available for this company.') % item.display_name)
            if not item.active or not item.is_published:
                raise UserError(_('%s is not available in the Store.') % item.display_name)

            quantity = quantities[item.id]
            allowed = item.available_qty
            if item.max_per_request:
                allowed = min(allowed, item.max_per_request)
            if float_compare(quantity, allowed, precision_digits=0) > 0:
                raise UserError(_(
                    '%s has only %s %s available for this request.',
                    item.display_name, allowed, item.unit or '',
                ))
            request_lines.append(fields.Command.create({
                'item_id': item.id,
                'requested_qty': quantity,
            }))

        request = self.env['buz.it.issue.request'].create({'line_ids': request_lines})
        return {
            'name': _('Issue Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.issue.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }
