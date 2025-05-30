# All In One Backdate Advanced

A comprehensive backdating module for Odoo 17 that allows authorized users to modify dates on posted documents while maintaining proper audit trails and validation rules.

## Features

### Document Support
- **Accounting Documents**: Customer Invoices, Vendor Bills, Payments, Journal Entries
- **Sales & Purchase**: Sale Orders, Purchase Orders
- **Inventory**: Stock Pickings, Inventory Moves
- **Banking**: Bank Statements and Statement Lines

### Security & Permissions
- **User Groups**: Separate permissions for users and managers
- **Date Restrictions**: Configurable maximum backdate days for users
- **Fiscal Controls**: Respects fiscal year locks and accounting periods
- **Document Type Controls**: Enable/disable backdating per document type

### Audit Trail
- **Complete Logging**: All backdate operations are logged
- **Reason Tracking**: Optional or mandatory reason for backdating
- **User Activity**: Track who performed the backdate operation
- **Date History**: Keep record of old and new dates

### Configuration Options
- Maximum backdate days for regular users
- Mandatory reason requirement
- Enable/disable by document type
- Company-specific settings
- Automated log cleanup

## Installation

1. Copy the module to your Odoo addons directory
2. Update the app list
3. Install "All In One Backdate Advanced" from the Apps menu

## Configuration

### 1. General Settings
Go to **Settings > General Settings > Backdate** section:
- Set maximum backdate days
- Configure reason requirements
- Enable/disable document types

### 2. User Permissions
Go to **Settings > Users & Companies > Groups**:
- **Backdate User**: Can backdate with restrictions
- **Backdate Manager**: Can backdate without restrictions

### 3. Company Settings
Configure company-specific backdate rules and fiscal year locks.

## Usage

### For Users with Backdate Permissions

1. **Open a Posted Document**: Navigate to any supported posted document
2. **Click Backdate Button**: Available in the document header
3. **Set New Date**: Choose the desired backdate
4. **Provide Reason**: If required by configuration
5. **Confirm**: The system will validate and update the date

### Supported Documents

| Document Type | Model | States |
|---------------|-------|--------|
| Customer Invoice | account.move | posted |
| Vendor Bill | account.move | posted |
| Payment | account.payment | posted |
| Sale Order | sale.order | sale, done |
| Purchase Order | purchase.order | purchase, done |
| Stock Picking | stock.picking | done |
| Bank Statement | account.bank.statement | posted |

### Validation Rules

The system validates:
- Date is not in the future
- Date respects maximum backdate days (for users)
- Date is not in locked fiscal periods
- Document type backdating is enabled
- User has appropriate permissions

## Audit & Compliance

### Backdate Logs
Access backdate logs through:
- **Main Menu**: Backdate > All Backdate Logs
- **Document-specific**: Each module has its own backdate log menu

### Log Information
Each log entry contains:
- Document name and type
- Old and new dates
- User who performed the operation
- Timestamp of the operation
- Reason provided

### Reporting
Use the backdate logs for:
- Compliance audits
- User activity monitoring
- Date change analysis
- Regulatory reporting

## Technical Details

### Models Extended
- `account.move` - Invoices and Bills
- `account.payment` - Payments
- `sale.order` - Sale Orders
- `purchase.order` - Purchase Orders
- `stock.picking` - Stock Pickings
- `account.bank.statement` - Bank Statements
- `account.bank.statement.line` - Statement Lines

### New Models
- `backdate.log` - Audit trail for backdate operations
- `backdate.wizard` - Wizard for backdate operations

### Configuration Parameters
- `sh_all_in_one_backdate.backdate_max_days`
- `sh_all_in_one_backdate.backdate_require_reason`
- `sh_all_in_one_backdate.backdate_enable_*` (per document type)

## Security Groups

### Backdate User (`group_backdate_user`)
- Can backdate documents with date restrictions
- Subject to maximum backdate days limit
- Can view own backdate logs

### Backdate Manager (`group_backdate_manager`)
- Can backdate any document without restrictions
- Can view all backdate logs
- Can manage backdate settings

## Best Practices

### 1. User Training
- Train users on proper backdating procedures
- Emphasize the importance of providing accurate reasons
- Explain the audit implications

### 2. Configuration
- Set reasonable maximum backdate days
- Require reasons for all backdate operations
- Regularly review backdate logs

### 3. Compliance
- Establish clear backdating policies
- Regular audit of backdate operations
- Document business justifications

### 4. Monitoring
- Review backdate logs regularly
- Monitor user activity patterns
- Investigate unusual backdating patterns

## Troubleshooting

### Common Issues

**Error: "You do not have permission to backdate this document"**
- Check user group membership
- Verify document state (must be posted/confirmed)
- Ensure document type backdating is enabled

**Error: "You cannot backdate more than X days"**
- Check maximum backdate days setting
- User may need manager permissions
- Verify the target date

**Error: "You cannot backdate to a locked fiscal period"**
- Check fiscal year lock dates
- Contact accounting manager
- May require manager override

### Performance Considerations
- Large numbers of backdate operations may impact performance
- Consider batch processing for multiple documents
- Regular cleanup of old backdate logs

## Support

For technical support or customization requests:
1. Check the documentation first
2. Review the backdate logs for error details
3. Contact your Odoo administrator
4. Reach out to your Odoo partner

## License

This module is licensed under LGPL-3.

## Credits

Developed for Odoo 17 Community and Enterprise editions.