from __future__ import annotations

import re
import sys
from pathlib import Path


GODOT_REDIRECT = '    location = /godot { return 308 /godot/; }\n'
GODOT_LOCATION = '''    location ^~ /godot/ {\n        alias /var/www/live-infinita-godot/;\n        try_files $uri $uri/ /godot/index.html;\n        add_header Cache-Control "no-cache" always;\n    }\n'''


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


def _redirect_only(server_block: str) -> bool:
    return bool(
        re.search(
            r"(?m)^\s*return\s+(?:301|302|307|308)\s+https?://",
            server_block,
        )
    )


def patch_nginx_config(text: str, server_name: str = "live.etbra.com.br") -> tuple[str, int, int]:
    changes: list[tuple[int, str]] = []
    matched = 0

    for start, end in server_ranges(text):
        chunk = text[start:end]
        if server_name not in server_names(chunk):
            continue
        matched += 1

        # A dedicated HTTP->HTTPS redirect block must remain a pure redirect.
        if _redirect_only(chunk):
            continue

        has_redirect = bool(re.search(r"(?m)^\s*location\s*=\s*/godot\s*\{", chunk))
        has_location = bool(re.search(r"(?m)^\s*location\s+\^~\s+/godot/\s*\{", chunk))
        if has_redirect and has_location:
            continue

        additions = ""
        if not has_redirect:
            additions += GODOT_REDIRECT
        if not has_location:
            additions += GODOT_LOCATION
        additions += "\n"

        first_location = re.search(r"(?m)^\s*location\s+", chunk)
        insert_at = end - 1 if first_location is None else start + first_location.start()
        changes.append((insert_at, additions))

    result = text
    for insert_at, additions in reversed(changes):
        result = result[:insert_at] + additions + result[insert_at:]
    return result, matched, len(changes)


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
        print(f"falha ao preparar rota /godot/: {exc}", file=sys.stderr)
        return 1
    print(f"Nginx: {matched} bloco(s) de {server_name}; {updated} rota(s) /godot/ atualizada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
