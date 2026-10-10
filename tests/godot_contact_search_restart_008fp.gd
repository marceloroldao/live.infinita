extends SceneTree
func _initialize()->void:
    var journal=load("res://nov_contact_search_journal.gd").new()
    journal.configure(OS.get_environment("LIVE_INFINITA_TEST_SEARCH_JOURNAL"))
    if not journal.ready:push_error("Journal failed cold load");quit(1);return
    print("008FP_COLD "+JSON.stringify({"records":journal.records,"pending":journal.pending,"clocks":journal.clocks}))
    quit(0)
