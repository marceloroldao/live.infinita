extends CanvasLayer

signal local_mode_changed(enabled: bool)

var _learning: Label
var _status: Label
var _toggle: Button
var _direction_buttons: Array[Button] = []
var _local_mode := false
var _world_size_m := 1024

func _ready() -> void:
    _learning = Label.new()
    _learning.name = "NovLearningPanel"
    _learning.anchor_left = 1.0
    _learning.anchor_right = 1.0
    _learning.offset_left = -330
    _learning.offset_right = -18
    _learning.offset_top = 104
    _learning.offset_bottom = 272
    _learning.add_theme_font_size_override("font_size",16)
    _learning.add_theme_color_override("font_color",Color.WHITE)
    var box := StyleBoxFlat.new()
    box.bg_color = Color(0.02,0.05,0.08,0.78)
    box.set_content_margin_all(12)
    box.set_corner_radius_all(8)
    _learning.add_theme_stylebox_override("normal",box)
    _learning.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(_learning)
    _status = Label.new()
    _status.position = Vector2(18, 22)
    _status.add_theme_color_override("font_color", Color.WHITE)
    _status.add_theme_color_override("font_shadow_color", Color.BLACK)
    _status.add_theme_constant_override("shadow_offset_x", 2)
    _status.add_theme_constant_override("shadow_offset_y", 2)
    add_child(_status)

    _toggle = Button.new()
    _toggle.text = "EXPLORAR LOCAL"
    _toggle.anchor_left = 1.0
    _toggle.anchor_top = 1.0
    _toggle.anchor_right = 1.0
    _toggle.anchor_bottom = 1.0
    _toggle.offset_left = -205
    _toggle.offset_top = -72
    _toggle.offset_right = -18
    _toggle.offset_bottom = -18
    _toggle.pressed.connect(_toggle_local)
    add_child(_toggle)
    _toggle.visible = false # Live presentation has no exploration control.
    _direction_buttons.append(_direction_button("←", "ui_left", 18, -84))
    _direction_buttons.append(_direction_button("↑", "ui_up", 78, -144))
    _direction_buttons.append(_direction_button("↓", "ui_down", 78, -84))
    _direction_buttons.append(_direction_button("→", "ui_right", 138, -84))
    _apply_mode(false, false)

func _direction_button(text: String, action: String, x: float, y: float) -> Button:
    var button := Button.new()
    button.text = text
    button.anchor_top = 1.0
    button.anchor_bottom = 1.0
    button.offset_left = x
    button.offset_top = y
    button.offset_right = x + 54
    button.offset_bottom = y + 54
    button.button_down.connect(Callable(self, "_press_action").bind(action))
    button.button_up.connect(Callable(self, "_release_action").bind(action))
    add_child(button)
    return button

func _press_action(action: String) -> void:
    Input.action_press(action)

func _release_action(action: String) -> void:
    Input.action_release(action)

func _release_all() -> void:
    for action in ["ui_left", "ui_right", "ui_up", "ui_down"]:
        Input.action_release(action)

func _toggle_local() -> void:
    _apply_mode(not _local_mode, true)

func _apply_mode(enabled: bool, notify: bool) -> void:
    _local_mode = enabled
    _toggle.text = "VOLTAR AO NOV" if enabled else "EXPLORAR LOCAL"
    for button in _direction_buttons:
        button.visible = enabled
    if not enabled:
        _release_all()
    if notify:
        local_mode_changed.emit(enabled)
func configure(world_size_m: int) -> void:
    _world_size_m = world_size_m

func set_technical_status_visible(visible: bool) -> void:
    if _status != null:
        _status.visible = visible

func set_status(text: String) -> void:
    _status.text = text

func update_live(
    active_tiles: int,
    decor_limit: int,
    region_id: String,
    sequence: int,
    connection: String,
    cx: int,
    cz: int,
    biome: String,
    hot: int,
    warm: int,
    regions: int
) -> void:
    set_status(
        "LIVE INFINITA / VALE DE NOV\n%d x %d m | %d setores ativos | max %d decoracoes\nNOV autoritativo | regiao %s | seq %d | %s\nSetor %d,%d - %s | HOT %d / WARM %d / REG %d | somente leitura"
        % [_world_size_m, _world_size_m, active_tiles, decor_limit, region_id, sequence, connection, cx, cz, biome, hot, warm, regions]
    )

func update_local(
    active_tiles: int,
    decor_limit: int,
    cx: int,
    cz: int,
    biome: String,
    surface: String,
    blocked_reason: String,
    explicit_local: bool
) -> void:
    var blocked := " | bloqueio " + blocked_reason if not blocked_reason.is_empty() else ""
    var mode := "EXPLORADOR LOCAL - nao move NOV" if explicit_local else "tour local offline"
    set_status(
        "LIVE INFINITA / VALE DE NOV\n%d x %d m | %d setores ativos | max %d decoracoes\n%s\nSetor %d,%d - %s | %s%s"
        % [_world_size_m, _world_size_m, active_tiles, decor_limit, mode, cx, cz, biome, surface, blocked]
    )

func _exit_tree() -> void:
    _release_all()

func update_learning(experience: RefCounted, journey: RefCounted) -> void:
    if _learning==null:return
    var names := {"working-memory":"RAM","memoria.ia":"Memoria.ia","perception":"percepção"}
    var source := str(names.get(experience.last_decision_source,"percepção"))
    var memory: RefCounted = experience.working_memory
    if OS.has_feature("web"):
        var qualified := 0
        for key_value in experience.recalled_routes:
            if experience.recalled_routes[key_value].has("route_quality"):qualified += 1
        var data: Dictionary = experience.server_learning_status
        var progress := "Caminhando: %.1f m" % float(data.get("distance_m",0.0)) if bool(data.get("active",false)) else str(data.get("result","aguardando caminhada")).left(60)
        if data.get("motion_state","")=="no_passage":progress = "Procurando passagem"
        elif data.get("motion_state","")=="water_egress":progress = "Saindo do lago: %.1f m" % float(data.get("distance_m",0.0))
        if not data.is_empty() and Time.get_unix_time_from_system()-float(data.get("observed_at_unix",0.0))<60.0:
            _learning.text = "NOV • TENTATIVA E ERRO\nSessão do servidor\nChegadas: %d | Interrompidas: %d\nEscolhas: RAM %d / Memoria.ia %d\nMemoria.ia: %d passos (%d com custo)\n%s" % [int(data.get("arrivals",0)),int(data.get("interruptions",0)),int(data.get("causal_ram_steps",0)),int(data.get("causal_memoria_steps",0)),experience.recalled_routes.size(),qualified,progress]
        else:
            _learning.text = "NOV • TENTATIVA E ERRO\nAguardando dados do servidor\nDecisão desta prévia: %s\nMemoria.ia: %d passos lembrados\nPassos avaliados: %d" % [source,experience.recalled_routes.size(),qualified]
    else:
        var data: Dictionary = journey.status()
        var progress := "Caminhando: %.1f m" % float(data.distance_m) if bool(data.active) else str(data.result)
        if data.get("motion_state","")=="no_passage":progress = "Procurando passagem"
        elif data.get("motion_state","")=="water_egress":progress = "Saindo do lago: %.1f m" % float(data.distance_m)
        _learning.text = "NOV • TENTATIVA E ERRO
Decisão: %s
RAM: %d | Promovidas: %d
Chegadas: %d | Interrompidas: %d
Escolhas: RAM %d / Memoria.ia %d
%s" % [source,memory.entries.size(),memory.promoted.size(),data.arrivals,data.interruptions,data.causal_ram_steps,data.causal_memoria_steps,progress]
