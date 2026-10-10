extends "godot_approach_full_motion_008fg.gd"
var fixture_path:=""
func _initialize()->void:
    fixture_path="/tmp/native-context-"+Crypto.new().generate_random_bytes(8).hex_encode()
    OS.set_environment("LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE",fixture_path)
    OS.set_environment("LIVE_INFINITA_APPROACH_TEST_CLOCK","100000")
    OS.set_environment("LIVE_INFINITA_APPROACH_TEST_TARGET","perception")
    OS.set_environment("LIVE_INFINITA_APPROACH_TEST_REVERSE","0")
    OS.set_environment("LIVE_INFINITA_APPROACH_TEST_HIDDEN","1")
    call_deferred("run")
func check(value:bool,label:String)->void:
    if not value:push_error(label);failures+=1
func verify_context_checkpoint(approach:RefCounted)->void:
    var history=load("res://nov_animal_context_history.gd").new()
    history.configure(fixture_path+".context")
    check(history.ready and history.records.size()==1,"Native context outcome survives cold reload")
    check(history.records[0].approach.id==approach._context_history.records[0].approach.id,"Cold context preserves actual attempt identity")
    check(history.records[0].context.profile=="capsule044-height18-sweep4-native-contour-v1","Native navigation has distinct locomotion profile")
    check(not history.record(history.records[0]),"Duplicate context rejected")
    check(not history.status().decision_use,"Collection does not claim changed decision")
    var wrong:Dictionary=history.records[0].duplicate(true)
    wrong.context.profile="capsule044-height18-sweep4-v1"
    check(not history.valid(wrong),"Direct-motion experience cannot enter native collector")
    wrong=history.records[0].duplicate(true);wrong.approach.censored=true
    check(not history.valid(wrong),"Interrupted result cannot become contextual experience")
    var f:=FileAccess.open(fixture_path+".bad",FileAccess.WRITE)
    f.store_string('{"payload":"changed","sha256":"wrong"}');f.close()
    var bad=load("res://nov_animal_context_history.gd").new();bad.configure(fixture_path+".bad")
    check(not bad.ready,"Checksum corruption disables collection")
    print("008FG_NATIVE_CONTEXT_CONTRACT "+JSON.stringify({"failures":failures,"stored":history.records.size()}))
func run()->void:
    await super.run()
    for suffix in ["",".context",".bad"]:
        if FileAccess.file_exists(fixture_path+suffix):DirAccess.remove_absolute(fixture_path+suffix)
