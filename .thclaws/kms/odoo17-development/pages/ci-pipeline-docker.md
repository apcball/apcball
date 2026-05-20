---
- "https: //www.metamorphosis.com.bd/blog/technology-7/testing-framework-for-odoo-69
category: reference
created: 2026-05-16
sources: 
tags: "[\"ci\", \"pipeline\", \"docker\", \"github-actions\", \"gitlab-ci\", \"testing\", \"automation\"]"
title: Odoo 17 CI Pipeline on Docker
topic: รูปแบบ CI Pipeline สำหรับ automated testing Odoo 17 modules บน Docker
updated: 2026-05-16
---

# Odoo 17 CI Pipeline on Docker
Description: รูปแบบ CI Pipeline สำหรับ automated testing Odoo 17 modules บน Docker
---

## ภาพรวม

3 รูปแบบหลักสำหรับ CI Pipeline: GitHub Actions, GitLab CI, Docker Compose (local)

---

## 1. GitHub Actions

```yaml
# .github/workflows/test.yml
name: Odoo Module Test

on:
  push:
    branches: [Docker_Ball]
  pull_request:
    branches: [Docker_Ball]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: MOG_TEST
          POSTGRES_USER: odoo
          POSTGRES_PASSWORD: odoo
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Run Odoo Tests
        run: |
          docker run --network=host \
            -v ${{ github.workspace }}:/mnt/extra-addons \
            odoo:17.0 \
            -d MOG_TEST \
            --db_host=localhost \
            --db_user=odoo \
            --db_password=odoo \
            --addons-path=/mnt/extra-addons \
            -u buz_commercial_invoice \
            --test-enable \
            --stop-after-init \
            --no-http
```

---

## 2. GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - lint
  - test
  - deploy

variables:
  ODOO_VERSION: "17.0"
  DB_NAME: "MOG_TEST"

lint:
  stage: lint
  image: python:3.10
  script:
    - pip install pylint pylint-odoo
    - find . -name "*.py" -path "*/buz_*" | xargs pylint --load-plugins=pylint_odoo
  allow_failure: true

test:
  stage: test
  services:
    - postgres:15
  variables:
    POSTGRES_DB: $DB_NAME
    POSTGRES_USER: odoo
    POSTGRES_PASSWORD: odoo
  script:
    - |
      docker run --network=host \
        -v $(pwd):/mnt/extra-addons \
        odoo:17.0 \
        -d $DB_NAME \
        --db_host=postgres \
        --db_user=odoo \
        --db_password=odoo \
        --addons-path=/mnt/extra-addons \
        -u buz_commercial_invoice \
        --test-enable \
        --stop-after-init \
        --no-http

deploy_staging:
  stage: deploy
  script:
    - ssh user@staging-server "docker exec -it odoo odoo -d MOG_DEV -u buz_commercial_invoice --stop-after-init --no-http"
  only:
    - Docker_Ball
  when: manual
```

GitLab CI มี 5 stages ที่ควรมี:
1. `lint` — ตรวจ Python/XML
2. `test` — รัน Odoo unittest
3. `review` — deploy review app (optional)
4. `staging` — deploy staging (manual)
5. `production` — deploy production (manual)

---

## 3. Docker Compose (รัน local)

```yaml
# docker-compose.test.yml
version: '3.8'
services:
  postgres-test:
    image: postgres:15
    environment:
      POSTGRES_DB: MOG_TEST
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
    ports:
      - "5433:5432"

  odoo-test:
    image: odoo:17.0
    depends_on:
      - postgres-test
    volumes:
      - ./:/mnt/extra-addons
    command: >
      odoo -d MOG_TEST
      --db_host=postgres-test
      --db_user=odoo
      --db_password=odoo
      --addons-path=/mnt/extra-addons
      -u buz_commercial_invoice
      --test-enable
      --stop-after-init
      --no-http
```

```bash
# รัน test
docker compose -f docker-compose.test.yml up --abort-on-container-exit

# ดูผล
docker compose -f docker-compose.test.yml logs odoo-test
```

---

## 4. Full Flow Pipeline (แนะนำ project ใหญ่)

Auto-detect changed modules + lint + xml validation + test:

```yaml
# .github/workflows/ci.yml
name: Odoo CI

on:
  push:
    paths:
      - 'buz_*/**'
      - 'accounting_*/**'
      - 'l10n_th_*/**'

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      modules: ${{ steps.detect.outputs.modules }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: detect
        run: |
          CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -oP '^[a-z_]+(?=/)' | sort -u | tr '\n' ' ')
          echo "modules=$CHANGED" >> $GITHUB_OUTPUT

  lint:
    needs: detect-changes
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          pip install pylint pylint-odoo
          for mod in ${{ needs.detect-changes.outputs.modules }}; do
            echo "Linting $mod..."
            pylint --load-plugins=pylint_odoo $mod/ || true
          done

  xml-validation:
    needs: detect-changes
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          apt-get update && apt-get install -y libxml2-utils
          find . -name "*.xml" -path "*/buz_*" | xargs xmllint --noout

  unit-test:
    needs: [lint, xml-validation]
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: MOG_TEST
          POSTGRES_USER: odoo
          POSTGRES_PASSWORD: odoo
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - name: Run Tests for Changed Modules
        run: |
          for mod in ${{ needs.detect-changes.outputs.modules }}; do
            echo "Testing $mod..."
            docker run --network=host \
              -v $(pwd):/mnt/extra-addons \
              odoo:17.0 \
              -d MOG_TEST \
              --db_host=localhost \
              --db_user=odoo \
              --db_password=odoo \
              --addons-path=/mnt/extra-addons \
              -u $mod \
              --test-enable \
              --stop-after-init \
              --no-http
          done
```

---

## เปรียบเทียบ

| Feature | GitHub Actions | GitLab CI | Local Docker Compose |
|---|---|---|---|
| ต้นทุน | ฟรี (public repo) | ฟรี (self-hosted runner) | ฟรี |
| Setup ยาก | กลาง | กลาง | ต่ำ |
| รันอัตโนมัติ | ✅ ทุก push | ✅ ทุก push | ❌ รันเอง |
| Detect changed modules | ✅ | ✅ | ❌ |
| Parallel jobs | ✅ | ✅ | ❌ |
| เหมาะกับ | Team ใช้ GitHub | Team ใช้ GitLab | Dev คนเดียว / ทดสอบเร็ว |

---

## คำสั่งหลักสำหรับรัน test ผ่าน Docker

```bash
# รัน test module เดียว
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --test-enable --stop-after-init --no-http

# รันเฉพาะ test tag
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --test-enable --test-tags /<module_name> --stop-after-init --no-http

# รัน test ทั้งหมดใน file
docker exec -it odoo odoo -d MOG_DEV -u <module_name> --test-enable --test-tags /<module_name>.tests.test_file --stop-after-init --no-http
```
