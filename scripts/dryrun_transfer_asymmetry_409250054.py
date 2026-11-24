# DRY-RUN (read-only): asymmetric transfer legs for product 409250054, window 2026-03-31..2026-10-31.
import base64, io, datetime
from collections import defaultdict
import xlsxwriter
CODE = '409250054'
try:
    p = env['product.product'].search([('default_code', '=', CODE)])
    cut = datetime.datetime(2026, 3, 30, 17, 0); end = datetime.datetime(2026, 10, 31, 17, 0)
    tz = datetime.timedelta(hours=7)
    svls = env['stock.valuation.layer'].sudo().search([('product_id', '=', p.id), ('warehouse_id', '!=', False)])
    L = [s for s in svls if not (s.stock_move_id.state == 'cancel' or (s.description or '').startswith('Reverse cancelled'))
         and cut <= (s.accounting_date or s.create_date) < end]
    bymove = defaultdict(list)
    for s in L:
        bymove[s.stock_move_id.id].append(s)
    asym = []
    for mid, ss in bymove.items():
        q = sum(s.quantity for s in ss); v = sum(s.value for s in ss)
        if abs(q) < 1e-6 and abs(v) >= 0.01 and mid:
            asym.append((mid, ss, v))
    asym.sort(key=lambda t: ((t[1][0].accounting_date or t[1][0].create_date), t[0]))
    bywh = defaultdict(lambda: [0.0, 0.0])
    for s in L:
        bywh[s.warehouse_id.name][0] += s.quantity; bywh[s.warehouse_id.name][1] += s.value
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {'in_memory': True})
    b = wb.add_format({'bold': True}); h = wb.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1, 'text_wrap': True})
    n = wb.add_format({'num_format': '#,##0.00', 'border': 1}); c4 = wb.add_format({'num_format': '#,##0.0000', 'border': 1})
    t = wb.add_format({'border': 1}); dt = wb.add_format({'num_format': 'dd/mm/yyyy', 'border': 1}); nb = wb.add_format({'num_format': '#,##0.00', 'border': 1, 'bold': True})
    # sheet 1 summary
    s1 = wb.add_worksheet('สรุป'); s1.set_column('A:A', 34); s1.set_column('B:E', 18)
    s1.write(0, 0, 'DRY-RUN: ขาโอนที่มูลค่าสองขาไม่เท่ากัน (ไม่ได้แก้ข้อมูล)', b)
    s1.write(1, 0, 'สินค้า %s %s | ช่วง 31/03/2026 - 31/10/2026 | เกณฑ์ layer เดียวกับรายงาน FIFO' % (p.default_code, p.name))
    for i, hh in enumerate(['คลัง', 'จำนวนสุทธิ', 'มูลค่าสุทธิ (SVL)']): s1.write(3, i, hh, h)
    r = 4
    for wh, (q, v) in sorted(bywh.items()):
        s1.write(r, 0, wh, t); s1.write(r, 1, q, n); s1.write(r, 2, v, n); r += 1
    s1.write(r, 0, 'รวม', b); s1.write(r, 1, sum(x[0] for x in bywh.values()), nb); s1.write(r, 2, sum(x[1] for x in bywh.values()), nb)
    r += 2
    s1.write(r, 0, 'เอกสารโอนที่จำนวนหักล้างแต่มูลค่าไม่หักล้าง', b); s1.write(r, 1, len(asym), nb); r += 1
    s1.write(r, 0, 'ผลต่างมูลค่ารวมของเอกสารเหล่านี้', b); s1.write(r, 1, sum(a[2] for a in asym), nb); r += 1
    s1.write(r, 0, '  ผลต่างบวก (เข้ามากกว่าออก)', t); s1.write(r, 1, sum(a[2] for a in asym if a[2] > 0), n); r += 1
    s1.write(r, 0, '  ผลต่างลบ (ออกมากกว่าเข้า)', t); s1.write(r, 1, sum(a[2] for a in asym if a[2] < 0), n); r += 2
    s1.write(r, 0, 'หมายเหตุ', b); r += 1
    for line in ['- ผลต่างรวมนี้เท่ากับส่วนต่างรายงานนี้ กับ Imex ของสินค้านี้ (Imex ตีมูลค่าขาโอนต่างจาก SVL)',
                 '- มูลค่าค้าง RM02 27,216.89 (จำนวน 0) เกิดจากขาออกถูกตัดราคาเฉลี่ย 0.5258 ต่ำกว่าราคารับเฉลี่ย 0.6839 — ไม่ได้ผูกกับเอกสารโอนรายใบในไฟล์นี้',
                 '- ไฟล์นี้ใช้ดูเท่านั้น ยังไม่มีการแก้ SVL/quant ใด ๆ']:
        s1.write(r, 0, line); r += 1
    # sheet 2 docs
    s2 = wb.add_worksheet('เอกสารโอน'); s2.freeze_panes(1, 0)
    heads = ['วันที่', 'เลขที่เอกสาร', 'ประเภท', 'move id', 'จำนวน', 'คลังออก', 'มูลค่าออก', '@ ออก', 'คลังเข้า', 'มูลค่าเข้า', '@ เข้า', 'ผลต่างมูลค่า (เข้า+ออก)', 'SVL id']
    for i, hh in enumerate(heads): s2.write(0, i, hh, h)
    s2.set_column('A:A', 12); s2.set_column('B:C', 22); s2.set_column('D:M', 16)
    r = 1
    for mid, ss, v in asym:
        m = ss[0].stock_move_id
        outs = [s for s in ss if s.quantity < 0]; ins = [s for s in ss if s.quantity > 0]
        oq = -sum(s.quantity for s in outs); ov = sum(s.value for s in outs)
        iq = sum(s.quantity for s in ins); iv = sum(s.value for s in ins)
        d = (ss[0].accounting_date or ss[0].create_date) + tz
        s2.write_datetime(r, 0, d, dt)
        s2.write(r, 1, m.picking_id.name or m.reference or '', t); s2.write(r, 2, m.picking_type_id.name or '', t); s2.write(r, 3, mid, t)
        s2.write(r, 4, iq, n)
        s2.write(r, 5, ', '.join(sorted({s.warehouse_id.name for s in outs})), t); s2.write(r, 6, ov, n); s2.write(r, 7, (ov / -oq) if oq else 0, c4)
        s2.write(r, 8, ', '.join(sorted({s.warehouse_id.name for s in ins})), t); s2.write(r, 9, iv, n); s2.write(r, 10, (iv / iq) if iq else 0, c4)
        s2.write(r, 11, v, n); s2.write(r, 12, ','.join(str(s.id) for s in ss), t)
        r += 1
    s2.write(r, 11, sum(a[2] for a in asym), nb)
    # sheet 3 layers
    s3 = wb.add_worksheet('layer รายละเอียด'); s3.freeze_panes(1, 0)
    for i, hh in enumerate(['SVL id', 'move id', 'เลขที่เอกสาร', 'วันที่บัญชี', 'คลัง', 'จำนวน', 'มูลค่า', '@', 'description']): s3.write(0, i, hh, h)
    s3.set_column('A:B', 12); s3.set_column('C:C', 22); s3.set_column('D:H', 16); s3.set_column('I:I', 40)
    r = 1
    for mid, ss, v in asym:
        for s in sorted(ss, key=lambda x: x.id):
            m = s.stock_move_id
            s3.write(r, 0, s.id, t); s3.write(r, 1, mid, t); s3.write(r, 2, m.picking_id.name or m.reference or '', t)
            s3.write_datetime(r, 3, (s.accounting_date or s.create_date) + tz, dt); s3.write(r, 4, s.warehouse_id.name, t)
            s3.write(r, 5, s.quantity, n); s3.write(r, 6, s.value, n); s3.write(r, 7, (s.value / s.quantity) if s.quantity else 0, c4)
            s3.write(r, 8, (s.description or '')[:80], t); r += 1
    wb.close()
    print('XLSX', base64.b64encode(buf.getvalue()).decode())
    print('INFO docs', len(asym), 'sum', round(sum(a[2] for a in asym), 2), 'layers', sum(len(a[1]) for a in asym))
    # integrity: nothing written
    print('INFO ro', env.cr.rowcount)
except Exception as e:
    import traceback; print('ERR', traceback.format_exc()[-800:])
env.cr.rollback()
