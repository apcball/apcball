# -*- coding: utf-8 -*-
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2023 Leap4Logic Solutions PVT LTD
#    Email : sales@leap4logic.com
#################################################

from odoo import api, models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    l4l_allow_back_date = fields.Boolean(related='company_id.l4l_allow_back_date', readonly=False, string='Allow Purchase Back Date')
    
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
