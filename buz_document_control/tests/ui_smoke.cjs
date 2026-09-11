/* Run with NODE_PATH pointing to an isolated Playwright install.
 * Usage: node ui_smoke.cjs <fixture-output> <base-url> <artifact-directory>
 * The fixture is generated ONLY on MOG_TEST_DOCUMENT_UI_* by ui_fixture.py.
 */
const fs = require("fs");
const path = require("path");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

async function main() {
    const [fixturePath, baseURL, output] = process.argv.slice(2);
    const line = fs.readFileSync(fixturePath, "utf8").split("\n").find(l => l.startsWith("BDC_UI_FIXTURE="));
    const fixture = JSON.parse(line.slice("BDC_UI_FIXTURE=".length));
    assert(fixture.db.startsWith("MOG_TEST_DOCUMENT_UI_"));
    fs.mkdirSync(output, { recursive: true });
    const browser = await chromium.launch({ headless: true });
    const results = [];
    const errors = [];
    try {
        for (const role of ["reader", "confidential", "manager"]) {
            const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1080 }, acceptDownloads: true });
            const page = await context.newPage();
            page.on("pageerror", error => errors.push(`${role}: ${error.message}`));
            page.on("console", msg => { if (msg.type() === "error") errors.push(`${role}: console: ${msg.text()}`); });
            page.on("response", async response => {
                if (response.url().includes("/web/dataset/") && response.request().method() === "POST") {
                    try { const data = await response.json(); if (data.error) errors.push(`${role}: RPC ${data.error.data?.message || data.error.message}`); } catch {}
                }
                if (response.status() >= 400 && /\/web\/assets\/|\/web\/static\//.test(response.url())) errors.push(`${role}: asset ${response.status()} ${response.url()}`);
            });
            const user = fixture.users[role];
            const auth = await context.request.post("/web/session/authenticate", {
                data: { jsonrpc: "2.0", method: "call", params: { db: fixture.db, login: user.login, password: user.password }, id: 1 },
            });
            const authBody = await auth.json();
            assert.equal(authBody.result?.uid, user.id, `${role}: authentication failed`);
            await page.goto(`/web?db=${fixture.db}#action=${fixture.action_id}&menu_id=${fixture.menu_id}`);
            await page.locator(".bdc-document-card").first().waitFor({ timeout: 120000 });
            await page.screenshot({ path: path.join(output, `${role}-dashboard-desktop.png`), fullPage: true });
            assert.equal(await page.getByRole("button", { name: "Create Document", exact: true }).count(), role === "manager" ? 1 : 0);
            assert.equal(await page.locator(".bdc-kpi").count(), role === "manager" ? 6 : 0);
            const search = page.getByRole("searchbox");
            await search.fill("QP-RESTRICTED-01");
            await page.waitForTimeout(700);
            await page.locator(".bdc-loading").waitFor({ state: "hidden" });
            assert.equal(await page.locator(".bdc-document-card").count(), role === "manager" ? 1 : 0);
            await search.fill("QP-CONFIDENTIAL-01");
            await page.waitForTimeout(700);
            await page.locator(".bdc-loading").waitFor({ state: "hidden" });
            assert.equal(await page.locator(".bdc-document-card").count(), role === "reader" ? 0 : 1);
            await search.fill("QP-ITD-01");
            await page.waitForTimeout(700);
            await page.locator(".bdc-document-card").first().waitFor();
            await page.locator(".bdc-document-card").getByRole("button", { name: "Preview", exact: true }).click();
            await page.locator(".bdc-pdf-frame").waitFor({ timeout: 30000 });
            const pdfFrame = page.frameLocator(".bdc-pdf-frame");
            await pdfFrame.locator("#viewer .page").first().waitFor({ timeout: 30000 });
            await page.screenshot({ path: path.join(output, `${role}-viewer-desktop.png`), fullPage: true });
            assert.equal(await page.getByRole("button", { name: "New Revision", exact: true }).count(), role === "manager" ? 1 : 0);
            assert.equal(await page.getByRole("button", { name: "Access", exact: true }).count(), role === "manager" ? 1 : 0);
            const downloadPromise = page.waitForEvent("download");
            await page.getByRole("button", { name: "Download Original", exact: true }).first().click();
            const download = await downloadPromise;
            assert(download.suggestedFilename().endsWith(".pdf"));
            for (const [key, allowed] of [["QP-RESTRICTED-01", role === "manager"], ["QP-CONFIDENTIAL-01", role !== "reader"]]) {
                for (const route of ["preview", "download"]) {
                    const response = await context.request.get(`/buz_document/${route}/${fixture.documents[key].revision_id}`);
                    assert.equal(response.status(), allowed ? 200 : 403, `${role} ${route} ${key}`);
                }
            }
            const old = await context.request.get(`/buz_document/download/${fixture.documents.obsolete.revision_id}`);
            assert.equal(old.status(), role === "manager" ? 200 : 403);
            for (const [width, height, label] of [[820, 1180, "tablet"], [390, 844, "mobile"]]) {
                await page.setViewportSize({ width, height });
                await page.screenshot({ path: path.join(output, `${role}-viewer-${label}.png`), fullPage: true });
                const overflow = await page.locator(".o_bdc").evaluate(el => el.scrollWidth > el.clientWidth + 2);
                assert.equal(overflow, false, `${role}: ${label} horizontal overflow`);
            }
            await page.setViewportSize({ width: 1440, height: 1080 });
            if (role === "manager") {
                await page.getByRole("button", { name: "Access", exact: true }).click();
                await page.getByText("Visible to all Document Users", { exact: true }).waitFor();
                await page.getByRole("button", { name: "Audit Trail", exact: true }).click();
                await page.locator(".bdc-info-card").getByRole("heading", { name: "Recent Activity" }).waitFor();
                await page.getByRole("button", { name: "Overview", exact: true }).click();
                await page.getByRole("button", { name: "New Revision", exact: true }).click();
                const dialog = page.getByRole("dialog");
                await dialog.locator(".bdc-dropzone").waitFor();
                await dialog.locator('input[type="file"]').setInputFiles({ name: "unsupported.exe", mimeType: "application/octet-stream", buffer: Buffer.from("test") });
                await dialog.getByRole("alert").filter({ hasText: "Unsupported file type" }).waitFor();
                await dialog.locator('input[type="file"]').setInputFiles({ name: "QP-ITD-01_Rev06.pdf", mimeType: "application/pdf", buffer: Buffer.from(fixture.pdf, "base64") });
                await dialog.getByText("QP-ITD-01_Rev06.pdf", { exact: true }).waitFor();
                await dialog.locator('[name="revision"] input').fill("06");
                await dialog.locator('[name="change_description"] textarea').fill("Browser test: revised procedure");
                await page.screenshot({ path: path.join(output, "manager-new-revision.png"), fullPage: true });
                await dialog.getByRole("button", { name: "Create Draft", exact: true }).click();
                await page.locator(".o_form_view").waitFor({ timeout: 30000 });
                await page.getByRole("button", { name: "Send to Review", exact: true }).click();
                await page.getByRole("button", { name: "Publish", exact: true }).click();
                await page.getByRole("dialog").getByRole("button", { name: "Ok", exact: true }).click();
                await page.waitForTimeout(1000);
                await page.screenshot({ path: path.join(output, "manager-published-revision.png"), fullPage: true });
            }
            await page.goto(`/web?db=${fixture.db}#action=${fixture.action_id}&menu_id=${fixture.menu_id}`);
            await page.locator(".bdc-category").first().waitFor({ timeout: 30000 });
            await page.locator(".bdc-category").filter({ hasText: "QP" }).click();
            await page.locator(".bdc-native-card").first().waitFor();
            await page.screenshot({ path: path.join(output, `${role}-kanban.png`), fullPage: true });
            await page.locator(".bdc-native-card").filter({ hasText: "QP-ITD-01" }).getByRole("button", { name: "Preview", exact: true }).click();
            await page.locator(".bdc-pdf-frame").waitFor();
            await page.getByRole("button", { name: "Back to Documents", exact: true }).click();
            await page.locator(".bdc-document-card").first().waitFor();
            await page.setViewportSize({ width: 390, height: 844 });
            await page.screenshot({ path: path.join(output, `${role}-dashboard-mobile.png`), fullPage: true });
            assert.equal(await page.locator(".o_bdc").evaluate(el => el.scrollWidth > el.clientWidth + 2), false);
            results.push(`${role}: dashboard, search, role controls, PDF, download, direct URL security, responsive layout, native kanban PASS`);
            await context.close();
        }
        assert.deepEqual(errors, [], "Browser console/RPC/asset errors");
    } finally {
        await browser.close();
        fs.writeFileSync(path.join(output, "browser-results.json"), JSON.stringify({ results, errors }, null, 2));
        console.log(JSON.stringify({ results, errors }, null, 2));
    }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
