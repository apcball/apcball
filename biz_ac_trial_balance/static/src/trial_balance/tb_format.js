/** @odoo-module **/

/**
 * รูปแบบตัวเลขของงบทดลอง — "1,234,567.89"
 *
 * โมดูลนี้ไม่พึ่งไลบรารีจัดรูปแบบของโมดูลอื่น เพื่อให้ติดตั้งงบทดลองได้ลำพัง
 */
export function fmtNum(v, digits = 2) {
    if (v === null || v === undefined || v === false || isNaN(v)) {
        return "–";
    }
    return Number(v).toLocaleString("th-TH", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    });
}
