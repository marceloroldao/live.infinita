extends RefCounted

# A presentation-only catalog. The World State stores identities/properties, never
# paths to vendor mesh files. The importer writes this catalog beside local models.
const CATALOG_PATH := "res://assets/quaternius/stylized_nature_megakit/catalog.json"
const MODEL_PREFIX := "res://assets/quaternius/stylized_nature_megakit/models/"

var _by_kind: Dictionary = {}

func _init() -> void:
    reload()

func reload() -> void:
    _by_kind.clear()
    if not FileAccess.file_exists(CATALOG_PATH):
        return
    var data = JSON.parse_string(FileAccess.get_file_as_string(CATALOG_PATH))
    if typeof(data) != TYPE_DICTIONARY or int(data.get("schema_version", 0)) != 1:
        push_warning("Quaternius nature catalog has an unsupported format.")
        return
    var assets = data.get("assets", [])
    if typeof(assets) != TYPE_ARRAY:
        return
    for item in assets:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        var kind := str(item.get("kind", "nature"))
        var path := str(item.get("path", ""))
        if not path.begins_with(MODEL_PREFIX) or ".." in path or not path.to_lower().ends_with(".glb") and not path.to_lower().ends_with(".gltf"):
            continue
        if not _by_kind.has(kind):
            _by_kind[kind] = []
        _by_kind[kind].append(item.duplicate(true))
    for kind in _by_kind:
        _by_kind[kind].sort_custom(func(a, b): return str(a.get("id", "")) < str(b.get("id", "")))

func count(kind: String) -> int:
    return _by_kind.get(kind, []).size()

func pick(kind: String, variant: int = 0) -> Dictionary:
    var items: Array = _by_kind.get(kind, [])
    if items.is_empty():
        return {}
    return items[posmod(variant, items.size())].duplicate(true)
