from io import BytesIO
from pathlib import Path

from lxml import html as lxml_html
from PIL import Image, ImageDraw, ImageFont, features
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from odoo import models
from odoo.exceptions import UserError


REPORT_NAME = 'buz_share_certificate.report_share_certificate'
IMAGE_DPI = 600
FONT_DIR = Path(__file__).resolve().parent.parent / 'static' / 'fonts'


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf(self, report_ref, res_ids=None, data=None):
        if self._get_report(report_ref).report_name != REPORT_NAME or not res_ids:
            return super()._render_qweb_pdf(report_ref, res_ids=res_ids, data=data)

        certificates = self.env['buz.share.certificate.print.wizard'].browse(res_ids)
        certificates.check_access_rights('read')
        certificates.check_access_rule('read')

        if not features.check('raqm'):
            raise UserError('ไม่สามารถพิมพ์ใบหุ้นได้: ระบบจัดรูปอักษรไทย RAQM ไม่พร้อมใช้งาน')

        markup, _content_type = self._render_qweb_html(report_ref, res_ids, data=data)
        document = lxml_html.fromstring(markup)
        articles = document.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " article ")]')
        if len(articles) != len(res_ids):
            raise UserError('ไม่สามารถพิมพ์ใบหุ้นได้: จำนวนหน้ารายงานไม่ตรงกับจำนวนใบหุ้น')

        layout = self.env['buz.share.certificate.layout.config'].sudo().get_default_config()
        if not layout:
            raise UserError('ไม่พบการตั้งค่าตำแหน่งพิมพ์ใบหุ้น')

        output = BytesIO()
        page_width, page_height = landscape(A4)
        pdf = canvas.Canvas(output, pagesize=(page_width, page_height))
        fonts = {}
        for article in articles:
            for field in article.xpath('.//span[contains(concat(" ", normalize-space(@class), " "), " field-value ")]'):
                value = field.text_content().strip()
                if not value:
                    continue
                style = dict(part.split(':', 1) for part in field.get('style', '').split(';') if ':' in part)
                if style.get('display') == 'none':
                    continue
                if not {'left', 'top', 'font-size'} <= style.keys():
                    raise UserError('ไม่สามารถพิมพ์ใบหุ้นได้: ตำแหน่งข้อความไม่ครบ')
                # QWeb หัก margin จากพิกัดแล้ว จึงบวกกลับเพื่อวัดจากขอบกระดาษจริง
                x_mm = float(style['left'].removesuffix('mm')) + layout.margin_left
                y_mm = float(style['top'].removesuffix('mm')) + layout.margin_top
                size_pt = float(style['font-size'].removesuffix('pt'))
                bold = 'company-value' in field.get('class', '').split()
                font_key = (bold, size_pt)
                if font_key not in fonts:
                    font_path = FONT_DIR / ('Sarabun-Bold.ttf' if bold else 'Sarabun-Regular.ttf')
                    fonts[font_key] = ImageFont.truetype(
                        str(font_path), round(size_pt * IMAGE_DPI / 72),
                        layout_engine=ImageFont.Layout.RAQM if hasattr(ImageFont, 'Layout') else ImageFont.LAYOUT_RAQM,
                    )
                font = fonts[font_key]
                # shortcut: ข้อความเป็นภาพเพื่อจัดรูปอักษรไทย; เปลี่ยนเป็น vector เมื่อจำเป็นต้องเลือกข้อความ
                bounds = font.getbbox(value, anchor='lt', direction='ltr', language='th')
                image = Image.new('RGBA', (max(1, bounds[2] - bounds[0]), max(1, bounds[3] - bounds[1])))
                ImageDraw.Draw(image).text(
                    (-bounds[0], -bounds[1]), value, font=font, fill='#171717',
                    anchor='lt', direction='ltr', language='th',
                )
                width_pt = image.width * 72 / IMAGE_DPI
                height_pt = image.height * 72 / IMAGE_DPI
                pdf.drawImage(
                    ImageReader(image), x_mm * mm, page_height - y_mm * mm - height_pt,
                    width=width_pt, height=height_pt, mask='auto',
                )
            pdf.showPage()
        pdf.save()
        return output.getvalue(), 'pdf'
