extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error(label)
        failures += 1

func flat(center: Dictionary) -> Vector2:
    return Vector2(float(center.get("x", 0.0)), float(center.get("z", 0.0)))

func height(_x: float, _z: float) -> float:
    return 0.0

func projection() -> Dictionary:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": "palette-projection",
        "policy": {
            "visual_only": true,
            "world_write_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "snow_peak",
                "center": {"x": 0.0, "z": 0.0},
                "elevation_bias_m": 18.0,
                "influence_radius_m": 160.0,
                "cognitive_mass": 1.0,
                "terrain_role": "uplift",
                "lake_candidate": false,
            },
            {
                "region_id": "wet_valley",
                "center": {"x": 320.0, "z": 0.0},
                "elevation_bias_m": -5.0,
                "influence_radius_m": 100.0,
                "cognitive_mass": 0.5,
                "terrain_role": "basin",
                "lake_candidate": false,
            },
        ],
        "transitions": [],
        "spatial_trails": [],
    }

func environment() -> Dictionary:
    return {
        "schema": "live-infinita-environmental-state/v1",
        "state_id": "palette-env",
        "policy": {
            "world_write_authority": false,
            "memory_is_authority": false,
            "selection_authority": false,
        },
        "regions": [
            {
                "region_id": "snow_peak",
                "ecological_zone": "snowfield",
                "vegetation_density": 0.04,
                "soil_moisture": 0.55,
                "rock_exposure": 0.76,
                "snow_cover": 0.82,
            },
            {
                "region_id": "wet_valley",
                "ecological_zone": "wetland",
                "vegetation_density": 0.74,
                "soil_moisture": 0.94,
                "rock_exposure": 0.08,
                "snow_cover": 0.0,
            },
        ],
    }

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var host := Node3D.new()
    root.add_child(host)
    var terrain_script = load("res://world_map_cognitive_terrain.gd")
    var palette_script = load("res://world_map_environmental_palette.gd")
    check(terrain_script != null, "Cognitive terrain must load")
    check(palette_script != null, "Environmental palette must load")

    var terrain = terrain_script.new(host)
    var changed: bool = terrain.update(
        projection(),
        Callable(self, "flat"),
        Callable(self, "height"),
        environment(),
    )
    check(changed, "Projection/environment must update")

    var peak: Dictionary = terrain.environment_at(0.0, 0.0)
    var wet: Dictionary = terrain.environment_at(320.0, 0.0)
    check(str(peak.get("region_id", "")) == "snow_peak", "Peak must resolve snow environment")
    check(str(wet.get("region_id", "")) == "wet_valley", "Valley must resolve wet environment")
    check(float(peak.get("cognitive_influence", 0.0)) > 0.8, "Peak influence must be strong")
    check(float(wet.get("cognitive_influence", 0.0)) > 0.5, "Wet valley influence must be strong")

    var palette = palette_script.new()
    var base := Color("#52784e")
    var snow_color: Color = palette.terrain_color(base, peak)
    var wet_color: Color = palette.terrain_color(base, wet)
    check(snow_color.get_luminance() > base.get_luminance(), "Snow must brighten terrain")
    check(wet_color != base, "Wetland must tint terrain")
    check(snow_color != wet_color, "Distinct environments must produce distinct terrain colors")

    host.queue_free()
    await process_frame
    print("Environmental ground palette smoke: ", failures, " failures")
    quit(1 if failures else 0)
