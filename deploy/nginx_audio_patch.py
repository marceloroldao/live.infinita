from __future__ import annotations

import re
import sys
from pathlib import Path

AUDIO_LOCATION = '''    location /audio/ {\n        proxy_pass http://127.0.0.1:8092/;\n        proxy_http_version 1.1;\n        proxy_buffering off;\n        proxy_cache off;\n        proxy_read_timeout 3600s;\n        add_header Cache-Control "no-store" always;\n    }\n\n'''


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
            char = text[i]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    ranges.append((match.start(), i + 1))
                    pos = i + 1
                    break
            i += 1
        else:
            raise ValueError("bloco server nginx sem fechamento")


def _server_names(server_block: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(r"(?m)^\s*server_name\s+([^;]+);", server_block):
        names.update(part.strip() for part in match.group(1).split() if part.strip())
    return names


def patch_nginx_config(text: str, server_name: str = "live.etbra.com.br") -> tuple[str, int, int]:
    ranges = server_ranges(text)
    insertions: list[int] = []
    matched = 0

    for start, end in ranges:
        chunk = text[start:end]
        if server_name not in _server_names(chunk):
            continue
        matched += 1
        if re.search(r"(?m)^\s*location\s+/audio/\s*\{", chunk):
            continue

        first_location = re.search(r"(?m)^\s*location\s+", chunk)
        if first_location is None:
            insert_at = end - 1
        else:
            insert_at = start + first_location.start()
        insertions.append(insert_at)

    result = text
    for insert_at in reversed(insertions):
        result = result[:insert_at] + AUDIO_LOCATION + result[insert_at:]
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
    path = Path(argv[1])
    server_name = argv[2] if len(argv) == 3 else "live.etbra.com.br"
    try:
        matched, updated = patch_file(path, server_name)
    except (OSError, ValueError) as exc:
        print(f"falha ao preparar rota /audio/: {exc}", file=sys.stderr)
        return 1
    print(f"Nginx: {matched} bloco(s) de {server_name}; {updated} rota(s) /audio/ adicionada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
