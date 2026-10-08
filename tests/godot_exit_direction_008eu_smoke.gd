extends SceneTree
# Contract tests only; no synthetic outcomes enter memory.
var failures := 0
func check(value: bool,label: String) -> void:
    if not value:push_error(label);failures+=1
func frame(enabled: bool):
    var value=load("res://nov_navigation_contour.gd").new()
    value.exit_direction_enabled=enabled
    value.local_turn_continuity_enabled=true
    var contact: Array[Dictionary]=[{"point":Vector2(0,1),"source":"perception","clear_ahead":true}]
    value.filter(Vector2.ZERO,Vector2(10,0),contact,false)
    return value
func _initialize() -> void:
    var rows: Array[Dictionary]=[
        {"point":Vector2(3,0),"source":"perception","clear_ahead":true},
        {"point":Vector2(4,1),"source":"perception","clear_ahead":true},
        {"point":Vector2(5,0),"source":"perception","clear_ahead":true},
        {"point":Vector2(6,0),"source":"perception","clear_ahead":false}]
    var legacy=frame(false)
    var old: Array[Dictionary]=legacy.filter(Vector2(4,0),Vector2(10,0),rows,true)
    check(old.size()==4 and not legacy.active,"Legacy release allows retreat and lateral candidates")
    var empty_legacy=frame(false)
    var empty_rows: Array[Dictionary]=[]
    empty_legacy.filter(Vector2(4,0),Vector2(10,0),empty_rows,true)
    check(not empty_legacy.active and not empty_legacy.exit_proposal.is_empty(),
        "Disabled policy preserves legacy release even with an empty candidate list")
    var fixed=frame(true)
    var serial: int=fixed.starts
    var selected: Array[Dictionary]=fixed.filter(Vector2(4,0),Vector2(10,0),rows,true)
    check(selected.size()==1 and selected[0].point==Vector2(5,0),"Exit selection requires checked forward physical displacement")
    check(fixed.exit_proposal.contact_serial==serial,"Proposal still identifies the measured contact")
    check(fixed.exit_proposal.normal==[1.0,0.0],"Original exit normal retained for physical collector")
    fixed=frame(true);serial=fixed.starts
    rows=[{"point":Vector2(3,0),"source":"perception","clear_ahead":true},
          {"point":Vector2(4,1),"source":"perception","clear_ahead":true}]
    fixed.filter(Vector2(4,0),Vector2(10,0),rows,true)
    check(fixed.active and fixed.starts==serial,"Without a forward exit, contact remains active")
    check(fixed.exit_proposal.is_empty(),"Clear ray alone grants no completion proposal")
    rows=[{"point":Vector2(4.75,0),"source":"perception","clear_ahead":true}]
    fixed.filter(Vector2(4,0),Vector2(10,0),rows,true)
    check(not fixed.exit_proposal.is_empty(),"Boundary matches existing 0.75 m physical completion threshold")
    var fixture_path: String=get_script().resource_path.get_base_dir().path_join("../docs/EXIT_DIRECTION_008EU/native-counterexample.json")
    check(FileAccess.file_exists(fixture_path),"Archived native counterexample available")
    if FileAccess.file_exists(fixture_path):
        var action=JSON.parse_string(FileAccess.get_file_as_string(fixture_path))
        var proposal: Dictionary=action.perception.contour.exit_proposal
        var start:=Vector2(proposal.start[0],proposal.start[1])
        var normal:=Vector2(proposal.normal[0],proposal.normal[1])
        var goal:=Vector2(action.goal[0],action.goal[1])
        var old_point:=Vector2(action.selected[0],action.selected[1])
        var actual_end:=Vector2(action.end[0],action.end[1])
        check((actual_end-start).dot(normal)<0,"Archived native step actually receded")
        rows=[]
        for sensed in action.perception.candidates:
            if bool(sensed.get("allowed",false)):
                rows.append({"point":Vector2(sensed.point[0],sensed.point[1]),
                    "source":"perception","clear_ahead":bool(sensed.get("clear_ahead",false))})
        fixed=frame(true);fixed.normal=normal;fixed.origin=start-normal*3.0
        var replay: Array[Dictionary]=fixed.filter(start,goal,rows,true)
        var old_allowed:=false
        for candidate in replay:
            if Vector2(candidate.point).distance_to(old_point)<0.001:old_allowed=true
        check(fixed.exit_proposal.is_empty() or not old_allowed,
            "Recorded receding choice cannot be proposed as an exit")
        for candidate in replay:
            if not fixed.exit_proposal.is_empty():
                check((Vector2(candidate.point)-start).dot(normal)>=0.75,
                    "Every replayed exit candidate meets the physical direction gate")
    print("008EU exit direction contract: ",failures," failures; no memory ingestion")
    quit(1 if failures else 0)
