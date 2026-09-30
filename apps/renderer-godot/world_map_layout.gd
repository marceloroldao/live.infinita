extends RefCounted

var grid_size: int
var tile_size_m: float
var half_m: float
var active_radius_tiles: int
var decorations_per_tile: int
var landmarks: Array

func _init(map_data: Dictionary) -> void:
    grid_size = maxi(4, int(map_data.get("grid_size", 16)))
    tile_size_m = maxf(8.0, float(map_data.get("tile_size_m", 64)))
    half_m = float(grid_size) * tile_size_m * 0.5
    active_radius_tiles = clampi(int(map_data.get("active_radius_tiles", 1)), 1, 2)
    decorations_per_tile = clampi(int(map_data.get("max_decorations_per_tile", 6)), 0, 12)
    landmarks = Array(map_data.get("landmarks", [])).duplicate(true)

func world_size_m() -> int:
    return int(round(float(grid_size) * tile_size_m))

func cell(value: float) -> int:
    return clampi(floori((value + half_m) / tile_size_m), 0, grid_size - 1)

func cell_center(cell_value: Array) -> Vector2:
    return Vector2(
        (float(cell_value[0]) + 0.5) * tile_size_m - half_m,
        (float(cell_value[1]) + 0.5) * tile_size_m - half_m
    )

func tile_origin(cx: int, cz: int) -> Vector2:
    return Vector2(float(cx) * tile_size_m - half_m, float(cz) * tile_size_m - half_m)

func biome(cx: int, cz: int, river_world_x: float = 32.0) -> String:
    if cx == cell(river_world_x):
        return "river"
    var best_biome := "forest"
    var best_distance := 1_000_000.0
    for item in landmarks:
        if typeof(item) != TYPE_DICTIONARY:
            continue
        var landmark: Dictionary = item
        var cell_data = landmark.get("cell", [])
        if typeof(cell_data) != TYPE_ARRAY or cell_data.size() != 2:
            continue
        var radius := maxi(0, int(landmark.get("radius_tiles", 0)))
        var dx := absi(cx - int(cell_data[0]))
        var dz := absi(cz - int(cell_data[1]))
        if dx > radius or dz > radius:
            continue
        var distance := float(dx * dx + dz * dz)
        if distance < best_distance:
            best_distance = distance
            best_biome = str(landmark.get("biome", "forest"))
    return best_biome
