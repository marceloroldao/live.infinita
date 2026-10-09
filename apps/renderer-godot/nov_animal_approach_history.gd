extends RefCounted
const SCHEMA := "live-infinita-animal-approach-history/v1"
const LIMIT := 512
const RESULTS := ["approached","contact_lost","no_progress","budget_exhausted","destination_rejected",
    "clock_unavailable","feed_unavailable","world_changed","clock_rewind","navigation_recovery","renderer_restart",
    "test_interrupted"]
var path := ""
var ready := true
var records: Array = []
var pending: Dictionary = {}
var _ids: Dictionary = {}
func _number(value: Variant) -> bool:
    return typeof(value) in [TYPE_INT,TYPE_FLOAT] and is_finite(float(value)) and float(value)>=0 and float(value)<=1.0e15
func _valid(row: Variant) -> bool:
    if typeof(row)!=TYPE_DICTIONARY or typeof(row.get("id"))!=TYPE_STRING or row.id.is_empty() or row.id.length()>240 or typeof(row.get("entity_id"))!=TYPE_STRING or row.entity_id.length()>160:return false
    if row.get("result") not in RESULTS or row.get("capture")!=false or row.get("contains_prediction")!=false or row.get("absence_claim")!=false or row.get("world_write_authority")!=false:return false
    if typeof(row.get("world_id"))!=TYPE_STRING or not row.id.begins_with(row.world_id+":animal-approach:") or not row.entity_id.begins_with(row.world_id+":rabbit:"):return false
    if not _number(row.get("started_ms")) or not _number(row.get("initial_observed_remaining_m")):return false
    if row.get("ended_ms")==null:
        if row.result!="renderer_restart" or row.get("distance_m")!=null:return false
    elif not _number(row.ended_ms) or row.ended_ms<row.started_ms:return false
    if row.result=="approached" and (not _number(row.get("final_observed_remaining_m")) or row.final_observed_remaining_m>6.5):return false
    if typeof(row.get("censored"))!=TYPE_BOOL or typeof(row.get("learning_eligible"))!=TYPE_BOOL:return false
    if row.get("distance_m")==null:
        return row.censored and not row.learning_eligible
    if not _number(row.distance_m):return false
    return not row.learning_eligible or (not row.censored and row.distance_m>0 and row.result in ["approached","contact_lost","no_progress","budget_exhausted"])
func configure(value: String) -> void:
    path=value
    if path.is_empty() or not FileAccess.file_exists(path):return
    var f:=FileAccess.open(path,FileAccess.READ)
    if f==null or f.get_length()>1000000:ready=false;return
    var envelope=JSON.parse_string(f.get_as_text())
    if typeof(envelope)!=TYPE_DICTIONARY or typeof(envelope.get("payload"))!=TYPE_STRING or envelope.get("sha256")!=str(envelope.payload).sha256_text():ready=false;return
    var saved=JSON.parse_string(envelope.payload)
    if typeof(saved)!=TYPE_DICTIONARY or saved.get("schema")!=SCHEMA or typeof(saved.get("records"))!=TYPE_ARRAY or saved.records.size()>LIMIT or typeof(saved.get("pending"))!=TYPE_DICTIONARY:ready=false;return
    for row in saved.records:
        if not _valid(row) or _ids.has(row.id):ready=false;return
        _ids[row.id]=true
    records=saved.records;pending=saved.pending
    if not pending.is_empty():
        if not _valid(pending) or _ids.has(pending.id) or pending.result!="renderer_restart" or not pending.censored:ready=false;return
        # The checkpoint proves an intention existed; it does not measure movement after it.
        records.append(pending.duplicate(true));_ids[pending.id]=true;pending.clear()
        while records.size()>LIMIT:_ids.erase(records[0].id);records.pop_front()
        save()
func save() -> bool:
    if path.is_empty():return true
    if not ready:return false
    var raw:=JSON.stringify({"schema":SCHEMA,"records":records,"pending":pending})
    var f:=FileAccess.open(path+".tmp",FileAccess.WRITE)
    if f==null:ready=false;return false
    f.store_string(JSON.stringify({"payload":raw,"sha256":raw.sha256_text()}));f.flush();f.close()
    if FileAccess.set_unix_permissions(path+".tmp",384)!=OK or DirAccess.rename_absolute(path+".tmp",path)!=OK:ready=false;return false
    return true
func begin(active: Dictionary) -> bool:
    if not ready:return false
    pending={"id":active.id,"world_id":active.world_id,"entity_id":active.entity_id,"started_ms":active.started_ms,"ended_ms":null,
        "initial_observed_remaining_m":active.initial_observed_remaining_m,"result":"renderer_restart","distance_m":null,
        "censored":true,"learning_eligible":false,"capture":false,"contains_prediction":false,
        "absence_claim":false,"world_write_authority":false}
    return save()
func record(value: Dictionary) -> bool:
    if not ready or not _valid(value) or _ids.has(value.id):return false
    records.append(value.duplicate(true));_ids[value.id]=true;pending.clear()
    while records.size()>LIMIT:_ids.erase(records[0].id);records.pop_front()
    return save()
func status() -> Dictionary:
    return {"storage_ready":ready,"persistent":not path.is_empty(),"stored_attempts":records.size(),
        "censored_attempts":records.filter(func(r):return r.censored).size(),
        "learning_eligible_attempts":records.filter(func(r):return r.learning_eligible).size(),
        "core_ingestion":false}
