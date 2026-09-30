extends RefCounted
# Authoritative world packets -> explicitly authored visual coordinates.
# Read-only projection: returns a Vector2, never mutates source or world.
const SCHEMA := "live-infinita-nov-visual-projection/v1"
var config: Dictionary = {}
var last_sequence := -1

func _init(mapping: Dictionary) -> void:
    config = mapping.duplicate(true)

func _reject(reason: String) -> Dictionary:
    return {"ok": false, "reason": reason}

func _valid_number(value: Variant) -> bool:
    if typeof(value) not in [TYPE_INT, TYPE_FLOAT]:
        return false
    var number := float(value)
    return not is_nan(number) and not is_inf(number) and absf(number) < 1000000.0

func project(message: Dictionary) -> Dictionary:
    if config.get("schema") != SCHEMA or config.get("preview_only") != true:
        return _reject("config_invalid")
    if message.get("type") != "world_state":
        return _reject("non_world_event")
    var world = message.get("world")
    var delivery = message.get("delivery")
    if typeof(world) != TYPE_DICTIONARY or typeof(delivery) != TYPE_DICTIONARY:
        return _reject("missing_world_delivery")
    if str(world.get("world_id", "")) != str(config.get("world_id", "")):
        return _reject("world_mismatch")
    if str(delivery.get("mode", "")) != "local_world_slice":
        return _reject("not_local_slice")
    if str(delivery.get("observer_entity_id", "")) != str(config.get("observer_entity_id", "")):
        return _reject("observer_mismatch")
    var sequence = world.get("sequence")
    if not _valid_number(sequence) or float(sequence) != floorf(float(sequence)):
        return _reject("sequence_invalid")
    if int(sequence) <= last_sequence:
        return _reject("stale_sequence")
    var interest = world.get("interest")
    if typeof(interest) != TYPE_DICTIONARY:
        return _reject("missing_interest")
    var region_id := str(interest.get("current_region_id", ""))
    var anchors = config.get("anchors")
    if typeof(anchors) != TYPE_DICTIONARY or not anchors.has(region_id):
        return _reject("region_unmapped")
    var entry = anchors[region_id]
    if typeof(entry) != TYPE_DICTIONARY:
        return _reject("anchor_invalid")
    var center = entry.get("world_center")
    var cell = entry.get("map_cell")
    if typeof(center) != TYPE_ARRAY or center.size() != 2 or typeof(cell) != TYPE_ARRAY or cell.size() != 2:
        return _reject("anchor_shape")
    if not _valid_number(center[0]) or not _valid_number(center[1]):
        return _reject("center_invalid")
    if not _valid_number(cell[0]) or not _valid_number(cell[1]):
        return _reject("cell_invalid")
    if float(cell[0]) != floorf(float(cell[0])) or float(cell[1]) != floorf(float(cell[1])):
        return _reject("fractional_cell")
    var grid := int(config.get("map_grid_size", 0))
    var tile := float(config.get("tile_size_m", 0.0))
    var scale := float(config.get("scale_m_per_world_unit", 0.0))
    var limit := float(config.get("max_world_offset", 0.0))
    if grid != 16 or tile != 64.0 or scale <= 0.0 or scale > 2.0 or limit <= 0.0:
        return _reject("projection_invalid")
    if int(cell[0]) < 0 or int(cell[1]) < 0 or int(cell[0]) >= grid or int(cell[1]) >= grid:
        return _reject("cell_out_of_bounds")
    var observer = delivery.get("observer")
    if typeof(observer) != TYPE_DICTIONARY:
        return _reject("observer_missing")
    if not _valid_number(observer.get("x")) or not _valid_number(observer.get("y")):
        return _reject("observer_invalid")
    var offset := Vector2(float(observer["x"]) - float(center[0]), float(observer["y"]) - float(center[1]))
    if offset.length() > limit:
        return _reject("observer_outside_anchor")
    var half := float(grid) * tile * 0.5
    var visual := Vector2((float(cell[0]) + 0.5) * tile - half,
                          (float(cell[1]) + 0.5) * tile - half) + offset * scale
    if absf(visual.x) >= half or absf(visual.y) >= half:
        return _reject("projection_out_of_bounds")
    last_sequence = int(sequence)
    return {"ok": true, "position": visual, "region_id": region_id,
            "sequence": last_sequence, "preview_only": true}
