# Quaternius nature assets — Live.infinita

## First chosen pack

**Quaternius Stylized Nature MegaKit, Standard (free edition)**

- Official page: https://quaternius.com/packs/stylizednaturemegakit.html
- Download page: https://quaternius.itch.io/stylized-nature-megakit
- Author-uploaded public Standard mirror: https://opengameart.org/content/stylized-nature-megakit
- License: CC0-1.0 (personal and commercial use).
- Standard is a subset of the models in glTF/other exchange formats. The
  paid Source edition, not Standard, contains the prebuilt Godot project and
  specialized wind/grass shaders.
- Do not copy a Source edition asset or its example project into this repository
  unless that edition has actually been obtained.

The selected import contains **68 glTF models**, 68 referenced binary buffers and
15 PNG textures (151 extracted source files), with Godot import sidecars as
needed. The source ZIP SHA-256 is
`298f6732b872e4cf7b30e6e7abf9641c7f6dc6b326df37ac089533ed7e3d58c9`.

The original upstream ZIP is not committed. The **Standard** glTF models,
their referenced textures/buffers, and the generated catalog are committed to
this repository in `apps/renderer-godot/assets/quaternius/stylized_nature_megakit/`.
The `SOURCE.json` record stores the archive SHA-256 and acquisition URL.
FBX/OBJ duplicates and the paid Source project are excluded.

## Installation

The models are available immediately after `git pull`; no manual vendor ZIP
is required for a normal checkout/deploy. To update them from upstream,
obtain the **Standard** ZIP from the official page or its author-uploaded mirror.
2. From the repository root:

   python tools/import_quaternius_nature.py "/path/to/Stylized Nature MegaKit[Standard].zip" --dry-run
   python tools/import_quaternius_nature.py "/path/to/Stylized Nature MegaKit[Standard].zip"

3. Import resources once with the installed Godot 4 editor:

   godot --headless --editor --quit --path apps/renderer-godot

4. Open only the optional preview scene (this does **not** replace the live):

   godot --path apps/renderer-godot res://nature_preview.tscn

Tracked outputs:

- apps/renderer-godot/assets/quaternius/stylized_nature_megakit/models/
- apps/renderer-godot/assets/quaternius/stylized_nature_megakit/catalog.json

The importer extracts **glB if present, otherwise glTF and its referenced
buffers/textures**, not redundant FBX/OBJ versions. It rejects traversal,
symlinks, duplicate filenames and missing glTF dependencies. Re-running the
command replaces only this pack's local import. Do not use untrusted ZIPs.

## How it is used

- nature_asset_catalog.gd provides stable visual IDs, categories
  (tree/rock/plant/nature), paths and deterministic variant selection.
- nature_preview.tscn / nature_preview.gd load one exemplar per category.
  Unavailable models are clearly identified as *not imported*; plain blocks
  are only preview placeholders.
- main.tscn remains the production 2D livestream renderer. Neither World
  State nor Memoria.ia contains glTF paths. The visual catalog is presentation
  data, not world authority.

The present milestone verifies model import and preview, not integration in the 2D broadcast. Before showing
these 3D models in the 2D portrait live, choose either a separate 3D renderer
or a SubViewport/2D compositing approach, and test performance on the server.
Do not silently change the current broadcast scene.

## CI/offline validation

   python -m unittest -v tests.test_quaternius_nature_importer

CI tests synthetic ZIPs and validates GDScript without requiring external
download. Models are shipped by Git checkout. Run Godot's editor import step
after deployment. The one-time vendor workflow downloads the author-uploaded
Standard archive and commits only the glTF selection to this branch.
