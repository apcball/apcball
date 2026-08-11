from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare


class BuzItInventoryStoreRequest(models.Model):
    _inherit = 'buz.it.inventory.item'

    @api.model
    def get_store_requester_summary(self):
        """Return the current user's name and department for the Store
        confirmation modal. Only the active user is referenced, never an ID
        passed from the frontend, and no sudo is used.
        """
        user = self.env.user
        employee = user.employee_id
        return {
            'requester_name': user.display_name or user.name or '',
            'department_name': (
                employee.department_id.name
                if employee and employee.department_id
                else False
            ),
        }

    @api.model
    def _create_store_request(self, lines, reason=None, require_reason=False):
        """Validate the Store cart lines and create one Draft Issue Request."""
        if not isinstance(lines, list) or not lines:
            raise UserError(_('Please add at least one item to the request.'))
        reason = (reason or '').strip()
        if require_reason and not reason:
            raise ValidationError(_('Please provide a reason for the request.'))

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

        return self.env['buz.it.issue.request'].create({
            'line_ids': request_lines,
            'reason': reason or False,
        })

    @api.model
    def action_create_store_request(self, lines):
        """Create one Draft issue request from the Store cart and open it."""
        request = self._create_store_request(lines)
        return {
            'name': _('Issue Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'buz.it.issue.request',
            'res_id': request.id,
            'view_mode': 'form',
            'views': [(self.env.ref('buz_it_inventory.view_issue_request_form').id, 'form')],
            'target': 'current',
        }

    @api.model
    def action_create_and_submit_store_request(self, lines, reason=None):
        """Create an Issue Request from the Store cart, submit it to IT and
        notify the IT agents. Returns a summary dict, not a form action."""
        request = self._create_store_request(lines, reason=reason, require_reason=True)
        activity_count = request.action_submit()
        return {
            'request_id': request.id,
            'request_name': request.name,
            'state': request.state,
            'activity_count': activity_count,
        }
