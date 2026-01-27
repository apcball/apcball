# Warranty Management System - Implementation Guide

## Module Overview

The `buz_warranty_management` module is a complete warranty management solution for Odoo 17 Community Edition that integrates seamlessly with Sales, Stock, and Accounting modules.

## Module Structure

```
buz_warranty_management/
├── __init__.py
├── __manifest__.py
├── README.md
├── IMPLEMENTATION_GUIDE.md
├── data/
│   └── sequence.xml                    # Sequences for warranty cards and claims
├── models/
│   ├── __init__.py
│   ├── product_template.py             # Product warranty configuration
│   ├── warranty_card.py                # Warranty card model
│   ├── warranty_claim.py               # Warranty claim model
│   └── stock_picking.py                # Auto warranty creation hook
├── wizard/
│   ├── __init__.py
│   ├── warranty_out_wizard.py          # Out-of-warranty quotation wizard
│   └── warranty_out_wizard_view.xml
├── views/
│   ├── menu.xml                        # Menu structure
│   ├── product_template_views.xml      # Product warranty tab
│   ├── warranty_card_views.xml         # Warranty card views
│   └── warranty_claim_views.xml        # Warranty claim views
├── report/
│   ├── report_warranty_certificate.xml # Warranty certificate report
│   └── report_warranty_claim_form.xml  # Claim form report
├── security/
│   ├── security.xml                    # User groups and record rules
│   └── ir.model.access.csv            # Access rights
└── static/
    └── description/
        ├── icon.png                    # Module icon
        └── index.html                  # Module description

```

## Installation Steps

### 1. Copy Module
```bash
cp -r buz_warranty_management /opt/instance1/odoo17/custom-addons/
```

### 2. Restart Odoo Server
```bash
sudo systemctl restart odoo
```

### 3. Update Apps List
- Go to **Apps** menu
- Click **Update Apps List**
- Search for "Warranty Management"

### 4. Install Module
- Click **Install** on the Warranty Management module

## Configuration

### Step 1: Configure User Access

1. Navigate to **Settings > Users & Companies > Users**
2. Select a user
3. Go to the **Access Rights** tab
4. Assign appropriate warranty group:
   - **Warranty / User**: Can view warranty cards and manage claims
   - **Warranty / Manager**: Full access to all warranty features

### Step 2: Configure Products

1. Go to **Inventory > Products > Products**
2. Open a product you want to configure
3. Navigate to **Warranty Information** tab
4. Configure the following:

   **Warranty Configuration:**
   - ✓ Enable **Auto Create Warranty**
   - Enter **Warranty Duration** (in months, e.g., 12)
   - Select **Warranty Type** (Repair/Replacement/Refund)

   **Out-of-Warranty Settings:**
   - ✓ Enable **Allow Out-of-Warranty Service**
   - Select **Service Product** (create a service product if needed)

   **Warranty Terms & Conditions:**
   - Enter detailed warranty terms and conditions

5. Save the product

### Step 3: Create Service Product (Optional)

If you plan to offer out-of-warranty services:

1. Create a new product with:
   - **Product Type**: Service
   - **Name**: "Warranty Repair Service" (or similar)
   - Set appropriate pricing
2. Link this product to your warranty-enabled products

## Usage Workflows

### Workflow 1: Automatic Warranty Card Creation

**Trigger:** When a delivery order is validated

**Process:**
1. Sales person creates a sale order with warranty-enabled product
2. Order is confirmed
3. Delivery order is created
4. When delivery is validated:
   - System checks if product has `auto_warranty = True`
   - System checks if `warranty_duration > 0`
   - If both conditions met, warranty card is created automatically
   - Warranty card status set to "Active"
   - Start date = delivery date
   - End date = start date + warranty duration

**Result:**
- Warranty card created with unique number (WARR/2025/00001)
- Certificate can be printed immediately
- Customer receives warranty protection

### Workflow 2: Under-Warranty Claim Processing

**Scenario:** Customer reports issue within warranty period

**Steps:**
1. **Create Claim:**
   - Go to **Warranty > Warranty Claims > Create**
   - Select warranty card
   - System auto-fills customer and product info
   - Enter problem description
   - Select claim type (Repair/Replace/Refund)
   - Save

2. **Review Status:**
   - System automatically checks if claim is under warranty
   - Green badge shows "Under Warranty"
   - No cost to customer

3. **Process Claim:**
   - Click **Under Review** to start processing
   - Add internal notes if needed
   - Click **Approve** once reviewed
   - Process the repair/replacement
   - Click **Mark as Done** when completed

4. **Print Documentation:**
   - Click **Print Claim Form** for service record
   - Document is generated as PDF

### Workflow 3: Out-of-Warranty Claim Processing

**Scenario:** Customer reports issue after warranty expires

**Steps:**
1. **Create Claim:**
   - Go to **Warranty > Warranty Claims > Create**
   - Select warranty card
   - System shows red warning: "OUT OF WARRANTY"
   - Enter problem description
   - Enter cost estimate
   - Save

2. **Create Quotation:**
   - Click **Create Quotation** button
   - Wizard opens
   - Select service product (pre-filled if configured)
   - Enter repair cost
   - Add description if needed
   - Click **Create Quotation**

3. **Send to Customer:**
   - System creates sale order automatically
   - Send quotation to customer via email
   - Customer reviews and approves

4. **Process Payment:**
   - Confirm sale order
   - Create invoice
   - Register payment

5. **Complete Repair:**
   - Process the repair
   - Update claim status to **Done**
   - Add resolution notes

### Workflow 4: Warranty Certificate Printing

**When to Print:**
- After automatic creation (give to customer)
- Customer requests replacement certificate
- For record keeping

**Steps:**
1. Go to **Warranty > Warranty Cards**
2. Open the warranty card
3. Click **Print Certificate** button
4. PDF is generated with:
   - Company letterhead
   - Warranty number and dates
   - Customer information
   - Product details
   - Terms and conditions
   - Signature blocks

## Advanced Features

### Smart Buttons

**On Products:**
- **Warranties** button shows count and opens warranty cards for that product

**On Warranty Cards:**
- **Claims** button shows count and opens related claims

### Filters and Search

**Warranty Cards:**
- Active warranties (default filter)
- Expired warranties
- Near expiry (within 30 days)
- Group by: Customer, Product, Status, Date

**Warranty Claims:**
- Under warranty vs Out of warranty
- By status: Draft, Under Review, Approved, Done, Rejected
- Group by: Customer, Product, Status, Claim Type, Date

### Automated Processes

**Daily Cron Job:**
- Runs every day at midnight
- Updates warranty cards from "Active" to "Expired" when end date is reached
- Keeps warranty status accurate automatically

### Chatter Integration

Both warranty cards and claims include full chatter functionality:
- **Followers**: Add team members to follow updates
- **Activities**: Schedule follow-up tasks
- **Messages**: Internal notes and customer communications
- **Log Notes**: Track all changes and actions

## Reports

### 1. Warranty Certificate
- Professional document for customers
- Includes all warranty details
- Company branding
- Signature blocks
- Terms and conditions

### 2. Warranty Claim Form
- Service documentation
- Problem description
- Resolution details
- Internal notes
- Multiple signature blocks (customer, technician, manager)

## Dashboard and Analytics

### Key Metrics to Monitor

1. **Active Warranties**: Total number of active warranty cards
2. **Claims Rate**: Percentage of warranties with claims
3. **Near Expiry**: Warranties expiring in next 30 days
4. **Out-of-Warranty Revenue**: Income from expired warranty services

### Create Custom Dashboards

Use Odoo's dashboard feature to create custom views:
1. Go to **Warranty** menu
2. Select **Warranty Cards** or **Warranty Claims**
3. Apply filters and groupings
4. Click **Favorites > Save Current Search**
5. Add to dashboard

## Integration Points

### With Sales Module
- Automatic link from sale orders to warranty cards
- Out-of-warranty quotations create sale orders
- Customer history includes warranty information

### With Stock Module
- Delivery validation triggers warranty creation
- Serial/lot numbers tracked in warranty cards
- Product movement history linked to warranties

### With Accounting Module
- Out-of-warranty quotations create invoices
- Revenue recognition for warranty services
- Customer payment tracking

## Troubleshooting

### Issue: Warranty Card Not Created Automatically

**Possible Causes:**
1. Product doesn't have `auto_warranty` enabled
2. Warranty duration is 0 or not set
3. Delivery order was not validated (done state)
4. Picking type is not 'outgoing'

**Solution:**
- Check product warranty configuration
- Ensure delivery is in "Done" state
- Check picking type

### Issue: Cannot Create Out-of-Warranty Quotation

**Possible Causes:**
1. Claim is still under warranty
2. Product doesn't allow out-of-warranty service
3. Service product not configured

**Solution:**
- Verify warranty end date
- Check product's "Allow Out-of-Warranty Service" setting
- Configure service product on main product

### Issue: Access Denied Error

**Solution:**
- Ensure user has appropriate warranty group assigned
- Check **Settings > Users & Companies > Users**
- Assign **Warranty / User** or **Warranty / Manager** group

## Customization Guide

### Adding Custom Fields

To add custom fields to warranty card:

```python
# In models/warranty_card.py
custom_field = fields.Char(string='Custom Field')
```

Then add to view:

```xml
<!-- In views/warranty_card_views.xml -->
<field name="custom_field"/>
```

### Custom Email Templates

Create email template for warranty expiry notification:

1. Go to **Settings > Technical > Email Templates**
2. Create new template with model `warranty.card`
3. Use fields like `${object.name}`, `${object.partner_id.name}`
4. Set up scheduled action to send emails

### Extend Warranty Types

To add new warranty types:

```python
# In models/product_template.py
warranty_type = fields.Selection([
    ('replacement', 'Replacement'),
    ('repair', 'Repair'),
    ('refund', 'Refund'),
    ('onsite', 'On-site Service'),  # New type
], string='Warranty Type')
```

## Best Practices

1. **Always configure warranty terms clearly** on each product
2. **Print and provide warranty certificates** to customers immediately
3. **Review claims promptly** to maintain customer satisfaction
4. **Keep internal notes** on all claims for future reference
5. **Monitor near-expiry warranties** to offer renewal or extended warranty services
6. **Train staff** on both under-warranty and out-of-warranty workflows
7. **Set up service products** before enabling out-of-warranty services
8. **Regular backup** of warranty data for compliance

## Compliance and Legal

### Data Retention
- Warranty cards should be retained for legal compliance periods
- Check local laws for minimum retention periods
- Consider archiving rather than deleting old records

### Terms and Conditions
- Ensure warranty terms comply with local consumer protection laws
- Have legal review warranty conditions
- Clearly communicate limitations and exclusions

### Customer Privacy
- Warranty data contains personal information
- Comply with GDPR or local privacy laws
- Implement appropriate access controls

## Support

For issues or customization requests, contact Buzzit:
- Website: https://www.buzzit.co.th
- Email: support@buzzit.co.th

## Version History

- **17.0.1.0.0** - Initial release
  - Product warranty configuration
  - Automatic warranty card creation
  - Claim management
  - Out-of-warranty quotations
  - QWeb reports
  - User access controls
