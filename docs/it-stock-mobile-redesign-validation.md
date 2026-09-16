# IT Issue Mobile redesign — validation

Implemented on 13 September 2026 in `buz_it_stock_mobile`.

The app now uses the supplied mockup's pale blue background, white rounded cards, blue actions, desktop dashboard, mobile equipment list and bottom navigation. Cart, recipient, signature, completion, lot selection and receipt details share the same visual language. Receipt details use Odoo's dialog service, preserving the underlying cart and supporting Escape to close.

Desktop retains the existing Odoo navbar. All metrics come from the existing APIs, valuation remains manager-only, and quantities with different units are never combined in a donut. Product images come from Odoo with icon fallbacks; the bundled banner is an SVG illustration. The disposable fixtures do not contain product photos, so the screenshots demonstrate the icon fallback. No database schema or stock-processing changes were required.

## Verification

| Check | Result |
| --- | --- |
| Odoo tests using `docker-compose.it-stock-test.yml`, separate project `buz-it-redesign-test` | 20 tests, 0 failures, 0 errors |
| Odoo QUnit module `buz_it_stock_mobile > IT Issue Mobile` | 3 tests, 10 assertions passed |
| Browser acceptance at 375, 390, 768, 1024 and 1440 pixels | Passed; no horizontal content overflow or browser errors |
| Full issue, receipt detail, Escape close, and own-history navigation | Passed |
| Touch signature and signature preservation on rotation | Passed |
| Lost signing response recovery, competing serial requests, duplicate confirmation | Passed |
| Empty dashboard, zero valuation, operator presentation and mixed units | Passed using intercepted read responses |
| Failed images, sold-out item, long product name, own/company history filters | Passed |
| Lot selection, quantity editing, cart removal and missing configuration | Passed |
| XML/SVG parsing, JavaScript syntax and `git diff --check` | Passed |

Browser edge-case fixtures test presentation; actual access control is covered by the Odoo test suite. All receipt creation and stock changes during verification were confined to the disposable local `MOG_IT_TEST` database. DEV and PROD were not used.

## Screenshots

- [Desktop dashboard](/private/tmp/buz-it-redesign-browser/desktop.png)
- [Mobile 390 px](/private/tmp/buz-it-redesign-browser/screen-390.png)
- [Mobile 375 px](/private/tmp/buz-it-redesign-browser/screen-375.png)
- [Tablet 768 px](/private/tmp/buz-it-redesign-browser/screen-768.png)
- [Desktop 1024 px](/private/tmp/buz-it-redesign-browser/screen-1024.png)
- [Cart](/private/tmp/buz-it-redesign-browser/cart.png)
- [Recipient](/private/tmp/buz-it-redesign-browser/receiver.png)
- [Signature](/private/tmp/buz-it-redesign-browser/signature.png)
- [Completion](/private/tmp/buz-it-redesign-browser/success.png)
- [Receipt details](/private/tmp/buz-it-redesign-browser/detail.png)

The separate local preview is running at `http://127.0.0.1:18070` in container `buz-it-redesign-preview`. Test credentials: `admin` / `redesign-isolated-only`, database `MOG_IT_TEST`. This preview is disposable and has not been deployed to DEV or PROD.

Reproduction instructions and the QUnit URL are in `buz_it_stock_mobile/SETUP.md`. Browser scripts accept `IT_TEST_URL`, `IT_TEST_PASSWORD` and, for acceptance screenshots, `IT_TEST_ARTIFACTS`.
