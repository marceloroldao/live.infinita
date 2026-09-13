#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${BRANCH:-hardening/live-showcase-002}"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/live.infinita}"
SERVICE_USER="${SERVICE_USER:-liveinfinita}"
DATA_DIR="${DATA_DIR:-/var/lib/live-infinita}"

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

# Bloqueia apenas alterações rastreadas. Artefatos locais/untracked do servidor não impedem deploy.
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

# Produção roda em /opt/live.infinita, não diretamente no checkout do operador.
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

# Ambiente virtual obrigatório: evita PEP 668 e coincide com ExecStart dos units systemd.
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

# Garante ownership consistente com os serviços, sem tocar /etc.
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" "$DATA_DIR"
else
  warn "Usuário de serviço '$SERVICE_USER' não existe; ownership não alterado."
fi

# Atualiza apenas units que já estão instalados. Não habilita serviços novos automaticamente.
UPDATED_UNITS=0
shopt -s nullglob
for unit_src in "$INSTALL_DIR"/deploy/live-infinita*.service "$INSTALL_DIR"/deploy/live-infinita*.path; do
  unit="$(basename "$unit_src")"
  if [[ -e "/etc/systemd/system/$unit" ]]; then
    sudo install -m 0644 "$unit_src" "/etc/systemd/system/$unit"
    UPDATED_UNITS=$((UPDATED_UNITS+1))
  fi
done
shopt -u nullglob
sudo systemctl daemon-reload
ok "$UPDATED_UNITS unit(s) systemd instalado(s) foram atualizados."

mapfile -t SERVICES < <(
  systemctl list-unit-files --type=service --no-legend 2>/dev/null \
    | awk '{print $1}' \
    | grep -E '^live-infinita.*\.service$' \
    | sort -u || true
)

if ((${#SERVICES[@]})); then
  for svc in "${SERVICES[@]}"; do
    # Não liga serviço que está propositalmente desabilitado/inativo (ex.: broadcaster).
    if systemctl is-active --quiet "$svc" || systemctl is-enabled --quiet "$svc" 2>/dev/null; then
      info "reiniciando $svc"
      sudo systemctl restart "$svc" || true
    else
      info "$svc instalado, porém inativo/desabilitado; mantendo assim."
    fi
  done
else
  warn 'Nenhum serviço live-infinita*.service instalado.'
fi

printf '\n== Status dos serviços ==\n'
FAIL=0
ACTIVE=0
INACTIVE=0
if ((${#SERVICES[@]})); then
  for svc in "${SERVICES[@]}"; do
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"
    enabled="$(systemctl is-enabled "$svc" 2>/dev/null || true)"
    if [[ "$state" == active ]]; then
      ok "$svc = active ($enabled)"
      ACTIVE=$((ACTIVE+1))
    elif [[ "$enabled" == enabled ]]; then
      fail "$svc = ${state:-unknown} (enabled)"
      FAIL=$((FAIL+1))
    else
      info "$svc = ${state:-unknown} ($enabled)"
      INACTIVE=$((INACTIVE+1))
    fi
  done
fi

printf '\n== Portas em escuta ==\n'
ss -ltnp 2>/dev/null | grep -E ':(80|443|8080|8092|8765|3000|5600|5500)\b' || true

printf '\n== Health checks ==\n'
HTTP_FAIL=0
check_http(){
  local label="$1" url="$2" required="${3:-0}" code
  code="$(curl -k -sS -m 8 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  [[ -n "$code" ]] || code=000
  if [[ "$code" =~ ^2[0-9][0-9]$|^3[0-9][0-9]$ ]]; then
    ok "$label -> $code $url"
  elif [[ "$required" == 1 ]]; then
    fail "$label -> $code $url"
    HTTP_FAIL=$((HTTP_FAIL+1))
  else
    warn "$label -> $code $url"
  fi
}

check_http 'Runtime' 'http://127.0.0.1:8080/api/health' 1
check_http 'Replay' 'http://127.0.0.1:8080/api/replay/verify' 0
check_http 'Áudio' 'http://127.0.0.1:8092/health' 0
check_http 'Nginx local' 'http://127.0.0.1/' 1
check_http 'Godot público' 'https://live.etbra.com.br/godot/' 0

printf '\n== Resumo ==\n'
printf 'Source commit : %s\n' "$SOURCE_SHA"
printf 'Branch        : %s\n' "$(git branch --show-current)"
printf 'Produção      : %s\n' "$INSTALL_DIR"
printf 'Serviços OK   : %d\n' "$ACTIVE"
printf 'Inativos      : %d\n' "$INACTIVE"
printf 'Falhas svc    : %d\n' "$FAIL"
printf 'Falhas HTTP   : %d\n' "$HTTP_FAIL"

if ((FAIL || HTTP_FAIL)); then
  printf '\nDEPLOY CONCLUÍDO COM FALHAS\n'
  printf 'Diagnóstico: sudo journalctl -u live-infinita -n 80 --no-pager\n'
  exit 1
fi

printf '\nDEPLOY OK\n'
printf 'Visual: https://live.etbra.com.br/godot/\n'
printf 'Monitor/gerência: https://live.etbra.com.br/manage/\n'
