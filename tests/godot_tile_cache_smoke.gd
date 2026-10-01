extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var preview_script = load("res://world_map_preview.gd")
    var preview = preview_script.new()
    var cache_root := Node3D.new()
    cache_root.name = "TileCache"
    cache_root.visible = false
    preview._tile_cache_root = cache_root
    preview.add_child(cache_root)

    var tile := Node3D.new()
    tile.name = "Tile_10_15"
    preview.add_child(tile)
    preview._cache_tile("10:15", tile)

    check(preview._tile_cache.size() == 1, "Tile must enter cache")
    check(tile.get_parent() == cache_root, "Cached tile parent must be cache root")
    check(not tile.visible, "Cached tile must be hidden")

    var reused: Node3D = preview._take_cached_tile("10:15")
    check(reused == tile, "Cache hit must reuse exact tile instance")
    check(reused.get_parent() == preview, "Reused tile must return to visible scene")
    check(reused.visible, "Reused tile must be visible")
    check(preview._tile_cache.size() == 0, "Cache entry must be consumed")
    check(preview._tile_cache_hits == 1, "Cache hit counter")
    check(preview._tile_cache_misses == 0, "No miss expected")

    preview._cache_tile("10:15", reused)
    preview._clear_tile_cache()
    check(preview._tile_cache.size() == 0, "Projection invalidation must clear cache")
    check(preview._tile_cache_hits == 0, "Invalidation resets hit counter")
    check(preview._tile_cache_misses == 0, "Invalidation resets miss counter")

    preview.free()
    print("Tile cache smoke: ", failures, " failures")
    quit(1 if failures else 0)
