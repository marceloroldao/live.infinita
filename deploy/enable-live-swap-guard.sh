#!/usr/bin/env bash
set -Eeuo pipefail

# Safety buffer, not a substitute for fixing retained Python objects.
[[ "${EUID}" -ne 0 ]] || { echo "Execute como etbra, sem sudo no comando externo."; exit 2; }
sudo -v
SIZE_MIB=2048
SWAP=/swapfile-live-infinita
echo "== Preflight =="
free -m
df -Pm /
if grep -q "^$SWAP[[:space:]]" /proc/swaps; then
  echo "SWAP_ALREADY_ACTIVE"
else
  if [[ -e "$SWAP" ]]; then
    sudo test -f "$SWAP" || { echo "swap path is not a regular file"; exit 2; }
    actual="$(sudo stat -c %s "$SWAP")"
    [[ "$actual" -eq $((SIZE_MIB * 1024 * 1024)) ]] || { echo "Existing swap has unexpected size"; exit 2; }
  else
    available="$(df -Pm / | awk 'NR==2 {print $4}')"
    (( available > SIZE_MIB + 2048 )) || { echo "Insufficient disk free space"; exit 2; }
    sudo install -m 0600 -o root -g root /dev/null "$SWAP"
    if ! sudo fallocate -l "${SIZE_MIB}M" "$SWAP"; then
      sudo dd if=/dev/zero of="$SWAP" bs=1M count="$SIZE_MIB" conv=fsync status=progress
    fi
  fi
  sudo chmod 0600 "$SWAP"
  sudo mkswap -f "$SWAP"
  sudo swapon "$SWAP"
fi
# One idempotent fstab entry. No data ledgers are modified.
if ! sudo grep -Eq "^$SWAP[[:space:]]+none[[:space:]]+swap[[:space:]]" /etc/fstab; then
  printf '%s\n' "$SWAP none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi
sudo install -d -m 0755 /etc/sysctl.d
printf 'vm.swappiness=10\n' | sudo tee /etc/sysctl.d/90-live-infinita-memory.conf >/dev/null
sudo sysctl -p /etc/sysctl.d/90-live-infinita-memory.conf
echo "== Result =="
swapon --show
free -m
systemctl show live-infinita-autonomous-world.service -p ActiveState -p MainPID -p NRestarts
echo LIVE_SWAP_GUARD_OK
