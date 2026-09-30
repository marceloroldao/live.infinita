extends SceneTree

var failures := 0

func check(value: bool, label: String) -> void:
    if not value:
        push_error("NOV_MAP_PROJECTION_FAIL " + label)
        failures += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var mapping: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://nov_map_projection_001.json"))
    var projection = load("res://nov_map_projection.gd").new(mapping)
    var packet := {
        "type": "world_state",
        "world": {
            "world_id": "nov-live-autonomous-001",
            "sequence": 10,
            "interest": {"current_region_id": "shelter"}
        },
        "delivery": {
            "mode": "local_world_slice",
            "observer_entity_id": "nov",
            "observer": {"x": 930.0, "y": 390.0}
        }
    }
    var original := JSON.stringify(packet)
    var accepted: Dictionary = projection.project(packet)
    check(accepted.get("ok") == true, "valid_packet")
    check(accepted.get("position") == Vector2(-352.0, -32.0), "explicit_shelter_anchor")
    check(accepted.get("region_id") == "shelter", "region")
    check(JSON.stringify(packet) == original, "no_payload_mutation")
    check(projection.project(packet).get("reason") == "stale_sequence", "duplicate_rejected")
    var altered: Dictionary = packet.duplicate(true)
    altered["world"]["sequence"] = 11
    altered["delivery"]["observer_entity_id"] = "other"
    check(projection.project(altered).get("reason") == "observer_mismatch", "wrong_observer")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 12
    altered["world"]["world_id"] = "another-world"
    check(projection.project(altered).get("reason") == "world_mismatch", "wrong_world")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 13
    altered["world"]["interest"]["current_region_id"] = "unknown"
    check(projection.project(altered).get("reason") == "region_unmapped", "unknown_region")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 14
    altered["delivery"]["observer"]["x"] = 999999.0
    check(projection.project(altered).get("reason") == "observer_outside_anchor", "out_of_region")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 15
    altered["delivery"]["observer"]["x"] = "not-a-number"
    check(projection.project(altered).get("reason") == "observer_invalid", "bad_number")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 16
    altered["world"]["interest"]["current_region_id"] = "deep_forest"
    altered["delivery"]["observer"] = {"x": 350.0, "y": 340.0}
    check(projection.project(altered).get("position") == Vector2(-160.0, -224.0), "deep_forest_anchor")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 17
    altered["world"]["interest"]["current_region_id"] = "clearing"
    altered["delivery"]["observer"] = {"x": 640.0, "y": 360.0}
    check(projection.project(altered).get("position") == Vector2(-160.0, -32.0), "clearing_anchor")
    altered = packet.duplicate(true)
    altered["world"]["sequence"] = 18
    var through_json: Dictionary = JSON.parse_string(JSON.stringify(altered))
    check(projection.project(through_json).get("ok") == true, "json_numeric_roundtrip")
    var invalid: Dictionary = mapping.duplicate(true)
    invalid["preview_only"] = false
    check(load("res://nov_map_projection.gd").new(invalid).project(packet).get("reason") == "config_invalid", "disabled_mapping")
    if failures == 0:
        print("NOV_MAP_PROJECTION_SMOKE_OK cases=12 no_world_mutation=true")
        quit(0)
    else:
        quit(1)
