#!/usr/bin/env bash
set -Eeuo pipefail

DISK=/dev/sda
PARTITION_NUMBER=3
PARTITION=/dev/sda3
LV=/dev/ubuntu-vg/ubuntu-lv
MIN_DISK_BYTES=$((40 * 1024 * 1024 * 1024))

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute com sudo: sudo bash deploy/extend-root-lvm-after-hypervisor-resize.sh" >&2
  exit 1
fi

for cmd in growpart pvresize lvextend resize2fs blockdev findmnt; do
  command -v "$cmd" >/dev/null || { echo "Comando ausente: $cmd" >&2; exit 1; }
done

[[ -b "$DISK" ]] || { echo "Disco $DISK não encontrado." >&2; exit 1; }
[[ -b "$PARTITION" ]] || { echo "Partição $PARTITION não encontrada." >&2; exit 1; }
[[ -e "$LV" || -e /dev/mapper/ubuntu--vg-ubuntu--lv ]] || {
  echo "LV raiz esperado não encontrado." >&2
  exit 1
}

ROOT_SOURCE="$(findmnt -n -o SOURCE /)"
ROOT_FSTYPE="$(findmnt -n -o FSTYPE /)"
DISK_BYTES="$(blockdev --getsize64 "$DISK")"
PART_BYTES="$(blockdev --getsize64 "$PARTITION")"

echo "=== ANTES ==="
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$DISK"
df -hT /
echo "root_source=$ROOT_SOURCE"
echo "root_fstype=$ROOT_FSTYPE"
echo "disk_bytes=$DISK_BYTES"
echo "partition_bytes=$PART_BYTES"

if (( DISK_BYTES < MIN_DISK_BYTES )); then
  echo "ABORTADO: /dev/sda ainda tem menos de 40 GiB." >&2
  echo "Aumente primeiro o disco virtual no hypervisor (recomendado: 80 GB)." >&2
  exit 2
fi

if (( DISK_BYTES <= PART_BYTES + 1073741824 )); then
  echo "ABORTADO: não há pelo menos 1 GiB novo disponível para expandir a partição." >&2
  exit 3
fi

if [[ "$ROOT_FSTYPE" != "ext4" ]]; then
  echo "ABORTADO: filesystem raiz esperado ext4, encontrado: $ROOT_FSTYPE" >&2
  exit 4
fi

echo "=== EXPANDINDO PARTIÇÃO 3 ==="
growpart "$DISK" "$PARTITION_NUMBER"

command -v partprobe >/dev/null && partprobe "$DISK" || true
command -v udevadm >/dev/null && udevadm settle || true

echo "=== EXPANDINDO PV LVM ==="
pvresize "$PARTITION"

echo "=== EXPANDINDO LV + FILESYSTEM ==="
lvextend -l +100%FREE -r "$LV"

echo "=== DEPOIS ==="
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS "$DISK"
df -hT /

FINAL_BYTES="$(blockdev --getsize64 "$DISK")"
echo "disk_bytes_final=$FINAL_BYTES"
echo "ROOT_LVM_EXPANSION_OK"
