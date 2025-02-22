{
    'name': 'Product Kanban View Customization',
    'version': '1.0',
    'summary': 'Customize Product Kanban View to show Internal Reference and Product Name',
    'author': 'Your Name',
    'category': 'Product',
    'depends': ['product'],  # โมดูลนี้ต้องการโมดูล product
    'data': [
        'views/product_template_kanban_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}