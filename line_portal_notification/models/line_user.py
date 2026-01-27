# -*- coding: utf-8 -*-
"""
LINE User Mapping Model
=======================

Master data model for mapping LINE User IDs to Odoo Users or Employees.
LINE User IDs are automatically captured via webhook and can be manually
linked to Odoo users/employees by admin.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

import logging

_logger = logging.getLogger(__name__)


class LineUser(models.Model):
    _name = 'line.user'
    _description = 'LINE User Mapping'
    _order = 'last_event_date desc, id desc'
    _rec_name = 'display_name'

    line_user_id = fields.Char(
        string='LINE User ID',
        required=True,
        index=True,
        copy=False,
        help="The unique LINE User ID. Always starts with 'U' and is 33 characters long.",
    )
    display_name = fields.Char(
        string='Display Name',
        help="LINE display name of the user (if available from profile API).",
    )
    user_id = fields.Many2one(
        'res.users',
        string='Odoo User',
        ondelete='set null',
        help="Link this LINE user to an Odoo user for notifications.",
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        ondelete='set null',
        help="Link this LINE user to an employee for notifications.",
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help="Inactive LINE users will not receive notifications.",
    )
    last_event_date = fields.Datetime(
        string='Last Event Date',
        readonly=True,
        help="The last time a webhook event was received from this LINE user.",
    )
    event_count = fields.Integer(
        string='Event Count',
        default=0,
        readonly=True,
        help="Total number of webhook events received from this LINE user.",
    )
    notes = fields.Text(
        string='Notes',
        help="Internal notes about this LINE user.",
    )

    _sql_constraints = [
        ('line_user_id_unique', 'UNIQUE(line_user_id)',
         'LINE User ID must be unique. This LINE user already exists.'),
    ]

    @api.constrains('line_user_id')
    def _check_line_user_id_format(self):
        """Validate LINE User ID format."""
        import re
        for record in self:
            if record.line_user_id:
                # LINE User ID should start with U, C, or R and be 33 chars
                if not re.match(r'^[UCR][0-9a-fA-F]{32}$', record.line_user_id):
                    raise ValidationError(_(
                        "Invalid LINE User ID format: '%s'. "
                        "LINE User ID should start with 'U' (user), 'C' (group), or 'R' (room) "
                        "followed by 32 hexadecimal characters (total 33 characters)."
                    ) % record.line_user_id)

    def name_get(self):
        """Custom name display."""
        result = []
        for record in self:
            if record.display_name:
                name = f"{record.display_name} ({record.line_user_id[:10]}...)"
            else:
                name = record.line_user_id[:15] + '...'
            result.append((record.id, name))
        return result

    def toggle_active(self):
        """Toggle active status."""
        for record in self:
            record.active = not record.active

    @api.model
    def find_or_create_from_webhook(self, line_user_id, display_name=None):
        """
        Find or create a LINE user record from webhook event.
        
        Args:
            line_user_id: The LINE User ID from webhook
            display_name: Optional display name
            
        Returns:
            line.user record
        """
        if not line_user_id:
            return self.browse()
        
        # Search for existing record
        existing = self.sudo().search([('line_user_id', '=', line_user_id)], limit=1)
        
        if existing:
            # Update last event date
            existing.sudo().write({
                'last_event_date': fields.Datetime.now(),
                'event_count': existing.event_count + 1,
            })
            if display_name and not existing.display_name:
                existing.sudo().write({'display_name': display_name})
            _logger.info("Updated LINE user: %s", line_user_id[:10] + '...')
            return existing
        else:
            # Create new record
            vals = {
                'line_user_id': line_user_id,
                'last_event_date': fields.Datetime.now(),
                'event_count': 1,
            }
            if display_name:
                vals['display_name'] = display_name
            
            new_record = self.sudo().create(vals)
            _logger.info("Created new LINE user: %s", line_user_id[:10] + '...')
            return new_record

    @api.model
    def get_line_user_id_for(self, user=None, employee=None):
        """
        Get LINE User ID for a given Odoo user or employee.
        
        Args:
            user: res.users record
            employee: hr.employee record
            
        Returns:
            str: LINE User ID or None
        """
        domain = [('active', '=', True)]
        
        if user:
            domain.append(('user_id', '=', user.id))
        elif employee:
            domain.append(('employee_id', '=', employee.id))
        else:
            return None
        
        line_user = self.sudo().search(domain, limit=1)
        return line_user.line_user_id if line_user else None

    @api.model
    def send_line_message(self, recipient, message):
        """
        Send a LINE message to an Odoo user or employee.
        
        This is the main service method for sending LINE notifications.
        It resolves the LINE User ID from the mapping and sends the message.
        
        Args:
            recipient: res.users or hr.employee record (or recordset)
            message: String message to send
            
        Returns:
            dict: Result with success/failure info for each recipient
        """
        if not recipient:
            raise UserError(_("Recipient is required to send a LINE message."))
        
        if not message:
            raise UserError(_("Message is required."))
        
        LineApiService = self.env['line.api.service']
        results = {'success': [], 'failed': [], 'skipped': []}
        
        # Handle both single and multiple recipients
        for rec in recipient:
            try:
                # Determine if it's a user or employee
                if rec._name == 'res.users':
                    line_user_id = self.get_line_user_id_for(user=rec)
                    recipient_name = rec.name
                elif rec._name == 'hr.employee':
                    line_user_id = self.get_line_user_id_for(employee=rec)
                    recipient_name = rec.name
                else:
                    _logger.warning("Unsupported recipient type: %s", rec._name)
                    results['skipped'].append({
                        'name': str(rec),
                        'reason': 'Unsupported recipient type',
                    })
                    continue
                
                if not line_user_id:
                    # Check if user/employee has direct line_user_id field
                    if hasattr(rec, 'line_user_id') and rec.line_user_id:
                        line_user_id = rec.line_user_id
                    else:
                        results['skipped'].append({
                            'name': recipient_name,
                            'reason': 'No LINE User ID mapping found',
                        })
                        continue
                
                # Check if mapping is active
                mapping = self.sudo().search([
                    ('line_user_id', '=', line_user_id),
                    ('active', '=', True),
                ], limit=1)
                
                if not mapping and not (hasattr(rec, 'line_user_id') and rec.line_user_id):
                    results['skipped'].append({
                        'name': recipient_name,
                        'reason': 'LINE User mapping is inactive',
                    })
                    continue
                
                # Send the message
                LineApiService.send_push_message(line_user_id, message)
                results['success'].append({
                    'name': recipient_name,
                    'line_user_id': line_user_id[:10] + '...',
                })
                
            except UserError as e:
                results['failed'].append({
                    'name': recipient_name if 'recipient_name' in dir() else str(rec),
                    'error': str(e),
                })
            except Exception as e:
                _logger.exception("Error sending LINE message")
                results['failed'].append({
                    'name': recipient_name if 'recipient_name' in dir() else str(rec),
                    'error': str(e),
                })
        
        return results
