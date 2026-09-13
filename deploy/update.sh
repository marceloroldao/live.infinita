#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${BRANCH:-hardening/live-showcase-002}"
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

ok(){ printf '[ OK ] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; }
fail(){ printf '[FAIL] %s\n' "$*"; }

printf '\n== Live.infinita deploy ==\n'
printf 'Repo   : %s\n' "$REPO_DIR"
printf 'Branch : %s\n' "$BRANCH"
printf 'Data   : %s\n\n' "$(date -Is 2>/dev/null || date)"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  fail 'Existem alterações rastreadas locais. Abortando para não sobrescrever nada.'
  git status --short
  exit 2
fi

# Ignora artefatos locais esperados do servidor; untracked não bloqueiam o deploy.
git fetch --prune origin
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git switch "$BRANCH"
else
  git switch -c "$BRANCH" --track "origin/$BRANCH"
fi

git pull --ff-only origin "$BRANCH"
ok "Código atualizado em $(git rev-parse --short HEAD)"

# Dependências Python
if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python;
elif [[ -x venv/bin/python ]]; then PY=venv/bin/python;
else PY="$(command -v python3 || true)"; fi

if [[ -n "$PY" ]]; then
  while IFS= read -r req; do
    [[ -n "$req" ]] || continue
    printf '[....] pip install -r %s\n' "$req"
    "$PY" -m pip install -r "$req"
  done < <(find apps tests -name requirements.txt -type f 2>/dev/null | sort -u)
fi

# Reinicia somente serviços realmente instalados.
mapfile -t SERVICES < <(systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -E '^live-infinita.*\.service$' | sort -u || true)

if ((${#SERVICES[@]})); then
  sudo systemctl daemon-reload
  for svc in "${SERVICES[@]}"; do
    printf '[....] reiniciando %s\n' "$svc"
    sudo systemctl restart "$svc" || true
  done
else
  warn 'Nenhum serviço live-infinita*.service instalado.'
fi

printf '\n== Status ==\n'
FAIL=0
if ((${#SERVICES[@]})); then
  for svc in "${SERVICES[@]}"; do
    state="$(systemctl is-active "$svc" 2>/dev/null || true)"
    if [[ "$state" == active ]]; then
      ok "$svc = active"
    else
      fail "$svc = ${state:-unknown}"
      FAIL=$((FAIL+1))
    fi
  done
fi

printf '\n== Portas em escuta ==\n'
ss -ltnp 2>/dev/null | grep -E ':(80|443|8000|8080|8765|3000|9000)\b' || true

printf '\n== HTTP ==\n'
for url in \
  http://127.0.0.1/ \
  http://127.0.0.1:8000/health \
  http://127.0.0.1:8080/health \
  http://127.0.0.1:8765/health; do
  code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
  [[ -n "$code" ]] || code=000
  printf '%s  %s\n' "$code" "$url"
done

printf '\nCommit: %s\n' "$(git log -1 --oneline)"
printf 'Branch: %s\n' "$(git branch --show-current)"

if ((FAIL)); then
  printf '\nDEPLOY CONCLUÍDO COM %d SERVIÇO(S) FORA DO AR\n' "$FAIL"
  exit 1
fi

printf '\nDEPLOY CONCLUÍDO\n'
