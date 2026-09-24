from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "deploy" / "nginx_audio_patch.py"
spec = importlib.util.spec_from_file_location("nginx_audio_patch", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
patch_nginx_config = module.patch_nginx_config
server_ranges = module.server_ranges


class NginxAudioPatchTest(unittest.TestCase):
    def test_patches_http_and_https_blocks(self) -> None:
        source = """
server {
    listen 80;
    server_name live.etbra.com.br;
    location / { proxy_pass http://127.0.0.1:8080; }
}
server {
    listen 443 ssl;
    server_name live.etbra.com.br;
    location /godot/ { root /var/www/live-infinita-godot; }
}
"""
        patched, matched, updated = patch_nginx_config(source)
        self.assertEqual(matched, 2)
        self.assertEqual(updated, 2)
        self.assertEqual(patched.count("location /audio/"), 2)

    def test_accepts_server_name_with_aliases(self) -> None:
        source = """
server {
    listen 443 ssl;
    server_name www.example.test live.etbra.com.br alias.example.test;
    location / { return 200; }
}
"""
        patched, matched, updated = patch_nginx_config(source)
        self.assertEqual((matched, updated), (1, 1))
        self.assertIn("location /audio/", patched)

    def test_is_idempotent(self) -> None:
        source = """
server {
    listen 443 ssl;
    server_name live.etbra.com.br;
    location / { return 200; }
}
"""
        once, _, updated_first = patch_nginx_config(source)
        twice, matched, updated_second = patch_nginx_config(once)
        self.assertEqual(updated_first, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(updated_second, 0)
        self.assertEqual(once, twice)

    def test_does_not_touch_unrelated_vhost(self) -> None:
        source = """
server {
    server_name other.example.test;
    location / { return 200; }
}
"""
        patched, matched, updated = patch_nginx_config(source)
        self.assertEqual((matched, updated), (0, 0))
        self.assertEqual(patched, source)

    def test_malformed_server_block_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            server_ranges("server { server_name live.etbra.com.br;")


if __name__ == "__main__":
    unittest.main()
