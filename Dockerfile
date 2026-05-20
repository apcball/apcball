# Custom Odoo 17 Image for Ball
# Based on official Odoo 17 with Thai localization

FROM odoo:17.0

USER root

# Install system dependencies + Thai fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev \
    libxslt1-dev \
    libldap2-dev \
    libsasl2-dev \
    libffi-dev \
    git \
    curl \
    wget \
    fonts-thai-tlwg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir \
    pythainlp \
    python-dateutil \
    PyPDF2 \
    xlrd \
    openpyxl \
    paramiko \
    psycopg2-binary

# Copy config
COPY ./odoo.conf /etc/odoo/odoo.conf

# Create addons directories
RUN mkdir -p /mnt/extra-addons /mnt/enterprise-addons && \
    chown -R odoo:odoo /mnt/extra-addons /mnt/enterprise-addons

USER odoo

EXPOSE 8069 8071 8072

CMD ["odoo"]
