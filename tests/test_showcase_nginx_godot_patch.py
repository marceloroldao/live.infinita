from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "deploy" / "nginx_godot_patch.py"
spec = importlib.util.spec_from_file_location("nginx_godot_patch", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
patch_nginx_config = module.patch_nginx_config
server_ranges = module.server_ranges


class NginxGodotPatchTest(unittest.TestCase):
    def test_patches_content_vhost_but_keeps_http_redirect_pure(self) -> None:
        source = """
server {
    listen 80;
    server_name live.etbra.com.br;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name live.etbra.com.br;
    location / { proxy_pass http://127.0.0.1:8080; }
}
"""
        patched, matched, updated = patch_nginx_config(source)
        self.assertEqual(matched, 2)
        self.assertEqual(updated, 1)
        self.assertEqual(patched.count("location ^~ /godot/"), 1)
        self.assertEqual(patched.count("location = /godot"), 1)

    def test_patches_http_only_install(self) -> None:
        source = """
server {
    listen 80 default_server;
    server_name live.etbra.com.br _;
    location / { proxy_pass http://127.0.0.1:8080; }
}
"""
        patched, matched, updated = patch_nginx_config(source)
        self.assertEqual((matched, updated), (1, 1))
        self.assertIn("alias /var/www/live-infinita-godot/;", patched)
        self.assertIn("try_files $uri $uri/ /godot/index.html;", patched)

    def test_is_idempotent(self) -> None:
        source = """
server {
    listen 443 ssl;
    server_name live.etbra.com.br;
    location / { return 200; }
}
"""
        once, _, first = patch_nginx_config(source)
        twice, matched, second = patch_nginx_config(once)
        self.assertEqual(first, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(second, 0)
        self.assertEqual(once, twice)

    def test_unrelated_vhost_is_untouched(self) -> None:
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

    def test_fresh_install_template_and_installers_keep_route_contract(self) -> None:
        nginx = (ROOT / "deploy" / "nginx-live-infinita.conf").read_text(encoding="utf-8")
        ubuntu = (ROOT / "deploy" / "install-ubuntu.sh").read_text(encoding="utf-8")
        godot = (ROOT / "deploy" / "install-godot-web.sh").read_text(encoding="utf-8")

        self.assertIn("server_name live.etbra.com.br _;", nginx)
        self.assertIn("location ^~ /godot/", nginx)
        self.assertIn("EXISTING_VHOST", ubuntu)
        self.assertIn("Preservando vhost nginx existente", ubuntu)
        self.assertIn("nginx_godot_patch.py", godot)
        self.assertIn("export-godot-web.sh", godot)
        self.assertIn("rollback_nginx", godot)


if __name__ == "__main__":
    unittest.main()
