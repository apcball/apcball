import base64
import io

from PIL import Image

from odoo.tests.common import TransactionCase

from ..models.sale_order import (
    SIGNATURE_MAX_HEIGHT,
    SIGNATURE_MAX_SOURCE_BYTES,
    SIGNATURE_MAX_WIDTH,
    prepare_signature_image,
)


def _make_image(image_format='PNG', size=(800, 400), mode='RGBA'):
    color = (30, 60, 90, 100) if mode == 'RGBA' else (30, 60, 90)
    image = Image.new(mode, size, color)
    output = io.BytesIO()
    image.save(output, format=image_format)
    return base64.b64encode(output.getvalue())


class TestProformaSignature(TransactionCase):
    def test_large_signature_is_resized_to_png(self):
        result = prepare_signature_image(_make_image(size=(4000, 2000)))

        with Image.open(io.BytesIO(base64.b64decode(result))) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertLessEqual(image.width, SIGNATURE_MAX_WIDTH)
            self.assertLessEqual(image.height, SIGNATURE_MAX_HEIGHT)

    def test_transparent_png_keeps_alpha_channel(self):
        result = prepare_signature_image(_make_image())

        with Image.open(io.BytesIO(base64.b64decode(result))) as image:
            self.assertEqual(image.mode, 'RGBA')

    def test_jpeg_is_normalized_to_png(self):
        result = prepare_signature_image(
            _make_image(image_format='JPEG', mode='RGB')
        )

        with Image.open(io.BytesIO(base64.b64decode(result))) as image:
            self.assertEqual(image.format, 'PNG')
            self.assertEqual(image.mode, 'RGBA')

    def test_invalid_signature_is_ignored(self):
        self.assertFalse(prepare_signature_image(b'not-valid-base64'))
        self.assertFalse(prepare_signature_image(base64.b64encode(b'not-an-image')))

    def test_oversized_source_is_ignored(self):
        source = base64.b64encode(b'x' * (SIGNATURE_MAX_SOURCE_BYTES + 1))
        self.assertFalse(prepare_signature_image(source))
