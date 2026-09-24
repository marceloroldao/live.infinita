from __future__ import annotations

import re
import sys
from pathlib import Path

STATUS_LOCATION = '''    location = /broadcast-status.json {\n        alias /var/lib/live-infinita/broadcaster-status.json;\n        default_type application/json;\n        add_header Cache-Control "no-store" always;\n        add_header X-Content-Type-Options "nosniff" always;\n    }\n\n'''


def server_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    pos = 0
    pattern = re.compile(r"\bserver\s*\{")
    while True:
        match = pattern.search(text, pos)
        if match is None:
            return ranges
        brace = text.find("{", match.start())
        depth = 0
        i = brace
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    ranges.append((match.start(), i + 1))
                    pos = i + 1
                    break
            i += 1
        else:
            raise ValueError("bloco server nginx sem fechamento")


def server_names(server_block: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"(?m)^\s*server_name\s+([^;]+);", server_block):
        names.update(part.strip() for part in match.group(1).split() if part.strip())
    return names


def patch_nginx_config(text: str, server_name: str = "live.etbra.com.br") -> tuple[str, int, int]:
    insertions: list[int] = []
    matched = 0
    for start, end in server_ranges(text):
        chunk = text[start:end]
        if server_name not in server_names(chunk):
            continue
        matched += 1
        if re.search(r"(?m)^\s*location\s*=\s*/broadcast-status\.json\s*\{", chunk):
            continue
        first_location = re.search(r"(?m)^\s*location\s+", chunk)
        insertions.append(end - 1 if first_location is None else start + first_location.start())

    result = text
    for insert_at in reversed(insertions):
        result = result[:insert_at] + STATUS_LOCATION + result[insert_at:]
    return result, matched, len(insertions)


def patch_file(path: Path, server_name: str = "live.etbra.com.br") -> tuple[int, int]:
    original = path.read_text(encoding="utf-8")
    patched, matched, updated = patch_nginx_config(original, server_name)
    if matched == 0:
        raise ValueError(f"nenhum bloco server encontrado para {server_name}")
    if patched != original:
        path.write_text(patched, encoding="utf-8")
    return matched, updated


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(f"uso: {argv[0]} ARQUIVO_NGINX [SERVER_NAME]", file=sys.stderr)
        return 2
    try:
        matched, updated = patch_file(Path(argv[1]), argv[2] if len(argv) == 3 else "live.etbra.com.br")
    except (OSError, ValueError) as exc:
        print(f"falha ao preparar status do Broadcaster: {exc}", file=sys.stderr)
        return 1
    print(f"Nginx: {matched} bloco(s); {updated} rota(s) /broadcast-status.json adicionada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
