# IT Asset Registry: Phase 5A Migration Plan

## Scope

This phase only defines the architecture, security boundary, and migration safeguards for the existing `buz.it.asset` model. No existing `email` or `system_account` records are deleted or transformed automatically.

## Role matrix

| Role | Asset records | License Key | Export / download |
|---|---|---|---|
| IT Asset User | Read/write in allowed companies | No access | Same company records only |
| IT Asset Manager | Create/read/write in allowed companies | Read/write | Same company records only |
| Helpdesk Requester / Portal | No access | No access | No access |

Helpdesk Agent and Manager inherit the corresponding IT Asset role for backward-compatible internal operations. Record rules still apply `company_ids`.

## Existing data mapping

- `asset_type=computer` and `asset_type=printer`: retain as hardware candidates.
- `asset_type=software_license`: retain as license candidates.
- `asset_type=email` and `asset_type=system_account`: retain unchanged and report for review; these types are out of scope for new Phase 5 work.
- `password`, `account_username`, `account_email`, and `account_url` are not migrated into a new model.

## Dry run and rollback

1. Export a read-only inventory grouped by `asset_type`, `company_id`, `active`, and duplicate serial number.
2. Validate required mappings and report conflicts without writing records.
3. Produce an import file only after the report is approved.
4. Use a transaction/savepoint for any approved migration; rollback on validation or company/security errors.
5. Keep the original records and use `active=False` for archival. Asset records are not deleted.

The operational dry run must be executed against a database copy before any production or DEV migration.