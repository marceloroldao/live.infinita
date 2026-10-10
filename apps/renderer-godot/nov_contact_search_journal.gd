extends RefCounted
# Single renderer process. Execution journal, never a learning-core fact source.
const SCHEMA:="live-infinita-contact-search-journal/v1"
const EPOCH_MS:=300000
const LIMIT:=64
var path:=""
var guard_path:=""
var ready:=true
var records:Array=[]
var pending:Dictionary={}
var clocks:Dictionary={}
func number(v:Variant)->bool:return typeof(v) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(v)) and float(v)>=0 and float(v)<=1e15
func valid(row:Variant)->bool:
    if typeof(row)!=TYPE_DICTIONARY or row.size()!=15:return false
    for field in ["approach_id","entity_id","world_id","result"]:
        if typeof(row.get(field))!=TYPE_STRING or row[field].is_empty() or row[field].length()>240:return false
    if not row.approach_id.begins_with(row.world_id+":animal-approach:") or not row.entity_id.begins_with(row.world_id+":rabbit:"):return false
    if row.result not in ["reserved","renderer_restart","reacquired","search_budget_exhausted","invalid_context"]:return false
    if not number(row.get("started_ms")) or row.started_ms!=floorf(row.started_ms) or not number(row.get("seed_observed_ms")) or row.seed_observed_ms>row.started_ms:return false
    for flag in ["capture","absence_claim","approach_confirmed","learning_eligible","world_write_authority"]:
        if row.get(flag)!=false:return false
    if row.result in ["reserved","renderer_restart"]:
        return row.get("ended_ms")==null and row.get("distance_m")==null and row.get("reacquired_observed_ms")==null and row.get("observed_position_m")==null
    if not number(row.get("ended_ms")) or row.ended_ms<row.started_ms or not number(row.get("distance_m")):return false
    if row.result!="reacquired":return row.get("reacquired_observed_ms")==null and row.get("observed_position_m")==null
    var stamp=row.get("reacquired_observed_ms");var point=row.get("observed_position_m")
    if not number(stamp) or stamp<=row.seed_observed_ms or stamp>row.ended_ms or row.ended_ms-stamp>300 or typeof(point)!=TYPE_ARRAY or point.size()!=3:return false
    for v in point:
        if typeof(v) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(v)) or absf(v)>100000:return false
    return true
func configure(value:String,shared_guard:String="")->void:
    path=value;guard_path=shared_guard
    if path.is_empty():return
    if FileAccess.file_exists(path):
        var f:=FileAccess.open(path,FileAccess.READ)
        if f==null or f.get_length()>1000000:ready=false;return
        var seal=JSON.parse_string(f.get_as_text())
        if typeof(seal)!=TYPE_DICTIONARY or typeof(seal.get("payload"))!=TYPE_STRING or seal.get("sha256")!=str(seal.payload).sha256_text():ready=false;return
        var saved=JSON.parse_string(seal.payload)
        if typeof(saved)!=TYPE_DICTIONARY or saved.size()!=4 or saved.get("schema")!=SCHEMA or typeof(saved.get("records"))!=TYPE_ARRAY or saved.records.size()>LIMIT or typeof(saved.get("pending"))!=TYPE_DICTIONARY or typeof(saved.get("clocks"))!=TYPE_DICTIONARY or saved.clocks.size()>16:ready=false;return
        if not saved.pending.is_empty() and saved.pending.get("result")!="reserved":ready=false;return
        for row in saved.records:
            if typeof(row)!=TYPE_DICTIONARY or row.get("result")=="reserved":ready=false;return
        var ids:Dictionary={}
        var budgets:Dictionary={}
        var rows:Array=saved.records.duplicate(true)
        if not saved.pending.is_empty():rows.append(saved.pending)
        if rows.size()>LIMIT:ready=false;return
        for row in rows:
            if not valid(row) or ids.has(row.approach_id) or not saved.clocks.has(row.world_id) or not number(saved.clocks[row.world_id]) or saved.clocks[row.world_id]<row.started_ms:ready=false;return
            if row.ended_ms!=null and saved.clocks[row.world_id]<row.ended_ms:ready=false;return
            var bucket:=str(row.world_id)+":"+str(int(row.started_ms)/EPOCH_MS)
            budgets[bucket]=int(budgets.get(bucket,0))+1
            if budgets[bucket]>4:ready=false;return
            ids[row.approach_id]=true
        for world in saved.clocks:
            if typeof(world)!=TYPE_STRING or world.is_empty() or not number(saved.clocks[world]) or saved.clocks[world]!=floorf(saved.clocks[world]):ready=false;return
        records=saved.records;pending=saved.pending;clocks=saved.clocks
        if not pending.is_empty():
            var interrupted:=pending.duplicate(true);interrupted.result="renderer_restart"
            records.append(interrupted);pending.clear()
    save()
func save()->bool:
    if not ready:return false
    if path.is_empty():return true
    var raw:=JSON.stringify({"schema":SCHEMA,"records":records,"pending":pending,"clocks":clocks})
    var f:=FileAccess.open(path+".tmp",FileAccess.WRITE)
    if f==null:ready=false;return false
    f.store_string(JSON.stringify({"payload":raw,"sha256":raw.sha256_text()}));f.flush();f.close()
    if FileAccess.set_unix_permissions(path+".tmp",384)!=OK or DirAccess.rename_absolute(path+".tmp",path)!=OK:ready=false;return false
    return true
func reserve(active:Dictionary)->bool:
    if not ready or not pending.is_empty() or records.size()>=LIMIT:return false
    var world:String=active.world_id;var now:int=active.started_ms
    if clocks.has(world) and now<int(clocks[world]):return false
    if not clocks.has(world) and clocks.size()>=16:return false
    var count:=0
    for row in records:
        if row.approach_id==active.approach_id:return false
        if row.world_id==world and int(row.started_ms)/EPOCH_MS==now/EPOCH_MS:count+=1
    if not guard_path.is_empty():
        if not FileAccess.file_exists(guard_path):return false
        var f:=FileAccess.open(guard_path,FileAccess.READ)
        if f==null or f.get_length()>1000000:return false
        var seal=JSON.parse_string(f.get_as_text())
        if typeof(seal)!=TYPE_DICTIONARY or typeof(seal.get("payload"))!=TYPE_STRING or seal.get("sha256")!=str(seal.payload).sha256_text():return false
        var state=JSON.parse_string(seal.payload)
        if typeof(state)!=TYPE_DICTIONARY or state.get("schema")!="live-infinita-exploration-reservations/v1" or typeof(state.get("worlds"))!=TYPE_DICTIONARY:return false
        var scope=state.worlds.get(world,{"last_ms":0,"reservations":[]})
        if typeof(scope)!=TYPE_DICTIONARY or not number(scope.get("last_ms")) or scope.last_ms>now or typeof(scope.get("reservations"))!=TYPE_ARRAY or scope.reservations.size()>4:return false
        for row in scope.reservations:
            if typeof(row)!=TYPE_DICTIONARY or row.get("status") not in ["reserved","closed","interrupted"] or not number(row.get("started_ms")):return false
            if row.status=="reserved":return false
            if int(row.started_ms)/EPOCH_MS==now/EPOCH_MS:count+=1
    if count>=4:return false
    pending={"approach_id":active.approach_id,"entity_id":active.entity_id,"world_id":world,"started_ms":now,"seed_observed_ms":active.seed_observed_ms,
        "ended_ms":null,"result":"reserved","distance_m":null,"reacquired_observed_ms":null,"observed_position_m":null,
        "capture":false,"absence_claim":false,"approach_confirmed":false,"learning_eligible":false,"world_write_authority":false}
    if not valid(pending):pending.clear();return false
    clocks[world]=now
    return save()
func settle(row:Dictionary)->bool:
    if not ready or pending.is_empty() or not valid(row) or row.result in ["reserved","renderer_restart"]:return false
    for field in ["approach_id","world_id","entity_id","started_ms","seed_observed_ms"]:
        if row[field]!=pending[field]:return false
    records.append(row.duplicate(true));pending.clear();clocks[row.world_id]=maxf(clocks[row.world_id],row.ended_ms)
    return save()
