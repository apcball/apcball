/* Run only against a disposable, seeded local Odoo database. See SETUP.md. */
const testURL = process.env.IT_TEST_URL || 'http://127.0.0.1:18069';
if (!['127.0.0.1', 'localhost'].includes(new URL(testURL).hostname)) throw Error('Local test server required');
if (!process.env.IT_TEST_PASSWORD) throw Error('Set IT_TEST_PASSWORD for the disposable test account');
const { chromium } = require('playwright');
const fs = require('fs');
const artifactDir = process.env.IT_TEST_ARTIFACTS || '/tmp/buz-it-stock-browser';
fs.mkdirSync(artifactDir, {recursive:true});
(async () => {
    const browser = await chromium.launch({headless:true});
    const context = await browser.newContext({viewport:{width:1440,height:1000}});
    const page = await context.newPage();
    const errors=[];
    page.on('pageerror', e=>{errors.push(e.message);console.error('PAGE_ERROR', e.stack);});
    await page.goto(testURL + '/web/login?db=MOG_IT_TEST');
    await page.locator('input[name="login"]').fill('admin');
    await page.locator('input[name="password"]').fill(process.env.IT_TEST_PASSWORD);
    await page.getByRole('button',{name:'Log in',exact:true}).click();
    await page.waitForURL('**/web*');
    await page.goto(testURL + '/web#action=buz_it_stock_mobile.action_it_app');
    await page.locator('.buz-it-app').waitFor({timeout:60000});
    await page.locator('.it-product').first().waitFor({timeout:30000});
    fs.writeFileSync(artifactDir + '/page.txt',await page.locator('.buz-it-app').innerText());
    await page.screenshot({path:artifactDir + '/desktop.png',fullPage:true});
    for(const width of [768,390]){
        await page.setViewportSize({width,height:900});
        await page.waitForTimeout(300);
        await page.screenshot({path:`${artifactDir}/screen-${width}.png`,fullPage:true});
        const overflow=await page.locator('.buz-it-app').evaluate(el=>el.scrollWidth>el.clientWidth);
        if(overflow) throw Error('Horizontal overflow at '+width);
    }
    await page.getByRole('button',{name:'เพิ่ม Logitech K120',exact:true}).click();
    await page.getByRole('button',{name:'เพิ่ม Logitech M100',exact:true}).click();
    await page.getByRole('button',{name:'ดูรายการ (2)'}).click();
    await page.getByRole('button',{name:/ต่อไป · เลือกผู้รับ/}).click();
    await page.locator('.it-people button').filter({hasText:'Somchai Jaidee'}).click();
    await page.getByRole('button',{name:'ยืนยันการเบิก',exact:true}).click();
    const canvas=page.locator('canvas');
    await canvas.waitFor();
    await canvas.scrollIntoViewIfNeeded();
    const box=await canvas.boundingBox();
    await page.mouse.move(box.x+30,box.y+80);await page.mouse.down();
    for(const [x,y] of [[70,20],[50,100],[160,45],[210,90],[270,30]]){await page.mouse.move(box.x+x,box.y+y,{steps:8});}
    await page.mouse.up();
    await page.screenshot({path:artifactDir + '/signature.png',fullPage:true});
    await page.locator('button.it-success').click();
    await page.getByRole('heading',{name:'เบิกอุปกรณ์สำเร็จ'}).waitFor({timeout:30000});
    await page.screenshot({path:artifactDir + '/success.png',fullPage:true});
    console.log(JSON.stringify({result:'PASS',document:await page.locator('.it-document-number').innerText(),errors}));
    if(errors.length) throw Error('Unexpected browser errors');
    await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
