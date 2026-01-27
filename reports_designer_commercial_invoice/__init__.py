# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

def pre_init_check(env):
    from odoo.service import common
    from odoo.exceptions import ValidationError
    version_info = common.exp_version()
    server_serie = version_info.get('server_serie')
    if server_serie != '17.0':
        raise ValidationError('Module support Odoo Version 17.0, found {}.'.format(server_serie))
    reports_designer  = env['ir.module.module'].sudo().search([('name', '=', 'reports_designer')])    
    if not len(reports_designer) or reports_designer.state != "installed":
        raise ValidationError('This Module requires the installed module "Report Designer (XLSX, XLSM)". Please install the module!')    
    if int(''.join([str(100+int(d)) for d in  reports_designer.installed_version.split('.')[2:]])) < 101104100:
        raise ValidationError('Module support "Report Designer (XLSX, XLSM)" module starting from Version 1.4.0, found Version {}. Please update the module "Report Designer (XLSX, XLSM)".'.format('.'.join(reports_designer.installed_version.split('.')[2:])))
    return True