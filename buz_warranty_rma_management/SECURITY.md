# Security Documentation for Warranty and RMA Management Module

## Security Groups

This module defines two security groups:

### Warranty User (group_buz_warranty_user)
- Basic access to warranty functionality
- Can read, write, and create warranty templates, contracts, claims, and cost lines
- Cannot delete warranty templates, contracts, claims, or cost lines
- Inherits permissions from the stock user group

### Warranty Manager (group_buz_warranty_manager)
- Full access to all warranty functionality
- Can read, write, create, and delete warranty templates, contracts, claims, and cost lines
- Can access and modify warranty-related settings
- Inherits permissions from the warranty user group

## Record Rules

The module implements company-based record rules to ensure data isolation in multi-company environments:

### Warranty Template Rules
- Users can only access warranty templates belonging to their company
- Implemented via the rule: `Warranty Template Company Rule`
- Domain: `[('company_id', '=', user.company_id.id)]`

### Warranty Contract Rules
- Users can only access warranty contracts belonging to their company
- Implemented via the rule: `Warranty Contract Company Rule`
- Domain: `[('company_id', '=', user.company_id.id)]`

### Warranty Claim Rules
- Users can only access warranty claims belonging to their company
- Implemented via the rule: `Warranty Claim Company Rule`
- Domain: `[('company_id', '=', user.company_id.id)]`

### Claim Cost Line Rules
- Users can only access claim cost lines for claims belonging to their company
- Implemented via the rule: `Claim Cost Line Company Rule`
- Domain: `[('claim_id.company_id', '=', user.company_id.id)]`

## Field-Level Security

- Company fields are automatically set to the current user's company when creating records
- Users cannot modify the company field after record creation
- Multi-company users with access to multiple companies can only see records from companies they have access to

## Access Rights

### Warranty Template Access Rights
- Warranty User: Read, Write, Create (No Delete)
- Warranty Manager: Read, Write, Create, Delete

### Warranty Contract Access Rights
- Warranty User: Read, Write, Create (No Delete)
- Warranty Manager: Read, Write, Create, Delete

### Warranty Claim Access Rights
- Warranty User: Read, Write, Create (No Delete)
- Warranty Manager: Read, Write, Create, Delete

### Claim Cost Line Access Rights
- Warranty User: Read, Write, Create (No Delete)
- Warranty Manager: Read, Write, Create, Delete

### Configuration Settings Access Rights
- Warranty User: Read, Write, Create (No Delete)
- Warranty Manager: Read, Write, Create, Delete

## Security Recommendations

1. Only assign Warranty Manager permissions to users who need full administrative control over warranty data
2. Regular users should only be granted Warranty User permissions
3. Ensure proper company access restrictions are in place for multi-company environments
4. Regularly review and audit security groups and permissions
5. Implement appropriate password policies and user access controls at the system level
6. Limit access to sensitive warranty contract and claim information based on business needs