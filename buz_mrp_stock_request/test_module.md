# Test Module Documentation

## Module: buz_mrp_stock_request

This module provides integration between Manufacturing Orders and Internal Transfers through a Stock Request mechanism.

### Test Cases

1. Create a manufacturing order
2. Create a stock request from the MO
3. Use the "Prepare from MO" feature to auto-populate components
4. Confirm the stock request to create an internal transfer
5. Check that the internal transfer is properly linked
6. Verify status synchronization between SRQ and picking
7. Test the approval workflow (if enabled)
8. Verify multi-company access controls
9. Test the sequence numbering
10. Verify the smart button functionality in MO

### Key Features Tested
- Stock request creation from MO
- Internal transfer generation
- Status synchronization
- Auto-population from MO
- Multi-company support
- Approval workflow
- Security access rights
- Sequence generation
- Traceability between MO, SRQ, and Picking