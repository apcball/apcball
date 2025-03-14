# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
{
    'name': "buz Import Template For Sales / Purchase / Invoice",
    'version': '17.0.1.0.0',
    'category': 'Sales, Purchases, Accounting',
    'summary': """ Download Import Templates for Sales, Purchase and Invoice """,
    'description': """ Download and import the templates for sales order, 
    purchase order and invoice or bills """,
    'author': "Cybrosys Techno Solutions",
    'website': "https://apps.odoo.com/apps/modules/18.0/import_user_excel",
    'company': 'Cybrosys Techno Solutions',
    'maintainer': 'Cybrosys Techno Solutions',
    'images': ['static/description/banner.jpg'],
    'depends': ['base', 'sale_management', 'account', 'purchase'],
    'license': 'AGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
