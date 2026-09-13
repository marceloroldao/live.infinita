#!/usr/bin/env bash
set -Eeuo pipefail

# Live.infinita - atualização segura do servidor
#
# Uso normal:
#   cd /opt/live.infinita
#   bash deploy/update.sh
#
# Opções por variável de ambiente:
#   BRANCH=main                    branch a atualizar
#   INSTALL_DEPS=1                instala/atualiza dependências Python (0 desativa)
#   RESTART_SERVICES=1            reinicia serviços detectados (0 desativa)
#   RUN_HEALTHCHECKS=1            executa checks HTTP no final (0 desativa)
#   HEALTH_URLS="url1 url2"       sobrescreve URLs de health check
#   UPDATE_TIMEOUT=15             timeout (s) por health check
#
# O script NÃO usa git reset --hard e NÃO apaga alterações locais.

BRANCH="${BRANCH:-main}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"
RESTART_SERVICES="${RESTART_SERVICES:-1}"
RUN_HEALTHCHECKS="${RUN_HEALTHCHECKS:-1}"
UPDATE_TIMEOUT="${UPDATE_TIMEOUT:-15}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

PASS=0
WARN=0
FAIL=0
RESTARTED_SERVICES=()
DETECTED_SERVICES=()
HEALTH_RESULTS=()

if [[ -t 1 ]]; then
  C_GREEN='\033[0;32m'
  C_YELLOW='\033[1;33m'
  C_RED='\033[0;31m'
  C_BLUE='\033[0;34m'
  C_BOLD='\033[1m'
  C_RESET='\033[0m'
else
  C_GREEN=''
  C_YELLOW=''
  C_RED=''
  C_BLUE=''
  C_BOLD=''
  C_RESET=''
fi

section() { printf '\n%b== %s ==%b\n' "$C_BLUE$C_BOLD" "$*" "$C_RESET"; }
ok()      { PASS=$((PASS + 1)); printf '%b[ OK ]%b %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()    { WARN=$((WARN + 1)); printf '%b[WARN]%b %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
fail()    { FAIL=$((FAIL + 1)); printf '%b[FAIL]%b %s\n' "$C_RED" "$C_RESET" "$*"; }
info()    { printf '[....] %s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

sudo_cmd() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  else
    return 127
  fi
}

on_error() {
  local code=$?
  printf '\n%bErro inesperado%b na linha %s (exit=%s).\n' "$C_RED" "$C_RESET" "${BASH_LINENO[0]:-?}" "$code" >&2
  printf 'Nenhum git reset --hard foi executado; verifique a saída acima.\n' >&2
  exit "$code"
}
trap on_error ERR

section "Live.infinita - atualização do servidor"
printf 'Repositório : %s\n' "$REPO_DIR"
printf 'Branch      : %s\n' "$BRANCH"
printf 'Data        : %s\n' "$(date -Is 2>/dev/null || date)"

cd "$REPO_DIR"

section "Pré-validação"
if ! have git; then
  fail "git não está instalado."
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "$REPO_DIR não é um repositório Git."
  exit 1
fi

CURRENT_BRANCH="$(git branch --show-current)"
CURRENT_SHA="$(git rev-parse --short HEAD)"
info "Commit atual: $CURRENT_SHA ($CURRENT_BRANCH)"

if [[ -n "$(git status --porcelain)" ]]; then
  warn "Existem alterações locais. O deploy foi interrompido para não sobrescrevê-las."
  git status --short
  printf '\nResolva/commite/stash as alterações e execute novamente.\n'
  exit 2
fi
ok "Working tree limpo."

section "Atualizando código"
git fetch --prune origin

if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git checkout "$BRANCH"
else
  git checkout -b "$BRANCH" --track "origin/$BRANCH"
fi

git pull --ff-only origin "$BRANCH"
NEW_SHA="$(git rev-parse --short HEAD)"
if [[ "$CURRENT_SHA" == "$NEW_SHA" ]]; then
  ok "Código já estava atualizado em $NEW_SHA."
else
  ok "Código atualizado: $CURRENT_SHA -> $NEW_SHA."
fi

section "Dependências"
if [[ "$INSTALL_DEPS" != "1" ]]; then
  warn "Instalação de dependências desativada (INSTALL_DEPS=$INSTALL_DEPS)."
else
  PYTHON_BIN=""
  if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_DIR/.venv/bin/python"
    ok "Virtualenv detectado: .venv"
  elif [[ -x "$REPO_DIR/venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_DIR/venv/bin/python"
    ok "Virtualenv detectado: venv"
  elif have python3; then
    PYTHON_BIN="$(command -v python3)"
    warn "Virtualenv não encontrado; usando $PYTHON_BIN."
  fi

  if [[ -n "$PYTHON_BIN" ]]; then
    REQUIREMENTS=()
    [[ -f "$REPO_DIR/requirements.txt" ]] && REQUIREMENTS+=("$REPO_DIR/requirements.txt")
    while IFS= read -r -d '' f; do
      REQUIREMENTS+=("$f")
    done < <(find "$REPO_DIR/apps" -mindepth 2 -maxdepth 2 -name requirements.txt -print0 2>/dev/null || true)

    if ((${#REQUIREMENTS[@]} > 0)); then
      "$PYTHON_BIN" -m pip install --disable-pip-version-check -U pip
      for req in "${REQUIREMENTS[@]}"; do
        info "Instalando $(realpath --relative-to="$REPO_DIR" "$req" 2>/dev/null || echo "$req")"
        "$PYTHON_BIN" -m pip install -r "$req"
      done
      ok "Dependências Python atualizadas."
    elif [[ -f "$REPO_DIR/pyproject.toml" ]]; then
      if have uv; then
        (cd "$REPO_DIR" && uv sync)
        ok "Dependências sincronizadas com uv."
      else
        warn "pyproject.toml encontrado, mas uv não está instalado e não há requirements.txt."
      fi
    else
      warn "Nenhum requirements.txt/pyproject.toml encontrado; nada para instalar."
    fi
  else
    warn "Python não encontrado; etapa Python ignorada."
  fi
fi

section "Containers (quando presentes)"
COMPOSE_FILE=""
for f in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do
  if [[ -f "$REPO_DIR/$f" ]]; then
    COMPOSE_FILE="$REPO_DIR/$f"
    break
  fi
done

if [[ -n "$COMPOSE_FILE" ]]; then
  if have docker && docker compose version >/dev/null 2>&1; then
    info "Compose detectado: $(basename "$COMPOSE_FILE")"
    docker compose -f "$COMPOSE_FILE" pull --ignore-pull-failures || warn "Nem todas as imagens puderam ser atualizadas."
    docker compose -f "$COMPOSE_FILE" up -d --build --remove-orphans
    ok "Docker Compose atualizado e iniciado."
  else
    warn "Arquivo Compose encontrado, mas 'docker compose' não está disponível."
  fi
else
  info "Nenhum arquivo Docker Compose no repositório."
fi

section "Serviços systemd"
# Somente unidades relacionadas explicitamente à Live.infinita.
SYSTEMD_PATTERNS=(
  'live-infinita*.service'
  'liveinfinita*.service'
)

if have systemctl; then
  mapfile -t DETECTED_SERVICES < <(
    systemctl list-unit-files --type=service --no-legend 2>/dev/null \
      | awk '{print $1}' \
      | grep -E '^(live-infinita|liveinfinita).*\.service$' \
      | sort -u || true
  )

  if ((${#DETECTED_SERVICES[@]} == 0)); then
    warn "Nenhuma unidade systemd live-infinita*.service encontrada."
  elif [[ "$RESTART_SERVICES" != "1" ]]; then
    warn "Restart de serviços desativado (RESTART_SERVICES=$RESTART_SERVICES)."
    printf 'Detectados: %s\n' "${DETECTED_SERVICES[*]}"
  else
    sudo_cmd systemctl daemon-reload || warn "Não foi possível executar systemctl daemon-reload."
    for svc in "${DETECTED_SERVICES[@]}"; do
      info "Reiniciando $svc"
      if sudo_cmd systemctl restart "$svc"; then
        RESTARTED_SERVICES+=("$svc")
        ok "$svc reiniciado."
      else
        fail "Falha ao reiniciar $svc."
      fi
    done
  fi
else
  warn "systemctl não disponível; etapa systemd ignorada."
fi

section "Status dos serviços"
if have systemctl && ((${#DETECTED_SERVICES[@]} > 0)); then
  for svc in "${DETECTED_SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc"; then
      ok "$svc = active"
    else
      STATE="$(systemctl is-active "$svc" 2>/dev/null || true)"
      fail "$svc = ${STATE:-unknown}"
      systemctl --no-pager --full status "$svc" 2>/dev/null | tail -n 12 || true
    fi
  done
else
  info "Sem unidades systemd Live.infinita para validar."
fi

section "Health checks HTTP"
if [[ "$RUN_HEALTHCHECKS" != "1" ]]; then
  warn "Health checks desativados (RUN_HEALTHCHECKS=$RUN_HEALTHCHECKS)."
elif ! have curl; then
  warn "curl não está instalado; health checks HTTP ignorados."
else
  if [[ -n "${HEALTH_URLS:-}" ]]; then
    read -r -a URLS <<< "$HEALTH_URLS"
  else
    # Portas/rotas candidatas. 404/000 são tratados apenas como indisponíveis,
    # pois os serviços ainda estão sendo consolidados no MVP.
    URLS=(
      'http://127.0.0.1:8000/health'
      'http://127.0.0.1:8080/health'
      'http://127.0.0.1:8765/health'
      'http://127.0.0.1:3000/health'
    )
  fi

  HTTP_OK=0
  for url in "${URLS[@]}"; do
    code="$(curl -sS -o /dev/null -m "$UPDATE_TIMEOUT" -w '%{http_code}' "$url" 2>/dev/null || echo 000)"
    if [[ "$code" =~ ^2[0-9][0-9]$|^3[0-9][0-9]$ ]]; then
      HEALTH_RESULTS+=("OK   $code $url")
      HTTP_OK=$((HTTP_OK + 1))
      ok "$code $url"
    else
      HEALTH_RESULTS+=("---- $code $url")
      info "$code $url"
    fi
  done

  if ((HTTP_OK == 0)); then
    warn "Nenhum endpoint HTTP candidato respondeu 2xx/3xx. Isso pode ser normal enquanto os endpoints do MVP ainda não estiverem instalados."
  fi
fi

section "Resumo final"
printf 'Commit      : %s\n' "$NEW_SHA"
printf 'Branch      : %s\n' "$BRANCH"
printf 'OK          : %d\n' "$PASS"
printf 'Avisos      : %d\n' "$WARN"
printf 'Falhas      : %d\n' "$FAIL"

if ((${#RESTARTED_SERVICES[@]} > 0)); then
  printf 'Reiniciados : %s\n' "${RESTARTED_SERVICES[*]}"
else
  printf 'Reiniciados : nenhum serviço systemd\n'
fi

if ((${#HEALTH_RESULTS[@]} > 0)); then
  printf '\nEndpoints:\n'
  printf '  %s\n' "${HEALTH_RESULTS[@]}"
fi

printf '\n'
if ((FAIL > 0)); then
  printf '%bDEPLOY CONCLUÍDO COM FALHAS%b\n' "$C_RED$C_BOLD" "$C_RESET"
  printf 'Veja os itens [FAIL] acima e, para systemd, use:\n'
  printf '  journalctl -u NOME_DO_SERVICO -n 100 --no-pager\n'
  exit 1
elif ((WARN > 0)); then
  printf '%bDEPLOY CONCLUÍDO COM AVISOS%b\n' "$C_YELLOW$C_BOLD" "$C_RESET"
  printf 'O código foi atualizado, mas há itens ainda não configurados ou não detectados.\n'
  exit 0
else
  printf '%bDEPLOY OK - TODOS OS CHECKS PASSARAM%b\n' "$C_GREEN$C_BOLD" "$C_RESET"
  exit 0
fi
