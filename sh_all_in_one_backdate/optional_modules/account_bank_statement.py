# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError


class AccountBankStatement(models.Model):
    _inherit = 'account.bank.statement'

    allow_backdate = fields.Boolean(
        string='Allow Backdate',
        compute='_compute_allow_backdate',
        help='Indicates if this statement can be backdated'
    )

    @api.depends('state', 'date')
    def _compute_allow_backdate(self):
        """Compute if the statement can be backdated"""
        for statement in self:
            statement.allow_backdate = self._can_backdate()

    def _can_backdate(self):
        """Check if the current user can backdate this statement"""
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user'):
            return False
        
        # Allow backdating for draft and posted statements
        if self.state in ['draft', 'posted']:
            return True
        
        return False

    def _validate_backdate(self, new_date):
        """Validate if the backdate is allowed"""
        if not self._can_backdate():
            raise UserError("You don't have permission to backdate this statement.")
        
        # Get maximum backdate days from configuration
        max_days = int(self.env['ir.config_parameter'].sudo().get_param('backdate_max_days', 365))
        
        if max_days > 0:
            # Handle both date and datetime fields
            if isinstance(new_date, str):
                new_date = fields.Date.from_string(new_date)
            elif hasattr(new_date, 'date'):
                new_date = new_date.date()
            
            current_date = fields.Date.today()
            max_backdate = current_date - timedelta(days=max_days)
            
            if new_date < max_backdate:
                raise ValidationError(
                    f"Cannot backdate more than {max_days} days. "
                    f"Minimum allowed date is {max_backdate}."
                )

    def action_backdate_statement(self):
        """Open backdate wizard for this statement"""
        return {
            'name': 'Backdate Bank Statement',
            'type': 'ir.actions.act_window',
            'res_model': 'backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_id': self.id,
                'default_document_model': 'account.bank.statement',
                'default_current_date': self.date,
                'default_document_name': self.name or 'Bank Statement',
            }
        }

    def backdate_document(self, new_date, reason):
        """Backdate the statement to a new date"""
        self._validate_backdate(new_date)
        
        old_date = self.date
        
        # Update the statement date
        self.write({'date': new_date})
        
        # Create audit log
        self.env['backdate.log'].create({
            'document_model': 'account.bank.statement',
            'document_id': self.id,
            'document_name': self.name or 'Bank Statement',
            'old_date': old_date,
            'new_date': new_date,
            'reason': reason,
            'user_id': self.env.user.id,
        })
        
        return True


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    allow_backdate = fields.Boolean(
        string='Allow Backdate',
        compute='_compute_allow_backdate',
        help='Indicates if this statement line can be backdated'
    )

    @api.depends('statement_id.state', 'date')
    def _compute_allow_backdate(self):
        """Compute if the statement line can be backdated"""
        for line in self:
            line.allow_backdate = line._can_backdate()

    def _can_backdate(self):
        """Check if the current user can backdate this statement line"""
        if not self.env.user.has_group('sh_all_in_one_backdate.group_backdate_user'):
            return False
        
        # Allow backdating for lines in draft and posted statements
        if self.statement_id.state in ['draft', 'posted']:
            return True
        
        return False

    def _validate_backdate(self, new_date):
        """Validate if the backdate is allowed"""
        if not self._can_backdate():
            raise UserError("You don't have permission to backdate this statement line.")
        
        # Get maximum backdate days from configuration
        max_days = int(self.env['ir.config_parameter'].sudo().get_param('backdate_max_days', 365))
        
        if max_days > 0:
            # Handle both date and datetime fields
            if isinstance(new_date, str):
                new_date = fields.Date.from_string(new_date)
            elif hasattr(new_date, 'date'):
                new_date = new_date.date()
            
            current_date = fields.Date.today()
            max_backdate = current_date - timedelta(days=max_days)
            
            if new_date < max_backdate:
                raise ValidationError(
                    f"Cannot backdate more than {max_days} days. "
                    f"Minimum allowed date is {max_backdate}."
                )

    def action_backdate_statement_line(self):
        """Open backdate wizard for this statement line"""
        return {
            'name': 'Backdate Statement Line',
            'type': 'ir.actions.act_window',
            'res_model': 'backdate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_document_id': self.id,
                'default_document_model': 'account.bank.statement.line',
                'default_current_date': self.date,
                'default_document_name': f"Statement Line - {self.payment_ref or self.ref or 'No Ref'}",
            }
        }

    def backdate_document(self, new_date, reason):
        """Backdate the statement line to a new date"""
        self._validate_backdate(new_date)
        
        old_date = self.date
        
        # Update the statement line date
        self.write({'date': new_date})
        
        # Create audit log
        self.env['backdate.log'].create({
            'document_model': 'account.bank.statement.line',
            'document_id': self.id,
            'document_name': f"Statement Line - {self.payment_ref or self.ref or 'No Ref'}",
            'old_date': old_date,
            'new_date': new_date,
            'reason': reason,
            'user_id': self.env.user.id,
        })
        
        return True