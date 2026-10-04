extends SceneTree
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:
        push_error(label)
        failures += 1
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var holder := Node3D.new()
    root.add_child(holder)
    var assets = load("res://world_map_perceptual_assets.gd").new(holder,func(_x,_z):return 0.0,func(_x,_z):return true,func(_v):return 0,512.0)
    var collision = load("res://nature_batch_collision.gd")
    var motion = load("res://world_map_local_motion.gd").new(func(_x,_z):return 0.0)
    var index := 0
    for path in [assets.COMMON_TREE,assets.PINE_TREE,assets.COMMON_TREE_MID,assets.PINE_TREE_MID,assets.ROCK,assets.BUSH]:
        var mesh: Mesh = assets._asset_mesh(path)
        check(mesh!=null,"Imported asset must be available")
        if mesh==null: continue
        var batch: MultiMeshInstance3D = assets._batch("CollisionFixture",mesh,1)
        var x := -100.0-float(index)*10.0
        batch.multimesh.set_instance_transform(0,Transform3D(Basis.IDENTITY,Vector3(x,0,0)))
        batch.multimesh.visible_instance_count = 1
        collision.sync(batch,[Transform3D(Basis.IDENTITY,Vector3(x,0,0))],index<4)
        await physics_frame
        await physics_frame
        var container = batch.get_node("PhysicalInstances")
        check(container.get_child(0).global_position.distance_to(Vector3(x,0,0))<0.001,"Collider must use the generated position immediately")
        var policy: Dictionary = motion._traversability.validate_step(Vector3(x-2,0,0),Vector3(x,0,0),holder.get_world_3d().direct_space_state)
        print("Nature asset ",path.get_file()," bounds=",mesh.get_aabb()," blocked=",not policy.allowed)
        check(not policy.allowed,"Visible tree/rock must block a capsule at ground level: "+path.get_file())
        index += 1
    var first: MultiMeshInstance3D = holder.get_child(0)
    first.multimesh.set_instance_transform(0,Transform3D(Basis.IDENTITY,Vector3(-100,0,8)))
    collision.sync(first,[Transform3D(Basis.IDENTITY,Vector3(-100,0,8))],true)
    await physics_frame
    await physics_frame
    var space := holder.get_world_3d().direct_space_state
    check(motion._traversability.validate_step(Vector3(-102,0,0),Vector3(-100,0,0),space).allowed,"Relocated instance cannot leave a collider at its former position")
    check(not motion._traversability.validate_step(Vector3(-102,0,8),Vector3(-100,0,8),space).allowed,"Relocated instance must block at its new position")
    first.multimesh.set_instance_transform(0,Transform3D(Basis.IDENTITY,Vector3(-100,0,0)))
    collision.sync(first,[Transform3D(Basis.IDENTITY,Vector3(-100,0,0))],true)
    await physics_frame
    await physics_frame
    motion._experience = load("res://nov_navigation_experience.gd").new("")
    var body: CharacterBody3D = motion.create_body(holder,null)
    await physics_frame
    var position := Vector3(-104,0,0)
    var goal := Vector3(-96,0,0)
    var reached := false
    var overlaps := 0
    var collisions := 0
    for tick in range(1500):
        var result: Dictionary = motion.advance(position,Vector2.ZERO,goal,0.1,body,space,true,4.0)
        position = result.get("position",position)
        collisions += int(result.get("collisions",0))
        if Vector2(position.x+100,position.z).length()<0.8: overlaps += 1
        if result.get("reached",false):
            reached = true
            break
    check(reached and motion._experience.anticipated_avoidances>0,"Nov must physically reach the opposite side by anticipating a real imported tree")
    check(overlaps==0 and collisions==0,"Automatic navigation must not pass through the imported trunk")
    print("Imported tree detour reached=",reached," overlaps=",overlaps," collisions=",collisions)
    collision.sync(first,[],true)
    await physics_frame
    await physics_frame
    check(motion._traversability.validate_step(Vector3(-102,0,0),Vector3(-100,0,0),space).allowed,"Removed instances must disable their old collision shapes")
    holder.queue_free()
    await process_frame
    var stage = load("res://world_map_preview.tscn").instantiate()
    root.add_child(stage)
    await process_frame
    stage.set_process(false)
    for name in ["DistantTreeTrunks","MidgroundVegetation","PerceptualTreeTrunks","PerceptualUndergrowth"]:
        var batch: MultiMeshInstance3D = stage.get_node_or_null(name)
        check(batch!=null,"Live nature layer must be materialized: "+name)
        if batch==null:continue
        var physical = batch.get_node_or_null("PhysicalInstances")
        check(physical!=null,"Live solid layer must synchronize collision bodies: "+name)
        if physical!=null:
            check(physical.get_child_count()>=batch.multimesh.visible_instance_count,"Every visible solid instance has a collision body: "+name)
    stage.queue_free()
    await process_frame
    print("Nature collision smoke: ",failures," failures")
    quit(1 if failures else 0)
