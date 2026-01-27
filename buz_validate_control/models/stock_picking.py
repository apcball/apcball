# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import AccessError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        """Override to add security check for validation"""
        if not self.env.user.has_group('buz_validate_control.group_validate_privileged'):
            raise AccessError(_("You don't have permission to validate stock transfers. Please contact your administrator."))
        
        return super(StockPicking, self).button_validate()