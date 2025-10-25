#!/usr/bin/env python3
"""
Quick scanner to find XML files with potential Odoo <odoo>/<data> structure problems.

Checks performed:
- presence of BOM before XML declaration
- multiple '<?xml' occurrences
- multiple '<odoo' occurrences
- content outside the first '<odoo'..'</odoo>' block (e.g. stray <data> after closing tag)

Run this from the Odoo addons root. It prints a list of suspicious files and simple hints.
"""
import os
import sys

ROOT = "/opt/instance1/odoo17/custom-addons"

def scan_file(path):
    with open(path, 'rb') as f:
        data = f.read()

    issues = []

    # BOM check
    if data.startswith(b"\xef\xbb\xbf"):
        issues.append('BOM at start')

    # look for xml declarations
    decl_count = data.count(b'<?xml')
    if decl_count > 1:
        issues.append(f"{decl_count} XML declarations")

    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        issues.append('Non-UTF8 encoding or binary content')
        return issues

    # positions
    first_xml = text.find('<?xml')
    first_odoo = text.find('<odoo')
    last_odoo_close = text.rfind('</odoo>')

    # check for stray content before XML declaration
    stripped = text.lstrip()
    if not text.startswith('<?xml') and not text.startswith('\ufeff<?xml') and not text.startswith('\n<?xml'):
        # allow whitespace/newlines before xml, flag only if non-whitespace
        prefix = text[:first_xml if first_xml!=-1 else 0]
        if prefix.strip():
            issues.append('Non-whitespace text before <?xml')

    # check order: xml -> odoo -> ... -> /odoo
    if first_odoo == -1:
        issues.append('Missing <odoo> root')
    else:
        if first_xml != -1 and first_xml > first_odoo:
            issues.append('<?xml appears after <odoo>')

    if last_odoo_close == -1:
        issues.append('Missing </odoo> closing tag')
    else:
        # any non-whitespace after closing tag?
        after = text[last_odoo_close+len('</odoo>'):]
        if after.strip():
            issues.append('Non-whitespace content after </odoo>')

    # multiple <odoo occurrences
    odoo_count = text.count('<odoo')
    if odoo_count > 1:
        issues.append(f'{odoo_count} <odoo> tags')

    # <data> outside <odoo> block: naive check using positions
    data_pos = text.find('<data')
    if data_pos != -1:
        if first_odoo != -1 and last_odoo_close != -1:
            if not (first_odoo < data_pos < last_odoo_close):
                issues.append('<data> appears outside <odoo>..</odoo>')

    return issues


def main():
    problems = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        for fn in filenames:
            if not fn.endswith('.xml'):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, ROOT)
            issues = scan_file(path)
            if issues:
                problems[rel] = issues

    if not problems:
        print('No obvious structural issues found in XML files under custom-addons.')
        return 0

    print('Potential XML issues found:')
    for path, issues in sorted(problems.items()):
        print(f'- {path}:')
        for it in issues:
            print(f'    - {it}')

    return 1


if __name__ == '__main__':
    sys.exit(main())
