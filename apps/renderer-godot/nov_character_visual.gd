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

func _part_material(color: Color) -> StandardMaterial3D:
    var material := StandardMaterial3D.new()
    material.albedo_color = color
    material.roughness = 1.0
    material.metallic = 0.0
    material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
    return material

func _part(name: String, mesh: Mesh, position: Vector3, color: Color) -> MeshInstance3D:
    var part := MeshInstance3D.new()
    part.name = name
    part.mesh = mesh
    part.position = position
    part.material_override = _part_material(color)
    add_child(part)
    return part

func _placeholder() -> void:
    # Presentation-only primitive humanoid. Replaced automatically when the
    # verified Quaternius body catalog is installed.
    var skin := Color("#b98b68")
    var hide := Color("#5a3b26")
    var cloth := Color("#3f4a35")

    var torso_mesh := CylinderMesh.new()
    torso_mesh.top_radius = 0.27
    torso_mesh.bottom_radius = 0.36
    torso_mesh.height = 0.78
    torso_mesh.radial_segments = 6
    torso_mesh.rings = 1
    _part("Torso", torso_mesh, Vector3(0.0, 0.24, 0.0), hide)

    var head_mesh := SphereMesh.new()
    head_mesh.radius = 0.22
    head_mesh.height = 0.44
    head_mesh.radial_segments = 8
    head_mesh.rings = 4
    _part("Head", head_mesh, Vector3(0.0, 0.88, 0.0), skin)

    var hip_mesh := CylinderMesh.new()
    hip_mesh.top_radius = 0.31
    hip_mesh.bottom_radius = 0.34
    hip_mesh.height = 0.28
    hip_mesh.radial_segments = 6
    hip_mesh.rings = 1
    _part("PrimitiveWrap", hip_mesh, Vector3(0.0, -0.18, 0.0), cloth)

    for side in [-1.0, 1.0]:
        var arm_mesh := CapsuleMesh.new()
        arm_mesh.radius = 0.09
        arm_mesh.height = 0.68
        arm_mesh.radial_segments = 6
        arm_mesh.rings = 2
        var arm := _part(
            "ArmL" if side < 0.0 else "ArmR",
            arm_mesh,
            Vector3(side * 0.39, 0.25, 0.0),
            skin
        )
        arm.rotation.z = side * 0.10

        var leg_mesh := CapsuleMesh.new()
        leg_mesh.radius = 0.11
        leg_mesh.height = 0.78
        leg_mesh.radial_segments = 6
        leg_mesh.rings = 2
        _part(
            "LegL" if side < 0.0 else "LegR",
            leg_mesh,
            Vector3(side * 0.17, -0.62, 0.0),
            hide
        )

    var hair_mesh := SphereMesh.new()
    hair_mesh.radius = 0.225
    hair_mesh.height = 0.30
    hair_mesh.radial_segments = 8
    hair_mesh.rings = 3
    var hair := _part("Hair", hair_mesh, Vector3(0.0, 1.00, 0.03), Color("#2b211a"))
    hair.scale = Vector3(1.02, 0.70, 1.02)

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
