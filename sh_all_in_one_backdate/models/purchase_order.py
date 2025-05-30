# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    allow_backdate = fields.Boolean(
        string='Allow Backdate',
        compute='_compute_allow_backdate',
        help='Technical field to check if user can backdate this document'
    )
    
    @api.depends('state')
    def _compute_allow_backdate(self):
        """Check if user has permission to backdate"""
        has_backdate_permission = self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user')
        for record in self:
            record.allow_backdate = has_backdate_permission and record.state in ['purchase', 'done']
    
    def action_backdate_purchase_order(self):
        """Open backdate wizard for purchase order"""
        self.ensure_one()
        if not self.allow_backdate:
            raise AccessError(_('You do not have permission to backdate this document.'))
            
        return {
            'name': _('Backdate Purchase Order'),
            'type': 'ir.actions.act_window',
            'res_model': 'backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': self._name,
                'default_document_id': self.id,
                'default_current_date': self.date_order,
                'default_document_name': self.display_name,
            }
        }
    
    def backdate_document(self, new_date, reason=None):
        """Backdate the purchase order"""
        self.ensure_one()
        
        # Check permissions
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user'):
            raise AccessError(_('You do not have permission to backdate documents.'))
        
        # Validate date
        self._validate_backdate(new_date)
        
        # Store old date for logging
        old_date = self.date_order
        
        # Update purchase order date
        self.write({'date_order': new_date})
        
        # Log the backdate operation
        self.env['backdate.log'].log_backdate(self, old_date, new_date, reason)
        
        return True
    
    def _validate_backdate(self, new_date):
        """Validate backdate constraints"""
        # Convert string to datetime if needed
        if isinstance(new_date, str):
            try:
                new_date = fields.Datetime.from_string(new_date)
            except:
                new_date = fields.Date.from_string(new_date)
                new_date = fields.Datetime.combine(new_date, fields.Datetime.min.time())
        
        # Check date restrictions for non-managers
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_manager'):
            # Get company settings
            max_days_back = int(self.env['ir.config_parameter'].sudo().get_param(
                'sh_all_in_one_backdate.backdate_max_days', '30'
            ))
            
            if max_days_back > 0:
                from datetime import timedelta
                max_date = fields.Datetime.now() - timedelta(days=max_days_back)
                if new_date < max_date:
                    raise UserError(_('You cannot backdate more than %d days.') % max_days_back)
        
        # Check if date is in the future
        if new_date > fields.Datetime.now():
            raise UserError(_('You cannot set a future date.'))
        
        return True