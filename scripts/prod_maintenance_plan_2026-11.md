# mog-prod maintenance plan — kernel/security update (draft 2026-11-25)

Status at check: running kernel 6.8.0-101, installed up to 6.8.0-151, uptime 37w, reboot-required (kernel+libc6), 120 pkgs upgradable, docker-ce/containerd.io (Docker repo) not auto-updated.
Services: systemd `instance1` (MOG_LIVE :8069), docker odoo (:8070, /srv/docker/odoo_mogen), PostgreSQL native + postgres:16 container.

## Pre-checks DONE 2026-11-25 (read-only)
- Autostart OK: instance1/postgresql/docker/containerd enabled+active; containers odoo=always, postgres=unless-stopped (manual `docker stop postgres` before reboot = it will NOT come back; leave it running, docker stops it cleanly at shutdown).
- Disk OK: / 490G used 45% (262G free), /boot 2.0G used 11%.
- /boot OK: vmlinuz/initrd 6.8.0-151 present, symlinks correct, dpkg has only images 101 + 151, linux-generic = 151, GRUB_DEFAULT=0 -> boots 151.
- Not checked (needs sudo): sshd config, ufw, grub.cfg.

## Script: scripts/prod_maintenance.sh (automates sections 0-6 below)
```bash
scp scripts/prod_maintenance.sh mog-prod:/tmp/
ssh -t mog-prod 'bash /tmp/prod_maintenance.sh <step>'
```
Run steps one at a time, in order: `preflight` -> `backup` -> (copy dump off-box) -> `upgrade` -> `reboot` -> `verify` -> `cleanup` (only after verify OK).
- `preflight`: disk (<40G free fails), autostart, restart policies, holds, baseline in /var/tmp/maint_<date>/
- `backup`: pg_dump -Fc MOG_LIVE as postgres to /var/backups (never overwrites). Not tested vs prod; adjust if MOG_LIVE needs odoo user/password from /etc/instance1.conf.
- `upgrade`: YES prompt, stops instance1 + container odoo only, apt upgrade, NO autoremove.
- `reboot`: shows /boot symlinks, YES prompt.
- `verify`: kernel, reboot-required, services, HTTP 8069/8070, diff vs baseline, journal errors.
- `cleanup`: YES prompt, autoremove + docker builder prune.
Script is untested on prod (syntax-checked only). Manual commands below are the same steps.

## 0. Prep (before window, no downtime)
1. Pick window outside business hours (e.g. Sat night). Announce to users ~1 day ahead. Expected downtime 5-15 min.
2. Confirm VM snapshot / provider backup possible (best rollback). If none, rely on dump + note old kernel stays in GRUB (6.8.0-101..151 all installed).
3. Check autostart (a reboot with no autostart = outage):
   ```bash
   ssh mog-prod 'systemctl is-enabled instance1 postgresql docker containerd; docker ps --format "{{.Names}} {{.Status}}"; docker inspect -f "{{.Name}} {{.HostConfig.RestartPolicy.Name}}" $(docker ps -q)'
   ```
   Every container needs restart policy `always`/`unless-stopped`. Fix before window if not.
4. Disk space for dump + apt: `ssh mog-prod 'df -h / /var /opt /srv'`
5. Save baseline for later compare:
   ```bash
   ssh mog-prod 'systemctl list-units --state=running --no-pager > /tmp/pre_units.txt; docker ps > /tmp/pre_docker.txt; ss -tlnp > /tmp/pre_ports.txt; uname -r'
   ```
6. Needs interactive sudo (password) -> run steps below via `ssh -t mog-prod` yourself, or use `! ssh -t mog-prod ...` in Claude Code.

## 1. Backup (standing policy: dump MOG_LIVE before prod change)
```bash
ssh -t mog-prod 'sudo -u postgres pg_dump -Fc MOG_LIVE -f /var/backups/MOG_LIVE_pre_maint_$(date +%F).dump && ls -lh /var/backups/MOG_LIVE_pre_maint_*.dump'
```
(If dump needs table scoping / max_locks issue as with docker stack, use native cluster — it is the separate prod-native one.) Copy dump off-box (scp to Mac or backup server). Also backup `/etc/instance1.conf`, `/opt/instance1` custom addons dir state is in git.

## 2. Upgrade packages (window start)
```bash
ssh -t mog-prod
sudo apt update
sudo apt list --upgradable 2>/dev/null | wc -l          # expect ~120
sudo apt-mark showhold                                   # note held pkgs
# stop app first so DB/containers quiesce cleanly
sudo systemctl stop instance1
docker stop odoo        # only odoo (restart=always). Do NOT stop postgres container (unless-stopped: won't return after reboot if stopped manually)
sudo apt -y upgrade                                      # keep conffiles: answer N / keep local if prompted
# NO autoremove here: keep kernel 6.8.0-101 as fallback until verify (step 4) passes.
```
Notes:
- docker-ce 29.5.3->29.10.0 and containerd.io 2.2.4->2.4.2 come in via `apt upgrade`; daemon restarts -> containers restart per policy.
- Do NOT `dist-upgrade` to a new release. Do not touch odoo venv / pip.
- If sshd/openssh config prompt appears: keep installed config.

## 3. Reboot
```bash
sudo reboot
```
Wait ~2-3 min, then reconnect.

## 4. Verify
```bash
ssh mog-prod 'uname -r; ls /var/run/reboot-required 2>&1; systemctl is-active instance1 postgresql docker; docker ps; ss -tlnp | grep -E "8069|8070|5432"'
ssh mog-prod 'sudo -n true 2>/dev/null; journalctl -u instance1 -b --no-pager | tail -30'
```
- Expect kernel 6.8.0-1xx (newest), no reboot-required.
- Compare with /tmp/pre_*.txt.
- Browser: login MOG_LIVE :8069 + :8070, open a sales order, a stock picking, run one report.
- Check cron (WorkerCron crash-loop known issue — compare against baseline, not "zero errors"). Known chronic /websocket 400 is pre-existing.
- Re-run: `apt list --upgradable | wc -l` (expect ~0-few) and `needrestart -r l` if installed.

## 5. Rollback
- App won't start: `journalctl -u instance1 -b`; check postgres first.
- Bad kernel: GRUB menu is hidden (`GRUB_TIMEOUT=0`, `TIMEOUT_STYLE=hidden`) -> need provider console/VNC, hold Shift (BIOS) / Esc (EFI) at boot, pick "Advanced options" -> 6.8.0-101. Kernel 101 stays installed (no autoremove before verify). Have console access + VM snapshot ready BEFORE reboot.
- Data problem: restore from dump / VM snapshot.

## 6. Follow-ups (after window)
- Only after verify OK: `sudo apt autoremove --purge` (removes old kernel 101) and clean stale `/lib/modules/6.8.0-*` dirs with no matching package.
- Optional: `docker builder prune` (~950M build cache).
- Harden: check `sudo sshd -T | grep -Ei "permitrootlogin|passwordauthentication"`, `sudo ufw status` (not checked yet, needed sudo).
- Enable `Unattended-Upgrade::Automatic-Reboot "true"` + `Automatic-Reboot-Time "03:00"`? Only if autostart verified and you accept auto downtime; else schedule monthly reboot.
- Add Docker repo to unattended origins or monthly manual `apt upgrade docker-ce`.
- Consider `pro attach` (free <=5 machines) + Livepatch to reduce reboots.
- Update memory note: prod deploy restart needs sudo/tty (deploy.sh).
