extends "godot_animal_approach_008fb_smoke.gd"
var directory := ""
var sequence := 0
func policy():
    if directory.is_empty():
        directory="/tmp/approach-history-"+Crypto.new().generate_random_bytes(8).hex_encode()
        DirAccess.make_dir_recursive_absolute(directory)
    sequence+=1
    var value=load("res://nov_animal_approach.gd").new()
    value.enabled=true
    value.configure(directory+"/"+str(sequence))
    value.choose(Vector3.ZERO,"fixture",100000,Callable(self,"allowed"))
    return value
func verify_persistence(approach: RefCounted) -> void:
    var recovered=load("res://nov_animal_approach.gd").new()
    recovered.enabled=true
    recovered.configure(approach._history.path)
    check(recovered._results.size()==1 and recovered._results[0].id==approach._results[0].id and recovered._results[0].result=="approached" and absf(recovered._results[0].distance_m-approach._results[0].distance_m)<0.000001 and recovered._results[0].started_ms==approach._results[0].started_ms and recovered._results[0].ended_ms==approach._results[0].ended_ms,"Measured physical result survives cold reload")
    check(recovered._history.status().learning_eligible_attempts==1,"Real moved approach eligible for later evaluation")
    check(not recovered._history.status().core_ingestion,"Disk checkpoint does not claim core ingestion")
    check(recovered.choose(Vector3.ZERO,"fixture",100000,Callable(self,"allowed")).is_empty(),"Restored clock waits without fabricating rewind")
    check(recovered.choose(Vector3.ZERO,"fixture",104000,Callable(self,"allowed")).is_empty(),"Cold restart preserves cooldown")
    check(not recovered._history.record(recovered._results[0]),"Duplicate outcome rejected")
    # Contract-only pending checkpoint: never published as a measured hunt.
    var history=load("res://nov_animal_approach_history.gd").new()
    history.configure(directory+"/pending")
    check(history.begin({"id":"fixture:animal-approach:pending","world_id":"fixture","entity_id":"fixture:rabbit:0","started_ms":100000,"initial_observed_remaining_m":10.0}),"Pending intention checkpoint saved")
    var cold=load("res://nov_animal_approach_history.gd").new()
    cold.configure(directory+"/pending")
    check(cold.ready and cold.records.size()==1,"Pending intention recovered once")
    check(cold.records[0].censored and not cold.records[0].learning_eligible and cold.records[0].distance_m==null and cold.records[0].ended_ms==null,"Crash invents no distance or completion")
    var twice=load("res://nov_animal_approach_history.gd").new()
    twice.configure(directory+"/pending")
    check(twice.records.size()==1 and twice.pending.is_empty(),"Second restart does not duplicate interruption")
    var bad=FileAccess.open(directory+"/corrupt",FileAccess.WRITE)
    bad.store_string('{"payload":"changed","sha256":"wrong"}');bad.close()
    var corrupt=load("res://nov_animal_approach_history.gd").new()
    corrupt.configure(directory+"/corrupt")
    check(not corrupt.ready,"Corrupt checksum disables storage")
    var blocked=load("res://nov_animal_approach.gd").new()
    blocked.enabled=true;blocked.configure(directory+"/corrupt")
    check(not blocked.enabled,"Corrupt history disables approach")
    var forged=approach._results[0].duplicate(true);forged.id+="forged";forged.capture=true
    check(not cold.record(forged),"Capture claim rejected")
    for i in range(513):
        var row=cold.records[0].duplicate(true)
        row.id="fixture:animal-approach:retention-"+str(i)
        check(cold.record(row),"Bounded censored contract fixture")
    check(cold.records.size()==512 and cold.status().learning_eligible_attempts==0,"Retention capped without converting interruptions into learning")
    print("008FC_HISTORY_CONTRACT_PASS")
func run() -> void:
    await super.run()
    if not directory.is_empty():
        for file in DirAccess.get_files_at(directory):DirAccess.remove_absolute(directory+"/"+file)
        DirAccess.remove_absolute(directory)
