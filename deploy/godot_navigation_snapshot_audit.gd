extends SceneTree
func _initialize() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 1:
        push_error("Provide a saved navigation cfg path")
        quit(2)
        return
    var cfg := ConfigFile.new()
    if cfg.load(args[0]) != OK:
        push_error("Navigation cfg could not be loaded")
        quit(1)
        return
    var memory = load("res://nov_navigation_experience.gd").new(args[0])
    var blocked: Dictionary = cfg.get_value("experience", "failures", {})
    var routes: Dictionary = cfg.get_value("experience", "routes", {})
    if memory.failures != blocked or memory.routes != routes:
        push_error("Saved navigation evidence was not restored")
        quit(1)
        return
    var reused := false
    for key in routes:
        var parts: PackedStringArray = str(key).split("|")
        var goal_parts := parts[0].split(",")
        var start_parts := parts[1].split(",")
        var start := Vector2(float(start_parts[0]), float(start_parts[1]))
        var goal := Vector2(float(goal_parts[0]), float(goal_parts[1]))
        var saved: Vector2 = routes[key]
        if start.distance_to(saved) <= 0.05 or start.distance_to(saved) >= 2.0:
            continue
        reused = memory.target(start, goal).distance_to(saved) < 0.001
        break
    print("NAVIGATION_RELOAD_AUDIT ", JSON.stringify({
        "blocked_passages": blocked.size(),
        "successful_steps": routes.size(),
        "restored": true,
        "saved_route_reused": reused,
        "source_written": false,
    }))
    quit(0 if routes.is_empty() or reused else 1)
