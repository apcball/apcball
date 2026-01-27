# Thai Localization - Withholding Tax Certificate Form Module (l10n_th_account_wht_cert_form)

## Module Overview
- **Name**: Thai Localization - Withholding Tax Certificate Form
- **Version**: 17.0.1.0.0
- **Author**: Ecosoft, Odoo Community Association (OCA)
- **License**: AGPL-3
- **Category**: Report
- **Development Status**: Beta
- **Maintainer**: Saran440

## Description
This module adds the Thailand standard withholding tax certificate report to the WHT Certificates menu. It provides a pre-formatted PDF report that follows the Thai withholding tax certificate standard layout.

### Key Features
1. **Standard Thai WHT Certificate Format**: Implements the official Thailand withholding tax certificate form layout
2. **A4 Paper Format**: Uses proper A4 paper format with custom settings for the certificate
3. **THSarabunNew Bold Font**: Uses the required Thai font for official documents
4. **Pre-print Format Option**: Allows selection of pre-print format in configuration settings
5. **Email Template**: Includes an email template for sending WHT certificates to partners
6. **Company Vat Number Display**: Shows company VAT number in boxes as per Thai standard
7. **Signature Support**: Option to print signatures on the certificate

### Dependencies
- `l10n_th_account_tax`: Thai localization for account tax
- `l10n_th_amount_to_text`: Thai localization for amount to text conversion
- `l10n_th_base_utils`: Thai localization base utilities

## Technical Architecture

### Models
1. **res.company** (Extended)
   - `wht_form_preprint`: Boolean field to enable pre-print format
   - `wht_form_print_signature`: Boolean field to enable signature printing

2. **res.config.settings** (Extended)
   - Related fields to company settings for WHT form configurations

3. **withholding.tax.cert** (Extended)
   - `_get_report_base_filename()`: Method to generate report filename
   - `_compute_desc_type_other()`: Method to compute description for "other" income type
   - `_group_wht_line()`: Method to group WHT lines by income type

### Views and Templates
1. **Report Templates**:
   - `withholding_layout_report`: Main report layout with background image
   - `withholding_layout_preprint_report`: Pre-print format template (customizable)

2. **Configuration Views**:
   - `res_config_settings_view_form`: Settings form with WHT options

### Data Files
1. **Paper Format**: Custom A4 paper format for WHT certificates
2. **Email Template**: Template for sending WHT certificates via email
3. **Action Data**: Send by email action for WHT certificates

### Static Assets
- **SCSS Styles**: Custom styles for the report layout (`style_report.scss`)
- **Background Image**: Withholding certificate background image

## File Structure
```
l10n_th_account_wht_cert_form/
├── __init__.py
├── __manifest__.py
├── Qwen.md (this file)
├── README.rst
├── pyproject.toml
├── data/
│   ├── paper_format.xml
│   ├── mail_template.xml
│   ├── withholding_tax_cert_data.xml
│   └── ...
├── models/
│   ├── __init__.py
│   ├── res_company.py
│   ├── res_config_settings.py
│   └── withholding_tax_cert.py
├── reports/
│   └── withholding_tax_cert_form_view.xml
├── static/
│   └── src/
│       └── scss/
│           └── style_report.scss
├── tests/
│   ├── __init__.py
│   └── test_wht_cert_form.py
├── views/
│   └── res_config_settings_views.xml
└── ...
```

## Usage Instructions
1. Install the module
2. Go to *Invoicing > Vendors > WHT Certificates*
3. Select a document > Print 'WHT Certificates (pdf)'

### Customization Options
1. **Pre-print Format**: Go to *Invoicing > Configuration > Settings* and select "Preprint - Withholding Tax Cert Form"
   - This changes the layout to pre-print format
   - You can inherit and customize using template `withholding_layout_preprint_report`

2. **Signature Printing**: Enable signature printing through settings

### Configuration Settings
- **Preprint - Withholding Tax Cert Form**: Toggle to use pre-print format layout
- **WHT Cert - Print Signature**: Toggle to include signatures on certificates

## Testing
The module includes a test file (`test_wht_cert_form.py`) that:
- Creates a direct WHT certificate
- Tests PDF rendering functionality
- Verifies report filename generation

## Customization Capabilities
1. **Layout Customization**: The pre-print format can be customized by inheriting the template
2. **Email Template**: The email template can be modified to match company requirements
3. **Report Styling**: SCSS styles can be extended or modified for custom appearance

## Dependencies and Integration
This module extends functionality from:
- `l10n_th_account_tax`: Provides core WHT functionality
- `l10n_th_amount_to_text`: Converts amounts to Thai text
- Integrates with core Odoo accounting features

## Internationalization
- The module supports translations
- Translation template available at `i18n/l10n_th_account_wht_cert_form.pot`
- Translation management via Weblate

## Important Notes
- This module uses a custom background image for the WHT certificate
- The report follows Thai standard format requirements
- VAT numbers are displayed in individual boxes as required by Thai standards
- The module is in Beta development status
- Includes a cancel state overlay that shows "ยกเลิก" on cancelled certificates