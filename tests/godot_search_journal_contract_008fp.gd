extends SceneTree
var failures:=0
var checks:=0
func check(ok:bool,label:String)->void:
    checks+=1
    if not ok:failures+=1;push_error(label)
func active(i:int,now:int=400000)->Dictionary:return {"world_id":"w","entity_id":"w:rabbit:1","approach_id":"w:animal-approach:journal:"+str(i),"started_ms":now,"seed_observed_ms":now-1600}
func _initialize()->void:
    var path:=OS.get_environment("LIVE_INFINITA_TEST_SEARCH_JOURNAL")
    var j=load("res://nov_contact_search_journal.gd").new();j.configure(path)
    check(j.ready,"writable empty checkpoint")
    check(j.reserve(active(0)),"reserve before motion")
    check(not j.reserve(active(1)),"pending blocks another")
    var cold=load("res://nov_contact_search_journal.gd").new();cold.configure(path)
    check(cold.ready and cold.pending.is_empty() and cold.records.size()==1,"cold archives pending")
    check(cold.records[0].result=="renderer_restart" and cold.records[0].ended_ms==null and cold.records[0].distance_m==null,"restart cannot fabricate outcome")
    check(not cold.reserve(active(0)),"duplicate after restart")
    for i in range(1,4):
        check(cold.reserve(active(i,400000+i*100)),"start within quota")
        var row=cold.pending.duplicate(true);row.result="search_budget_exhausted";row.ended_ms=row.started_ms+50;row.distance_m=1.0
        var wrong:Dictionary=row.duplicate(true);wrong.entity_id="w:rabbit:2"
        check(not cold.settle(wrong),"mismatched settlement")
        check(cold.settle(row),"measured settlement")
    check(not cold.reserve(active(4,400500)),"four starts including restart exhaust budget")
    var again=load("res://nov_contact_search_journal.gd").new();again.configure(path)
    check(again.ready and again.records.size()==4 and not again.reserve(active(4,400600)),"budget survives completed cold load")
    check(not again.reserve(active(5,399000)),"clock rewind")
    check(again.reserve(active(5,600000)),"new logical epoch")
    var broken=load("res://nov_contact_search_journal.gd").new();broken.configure(path+"/missing/journal")
    check(not broken.ready and not broken.reserve(active(8,600100)),"write failure blocks start")
    var f:=FileAccess.open(path,FileAccess.WRITE);f.store_string("{\"payload\":\"{}\",\"sha256\":\"wrong\"}");f.close()
    broken=load("res://nov_contact_search_journal.gd").new();broken.configure(path)
    check(not broken.ready and not broken.reserve(active(9,600200)),"corruption blocks start")
    print("008FP_JOURNAL_CONTRACT_PASS checks="+str(checks));quit(1 if failures else 0)
