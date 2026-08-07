{
    'name': 'Transfer Employee/Department',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Stock Management',
    'summary': 'Show Employee and Department on Internal Transfer, derived from Responsible',
    'description': """
Transfer Employee/Department
=============================
Adds Employee and Department fields to stock.picking (Transfer), derived
from the Responsible (user_id) field's linked hr.employee record.

- Form view: shows Employee/Department in the Additional Info > Other
  Information group, next to Responsible.
- Tree view: adds Employee/Department as optional columns.
""",
    'author': 'BUZ',
    'website': 'https://www.buz.co.th',
    'license': 'LGPL-3',
    'depends': ['stock', 'hr'],
    'data': [
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
