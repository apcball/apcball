# BUZ ISO Document Control

ISO Document Control for Odoo 17. The document master contains metadata only; every original file belongs to a revision. Managers create and publish revisions, while ordinary users can only view authorised published documents and download the original.

## Installation

1. Copy `buz_document_control` into the Odoo addons path.
2. Update Apps List, install **BUZ ISO Document Control**, and assign the supplied groups.
3. Set System Parameters as needed:
   - `buz_document_control.max_file_size_mb` (default `50`)
   - `buz_document_control.review_warning_days` (default `30`)
   - `buz_document_control.enable_download_log` (`True` to enable audit rows)

## Security and workflow

- **Document User** reads general documents and restricted documents distributed to one of their groups or departments.
- **Confidential Document User** additionally reads confidential documents. If an allowed-group list is set, one group must match.
- **Document Manager** manages documents, revisions, distribution and conversion. **Document Administrator** has the same access plus deletion of published revisions.
- Draft → Review → Published. Publishing a replacement automatically marks the old current revision obsolete in the same database transaction. Published file, revision number, effective date and change description cannot be edited.

Both `/buz_document/preview/<revision_id>` and `/buz_document/download/<revision_id>` require a logged-in user and re-check model ACL plus record rules. This prevents URL guessing from bypassing distribution rules.

## Preview conversion

PDF files preview immediately. DOC/DOCX/XLS/XLSX/PPT/PPTX conversion uses LibreOffice headless, with a temporary directory, safe fixed filename, argument-list subprocess, 120-second timeout, and cleanup. The upload succeeds if conversion fails and the original remains downloadable.

Install LibreOffice on Ubuntu:

```bash
sudo apt install libreoffice
```

If unavailable, the revision displays: “Document preview is unavailable because the document conversion service is not installed.”

## Troubleshooting

Run an Odoo module upgrade after deployment: `odoo -d DATABASE -u buz_document_control --stop-after-init`. Check the Odoo server account can execute `libreoffice` for Office previews. Conversion output is deliberately not exposed to end users.
