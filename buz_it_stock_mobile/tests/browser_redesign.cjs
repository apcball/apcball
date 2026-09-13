/* UI edge cases on the disposable local preview; RPC fixtures never write data. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const testURL = process.env.IT_TEST_URL || 'http://127.0.0.1:18069';
if (!['127.0.0.1', 'localhost'].includes(new URL(testURL).hostname)) throw Error('Local test server required');
if (!process.env.IT_TEST_PASSWORD) throw Error('Set IT_TEST_PASSWORD for the disposable test account');

(async () => {
    const browser = await chromium.launch({headless: true});
    try {
        const context = await browser.newContext({baseURL: testURL, viewport: {width: 1440, height: 1000}});
        const response = await context.request.post('/web/session/authenticate', {data: {
            jsonrpc: '2.0', method: 'call', params: {db: 'MOG_IT_TEST', login: 'admin', password: process.env.IT_TEST_PASSWORD},
        }});
        assert.ok(!(await response.json()).error, 'Authentication succeeds');
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        let mode = 'empty';
        let bootstrap;
        let myDomain;
        await page.route('**/web/dataset/call_kw/buz.it.issue/get_bootstrap', async route => {
            const data = await (await route.fetch()).json();
            bootstrap = data.result;
            if (mode === 'operator') data.result.manager = false;
            if (mode === 'setup') data.result.setup_error = 'กรุณาตั้งค่าคลังทดสอบ';
            await route.fulfill({json: data});
        });
        await page.route('**/web/dataset/call_kw/buz.it.issue/get_dashboard', async route => {
            const data = await (await route.fetch()).json();
            if (mode === 'empty') Object.assign(data.result, {categories: [], recent: [], month_count: 0, stock: {}, product_count: 0, value: 0});
            if (mode === 'operator') Object.assign(data.result, {value: false});
            if (mode === 'mixed') Object.assign(data.result, {categories: [{name: 'Keyboard', uom: 'ชิ้น', qty: 2}, {name: 'Cable', uom: 'เมตร', qty: 3}], totals: {'ชิ้น': 2, 'เมตร': 3}});
            await route.fulfill({json: data});
        });
        await page.route('**/web/dataset/call_kw/buz.it.issue/get_catalog', async route => {
            const data = await (await route.fetch()).json();
            if (mode === 'empty') Object.assign(data.result, {products: [], more: false});
            if (mode === 'images') {
                const products = data.result.products;
                products[0] = {...products[0], name: 'อุปกรณ์ทดสอบชื่อยาว'.repeat(8), has_image: true, available: 0};
                products[1] = {...products[1], has_image: true};
            }
            await route.fulfill({json: data});
        });
        await page.route('**/web/image/product.product/**', route => route.abort());
        page.on('request', request => {
            if (request.url().includes('/buz.it.issue/web_search_read')) myDomain = request.postDataJSON().params.kwargs.domain;
        });
        async function open(nextMode) {
            mode = nextMode;
            await page.goto(`/web?debug=assets&it_test=${mode}#action=buz_it_stock_mobile.action_it_app`);
            await page.locator(mode === 'setup' ? '.it-setup' : '.it-overview').waitFor();
        }
        await open('empty');
        assert.equal(await page.locator('.it-product').count(), 0);
        assert.equal(await page.locator('.it-donut').count(), 0);
        assert.equal((await page.locator('.it-value').innerText()).includes('0'), true, 'Manager sees a legitimate zero value');
        await open('operator');
        assert.equal(await page.locator('.it-value').count(), 0, 'No manager valuation in operator UI');
        await page.setViewportSize({width: 390, height: 900});
        await page.locator('.it-menu-toggle').click();
        assert.equal(await page.locator('.it-sidebar').getByRole('button', {name: 'ตั้งค่าคลัง', exact: true}).count(), 0);
        await page.locator('.it-mobile-close').click();
        await page.setViewportSize({width: 1440, height: 1000});
        await open('mixed');
        assert.equal(await page.locator('.it-donut').count(), 0, 'Mixed units never share a donut');
        assert.equal(await page.locator('.it-chart progress').count(), 2);
        await open('images');
        await page.waitForFunction(() => !document.querySelector('.it-product-image img'));
        assert.equal(await page.locator('.it-product').first().locator('.it-add').isDisabled(), true);
        for (const width of [1440, 1024, 768, 390, 375]) {
            await page.setViewportSize({width, height: 900});
            assert.equal(await page.locator('.it-main').evaluate(el => el.scrollWidth > el.clientWidth), false, `Long name fits at ${width}`);
        }
        await page.locator('.it-bottom-nav').getByRole('button', {name: 'รายการของฉัน'}).click();
        await page.locator('.o_list_view').waitFor();
        assert.ok(myDomain.some(term => Array.isArray(term) && term[0] === 'create_uid' && term[2] === bootstrap.user_id));
        assert.ok(myDomain.some(term => Array.isArray(term) && term[0] === 'company_id' && term[2] === bootstrap.company_id));
        await open('lots');
        await page.getByRole('button', {name: 'เพิ่ม HDMI Cable 2m', exact: true}).click();
        await page.locator('.it-lot-list button').first().click();
        await page.locator('.it-lot-modal').getByRole('button', {name: 'เสร็จแล้ว'}).click();
        await page.locator('.it-cart-bar button').click();
        await page.locator('.it-cart-line').waitFor();
        assert.equal(await page.locator('.it-cart-line').count(), 1);
        assert.ok((await page.locator('.it-cart-line').innerText()).includes('HDMI-2026-A'));
        await page.locator('.it-qty input').fill('2');
        await page.locator('.it-qty input').press('Tab');
        await page.waitForFunction(() => document.querySelector('.it-total')?.textContent.includes('2 Units'));
        assert.ok((await page.locator('.it-total').innerText()).includes('2 Units'));
        await page.locator('.it-remove').click();
        await page.locator('.it-cart-line').waitFor({state: 'detached'});
        assert.equal(await page.locator('.it-cart-line').count(), 0);
        await open('setup');
        assert.equal(await page.locator('.it-bottom-nav').count(), 0);
        assert.equal(await page.locator('.it-overview').count(), 0);
        assert.equal(await page.locator('.o_error_dialog').count(), 0);
        assert.deepEqual(errors, []);
        console.log('PASS empty dashboard, zero valuation, operator UI, mixed units, image fallback, sold out, long names, own/company history, lot selection, quantity editing, removal, setup state');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exit(1); });
