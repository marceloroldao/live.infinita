extends SceneTree
func _initialize()->void:
    var j=load("res://nov_contact_search_journal.gd").new()
    j.configure(OS.get_environment("LIVE_INFINITA_TEST_SEARCH_JOURNAL"),OS.get_environment("LIVE_INFINITA_TEST_SHARED_GUARD"))
    var active={"world_id":"w","entity_id":"w:rabbit:0","approach_id":"w:animal-approach:native:1","started_ms":410000,"seed_observed_ms":408000}
    if not j.ready or j.reserve(active):push_error("Four exploration starts must block a contact search");quit(1);return
    print("008FP_SHARED_GUARD_PASS");quit(0)
