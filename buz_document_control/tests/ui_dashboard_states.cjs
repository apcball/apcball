/* Read-only browser checks on the dedicated UI fixture database.
 * Usage matches ui_smoke.cjs. Empty/error/loading responses are intercepted
 * in the browser; no real document is changed by this script.
 */
const fs = require("fs");
const path = require("path");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

async function main() {
    const [fixturePath, baseURL, output] = process.argv.slice(2);
    const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8").split("\n")
        .find(line => line.startsWith("BDC_UI_FIXTURE=")).slice("BDC_UI_FIXTURE=".length));
    assert(fixture.db.startsWith("MOG_TEST_DOCUMENT_UI_"));
    fs.mkdirSync(output, { recursive: true });
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ baseURL, viewport: { width: 1630, height: 1080 } });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const rpc = "**/web/dataset/call_kw/buz.document/get_document_center_data";
    const dashboardURL = `/web?db=${fixture.db}#action=${fixture.action_id}&menu_id=${fixture.menu_id}`;
    const ready = () => page.locator('.bdc-center[aria-busy="false"]').waitFor();
    const home = async () => { await page.goto(dashboardURL); await ready(); };
    const snapshot = name => page.screenshot({ path: path.join(output, name + ".png"), fullPage: true });
    try {
        const user = fixture.users.manager;
        const auth = await context.request.post("/web/session/authenticate", {
            data: { jsonrpc: "2.0", method: "call", params: { db: fixture.db, login: user.login, password: user.password }, id: 1 },
        });
        assert.equal((await auth.json()).result.uid, user.id);
        const response = await context.request.post("/web/dataset/call_kw/buz.document/get_document_center_data", {
            data: { jsonrpc: "2.0", method: "call", params: { model: "buz.document", method: "get_document_center_data", args: [], kwargs: {} }, id: 2 },
        });
        const summary = (await response.json()).result;
        assert(summary?.counts);
        await home();
        await snapshot("manager-dashboard-final-desktop");
        for (const [width, height, label] of [[1440, 1080, "desktop"], [820, 1180, "tablet"], [390, 844, "mobile"]]) {
            await page.setViewportSize({ width, height });
            assert.equal(await page.locator(".bdc-center").evaluate(el => el.scrollWidth > el.clientWidth + 2), false);
            await snapshot(`manager-dashboard-final-${label}`);
        }
        await page.setViewportSize({ width: 1630, height: 1080 });
        for (const [index, key] of ["all", "published", "due", "overdue", "draft", "due"].entries()) {
            await page.locator(".bdc-kpi").nth(index).click();
            await page.locator(".o_list_view").waitFor();
            assert.equal(await page.locator(".o_data_row").count(), summary.counts[key]);
            await home();
        }
        for (const selector of [".bdc-types-panel", ".bdc-departments", ".bdc-recent"]) {
            await page.locator(selector).getByRole("button", { name: "ดูทั้งหมด", exact: true }).click();
            await page.locator(".o_list_view, .o_kanban_view").first().waitFor();
            assert.equal(await page.locator(".o_data_row, .bdc-native-card").count(), summary.counts.all);
            await home();
        }
        await page.locator(".bdc-attention").getByRole("button", { name: "ดูทั้งหมด", exact: true }).click();
        await page.locator(".o_list_view").waitFor();
        assert(await page.locator(".o_data_row").count() >= summary.needs_attention.length);
        await home();
        const draft = page.locator(".bdc-attention-table tr").filter({ hasText: "QP-DRAFT-01" });
        await draft.getByRole("button", { name: "Edit", exact: true }).click();
        await page.locator(".o_form_view").waitFor();
        assert.equal(await page.locator('[name="document_no"] input').inputValue(), "QP-DRAFT-01");
        await home();
        const bars = page.locator(".bdc-department-row");
        const barCount = await bars.count();
        for (let index = 0; index < barCount; index++) {
            const expected = Number(await bars.nth(index).locator(":scope > span").last().textContent());
            await bars.nth(index).click();
            await page.locator(".o_list_view").waitFor();
            assert.equal(await page.locator(".o_data_row").count(), expected);
            await home();
        }
        await page.getByRole("searchbox").fill("NO-DOCUMENT-WITH-THIS-NUMBER");
        await page.getByRole("searchbox").press("Enter");
        await page.getByRole("heading", { name: "ไม่มีเอกสารในหมวดนี้", exact: true }).waitFor();
        await snapshot("dashboard-empty-search");
        await page.locator(".bdc-search-context").getByRole("button", { name: "Clear filters", exact: true }).click();
        await page.locator(".bdc-dashboard-card").first().waitFor();

        let release;
        const held = new Promise(resolve => { release = resolve; });
        await page.route(rpc, async route => { await held; await route.continue(); });
        await page.getByRole("button", { name: "Refresh documents", exact: true }).click();
        await page.locator('.bdc-center[aria-busy="true"]').waitFor();
        await snapshot("dashboard-loading");
        release();
        await ready();
        await page.unroute(rpc);

        await page.route(rpc, route => route.fulfill({ json: { jsonrpc: "2.0", id: 3,
            error: { code: 200, message: "Intentional test failure", data: { message: "Intentional test failure" } } } }));
        await page.getByRole("button", { name: "Refresh documents", exact: true }).click();
        await page.getByRole("alert").waitFor();
        await snapshot("dashboard-error");
        await page.unroute(rpc);
        await page.getByRole("button", { name: "Try Again", exact: true }).click();
        await page.locator(".bdc-dashboard-card").first().waitFor();
        await ready();

        await page.route(rpc, route => route.fulfill({ json: { jsonrpc: "2.0", id: 4, result: {
            ...summary, documents: [], total: 0, needs_attention: [], document_types: [], departments: [],
            created_this_month: 0, counts: Object.fromEntries(Object.keys(summary.counts).map(key => [key, 0])),
        } } }));
        await page.getByRole("button", { name: "Refresh documents", exact: true }).click();
        await page.getByText("ยังไม่มีเอกสารสำหรับแสดงกราฟ", { exact: true }).waitFor();
        assert((await page.locator(".bdc-kpi strong").allTextContents()).every(value => value === "0"));
        assert(!/NaN|Infinity|undefined/.test(await page.locator(".bdc-center").innerText()));
        await snapshot("dashboard-empty-data");
        await page.unroute(rpc);
        assert.deepEqual(errors, []);
        console.log("PASS: six KPI drilldowns, all section links, Edit, department/other/unassigned drilldowns, Enter search, empty, loading, error/retry, zero totals, responsive screenshots");
    } finally {
        await browser.close();
    }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
