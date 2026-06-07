def migrate(cr, version):
    old_selection_map = {
        'air': 'By Air',
        'sea': 'By Sea',
        'land': 'By Land',
    }
    for old_val, new_val in old_selection_map.items():
        cr.execute(
            "UPDATE sale_order SET shipping_by = %s WHERE shipping_by = %s",
            (new_val, old_val)
        )
        cr.execute(
            "UPDATE account_move SET shipping_by = %s WHERE shipping_by = %s",
            (new_val, old_val)
        )
