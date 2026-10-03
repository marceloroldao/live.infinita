extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func height(_x: float, _z: float) -> float:
    return 0.0

func allowed(_x: float, _z: float) -> bool:
    return true

func cell(value: float) -> int:
    return int(floor(value / 64.0))

func state() -> Dictionary:
    return {
        "state_id": "hero-test",
        "regions": [
            {
                "region_id": "forest",
                "ecological_zone": "forest",
                "climate_type": "temperate_humid",
                "vegetation_density": 0.82,
                "tree_suitability": 0.78,
                "rock_exposure": 0.05,
                "snow_cover": 0.0,
            },
            {
                "region_id": "alpine",
                "ecological_zone": "alpine_rock",
                "climate_type": "alpine_cold",
                "vegetation_density": 0.08,
                "tree_suitability": 0.05,
                "rock_exposure": 0.82,
                "snow_cover": 0.30,
            },
        ],
    }

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var script = load("res://world_map_perceptual_assets.gd")
    check(script != null, "Hero asset module must load")
    if script == null:
        quit(1)
        return

    var root3d := Node3D.new()
    root.add_child(root3d)
    var hero = script.new(
        root3d,
        Callable(self, "height"),
        Callable(self, "allowed"),
        Callable(self, "cell"),
        1024.0,
    )
    hero.build()
    hero.update_environment(state())

    var forest: Dictionary = hero._environment("forest")
    var alpine: Dictionary = hero._environment("alpine")
    check(hero._tree_asset(forest).ends_with("CommonTree_1.gltf"), "Temperate forest must choose common tree")
    check(hero._tree_asset(alpine).ends_with("Pine_1.gltf"), "Cold alpine climate must choose pine class")
    check(hero._mid_tree_asset(forest).ends_with("CommonTree_5.gltf"), "Temperate midground must use lighter common tree")
    check(hero._mid_tree_asset(alpine).ends_with("Pine_5.gltf"), "Cold midground must use lighter pine")
    check(hero._understory_asset(forest).ends_with("Bush_Common.gltf"), "Forest must choose bush understory")
    check(hero._understory_asset(alpine).ends_with("Bush_Common.gltf"), "Alpine rock does not force meadow grass")

    var forest_factors: Vector3 = hero._environment_factors(forest)
    var alpine_factors: Vector3 = hero._environment_factors(alpine)
    check(forest_factors.x > 0.6, "Forest must permit hero trees")
    check(alpine_factors.x == 0.0, "Alpine rock must suppress hero trees")
    check(alpine_factors.z > forest_factors.z, "Alpine rock must favor hero rocks")

    hero.rebuild(Vector3.ZERO, Vector3(0, 0, -1), "forest", true)
    var counts: Vector3i = hero.visible_counts()
    var mid_count: int = hero.mid_tree_visible_count()
    check(counts.x <= 14 and counts.y <= 40 and counts.z <= 18, "Visible counts must stay bounded")
    check(mid_count <= 18, "Midground real-tree count must stay bounded")
    if hero.vendor_ready():
        check(mid_count > 0, "Temperate forest must materialize real midground trees")
    else:
        check(counts == Vector3i.ZERO, "Missing import cache must make hero layer invisible")
        check(mid_count == 0, "Missing import cache must hide midground real trees")

    root3d.queue_free()
    await process_frame
    print("Environmental hero assets smoke: ", failures, " failures")
    quit(1 if failures else 0)
