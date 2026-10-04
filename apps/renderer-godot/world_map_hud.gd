extends CanvasLayer

signal local_mode_changed(enabled: bool)

var _status: Label
var _toggle: Button
var _direction_buttons: Array[Button] = []
var _local_mode := false
var _world_size_m := 1024

func _ready() -> void:
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
