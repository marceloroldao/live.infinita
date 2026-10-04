extends RefCounted
# 008BK: presentation-only environmental palette.
# It consumes derived EnvironmentalState values; it never writes world state.

func terrain_color(base: Color, environment: Dictionary) -> Color:
    if environment.is_empty():
        return base

    var vegetation := clampf(float(environment.get("vegetation_density", 0.0)), 0.0, 1.0)
    var moisture := clampf(float(environment.get("soil_moisture", 0.0)), 0.0, 1.0)
    var rock := clampf(float(environment.get("rock_exposure", 0.0)), 0.0, 1.0)
    var snow := clampf(float(environment.get("snow_cover", 0.0)), 0.0, 1.0)
    var influence := clampf(float(environment.get("cognitive_influence", 1.0)), 0.0, 1.0)
    var zone := str(environment.get("ecological_zone", ""))
    var forest_affinity := clampf(float(environment.get("forest_affinity", 0.0)), 0.0, 1.0)
    var meadow_affinity := clampf(float(environment.get("meadow_affinity", 0.0)), 0.0, 1.0)
    var wetland_affinity := clampf(float(environment.get("wetland_affinity", 0.0)), 0.0, 1.0)
    var alpine_affinity := clampf(float(environment.get("alpine_affinity", 0.0)), 0.0, 1.0)

    var color := base
    var vegetation_tint := Color("#486d40")
    var wet_tint := Color("#496b58")
    var rock_tint := Color("#77746f")
    var snow_tint := Color("#e6ece9")

    color = color.lerp(
        vegetation_tint,
        clampf(
            vegetation
            * (0.20 + 0.26 * forest_affinity + 0.16 * meadow_affinity)
            * influence,
            0.0,
            0.46
        )
    )
    color = color.lerp(
        wet_tint,
        clampf(wetland_affinity * 0.26 * influence, 0.0, 0.26)
    )
    if zone == "wetland":
        color = color.lerp(
            wet_tint,
            clampf((0.18 + moisture * 0.30) * influence, 0.0, 0.48)
        )
    elif zone == "alpine_meadow":
        color = color.lerp(Color("#78856c"), 0.20 * influence)
    elif zone in ["alpine_rock", "snowfield"]:
        color = color.lerp(rock_tint, 0.20 * influence)

    color = color.lerp(
        rock_tint,
        clampf(alpine_affinity * 0.22 * influence, 0.0, 0.22)
    )
    color = color.lerp(
        rock_tint,
        clampf(rock * 0.72 * influence, 0.0, 0.72)
    )
    color = color.lerp(
        snow_tint,
        clampf(snow * 0.92 * influence, 0.0, 0.92)
    )
    return color

func horizon_base(height_m: float) -> Color:
    var low := Color("#4b6748")
    var high := Color("#7c806d")
    var blend := clampf((height_m + 4.0) / 28.0, 0.0, 1.0)
    return low.lerp(high, blend)
