# Quaternius nature assets — Live.infinita

## First chosen pack

**Quaternius Stylized Nature MegaKit, Standard (free edition)**

- Official page: https://quaternius.com/packs/stylizednaturemegakit.html
- Download page: https://quaternius.itch.io/stylized-nature-megakit
- License: CC0-1.0 (personal and commercial use).
- Standard is a subset of the models in glTF/other exchange formats. The
  paid Source edition, not Standard, contains the prebuilt Godot project and
  specialized wind/grass shaders.
- Do not copy a Source edition asset or its example project into this repository
  unless that edition has actually been obtained.

The ZIP is an upstream vendor download. It is **not currently committed** to
the repository. A catalog/preview integration is implemented here; imported
vendor models remain local and must be deployed separately. This avoids a
~99 MB archive plus its multiple engine formats in the source repository.

## Installation

1. Download the **Standard** ZIP from the official download page.
2. From the repository root:

   python tools/import_quaternius_nature.py "/path/to/Stylized Nature MegaKit[Standard].zip" --dry-run
   python tools/import_quaternius_nature.py "/path/to/Stylized Nature MegaKit[Standard].zip"

3. Import resources once with the installed Godot 4 editor:

   godot --headless --editor --quit --path apps/renderer-godot

4. Open only the optional preview scene (this does **not** replace the live):

   godot --path apps/renderer-godot res://nature_preview.tscn

Local outputs:

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

The present milestone verifies actual model import and preview. Before showing
these 3D models in the 2D portrait live, choose either a separate 3D renderer
or a SubViewport/2D compositing approach, and test performance on the server.
Do not silently change the current broadcast scene.

## CI/offline validation

   python -m unittest -v tests.test_quaternius_nature_importer

CI tests synthetic ZIPs and validates GDScript without requiring external
download. To ship models to the server, run the importer there (or copy the
resulting local asset directory) and run Godot's editor import step.
