extends RefCounted
# Shape only a new inference sample; never move an already visible vertex.
const GRID_M := 8.0
const GRADE := 0.65
const NEIGHBOR_CELLS := 3
var adjusted := 0
var conflicts := 0
func sample(key: Vector2, proposal: float, known: Dictionary) -> float:
    if known.has(key):
        return float(known[key])
    var low := -INF
    var high := INF
    var nearest := INF
    var nearest_height := 0.0
    for z in range(-NEIGHBOR_CELLS,NEIGHBOR_CELLS+1):
        for x in range(-NEIGHBOR_CELLS,NEIGHBOR_CELLS+1):
            if x==0 and z==0:continue
            var other := key+Vector2(float(x),float(z))*GRID_M
            if not known.has(other):continue
            var height := float(known[other])
            if not is_finite(height):continue
            var distance := key.distance_to(other)
            var allowance := GRADE*distance
            low = maxf(low,height-allowance)
            high = minf(high,height+allowance)
            if distance<nearest:
                nearest = distance
                nearest_height = height
    var value := proposal if is_finite(proposal) else nearest_height
    if low<=high:
        value = clampf(value,low,high)
    else:
        # Incompatible old samples cannot be repaired without moving old
        # ground. Honor the closest sample and expose that limitation.
        conflicts += 1
        value = clampf(value,nearest_height-GRADE*nearest,nearest_height+GRADE*nearest)
    if not is_finite(proposal) or absf(value-proposal)>0.00001:
        adjusted += 1
    known[key] = value
    return value
