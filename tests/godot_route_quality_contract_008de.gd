extends SceneTree
const Experience = preload("res://nov_trial_error_quality_008de.gd")
func _initialize() -> void:
    var motor = Experience.new("")
    var point := Vector2(1,0)
    var identity: String = motor.quality_key("3,0|0,0",point)
    motor.quality[identity] = {"remaining_cost_m":10.0,"reference_cost_m":8.0,"samples":3}
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==1.5)
    motor.quality_enabled = true
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==0.0)
    assert(motor.quality_bonus("unknown",point,1.5)==1.5)
    motor.quality[identity]["reference_cost_m"] = 9.5
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==1.0)
    motor.quality[identity]["reference_cost_m"] = 10.0
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==1.5)
    motor.quality[identity]["remaining_cost_m"] = NAN
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==1.5)
    motor.quality[identity] = {"remaining_cost_m":2.0,"reference_cost_m":3.0,"samples":3}
    assert(motor.quality_bonus("3,0|0,0",point,2.0)==2.0)
    var parsed: Dictionary = JSON.parse_string('{"remaining_cost_m":10.0,"reference_cost_m":8.0,"samples":3}')
    motor.quality[identity] = parsed
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==0.0)
    motor.quality[identity]["samples"] = 1.5
    assert(motor.quality_bonus("3,0|0,0",point,1.5)==1.5)
    motor.quality[identity]["samples"] = 0
    assert(motor.quality_bonus("3,0|0,0",point,2.0)==2.0)
    print("008DE_QUALITY_CONTRACT_OK")
    quit(0)
