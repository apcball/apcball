# Warranty and RMA Management Module

This module provides a complete solution for managing warranty contracts, warranty claims, and RMA (Return Merchandise Authorization) processes including repair, replacement, and billing for out-of-warranty items. The module supports multi-company operations and serial/lot tracking.

## Features

- Warranty templates for products
- Warranty contracts linked to serial/lot numbers
- Complete RMA workflow with repair and replacement options
- Out-of-warranty billing capability
- Multi-company support
- Serial/lot number tracking
- Email reminders for contract expiry
- Integration with stock operations and repair orders

## Dependencies

This module requires the following Odoo modules:
- stock
- repair
- sale_management
- account
- mail

## Installation

1. Place the module folder `buz_warranty_rma_management` in your Odoo addons directory.
2. Update your apps list in Odoo by going to Apps > Update Apps List.
3. Search for "Warranty and RMA Management" and click Install.

## Configuration

After installation, you need to configure the following settings:

1. Go to Settings > Configuration > Warranty Management.
2. Set up the default operation types for RMA processes:
   - Default RMA Inbound Operation Type
   - Default RMA Return Operation Type
   - Default Replacement Operation Type
   - Default Repair Location
3. Configure the number of days before expiry to send warranty reminder emails.

## Usage

### Creating Warranty Templates

1. Go to Warranty > Configuration > Warranty Templates.
2. Create a new warranty template with the product, duration, and terms.
3. For extended warranties, select the sellable product that will be used for renewals.

### Creating Warranty Contracts

1. Go to Warranty > Operations > Warranty Contracts.
2. Create a new contract, linking it to a customer, product, lot/serial number, and warranty template.
3. The end date will be automatically calculated based on the template duration.

### Processing Warranty Claims

1. Go to Warranty > Operations > Warranty Claims.
2. Create a new claim, selecting the warranty contract and providing details about the issue.
3. Use the workflow buttons to progress the claim through the RMA process:
   - Submit: Move from draft to under review
   - Receive RMA: Create inbound picking to receive the item
   - Create Repair: Generate a repair order
   - Create Replacement: Generate an outbound picking with a replacement item
   - Return to Customer: Create outbound picking to return the item to customer
   - Create Invoice: Generate invoice for out-of-warranty repairs
   - Mark Done: Complete the claim

### Repair Process

For items that need repair:
1. The system creates a repair order linked to the warranty claim
2. After repairs are completed, mark the repair order as done
3. The warranty claim will automatically update to the next appropriate state

### Replacement Process

When an item needs replacement:
1. The system creates an outbound picking for the replacement item
2. After the replacement is shipped, validate the picking
3. The warranty claim will automatically update to the done state

### Out-of-Warranty Billing

For items outside warranty coverage:
1. Add cost lines to the warranty claim for parts, labor, etc.
2. Use the "Create Invoice" button to generate a sales order and invoice
3. After payment, mark the claim as done

## Multi-Company Support

The module fully supports multi-company operations. Each warranty contract, claim, and related document is linked to a specific company. Record rules ensure users only see documents from their allowed companies.

## Serial/Lot Number Tracking

The module requires that warranty contracts and claims are linked to specific serial/lot numbers. This ensures accurate tracking of warranty coverage for individual items and prevents unauthorized claims.

## Email Reminders

The system automatically sends email reminders to customers before their warranty contracts expire. The number of days before expiry can be configured in the settings.

## Reporting

The module includes a Claims Analysis report available at Warranty > Reporting > Claims Analysis. This report provides insights into warranty claims by product, reason, and other dimensions to help identify trends and quality issues.