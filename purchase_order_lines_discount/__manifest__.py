# -*- coding: utf-8 -*-
{
    'name': "buz Purchase Discount|Purchase Fixed Discount|Purchase Percentage Discount",

    'summary': """
        Fixed Discount|Percentage Discount On Purchase Order Lines
        """,

    'description': """
        Adding a new custom fixed discount by amount and percentage discount fields on Purchase Order Lines. 
        If you add a value by percentage it will automatically calculate the fixed amount for it, and vice versa.
    """,

    'images': ["static/description/main_banner.png"],
    'author': "Sayed Hassan",
    'version': '17.0',
    'license': "AGPL-3",
    'category': "Purchase Management",


    # any module necessary for this one to work correctly
    'depends': ['base', 'purchase'],

    # always loaded
    'data': [
        'views/purchase_order_view.xml',
    ]
}
