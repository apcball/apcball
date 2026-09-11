/* Uses the disposable fixture and Playwright runtime described in ui_smoke.cjs. */
const fs = require("fs");
const path = require("path");
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
    const [fixturePath, baseURL, output] = process.argv.slice(2);
    const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8").split("\n").find(l => l.startsWith("BDC_UI_FIXTURE=")).slice(15));
    assert(fixture.db.startsWith("MOG_TEST_DOCUMENT_UI_"));
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 1080 } });
    const user = fixture.users.manager;
    const errors = [];
    const results = [];
    const page = await context.newPage();
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    async function rpc(model, method, args, kwargs = {}) {
        const response = await context.request.post(`/web/dataset/call_kw/${model}/${method}`, {
            data: { jsonrpc: "2.0", params: { model, method, args, kwargs } },
        });
        const data = await response.json();
        assert(!data.error, data.error?.data?.message);
        return data.result;
    }
    try {
        await context.request.post("/web/session/authenticate", { data: { jsonrpc: "2.0", params: { db: fixture.db, login: user.login, password: user.password } } });
        const docId = await rpc("buz.document", "create", [{ document_no: `ATTACH-${Date.now()}`, name: "Attachment browser regression" }]);
        const revId = await rpc("buz.document.revision", "create", [{ document_id: docId, revision: "00", effective_date: "2026-09-01", change_description: "Native draft upload" }]);
        await page.goto(`/web?db=${fixture.db}#id=${revId}&model=buz.document.revision&view_type=form`);
        await page.getByRole("tab", { name: "Original Document", exact: true }).click({ timeout: 60000 });
        await page.locator('[name="original_file"] input[type="file"]').setInputFiles({ name: "แบบฟอร์ม_Rev00.pdf", mimeType: "application/pdf", buffer: Buffer.from(fixture.pdf, "base64") });
        await page.locator(".o_form_button_save").click();
        await page.waitForTimeout(1000);
        let [revision] = await rpc("buz.document.revision", "read", [[revId], ["original_filename", "preview_status", "original_file"]]);
        assert.equal(revision.original_filename, "แบบฟอร์ม_Rev00.pdf");
        assert.equal(revision.preview_status, "ready");
        assert.equal(revision.original_file, fixture.pdf);
        results.push("Native draft attachment: Thai filename, binary persistence and PDF preview PASS");
        await page.screenshot({ path: path.join(output, "manager-native-attachment.png"), fullPage: true });
        await page.goto(`/web?db=${fixture.db}#id=${docId}&model=buz.document&view_type=form`);
        await page.getByRole("button", { name: "Upload Document", exact: true }).click({ timeout: 30000 });
        const dialog = page.getByRole("dialog");
        await dialog.locator(".bdc-dropzone").waitFor();
        await dialog.locator('[name="revision"] input').fill("01");
        await dialog.locator('[name="change_description"] textarea').fill("Drag and drop upload");
        await dialog.locator(".bdc-dropzone").evaluate((element, pdf) => {
            const bytes = Uint8Array.from(atob(pdf), c => c.charCodeAt(0));
            const transfer = new DataTransfer();
            transfer.items.add(new File([bytes], "แนบไฟล์_Rev01.pdf", { type: "application/pdf" }));
            element.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
        }, fixture.pdf);
        await dialog.getByText("แนบไฟล์_Rev01.pdf", { exact: true }).waitFor();
        await dialog.getByRole("button", { name: "Create Draft", exact: true }).click();
        await dialog.locator(".o_bdc_revision_wizard").waitFor({ state: "hidden" });
        await page.locator(".o_form_view").first().waitFor();
        await page.waitForTimeout(1000);
        [revision] = await rpc("buz.document.revision", "search_read", [[["document_id", "=", docId], ["revision", "=", "01"]], ["original_filename", "preview_status", "original_file", "state"]]);
        assert.equal(revision.original_filename, "แนบไฟล์_Rev01.pdf");
        assert.equal(revision.preview_status, "ready");
        assert.equal(revision.original_file, fixture.pdf);
        assert.equal(revision.state, "draft");
        results.push("Document Upload button and drag/drop wizard: file persisted as draft PASS");
        assert.deepEqual(errors, []);
    } finally {
        await page.screenshot({ path: path.join(output, "attachment-final.png"), fullPage: true }).catch(() => {});
        fs.writeFileSync(path.join(output, "attachment-results.json"), JSON.stringify({ results, errors }, null, 2));
        console.log(JSON.stringify({ results, errors }, null, 2));
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
