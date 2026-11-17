from pathlib import Path
from xml.etree import ElementTree

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    defaults_file = Path(__file__).resolve().parents[2] / 'data' / 'share_certificate_layout_defaults.xml'
    for record in ElementTree.parse(defaults_file).iter('record'):
        position = env.ref('buz_share_certificate.%s' % record.attrib['id'], raise_if_not_found=False)
        if position:
            values = {field.attrib['name']: float(field.text) for field in record.findall('field')}
            position.write(values)
