extends SceneTree
var checks:=0
var failures:=0
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:failures+=1;push_error(label)
func _initialize()->void:call_deferred("run")
func run()->void:
    var visual=load("res://nov_character_visual.gd").new()
    var parent:=CharacterBody3D.new();root.add_child(parent);parent.add_child(visual)
    visual.set_process(false)
    var parent_pose:Transform3D=parent.transform
    visual.set_motion_velocity(Vector3.ZERO,0,true);visual._process(.05)
    check(visual._landing_strength==0.0 and visual._landing_blend==0.0,"Initial support never fabricates a landing")
    visual.set_motion_velocity(Vector3(3,0,0),1,true);visual._process(.1)
    var phase:float=visual._gait_phase
    visual.set_motion_velocity(Vector3(2,-4,0),1,false)
    for _i in range(4):visual._process(.1)
    check(visual.desired_action=="fall" and not visual.visual_status().grounded,"Physical support selects falling despite horizontal motion")
    check(is_equal_approx(visual._gait_phase,phase) and visual._walk_blend==0.0,"Airborne body stops walking cadence")
    check(visual.get_node("ArmL").rotation.x<0.0 and visual.get_node("LegL").rotation.x>0.0,"Primitive body assumes a distinct fall pose")
    visual.set_motion_velocity(Vector3.ZERO,1,true);visual._process(.05)
    check(visual.visual_status().motion_phase=="landing" and visual._landing_blend>0.0,"Support transition starts visual landing pulse")
    var elapsed:float=visual._landing_elapsed
    visual.set_motion_velocity(Vector3.ZERO,1,true)
    check(visual._landing_elapsed==elapsed,"Repeated supported frames never retrigger landing")
    for _i in range(8):visual._process(.05)
    check(visual._landing_blend==0.0 and visual._fall_blend==0.0 and visual.desired_action=="idle","Landing settles within its bounded duration")
    check(parent.transform==parent_pose and parent.velocity==Vector3.ZERO,"Visual response cannot displace or accelerate physical capsule")
    check(not visual.visual_status().writes_world_state,"Visual response has no World State authority")
    visual.set_motion_velocity(Vector3(0,2,0),1,false);visual.set_motion_velocity(Vector3.ZERO,1,true)
    check(visual._landing_strength==0.0,"Upward-only observation fabricates no fall impact")
    visual.set_motion_velocity(Vector3(NAN,0,0),NAN,true);visual._process(.1)
    check(is_finite(visual.rotation.y) and visual._motion_speed==0.0,"Invalid velocity and heading remain bounded")
    for fps in [15,30,60]:
        visual.set_motion_velocity(Vector3(0,-4,0),1,false)
        for _i in range(ceili(.3*fps)):visual._process(1.0/fps)
        visual.set_motion_velocity(Vector3.ZERO,1,true)
        var peak:=0.0
        for _i in range(ceili(.4*fps)):
            visual.set_motion_velocity(Vector3.ZERO,1,true);visual._process(1.0/fps)
            peak=maxf(peak,visual._landing_blend)
        check(absf(peak-.5)<.025 and visual._landing_blend==0.0,"Bounded landing response at "+str(fps)+" FPS")
        print("008FV_LANDING fps=",fps," peak=",peak)
    visual.set_motion_velocity(Vector3(0,-100,0),1,false);visual.set_motion_velocity(Vector3.ZERO,1,true)
    check(visual._landing_strength==1.0,"Landing strength caps at one even for an extreme observation")
    # Verified rigs without a fall clip must pause instead of walking in air.
    var player:=AnimationPlayer.new();visual.add_child(player)
    var library:=AnimationLibrary.new()
    for name in ["Walk","Idle"]:
        var clip:=Animation.new();clip.length=1.0;library.add_animation(name,clip)
    player.add_animation_library("",library)
    visual._player=player;visual.rig_motion_ready=true
    visual._catalog={"semantic_clips":{"walk":"Walk","idle":"Idle"}}
    visual.set_motion_velocity(Vector3(3,0,0),1,true)
    check(player.is_playing() and player.current_animation=="Walk","Verified supported rig plays walking")
    visual.set_motion_velocity(Vector3(3,-2,0),1,false)
    check(not player.is_playing(),"Missing verified fall clip pauses walking in air")
    visual.set_motion_velocity(Vector3(3,0,0),1,true)
    check(player.is_playing() and player.current_animation=="Walk","Verified rig resumes walking on support")
    parent.queue_free();await process_frame
    # Real scene and real gravity supply support; vertical displacement alone does not infer it.
    var stage=load("res://world_map_preview.tscn").instantiate();root.add_child(stage)
    stage.set_process(false);stage.set_physics_process(false)
    var body:CharacterBody3D=stage._walker
    var nov=body.get_node("NovVisual");nov.set_process(false)
    stage._local_motion.gravity_enabled=true
    var ground:Vector3=stage._position
    stage._position=ground+Vector3(0,.6,0)
    stage._local_motion.snap_body(body,stage._position)
    var start:Vector3=stage._position
    var result:Dictionary=stage._local_motion.advance_gravity(start,1.0/60.0,body)
    stage._position=result.position;stage._animate_nov_movement(start,1.0/60.0);nov._process(1.0/60.0)
    check(not result.grounded and nov.desired_action=="fall","Scene forwards actual airborne support to the visual")
    for _i in range(90):
        var before:Vector3=stage._position
        result=stage._local_motion.advance_gravity(before,1.0/60.0,body)
        stage._position=result.position;stage._animate_nov_movement(before,1.0/60.0);nov._process(1.0/60.0)
        if result.grounded:break
    check(result.grounded and nov.visual_status().motion_phase=="landing","Actual physical landing triggers the scene transition")
    var landed:Transform3D=body.transform
    for _i in range(20):nov._process(.02)
    check(body.transform==landed and nov._landing_blend==0.0,"Landing presentation settles without altering physical ground contact")
    stage._local_motion.gravity_enabled=false
    stage._animate_nov_movement(stage._position+Vector3(0,1,0),.1)
    check(nov.desired_action=="idle" and nov.visual_status().grounded,"Vertical terrain correction without gravity is not a fall")
    stage.queue_free();await process_frame
    print("008FV_AIRBORNE_PRESENTATION checks=",checks," failures=",failures)
    quit(1 if failures else 0)
