extends "godot_physical_memory_comparison_008ed.gd"
# Actual capsule/probes/callbacks. Outcomes are created only by the native collector.
var actions: Array=[]
var training_facts: Array[Dictionary]=[]
func box(holder: Node3D, center: Vector3, size: Vector3) -> void:
    var obstacle:=StaticBody3D.new()
    var shape:=CollisionShape3D.new()
    var geometry:=BoxShape3D.new();geometry.size=size;shape.shape=geometry
    obstacle.add_child(shape);holder.add_child(obstacle);obstacle.position=center
func actual_action(action: Dictionary) -> void:
    if actions.size()<3000:actions.append(action.duplicate(true))
func physical_run(holder: Node3D,label: String,experimental: bool) -> Dictionary:
    actions.clear()
    var motion=load("res://world_map_local_motion.gd").new(Callable(self,"flat"),512)
    motion._experience.storage=""
    motion._experience.trial_error_enabled=true
    motion._experience.memoria_enabled=false
    motion._experience.working_memory.storage="";motion._experience.working_memory.enabled=false
    motion._episodes.storage="";motion._episodes.enabled=true
    motion._episodes.set_context({"world_id":"contact-turns-008et","observer_entity_id":"nov"})
    motion._pattern_collector.storage=""
    motion._pattern_collector.local_rows.clear()
    if label.begins_with("exploration_"):
        for row in training_facts:motion._pattern_collector.local_rows.append(row.duplicate(true))
    motion._pattern_collector._rebuild()
    motion._pattern_collector.set_context(motion._episodes.context)
    motion._pattern_collector.set_enabled(true)
    motion._experience.contour.local_turn_continuity_enabled=experimental
    motion._episodes.action_completed.connect(Callable(self,"actual_action"))
    motion.route_goal_id=label
    var body: CharacterBody3D=motion.create_body(holder,null)
    var current:=initial
    var collisions:=0
    var ticks:=0
    var watchdog=load("res://nov_stuck_recovery.gd").new()
    var confined:=false
    for i in range(2500):
        var value: Dictionary=motion.advance(current,Vector2.ZERO,destination,0.1,body,holder.get_world_3d().direct_space_state,true,4)
        current=value.get("position",current);ticks+=1;collisions+=int(value.get("collisions",0))
        if value.get("reached",false):break
        if watchdog.observe(current,destination,0.1,true):confined=true;break
    var arrived:=Vector2(current.x,current.z).distance_to(Vector2(destination.x,destination.z))<0.1
    if not arrived:motion.abort_journey("isolated test bounded stop","interrupted")
    var result: Dictionary={"arm":label,"arrived":arrived,"distance_m":motion._journey.distance_m,
        "ticks":ticks,"simulated_seconds":ticks*0.1,"collisions":collisions,"watchdog_stop":confined,
        "final_position":[current.x,current.z],"route_plan_builds":motion._experience.route_plan_builds,
        "collector":motion._pattern_collector.status(),"facts":motion._pattern_collector.local_rows.duplicate(true),
        "frame":motion._experience.contour.evidence(),"actions":actions.duplicate(true)}
    check(collisions==0 and result.route_plan_builds==0,label+": no collision or global route search")
    if experimental:check(arrived and not confined,label+": continuous contact must finish the physical journey")
    if label.begins_with("exploration_"):check(motion._pattern_collector.exploration_decisions>0,label+": real prior training triggers exploratory decision")
    body.queue_free();return result
func run() -> void:
    var output:=OS.get_environment("LIVE_INFINITA_CONTACT_TURN_OUTPUT")
    var rows: Array=[]
    for geometry in ["open_wall","corner","pocket","wide_corner","wide_pocket","mirrored_pocket","exploration_corner","exploration_pocket"]:
        var holder:=Node3D.new();root.add_child(holder)
        initial=Vector3(-86,0,0);destination=Vector3(-68,0,0)
        var mirrored: bool=geometry=="mirrored_pocket"
        if mirrored:initial=Vector3(-74,0,0);destination=Vector3(-92,0,0)
        var depth:=40.0 if geometry.begins_with("wide_") else 20.0
        var x_center: float=-80.0+depth*0.5 if mirrored else -80.0-depth*0.5
        box(holder,Vector3(-80,2,0),Vector3(0.4,4,60))
        var first_z: float=-30.0 if geometry.begins_with("exploration_") else 30.0
        if geometry!="open_wall":box(holder,Vector3(x_center,2,first_z),Vector3(depth,4,0.4))
        if "pocket" in geometry:box(holder,Vector3(x_center,2,-first_z),Vector3(depth,4,0.4))
        await physics_frame
        for experimental in [false,true]:
            var result: Dictionary=physical_run(holder,geometry+("_continuity" if experimental else "_baseline"),experimental)
            rows.append(result)
            if result.arm=="open_wall_baseline":
                training_facts.clear()
                for row in result.facts:training_facts.append(row.duplicate(true))
            var summary: Dictionary=result.duplicate();summary.erase("actions");summary.erase("facts")
            print("008ET_CONTACT_TURN "+JSON.stringify(summary))
            await physics_frame
        holder.queue_free();await physics_frame
    var file:=FileAccess.open(output,FileAccess.WRITE)
    check(file!=null,"Output writable")
    if file!=null:
        file.store_string(JSON.stringify({"scope":"isolated_actual_capsule_local_turn_comparison",
            "production_change":false,"failures":failures,"runs":rows}));file.close()
    quit(1 if failures else 0)
