#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/enable-https-mvp011.sh'; exit 1; }

domain=live.etbra.com.br
site=/etc/nginx/sites-available/live-infinita
backup=$(mktemp -d /var/backups/live-infinita-https.XXXXXX)
chmod 700 "$backup"
cp -p "$site" "$backup/nginx-live-infinita"
echo "Backup: $backup"

restore() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 ]]; then
    cp -p "$backup/nginx-live-infinita" "$site"
    nginx -t && systemctl reload nginx || true
    echo "HTTPS não foi ativado; nginx restaurado de $backup" >&2
  fi
  exit "$result"
}
trap restore EXIT

certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email \
  --redirect --domain "$domain"
nginx -t
systemctl reload nginx
curl --fail --silent --show-error "https://$domain/" | grep -q 'login-form'
curl --fail --silent --show-error "https://$domain/godot/" >/dev/null
curl --fail --silent --show-error "https://$domain/gdscript/" >/dev/null
echo 'HTTPS ativo. Login, Godot e GDScript validados.'
