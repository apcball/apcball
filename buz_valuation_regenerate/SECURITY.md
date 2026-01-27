# Security Guidelines for buz_valuation_regenerate

## Access Controls

### User Groups
This module defines the following user groups with specific permissions:

- **Valuation Regeneration User**: Basic access to view and use the regeneration tools
- **Valuation Regeneration Manager**: Full access including the ability to execute regeneration

### Required Permissions
To use the main features of this module, users need to belong to one of the following groups:
- `stock.group_stock_manager` (Inventory Manager)
- `account.group_account_manager` (Accounting Manager)

These permissions are required because the module can significantly affect inventory valuations and financial records.

## Security Features

### Multi-Company Isolation
- All operations are restricted to the selected company
- Record rules ensure users only see data relevant to their allowed companies
- Cross-company data access is prevented

### Validation Checks
The module performs several security and validation checks before executing operations:

1. **Permission Validation**: Verifies users have appropriate stock or accounting manager permissions
2. **Period Lock Validation**: Checks for fiscal year and period locks before modifying data
3. **Data Scope Validation**: Ensures that only authorized products/periods/companies are processed
4. **Dry Run Option**: By default, operations are performed in dry-run mode to preview impact before execution

### Data Protection
- All original data is backed up in JSON format before deletion
- Backup logs are stored for audit purposes
- Rollback functionality is available (with limitations)

## Safe Usage Guidelines

### Before Running Regeneration
1. **Backup**: Always create a full database backup before running valuation regeneration
2. **Dry Run**: Always perform a dry run first to preview changes
3. **Permissions**: Ensure the executing user has appropriate permissions
4. **Timing**: Run during low-usage periods to avoid conflicts with concurrent operations

### Operational Safeguards
- The module respects Odoo's lock date settings by default (can be overridden with caution)
- Only allows modifications to valuation layers and journal entries that are directly related to stock movements
- Includes landed cost handling to maintain proper cost allocation relationships

## Risk Mitigation

1. **Dry Run First**: Always start with dry-run mode to check the impact
2. **Limited Scope**: Use date ranges and specific product selections to limit the scope
3. **Monitoring**: The system creates logs that track all operations for audit purposes
4. **Rollback**: While not perfect, the system provides rollback functionality with appropriate warnings

## Audit Trail

All regeneration operations create detailed log entries that include:
- Who executed the operation
- When it was executed
- What products/dates were affected
- What options were used
- Original data backup
- New data created
- Any attached reports

## Important Security Notes

⚠️ **Critical Warning**: This module can significantly alter financial records and inventory valuations. Improper use can result in incorrect financial reporting.

- Only grant access to trusted personnel with appropriate financial and inventory management knowledge
- Always test in a non-production environment first
- Consult with financial personnel before running regeneration on financial period data
- Be aware of the impact on dependent transactions that may have occurred since the original valuation

## Emergency Procedures

If an incorrect regeneration occurs:
1. Check the logs to understand what changes were made
2. If possible, use the rollback feature (with awareness of its limitations)
3. Restore from database backup if rollback is not feasible
4. Review and correct any related data that may have been affected