# -*- coding: utf-8 -*-
from odoo import models

_models = [
    'res_partner',
    'product_product',
    'pos_config',
    'pos_payment',
    'pos_session',
    'pos_order',
]

for _m in _models:
    __import__(_m, globals(), locals(), fromlist=[''], level=1)
