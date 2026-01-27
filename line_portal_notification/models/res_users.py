# -*- coding: utf-8 -*-
"""
Extend res.users with LINE User ID
===================================

Adds LINE User ID field to user profiles for LINE notification delivery.
"""

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    line_user_id = fields.Char(
        string='LINE User ID',
        help="LINE User ID for receiving approval notifications. "
             "You can get this from LINE Official Account or LINE Login.",
        copy=False,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        """Allow users to read their own LINE ID."""
        return super().SELF_READABLE_FIELDS + ['line_user_id']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        """Allow users to write their own LINE ID."""
        return super().SELF_WRITEABLE_FIELDS + ['line_user_id']


class ResPartner(models.Model):
    """Also add LINE User ID to partner for flexibility."""
    _inherit = 'res.partner'

    line_user_id = fields.Char(
        string='LINE User ID',
        help="LINE User ID for receiving notifications.",
        copy=False,
    )
