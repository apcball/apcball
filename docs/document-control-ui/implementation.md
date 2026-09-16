# Document Control UI/UX — implementation and DEV validation

Date: 10 September 2026 · Odoo 17 · Module version: `17.0.1.1.1`

Deployed to **https://mogdev.work**, database **MOG_DEV**, through `scripts/deploy.sh dev buz_document_control`. The Odoo service was restarted after the Python changes. The existing `QP-ITD-01` document was preserved. Browser verification on the live DEV site opened Document Center and its upload dialog without creating or editing a document; the temporary administrative session was revoked afterwards.

## Attachment issue fixed

Two separate issues were identified and corrected:

1. The action returned to OWL by `action_new_revision()` lacked an explicit `views` array. The native action service could not open the upload wizard. Both the wizard action and its follow-up draft action now include their form view descriptors.
2. The native revision form displayed `original_filename` as read-only. It now uses `force_save="1"` so the filename changed by the binary widget is submitted with the uploaded file.

Documents without a published revision now have an **Upload Document** action. It opens the same controlled revision wizard; uploaded files become drafts and the existing publication workflow remains in charge of making them current.

Browser tests verified native draft upload, actual drag-and-drop, Thai filenames, exact saved PDF bytes, generated preview, and creation of a draft without changing the current published revision.

## 1. Files created

All paths below are relative to `buz_document_control/`:

- `models/document_center.py`
- `wizard/__init__.py`
- `wizard/document_revision_wizard.py`
- `wizard/document_revision_wizard_views.xml`
- `static/src/js/document_components.js`
- `static/src/js/document_dashboard.js`
- `static/src/js/document_viewer.js`
- `static/src/xml/document_components.xml`
- `static/src/xml/document_dashboard.xml`
- `static/src/xml/document_viewer.xml`
- `static/src/scss/document_control.scss`
- `tests/test_document_center.py`
- `tests/ui_fixture.py`
- `tests/ui_smoke.cjs`
- `tests/ui_attach_smoke.cjs`

This report, browser result JSON files and selected screenshots are under `docs/document-control-ui/`.

## 2. Files modified

- `__manifest__.py`: backend asset registration, wizard view and version.
- `__init__.py`, `models/__init__.py`: import presentation helpers and wizard.
- `models/document.py`: open the new revision modal through the existing method.
- `controllers/document_controller.py`: validate the parent document on file requests; preserve safe Thai/original filenames.
- `security/record_rules.xml`: retain rule IDs and explicitly evaluate accessible parent documents as the real user.
- `security/ir.model.access.csv`: manager-only ACL for the transient wizard.
- `views/document_views.xml`: search, kanban, list, tabbed management form and Upload Document action.
- `views/document_revision_views.xml`: workflow confirmations, tabbed form and filename persistence.
- `views/menu_views.xml`: first-position Document Center and corrected native HR action reference.
- `tests/test_document_control.py`: existing test users now include the Internal User group and use `fields.Command`.
- `tests/__init__.py`: import the new regression suite.

The entire module was untracked in Git when work started. Unrelated working-tree changes were preserved; no commit was created.

## 3. New OWL components

- **DocumentDashboard**: action registry key `buz_document_control.center`; 300 ms debounced search, type cards, filters, pagination, recent documents and manager KPIs/Needs Attention.
- **DocumentViewer**: action registry key `buz_document_control.viewer`; native PDF.js viewer, download, revision metadata, manager workflow controls, history, access and audit sections.
- **DocumentCard**: reusable metadata card with file icons and Preview/Download actions.
- **DocumentDropzone**: extends Odoo's binary field; validates extensions and handles file selection/drag-and-drop in the revision wizard.
- **DocumentKanbanController**: scoped view registry extension, `bdc_document_kanban`, opening the viewer from native kanban records.

No external frontend library or external icon/image service was added to runtime assets. Playwright is only a development test dependency installed outside the repository.

## 4. Views and navigation

- New first menu: **Document Control → Document Center** (`action_document_center`, `menu_document_center`).
- Updated existing search/list/kanban/form XML IDs; manager list view remains available for bulk work.
- New modal: `view_document_revision_wizard`.
- Manager tabs: Overview, Current Revision, Revision History, Access, Audit Trail.
- Employee experience: search, browse, current revision details, PDF preview and download; management actions and chatter are hidden.
- Desktop viewer uses approximately 68% preview / 32% metadata. Tablet stacks the preview above information. Mobile cards use one column.

## 5. New backend methods and model impact

On `buz.document`:

- `get_document_center_data(query, filter_key, type_id, offset, include_summary)`: capped metadata result, accessible counts/types and optional manager attention section in one RPC.
- `get_document_viewer_data()`: explicit parent access checks followed by accessible revision metadata and manager-only access/audit information.
- `action_document_viewer()`: viewer client action.
- Private helpers `_center_filters()`, `_compute_my_department()`, `_search_my_department()`.

On the new transient model `buz.document.revision.wizard`:

- `default_get()`: existing current revision/default dates and `_next_revision()`.
- `action_create_draft()`: manager checks, friendly duplicate validation, then the existing revision model's `create()` implementation.

Only a transient wizard model and two non-stored presentation fields (`original_filename`, `is_my_department`) were added. Existing persistent field names, current revision values, security IDs and method signatures were not renamed or dropped.

File validation, conversion, immutable published-file checks, Send to Review, Publish, Obsolete, Archive and download auditing reuse their existing implementations.

## 6. Security impact

Dashboard and viewer document/revision queries use the caller's ACLs and record rules. No `sudo()` was introduced in these APIs. Dashboard data never contains `original_file`, `preview_file` or file base64. File data is fetched only when viewing/downloading a file.

A pre-existing security failure was reproduced: an unassigned Document User could fetch a Restricted revision through its direct URL. The old revision rule evaluated parent searches in the rule-evaluation environment, which could carry elevated rights. Its parent search now explicitly calls `with_user(user.id)`. The existing controller additionally checks the parent Document Master's read rights and record rule before returning bytes.

Employee obsolete-history access was **not expanded**. The existing rules allow published revisions only; the viewer respects that restriction. Managers can inspect older revisions under their existing rights.

The filename sanitizer was also corrected: its previous regular expression removed ordinary letters/digits, including revision-number zeroes. Responses now use Odoo's `content_disposition()` for safe Unicode filenames.

## 7. Deployment and upgrade

From the repository root:

```bash
bash scripts/deploy.sh dev buz_document_control
ssh dev "docker restart odoo"
```

The script runs the equivalent of:

```bash
odoo -d MOG_DEV -u buz_document_control --stop-after-init --no-http
```

For a database where the module is not installed, install it first with `-i buz_document_control`. Both first installation and a subsequent `-u` were exercised on an isolated Odoo 17 database on DEV.

After deployment, reload the browser page so the new assets and views are loaded. No production deployment was performed.

## 8. How to test as a Document User

1. Use an Internal User with Document User permission.
2. Open Document Control; Document Center should be the first landing page.
3. Search by number/name/type/department/category/current revision and use type/department filters.
4. Open an authorized current document; verify PDF zoom/navigation, preview, original download and revision metadata.
5. Verify no Create, Edit, Upload, New Revision, Archive or chatter controls appear.
6. Check an unassigned Restricted document: absent from counts/search/recent cards, and its direct preview/download URLs must return 403.
7. Repeat as Confidential Document User: assigned confidential documents become accessible under the existing rule; unassigned Restricted documents remain hidden.

## 9. How to test as a Document Manager

1. Verify six clickable KPI cards and Needs Attention.
2. Open a document without a file and choose **Upload Document**. Choose/drop a supported file, enter the revision/dates/change description, then **Create Draft**.
3. For an existing published document use **New Revision**. Confirm that draft creation does not change the current published revision.
4. On an existing draft, use the Original Document tab to attach a file and Save. Confirm filename and PDF preview remain available after reloading.
5. Send the draft to Review, Publish and accept confirmation; the new revision becomes Current and the previous current becomes Obsolete.
6. Check older revisions, Access, Audit Trail and Regenerate Preview. Archive requires confirmation.

## Validation evidence

| Check | Result |
| --- | --- |
| Python/JS/XML syntax and manifest asset paths | Passed |
| Odoo 17 isolated first installation | Passed after correcting the old HR action reference |
| Final isolated `-u` with Odoo test runner | **13 tests, 0 failures, 0 errors** |
| Document User browser flow | Passed |
| Confidential Document User browser flow | Passed |
| Document Manager browser flow, draft upload and publish | Passed |
| Browser console / RPC / JS-CSS assets in three-role suite | No errors |
| Desktop, tablet (820 px), mobile (390 px) | Passed; no outer horizontal overflow |
| Native draft attachment and Thai filename | Passed; exact saved file content checked |
| Upload Document drag-and-drop wizard | Passed; exact saved file content checked |
| Restricted/Confidential direct preview/download URLs | Correct allowed/denied results |
| Obsolete original download | Denied for employees; allowed for manager |
| Live `https://mogdev.work` dashboard/upload dialog | Passed; no document mutation |
| Simulated dark-theme tokens | Checked in Chromium; card text and metadata use the supplied dark palette |

Full browser results: [browser-results.json](browser-results.json) and [attachment-results.json](attachment-results.json).

Screenshots: [Manager dashboard](manager-dashboard.png), [Document viewer](document-viewer.png), [New Revision](new-revision.png), [Dark-theme simulation](dark-theme-simulation.png).

## Practical limits

- The DEV installation does not provide the Enterprise dark-mode toggle. SCSS supports compiled Odoo palettes and common `[data-bs-theme="dark"]` / `.o_dark` theme markers; compatibility with a different third-party theme depends on its theme tokens.
- PDF uploads were exercised end to end. Word/Excel validation and conversion reuse the existing backend; converting office documents still requires LibreOffice/soffice on the server.
- File size is omitted because the existing revision model has no stored file-size metadata. No binary is loaded merely to calculate dashboard/viewer size.
- Search uses native `ilike` matching, not a separate typo-correction service. Recent results are paginated at 12, viewer history at 50, and audit events at 20.
- The UI test helpers must only be used with a dedicated `MOG_TEST_DOCUMENT_UI_*` database. They contain guards and generate random test-user passwords; credentials are not included in these artifacts.

The context-mode skill was used for source/test-output analysis. Odoo frontend APIs were checked against the installed Odoo 17 source and the official [binary field](https://github.com/odoo/odoo/blob/17.0/addons/web/static/src/views/fields/binary/binary_field.js) and [kanban controller](https://github.com/odoo/odoo/blob/17.0/addons/web/static/src/views/kanban/kanban_controller.js) implementations.
