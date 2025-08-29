#!/bin/bash

# Script to convert SVG icon to PNG for Odoo module
# Requires ImageMagick or Inkscape

# Using ImageMagick (if available)
if command -v convert &> /dev/null; then
    echo "Converting SVG to PNG using ImageMagick..."
    convert -background transparent -size 128x128 icon_template.svg icon.png
    echo "Icon created: icon.png"
elif command -v inkscape &> /dev/null; then
    echo "Converting SVG to PNG using Inkscape..."
    inkscape --export-type=png --export-filename=icon.png --export-width=128 --export-height=128 icon_template.svg
    echo "Icon created: icon.png"
else
    echo "Neither ImageMagick nor Inkscape found."
    echo "Please install one of these tools to convert SVG to PNG:"
    echo "  sudo apt-get install imagemagick"
    echo "  # or"
    echo "  sudo apt-get install inkscape"
    echo ""
    echo "Alternatively, you can:"
    echo "1. Open icon_template.svg in any graphics editor"
    echo "2. Export/Save as PNG with 128x128 dimensions"
    echo "3. Name it 'icon.png'"
fi
