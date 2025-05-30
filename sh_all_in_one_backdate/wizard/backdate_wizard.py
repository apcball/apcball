# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class BackdateWizard(models.TransientModel):
    _name = 'backdate.wizard'
    _description = 'Backdate Wizard'

    document_model = fields.Char(string='Document Model', required=True)
    document_id = fields.Integer(string='Document ID', required=True)
    document_name = fields.Char(string='Document', readonly=True)
    current_date = fields.Datetime(string='Current Date', readonly=True)
    new_date = fields.Datetime(string='New Date', required=True)
    reason = fields.Text(string='Reason', help='Reason for backdating this document')
    require_reason = fields.Boolean(string='Require Reason', compute='_compute_require_reason')
    
    @api.depends()
    def _compute_require_reason(self):
        """Check if reason is required"""
        require_reason = self.env['ir.config_parameter'].sudo().get_param(
            'sh_all_in_one_backdate.backdate_require_reason', 'True'
        ) == 'True'
        for record in self:
            record.require_reason = require_reason
    
    @api.onchange('new_date')
    def _onchange_new_date(self):
        """Validate new date on change"""
        if self.new_date:
            # Check if date is in the future
            if self.new_date > fields.Datetime.now():
                raise ValidationError(_('You cannot set a future date.'))
            
            # Check date restrictions for non-managers
            if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_manager'):
                max_days_back = int(self.env['ir.config_parameter'].sudo().get_param(
                    'sh_all_in_one_backdate.backdate_max_days', '30'
                ))
                
                if max_days_back > 0:
                    from datetime import timedelta
                    max_date = fields.Datetime.now() - timedelta(days=max_days_back)
                    if self.new_date < max_date:
                        raise ValidationError(_('You cannot backdate more than %d days.') % max_days_back)
    
    def action_backdate(self):
        """Execute the backdate operation"""
        self.ensure_one()
        
        # Validate reason if required
        if self.require_reason and not self.reason:
            raise UserError(_('Please provide a reason for backdating this document.'))
        
        # Get the document
        document = self.env[self.document_model].browse(self.document_id)
        if not document.exists():
            raise UserError(_('Document not found.'))
        
        # Check if backdating is enabled for this document type
        self._check_backdate_enabled()
        
        # Execute backdate
        try:
            document.backdate_document(self.new_date, self.reason)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Document has been backdated successfully.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            raise UserError(_('Error while backdating document: %s') % str(e))
    
    def _check_backdate_enabled(self):
        """Check if backdating is enabled for this document type"""
        config_map = {
            'account.move': 'sh_all_in_one_backdate.backdate_enable_invoice',
            'account.payment': 'sh_all_in_one_backdate.backdate_enable_payment',
            'sale.order': 'sh_all_in_one_backdate.backdate_enable_sale',
            'purchase.order': 'sh_all_in_one_backdate.backdate_enable_purchase',
            'stock.picking': 'sh_all_in_one_backdate.backdate_enable_picking',
            'account.bank.statement': 'sh_all_in_one_backdate.backdate_enable_statement',
            'account.bank.statement.line': 'sh_all_in_one_backdate.backdate_enable_statement',
        }
        
        config_param = config_map.get(self.document_model)
        if config_param:
            enabled = self.env['ir.config_parameter'].sudo().get_param(config_param, 'True') == 'True'
            if not enabled:
                raise UserError(_('Backdating is not enabled for this document type.'))
    
    @api.model
    def default_get(self, fields_list):
        """Set default values from context"""
        res = super().default_get(fields_list)
        
        # Get values from context
        res.update({
            'document_model': self.env.context.get('default_document_model'),
            'document_id': self.env.context.get('default_document_id'),
            'document_name': self.env.context.get('default_document_name'),
            'current_date': self.env.context.get('default_current_date'),
            'new_date': self.env.context.get('default_current_date'),
        })
        
        return res