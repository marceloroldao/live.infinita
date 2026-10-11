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
var _motion_speed := 0.0
var _walk_blend := 0.0
var _gait_phase := 0.0
var _idle_time := 0.0
const LANDING_SECONDS := 0.24
const FALL_REFERENCE_MPS := 8.0
var _grounded := true
var _fall_blend := 0.0
var _fall_speed_peak := 0.0
var _landing_strength := 0.0
var _landing_elapsed := LANDING_SECONDS
var _landing_blend := 0.0
var _rest_positions: Dictionary = {}

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
    if action not in ["idle", "walk", "run", "interact", "fall"]:
        action = "idle"
    desired_action = action
    _visual_heading = heading_radians
    _apply_action()

func _apply_action() -> void:
    if not rig_motion_ready or _player == null:
        return
    var sem = _catalog.get("semantic_clips", {})
    if typeof(sem) != TYPE_DICTIONARY:
        return
    var clip := str(sem.get(desired_action, ""))
    # A missing verified fall clip must not keep a walking clip running in air.
    if desired_action == "fall" and (clip.is_empty() or not _player.has_animation(clip)):
        _player.pause()
        return
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
        "grounded": _grounded,
        "motion_phase": "falling" if not _grounded else ("landing" if _landing_elapsed < LANDING_SECONDS and _landing_strength > 0.0 else desired_action),
        "landing_blend": _landing_blend,
        "motion_speed_mps": _motion_speed,
        "support_source": "local_physics",
        "writes_world_state": false,
    }

func set_motion_velocity(velocity: Vector3, relative_heading: float = 0.0, grounded: bool = true) -> void:
    if not velocity.is_finite():velocity=Vector3.ZERO
    if not is_finite(relative_heading):relative_heading=_visual_heading
    _motion_speed = Vector2(velocity.x, velocity.z).length()
    if not grounded:
        _fall_speed_peak=maxf(_fall_speed_peak,maxf(-velocity.y,0.0))
        _landing_elapsed=LANDING_SECONDS
        _landing_strength=0.0
        _landing_blend=0.0
    elif not _grounded:
        # One visual pulse per real support transition, bounded by observed fall speed.
        _landing_strength=clampf(_fall_speed_peak/FALL_REFERENCE_MPS,0.0,1.0)
        _landing_elapsed=0.0
        _fall_speed_peak=0.0
    _grounded=grounded
    apply_visual_intent("fall" if not grounded else ("walk" if _motion_speed > 0.08 else "idle"), relative_heading)
    if _player != null and rig_motion_ready:
        _player.speed_scale = clampf(_motion_speed / 3.0, 0.45, 1.8) if desired_action == "walk" else 1.0

func _process(delta: float) -> void:
    var dt := clampf(delta, 0.0, 0.1)
    _idle_time += dt
    _fall_blend=move_toward(_fall_blend,0.0 if _grounded else 1.0,dt*10.0)
    _landing_elapsed=minf(LANDING_SECONDS,_landing_elapsed+dt)
    _landing_blend=sin(PI*_landing_elapsed/LANDING_SECONDS)*_landing_strength if _landing_elapsed<LANDING_SECONDS else 0.0
    rotation.y = lerp_angle(rotation.y, _visual_heading, 1.0 - exp(-dt * 8.0))
    var moving := _grounded and desired_action in ["walk", "run"]
    var speed := _motion_speed if _motion_speed > 0.0 else (3.0 if moving else 0.0)
    _walk_blend = move_toward(_walk_blend, clampf(speed / 3.0, 0.0, 1.0) if moving else 0.0, dt * 5.0)
    # Phase follows distance traveled; stopped feet settle instead of skating.
    if moving:
        _gait_phase = fmod(_gait_phase + dt * speed * TAU / 2.4, TAU)
    if model_loaded:
        return
    var stride := sin(_gait_phase) * _walk_blend
    for part_name in ["ArmL", "ArmR", "LegL", "LegR", "Torso", "Head", "Hair", "PrimitiveWrap"]:
        var part := get_node_or_null(part_name) as Node3D
        if part == null:
            continue
        if not _rest_positions.has(part_name):
            _rest_positions[part_name] = part.position
        var rest: Vector3 = _rest_positions[part_name]
        var side := -1.0 if part_name.ends_with("L") else 1.0
        part.position = rest
        if part_name.begins_with("Leg"):
            part.rotation.x = stride * side * 0.48 + _fall_blend * 0.25
            part.position.z += stride * side * 0.08
            part.position.y += maxf(0.0, stride * side) * 0.06
        elif part_name.begins_with("Arm"):
            part.rotation.x = -stride * side * 0.38 - _fall_blend * 0.45 + _landing_blend * 0.12
        else:
            var breath := sin(_idle_time * 1.8) * 0.008 * (1.0 - _walk_blend)
            part.position.y += breath + absf(stride) * 0.018 - _landing_blend * 0.055
            if part_name == "Torso":
                part.rotation.z = stride * 0.025
                part.rotation.x = _fall_blend * 0.08 + _landing_blend * 0.10
