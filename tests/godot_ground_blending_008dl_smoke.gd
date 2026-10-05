extends SceneTree
class GroundPreview:
    extends "res://world_map_preview.gd"
    var changed := false
    func _ready() -> void:pass
    func _proposed_raw_height(x: float,_z: float) -> float:
        return -24.0 if changed and x>=-96.0 else 0.0
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void:call_deferred("run")
func run() -> void:
    var filter = load("res://nov_ground_consolidation.gd").new()
    var known := {Vector2.ZERO:0.0}
    var neighbor: float = filter.sample(Vector2(8,0),-24.0,known)
    check(absf(neighbor+5.2)<0.0001,"A newly proposed 24m drop must blend from the known edge")
    check(filter.sample(Vector2.ZERO,22.0,known)==0.0,"Previously consolidated height must not move")
    var next: float = filter.sample(Vector2(16,0),-24.0,known)
    check(absf(next-neighbor)<=5.20001,"Following new samples must keep bounded grade")
    var diagonal: float = filter.sample(Vector2(8,8),22.0,known)
    check(absf(diagonal-neighbor)<=5.20001,"Diagonal frontier must honor existing side neighbor")
    var incompatible := {Vector2(-8,0):-20.0,Vector2(8,0):20.0}
    var before := incompatible.duplicate()
    filter.sample(Vector2.ZERO,0.0,incompatible)
    check(filter.conflicts==1 and incompatible[Vector2(-8,0)]==before[Vector2(-8,0)] and incompatible[Vector2(8,0)]==before[Vector2(8,0)],"Incompatible old samples must be reported and preserved")
    check(is_finite(filter.sample(Vector2(24,0),NAN,known)),"Invalid proposal must not create invalid ground")

    var preview := GroundPreview.new()
    root.add_child(preview)
    preview._raw_height(-104,0)
    preview._raw_height(-104,8)
    preview.changed = true
    # The real height interpolation and motion both consume the same samples.
    var motion = load("res://world_map_local_motion.gd").new(Callable(preview,"_height"),1024.0)
    motion._experience.storage = ""
    motion._experience.working_memory.storage = ""
    motion._experience.trial_error_enabled = true
    motion._episodes.enabled = false
    var body: CharacterBody3D = motion.create_body(preview,null)
    await physics_frame
    var position := Vector3(-104,preview._height(-104,0),0)
    var goal := Vector3(-80,preview._height(-80,0),0)
    var distance := 0.0
    var reached := false
    for i in range(200):
        var step: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,preview.get_world_3d().direct_space_state,true,4.0)
        var result: Vector3 = step.get("position",position)
        distance += Vector2(result.x-position.x,result.z-position.z).length()
        check(result.is_finite() and int(step.get("collisions",0))==0,"Blended crossing must retain valid physical motion")
        position = result
        if step.get("reached",false):
            reached = true
            break
    check(reached and distance>=23.9 and distance<25.0,"Real motion must cross the blended frontier and return naturally")
    check(preview._raw_height(-104,0)==0.0,"Walking must not change the old floor")

    var layout = load("res://world_map_layout.gd").new(JSON.parse_string(FileAccess.get_file_as_string("res://world_map_001.json")))
    preview._layout = layout
    preview._cognitive_terrain = load("res://world_map_cognitive_terrain.gd").new(preview)
    var left: MeshInstance3D = preview._terrain(14,16,"clearing")
    var right: MeshInstance3D = preview._terrain(15,16,"clearing")
    var lh: PackedFloat32Array = left.get_meta("resident_ground_heights")
    var rh: PackedFloat32Array = right.get_meta("resident_ground_heights")
    for i in range(9):
        check(absf(lh[i*9+8]-rh[i*9])<0.00001,"Rendered neighboring tiles must have identical edges")
    left.free()
    right.free()
    preview.queue_free()
    var natural = load("res://world_map_preview.gd").new()
    var jump: float = absf(natural._proposed_raw_height(175.1,-150)-natural._proposed_raw_height(174.9,-150))
    check(jump<0.1,"Highland boundary must use a smooth transition instead of an abrupt multiplier")
    natural.free()
    await process_frame
    print("Ground blending smoke: ",failures," failures; distance_m=",distance," old_proposal_drop_m=24 new_first_drop_m=",absf(neighbor))
    quit(1 if failures else 0)
