#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
REQUIRED_COMMIT=__REQUIRED_COMMIT__
CACHE=/var/cache/live-infinita-godot
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
WEB=/var/www/live-infinita-godot/index.html
TEMPLATES=/root/.local/share/godot/export_templates/4.7.2.stable
BACKUP="/var/backups/live-infinita/ubuntu-safe-clean-$(date +%Y%m%d-%H%M%S)"

fail(){ echo "UBUNTU_CLEAN_FAIL: $*" >&2; exit 2; }
[[ "${EUID}" -ne 0 ]] || fail "Execute como etbra, sem sudo antes do comando."
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail "Checkout deve estar na main"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Checkout possui alteracoes rastreadas"
git merge-base --is-ancestor "$REQUIRED_COMMIT" HEAD || fail "Script nao integrado ao checkout main"

systemctl is-active --quiet live-infinita-autonomous-world.service || fail "Mundo autoritativo inativo"
systemctl is-active --quiet live-infinita.service || fail "API inativa"
curl -fsS --max-time 12 http://127.0.0.1:8080/api/health | python3 -c '
import json,sys
d=json.load(sys.stdin)
s=(d.get("cognitive_gym_v2") or {}).get("shadow_observer") or {}
assert d.get("ok") is True and s.get("metrics_scope")=="recent_window"
assert s.get("direct_world_write") is False and s.get("selection_authority") is False
' || fail "Preflight HTTP/shadow reprovado"
[[ -f /var/lib/live-infinita/autonomous-world/simulation-clock.json ]] || fail "Dados autoritativos ausentes"
[[ -n "$(swapon --noheadings --show=NAME)" ]] || fail "Swap de protecao nao ativo"
sudo -v

echo "== Antes: disco, memoria, jornal, caches =="
df -h / /tmp
free -h
sudo journalctl --disk-usage
sudo du -sh /var/cache/apt/archives "$CACHE" /var/log/journal 2>/dev/null || true

echo "== Salvando evidencias do OOM e da unidade antes de limitar logs =="
sudo install -d -m 0700 "$BACKUP"
sudo journalctl -k --since "2026-09-28 00:00:00" --no-pager -o short-iso \
  | grep -Ei "oom|out of memory|killed process" \
  | sudo tee "$BACKUP/kernel-oom-20260928.log" >/dev/null || true
sudo journalctl -u live-infinita-autonomous-world.service --since "2026-09-28 00:00:00" \
  --no-pager -o short-iso -n 500 \
  | sudo tee "$BACKUP/single-writer-20260928.log" >/dev/null
echo "LOG_BACKUP=$BACKUP"

echo "== Limitando logs persistentes sem desabilitar journald =="
sudo install -d -m 0755 /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=persistent\nSystemMaxUse=200M\nSystemKeepFree=1G\nMaxRetentionSec=14day\n' \
  | sudo tee /etc/systemd/journald.conf.d/90-live-infinita-retention.conf >/dev/null
sudo systemctl restart systemd-journald.service
sudo journalctl --rotate
sudo journalctl --vacuum-size=200M
sudo journalctl --disk-usage

echo "== Removendo APENAS arquivos de download do APT =="
sudo apt-get clean

echo "== Removendo arquivos de instalacao Godot apenas apos conferir o executavel instalado =="
if [[ -x "$ENGINE" && -s "$WEB" && -f "$CACHE/Godot_v4.7.2-stable_linux.x86_64.zip" ]]; then
  sudo rm -- "$CACHE/Godot_v4.7.2-stable_linux.x86_64.zip"
  echo GODOT_ENGINE_ARCHIVE_REMOVED
else
  echo GODOT_ENGINE_ARCHIVE_PRESERVED
fi
if [[ -x "$ENGINE" && -s "$WEB" ]] \
   && sudo test -d "$TEMPLATES" \
   && [[ -n "$(sudo find "$TEMPLATES" -maxdepth 1 -type f -print -quit)" ]] \
   && [[ -f "$CACHE/Godot_v4.7.2-stable_export_templates.tpz" ]]; then
  sudo rm -- "$CACHE/Godot_v4.7.2-stable_export_templates.tpz"
  echo GODOT_TEMPLATE_ARCHIVE_REMOVED
else
  echo GODOT_TEMPLATE_ARCHIVE_PRESERVED_CHECK_TEMPLATES
fi

echo "== Validando integridade dos servicos e dados protegidos =="
[[ -x "$ENGINE" && -s "$WEB" ]] || fail "Godot instalado ou Web ausente"
systemctl is-active --quiet live-infinita-autonomous-world.service || fail "Single Writer inativo"
systemctl is-active --quiet live-infinita.service || fail "API inativa"
curl -fsS --max-time 12 http://127.0.0.1:8080/api/health | python3 -c '
import json,sys
d=json.load(sys.stdin)
s=(d.get("cognitive_gym_v2") or {}).get("shadow_observer") or {}
assert d.get("ok") is True and s.get("metrics_scope")=="recent_window"
assert s.get("direct_world_write") is False and s.get("selection_authority") is False
print("HTTP_HEALTH_OK")
' || fail "Health falhou apos limpeza"
python3 "$REPO/deploy/verify-mvp014b-social.py" /var/lib/live-infinita/autonomous-world

echo "== Depois: disco, memoria, jornal, caches =="
df -h / /tmp
free -h
sudo journalctl --disk-usage
sudo du -sh /var/cache/apt/archives "$CACHE" /var/log/journal 2>/dev/null || true
systemctl show live-infinita-autonomous-world.service -p ActiveState -p MainPID -p NRestarts
echo UBUNTU_SAFE_CLEAN_VALIDADO
