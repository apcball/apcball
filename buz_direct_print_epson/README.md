# Direct Print Epson

This module allows Odoo users to print documents directly to Epson printers through a Local Print Agent (HTTP API).

## Features

- Direct printing to Epson continuous form printers
- Support for multiple document types (Invoices, Pickings, Bills)
- Multi-record selection for batch printing
- Configuration management for print agent settings
- Error handling and user notifications

## Installation

1. Copy the module to your Odoo addons directory
2. Update the module list in Odoo
3. Install the module from Apps menu

## Configuration

1. Go to Settings > Technical > Printing > Epson Print Configuration
2. Create a new configuration with:
   - Configuration Name: A descriptive name for this configuration
   - Agent URL: URL of your Local Print Agent (e.g., http://192.168.1.55:5000/print)
   - Default Printer: Printer name as configured in your system (e.g., Epson_LQ310)
   - Active: Check to enable this configuration

## Usage

### For Invoices/Bills

1. Go to Accounting > Customers > Invoices or Accounting > Vendors > Bills
2. Select one or more invoices/bills from the list view
3. Click "Action > พิมพ์ต่อเนื่อง (Epson)" or use the button in the header
4. The documents will be sent to the configured Epson printer

### For Stock Pickings

1. Go to Inventory > Operations > Transfers
2. Select one or more pickings from the list view
3. Click "Action > พิมพ์ต่อเนื่อง (Epson)" or use the button in the header
4. The documents will be sent to the configured Epson printer

## Local Print Agent

This module requires a Local Print Agent running in your office network. The agent should:

1. Accept HTTP POST requests at the configured URL
2. Process JSON payloads with the following structure:
   ```json
   {
     "printer": "Epson_LQ310",
     "file_url": "https://odoo.example.com/web/content/123?download=true",
     "type": "pdf"
   }
   ```
3. Download the PDF from the provided URL
4. Send the PDF to the specified printer using the Windows driver

## Security

- Only users in the System group can modify Epson Print Configuration
- All users can read the configuration but cannot modify it
- Print actions are available to all users with appropriate access to the documents

## Technical Details

### Models

- `buz.epson.config`: Stores configuration for the Local Print Agent
- `account.move`: Extended with `action_print_epson()` method
- `stock.picking`: Extended with `action_print_epson()` method

### Dependencies

- `base`: Core Odoo functionality
- `account`: For invoice and bill printing
- `stock`: For picking printing

## Version

- Version: 17.0.1.0.0
- License: LGPL-3

## Support

For support and issues, please contact your system administrator.