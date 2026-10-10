extends RefCounted
const SCHEMA := "live-infinita-contextual-approach-history/v1"
const PROFILE := "capsule044-height18-sweep4-native-contour-v1"
const LIMIT := 512
var path := ""
var ready := true
var records: Array = []
var _ids: Dictionary = {}
var _base = preload("res://nov_animal_approach_history.gd").new()
func valid(value: Variant) -> bool:
    if typeof(value)!=TYPE_DICTIONARY or value.size()!=3 or not _base._valid(value.get("approach")):return false
    var row:Dictionary=value.approach
    if not row.learning_eligible or row.censored:return false
    var ctx=value.get("context")
    if typeof(ctx)!=TYPE_DICTIONARY or ctx.size()!=4 or ctx.get("profile")!=PROFILE or ctx.get("sweep_m")!=4.0 or typeof(ctx.get("blocked_ahead"))!=TYPE_BOOL or not _base._number(ctx.get("sample_logical_ms")) or ctx.sample_logical_ms!=row.started_ms:return false
    var contacts=value.get("contacts")
    return typeof(contacts) in [TYPE_INT,TYPE_FLOAT] and _base._number(contacts) and contacts==floorf(float(contacts)) and contacts<=10000
func configure(value: String) -> void:
    path=value
    if path.is_empty():return
    if not FileAccess.file_exists(path):
        save();return
    var f:=FileAccess.open(path,FileAccess.READ)
    if f==null or f.get_length()>1000000:ready=false;return
    var sealed=JSON.parse_string(f.get_as_text())
    if typeof(sealed)!=TYPE_DICTIONARY or typeof(sealed.get("payload"))!=TYPE_STRING or sealed.get("sha256")!=str(sealed.payload).sha256_text():ready=false;return
    var snapshot=JSON.parse_string(sealed.payload)
    if typeof(snapshot)!=TYPE_DICTIONARY or snapshot.get("schema")!=SCHEMA or typeof(snapshot.get("records"))!=TYPE_ARRAY or snapshot.records.size()>LIMIT:ready=false;return
    for row in snapshot.records:
        if not valid(row) or _ids.has(row.approach.id):ready=false;return
        _ids[row.approach.id]=true
    records=snapshot.records
func save() -> bool:
    if not ready:return false
    if path.is_empty():return true
    var raw:=JSON.stringify({"schema":SCHEMA,"records":records})
    var f:=FileAccess.open(path+".tmp",FileAccess.WRITE)
    if f==null:ready=false;return false
    f.store_string(JSON.stringify({"payload":raw,"sha256":raw.sha256_text()}));f.flush();f.close()
    if FileAccess.set_unix_permissions(path+".tmp",384)!=OK or DirAccess.rename_absolute(path+".tmp",path)!=OK:ready=false;return false
    return true
func record(value: Dictionary) -> bool:
    if not ready or not valid(value) or _ids.has(value.approach.id):return false
    records.append(value.duplicate(true));_ids[value.approach.id]=true
    while records.size()>LIMIT:_ids.erase(records[0].approach.id);records.pop_front()
    return save()
func status() -> Dictionary:
    return {"storage_ready":ready,"persistent":not path.is_empty(),"stored_attempts":records.size(),"profile":PROFILE,"decision_use":false}
