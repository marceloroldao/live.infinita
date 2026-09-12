extends Node2D

var entity_id: String = ""
var entity_type: String = ""
var entity_data: Dictionary = {}
var data_signature: String = ""

func apply_entity(next_entity: Dictionary) -> bool:
    var next_signature := JSON.stringify(next_entity)
    if next_signature == data_signature:
        return false

    entity_data = next_entity.duplicate(true)
    entity_id = str(entity_data.get("id", ""))
    entity_type = str(entity_data.get("type", ""))
    data_signature = next_signature

    var p_data = entity_data.get("position", {})
    position = Vector2(float(p_data.get("x", 0)), float(p_data.get("y", 0)))
    queue_redraw()
    return true

func _draw() -> void:
    var scale_value := float(entity_data.get("scale", 1.0))
    match entity_type:
        "tree":
            draw_rect(Rect2(-13 * scale_value, 0, 26 * scale_value, 95 * scale_value), Color("#6c4428"), true)
            draw_circle(Vector2(0, -8), 60 * scale_value, Color("#286542"))
            draw_circle(Vector2(-35, 18), 42 * scale_value, Color("#347d4d"))
            draw_circle(Vector2(34, 18), 42 * scale_value, Color("#347d4d"))
        "campfire":
            draw_line(Vector2(-25, 20), Vector2(25, -12), Color("#6d4b31"), 9)
            draw_line(Vector2(-25, -12), Vector2(25, 20), Color("#6d4b31"), 9)
            if bool(entity_data.get("properties", {}).get("lit", false)):
                draw_circle(Vector2(0, -12), 31, Color("#ff7c2d"))
                draw_circle(Vector2(0, -20), 19, Color("#ffd24a"))
        "human":
            draw_circle(Vector2(0, -42), 15 * scale_value, Color("#f0c7a0"))
            draw_line(Vector2(0, -27), Vector2(0, 22), Color("#384d88"), 15 * scale_value)
            draw_line(Vector2(0, -4), Vector2(-22, 12), Color("#384d88"), 8 * scale_value)
            draw_line(Vector2(0, -4), Vector2(22, 12), Color("#384d88"), 8 * scale_value)
            draw_line(Vector2(0, 20), Vector2(-15, 50), Color("#26304e"), 8 * scale_value)
            draw_line(Vector2(0, 20), Vector2(15, 50), Color("#26304e"), 8 * scale_value)
        _:
            draw_circle(Vector2.ZERO, 12 * scale_value, Color("#dddddd"))
