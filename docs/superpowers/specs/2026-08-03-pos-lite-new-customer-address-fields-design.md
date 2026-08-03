# pos_lite terminal: proper res.partner address fields on "New Customer"

## Context
The "สร้างลูกค้าใหม่" (New Customer) modal in the POS Lite terminal
(`pos_lite/views/pos_lite_terminal.xml`) currently has a single free-text address
textarea (`ncStreet`, mapped to `street`) and one combined text field
(`ncCity`, labeled "อำเภอ/เขต จังหวัด") mapped to `city`. There's no `street2`, no
`state_id`, and `country_id` is never set. This doesn't match `res.partner`'s real
address shape (`street`, `street2`, `city`, `state_id`, `zip`, `country_id`), so
province data is lost into a free-text city field.

## Approach
Split the address block into fields matching `res.partner`, decisions per user:
- **Country**: fixed to Thailand, always. No dropdown, no country switching — set
  server-side via `env.ref('base.th')`, matching this being a Thai-only company.
- **State (จังหวัด)**: a real `<select>` dropdown populated from
  `res.country.state` (Thailand only), not free text — avoids name-mismatch when
  creating the partner.
- **City (อำเภอ/เขต)**: stays free text, matches `res.partner.city`.
- **Street / Street2**: two separate text inputs.
- **Zip**: unchanged.

### Frontend (`pos_lite/views/pos_lite_terminal.xml`)
- New Customer modal fields, replacing lines 824-841:
  - `ncStreet` — text input, label "ที่อยู่ (บ้านเลขที่ ถนน)"
  - `ncStreet2` — text input, label "ที่อยู่ 2 (เพิ่มเติม)"
  - row: `ncCity` (text, "อำเภอ/เขต") + `ncZip` (text, existing, "รหัสไปรษณีย์")
  - row: `ncState` — `<select>`, label "จังหวัด", populated on modal open
- `state.thStates` cache: fetch once (first time the modal opens, or on terminal
  start) from a new endpoint, reused across opens.
- `saveNewCustomer()`: add `street2: ...`, `state_id: parseInt(ncState.value) ||
  false` to the POST body sent to `/pos_lite/api/create_customer`.
- Address display strings (the ones built client-side aren't — they come from the
  server response) stay as-is except the server now includes street2/state in the
  formatted `address` string it returns (see below).

### Backend
- **New endpoint** `POST /pos_lite/api/states` (`pos_lite/controllers/main.py`,
  same pattern as `get_warehouses`): returns
  `res.country.state.search_read([('country_id.code','=','TH')], ['name'],
  order='name')`, sudo (cashiers aren't config managers, same reasoning as
  `get_warehouses`... actually `get_warehouses` runs as normal user; states is
  pure reference data, no sudo needed since `res.country.state` is globally
  readable).
- `pos_lite/models/res_partner.py` `pos_lite_create_customer`: add to `vals`:
  - `'street2': (data.get('street2') or '').strip() or False`
  - `'state_id': int(data['state_id']) if data.get('state_id') else False`
  - `'country_id': self.env.ref('base.th').id` (always, regardless of input —
    don't trust client for this)
- `pos_lite/controllers/main.py` `create_customer` response and `customer_search`
  response: extend the `address` string builder from `[street, city, zip]` to
  `[street, street2, city, state_id.name, zip]` (filtered for falsy), so the
  terminal's read-only address displays include the new parts.

## Out of scope
- No country dropdown (fixed Thailand per user decision).
- Not touching the separate `custAddress` free-text field in the main order form
  (used for `partner_address` on the order itself, independent of `res.partner`
  fields) — user's request is specifically about the New Customer creation modal.
- No validation that `state_id` actually belongs to Thailand (dropdown is
  pre-filtered to Thai states only, so an invalid id would require a tampered
  request — not defended against beyond existing whitelisting).

## Verification
- Open POS Lite terminal in DEV, open "สร้างลูกค้าใหม่", confirm the จังหวัด dropdown
  populates with Thai provinces.
- Create a customer with street/street2/city/state/zip filled in; check the
  resulting `res.partner` record in Odoo has all fields set correctly
  (`country_id` = Thailand).
- Confirm the returned/displayed address string includes street2 and the
  province name.
- Search for that customer via the terminal's customer search and confirm the
  address preview also reflects the new fields.
