extends Node3D

# Only visual state belongs here. Never writes World State, positions, needs,
# beliefs, memories, plans or logical simulation time.
const CATALOG_PATH := "res://assets/quaternius/nov_character/catalog.json"
const BODY_PREFIX := "res://assets/quaternius/nov_character/body/"

var model_loaded := false
var rig_motion_ready := false
var desired_action := "idle"
var _catalog: Dictionary = {}
var _body: Node3D
var _player: AnimationPlayer
var _visual_heading := 0.0

func _ready() -> void:
    _load_body()

func _load_body() -> void:
    if not FileAccess.file_exists(CATALOG_PATH):
        _placeholder()
        return
    var raw = JSON.parse_string(FileAccess.get_file_as_string(CATALOG_PATH))
    if typeof(raw) != TYPE_DICTIONARY:
        _placeholder()
        return
    _catalog = raw
    if int(_catalog.get("schema_version", 0)) != 1 or str(_catalog.get("character_id", "")) != "nov":
        _placeholder()
        return
    var path := str(_catalog.get("body_scene", ""))
    if not path.begins_with(BODY_PREFIX) or ".." in path or not path.ends_with(".gltf") and not path.ends_with(".glb"):
        _placeholder()
        return
    if not ResourceLoader.exists(path):
        _placeholder()
        return
    var packed: Resource = load(path)
    if not packed is PackedScene:
        _placeholder()
        return
    var scene: PackedScene = packed as PackedScene
    var spawned: Node = scene.instantiate()
    if not spawned is Node3D:
        spawned.queue_free()
        _placeholder()
        return
    _body = spawned as Node3D
    add_child(_body)
    model_loaded = true
    _player = _find_player(_body)
    # Imported donor clips alone do not prove that retargeting onto this body
    # works. Play only clips that are already installed on the body skeleton.
    rig_motion_ready = bool(_catalog.get("retarget_verified", false)) and _player != null
    _apply_action()

func _find_player(root: Node) -> AnimationPlayer:
    var pending: Array[Node] = [root]
    while not pending.is_empty():
        var node: Node = pending.pop_back()
        if node is AnimationPlayer:
            return node as AnimationPlayer
        for child in node.get_children():
            pending.append(child)
    return null

func _placeholder() -> void:
    var mesh := MeshInstance3D.new()
    var primitive := CapsuleMesh.new()
    primitive.radius = 0.35
    primitive.height = 1.6
    mesh.mesh = primitive
    mesh.position.y = 0.8
    var material := StandardMaterial3D.new()
    material.albedo_color = Color(0.45, 0.54, 0.62)
    mesh.material_override = material
    add_child(mesh)

func apply_visual_intent(action: String, heading_radians: float = 0.0) -> void:
    # Called from the approved world presentation stream; never derives facts.
    if action not in ["idle", "walk", "run", "interact"]:
        action = "idle"
    desired_action = action
    _visual_heading = heading_radians
    rotation.y = _visual_heading
    _apply_action()

func _apply_action() -> void:
    if not rig_motion_ready or _player == null:
        return
    var sem = _catalog.get("semantic_clips", {})
    if typeof(sem) != TYPE_DICTIONARY:
        return
    var clip := str(sem.get(desired_action, ""))
    if not clip.is_empty() and _player.has_animation(clip):
        if _player.current_animation != clip or not _player.is_playing():
            _player.play(clip, 0.15)

func visual_status() -> Dictionary:
    return {
        "character_id": "nov",
        "body_loaded": model_loaded,
        "retarget_verified": rig_motion_ready,
        "donor_animation_imported": not str(_catalog.get("animation_scene", "")).is_empty(),
        "action": desired_action,
        "writes_world_state": false,
    }
