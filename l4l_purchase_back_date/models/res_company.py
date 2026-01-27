# -*- coding: utf-8 -*-
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2023 Leap4Logic Solutions PVT LTD
#    Email : sales@leap4logic.com
#################################################

from odoo import api, models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'
    
    l4l_allow_back_date = fields.Boolean('Allow Back Date')
    
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
