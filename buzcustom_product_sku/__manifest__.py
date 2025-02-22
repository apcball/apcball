{
    'name': 'Custom Product SKU',
    'version': '1.0',
    'category': 'Custom',
    'summary': 'Adds SKU field to Product Template',
    'description': 'This module adds an SKU field below the Purchase UoM field on the product form.',
    'author': 'Your Name',
    'depends': ['product'],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
