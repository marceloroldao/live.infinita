#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${BRANCH:-hardening/live-showcase-002}"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/live.infinita}"
SERVICE_USER="${SERVICE_USER:-liveinfinita}"
DATA_DIR="${DATA_DIR:-/var/lib/live-infinita}"
READY_TIMEOUT="${READY_TIMEOUT:-25}"

ok(){ printf '[ OK ] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; }
info(){ printf '[....] %s\n' "$*"; }

printf '\n== Live.infinita deploy ==\n'
printf 'Source : %s\n' "$SOURCE_DIR"
printf 'Install: %s\n' "$INSTALL_DIR"
printf 'Branch : %s\n' "$BRANCH"
printf 'Data   : %s\n\n' "$(date -Is 2>/dev/null || date)"

cd "$SOURCE_DIR"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  fail 'Existem alterações rastreadas locais. Abortando para não sobrescrever nada.'
  git status --short
  exit 2
fi

git fetch --prune origin
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git switch "$BRANCH"
else
  git switch -c "$BRANCH" --track "origin/$BRANCH"
fi
git pull --ff-only origin "$BRANCH"
SOURCE_SHA="$(git rev-parse --short HEAD)"
ok "Código-fonte atualizado em $SOURCE_SHA"

if ! command -v rsync >/dev/null 2>&1; then
  info 'rsync não encontrado; instalando.'
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y rsync
fi

sudo mkdir -p "$INSTALL_DIR" "$DATA_DIR"
info "Sincronizando checkout -> $INSTALL_DIR"
sudo rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.godot/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.log' \
  "$SOURCE_DIR/" "$INSTALL_DIR/"
ok 'Código de produção sincronizado.'

if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  info "Criando virtualenv em $INSTALL_DIR/.venv"
  if ! sudo python3 -m venv "$INSTALL_DIR/.venv"; then
    warn 'python3-venv ausente; instalando pacote do sistema e tentando novamente.'
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv
    sudo python3 -m venv "$INSTALL_DIR/.venv"
  fi
fi

sudo "$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -U pip
mapfile -t REQUIREMENTS < <(find "$INSTALL_DIR/apps" "$INSTALL_DIR/tests" -name requirements.txt -type f 2>/dev/null | sort -u || true)
if ((${#REQUIREMENTS[@]})); then
  for req in "${REQUIREMENTS[@]}"; do
    info "pip install -r ${req#$INSTALL_DIR/}"
    sudo "$INSTALL_DIR/.venv/bin/python" -m pip install --disable-pip-version-check -r "$req"
  done
  ok 'Dependências Python instaladas no virtualenv de produção.'
else
  warn 'Nenhum requirements.txt encontrado.'
fi

if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" "$DATA_DIR"
else
  warn "Usuário de serviço '$SERVICE_USER' não existe; ownership não alterado."
fi

# Reexporta a cena Godot Web já instalada. O instalador completo continua sendo necessário
# apenas na primeira instalação da engine/templates.
VISUAL_EXPORT="skipped"
VISUAL_FAIL=0
if [[ -f "$INSTALL_DIR/deploy/export-godot-web.sh" ]]; then
  if find /opt/live-infinita-godot/engine -maxdepth 1 -type f -name 'Godot_v*_linux.x86_64' -perm -u+x -print -quit 2>/dev/null | grep -q .; then
    info 'Reexportando cenário Godot Web atual...'
    if sudo env \
      LIVE_INFINITA_SOURCE_SHA="$SOURCE_SHA" \
      INSTALL_DIR="$INSTALL_DIR" \
      bash "$INSTALL_DIR/deploy/export-godot-web.sh"; then
      VISUAL_EXPORT="ok"
      ok "Godot Web publicado a partir do commit $SOURCE_SHA"
    else
      VISUAL_EXPORT="failed"
      VISUAL_FAIL=1
      fail 'Falha ao reexportar o Godot Web.'
    fi
  else
    VISUAL_EXPORT="engine-missing"
    warn 'Engine Godot instalada não encontrada; mantendo export web existente.'
    warn "Primeira instalação: sudo bash $INSTALL_DIR/deploy/install-godot-web.sh"
  fi
else
  warn 'Script de export Godot Web ausente; mantendo export existente.'
fi

# Apenas units presentes no repositório são considerados gerenciados por este deploy.
MANAGED_SERVICES=()
UPDATED_UNITS=0
shopt -s nullglob
for unit_src in "$INSTALL_DIR"/deploy/live-infinita*.service "$INSTALL_DIR"/deploy/live-infinita*.path; do
  unit="$(basename "$unit_src")"
  if [[ -e "/etc/systemd/system/$unit" ]]; then
    sudo install -m 0644 "$unit_src" "/etc/systemd/system/$unit"
    UPDATED_UNITS=$((UPDATED_UNITS+1))
    [[ "$unit" == *.service ]] && MANAGED_SERVICES+=("$unit")
  fi
done
shopt -u nullglob
sudo systemctl daemon-reload
ok "$UPDATED_UNITS unit(s) systemd instalado(s) foram atualizados."

mapfile -t INSTALLED_SERVICES < <(
  systemctl list-unit-files --type=service --no-legend 2>/dev/null \
    | awk '{print $1}' \
    | grep -E '^live-infinita.*\.service$' \
    | sort -u || true
)

LEGACY_SERVICES=()
for svc in "${INSTALLED_SERVICES[@]}"; do
  managed=0
  for known in "${MANAGED_SERVICES[@]}"; do
    [[ "$svc" == "$known" ]] && managed=1 && break
  done
  ((managed == 0)) && LEGACY_SERVICES+=("$svc")
done

if ((${#LEGACY_SERVICES[@]})); then
  warn "Serviços legados/não versionados detectados: ${LEGACY_SERVICES[*]}"
fi

if ((${#MANAGED_SERVICES[@]})); then
  for svc in "${MANAGED_SERVICES[@]}"; do
    enabled="$(systemctl is-enabled "$svc" 2>/dev/null || true)"
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"

    if [[ "$enabled" == static ]]; then
      info "$svc = helper static; restart direto ignorado."
      continue
    fi

    if [[ "$state" == active || "$enabled" == enabled ]]; then
      info "reiniciando $svc"
      sudo systemctl restart "$svc" || true
    else
      info "$svc instalado, porém inativo/desabilitado; mantendo assim."
    fi
  done
else
  warn 'Nenhum serviço versionado Live.infinita está instalado.'
fi

wait_service_active(){
  local svc="$1" timeout="${2:-$READY_TIMEOUT}" i state
  for ((i=0; i<timeout; i++)); do
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"
    [[ "$state" == active ]] && return 0
    sleep 1
  done
  return 1
}

printf '\n== Status dos serviços gerenciados ==\n'
FAIL=0
ACTIVE=0
INACTIVE=0
for svc in "${MANAGED_SERVICES[@]}"; do
  enabled="$(systemctl is-enabled "$svc" 2>/dev/null || true)"

  if [[ "$enabled" == static ]]; then
    info "$svc = static/helper"
    INACTIVE=$((INACTIVE+1))
    continue
  fi

  if [[ "$enabled" == enabled ]]; then
    if wait_service_active "$svc"; then
      ok "$svc = active (enabled)"
      ACTIVE=$((ACTIVE+1))
    else
      state="$(systemctl is-active "$svc" 2>/dev/null || true)"
      fail "$svc = ${state:-unknown} (enabled)"
      FAIL=$((FAIL+1))
    fi
  else
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"
    if [[ "$state" == active ]]; then
      ok "$svc = active ($enabled)"
      ACTIVE=$((ACTIVE+1))
    else
      info "$svc = ${state:-unknown} ($enabled)"
      INACTIVE=$((INACTIVE+1))
    fi
  fi
done

check_http(){
  local label="$1" url="$2" required="${3:-0}" timeout="${4:-$READY_TIMEOUT}" code i
  for ((i=0; i<timeout; i++)); do
    code="$(curl -k -sS -m 4 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    [[ -n "$code" ]] || code=000
    if [[ "$code" =~ ^2[0-9][0-9]$|^3[0-9][0-9]$ ]]; then
      ok "$label -> $code $url"
      return 0
    fi
    sleep 1
  done

  if [[ "$required" == 1 ]]; then
    fail "$label -> $code $url"
    HTTP_FAIL=$((HTTP_FAIL+1))
  else
    warn "$label -> $code $url"
  fi
  return 0
}

printf '\n== Health checks com readiness ==\n'
HTTP_FAIL=0
check_http 'Runtime' 'http://127.0.0.1:8080/api/health' 1 25
check_http 'Replay' 'http://127.0.0.1:8080/api/replay/verify' 0 10
check_http 'Áudio web' 'http://127.0.0.1:8092/health' 0 20
check_http 'Nginx local' 'http://127.0.0.1/' 1 15
check_http 'Godot público' 'https://live.etbra.com.br/godot/' 1 10
if [[ "$VISUAL_EXPORT" == ok ]]; then
  check_http 'Godot build' 'https://live.etbra.com.br/godot/build.json' 1 10
fi

printf '\n== Portas em escuta ==\n'
ss -ltnp 2>/dev/null | grep -E ':(80|443|8080|8092|8765|3000|5600|5500)\b' || true

printf '\n== Resumo ==\n'
printf 'Source commit : %s\n' "$SOURCE_SHA"
printf 'Branch        : %s\n' "$(git branch --show-current)"
printf 'Produção      : %s\n' "$INSTALL_DIR"
printf 'Godot export  : %s\n' "$VISUAL_EXPORT"
printf 'Serviços OK   : %d\n' "$ACTIVE"
printf 'Inativos      : %d\n' "$INACTIVE"
printf 'Legados       : %d\n' "${#LEGACY_SERVICES[@]}"
printf 'Falhas svc    : %d\n' "$FAIL"
printf 'Falhas HTTP   : %d\n' "$HTTP_FAIL"

if ((VISUAL_FAIL || FAIL || HTTP_FAIL)); then
  printf '\nDEPLOY CONCLUÍDO COM FALHAS\n'
  printf 'Runtime: sudo journalctl -u live-infinita -n 80 --no-pager\n'
  printf 'Áudio:   sudo journalctl -u live-infinita-audio-web -n 80 --no-pager\n'
  exit 1
fi

printf '\nDEPLOY OK\n'
printf 'Visual: https://live.etbra.com.br/godot/\n'
printf 'Build:  https://live.etbra.com.br/godot/build.json\n'
printf 'Monitor/gerência: https://live.etbra.com.br/manage/\n'