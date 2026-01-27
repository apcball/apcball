# Quick Start Guide - Warranty Management

## 5-Minute Setup

### Step 1: Install Module (2 minutes)
1. Go to **Apps** menu in Odoo
2. Search for "Warranty Management"
3. Click **Install**

### Step 2: Configure a Product (2 minutes)
1. Go to **Inventory > Products**
2. Open any product
3. Click **Warranty Information** tab
4. Enable these settings:
   - ☑ **Auto Create Warranty**
   - **Duration**: `12` (months)
   - **Type**: `Repair`
   - **Terms**: `Standard 12-month manufacturer warranty`
5. Click **Save**

### Step 3: Test the Flow (1 minute)
1. Create a sale order with your warranty product
2. Confirm the order
3. Validate delivery
4. Check **Warranty > Warranty Cards** - you'll see the auto-created warranty!

## Common Use Cases

### Use Case 1: Customer Buys Product with Warranty
```
Sale Order → Delivery → ✓ Warranty Card Created Automatically
```

### Use Case 2: Customer Reports Problem (Under Warranty)
```
1. Warranty > Claims > Create
2. Select warranty card
3. Enter problem
4. Under Review → Approve → Done
5. No charge to customer ✓
```

### Use Case 3: Customer Reports Problem (After Warranty Expires)
```
1. Warranty > Claims > Create
2. System shows "OUT OF WARRANTY" warning
3. Click "Create Quotation"
4. Enter repair cost
5. Send quotation to customer
6. Customer pays → Do repair
```

## Essential Settings

### Product Configuration
| Field | Recommended Value | Purpose |
|-------|-------------------|---------|
| Auto Create Warranty | ☑ Yes | Automatic card generation |
| Duration | 12 months | Standard warranty period |
| Warranty Type | Repair | Most common option |
| Allow Out-of-Warranty | ☑ Yes | Additional revenue stream |
| Service Product | "Repair Service" | For paid repairs |

### User Access
- **Warranty User**: Service desk, support staff
- **Warranty Manager**: Service manager, admin

## Tips & Tricks

### Tip 1: Print Certificates Immediately
After delivery, go to warranty card and click **Print Certificate** - give to customer with product.

### Tip 2: Use Filters Effectively
- **Active**: Current warranties
- **Near Expiry**: Upsell extended warranty
- **Expired**: Contact for renewal

### Tip 3: Smart Buttons
- Click warranty count on products to see all warranties
- Click claim count on warranty cards to see issues

### Tip 4: Service Revenue
Create attractive service product pricing for out-of-warranty repairs to generate additional revenue.

### Tip 5: Customer Communication
Use chatter on warranty cards and claims to:
- Tag team members
- Schedule follow-ups
- Track all communications

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Warranty not created | Check: ☑ Auto Warranty + Duration > 0 |
| Can't create quotation | Check: ☑ Allow Out-of-Warranty |
| Access denied | Assign user to Warranty group |

## Next Steps

1. ✓ Module installed
2. ✓ Product configured
3. ✓ Test completed
4. □ Train team on workflows
5. □ Configure all products
6. □ Set up service products
7. □ Create email templates
8. □ Build dashboard

## Need More Help?

- Read **README.md** for feature overview
- Read **IMPLEMENTATION_GUIDE.md** for detailed workflows
- Contact Buzzit support

---

**Ready to Go!** 🚀

Your warranty management system is now operational. Start processing warranties and provide excellent after-sales service!
