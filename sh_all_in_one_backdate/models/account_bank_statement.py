# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    allow_backdate = fields.Boolean(
        string='Allow Backdate',
        compute='_compute_allow_backdate',
        help='Technical field to check if user can backdate this document'
    )
    
    @api.depends()
    def _compute_allow_backdate(self):
        """Check if user has permission to backdate"""
        has_backdate_permission = self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user')
        for record in self:
            # Check if statement is validated/posted (different field name in different versions)
            is_posted = getattr(record, 'state', False) == 'posted' or getattr(record, 'is_valid', False)
            record.allow_backdate = has_backdate_permission and is_posted
    
    def action_backdate_statement(self):
        """Open backdate wizard for bank statement"""
        self.ensure_one()
        if not self.allow_backdate:
            raise AccessError(_('You do not have permission to backdate this document.'))
            
        return {
            'name': _('Backdate Bank Statement'),
            'type': 'ir.actions.act_window',
            'res_model': 'backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': self._name,
                'default_document_id': self.id,
                'default_current_date': self.date,
                'default_document_name': self.display_name,
            }
        }
    
    def backdate_document(self, new_date, reason=None):
        """Backdate the bank statement"""
        self.ensure_one()
        
        # Check permissions
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user'):
            raise AccessError(_('You do not have permission to backdate documents.'))
        
        # Validate date
        self._validate_backdate(new_date)
        
        # Store old date for logging
        old_date = self.date
        
        # Update statement date
        self.write({'date': new_date})
        
        # Update statement lines
        for line in self.line_ids:
            line.write({'date': new_date})
        
        # Log the backdate operation
        self.env['backdate.log'].log_backdate(self, old_date, new_date, reason)
        
        return True
    
    def _validate_backdate(self, new_date):
        """Validate backdate constraints"""
        # Convert string to date if needed
        if isinstance(new_date, str):
            try:
                new_date = fields.Date.from_string(new_date)
            except:
                new_date = fields.Datetime.from_string(new_date).date()
        elif hasattr(new_date, 'date'):
            new_date = new_date.date()
        
        # Check date restrictions for non-managers
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_manager'):
            # Get company settings
            max_days_back = int(self.env['ir.config_parameter'].sudo().get_param(
                'sh_all_in_one_backdate.backdate_max_days', '30'
            ))
            
            if max_days_back > 0:
                from datetime import timedelta
                max_date = fields.Date.today() - timedelta(days=max_days_back)
                if new_date < max_date:
                    raise UserError(_('You cannot backdate more than %d days.') % max_days_back)
        
        # Check if date is in the future
        if new_date > fields.Date.today():
            raise UserError(_('You cannot set a future date.'))
        
        # Check fiscal year lock
        if hasattr(self.company_id, 'fiscalyear_lock_date') and self.company_id.fiscalyear_lock_date:
            if new_date <= self.company_id.fiscalyear_lock_date:
                raise UserError(_('You cannot backdate to a locked fiscal period.'))
        
        return True


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    allow_backdate = fields.Boolean(
        string='Allow Backdate',
        compute='_compute_allow_backdate',
        help='Technical field to check if user can backdate this document'
    )
    
    @api.depends()
    def _compute_allow_backdate(self):
        """Check if user has permission to backdate"""
        has_backdate_permission = self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user')
        for record in self:
            # Check if statement is validated/posted
            is_posted = getattr(record.statement_id, 'state', False) == 'posted' or getattr(record.statement_id, 'is_valid', False)
            record.allow_backdate = has_backdate_permission and is_posted
    
    def action_backdate_statement_line(self):
        """Open backdate wizard for bank statement line"""
        self.ensure_one()
        if not self.allow_backdate:
            raise AccessError(_('You do not have permission to backdate this document.'))
            
        return {
            'name': _('Backdate Statement Line'),
            'type': 'ir.actions.act_window',
            'res_model': 'backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_model': self._name,
                'default_document_id': self.id,
                'default_current_date': self.date,
                'default_document_name': self.display_name,
            }
        }
    
    def backdate_document(self, new_date, reason=None):
        """Backdate the statement line"""
        self.ensure_one()
        
        # Check permissions
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user'):
            raise AccessError(_('You do not have permission to backdate documents.'))
        
        # Validate date
        self._validate_backdate(new_date)
        
        # Store old date for logging
        old_date = self.date
        
        # Update line date
        self.write({'date': new_date})
        
        # Log the backdate operation
        self.env['backdate.log'].log_backdate(self, old_date, new_date, reason)
        
        return True
    
    def _validate_backdate(self, new_date):
        """Validate backdate constraints"""
        # Convert string to date if needed
        if isinstance(new_date, str):
            try:
                new_date = fields.Date.from_string(new_date)
            except:
                new_date = fields.Datetime.from_string(new_date).date()
        elif hasattr(new_date, 'date'):
            new_date = new_date.date()
        
        # Check date restrictions for non-managers
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_manager'):
            # Get company settings
            max_days_back = int(self.env['ir.config_parameter'].sudo().get_param(
                'sh_all_in_one_backdate.backdate_max_days', '30'
            ))
            
            if max_days_back > 0:
                from datetime import timedelta
                max_date = fields.Date.today() - timedelta(days=max_days_back)
                if new_date < max_date:
                    raise UserError(_('You cannot backdate more than %d days.') % max_days_back)
        
        # Check if date is in the future
        if new_date > fields.Date.today():
            raise UserError(_('You cannot set a future date.'))
        
        return True