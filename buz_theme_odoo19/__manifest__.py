{
    'name': 'Odoo 19 Backend Theme',
    'summary': 'Adapt Odoo 19 visual design for Odoo 17 backend',
    'description': '''
        Backend theme that adapts Odoo 19's modern visual design language
        to Odoo 17. Includes improved dark mode, configurable color variants,
        refreshed navbar, control panel, list/form views, and buttons.
        Compatible with both Community and Enterprise editions.
    ''',
    'version': '17.0.1.0.0',
    'category': 'Themes/Backend',
    'license': 'LGPL-3',
    'author': 'Mogen Co., Ltd.',
    'depends': [
        'web',
    ],
    'data': [
        'views/res_config_settings.xml',
    ],
    'assets': {
        'web._assets_primary_variables': [
            ('after', 'web/static/src/scss/primary_variables.scss', 'buz_theme_odoo19/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'buz_theme_odoo19/static/src/scss/navbar.scss',
            'buz_theme_odoo19/static/src/scss/control_panel.scss',
            'buz_theme_odoo19/static/src/scss/list_view.scss',
            'buz_theme_odoo19/static/src/scss/form_view.scss',
            'buz_theme_odoo19/static/src/scss/buttons.scss',
            'buz_theme_odoo19/static/src/scss/dialogs.scss',
            'buz_theme_odoo19/static/src/scss/base.scss',
            'buz_theme_odoo19/static/src/scss/dark_mode.scss',
            'buz_theme_odoo19/static/src/js/dark_mode.js',
        ],

    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
