import base64
import binascii
import io
import logging

from PIL import Image, ImageOps

from odoo import models


_logger = logging.getLogger(__name__)

SIGNATURE_MAX_WIDTH = 200
SIGNATURE_MAX_HEIGHT = 100
SIGNATURE_MAX_SOURCE_BYTES = 5 * 1024 * 1024
SIGNATURE_MAX_ENCODED_BYTES = ((SIGNATURE_MAX_SOURCE_BYTES + 2) // 3) * 4
SIGNATURE_MAX_SOURCE_PIXELS = 20_000_000
SIGNATURE_RESAMPLE = getattr(Image, 'Resampling', Image).LANCZOS


def prepare_signature_image(signature):
    '''Return a normalized signature for wkhtmltopdf, or False if unsafe.'''
    if not signature:
        return False
    try:
        encoded = signature.encode('ascii') if isinstance(signature, str) else signature
        if len(encoded) > SIGNATURE_MAX_ENCODED_BYTES:
            return False
        image_data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return False
    if not image_data or len(image_data) > SIGNATURE_MAX_SOURCE_BYTES:
        return False

    try:
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size
        if not width or not height or width * height > SIGNATURE_MAX_SOURCE_PIXELS:
            image.close()
            return False
    except (Image.DecompressionBombError, OSError, ValueError):
        return False

    try:
        with image:
            prepared = ImageOps.exif_transpose(image)
            prepared.thumbnail(
                (SIGNATURE_MAX_WIDTH, SIGNATURE_MAX_HEIGHT),
                SIGNATURE_RESAMPLE,
            )
            prepared = prepared.convert('RGBA')
            output = io.BytesIO()
            prepared.save(output, format='PNG', optimize=True)
        return base64.b64encode(output.getvalue())
    except (OSError, ValueError):
        return False

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_proforma_signature(self):
        self.ensure_one()
        signature = prepare_signature_image(self.approval_signature)
        if self.approval_signature and not signature:
            _logger.warning(
                'Skipping invalid or oversized Proforma Invoice signature '
                'for sale order %s',
                self.id,
            )
        return signature

    def action_print_proforma_invoice(self):
        self.ensure_one()
        report = self.env.ref(
            'buz_proforma_invoice.action_report_proforma_invoice'
        )
        return report.report_action(self)
