# Warranty Management System for Odoo 17

A comprehensive warranty management system that integrates seamlessly with Sales, Stock, and Accounting modules in Odoo 17 Community Edition.

## Features

### 1. Product-Level Warranty Configuration
- Configure warranty duration (in months) at product level
- Set warranty terms and conditions
- Define warranty type (Replacement/Repair/Refund)
- Enable automatic warranty card creation on delivery
- Configure service products for out-of-warranty repairs

### 2. Automatic Warranty Card Generation
- Automatically creates warranty cards when products are delivered
- Generates unique warranty numbers (WARR/YYYY/#####)
- Links to sale orders and delivery orders
- Tracks warranty start and end dates
- Monitors warranty status (Draft/Active/Expired/Cancelled)

### 3. Warranty Claim Management
- Submit warranty claims for products
- Automatically determines if claim is under warranty
- Track claim status (Draft/Under Review/Approved/Done/Rejected)
- Different workflows for under-warranty and out-of-warranty claims
- Link claims to warranty cards

### 4. Out-of-Warranty Service Flow
- Create quotations for expired warranty claims
- Configurable service products for repairs
- Automatic cost estimation
- Generate sale orders for out-of-warranty services
- Track quotations linked to claims

### 5. Reports and Certificates
- **Warranty Certificate**: Professional printable warranty certificate
- **Warranty Claim Form**: Detailed claim documentation form
- Both reports include customer information, product details, and terms

### 6. Smart Features
- Dashboard with filters (Active/Expired/Near Expiry)
- Smart buttons showing warranty count on products
- Smart buttons showing claim count on warranty cards
- Automated daily cron job to update expired warranties
- Chatter integration for communication tracking

## Installation

1. Copy the `buz_warranty_management` folder to your Odoo addons directory
2. Update the apps list in Odoo
3. Install the "Warranty Management" module

## Configuration

### Product Setup
1. Go to **Inventory > Products > Products**
2. Open a product and navigate to the **Warranty Information** tab
3. Configure:
   - Enable "Auto Create Warranty"
   - Set warranty duration in months
   - Select warranty type
   - Define warranty terms and conditions
   - (Optional) Set service product for out-of-warranty repairs
   - Enable "Allow Out-of-Warranty Service" if applicable

### User Access
The module provides two access levels:
- **Warranty User**: Can view warranty cards and create/manage claims
- **Warranty Manager**: Full access to all warranty features

Assign users to appropriate groups in **Settings > Users & Companies > Users**.

## Usage

### Creating Warranty Cards
Warranty cards are created automatically when:
1. A delivery order is validated (button_validate)
2. The delivered product has "Auto Create Warranty" enabled
3. The product has a warranty duration > 0

Manual creation is also possible from **Warranty > Warranty Cards > Create**.

### Submitting Warranty Claims
1. Go to **Warranty > Warranty Claims > Create**
2. Select the warranty card
3. Customer and product information auto-populate
4. Enter problem description
5. Select claim type (Repair/Replace/Refund)
6. Submit for review

### Processing Claims

#### Under Warranty:
1. Review the claim
2. Approve if valid
3. Process repair/replacement
4. Mark as done

#### Out of Warranty:
1. Click "Create Quotation" button
2. Enter service product and repair cost
3. System creates a sale order
4. Send quotation to customer
5. Confirm and process payment

## Technical Details

### Models
- `warranty.card`: Warranty card records
- `warranty.claim`: Warranty claim records
- `warranty.out.wizard`: Wizard for out-of-warranty quotations
- `product.template`: Extended with warranty fields
- `stock.picking`: Extended to auto-create warranty cards

### Dependencies
- sale
- stock
- account
- mail

### Key Methods
- `stock.picking.button_validate()`: Overridden to create warranty cards
- `warranty.card.cron_update_expired_warranties()`: Daily cron to update expired warranties
- `warranty.claim.action_create_out_warranty_quotation()`: Creates out-of-warranty quotations

## Scheduled Actions

The module includes a scheduled action that runs daily:
- **Warranty: Update Expired Status**: Automatically updates warranty cards to expired status when end date is reached

## Reports

### Warranty Certificate
Professional certificate document including:
- Warranty number and dates
- Customer information
- Product and serial number details
- Warranty terms and conditions
- Signature blocks

### Warranty Claim Form
Comprehensive claim documentation including:
- Claim information
- Customer and product details
- Problem description
- Internal notes and resolution
- Signature blocks for customer, technician, and authorization

## Workflow Diagram

```
Product Configuration → Delivery Validation → Warranty Card Created
                                                      ↓
                                            Customer Reports Issue
                                                      ↓
                                              Warranty Claim Created
                                                      ↓
                                        ┌─────────────┴─────────────┐
                                   Under Warranty              Out of Warranty
                                        ↓                           ↓
                              Review → Approve              Create Quotation
                                        ↓                           ↓
                              Process Repair                 Customer Pays
                                        ↓                           ↓
                                    Mark Done                   Mark Done
```

## Support and Customization

For support or customization requests, please contact Buzzit.

## License

LGPL-3

## Author

Buzzit
Website: https://www.buzzit.co.th

## Version

17.0.1.0.0
