"""Experimental durable exploration reservations; intentions never become learning facts."""
import json,os,fcntl,uuid
from pathlib import Path
from contextlib import contextmanager
from hashlib import sha256
from nov_animal_cost_revalidation import recommend as cost_recommend,EPOCH_MS
from nov_animal_approach_context import key,PROFILE,NATIVE_PROFILE
from nov_animal_approach_sync import read_json,number,validate
from nov_navigation_memory_sync import write_checkpoint
SCHEMA="live-infinita-exploration-reservations/v1"
MAX_ATTEMPTS=4
MAX_WORLDS=16
EXPLORATION={"recovered-cost-revalidation","recovered-failure-reassessment"}
class GuardError(ValueError):pass
def check_state(s):
    if not isinstance(s,dict) or set(s)!={"schema","worlds"} or s["schema"]!=SCHEMA or not isinstance(s["worlds"],dict) or len(s["worlds"])>MAX_WORLDS:raise GuardError("invalid_guard_state")
    tokens=set()
    for world,value in s["worlds"].items():
        if not isinstance(world,str) or not 1<=len(world)<=160 or not isinstance(value,dict) or set(value)!={"last_ms","epoch_start_ms","reservations"}:raise GuardError("invalid_guard_scope")
        if not number(value["last_ms"],True) or not number(value["epoch_start_ms"],True) or value["epoch_start_ms"]%EPOCH_MS or value["last_ms"]<value["epoch_start_ms"]:raise GuardError("invalid_guard_clock")
        rows=value["reservations"]
        if not isinstance(rows,list) or len(rows)>MAX_ATTEMPTS:raise GuardError("invalid_guard_budget")
        pending=0
        for r in rows:
            if not isinstance(r,dict) or set(r)!={"token","entity_id","started_ms","context_key","status","outcome_id","outcome_sha256"}:raise GuardError("invalid_reservation")
            if not isinstance(r["token"],str) or len(r["token"])!=32 or any(c not in "0123456789abcdef" for c in r["token"]) or r["token"] in tokens:raise GuardError("invalid_reservation_token")
            tokens.add(r["token"])
            if not isinstance(r["entity_id"],str) or not r["entity_id"].startswith(world+":rabbit:") or len(r["entity_id"])>160 or not number(r["started_ms"],True) or not value["epoch_start_ms"]<=r["started_ms"]<=value["last_ms"] or r["started_ms"]>=value["epoch_start_ms"]+EPOCH_MS:raise GuardError("invalid_reserved_attempt")
            k=r["context_key"]
            if not isinstance(k,list) or len(k)!=3 or type(k[0]) is not int or not 1<=k[0]<=4 or k[1] not in (PROFILE,NATIVE_PROFILE) or type(k[2]) is not bool:raise GuardError("invalid_reserved_context")
            if r["status"] not in ("reserved","closed","interrupted"):raise GuardError("invalid_reservation_status")
            if r["status"]=="reserved":
                pending+=1
                if r["outcome_id"] is not None or r["outcome_sha256"] is not None:raise GuardError("unmeasured_reservation")
            elif not isinstance(r["outcome_id"],str) or not r["outcome_id"].startswith(world+":animal-approach:") or not isinstance(r["outcome_sha256"],str) or len(r["outcome_sha256"])!=64:raise GuardError("invalid_settled_reservation")
        if pending>1:raise GuardError("multiple_pending_reservations")
    return s
@contextmanager
def locked(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_symlink():raise GuardError("symlink_guard_rejected")
    fd=os.open(str(path)+".lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        os.fchmod(fd,0o600);fcntl.flock(fd,fcntl.LOCK_EX)
        if path.exists():
            sealed=read_json(path)
            if type(sealed.get("payload")) is not str or sealed.get("sha256")!=sha256(sealed["payload"].encode()).hexdigest():raise GuardError("invalid_guard_checksum")
            state=check_state(json.loads(sealed["payload"]))
        else:state={"schema":SCHEMA,"worlds":{}}
        yield state
        check_state(state)
        raw=json.dumps(state,sort_keys=True,separators=(",",":"),allow_nan=False)
        write_checkpoint(path,{"payload":raw,"sha256":sha256(raw.encode()).hexdigest()},mode=0o600)
    finally:os.close(fd)
def recommend_and_reserve(path,candidates,entries,world,now):
    decision=cost_recommend(candidates,entries,world,now)
    with locked(path) as state:
        epoch=int(now)//EPOCH_MS*EPOCH_MS
        if world not in state["worlds"]:
            if len(state["worlds"])==MAX_WORLDS:raise GuardError("guard_scope_limit")
            state["worlds"][world]={"last_ms":int(now),"epoch_start_ms":epoch,"reservations":[]}
        scope=state["worlds"][world]
        if now<scope["last_ms"]:raise GuardError("guard_clock_rewind")
        scope["last_ms"]=int(now)
        rows=scope["reservations"]
        if any(r["status"]=="reserved" for r in rows):
            return {"entity_id":None,"source":"exploration_guard","reason":"pending_reservation","reservation_token":None}
        if epoch>scope["epoch_start_ms"]:
            scope["epoch_start_ms"]=epoch;rows=[];scope["reservations"]=rows
        status={"epoch_start_ms":epoch,"used_attempts":len(rows),"attempt_limit":MAX_ATTEMPTS,"intent_only":True}
        if decision["source"] not in EXPLORATION:return dict(decision,reservation_token=None,exploration_budget=status)
        if len(rows)==MAX_ATTEMPTS:
            closest=min(candidates,key=lambda c:(c["distance_m"],c["entity_id"]))
            return {"entity_id":closest["entity_id"],"source":"perception","reason":"exploration_budget_exhausted",
                    "observation_ids":[],"reservation_token":None,"exploration_budget":status}
        chosen=next(c for c in candidates if c["entity_id"]==decision["entity_id"])
        token=uuid.uuid4().hex
        rows.append({"token":token,"entity_id":chosen["entity_id"],"started_ms":int(now),
                     "context_key":list(key(chosen["distance_m"],chosen["context"])),"status":"reserved","outcome_id":None,"outcome_sha256":None})
        status["used_attempts"]=len(rows)
        return dict(decision,reservation_token=token,exploration_budget=status)
def settle(path,token,actual_base_outcome):
    row=validate(actual_base_outcome)
    digest=sha256(json.dumps(row,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    with locked(path) as state:
        matches=[r for s in state["worlds"].values() for r in s["reservations"] if r["token"]==token]
        if len(matches)!=1:raise GuardError("unknown_reservation")
        reservation=matches[0]
        scope=state["worlds"].get(row["world_id"])
        if scope is None or reservation not in scope["reservations"] or row["entity_id"]!=reservation["entity_id"] or row["started_ms"]!=reservation["started_ms"]:raise GuardError("reservation_outcome_mismatch")
        if reservation["status"]!="reserved":
            if reservation["outcome_sha256"]!=digest:raise GuardError("changed_settled_outcome")
            return reservation["status"]
        if any(r["outcome_id"]==row["id"] for s in state["worlds"].values() for r in s["reservations"]):raise GuardError("duplicate_outcome_binding")
        scope["last_ms"]=max(scope["last_ms"],row["ended_ms"] or row["started_ms"])
        reservation["status"]="interrupted" if row["censored"] else "closed"
        reservation["outcome_id"]=row["id"];reservation["outcome_sha256"]=digest
        return reservation["status"]
