# Tax Report Excel (buz_tax_report) - เพิ่ม Tax ID ในรายงาน

A comprehensive Odoo module for generating tax reports in Excel format with Tax ID/VAT information, similar to the `account_tax_report_excel` module.

## Features

### Core Functionality
- **Excel Tax Reports**: Generate professional tax reports in Excel format
- **Dual Report Types**: Support for both detailed and summary views
- **Tax Type Filtering**: Filter by Sales Taxes, Purchase Taxes, or All Taxes
- **Date Range Filtering**: Generate reports for specific periods
- **Company-wise Reporting**: Multi-company support
- **Tax ID Integration**: Display partner Tax ID/VAT numbers in detailed reports

### Report Views
1. **Detailed View**: Shows individual journal entries with:
   - Tax Name and Type
   - Tax Rate and Amounts
   - Document References
   - Partner Information
   - **Partner Tax ID/VAT Numbers**
   - Transaction Descriptions

2. **Summary View**: Shows aggregated data with:
   - Tax summaries grouped by tax type
   - Total base and tax amounts
   - Transaction counts

### Advanced Features
- **Tax Report Configuration**: Create predefined tax report configurations
- **Specific Tax Selection**: Choose specific taxes to include in reports
- **Professional Excel Formatting**: 
  - Styled headers and titles
  - Proper number formatting
  - Color-coded sections
  - Auto-sized columns

## Installation

1. Copy the module to your Odoo addons directory
2. Update your module list
3. Install the module from Apps menu

## Dependencies

- `account`: Core accounting module
- `report_xlsx`: Excel report generation module

## Usage

### Generating Tax Reports

1. Navigate to **Accounting > Reporting > Tax Reports > Tax Report (Excel)**
2. Configure the report parameters:
   - **Start Date** and **End Date**: Define the reporting period
   - **Company**: Select the company (multi-company environments)
   - **Tax Type**: Choose All, Sales, or Purchase taxes
   - **Display Details**: Toggle between detailed and summary views
   - **Report Configuration**: Use predefined configurations (optional)
   - **Specific Taxes**: Select particular taxes to include (optional)

3. Click **Generate Excel Report** to download the report

### Tax Report Configuration

1. Navigate to **Accounting > Configuration > Tax Report Configuration**
2. Create new configurations with:
   - **Report Name**: Descriptive name for the configuration
   - **Report Type**: Sales, Purchase, or Both
   - **Taxes**: Select which taxes to include
   - **Description**: Optional description

## Menu Structure

### Reporting
- **Accounting > Reporting > Tax Reports > Tax Report (Excel)**

### Configuration
- **Accounting > Configuration > Tax Report Configuration**

## Technical Details

### Models
- `tax.report.wizard`: Wizard for generating reports
- `tax.report.config`: Configuration model for predefined reports

### Reports
- `report.buz_tax_report.tax_report_xlsx`: Excel report generator

### Key Features
- Dynamic Excel formatting
- Efficient data aggregation
- Multi-company support
- Flexible filtering options
- Professional report layout

## Security

Access rights are configured for:
- **Account Users**: Can generate reports
- **Account Managers**: Can configure and manage tax report settings

## Version Information

- **Version**: 17.0.1.0.0
- **Odoo Version**: 17.0
- **License**: LGPL-3

## Author

**apcball**

## Support

For support and customization requests, please contact the module author.
