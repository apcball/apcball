# Qwen Context File

**Date:** วันศุกร์ที่ 17 ตุลาคม 2568
**Operating System:** Linux
**Project Directory:** /opt/instance1/odoo17/custom-addons/buz_valuation_regenerate

## Project Overview
This appears to be an Odoo 17 custom addon called 'buz_valuation_regenerate'. It seems to be related to inventory valuation regeneration functionality with features like:
- Valuation regeneration with logging
- Rollback capabilities via wizard
- Server actions and menu items

## Folder Structure
```
├───__init__.py
├───__manifest__.py
├───README.md
├───SECURITY.md
├───data/
│   ├───menu.xml
│   └───server_actions.xml
├───i18n/
│   └───th.po
├───models/
│   ├───__init__.py
│   ├───valuation_regenerate_log.py
│   ├───valuation_regenerate_rollback_wizard.py
│   ├───valuation_regenerate_wizard.py
│   └───__pycache__/
├───__pycache__/
├───report/
├───security/
├───tests/
└───views/
```

## Key Components
- **Models:**
  - `valuation_regenerate_log.py` - Handles logging of regeneration activities
  - `valuation_regenerate_wizard.py` - Wizard for initiating valuation regeneration
  - `valuation_regenerate_rollback_wizard.py` - Wizard for rolling back valuations
- **Data:** Menu and server action configurations
- **Localization:** Thai language support