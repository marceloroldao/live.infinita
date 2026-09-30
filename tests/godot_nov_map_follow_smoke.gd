extends SceneTree
var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error("NOV_MAP_FOLLOW_FAIL " + label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    check(OS.get_cmdline_user_args().has("--follow-nov"), "opt_in_required")
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    await create_timer(3.0).timeout
    check(stage._follow_nov, "enabled")
    check(stage._has_follow_pose, "real_pose_received")
    check(stage._follow_sequence > 0, "world_sequence")
    check(stage._follow_region in ["shelter", "clearing", "deep_forest"], "mapped_region")
    check(stage._tiles.size() <= 9, "bounded_tiles")
    check(absf(stage._position.x) < 512.0 and absf(stage._position.z) < 512.0, "map_bounds")
    if failures == 0:
        print("NOV_MAP_FOLLOW_SMOKE_OK read_only=true region=%s tiles=%d" % [stage._follow_region, stage._tiles.size()])
        quit(0)
    else:
        quit(1)
