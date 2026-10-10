extends SceneTree
# Synthetic boundary contracts, separate from the physical experiment.
var count:=0
var failures:=0
func allowed(point:Vector3)->Dictionary:return {"allowed":true,"position":point}
func denied(point:Vector3)->Dictionary:return {"allowed":false,"position":point}
func check(ok:bool,label:String)->void:
    if not ok:push_error(label);failures+=1
    count+=1
func sight(stamp:int,world:String="w",source:String="local_physics_eye_sensor")->Dictionary:
    return {"schema":"live-infinita-nov-visual-observation/v1","source":source,"observer_entity_id":"nov","world_write_authority":false,"absence_claim":false,"logical_time_ms":stamp,"world_id":world,
        "visible_entities":[{"entity_id":world+":rabbit:1","kind":"rabbit","evidence":"eye_ray_unobstructed","observed_position_m":[10,0,0]}]}
func fact(now:int=2000)->Dictionary:
    return {"id":"w:animal-approach:test:1","entity_id":"w:rabbit:1","world_id":"w","ended_ms":now,"result":"contact_lost","censored":false,"capture":false,"world_write_authority":false}
func seeded(stamp:int=0):
    var search=load("res://nov_animal_contact_search.gd").new();search.observe(sight(stamp));return search
func _initialize()->void:
    var s=seeded()
    check(s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed")),"valid seed")
    check(not s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed")),"pending search must block another")
    check(not s.choose(Vector3(7,0,0),"w",2100).is_empty() and s.result.is_empty(),"reaching hypothetical goal must not assert reacquisition")
    s.observe(sight(2200,"w","untrusted"))
    check(not s.choose(Vector3(7,0,0),"w",2200).is_empty(),"invalid observation must not reacquire")
    s.observe(sight(2300,"other"))
    check(not s.choose(Vector3(7,0,0),"w",2300).is_empty(),"other world must not reacquire")
    s.observe(sight(2400))
    check(s.choose(Vector3(7,0,0),"w",2400).is_empty() and s.result.result=="reacquired","fresh same-target sight required")
    check(not s.result.approach_confirmed and not s.result.learning_eligible,"reacquisition is not approach success")
    check(not s.begin(fact(2400),Vector3.ZERO,2400,Callable(self,"allowed")),"same attempt must not launch twice")
    s=seeded(3000)
    check(not s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed")),"future seed rejected")
    s=seeded()
    check(not s.begin(fact(7000),Vector3.ZERO,7000,Callable(self,"allowed")),"stale seed rejected")
    check(not s.begin(fact(),Vector3.ZERO,2000,Callable(self,"denied")),"terrain rejection")
    check(s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed")),"budget setup")
    check(s.choose(Vector3.ZERO,"w",7000).is_empty() and s.result.result=="search_budget_exhausted","time budget")
    s=seeded();s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed"))
    check(s.choose(Vector3(13,0,0),"w",2100).is_empty() and s.result.result=="search_budget_exhausted","distance budget")
    s=seeded();s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed"))
    check(s.choose(Vector3.ZERO,"w",1999).is_empty() and s.result.result=="invalid_context","clock rewind")
    s=seeded();s.begin(fact(),Vector3.ZERO,2000,Callable(self,"allowed"))
    check(s.choose(Vector3.ZERO,"other",2100).is_empty() and s.result.result=="invalid_context","world change")
    s=seeded()
    var all_allowed:=true
    for i in range(32):
        var now:=2000+i*300000
        s.observe(sight(now-1600))
        var row:=fact(now);row.id="w:animal-approach:quota:"+str(i)
        all_allowed=all_allowed and s.begin(row,Vector3.ZERO,now,Callable(self,"allowed"))
        s.choose(Vector3.ZERO,"other",now)
    check(all_allowed,"32 bounded distinct launches")
    var extra:=fact(9602000);extra.id="w:animal-approach:quota:extra"
    check(not s.begin(extra,Vector3.ZERO,9602000,Callable(self,"allowed")),"process quota must not evict ids and reopen old attempts")
    print("008FO_CONTRACT_PASS checks="+str(count));quit(1 if failures else 0)
