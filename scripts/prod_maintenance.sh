#!/usr/bin/env bash
# mog-prod maintenance: security updates + kernel reboot.
# Run ON the server, interactively (sudo needs a password/tty):
#   scp scripts/prod_maintenance.sh mog-prod:/tmp/ && ssh -t mog-prod 'bash /tmp/prod_maintenance.sh <step>'
# Steps (run in order, each is separate on purpose):
#   preflight  read-only checks + baseline
#   backup     pg_dump MOG_LIVE (native cluster)
#   upgrade    stop odoo, apt upgrade   (no autoremove)
#   reboot     asks confirmation, then reboots
#   verify     post-reboot checks
#   cleanup    autoremove old kernel (ONLY after verify OK)
# Nothing runs unless you type the step. See scripts/prod_maintenance_plan_2026-11.md.
set -euo pipefail

DB=MOG_LIVE
BACKUP_DIR=/var/backups
STAMP=$(date +%F)
BASE=/var/tmp/maint_$STAMP
DOCKER_ODOO=odoo        # container with restart=always (comes back after reboot)
# postgres container is restart=unless-stopped: do NOT docker stop it manually.

confirm() { read -r -p "$1 [type YES]: " a; [ "$a" = "YES" ] || { echo "aborted"; exit 1; }; }
step() { echo; echo "=== $* ==="; }

preflight() {
  step "preflight"
  mkdir -p "$BASE"
  uname -r
  df -h / /boot
  [ "$(df --output=avail -BG / | tail -1 | tr -dc 0-9)" -ge 40 ] || { echo "FAIL: <40G free on /"; exit 1; }
  systemctl is-enabled instance1 postgresql docker containerd
  docker ps --format '{{.Names}} {{.Status}}'
  docker ps -q | xargs -r docker inspect -f '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}}'
  apt-mark showhold | sed 's/^/HOLD: /'
  systemctl list-units --state=running --no-pager > "$BASE/pre_units.txt"
  docker ps > "$BASE/pre_docker.txt"
  ss -tlnp > "$BASE/pre_ports.txt" 2>/dev/null || ss -tln > "$BASE/pre_ports.txt"
  echo "baseline saved in $BASE"
  echo "REMINDER: VM snapshot + provider console access ready? (GRUB menu is hidden)"
}

backup() {
  step "backup $DB"
  local f="$BACKUP_DIR/${DB}_pre_maint_$STAMP.dump"
  [ ! -e "$f" ] || { echo "exists: $f (refusing to overwrite)"; exit 1; }
  sudo -u postgres pg_dump -Fc "$DB" -f "$f"
  sudo chmod 600 "$f"
  ls -lh "$f"
  sudo -u postgres pg_restore -l "$f" | head -3   # sanity: archive readable
  echo "Copy off-box now:  scp mog-prod:$f ~/backups/"
}

upgrade() {
  step "upgrade"
  confirm "Stop instance1 + odoo container and run apt upgrade?"
  sudo apt update
  echo "upgradable: $(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)"
  sudo systemctl stop instance1
  docker stop "$DOCKER_ODOO"
  sudo apt -y upgrade        # keeps existing conffiles by default prompt; answer N/keep local
  echo "NOTE: no autoremove (kernel 6.8.0-101 kept as fallback)"
  ls /var/run/reboot-required && cat /var/run/reboot-required.pkgs || true
  ls -l /boot | grep -E 'vmlinuz|initrd.img '
  echo "Check vmlinuz/initrd point to newest kernel, then: bash $0 reboot"
}

do_reboot() {
  step "reboot"
  ls -l /boot/vmlinuz /boot/initrd.img
  confirm "Reboot NOW? (backup copied off-box, snapshot/console ready)"
  sudo systemctl reboot
}

verify() {
  step "verify"
  echo "kernel: $(uname -r)"
  [ ! -e /var/run/reboot-required ] && echo "reboot-required: none" || echo "WARN reboot-required still set"
  systemctl is-active instance1 postgresql docker
  docker ps --format '{{.Names}} {{.Status}}'
  for p in 8069 8070; do
    printf "port %s -> HTTP " "$p"; curl -s -o /dev/null -w '%{http_code}\n' --max-time 20 "http://127.0.0.1:$p/web/login" || echo fail
  done
  echo "--- diff vs baseline (units)"
  systemctl list-units --state=running --no-pager | diff "$BASE/pre_units.txt" - || true
  echo "--- diff vs baseline (docker)"
  docker ps | awk '{print $1,$2,$NF}' | diff <(awk '{print $1,$2,$NF}' "$BASE/pre_docker.txt") - || true
  echo "--- instance1 errors since boot"
  sudo journalctl -u instance1 -b --no-pager -p err | tail -15
  echo "--- still upgradable: $(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l)"
  echo "If a container is missing (postgres unless-stopped): cd /srv/docker/odoo_mogen && sudo docker compose up -d"
  echo "Then test in browser: login both, open SO + picking + one report."
}

cleanup() {
  step "cleanup (only after verify OK)"
  confirm "Verify passed and kernel 101 fallback no longer needed?"
  sudo apt -y autoremove --purge
  docker builder prune -f || true
  df -h / /boot
}

case "${1:-}" in
  preflight) preflight ;;
  backup)    backup ;;
  upgrade)   upgrade ;;
  reboot)    do_reboot ;;
  verify)    verify ;;
  cleanup)   cleanup ;;
  *) sed -n '2,14p' "$0"; exit 2 ;;
esac
