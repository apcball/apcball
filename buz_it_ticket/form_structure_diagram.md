# IT Ticket Form Structure Diagram

## Current Structure (Single Form)

```mermaid
graph TD
    A[Single Form View] --> B{Category Field}
    B -->|issue| C[Issue/Repair Fields Visible]
    B -->|access| D[Access Fields Visible]
    B -->|purchase| E[Purchase Fields Visible]
    
    C --> F[Issue Buttons]
    D --> G[Access Buttons]
    E --> H[Purchase Buttons]
    
    F --> I[Issue Status Bar]
    G --> J[Access Status Bar]
    H --> K[Purchase Status Bar]
```

## New Structure (Separate Forms)

```mermaid
graph TD
    A[Menu Selection] --> B{Ticket Type}
    
    B -->|Issue/Repair| C[Issue Form View]
    B -->|Access Request| D[Access Form View]
    B -->|Purchase Request| E[Purchase Form View]
    
    C --> C1[Issue-Specific Fields]
    C --> C2[Issue-Specific Buttons]
    C --> C3[Issue Status Bar]
    
    D --> D1[Access-Specific Fields]
    D --> D2[Access-Specific Buttons]
    D --> D3[Access Status Bar]
    
    E --> E1[Purchase-Specific Fields]
    E --> E2[Purchase-Specific Buttons]
    E --> E3[Purchase Status Bar]
```

## Form Field Distribution

### Common Fields (All Forms)
- name (Ticket Number)
- priority
- employee_id (Requester)
- manager_id
- department_id
- it_responsible_id
- company_id
- user_id (Created By)
- create_date
- description
- attachment_ids
- sla_policy_id
- deadline_sla
- sla_breached
- iso_doc_code
- revision
- printed_count
- printed_by
- printed_at

### Issue/Repair Form - Unique Elements
- Status States: draft, submitted, in_progress, pending_info, resolved, closed
- Buttons: Submit Issue, Start Work, Need Info, Resolve, Close Issue, Cancel
- No specific fields (focus on description)

### Access Request Form - Unique Elements
- Status States: draft, waiting_manager, approved, implementing, closed
- Buttons: Submit Request, Approve, Reject, Start Implement, Mark Done, Cancel
- Fields: access_template_id, access_line_ids

### Purchase Request Form - Unique Elements
- Status States: draft, waiting_manager, waiting_it, po_created, received, closed
- Buttons: Submit Request, Approve, Reject, Create PO, Mark Received, Close Purchase, Cancel
- Fields: purchase_line_ids, purchase_id
- Stat Button: Purchase Order

## Workflow Comparison

### Issue/Repair Workflow
```mermaid
graph LR
    A[Draft] --> B[Submitted]
    B --> C[In Progress]
    C --> D[Pending Info]
    D --> C
    C --> E[Resolved]
    E --> F[Closed]
    A --> G[Cancelled]
    B --> G
    C --> G
```

### Access Request Workflow
```mermaid
graph LR
    A[Draft] --> B[Waiting Manager]
    B --> C[Approved]
    B --> D[Rejected]
    C --> E[Implementing]
    E --> F[Closed]
    A --> G[Cancelled]
    B --> G
```

### Purchase Request Workflow
```mermaid
graph LR
    A[Draft] --> B[Waiting Manager]
    B --> C[Waiting IT]
    B --> D[Rejected]
    C --> E[PO Created]
    E --> F[Received]
    F --> G[Closed]
    E --> G
    A --> H[Cancelled]
    B --> H
    C --> H
```

## Benefits of Separate Forms

1. **Improved User Experience**
   - Cleaner interface with only relevant fields
   - Clear workflow visualization
   - Reduced confusion

2. **Better Performance**
   - Smaller DOM trees
   - Faster loading
   - Less conditional rendering

3. **Easier Maintenance**
   - Independent form modifications
   - Clear separation of concerns
   - Reduced complexity

4. **Enhanced Extensibility**
   - Easy to add fields to specific ticket types
   - Custom workflows per ticket type
   - Better code organization