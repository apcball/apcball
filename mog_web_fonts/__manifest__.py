{
    "name": "MOG Web Fonts",
    "version": "17.0.1.0.0",
    "author": "MOG / Ball",
    "depends": ["web", "website", "web_editor"],
    "assets": {
    "web.assets_frontend": [],
        # โหลดเวลาเปิด WYSIWYG/Website Editor
        # Load our custom editor fonts script into the web editor assets
        # Load our custom editor fonts script into the web_editor assets
        "web_editor.assets_wysiwyg": [
            "mog_web_fonts/static/src/js/editor_fonts.js",
        ],
        # Also load the script in website editor bundle
        "website.assets_wysiwyg": [
            "mog_web_fonts/static/src/js/editor_fonts.js",
        ],
        # Ensure script is loaded in backend editor assets for both backend and website
        "web_editor.backend_assets_wysiwyg": [
            "mog_web_fonts/static/src/js/editor_fonts.js",
        ],
    },
    "license": "LGPL-3",
}