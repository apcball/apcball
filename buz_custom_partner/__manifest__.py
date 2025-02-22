{
    'name': 'Custom Partner Code',
    'version': '1.0',
    'category': 'Customizations',
    'summary': 'Add Partner Code to res.partner',
    'depends': ['base', 'contacts'],
    'data': [
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
}