




import bisect
import copy
import ctypes
import json
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Iterator, List, Optional, Set, Tuple

import pygame

pygame.init()

if sys.platform == "win32":
    try:
        windll = getattr(ctypes, "windll")
        windll.shell32.SetCurrentProcessExplicitAppUserModelID("GateOfLight")
    except Exception:
        pass

COLOR_ON = (100, 149, 237)
COLOR_OFF = (105, 105, 105)
COLOR_BG = (30, 30, 30)
COLOR_GRID = (60, 60, 60)
THEMES = {
    'Dark':          {'on': (100, 149, 237), 'off': (105, 105, 105), 'bg': (30, 30, 30),   'grid': (60, 60, 60)},
    'Light':         {'on': (18, 62, 140),   'off': (95, 100, 110),  'bg': (236, 238, 244), 'grid': (202, 208, 220)},
    'High Contrast': {'on': (0, 255, 140),   'off': (235, 235, 235), 'bg': (0, 0, 0),       'grid': (110, 110, 110)},
}
THEME_ORDER = ('Dark', 'Light', 'High Contrast')
current_theme = 'Dark'
CLEAR = (0, 0, 0, 0)

WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 700

BASE_CELL_SIZE = 40
WORLD_HALF_COLS = WORLD_HALF_ROWS = 5000
WORLD_COLS, WORLD_ROWS = WORLD_HALF_COLS * 2, WORLD_HALF_ROWS * 2
WORLD_WIDTH_PX, WORLD_HEIGHT_PX = WORLD_COLS * BASE_CELL_SIZE, WORLD_ROWS * BASE_CELL_SIZE
WORLD_MIN_PX = -WORLD_HALF_COLS * BASE_CELL_SIZE
WORLD_MAX_PX = WORLD_HALF_COLS * BASE_CELL_SIZE
WORLD_MIN_PY, WORLD_MAX_PY = WORLD_MIN_PX, WORLD_MAX_PX
MIN_ZOOM, MAX_ZOOM, ZOOM_FACTOR = 0.15, 5.0, 0.8
PAN_SPEED_PX = 500
MAX_FRAME_DT_S = 0.05

MAX_RAY_STEPS = 100000
MAX_LIGHT_ROUNDS = 100000
MAX_RAYS_PER_ROUND = 100000
MAX_STEPS_PER_ROUND = 100000
MAX_TRACE_SEGMENTS = 100000
TRACE_TIME_LIMIT_S = 0.05

DELAY_LINE_DEFAULT_TICKS = 1
DELAY_LINE_MIN_TICKS, DELAY_LINE_MAX_TICKS = 1, 12
TICK_INTERVAL_S = 0.25
TICK_DISPLAY_WRAP = 100

ICON_SIZE = BASE_CELL_SIZE
ICON_MAIN = int(ICON_SIZE * 0.7)
ICON_WALL = int(ICON_SIZE * 0.8)
ICON_PROTRUDE = max(3, int(ICON_SIZE * 0.2))
ICON_LINE_W = max(2, int(ICON_SIZE * 0.1))
ICON_INSET = int(ICON_SIZE * 0.2)
ICON_BAR_LEN = int(ICON_SIZE * 0.88)
ICON_BAR_W = max(2, int(ICON_SIZE * 0.08))
ICON_BAR_GAP = int(ICON_SIZE * 0.22)
ICON_RING_R, ICON_RING_W = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.12)
ICON_LATCH_R, ICON_LATCH_CORE = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.2)

HOTBAR_CELL = 60
HOTBAR_GAP = 6
HOTBAR_BOTTOM_PAD = 10

PLACE_BTN = 3
ERASE_BTN = 1

SAVE_VERSION = 1
SAVE_SLOTS = (1, 2, 3, 4, 5)
MAX_CELLS_LIMIT = 200000
UNDO_LIMIT = 200
MESSAGE_TTL_S = 4.0

_ESC_RETURN_WIN = 600
_MENU_DECOR_CELL = 92
_MENU_DECOR_MAX = 12
_MENU_DECOR_STEP_MS = 240
_MENU_DECOR_FADE_MS = 520

KEY_TOOL_BASE = pygame.K_1
KEY_ROTATE_ELEMENT = pygame.K_q
KEY_CYCLE_PLACE_ROT = pygame.K_e
KEY_TOGGLE_SWITCH = pygame.K_f
KEY_PASTE_SLOT = pygame.K_v
KEY_UNDO = pygame.K_z
KEY_REDO = pygame.K_x
KEY_TOGGLE_PAUSE = pygame.K_SPACE
KEY_SAVE_SLOT_BASE = pygame.K_F1
KEY_SAVE_SLOTS = (pygame.K_F1,)
SAVE_SLOT_KEYS = {pygame.K_F1: 1}
KEY_LOAD_SLOT = pygame.K_F2
KEY_SAVE_MENU = pygame.K_F1
KEY_TOGGLE_PERF = pygame.K_F12
KEY_BACK = pygame.K_ESCAPE
KEY_SL_SAVE = pygame.K_RETURN
KEY_SL_LOAD = pygame.K_l
KEY_SL_RENAME = pygame.K_r
KEY_SL_DELETE = pygame.K_DELETE
KEY_SL_NEW = pygame.K_n
KEY_PAN_LEFT = pygame.K_LEFT
KEY_PAN_RIGHT = pygame.K_RIGHT
KEY_PAN_UP = pygame.K_UP
KEY_PAN_DOWN = pygame.K_DOWN
KEY_PAN_LEFT_ALT = pygame.K_a
KEY_PAN_RIGHT_ALT = pygame.K_d
KEY_PAN_UP_ALT = pygame.K_w
KEY_PAN_DOWN_ALT = pygame.K_s

_DEFAULT_KEYS = {
    'tool_0': pygame.K_1, 'tool_1': pygame.K_2,
    'tool_2': pygame.K_3, 'tool_3': pygame.K_4,
    'tool_4': pygame.K_5, 'tool_5': pygame.K_6,
    'tool_6': pygame.K_7, 'tool_7': pygame.K_8,
    'undo': KEY_UNDO,
    'redo': KEY_REDO,
    'rotate': KEY_ROTATE_ELEMENT,
    'cycle_rot': KEY_CYCLE_PLACE_ROT,
    'toggle_switch': KEY_TOGGLE_SWITCH,
    'paste': KEY_PASTE_SLOT,
    'pause': KEY_TOGGLE_PAUSE,
    'perf': KEY_TOGGLE_PERF,
    'save_1': pygame.K_F1,
    'sl_save': KEY_SL_SAVE,
    'sl_load': KEY_SL_LOAD,
    'sl_rename': KEY_SL_RENAME,
    'sl_delete': KEY_SL_DELETE,
    'sl_new': KEY_SL_NEW,
    'load': KEY_LOAD_SLOT,
    'pan_up': KEY_PAN_UP,
    'pan_down': KEY_PAN_DOWN,
    'pan_left': KEY_PAN_LEFT,
    'pan_right': KEY_PAN_RIGHT,
    'pan_up_alt': KEY_PAN_UP_ALT,
    'pan_down_alt': KEY_PAN_DOWN_ALT,
    'pan_left_alt': KEY_PAN_LEFT_ALT,
    'pan_right_alt': KEY_PAN_RIGHT_ALT,
    'zoom_in': pygame.K_EQUALS,
    'zoom_out': pygame.K_MINUS,
}
KEYMAP = dict(_DEFAULT_KEYS)
_KEY_LABEL_SPECIAL = {
    pygame.K_UP: 'Up', pygame.K_DOWN: 'Down', pygame.K_LEFT: 'Left',
    pygame.K_RIGHT: 'Right', pygame.K_SPACE: 'Space',
    pygame.K_RETURN: 'Enter', pygame.K_KP_ENTER: 'Enter',
    pygame.K_BACKSPACE: 'Backsp', pygame.K_DELETE: 'Del',
    pygame.K_ESCAPE: 'Esc', pygame.K_TAB: 'Tab',
    pygame.K_HOME: 'Home', pygame.K_END: 'End',
    pygame.K_PAGEUP: 'PgUp', pygame.K_PAGEDOWN: 'PgDn',
    pygame.K_LSHIFT: 'LShift', pygame.K_RSHIFT: 'RShift',
    pygame.K_LCTRL: 'LCtrl', pygame.K_RCTRL: 'RCtrl',
    pygame.K_LALT: 'LAlt', pygame.K_RALT: 'RAlt',
}
def _key_label(key: int) -> str:
    if key in _KEY_LABEL_SPECIAL:
        return _KEY_LABEL_SPECIAL[key]
    name = pygame.key.name(key)
    if name.startswith('f') and name[1:].isdigit():
        return name.upper()
    return name.upper() if len(name) <= 3 else name.capitalize()
def _key_owner(exclude_id: str, key: int) -> Optional[str]:
    for aid, k in KEYMAP.items():
        if k == key and aid != exclude_id:
            return aid
    return None
def apply_keymap() -> None:
    g = globals()
    g['KEY_UNDO'] = KEYMAP['undo']
    g['KEY_REDO'] = KEYMAP['redo']
    g['KEY_ROTATE_ELEMENT'] = KEYMAP['rotate']
    g['KEY_CYCLE_PLACE_ROT'] = KEYMAP['cycle_rot']
    g['KEY_TOGGLE_SWITCH'] = KEYMAP['toggle_switch']
    g['KEY_PASTE_SLOT'] = KEYMAP['paste']
    g['KEY_TOGGLE_PAUSE'] = KEYMAP['pause']
    g['KEY_TOGGLE_PERF'] = KEYMAP['perf']
    g['KEY_LOAD_SLOT'] = KEYMAP['load']
    g['KEY_SAVE_MENU'] = KEYMAP['save_1']
    g['KEY_SL_SAVE'] = KEYMAP['sl_save']
    g['KEY_SL_LOAD'] = KEYMAP['sl_load']
    g['KEY_SL_RENAME'] = KEYMAP['sl_rename']
    g['KEY_SL_DELETE'] = KEYMAP['sl_delete']
    g['KEY_SL_NEW'] = KEYMAP['sl_new']
    g['TOOL_KEY_MAP'] = {KEYMAP['tool_%d' % i]: i for i in range(len(TOOL_TYPES))}
    g['KEY_SAVE_SLOTS'] = tuple(KEYMAP['save_%d' % i] for i in (1,))
    g['SAVE_SLOT_KEYS'] = {KEYMAP['save_%d' % i]: i for i in (1,)}
    g['PAN_KEYS'] = (
        (KEYMAP['pan_left'], KEYMAP['pan_left_alt'], 'x', -1),
        (KEYMAP['pan_right'], KEYMAP['pan_right_alt'], 'x', 1),
        (KEYMAP['pan_up'], KEYMAP['pan_up_alt'], 'y', -1),
        (KEYMAP['pan_down'], KEYMAP['pan_down_alt'], 'y', 1),
    )
REFLECT_ON_SLASH = {0: 1, 1: 0, 2: 3, 3: 2}
REFLECT_ON_BACKSLASH = {0: 3, 3: 0, 2: 1, 1: 2}
STEP_BY_DIR = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}
EDGE_PX = {0: ('y', WORLD_MIN_PY), 1: ('x', WORLD_MAX_PX),
           2: ('y', WORLD_MAX_PY), 3: ('x', WORLD_MIN_PX)}

PERSIST_FIELDS = {
    'wall': ('dir',), 'laser': ('dir', 'is_on'), 'mirror': ('dir',),
    'coupler': ('dir',), 'and_gate': ('dir',), 'xor_gate': ('dir',),
    'latch': ('dir', 'state', 'in_levels'),
    'delay_line': ('dir', 'ticks'),
}

def _resolve_base_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _resolve_base_dir()
SAVE_DIR = os.path.join(BASE_DIR, "saves")
SETTINGS_PATH = os.path.join(SAVE_DIR, "settings.json")

def resource_path(rel: str) -> str:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = os.path.join(meipass, rel)
            if os.path.exists(cand):
                return cand
    return os.path.join(BASE_DIR, rel)

def _load_app_icon(fallback_size: int = 64):
    for name in ("GateOfLight.ico", "GateOfLight.png", "app.ico"):
        path = resource_path(name)
        if os.path.exists(path):
            try:
                return pygame.image.load(path)
            except Exception:
                pass
    return None

screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
_APP_ICON = _load_app_icon()
if _APP_ICON is not None:
    pygame.display.set_icon(_APP_ICON)
pygame.display.set_caption('GateOfLight')
clock = pygame.time.Clock()

def _tint(color, alpha):
    return (color[0], color[1], color[2], alpha)


def _draw_scrollbar(track_rect, total_h, view_h, scroll):
    """统一滚动条样式（以 F1 存档界面为准）：
    轨道 COLOR_OFF@70、滑块 COLOR_ON、宽 6、滑块最小 24px。"""
    if view_h <= 0 or total_h <= view_h:
        return
    pygame.draw.rect(screen, _tint(COLOR_OFF, 70), track_rect)
    ratio = view_h / float(total_h)
    thumb_h = max(24, int(track_rect.h * min(1.0, ratio)))
    mx = max(1.0, float(total_h - view_h))
    thumb_y = track_rect.y + int((track_rect.h - thumb_h) * (scroll / mx))
    pygame.draw.rect(screen, COLOR_ON,
                     (track_rect.x, thumb_y, track_rect.w, thumb_h))

camera_x = -round(WINDOW_WIDTH / 2.0 / BASE_CELL_SIZE) * BASE_CELL_SIZE
camera_y = -round(WINDOW_HEIGHT / 2.0 / BASE_CELL_SIZE) * BASE_CELL_SIZE
zoom = 1.0

Coord = Tuple[int, int]
Point = Tuple[float, float]
Segment = Tuple[Point, Point]
RaySeed = RayState = Tuple[int, int, int]
HandlerResult = Optional[Tuple[Coord, int, Point]]

def _etype(data: dict) -> str:
    element_type = data.get('type')
    return element_type if isinstance(element_type, str) else ''

grid_data: Dict[Coord, dict] = {}

_idx_laser: Set[Coord] = set()
_idx_latch: Set[Coord] = set()
_idx_delay: Set[Coord] = set()
_lit_relay: Set[Coord] = set()
_touched_and: Set[Coord] = set()
_lit_walls: Set[Coord] = set()
_touched_xor: Set[Coord] = set()
_RELAY_TYPES = ('mirror', 'coupler')
_idx_row_cols: Dict[int, list] = {}
_idx_col_rows: Dict[int, list] = {}

def _index_track(coord: Coord, data: dict) -> None:
    row, col = coord
    bisect.insort(_idx_row_cols.setdefault(row, []), col)
    bisect.insort(_idx_col_rows.setdefault(col, []), row)
    t = data.get('type')
    if t == 'laser':
        _idx_laser.add(coord)
    elif t == 'latch':
        _idx_latch.add(coord)
    elif t == 'delay_line':
        _idx_delay.add(coord)

def _index_untrack(coord: Coord, data: Optional[dict]) -> None:
    row, col = coord
    lst = _idx_row_cols.get(row)
    if lst:
        i = bisect.bisect_left(lst, col)
        if i < len(lst) and lst[i] == col:
            lst.pop(i)
        if not lst:
            _idx_row_cols.pop(row, None)
    lst = _idx_col_rows.get(col)
    if lst:
        i = bisect.bisect_left(lst, row)
        if i < len(lst) and lst[i] == row:
            lst.pop(i)
        if not lst:
            _idx_col_rows.pop(col, None)
    t = (data or {}).get('type')
    if t == 'laser':
        _idx_laser.discard(coord)
    elif t == 'latch':
        _idx_latch.discard(coord)
    elif t == 'delay_line':
        _idx_delay.discard(coord)

def _rebuild_indices() -> None:
    _idx_laser.clear(); _idx_latch.clear(); _idx_delay.clear()
    _idx_row_cols.clear(); _idx_col_rows.clear()
    _lit_relay.clear(); _touched_and.clear(); _lit_walls.clear(); _touched_xor.clear()
    for coord, data in grid_data.items():
        _index_track(coord, data)
    _lit_relay.update(c for c, d in grid_data.items()
                    if d.get('type') in _RELAY_TYPES and d.get('is_lit'))
    _touched_and.update(c for c, d in grid_data.items()
                        if d.get('type') == 'and_gate'
                        and (d.get('is_lit') or d.get('axis_inputs') or d.get('perp_inputs')))
current_tool = 0
place_rot = 0
grid_changed = True
cached_ray_segments: List[Segment] = []
paused = False

TOOL_TYPES = ('wall', 'laser', 'mirror', 'coupler', 'and_gate', 'xor_gate', 'latch',
             'delay_line')
SWITCHABLE_TYPES = ('laser',)
TOOL_SPECS = {
    'wall': lambda: {'type': 'wall', 'dir': 0, 'is_lit': False},
    'laser': lambda: {'type': 'laser', 'dir': 0, 'is_on': True},
    'mirror': lambda: {'type': 'mirror', 'dir': 0, 'is_lit': False},
    'coupler': lambda: {'type': 'coupler', 'dir': 0},
    'and_gate': lambda: {'type': 'and_gate', 'dir': 0},
    'xor_gate': lambda: {'type': 'xor_gate', 'dir': 0, 'is_lit': False,
                         'input_dirs': set()},
    'latch': lambda: {'type': 'latch', 'dir': 0, 'is_lit': False, 'state': 0,
                      'in_levels': frozenset()},
    'delay_line': lambda: {'type': 'delay_line', 'dir': 0, 'ticks': delay_line_setting,
                      'is_lit': False, 'inject': set(), 'pipe': [], 'out_ready': ()},
}
_LANG = 'en'
_LANG_LABELS = {'en': 'English', 'zh': '简体中文'}
TEXTS = {
    'en': {
        'tool.wall': 'Wall', 'tool.laser': 'Laser', 'tool.mirror': 'Mirror',
        'tool.coupler': 'Coupler', 'tool.and_gate': 'AND Gate', 'tool.xor_gate': 'XOR Gate',
        'tool.latch': 'Latch', 'tool.delay_line': 'Delay Line',
        'ui.view_info': 'center {r},{c}  zoom {z}x',
        'key.select_tool': 'Select tool   {name}',
        'key.undo': 'Undo', 'key.redo': 'Redo',
        'key.rotate': 'Rotate element', 'key.cycle_rot': 'Cycle place rotation',
        'key.toggle_switch': 'Toggle switch / power',
        'key.paste': 'Stamp-paste slot', 'key.pause': 'Pause / resume',
        'key.perf': 'Toggle perf panel', 'key.save_1': 'Save', 'key.load': 'Load',
        'key.pan_up': 'Pan up', 'key.pan_down': 'Pan down',
        'key.pan_left': 'Pan left', 'key.pan_right': 'Pan right',
        'key.pan_up_alt': 'Pan up  (alt)', 'key.pan_down_alt': 'Pan down  (alt)',
        'key.pan_left_alt': 'Pan left  (alt)', 'key.pan_right_alt': 'Pan right  (alt)',
        'key.zoom_in': 'Zoom in', 'key.zoom_out': 'Zoom out',
        'game.unsaved': 'Unsaved changes - press ESC again to return',
        'game.back_menu': 'Press ESC again to return to menu',
        'game.paused': 'PAUSED',
        'menu.start': 'Start', 'menu.tutorial': 'Tutorial', 'menu.settings': 'Settings',
        'menu.hint': 'Start / Enter / Space to begin    ESC x2 in game returns here',
        'menu.quit_hint': 'Press ESC again to quit',
        'tut.title': 'Help', 'tut.close': '[ESC] back to menu',
        'tut.sec.play': 'HOW TO PLAY', 'tut.sec.elements': 'ELEMENTS', 'tut.sec.tips': 'TIPS',
        'tut.play.place': 'LMB / Enter place   RMB / Del erase',
        'tut.play.select': '{tools} select tools   {rot} / {cyc} rotate   wheel zoom',
        'tut.play.move': '{pan} move   {alt} alt move   MMB drag',
        'tut.play.undo': '{undo} undo  {redo} redo   {del_} erase',
        'tut.play.save': '{save} save   {load} load   {paste} stamp-paste',
        'tut.play.sl': 'Save panel: open it, then operate only with the mouse (Save / Load / Rename / Delete / New buttons); Delete needs a second confirming click.',
        'tut.play.misc': '{pause} pause/resume',
        'tut.play.esc': 'ESC x2 returns to menu   ESC quit from menu',
        'tut.play.solver': 'solver recomputes only on change',
        'tut.play.perf': '{perf} perf panel: FPS / solve ms / cells / undo depth',
        'tut.play.hold': 'Hold Enter / Del to lay/erase a run; one {undo} undoes the whole run',
        'tut.el.wall': 'Wall: solid block, does not conduct light',
        'tut.el.laser': 'Laser: light source, emits a beam each tick along its dir',
        'tut.el.mirror': 'Mirror: reflects 45 degrees, bends the beam by 90 degrees',
        'tut.el.coupler': 'Coupler: merges several beams toward one output',
        'tut.el.and_gate': 'AND gate: lights output only when two adjacent inputs are present',
        'tut.el.xor_gate': 'XOR gate: outputs when 1 or 3 of the 3 inputs are lit (odd parity)',
        'tut.el.latch': 'Latch: self-holds on/off, one bit of memory',
        'tut.el.delay_line': 'Delay line: the only time element, stores N ticks then emits',
        'tut.tip.solver': 'Light is solved within one tick; only delay line carries state',
        'tut.tip.rotate': 'Element dir decides optics; misplaced? press {undo} to undo',
        "tut.tip.corner": "Hotbar corner = each slot's own select-tool key",
        'tut.tip.rebind': 'Rebind any key under Settings > Keybindings',
        'set.tab.theme': 'Theme', 'set.tab.keys': 'Keybindings',
        'set.tab.language': 'Language',
        'set.active': 'Active: {name}',
        'theme.dark': 'Dark', 'theme.light': 'Light', 'theme.high_contrast': 'High Contrast',
        'set.keybind.listening': 'press key...',
        'set.keybind.press': 'Press a new key to bind  Backspace reset  Esc cancel',
        'set.keybind.hint': 'Click a row, then press a key to rebind  conflicts auto-swap',
        'note.delay_preset': 'delay preset now {n} ticks',
        'note.delay_now': 'delay now {n} ticks',
        'note.delay_flush': 'delay line flushed',
        'note.save_fail': 'save slot {slot} FAILED: {err}',
        'note.saved': 'saved slot {slot}  ({cells} cells) -> {dir}',
        'note.load_broken': 'slot {slot} BROKEN: {err}',
        'note.loaded': 'loaded slot {slot}  ({cells} cells)',
        'note.no_save': 'no save yet  (F1 to save)',
        'note.paste_none': 'no save to paste  (F1 to save)',
        'note.paste_broken': 'paste slot {slot} BROKEN: {err}',
        'note.paste_empty': 'paste slot {slot} has no cell',
        'note.paste_out': 'paste slot {slot} -> r{r},c{c}  all {n} cells out of world',
        'note.pasted': 'pasted slot {slot} -> r{r},c{c}  +{cells} cells ({over} over, {out} out)',
        'note.undo_nothing': 'nothing to {label}',
        'note.undo_done': '{label}  {cells} cells ({now} cells now)',
    },
    'zh': {
        'tool.wall': '墙', 'tool.laser': '激光器', 'tool.mirror': '反射镜',
        'tool.coupler': '耦合器',
        'tool.and_gate': '光与门', 'tool.xor_gate': '异或门', 'tool.latch': '锁存器',
        'tool.delay_line': '延迟线',
        'ui.view_info': '中心坐标 {r},{c}  缩放 {z}x',
        'key.select_tool': '选择工具   {name}',
        'key.undo': '撤销', 'key.redo': '重做',
        'key.rotate': '旋转元件', 'key.cycle_rot': '切换放置朝向',
        'key.toggle_switch': '切换开关 / 电源',
        'key.paste': '图章粘贴存档',
        'key.pause': '暂停或继续',
        'key.perf': '显示或隐藏性能面板',
        'key.save_1': '保存', 'key.load': '读取',
        'key.pan_up': '上移', 'key.pan_down': '下移',
        'key.pan_left': '左移', 'key.pan_right': '右移',
        'key.pan_up_alt': '上移  (备用)', 'key.pan_down_alt': '下移  (备用)',
        'key.pan_left_alt': '左移  (备用)', 'key.pan_right_alt': '右移  (备用)',
        'key.zoom_in': '放大', 'key.zoom_out': '缩小',
        'game.unsaved': '存在未保存的更改 —— 再按一次 ESC 返回',
        'game.back_menu': '再按一次 ESC 返回主菜单',
        'game.paused': '已暂停',
        'menu.start': '开始', 'menu.tutorial': '教学', 'menu.settings': '设置',
        'menu.hint': '开始 / 回车 / 空格 进入游戏    游戏内连按两次 ESC 返回此处',
        'menu.quit_hint': '再按一次 ESC 退出程序',
        'tut.title': '帮助', 'tut.close': '[ESC] 返回主菜单',
        'tut.sec.play': '玩法', 'tut.sec.elements': '元件', 'tut.sec.tips': '提示',
        'tut.play.place': '左键 / 回车 放置   右键 / Del 擦除',
        'tut.play.select': '{tools} 选择工具   {rot} / {cyc} 旋转   滚轮缩放',
        'tut.play.move': '{pan} 平移   {alt} 备用平移   中键拖拽',
        'tut.play.undo': '{undo} 撤销  {redo} 重做   {del_} 擦除',
        'tut.play.save': '{save} 保存   {load} 读取   {paste} 图章粘贴',
        'tut.play.sl': '存档界面：全部用鼠标点击按钮操作（保存/读取/重命名/删除/新建），不使用快捷键；删除需再点一次确认。',
        'tut.play.misc': '{pause} 暂停/继续',
        'tut.play.esc': '连按两次 ESC 返回主菜单   主菜单按 ESC 退出程序',
        'tut.play.solver': '求解器仅在场景改动时重新计算',
        'tut.play.perf': '{perf} 性能面板：帧率 / 求解毫秒 / 元件数 / 撤销深度',
        'tut.play.hold': '按住 回车 / Del 可连铺或连擦；一次 {undo} 即可撤销整段',
        'tut.el.wall': '墙：实心方块，不透光',
        'tut.el.laser': '激光器：光源，每个刻沿朝向发出一束光',
        'tut.el.mirror': '反射镜：以 45 度反射，使光束偏转 90 度',
        'tut.el.coupler': '耦合器：把多束光汇聚到一个输出',
        'tut.el.and_gate': '光与门：仅当相邻两方向输入时才输出',
        'tut.el.xor_gate': '异或门：三输入中 1 或 3（奇数）束有光时从输出口发出',
        'tut.el.latch': '锁存器：自保持开或关，存储 1 个比特',
        'tut.el.delay_line': '延迟线：唯一的时序元件，存储 N 刻后再发出',
        'tut.tip.solver': '光路在一个刻内求解完毕；只有延迟线携带状态',
        'tut.tip.rotate': '元件朝向决定光路；放错了？按 {undo} 撤销',
        'tut.tip.corner': '快捷栏角标＝每个格子自身的选工具键',
        'tut.tip.rebind': '在 设置 > 键位 中可以重新绑定任意按键',
        'set.tab.theme': '主题', 'set.tab.keys': '键位', 'set.tab.language': '语言',
        'set.active': '当前：{name}',
        'theme.dark': '深色', 'theme.light': '浅色', 'theme.high_contrast': '高对比',
        'set.keybind.listening': '请按键…',
        'set.keybind.press': '按下一个新键以绑定  Backspace 重置  Esc 取消',
        'set.keybind.hint': '点击一行后再按一个键即可重绑  冲突时自动互换',
        'note.delay_preset': '延迟预设改为 {n} 刻',
        'note.delay_now': '延迟改为 {n} 刻',
        'note.delay_flush': '延迟线已排空',
        'note.save_fail': '保存槽位 {slot} 失败：{err}',
        'note.saved': '已保存槽位 {slot}（共 {cells} 个元件）-> {dir}',
        'note.load_broken': '槽位 {slot} 已损坏：{err}',
        'note.loaded': '已读取槽位 {slot}（共 {cells} 个元件）',
        'note.no_save': '尚无存档（按 F1 保存）',
        'note.paste_none': '没有可粘贴的存档（按 F1 保存）',
        'note.paste_broken': '粘贴槽位 {slot} 已损坏：{err}',
        'note.paste_empty': '粘贴槽位 {slot} 没有任何元件',
        'note.paste_out': '粘贴槽位 {slot} -> 行{r}，列{c}  全部 {n} 个元件越界',
        'note.pasted': '已粘贴槽位 {slot} -> 行{r}，列{c}  增加 {cells} 个元件（覆盖 {over}，越界 {out}）',
        'note.undo_nothing': '没有可{label}的操作',
        'note.undo_done': '{label}：{cells} 个元件（当前共 {now} 个）',
    },
}

THEME_LABEL_KEYS = {
    'Dark': 'theme.dark', 'Light': 'theme.light', 'High Contrast': 'theme.high_contrast',
}

def theme_display(name):
    return trans(THEME_LABEL_KEYS.get(name, name))

TEXTS['en'].update({
    'key.save_1': 'Save/Load menu',
    'key.sl_save': 'Save panel: save', 'key.sl_load': 'Save panel: load',
    'key.sl_rename': 'Save panel: rename',
    'key.sl_delete': 'Save panel: delete',
    'key.sl_new': 'Save panel: new save',
    'sl.title': 'Save / Load', 'sl.slot': 'Slot {slot}',
    'sl.empty': 'empty', 'sl.cells': '{cells} components', 'sl.bad': 'corrupted',
    'sl.btn.save': 'Save', 'sl.btn.load': 'Load', 'sl.btn.del': 'Delete',
    'sl.btn.del.confirm': 'Confirm?',
    'sl.btn.rename': 'Rename',
    'sl.cur': 'world: {cells} components{dirty}', 'sl.dirty': '  (unsaved)',
    'sl.hint': 'Click a row to select  ·  click the buttons to Save / Load / Rename / Delete / New  ·  wheel to scroll  ·  click outside or {cl}/ESC to close',
    'note.deleted': 'deleted save "{slot}"',
    'note.del_fail': 'delete slot {slot} FAILED: {err}',
    'sl.new': '+ New',
    'sl.default_name': 'Save {slot}',
    'sl.count': '{n} save(s) total',
    'sl.edit.tip': 'type name   Enter confirm   Esc cancel',
    'note.renamed': 'renamed to "{name}"',
    'note.rename_fail': 'rename FAILED: {err}',
})
TEXTS['zh'].update({
    'key.save_1': '存档/读档',
    'key.sl_save': '存档界面：保存', 'key.sl_load': '存档界面：读取',
    'key.sl_rename': '存档界面：重命名',
    'key.sl_delete': '存档界面：删除',
    'key.sl_new': '存档界面：新建存档',
    'sl.title': '存档 · 读档', 'sl.slot': '槽位 {slot}',
    'sl.empty': '空', 'sl.cells': '{cells} 个元件', 'sl.bad': '已损坏',
    'sl.btn.save': '保存', 'sl.btn.load': '读取', 'sl.btn.del': '删除',
    'sl.btn.del.confirm': '确认?',
    'sl.btn.rename': '重命名',
    'sl.cur': '当前世界：{cells} 个元件{dirty}', 'sl.dirty': '  （未保存）',
    'sl.hint': '点击一行选中  ·  点右侧按钮操作：保存 / 读取 / 重命名 / 删除 / 新建  ·  滚轮滚动  ·  点空白处或 {cl}/ESC 关闭',
    'note.deleted': '已删除存档“{slot}”',
    'note.del_fail': '删除槽位 {slot} 失败：{err}',
    'sl.new': '＋ 新建',
    'sl.default_name': '存档 {slot}',
    'sl.count': '共 {n} 个存档',
    'sl.edit.tip': '输入名称   回车 确认   Esc 取消',
    'note.renamed': '已重命名为“{name}”',
    'note.rename_fail': '重命名失败：{err}',
})

def trans(key, **kw):
    table = TEXTS.get(_LANG) or TEXTS['en']
    s = table.get(key)
    if s is None:
        s = TEXTS['en'].get(key, key)
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError):
            pass
    return s

def tool_display(i):
    return trans('tool.' + TOOL_TYPES[i])

def tool_names():
    return ['%d %s' % (i + 1, tool_display(i)) for i in range(len(TOOL_TYPES))]

def build_key_action_labels():
    names = tool_names()
    return (
        [('tool_%d' % i, trans('key.select_tool', name=names[i]))
         for i in range(len(TOOL_TYPES))]
        + [('undo', trans('key.undo')), ('redo', trans('key.redo')),
           ('rotate', trans('key.rotate')), ('cycle_rot', trans('key.cycle_rot')),
           ('toggle_switch', trans('key.toggle_switch')),
           ('paste', trans('key.paste')), ('pause', trans('key.pause')),
           ('perf', trans('key.perf'))]
        + [('save_1', trans('key.save_1'))]
        + [('pan_up', trans('key.pan_up')),
           ('pan_down', trans('key.pan_down')),
           ('pan_left', trans('key.pan_left')), ('pan_right', trans('key.pan_right')),
           ('pan_up_alt', trans('key.pan_up_alt')), ('pan_down_alt', trans('key.pan_down_alt')),
           ('pan_left_alt', trans('key.pan_left_alt')),
           ('pan_right_alt', trans('key.pan_right_alt')),
           ('zoom_in', trans('key.zoom_in')), ('zoom_out', trans('key.zoom_out'))]
    )

KEY_ACTION_LABELS = build_key_action_labels()

def set_lang(lang):
    global _LANG, KEY_ACTION_LABELS
    if lang not in TEXTS:
        return
    _LANG = lang
    KEY_ACTION_LABELS = build_key_action_labels()

trace_note = 'ok'

tick_index = 0
delay_line_ready = 0
timeline_present = False
tick_note = ''
delay_line_setting = DELAY_LINE_DEFAULT_TICKS

def _surf() -> pygame.Surface:
    return pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)

def _icon_frames(base: pygame.Surface) -> Dict[int, pygame.Surface]:
    return {d: (base if d == 0 else pygame.transform.rotate(base, -90 * d)) for d in range(4)}

def _rect(surf, color, size):
    off = (ICON_SIZE - size) // 2
    pygame.draw.rect(surf, color, (off, off, size, size))

def _protrude(surf, color):
    off = (ICON_SIZE - ICON_PROTRUDE) // 2
    pygame.draw.rect(surf, color, (off, 0, ICON_PROTRUDE, ICON_PROTRUDE))

def _slash(surf, color, slash):
    if slash:
        a, b = (ICON_INSET, ICON_SIZE - ICON_INSET), (ICON_SIZE - ICON_INSET, ICON_INSET)
    else:
        a, b = (ICON_INSET, ICON_INSET), (ICON_SIZE - ICON_INSET, ICON_SIZE - ICON_INSET)
    pygame.draw.line(surf, color, a, b, ICON_LINE_W)

def _plus(surf, color):
    c = ICON_SIZE / 2.0
    w = ICON_LINE_W
    span = ICON_SIZE - 2 * ICON_INSET
    off = round(c - w / 2.0)
    pygame.draw.rect(surf, color, (off, ICON_INSET, w, span))
    pygame.draw.rect(surf, color, (ICON_INSET, off, span, w))

def _diamond(surf, color, radius):
    cx = cy = ICON_SIZE // 2
    pygame.draw.polygon(surf, color, [(cx, cy - radius), (cx + radius, cy),
                                      (cx, cy + radius), (cx - radius, cy)])

def _make_laser_icon(color):
    surf = _surf(); _rect(surf, color, ICON_MAIN); _protrude(surf, color); return surf

def _make_wall_icon(color):
    surf = _surf(); _rect(surf, color, ICON_WALL); return surf

def _make_mirror_icon(color):
    surf = _surf(); _slash(surf, color, True); return surf

def _make_xor_icon(color):
    surf = _surf()
    c = ICON_SIZE // 2
    r = ICON_LATCH_R
    bottom = ICON_SIZE - 8
    top = 6
    halfw = ICON_SIZE // 2 - 6
    pts = [(c, top), (c + halfw, bottom), (c - halfw, bottom)]
    if 2 * ICON_LINE_W < r:
        pygame.draw.polygon(surf, color, pts, ICON_LINE_W)
    else:
        pygame.draw.polygon(surf, color, pts)
    return surf

def _make_coupler_icon(color):
    surf = _surf(); c = ICON_SIZE // 2
    pygame.draw.circle(surf, color, (c, c), ICON_RING_R)
    pygame.draw.circle(surf, CLEAR, (c, c), ICON_RING_R - ICON_RING_W)
    _protrude(surf, color)
    return surf

def _make_and_gate_icon(color):
    surf = _surf(); cx = cy = ICON_SIZE // 2
    top = cy - ICON_BAR_LEN // 2
    for left in (cx - ICON_BAR_GAP // 2 - ICON_BAR_W, cx + ICON_BAR_GAP // 2):
        pygame.draw.rect(surf, color, (left, top, ICON_BAR_W, ICON_BAR_LEN))
    return surf

def _make_latch_icon(color):
    surf = _surf()
    _diamond(surf, color, ICON_LATCH_R)
    if ICON_LATCH_R - ICON_LINE_W > 0:
        _diamond(surf, CLEAR, ICON_LATCH_R - ICON_LINE_W)
    if color == COLOR_ON:
        _diamond(surf, color, ICON_LATCH_CORE)
    _protrude(surf, color)
    return surf

def _make_delay_line_icon(color):
    surf = _surf()
    inner = pygame.Rect(ICON_INSET, ICON_INSET, ICON_SIZE - 2 * ICON_INSET,
                        ICON_SIZE - 2 * ICON_INSET)
    pygame.draw.rect(surf, color, inner, ICON_LINE_W)
    _plus(surf, color)
    return surf

def _make_off_mark_icon(color):
    surf = _surf(); _slash(surf, color, True); _slash(surf, color, False); return surf

ICONS: Dict[str, Dict[int, pygame.Surface]] = {}

for _name, _maker in (('wall', _make_wall_icon), ('laser', _make_laser_icon),
                      ('mirror', _make_mirror_icon),
                      ('coupler', _make_coupler_icon), ('xor_gate', _make_xor_icon),
                      ('and_gate', _make_and_gate_icon), ('latch', _make_latch_icon),
                      ('delay_line', _make_delay_line_icon)):
    for _suffix, _color in (('_on', COLOR_ON), ('_off', COLOR_OFF)):
        ICONS[_name + _suffix] = _icon_frames(_maker(_color))

ICONS['off_mark'] = _icon_frames(_make_off_mark_icon(COLOR_ON))

_SCALED_CACHE: Dict[Tuple[str, int, int], pygame.Surface] = {}
SCALED_CACHE_LIMIT = 3000

def blit_icon(name: str, direction: int, screen_x: int, screen_y: int,
              cell_size: int) -> None:
    key = (name, direction, cell_size)
    surf = _SCALED_CACHE.get(key)
    if surf is None:
        base = ICONS[name][direction % 4]
        surf = base if base.get_width() == cell_size else pygame.transform.scale(
            base, (cell_size, cell_size))
        if len(_SCALED_CACHE) >= SCALED_CACHE_LIMIT:
            _SCALED_CACHE.clear()
        _SCALED_CACHE[key] = surf
    screen.blit(surf, (screen_x, screen_y))

def reflected_direction(direction, mirror_dir):
    table = REFLECT_ON_SLASH if mirror_dir % 2 == 0 else REFLECT_ON_BACKSLASH
    return table.get(direction, direction)

def and_gate_ports(out_dir):
    return ((1, 3), (0, 2)) if out_dir % 2 == 0 else ((0, 2), (1, 3))

def latch_ports(out_dir):
    out_dir %= 4
    return out_dir, tuple(d for d in range(4) if d != out_dir)

def _next_cell(row, col, direction):
    d_row, d_col = STEP_BY_DIR[direction]
    return row + d_row, col + d_col

def _cell_center(col, row):
    return (col + 0.5) * BASE_CELL_SIZE, (row + 0.5) * BASE_CELL_SIZE

def _ray_end_at_world_edge(col, row, direction):
    axis, value = EDGE_PX[direction]
    end_x, end_y = _cell_center(col, row)
    return (value, end_y) if axis == 'x' else (end_x, value)

def _in_world_bounds(row, col):
    return -WORLD_HALF_COLS <= col < WORLD_HALF_COLS and -WORLD_HALF_ROWS <= row < WORLD_HALF_ROWS

def _add_segment(segments: List[Segment], start: Point, end: Point) -> None:
    segments.append((start, end))

def _view_range():
    r0 = max(-WORLD_HALF_ROWS, int(camera_y // BASE_CELL_SIZE))
    c0 = max(-WORLD_HALF_COLS, int(camera_x // BASE_CELL_SIZE))
    r1 = min(WORLD_ROWS - WORLD_HALF_ROWS,
             int((camera_y + WINDOW_HEIGHT / zoom) // BASE_CELL_SIZE) + 2)
    c1 = min(WORLD_COLS - WORLD_HALF_COLS,
             int((camera_x + WINDOW_WIDTH / zoom) // BASE_CELL_SIZE) + 2)
    return r0, c0, r1, c1

def _cells_in_range(r0, r1, c0, c1, scan_by_bounds: bool) -> Iterator:
    if scan_by_bounds:
        for row in range(r0, r1):
            for col in range(c0, c1):
                data = grid_data.get((row, col))
                if data is not None:
                    yield row, col, data
    else:
        for (row, col), data in grid_data.items():
            if r0 <= row < r1 and c0 <= col < c1:
                yield row, col, data

def _cells_in_view(r0, r1, c0, c1) -> Iterator:
    if (r1 - r0) <= len(_idx_row_cols):
        for row in range(r0, r1):
            cols = _idx_row_cols.get(row)
            if not cols:
                continue
            lo = bisect.bisect_left(cols, c0)
            hi = bisect.bisect_left(cols, c1, lo)
            for col in cols[lo:hi]:
                data = grid_data.get((row, col))
                if data is not None:
                    yield row, col, data
    else:
        for (row, col), data in grid_data.items():
            if r0 <= row < r1 and c0 <= col < c1:
                yield row, col, data

def screen_to_grid(mouse_x, mouse_y):
    return (int((mouse_y / zoom + camera_y) // BASE_CELL_SIZE),
            int((mouse_x / zoom + camera_x) // BASE_CELL_SIZE))

def clamp_camera():
    global camera_x, camera_y
    view_width, view_height = WINDOW_WIDTH / zoom, WINDOW_HEIGHT / zoom
    if view_width >= WORLD_WIDTH_PX:
        camera_x = float(WORLD_MIN_PX)
    else:
        camera_x = max(float(WORLD_MIN_PX), min(camera_x, WORLD_MAX_PX - view_width))
    if view_height >= WORLD_HEIGHT_PX:
        camera_y = float(WORLD_MIN_PY)
    else:
        camera_y = max(float(WORLD_MIN_PY), min(camera_y, WORLD_MAX_PY - view_height))

@dataclass
class TraceCtx:
    segments: List[Segment] = field(default_factory=list)
    pending: Deque[RaySeed] = field(default_factory=deque)
    hit_lasers: Set[Coord] = field(default_factory=set)
    seen: Set[RayState] = field(default_factory=set)
    lit_relay: Set[Coord] = field(default_factory=set)
    lit_focus: Set[Coord] = field(default_factory=set)
    lit_walls: Set[Coord] = field(default_factory=set)
    touched_and_gates: Set[Coord] = field(default_factory=set)
    touched_latchs: Set[Coord] = field(default_factory=set)
    touched_delay_lines: Set[Coord] = field(default_factory=set)
    touched_xors: Set[Coord] = field(default_factory=set)
    delay_line_injects: Dict[Coord, Set[int]] = field(default_factory=dict)
    rays: int = 0
    steps: int = 0
    deadline: float = 0.0
    aborted: bool = False
    abort_reason: str = ''

def _reset_cell_dynamic(coord: Coord, data: dict, dark: Optional[Set[Coord]] = None,
                        and_gate_lit: Optional[bool] = None) -> None:
    element_type = data['type']
    if element_type == 'laser':
        data['is_lit'] = bool(data.get('is_on', True)) and not (dark and coord in dark)
    elif element_type == 'and_gate':
        data['axis_inputs'] = set()
        data['perp_inputs'] = set()
        data['is_lit'] = False if and_gate_lit is None else bool(and_gate_lit)
    elif element_type == 'latch':
        data['is_lit'] = bool(data.get('state'))
        data['input_dirs'] = set()
    elif element_type in ('coupler', 'mirror'):
        data['is_lit'] = False
    elif element_type == 'xor_gate':
        data['input_dirs'] = set()
        data['is_lit'] = False
    elif element_type == 'wall':
        data['is_lit'] = False
    elif element_type == 'delay_line':
        data['is_lit'] = bool(data.get('out_ready'))

def _wipe(coord: Coord, dark: Optional[Set[Coord]] = None,
          and_gate_lit: Optional[bool] = None) -> Optional[dict]:
    data = grid_data.get(coord)
    if data is None:
        return None
    _reset_cell_dynamic(coord, data, dark, and_gate_lit)
    return data

def _baseline_reset() -> Tuple[List[Coord], Set[Coord], List[Coord], List[Coord]]:
    laser_on: List[Coord] = []
    emitting_stones: Set[Coord] = set()
    latch_coords: List[Coord] = []
    delay_line_coords: List[Coord] = []
    for coord in _idx_delay:
        data = grid_data.get(coord)
        if data is None:
            continue
        _reset_cell_dynamic(coord, data)
        delay_line_coords.append(coord)
    for coord in _idx_latch:
        data = grid_data.get(coord)
        if data is None:
            continue
        _reset_cell_dynamic(coord, data)
        latch_coords.append(coord)
        if data['is_lit']:
            emitting_stones.add(coord)
    for coord in _idx_laser:
        data = grid_data.get(coord)
        if data is None:
            continue
        _reset_cell_dynamic(coord, data)
        if data['is_lit']:
            laser_on.append(coord)
    for coord in _lit_relay:
        data = grid_data.get(coord)
        if data is not None and data.get('type') in _RELAY_TYPES:
            data['is_lit'] = False
    for coord in _lit_walls:
        data = grid_data.get(coord)
        if data is not None and data.get('type') == 'wall':
            data['is_lit'] = False
    for coord in _touched_xor:
        data = grid_data.get(coord)
        if data is not None and data.get('type') == 'xor_gate':
            data['is_lit'] = False
            data['input_dirs'] = set()
    for coord in _touched_and:
        data = grid_data.get(coord)
        if data is not None and data.get('type') == 'and_gate':
            data['axis_inputs'] = set()
            data['perp_inputs'] = set()
            data['is_lit'] = False
    return laser_on, emitting_stones, latch_coords, delay_line_coords

def _incremental_reset(prev: TraceCtx, dark: Set[Coord], lit_and_gates: Set[Coord]) -> None:
    for coord in prev.lit_relay | prev.lit_focus:
        _wipe(coord, dark)
    for coord in prev.touched_and_gates | lit_and_gates:
        _wipe(coord, dark, and_gate_lit=coord in lit_and_gates)
    for coord in prev.touched_latchs | prev.touched_delay_lines:
        _wipe(coord, dark)
    for coord in prev.lit_walls:
        _wipe(coord, dark)
    for coord in prev.touched_xors:
        _wipe(coord, dark)

def _seed_rays(emitting_lasers: Set[Coord], emitting_stones: Set[Coord],
               delay_line_seeds: Optional[List[RaySeed]] = None) -> List[RaySeed]:
    return [(r, c, grid_data[(r, c)]['dir'])
            for group in (sorted(emitting_lasers), sorted(emitting_stones)) for r, c in group] \
        + sorted(delay_line_seeds or [])

def _abort_trace(ctx: TraceCtx, reason: str) -> None:
    if not ctx.aborted:
        ctx.aborted = True
        ctx.abort_reason = reason

def _spawn_ray(ctx: TraceCtx, row: int, col: int, direction: int) -> bool:
    if ctx.aborted:
        return False
    if ctx.rays + len(ctx.pending) >= MAX_RAYS_PER_ROUND:
        _abort_trace(ctx, 'rays>%d' % MAX_RAYS_PER_ROUND)
        return False
    ctx.pending.append((row, col, direction))
    return True

def _handle_laser(ctx, coord, hit_data, _direction):
    ctx.hit_lasers.add(coord)

def _handle_mirror(ctx, coord, hit_data, direction):
    hit_data['is_lit'] = True
    ctx.lit_relay.add(coord)
    return coord, reflected_direction(direction, hit_data['dir']), _cell_center(coord[1], coord[0])

def _handle_xor(ctx, coord, hit_data, direction):
    out_dir = hit_data['dir'] % 4
    ctx.touched_xors.add(coord)
    entry_edge = (direction + 2) % 4
    if entry_edge != out_dir:
        hit_data.setdefault('input_dirs', set()).add(entry_edge)
    return None

def _handle_coupler(ctx, coord, hit_data, direction):
    output_dir = hit_data['dir']
    if hit_data.get('is_lit'):
        return None
    if direction == (output_dir + 2) % 4:
        hit_data['is_lit'] = True
        ctx.lit_focus.add(coord)
        _spawn_ray(ctx, coord[0], coord[1], (output_dir + 1) % 4)
        _spawn_ray(ctx, coord[0], coord[1], (output_dir + 3) % 4)
        return None
    hit_data['is_lit'] = True
    ctx.lit_focus.add(coord)
    _spawn_ray(ctx, coord[0], coord[1], output_dir)
    return None

def _handle_and_gate(ctx, coord, hit_data, direction):
    axis_dirs, perp_dirs = and_gate_ports(hit_data['dir'])
    ctx.touched_and_gates.add(coord)
    if direction in perp_dirs:
        hit_data.setdefault('perp_inputs', set()).add(direction)
        return None
    hit_data.setdefault('axis_inputs', set()).add(direction)
    if hit_data.get('is_lit'):
        return coord, direction, _cell_center(coord[1], coord[0])

def _handle_latch(ctx, coord, hit_data, direction):
    _, input_dirs = latch_ports(hit_data['dir'])
    entry_edge = (direction + 2) % 4
    if entry_edge in input_dirs:
        hit_data['input_dirs'].add(entry_edge)
        ctx.touched_latchs.add(coord)

def _handle_delay_line(ctx, coord, hit_data, direction):
    ctx.delay_line_injects.setdefault(coord, set()).add(direction)
    hit_data['is_lit'] = True
    ctx.touched_delay_lines.add(coord)

def _handle_wall(ctx, coord, hit_data, direction):
    if hit_data.get('type') == 'wall':
        hit_data['is_lit'] = True
        ctx.lit_walls.add(coord)

ELEMENT_HANDLERS: Dict[str, Callable[..., HandlerResult]] = {
    'wall': _handle_wall, 'laser': _handle_laser, 'mirror': _handle_mirror,
    'coupler': _handle_coupler, 'and_gate': _handle_and_gate, 'xor_gate': _handle_xor,
    'latch': _handle_latch, 'delay_line': _handle_delay_line,
}

def _next_occupied(row: int, col: int, direction: int) -> Optional[Coord]:
    if direction == 0:
        lst = _idx_col_rows.get(col)
        i = (bisect.bisect_left(lst, row) - 1) if lst else -1
        return (lst[i], col) if lst and i >= 0 else None
    if direction == 2:
        lst = _idx_col_rows.get(col)
        i = bisect.bisect_right(lst, row) if lst else 0
        return (lst[i], col) if lst and i < len(lst) else None
    if direction == 1:
        lst = _idx_row_cols.get(row)
        i = bisect.bisect_right(lst, col) if lst else 0
        return (row, lst[i]) if lst and i < len(lst) else None
    lst = _idx_row_cols.get(row)
    i = (bisect.bisect_left(lst, col) - 1) if lst else -1
    return (row, lst[i]) if lst and i >= 0 else None

def _trace_one_ray(ctx: TraceCtx) -> None:
    segments, pending, seen = ctx.segments, ctx.pending, ctx.seen
    cur_row, cur_col, direction = pending.popleft()
    ctx.rays += 1
    start = _cell_center(cur_col, cur_row)

    for _step in range(MAX_RAY_STEPS):
        hit = _next_occupied(cur_row, cur_col, direction)
        if hit is None:
            _add_segment(segments, start, _ray_end_at_world_edge(cur_col, cur_row, direction))
            return
        next_row, next_col = hit
        state = (next_row, next_col, direction)
        if state in seen:
            return
        seen.add(state)
        ctx.steps += 1
        if ctx.steps >= MAX_STEPS_PER_ROUND:
            _abort_trace(ctx, 'steps>%d' % MAX_STEPS_PER_ROUND)
        elif len(segments) >= MAX_TRACE_SEGMENTS:
            _abort_trace(ctx, 'segments>%d' % MAX_TRACE_SEGMENTS)
        elif not (ctx.steps & 0xFFF) and time.perf_counter() > ctx.deadline:
            _abort_trace(ctx, 'time>%.2fs' % TRACE_TIME_LIMIT_S)
        if ctx.aborted:
            return
        hit_data = grid_data.get((next_row, next_col))
        if hit_data is None:
            cur_row, cur_col = next_row, next_col
            continue
        _add_segment(segments, start, _cell_center(next_col, next_row))
        handler = ELEMENT_HANDLERS.get(_etype(hit_data), _handle_wall)
        result = handler(ctx, (next_row, next_col), hit_data, direction)
        if result is None:
            return
        (cur_row, cur_col), direction, start = result

    _abort_trace(ctx, 'ray steps>%d' % MAX_RAY_STEPS)

def _collect_lit_and_gates(ctx: TraceCtx) -> Set[Coord]:
    lit: Set[Coord] = set()
    for coord in ctx.touched_and_gates:
        data = grid_data.get(coord)
        if data is not None and data.get('axis_inputs') and data.get('perp_inputs'):
            lit.add(coord)
    return lit

def _collect_lit_xors(ctx: TraceCtx) -> Set[Coord]:
    lit: Set[Coord] = set()
    for coord in ctx.touched_xors:
        data = grid_data.get(coord)
        if (data is not None and data.get('type') == 'xor_gate'
                and len(data.get('input_dirs') or ()) % 2 == 1):
            lit.add(coord)
    return lit

def _advance_latch_states(candidates: List[Coord], armed_latchs: Set[Coord]
                          ) -> Tuple[Set[Coord], Set[Coord]]:
    flipped: Set[Coord] = set()
    armed: Set[Coord] = set(armed_latchs)
    for coord in candidates:
        data = grid_data.get(coord)
        if data is None:
            continue
        _, input_dirs = latch_ports(data['dir'])
        levels = frozenset(d for d in data.get('input_dirs') or () if d in input_dirs)
        previous = data['in_levels']
        if previous is not None:
            rising = len([edge for edge in levels if edge not in previous])
            if rising:
                data['state'] = (data['state'] + rising) % 2
                data['is_lit'] = bool(data['state'])
                flipped.add(coord)
        data['in_levels'] = levels
        if levels:
            armed.add(coord)
        else:
            armed.discard(coord)
    return flipped, armed

def _solve_tick_iter(delay_line_seeds: List[RaySeed],
                     deadline: List[float]) -> Iterator[Tuple[List[Segment], List[Coord], bool]]:
    global trace_note, timeline_present
    laser_on, emitting_latchs, latch_coords, delay_line_coords = _baseline_reset()
    timeline_present = bool(delay_line_coords)
    emitting: Set[Coord] = set(laser_on)
    lit_and_gates: Set[Coord] = set()
    lit_xors: Set[Coord] = set()
    armed_latchs: Set[Coord] = set()
    dark: Set[Coord] = set()
    ctx = TraceCtx()
    used_rounds = 0
    converged = False
    segments: List[Segment] = []
    for round_index in range(MAX_LIGHT_ROUNDS):
        if time.perf_counter() >= deadline[0]:
            yield
        used_rounds = round_index + 1
        if round_index:
            _incremental_reset(ctx, dark, lit_and_gates)
        ctx = TraceCtx()
        segments = ctx.segments
        ctx.pending = deque(_seed_rays(emitting, emitting_latchs, delay_line_seeds))
        for _xc in sorted(lit_xors):
            _xd = grid_data.get(_xc)
            if _xd is not None and _xd.get('type') == 'xor_gate':
                ctx.pending.append((_xc[0], _xc[1], _xd['dir'] % 4))
        ctx.deadline = time.perf_counter() + TRACE_TIME_LIMIT_S
        while ctx.pending and not ctx.aborted:
            _trace_one_ray(ctx)
            if time.perf_counter() >= deadline[0]:
                yield
        if ctx.aborted:
            trace_note = 'TRUNC r%d %s (rays %d steps %d segs %d)' % (
                used_rounds, ctx.abort_reason, ctx.rays, ctx.steps, len(segments))
            break
        new_lit = _collect_lit_and_gates(ctx)
        for coord in new_lit:
            grid_data[coord]['is_lit'] = True
        new_lit_xors = _collect_lit_xors(ctx)
        for coord in lit_xors - new_lit_xors:
            _d = grid_data.get(coord)
            if _d is not None:
                _d['is_lit'] = False
        for coord in new_lit_xors:
            grid_data[coord]['is_lit'] = True
        flipped, armed_latchs = _advance_latch_states(
            latch_coords if round_index == 0 else list(ctx.touched_latchs | armed_latchs),
            armed_latchs)
        newly_dark = ctx.hit_lasers & emitting
        dark |= newly_dark
        if (not newly_dark and new_lit == lit_and_gates and new_lit_xors == lit_xors
                and not flipped):
            converged = True
            break
        emitting -= newly_dark
        lit_and_gates = new_lit
        lit_xors = new_lit_xors
        for coord in flipped:
            if grid_data[coord]['state']:
                emitting_latchs.add(coord)
            else:
                emitting_latchs.discard(coord)
    if not ctx.aborted:
        trace_note = '%s r%d (rays %d steps %d segs %d)' % (
            'ok' if converged else 'MAXR', used_rounds, ctx.rays, ctx.steps, len(segments))
    for coord in dark:
        data = grid_data.get(coord)
        if data is not None:
            data['is_lit'] = False
    for coord, dirs in ctx.delay_line_injects.items():
        data = grid_data.get(coord)
        if data is not None and _etype(data) == 'delay_line':
            data['inject'] = set(dirs)
            data['is_lit'] = True
    _lit_relay.clear()
    _lit_relay.update(ctx.lit_relay)
    _lit_relay.update(ctx.lit_focus)
    _touched_and.clear()
    _touched_and.update(ctx.touched_and_gates)
    _lit_walls.clear()
    _lit_walls.update(ctx.lit_walls)
    _touched_xor.clear()
    _touched_xor.update(ctx.touched_xors)
    return segments, delay_line_coords, ctx.aborted

def solve_tick(delay_line_seeds: List[RaySeed]) -> Tuple[List[Segment], List[Coord], bool]:
    gen = _solve_tick_iter(delay_line_seeds, [float('inf')])
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value

SOLVE_SLICE_BUDGET_S = 0.006

class _SolveJob:
    __slots__ = ('gen', 'deadline', 'advance', 'coords')

    def __init__(self, advance: bool):
        coords = _delay_line_coords()
        seeds = [(row, col, d) for (row, col) in sorted(coords)
                 for d in (grid_data[(row, col)].get('out_ready') or ())]
        self.deadline = [0.0]
        self.gen = _solve_tick_iter(seeds, self.deadline)
        self.advance = advance
        self.coords = coords

_pending_solve: Optional[_SolveJob] = None

def _start_sliced_solve(advance: bool) -> None:
    global _pending_solve
    _pending_solve = _SolveJob(advance=advance)

def _finalize_sliced_solve(job: _SolveJob, segments: List[Segment],
                           aborted: bool) -> List[Segment]:
    global tick_index, tick_note
    if aborted:
        tick_note = 'aborted'
        return segments
    if not job.advance:
        tick_note = 'paused'
        return segments
    _advance_delay_lines(job.coords)
    tick_note = ''
    tick_index = (tick_index + 1) % TICK_DISPLAY_WRAP
    return segments

def _drive_sliced_solve() -> Optional[List[Segment]]:
    global _pending_solve
    job = _pending_solve
    if job is None:
        return None
    job.deadline[0] = time.perf_counter() + SOLVE_SLICE_BUDGET_S
    try:
        next(job.gen)
    except StopIteration as stop:
        segments, _dlc, aborted = stop.value
        _pending_solve = None
        return _finalize_sliced_solve(job, segments, aborted)
    return None

def _delay_line_ticks(data: dict) -> int:
    try:
        ticks = int(data.get('ticks', DELAY_LINE_DEFAULT_TICKS))
    except (TypeError, ValueError):
        ticks = DELAY_LINE_DEFAULT_TICKS
    return max(DELAY_LINE_MIN_TICKS, min(ticks, DELAY_LINE_MAX_TICKS))

def _advance_delay_lines(coords: List[Coord]) -> int:
    global delay_line_ready
    ready = 0
    for coord in coords:
        data = grid_data.get(coord)
        if data is None or _etype(data) != 'delay_line':
            continue
        ticks = _delay_line_ticks(data)
        inject = tuple(sorted(data.get('inject') or ()))
        data['inject'] = set()
        pipe: List[Tuple[int, ...]] = data.setdefault('pipe', [])
        pipe.append(inject)
        data['out_ready'] = pipe.pop(0) if len(pipe) >= ticks else ()
        if len(pipe) > ticks:
            del pipe[:len(pipe) - ticks]
        if data['out_ready']:
            data['is_lit'] = True
            ready += 1
    delay_line_ready = ready
    return ready

def _delay_line_coords() -> List[Coord]:
    return [coord for coord in _idx_delay if coord in grid_data]

def reset_timeline(reason: str = '') -> None:
    global tick_index, tick_note, timeline_present
    tick_index = 0
    if not timeline_present:
        tick_note = ('reset: %s' % reason) if reason else 'timeline reset'
        return
    for coord in list(_idx_delay):
        data = grid_data.get(coord)
        if data is not None and _etype(data) == 'delay_line':
            data['pipe'] = []
            data['out_ready'] = ()
            data['inject'] = set()
            data['is_lit'] = False
    tick_note = ('reset: %s' % reason) if reason else 'timeline reset'

def step_tick(advance: bool = True) -> List[Segment]:
    global tick_index, tick_note
    coords = _delay_line_coords()
    delay_line_seeds = [(row, col, d) for (row, col) in sorted(coords)
                        for d in (grid_data[(row, col)].get('out_ready') or ())]
    segments, _, aborted = solve_tick(delay_line_seeds)
    if aborted:
        tick_note = 'aborted'
        return segments
    if not advance:
        tick_note = 'paused'
        return segments
    _advance_delay_lines(coords)
    tick_note = ''
    tick_index = (tick_index + 1) % TICK_DISPLAY_WRAP
    return segments

_HOVER_CACHE: Dict[int, pygame.Surface] = {}

def _hover_surface(cell_size: int) -> pygame.Surface:
    surf = _HOVER_CACHE.get(cell_size)
    if surf is None:
        surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
        surf.fill(_tint(COLOR_ON, 45))
        _HOVER_CACHE[cell_size] = surf
    return surf

def _draw_element(data: dict, screen_x: int, screen_y: int, cell_size: int) -> None:
    element_type = _etype(data)
    name = '%s_%s' % (element_type, 'on' if data.get('is_lit', False) else 'off')
    blit_icon(name, data['dir'], screen_x, screen_y, cell_size)
    if element_type in SWITCHABLE_TYPES and not data.get('is_on', True):
        blit_icon('off_mark', 0, screen_x, screen_y, cell_size)

def _draw_cells_in_view(hover_row, hover_col) -> None:
    start_row, start_col, end_row, end_col = _view_range()
    cell_size = int(round(BASE_CELL_SIZE * zoom))
    view_w, view_h = screen.get_size()

    for row in range(start_row, end_row + 1):
        line_y = int(round((row * BASE_CELL_SIZE - camera_y) * zoom))
        pygame.draw.line(screen, COLOR_GRID, (0, line_y), (view_w, line_y), 1)
    for col in range(start_col, end_col + 1):
        line_x = int(round((col * BASE_CELL_SIZE - camera_x) * zoom))
        pygame.draw.line(screen, COLOR_GRID, (line_x, 0), (line_x, view_h), 1)

    if hover_row is not None:
        screen.blit(_hover_surface(cell_size),
                    (int(round((hover_col * BASE_CELL_SIZE - camera_x) * zoom)),
                     int(round((hover_row * BASE_CELL_SIZE - camera_y) * zoom))))

    for row, col, data in _cells_in_view(start_row, end_row, start_col, end_col):
        _draw_element(data, int(round((col * BASE_CELL_SIZE - camera_x) * zoom)),
                      int(round((row * BASE_CELL_SIZE - camera_y) * zoom)), cell_size)

def _draw_rays(ray_segments: List[Segment]) -> None:
    if not ray_segments:
        return
    line_width = max(2, int(BASE_CELL_SIZE * 0.1 * zoom))
    view_w, view_h = screen.get_size()
    inv = 1.0 / zoom
    margin = line_width * inv + BASE_CELL_SIZE
    vx0 = camera_x - margin
    vx1 = camera_x + view_w * inv + margin
    vy0 = camera_y - margin
    vy1 = camera_y + view_h * inv + margin
    draw_line = pygame.draw.line
    for (x1, y1), (x2, y2) in ray_segments:
        if (x1 < vx0 and x2 < vx0) or (x1 > vx1 and x2 > vx1) or \
           (y1 < vy0 and y2 < vy0) or (y1 > vy1 and y2 > vy1):
            continue
        draw_line(screen, COLOR_ON,
                  (int(round((x1 - camera_x) * zoom)), int(round((y1 - camera_y) * zoom))),
                  (int(round((x2 - camera_x) * zoom)), int(round((y2 - camera_y) * zoom))),
                  line_width)

_game_glow_cache: dict = {}

def _build_game_glow(win_w, win_h) -> pygame.Surface:
    return _build_bg_gradient(win_w, win_h, with_grid=False)

def _draw_game_glow() -> None:
    win_w, win_h = screen.get_size()
    key = (win_w, win_h)
    glow = _game_glow_cache.get(key)
    if glow is None:
        _game_glow_cache.clear()
        glow = _build_game_glow(win_w, win_h)
        _game_glow_cache[key] = glow
    screen.blit(glow, (0, 0))

def draw_scene(ray_segments: List[Segment]) -> None:
    _draw_game_glow()
    mouse_pos = pygame.mouse.get_pos()
    _ui_hover = hotbar_index_at(mouse_pos) is not None
    hover_row, hover_col = (None, None) if _ui_hover else screen_to_grid(*mouse_pos)
    _draw_cells_in_view(hover_row, hover_col)
    _draw_rays(ray_segments)
    draw_hotbar()

_CN_FONT_CANDIDATES = (
    os.path.join('fonts', 'SourceHanSansSC.otf'),
    'SourceHanSansSC.otf',
)
_font_cache = {}

def _load_font(size, bold=False):
    key = (size, bool(bold))
    font = _font_cache.get(key)
    if font is not None:
        return font
    font = None
    for rel in _CN_FONT_CANDIDATES:
        path = resource_path(rel)
        if os.path.exists(path):
            try:
                font = pygame.font.Font(path, size)
                break
            except Exception:
                font = None
    if font is None:
        font = pygame.font.SysFont('consolas,menlo,monospace', size)
    if bold:
        font.set_bold(True)
    _font_cache[key] = font
    return font

def _text(font, text, cache, limit, bg_pad=None):
    pair = cache.get(text)
    if pair is None:
        surf = font.render(text, True, COLOR_ON)
        if bg_pad is None:
            value = surf
        else:
            bg = pygame.Surface((surf.get_width() + bg_pad[0], surf.get_height() + bg_pad[1]),
                                pygame.SRCALPHA)
            bg.fill(_tint(COLOR_BG, 80))
            value = (surf, bg)
        if len(cache) >= limit:
            cache.clear()
        cache[text] = value
        return value
    return pair

HOTBAR_FONT = _load_font(11)
HOTBAR_NAME_FONT = _load_font(24)
HOTBAR_NUM_FONT  = _load_font(20, bold=True)

def _hotbar_rects() -> List[pygame.Rect]:
    n = len(TOOL_TYPES)
    step = HOTBAR_CELL + HOTBAR_GAP
    total = n * step - HOTBAR_GAP
    win_w, win_h = screen.get_size()
    group_total = HOTBAR_CELL + HOTBAR_GAP + total
    left = max(4, (win_w - group_total) // 2)
    x0 = left + HOTBAR_CELL + HOTBAR_GAP
    y0 = win_h - HOTBAR_CELL - HOTBAR_BOTTOM_PAD
    return [pygame.Rect(x0 + i * step, y0, HOTBAR_CELL, HOTBAR_CELL) for i in range(n)]

def hotbar_index_at(pos) -> Optional[int]:
    for i, rect in enumerate(_hotbar_rects()):
        if rect.collidepoint(pos):
            return i
    return None

def _rotate_btn_rect() -> pygame.Rect:
    rects = _hotbar_rects()
    first = rects[0]
    return pygame.Rect(max(4, first.x - HOTBAR_GAP - HOTBAR_CELL), first.y, HOTBAR_CELL, HOTBAR_CELL)

def _is_ui_pos(pos) -> bool:
    if hotbar_index_at(pos) is not None:
        return True
    return _rotate_btn_rect().collidepoint(pos)

def _hotbar_icon_name(tool_type: str, selected: bool) -> str:
    return tool_type + ('_on' if selected else '_off')

def draw_hotbar() -> None:
    rects = _hotbar_rects()
    for i, rect in enumerate(rects):
        selected = (i == current_tool)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_BG, 130))
        screen.blit(bg, rect.topleft)
        side = HOTBAR_CELL - 8
        sx = rect.x + (rect.w - side) // 2
        sy = rect.y + (rect.h - side) // 2
        blit_icon(_hotbar_icon_name(TOOL_TYPES[i], selected), place_rot, sx, sy, side)
        pygame.draw.rect(screen, COLOR_ON if selected else COLOR_OFF,
                         rect, 3 if selected else 1)
        num_col = COLOR_ON if selected else COLOR_OFF
        key_str = _key_label(KEYMAP['tool_%d' % i])
        shadow = HOTBAR_NUM_FONT.render(key_str, True, (0, 0, 0))
        num = HOTBAR_NUM_FONT.render(key_str, True, num_col)
        screen.blit(shadow, (rect.x + 4, rect.y))
        screen.blit(num,    (rect.x + 3, rect.y - 1))
    label = HOTBAR_NAME_FONT.render(tool_display(current_tool), True, COLOR_ON)
    rot_btn = _rotate_btn_rect()
    lx = (rot_btn.x + rects[-1].right) // 2 - label.get_width() // 2
    ly = rects[0].top - label.get_height() - 4
    screen.blit(label, (lx, ly))
    _draw_rotate_btn()

def _draw_ui_button(rect, active, draw_icon, label) -> None:
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(_tint(COLOR_BG, 130))
    screen.blit(bg, rect.topleft)
    draw_icon(active)
    col = COLOR_ON if active else COLOR_OFF
    pygame.draw.rect(screen, col, rect, 3 if active else 1)
    if label:
        shadow = HOTBAR_NUM_FONT.render(label, True, (0, 0, 0))
        txt = HOTBAR_NUM_FONT.render(label, True, col)
        screen.blit(shadow, (rect.x + 4, rect.y))
        screen.blit(txt, (rect.x + 3, rect.y - 1))

def _draw_rotate_btn() -> None:
    rot = _rotate_btn_rect()

    def _icon(active):
        col = COLOR_ON if active else COLOR_OFF
        cx, cy = rot.center; rad = rot.w // 3
        ring_w = 5
        r_in, r_out = rad - ring_w / 2.0, rad + ring_w / 2.0
        r_mid = (r_in + r_out) / 2.0
        pygame.draw.circle(screen, col, (cx, cy), rad, ring_w)
        import math as _m
        s = 16.0
        _H = s * _m.sqrt(3) / 2.0
        wx, wy = cx - r_mid * 0.8, cy
        pygame.draw.polygon(screen, col,
                            [(wx, wy - 2 * _H / 3),
                             (wx - s / 2, wy + _H / 3),
                             (wx + s / 2, wy + _H / 3)])
        ex, ey = cx + r_mid * 0.8, cy
        ew, eh = 16.0, 15.0
        pygame.draw.polygon(screen, col,
                            [(ex, ey + 2 * eh / 3),
                             (ex - ew / 2, ey - eh / 3),
                             (ex + ew / 2, ey - eh / 3)])

    _draw_ui_button(rot, bool(place_rot), _icon, _key_label(KEY_CYCLE_PLACE_ROT))

TOOL_KEY_MAP = {KEY_TOOL_BASE + i: i for i in range(len(TOOL_TYPES))}
is_dragging = False
last_mouse_pos = (0, 0)
delete_held = False
place_held = False
_place_last_coord = None
_stroke_last_coord: Optional[Coord] = None

_stroke_active = False
_stroke_capture: Dict[Coord, Optional[dict]] = {}

def _stroke_begin() -> None:
    global _stroke_active, _stroke_last_coord
    _stroke_active = True
    _stroke_last_coord = None
    _stroke_capture.clear()

def _stroke_capture_cell(coord: Coord) -> None:
    if coord not in _stroke_capture:
        _stroke_capture[coord] = copy.deepcopy(grid_data.get(coord))

def _stroke_commit() -> None:
    global _stroke_active
    if not _stroke_active:
        return
    _stroke_active = False
    if _stroke_capture:
        undo_stack.append(list(_stroke_capture.items()))
        del undo_stack[:-UNDO_LIMIT]
        del redo_stack[:]
    _stroke_capture.clear()

def _bresenham_cells(r0: int, c0: int, r1: int, c1: int) -> List[Coord]:
    cells: List[Coord] = []
    dr, dc = abs(r1 - r0), abs(c1 - c0)
    sr = 1 if r0 < r1 else -1
    sc = 1 if c0 < c1 else -1
    err = dr - dc
    r, c = r0, c0
    while True:
        cells.append((r, c))
        if r == r1 and c == c1:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            r += sr
        if e2 < dr:
            err += dr
            c += sc
    return cells

def place_element(coord: Optional[Coord] = None) -> None:
    global grid_changed, world_dirty
    if coord is None:
        coord = _cursor_coord()
    if not _in_world_bounds(*coord):
        return
    if _stroke_active:
        _stroke_capture_cell(coord)
    else:
        push_undo([coord])
    new_data = TOOL_SPECS[TOOL_TYPES[current_tool]]()
    if place_rot:
        new_data['dir'] = (new_data['dir'] + place_rot) % 4
    _index_untrack(coord, grid_data.get(coord))
    _index_track(coord, new_data)
    grid_data[coord] = new_data
    reset_timeline('place')
    grid_changed = world_dirty = True

def erase_element(coord: Optional[Coord] = None) -> None:
    global grid_changed, world_dirty
    if coord is None:
        coord = _cursor_coord()
    if coord not in grid_data:
        return
    if _stroke_active:
        _stroke_capture_cell(coord)
    else:
        push_undo([coord])
    _index_untrack(coord, grid_data.pop(coord))
    reset_timeline('erase')
    grid_changed = world_dirty = True

def delete_erase_at_cursor() -> None:
    global _stroke_last_coord
    _mp = pygame.mouse.get_pos()
    if _is_ui_pos(_mp):
        _stroke_last_coord = None
        return
    coord = _cursor_coord()
    prev = _stroke_last_coord
    if prev is not None:
        for cell in _bresenham_cells(prev[0], prev[1], coord[0], coord[1]):
            if cell != prev:
                erase_element(cell)
    else:
        erase_element(coord)
    _stroke_last_coord = coord

def place_at_cursor() -> None:
    global _place_last_coord, _stroke_last_coord
    _mp = pygame.mouse.get_pos()
    if _is_ui_pos(_mp):
        _stroke_last_coord = None
        return
    coord = _cursor_coord()
    if coord == _place_last_coord:
        return
    prev = _stroke_last_coord
    if prev is not None:
        for cell in _bresenham_cells(prev[0], prev[1], coord[0], coord[1]):
            if cell != prev:
                place_element(cell)
    else:
        place_element(coord)
    _place_last_coord = _stroke_last_coord = coord

def _cursor_coord() -> Coord:
    return screen_to_grid(*pygame.mouse.get_pos())

def _cursor_element() -> Optional[dict]:
    return grid_data.get(_cursor_coord())

def rotate_element(step: int) -> None:
    global grid_changed, world_dirty, delay_line_setting
    data = _cursor_element()
    if data is None:
        if TOOL_TYPES[current_tool] != 'delay_line':
            return
        new_setting = max(DELAY_LINE_MIN_TICKS, min(delay_line_setting + step, DELAY_LINE_MAX_TICKS))
        if new_setting == delay_line_setting:
            return
        delay_line_setting = new_setting
        _note(trans('note.delay_preset', n=delay_line_setting))
        return
    if _etype(data) == 'delay_line':
        new_ticks = _delay_line_ticks(data)
        new_ticks = max(DELAY_LINE_MIN_TICKS, min(new_ticks + step, DELAY_LINE_MAX_TICKS))
        if new_ticks == _delay_line_ticks(data):
            return
        push_undo([_cursor_coord()])
        data['ticks'] = new_ticks
        data['pipe'] = []
        data['out_ready'] = ()
        _note(trans('note.delay_now', n=new_ticks))
    else:
        push_undo([_cursor_coord()])
        data['dir'] = (data['dir'] + step) % 4
        if _etype(data) == 'latch':
            data['in_levels'] = None
    reset_timeline('rotate')
    grid_changed = world_dirty = True

def toggle_switch() -> None:
    global grid_changed, world_dirty
    data = _cursor_element()
    if data is None:
        return
    element_type = _etype(data)
    if element_type not in SWITCHABLE_TYPES and element_type not in ('latch', 'delay_line'):
        return
    push_undo([_cursor_coord()])
    if element_type in SWITCHABLE_TYPES:
        data['is_on'] = not data.get('is_on', True)
    elif element_type == 'latch':
        data['state'] = 1 - (int(data.get('state', 0) or 0) % 2)
        data['in_levels'] = None
    else:
        data['pipe'] = []
        data['out_ready'] = ()
        data['inject'] = set()
        _note(trans('note.delay_flush'))
    reset_timeline('toggle')
    grid_changed = world_dirty = True

def drag_camera() -> None:
    global camera_x, camera_y, last_mouse_pos
    mouse_x, mouse_y = pygame.mouse.get_pos()
    camera_x -= (mouse_x - last_mouse_pos[0]) / zoom
    camera_y -= (mouse_y - last_mouse_pos[1]) / zoom
    last_mouse_pos = (mouse_x, mouse_y)
    clamp_camera()

def zoom_camera(wheel_y: int) -> None:
    global zoom, camera_x, camera_y
    mouse_x, mouse_y = pygame.mouse.get_pos()
    old_zoom = zoom
    if wheel_y > 0:
        factor = 1.0 / ZOOM_FACTOR
    elif wheel_y < 0:
        factor = ZOOM_FACTOR
    else:
        return
    zoom = max(MIN_ZOOM, min(zoom * factor, MAX_ZOOM))
    camera_x += mouse_x * (1 / old_zoom - 1 / zoom)
    camera_y += mouse_y * (1 / old_zoom - 1 / zoom)
    clamp_camera()

PAN_KEYS = ((KEY_PAN_LEFT, KEY_PAN_LEFT_ALT, 'x', -1), (KEY_PAN_RIGHT, KEY_PAN_RIGHT_ALT, 'x', 1),
            (KEY_PAN_UP, KEY_PAN_UP_ALT, 'y', -1), (KEY_PAN_DOWN, KEY_PAN_DOWN_ALT, 'y', 1))

def pan_camera(dt: float) -> None:
    global camera_x, camera_y
    keys = pygame.key.get_pressed()
    pan_speed = PAN_SPEED_PX * dt / zoom
    for key_a, key_b, axis, factor in PAN_KEYS:
        if keys[key_a] or keys[key_b]:
            if axis == 'x':
                camera_x += pan_speed * factor
            else:
                camera_y += pan_speed * factor

def handle_event(event):
    global current_tool, WINDOW_WIDTH, WINDOW_HEIGHT, is_dragging, delete_held
    global place_held, _place_last_coord, _stroke_last_coord, place_rot
    global last_mouse_pos, screen_state, _game_esc_time, perf_visible, paused
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
        clamp_camera()
    if _saveload_open:
        return _handle_saveload_event(event)
    if event.type == pygame.MOUSEBUTTONDOWN:
        hb_idx = hotbar_index_at(event.pos)
        if hb_idx is not None:
            if event.button == 1:
                current_tool = hb_idx
            return True
        _rb = _rotate_btn_rect()
        if _rb.collidepoint(event.pos):
            if event.button == 1:
                place_rot = (place_rot + 1) % 4
            return True
        if event.button == 2:
            is_dragging = True
            last_mouse_pos = pygame.mouse.get_pos()
        elif event.button == PLACE_BTN:
            place_held = True
            _place_last_coord = None
            _stroke_begin()
            place_at_cursor()
        elif event.button == ERASE_BTN:
            delete_held = True
            _stroke_begin()
            delete_erase_at_cursor()
    elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 2:
            is_dragging = False
        elif event.button == PLACE_BTN:
            place_held = False
            _place_last_coord = None
            _stroke_last_coord = None
            _stroke_commit()
        elif event.button == ERASE_BTN:
            delete_held = False
            _stroke_last_coord = None
            _stroke_commit()
    elif event.type == pygame.MOUSEMOTION:
        buttons = event.buttons
        if is_dragging:
            if buttons[1]:
                drag_camera()
            else:
                is_dragging = False
    elif event.type == pygame.MOUSEWHEEL:
        zoom_camera(event.y)
    elif event.type == pygame.KEYDOWN:
        if event.key in TOOL_KEY_MAP:
            current_tool = TOOL_KEY_MAP[event.key]
        elif event.key in (KEYMAP['zoom_in'], pygame.K_KP_PLUS):
            zoom_camera(1)
        elif event.key in (KEYMAP['zoom_out'], pygame.K_KP_MINUS):
            zoom_camera(-1)
        elif event.key == KEY_TOGGLE_SWITCH:
            toggle_switch()
        elif event.key == KEY_ROTATE_ELEMENT:
            rotate_element(1)
        elif event.key == KEY_CYCLE_PLACE_ROT:
            place_rot = (place_rot + 1) % 4
        elif event.key == KEY_UNDO:
            undo()
        elif event.key == KEY_REDO:
            redo()
        elif event.key == KEY_SAVE_MENU:
            _open_saveload()
        elif event.key == KEY_LOAD_SLOT:
            load_recent_slot()
        elif event.key == KEY_TOGGLE_PERF:
            perf_visible = not perf_visible
        elif event.key == KEY_TOGGLE_PAUSE:
            paused = not paused
        elif event.key == KEY_PASTE_SLOT:
            paste_slot_at_cursor()
        elif event.key == KEY_BACK:
            now = pygame.time.get_ticks()
            if now - _game_esc_time < _ESC_RETURN_WIN:
                delete_held = place_held = is_dragging = False
                _place_last_coord = None
                screen_state = 'menu'
                _game_esc_time = 0
            else:
                _game_esc_time = now
    return True

undo_stack: List[List[Tuple[Coord, Optional[dict]]]] = []
redo_stack: List[List[Tuple[Coord, Optional[dict]]]] = []
world_dirty = False
last_slot = 0
_last_slot_by_mtime = 0
save_status: Dict[int, str] = {}

_slot_meta: Dict[int, dict] = {}
_slot_names: Dict[int, str] = {}
_sl_slots: List[int] = []
_sl_scroll: int = 0
_sl_edit_slot: int = -1
_sl_edit_buf: str = ''
_sl_del_confirm_slot: int = -1
_message = ''
_message_until = 0.0

def _note(msg: str) -> None:
    global _message, _message_until
    _message = msg
    _message_until = time.perf_counter() + MESSAGE_TTL_S

def _slot_path(slot: int) -> str:
    return os.path.join(SAVE_DIR, 'slot%d.json' % slot)

def _discover_slots() -> List[int]:
    found = set()
    try:
        names = os.listdir(SAVE_DIR)
    except OSError:
        return []
    for fn in names:
        if fn.startswith('slot') and fn.endswith('.json'):
            core = fn[4:-5]
            if core.isdigit():
                found.add(int(core))
    return sorted(found)

def _next_free_slot() -> int:
    used = set(_discover_slots()) | set(_slot_names.keys())
    n = 1
    while n in used:
        n += 1
    return n

def _slot_display_name(slot: int) -> str:
    nm = _slot_names.get(slot)
    if isinstance(nm, str) and nm.strip():
        return nm.strip()
    return trans('sl.default_name', slot=slot)

def _rename_slot(slot: int, new_name: str) -> bool:
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return False
    clean = (new_name or '').strip()[:32]
    final = clean or trans('sl.default_name', slot=slot)
    _slot_names[slot] = final
    path = _slot_path(slot)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                doc = json.load(fh)
            if not isinstance(doc, dict):
                doc = {'cells': {}}
            doc['name'] = final
            with open(path + '.tmp', 'w', encoding='utf-8') as fh:
                json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
            os.replace(path + '.tmp', path)
        except (OSError, ValueError) as exc:
            _note(trans('note.rename_fail', err=exc))
            return False
    _note(trans('note.renamed', name=final))
    _refresh_slot_status()
    return True

def _encode_levels(value):
    return -1 if value is None else sorted(int(d) for d in value)

def _decode_levels(value) -> Optional[frozenset]:
    if value is None or value == -1:
        return None
    try:
        return frozenset(int(d) for d in value)
    except (TypeError, ValueError):
        return None

def serialize_world(with_camera: bool = True) -> dict:
    cells = {}
    for (row, col), data in grid_data.items():
        etype = _etype(data)
        fields = PERSIST_FIELDS.get(etype)
        if fields is None:
            continue
        item = {'type': etype}
        for f in fields:
            if f == 'in_levels':
                item[f] = _encode_levels(data[f])
                continue
            v = data.get(f)
            if f == 'dir' and v == 0:
                continue
            if f == 'is_on' and v is True:
                continue
            if f == 'state' and v == 0:
                continue
            item[f] = v
        cells['%d,%d' % (row, col)] = item
    out = {'version': SAVE_VERSION, 'cells': cells}
    if with_camera:
        out['camera'] = {'camera_x': camera_x, 'camera_y': camera_y, 'zoom': zoom,
                         'current_tool': current_tool}
    return out

def _normalize_cell(key, item):
    if not isinstance(item, dict) or not isinstance(key, str):
        return None
    try:
        row_s, col_s = key.split(',')
        coord = (int(row_s), int(col_s))
    except (ValueError, AttributeError):
        return None
    etype = item.get('type')
    if not isinstance(etype, str) or etype not in TOOL_SPECS or not _in_world_bounds(*coord):
        return None
    data = TOOL_SPECS[etype]()
    for f in PERSIST_FIELDS[etype]:
        if f in item:
            data[f] = _decode_levels(item[f]) if f == 'in_levels' else item[f]
    if etype == 'laser' and data.get('is_on') is None:
        data['is_on'] = True
    try:
        data['dir'] = int(data['dir']) % 4
    except (TypeError, ValueError):
        data['dir'] = 0
    if etype == 'latch':
        data['state'] = int(data.get('state') or 0) % 2
    if etype == 'delay_line':
        data['ticks'] = _delay_line_ticks(data)
    return coord, data

def _try_float(value, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

def _refresh_slot_status():
    global _last_slot_by_mtime, _sl_slots
    union = set(_discover_slots()) | set(int(s) for s in _slot_names.keys())
    slots = sorted(s for s in union if s and s > 0)
    _sl_slots = slots
    newest_mtime, newest_slot = 0.0, 0
    for slot in slots:
        path = _slot_path(slot)
        if not os.path.exists(path):
            save_status[slot] = '%d:-' % slot
            _slot_meta[slot] = {'cells': 0, 'mtime': 0.0}
            continue
        try:
            mtime = os.path.getmtime(path)
            with open(path, 'r', encoding='utf-8') as fh:
                doc = json.load(fh)
            raw = doc.get('cells') if isinstance(doc, dict) else None
            if not isinstance(raw, dict):
                raise ValueError('cells 不是对象')
            count = sum(1 for v in raw.values()
                        if isinstance(v, dict) and v.get('type') in TOOL_SPECS)
            save_status[slot] = '%d:%dc' % (slot, count)
            nm = doc.get('name') if isinstance(doc, dict) else None
            if isinstance(nm, str) and nm.strip():
                _slot_names[slot] = nm.strip()
            _slot_meta[slot] = {'cells': count, 'mtime': mtime}
            if mtime >= newest_mtime:
                newest_mtime, newest_slot = mtime, slot
        except (ValueError, OSError, TypeError, AttributeError):
            save_status[slot] = '%d:BAD' % slot
            _slot_meta[slot] = {'cells': 0, 'mtime': 0.0, 'bad': True}
    _last_slot_by_mtime = newest_slot

def save_slot(slot: int, name=None) -> bool:
    global world_dirty, last_slot
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return False
    if slot <= 0:
        return False
    if name is not None:
        clean = str(name).strip()[:32]
        _slot_names[slot] = clean or trans('sl.default_name', slot=slot)
    disp = _slot_display_name(slot)
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        path = _slot_path(slot)
        doc = serialize_world()
        doc['name'] = disp
        with open(path + '.tmp', 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
        os.replace(path + '.tmp', path)
    except OSError as exc:
        _note(trans('note.save_fail', slot=slot, err=exc))
        return False
    world_dirty = False
    last_slot = slot
    _note(trans('note.saved', slot=disp, cells=len(grid_data), dir=SAVE_DIR))
    _refresh_slot_status()
    return True

def _read_slot(slot: int) -> Tuple[Dict[Coord, dict], dict]:
    path = _slot_path(slot)
    if not os.path.exists(path):
        raise FileNotFoundError('slot %d is empty' % slot)
    with open(path, 'r', encoding='utf-8') as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError('存档根节点不是对象')
    raw_cells = doc.get('cells') or {}
    if not isinstance(raw_cells, dict):
        raise ValueError('cells 不是对象')
    cells: Dict[Coord, dict] = {}
    for key, item in raw_cells.items():
        parsed = _normalize_cell(key, item)
        if parsed is not None and len(cells) < MAX_CELLS_LIMIT:
            cells[parsed[0]] = parsed[1]
    return cells, doc

def _f4_target_slot() -> int:
    _refresh_slot_status()
    seen: Set[int] = set()
    for cand in [last_slot, _last_slot_by_mtime] + list(_sl_slots):
        try:
            slot = int(cand)
        except (TypeError, ValueError):
            continue
        if slot > 0 and slot not in seen:
            seen.add(slot)
            if os.path.exists(_slot_path(slot)):
                return slot
    return 0

def load_slot(slot: int) -> bool:
    global grid_data, camera_x, camera_y, zoom, current_tool
    global world_dirty, last_slot, grid_changed, timeline_present
    try:
        slot = int(slot)
    except (TypeError, ValueError):
        return False
    if slot <= 0:
        return False
    try:
        cells, doc = _read_slot(slot)
    except (ValueError, OSError, TypeError, AttributeError, FileNotFoundError) as exc:
        _note(trans('note.load_broken', slot=slot, err=exc))
        return False
    push_undo_replaced(grid_data, cells)
    grid_data = cells
    _rebuild_indices()
    cam = doc.get('camera')
    if isinstance(cam, dict):
        camera_x = _try_float(cam.get('camera_x'), camera_x)
        camera_y = _try_float(cam.get('camera_y'), camera_y)
        zoom = max(MIN_ZOOM, min(_try_float(cam.get('zoom'), zoom), MAX_ZOOM))
        tool = cam.get('current_tool')
        if isinstance(tool, int) and tool in range(len(TOOL_TYPES)):
            current_tool = tool
        clamp_camera()
    world_dirty = False
    last_slot = slot
    timeline_present = any(_etype(d) == 'delay_line' for d in cells.values())
    reset_timeline('load slot %d' % slot)
    _note(trans('note.loaded', slot=slot, cells=len(grid_data)))
    _refresh_slot_status()
    grid_changed = True
    return True

def load_recent_slot() -> bool:
    slot = _f4_target_slot()
    if not slot:
        _note(trans('note.no_save'))
        return False
    return load_slot(slot)

def paste_slot_at_cursor(slot: int = 0) -> bool:
    global grid_changed, world_dirty, last_slot
    try:
        _slot_int = int(slot)
    except (TypeError, ValueError):
        _slot_int = 0
    target = _slot_int if _slot_int > 0 else _f4_target_slot()
    if not target:
        _note(trans('note.paste_none'))
        return False
    try:
        cells, _doc = _read_slot(target)
    except (ValueError, OSError, TypeError, AttributeError, FileNotFoundError) as exc:
        _note(trans('note.paste_broken', slot=target, err=exc))
        return False
    if not cells:
        _note(trans('note.paste_empty', slot=target))
        return False
    anchor_row, anchor_col = screen_to_grid(*pygame.mouse.get_pos())
    delta_row = anchor_row - min(row for row, _col in cells)
    delta_col = anchor_col - min(col for _row, col in cells)
    moved, dropped = [], 0
    for (row, col), data in cells.items():
        coord = (row + delta_row, col + delta_col)
        if _in_world_bounds(*coord):
            moved.append((coord, data))
        else:
            dropped += 1
    if not moved:
        _note(trans('note.paste_out', slot=target, r=anchor_row, c=anchor_col, n=dropped))
        return False
    push_undo([coord for coord, _data in moved])
    pasted = covered = 0
    for coord, data in moved:
        if coord in grid_data:
            covered += 1
        grid_data[coord] = data
        pasted += 1
    _rebuild_indices()
    reset_timeline('paste')
    world_dirty = True
    last_slot = target
    _note(trans('note.pasted', slot=target, r=anchor_row, c=anchor_col,
                cells=pasted, over=covered, out=dropped))
    _refresh_slot_status()
    grid_changed = True
    return True

def _snapshot_cells(coords: List[Coord]) -> List[Tuple[Coord, Optional[dict]]]:
    return [(coord, copy.deepcopy(grid_data.get(coord))) for coord in sorted(set(coords))]

def push_undo(coords: List[Coord]) -> None:
    if not coords:
        return
    undo_stack.append(_snapshot_cells(coords))
    del undo_stack[:-UNDO_LIMIT]
    del redo_stack[:]

def push_undo_replaced(before: Dict[Coord, dict], after: Dict[Coord, dict]) -> None:
    keys_after = set(after)
    entries: List[Tuple[Coord, Optional[dict]]] = [(c, before.get(c)) for c in sorted(keys_after)]
    entries += [(c, before[c]) for c in sorted(before) if c not in keys_after]
    if not entries:
        return
    undo_stack.append(entries)
    del undo_stack[:-UNDO_LIMIT]
    del redo_stack[:]

def _apply_delta(entries: List[Tuple[Coord, Optional[dict]]]
                 ) -> List[Tuple[Coord, Optional[dict]]]:
    reverse: List[Tuple[Coord, Optional[dict]]] = []
    for coord, before in entries:
        reverse.append((coord, copy.deepcopy(grid_data.get(coord))))
        if before is None:
            grid_data.pop(coord, None)
        else:
            grid_data[coord] = before
    return reverse

def _restore(stack: List[List[Tuple[Coord, Optional[dict]]]],
             other: List[List[Tuple[Coord, Optional[dict]]]], label: str,
             label_key: str) -> bool:
    global grid_data, world_dirty, grid_changed
    if not stack:
        _note(trans('note.undo_nothing', label=trans(label_key)))
        return False
    entries = stack.pop()
    other.append(_apply_delta(entries))
    _rebuild_indices()
    del other[:-UNDO_LIMIT]
    reset_timeline(label)
    world_dirty = True
    _note(trans('note.undo_done', label=trans(label_key), cells=len(entries), now=len(grid_data)))
    grid_changed = True
    return True

def undo() -> bool:
    return _restore(undo_stack, redo_stack, 'undo', 'key.undo')

def redo() -> bool:
    return _restore(redo_stack, undo_stack, 'redo', 'key.redo')

_refresh_slot_status()

MENU_FONT_TITLE = _load_font(96)
MENU_FONT_SUB = _load_font(20)
MENU_FONT_BTN = _load_font(40)
MENU_FONT_SEC = _load_font(28)
MENU_FONT_BODY = _load_font(20)
screen_state = 'menu'
_game_esc_time = 0
_menu_esc_time = 0
_tut_scroll = 0.0
_tut_content_h = 0

_MENU_ICON_POOL = (
    'laser_off', 'mirror_off', 'coupler_off', 'and_gate_off',
    'xor_gate_off', 'latch_off', 'delay_line_off', 'wall_off',
)
_menu_bg_cache = {}
_menu_decor = {}
_menu_decor_size = None
_menu_decor_last = -1

def _build_bg_gradient(win_w, win_h, with_grid=True) -> pygame.Surface:
    surf = pygame.Surface((win_w, win_h))
    top = COLOR_BG
    bot = tuple(max(0, min(255, top[i] + add)) for i, add in enumerate((0, 8, 28)))
    denom = max(1, win_h - 1)
    for y in range(win_h):
        r = y / denom
        pygame.draw.line(
            surf,
            (max(0, min(255, int(top[0] + (bot[0] - top[0]) * r))),
             max(0, min(255, int(top[1] + (bot[1] - top[1]) * r))),
             max(0, min(255, int(top[2] + (bot[2] - top[2]) * r)))),
            (0, y), (win_w, y))
    if with_grid:
        gc = COLOR_GRID
        step = BASE_CELL_SIZE
        for gx in range(0, win_w, step):
            pygame.draw.line(surf, gc, (gx, 0), (gx, win_h), 1)
        for gy in range(0, win_h, step):
            pygame.draw.line(surf, gc, (0, gy), (win_w, gy), 1)
    try:
        return surf.convert()
    except pygame.error:
        return surf

def _build_menu_bg(win_w, win_h) -> pygame.Surface:
    return _build_bg_gradient(win_w, win_h, with_grid=True)

def _menu_pick_free_cell(win_w, win_h):
    cell = _MENU_DECOR_CELL
    free = []
    for col in range(0, int(win_w / cell) + 1):
        for row in range(0, int(win_h / cell) + 1):
            key = (col, row)
            if key in _menu_decor:
                continue
            free.append(key)
    return random.choice(free) if free else None

def _menu_decor_step(win_w, win_h, t_ms) -> None:
    global _menu_decor_last, _menu_decor_size
    if _menu_decor_size != (win_w, win_h):
        _menu_decor.clear()
        _menu_decor_size = (win_w, win_h)
        _menu_decor_last = t_ms
        return
    if _menu_decor_last < 0:
        _menu_decor_last = t_ms
    while t_ms - _menu_decor_last >= _MENU_DECOR_STEP_MS:
        _menu_decor_last += _MENU_DECOR_STEP_MS
        cur = _menu_decor_last
        place = random.random() < (0.72 if len(_menu_decor) < _MENU_DECOR_MAX else 0.28)
        if place:
            key = _menu_pick_free_cell(win_w, win_h)
            if key is not None:
                _menu_decor[key] = {
                    'name': random.choice(_MENU_ICON_POOL),
                    'dir': random.randrange(4),
                    'side': int(ICON_SIZE * (1.5 + random.random() * 0.8)),
                    'born': cur, 'dying': None,
                    'base': 0.35 + random.random() * 0.65,
                }
                continue
        alive = [k for k, v in _menu_decor.items() if v['dying'] is None]
        if alive:
            _menu_decor[random.choice(alive)]['dying'] = cur

def _draw_ambient_menu(t_ms) -> None:
    win_w, win_h = screen.get_size()
    key = (win_w, win_h)
    base = _menu_bg_cache.get(key)
    if base is None:
        _menu_bg_cache.clear()
        base = _build_menu_bg(win_w, win_h)
        _menu_bg_cache[key] = base
    screen.blit(base, (0, 0))
    _menu_decor_step(win_w, win_h, t_ms)
    for k in [k for k, v in _menu_decor.items()
              if v['dying'] is not None and t_ms - v['dying'] >= _MENU_DECOR_FADE_MS]:
        _menu_decor.pop(k, None)
    cell = _MENU_DECOR_CELL
    for (col, row), d in _menu_decor.items():
        if d['dying'] is None:
            fade = min(1.0, (t_ms - d['born']) / _MENU_DECOR_FADE_MS)
        else:
            fade = 1.0 - min(1.0, (t_ms - d['dying']) / _MENU_DECOR_FADE_MS)
        alpha = max(0, min(255, int(80 * fade * d['base'])))
        if alpha <= 0:
            continue
        icon = pygame.transform.rotozoom(ICONS[d['name']][d['dir'] % 4], 0,
                                         d['side'] / ICON_SIZE).copy()
        icon.set_alpha(alpha)
        cx = int(col * cell + cell / 2)
        cy = int(row * cell + cell / 2)
        screen.blit(icon, (cx - icon.get_width() // 2, cy - icon.get_height() // 2))

def _start_button_rect() -> pygame.Rect:
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 480, 60
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 - 60, btn_w, btn_h)

def _tutorial_button_rect() -> pygame.Rect:
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 480, 60
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 + 20, btn_w, btn_h)

def _settings_button_rect() -> pygame.Rect:
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 480, 60
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 + 100, btn_w, btn_h)

def draw_menu() -> None:
    _draw_ambient_menu(pygame.time.get_ticks())
    win_w, win_h = screen.get_size()
    title = MENU_FONT_TITLE.render('GATE OF LIGHT', True, COLOR_ON)
    screen.blit(title, (win_w // 2 - title.get_width() // 2, win_h // 2 - 225))
    for rect, label in ((_start_button_rect(), trans('menu.start')),
                        (_tutorial_button_rect(), trans('menu.tutorial')),
                        (_settings_button_rect(), trans('menu.settings'))):
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_ON, 74 if hovered else 44))
        screen.blit(bg, rect.topleft)
        pygame.draw.rect(screen, COLOR_ON, rect, 3 if hovered else 2)
        txt = MENU_FONT_BTN.render(label, True, COLOR_ON)
        screen.blit(txt, (rect.centerx - txt.get_width() // 2,
                          rect.centery - txt.get_height() // 2))
    hint = MENU_FONT_SUB.render(trans('menu.hint'), True, COLOR_OFF)
    screen.blit(hint, (win_w - hint.get_width() - 16, win_h - hint.get_height() - 12))
    if _menu_esc_time and pygame.time.get_ticks() - _menu_esc_time < _ESC_RETURN_WIN:
        warn = MENU_FONT_SUB.render(trans('menu.quit_hint'), True, COLOR_ON)
        screen.blit(warn, (win_w // 2 - warn.get_width() // 2, 12))

def handle_menu_event(event) -> bool:
    global screen_state, WINDOW_WIDTH, WINDOW_HEIGHT, _tut_scroll, _menu_esc_time
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        if _start_button_rect().collidepoint(event.pos):
            screen_state = 'game'
        elif _tutorial_button_rect().collidepoint(event.pos):
            _tut_scroll = 0.0
            screen_state = 'tutorial'
        elif _settings_button_rect().collidepoint(event.pos):
            screen_state = 'settings'
    elif event.type == pygame.KEYDOWN:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            screen_state = 'game'
        elif event.key == KEY_BACK:
            now = pygame.time.get_ticks()
            if _menu_esc_time and now - _menu_esc_time < _ESC_RETURN_WIN:
                return False
            _menu_esc_time = now
    return True

def build_tutorial_sections():
    pan4 = '%s %s %s %s' % (_key_label(KEYMAP['pan_left']), _key_label(KEYMAP['pan_up']),
                            _key_label(KEYMAP['pan_right']), _key_label(KEYMAP['pan_down']))
    alt4 = '%s %s %s %s' % (_key_label(KEYMAP['pan_left_alt']), _key_label(KEYMAP['pan_up_alt']),
                            _key_label(KEYMAP['pan_right_alt']), _key_label(KEYMAP['pan_down_alt']))
    save_rng = _key_label(KEYMAP['save_1'])
    tools_lbl = '/'.join(_key_label(KEYMAP['tool_%d' % i]) for i in range(len(TOOL_TYPES)))
    return [
        (trans('tut.sec.play'), [
            ('', trans('tut.play.place')),
            ('', trans('tut.play.select', tools=tools_lbl,
                       rot=_key_label(KEYMAP['rotate']), cyc=_key_label(KEYMAP['cycle_rot']))),
            ('', trans('tut.play.move', pan=pan4, alt=alt4)),
            ('', trans('tut.play.undo', undo=_key_label(KEYMAP['undo']),
                       redo=_key_label(KEYMAP['redo']), del_=_key_label(pygame.K_DELETE))),
            ('', trans('tut.play.save', save=save_rng, load=_key_label(KEYMAP['load']),
                       paste=_key_label(KEYMAP['paste']))),
            ('', trans('tut.play.sl', sv=_key_label(KEYMAP['sl_save']),
                       ld=_key_label(KEYMAP['sl_load']),
                       rn=_key_label(KEYMAP['sl_rename']),
                       dl=_key_label(KEYMAP['sl_delete']),
                       nw=_key_label(KEYMAP['sl_new']))),
            ('', trans('tut.play.misc', pause=_key_label(KEYMAP['pause']))),
            ('', trans('tut.play.esc')),
            ('', trans('tut.play.solver')),
            ('', trans('tut.play.perf', perf=_key_label(KEYMAP['perf']))),
            ('', trans('tut.play.hold', undo=_key_label(KEYMAP['undo']))),
        ]),
        (trans('tut.sec.elements'), [
            ('wall_off', trans('tut.el.wall')),
            ('laser_off', trans('tut.el.laser')),
            ('mirror_off', trans('tut.el.mirror')),
            ('coupler_off', trans('tut.el.coupler')),
            ('and_gate_off', trans('tut.el.and_gate')),
            ('xor_gate_off', trans('tut.el.xor_gate')),
            ('latch_off', trans('tut.el.latch')),
            ('delay_line_off', trans('tut.el.delay_line')),
        ]),
        (trans('tut.sec.tips'), [
            ('', trans('tut.tip.solver')),
            ('', trans('tut.tip.rotate', undo=_key_label(KEYMAP['undo']))),
            ('', trans('tut.tip.corner')),
            ('', trans('tut.tip.rebind')),
        ]),
    ]
def _tutorial_wrap(text, _max_chars=None):
    text = ' '.join(text.split())
    if not text:
        return [text]
    lines = []
    cur = ''
    for ch in text:
        cur += ch
        if ch in '.!?;。！？；':
            lines.append(cur.strip())
            cur = ''
    if cur.strip():
        lines.append(cur.strip())
    return lines or [text]

def _draw_game_esc_hint() -> None:
    global paused
    win_w, _ = screen.get_size()
    now = pygame.time.get_ticks()
    if now - _game_esc_time < _ESC_RETURN_WIN:
        msg = trans('game.unsaved') if (world_dirty and grid_data) \
            else trans('game.back_menu')
        t = MENU_FONT_SUB.render(msg, True, COLOR_ON)
        screen.blit(t, (win_w // 2 - t.get_width() // 2, 12))
    if paused:
        p = MENU_FONT_SUB.render(trans('game.paused'), True, COLOR_ON)
        screen.blit(p, (win_w - p.get_width() - 12, 12))

def handle_tutorial_event(event) -> None:
    global screen_state, _tut_scroll, WINDOW_WIDTH, WINDOW_HEIGHT, _game_esc_time
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
        _tut_scroll += -90 if event.button == 4 else 90
    elif event.type == pygame.KEYDOWN:
        if event.key == KEY_BACK:
            screen_state = 'menu'
            _game_esc_time = 0
        elif event.key == pygame.K_PAGEUP:
            _tut_scroll -= 300
        elif event.key == pygame.K_PAGEDOWN:
            _tut_scroll += 300
        elif event.key == pygame.K_UP:
            _tut_scroll -= 40
        elif event.key == pygame.K_DOWN:
            _tut_scroll += 40

def _draw_tutorial() -> None:
    global _tut_scroll, _tut_content_h
    TUTORIAL_SECTIONS = build_tutorial_sections()
    _draw_ambient_menu(pygame.time.get_ticks())
    win_w, win_h = screen.get_size()
    title = MENU_FONT_BTN.render(trans('tut.title'), True, COLOR_ON)
    screen.blit(title, (win_w // 2 - title.get_width() // 2, 22))
    close_hint = MENU_FONT_SUB.render(trans('tut.close'), True, COLOR_OFF)
    screen.blit(close_hint, (win_w // 2 - close_hint.get_width() // 2, win_h - 34))

    panel_w = min(760, win_w - 80)
    panel_x = win_w // 2 - panel_w // 2
    panel_y = 76
    panel_h = win_h - 76 - 46
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill(_tint(COLOR_BG, 255))
    screen.blit(panel, (panel_x, panel_y))
    pygame.draw.rect(screen, COLOR_ON, (panel_x, panel_y, panel_w, panel_h), 2)

    inner_w = panel_w - 48
    sec_line = 44
    body_line = 28
    TUTORIAL_SECTIONS = [
        (sec, [(k, _tutorial_wrap(t)) for k, t in rows])
        for sec, rows in TUTORIAL_SECTIONS
    ]

    total_h = 0
    for _, rows in TUTORIAL_SECTIONS:
        total_h += sec_line + body_line * sum(len(ls) for _k, ls in rows) + 12
    _tut_content_h = total_h
    view_h = panel_h - 32
    _tut_scroll = max(0, min(_tut_scroll, max(0, total_h - view_h)))

    canvas = pygame.Surface((inner_w, max(1, total_h)), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    y = 0
    for sec, rows in TUTORIAL_SECTIONS:
        canvas.blit(MENU_FONT_SEC.render(sec, True, COLOR_ON), (0, y))
        y += sec_line
        for key, lines in rows:
            has_icon = bool(key) and key in ICONS
            for li, ln in enumerate(lines):
                canvas.blit(MENU_FONT_BODY.render(ln, True, COLOR_OFF),
                            (30 if has_icon else 0, y))
                if li == 0 and has_icon:
                    ic = pygame.transform.scale(ICONS[key][0], (22, 22)).copy()
                    ic.set_alpha(210)
                    canvas.blit(ic, (0, y + 2))
                y += body_line
        y += 12

    clip = pygame.Rect(panel_x + 24, panel_y + 16, inner_w, view_h)
    screen.set_clip(clip)
    screen.blit(canvas, (panel_x + 24, panel_y + 16 - int(_tut_scroll)))
    screen.set_clip(None)

    _draw_scrollbar(pygame.Rect(panel_x + panel_w - 14, panel_y + 16, 6, view_h),
                    total_h, view_h, _tut_scroll)

def _rebuild_icons() -> None:
    for _name, _maker in (('wall', _make_wall_icon), ('laser', _make_laser_icon),
                          ('mirror', _make_mirror_icon),
                          ('coupler', _make_coupler_icon), ('xor_gate', _make_xor_icon),
                          ('and_gate', _make_and_gate_icon), ('latch', _make_latch_icon),
                          ('delay_line', _make_delay_line_icon)):
        for _suffix, _color in (('_on', COLOR_ON), ('_off', COLOR_OFF)):
            ICONS[_name + _suffix] = _icon_frames(_maker(_color))
    ICONS['off_mark'] = _icon_frames(_make_off_mark_icon(COLOR_ON))
    _SCALED_CACHE.clear()

def _apply_theme(name: str) -> None:
    global COLOR_ON, COLOR_OFF, COLOR_BG, COLOR_GRID, current_theme
    theme = THEMES.get(name)
    if theme is None:
        return
    current_theme = name
    COLOR_ON = theme['on']
    COLOR_OFF = theme['off']
    COLOR_BG = theme['bg']
    COLOR_GRID = theme['grid']
    _rebuild_icons()
    _menu_bg_cache.clear()
    _game_glow_cache.clear()

def _save_settings() -> None:
    try:
        payload = {'theme': current_theme, 'lang': _LANG,
                   'keys': {aid: KEYMAP.get(aid) for aid, _ in KEY_ACTION_LABELS}}
        os.makedirs(SAVE_DIR, exist_ok=True)
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
def _load_settings() -> None:
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            theme = data.get('theme')
            if theme in THEMES:
                _apply_theme(theme)
            lang = data.get('lang')
            if lang in TEXTS:
                set_lang(lang)
            raw = data.get('keys')
            if isinstance(raw, dict):
                for aid, _lab in KEY_ACTION_LABELS:
                    v = raw.get(aid)
                    if isinstance(v, int) and _key_owner(aid, v) is None:
                        KEYMAP[aid] = v
    except Exception:
        pass
_SET_TAB_TOP = 34
_SET_OPT_TOP = 114
_SET_LIST_TOP = 112
_SET_LIST_BOTTOM_IN = 46
_SET_TITLE_UP = 84

def _settings_layout():
    win_w, win_h = screen.get_size()
    panel_w = min(760, win_w - 80)
    panel_x = win_w // 2 - panel_w // 2
    panel_y = 112
    panel_h = win_h - panel_y - 46
    return win_w, win_h, panel_x, panel_y, panel_w, panel_h

settings_tab = 'theme'
settings_listen = None
settings_scroll = 0.0
def settings_tab_labels():
    return [('theme', trans('set.tab.theme')), ('keys', trans('set.tab.keys')),
            ('language', trans('set.tab.language'))]
def _settings_tab_rects():
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    inner_x = panel_x + 32
    inner_w = panel_w - 64
    labels = settings_tab_labels()
    n = max(1, len(labels))
    bw = (inner_w - 16 * (n - 1)) // n
    y = panel_y + _SET_TAB_TOP
    rects = []
    for _i, (_tid, _lbl) in enumerate(labels):
        rects.append((_tid, pygame.Rect(inner_x + _i * (bw + 16), y, bw, 40)))
    return rects
_KEYS_ROW_H, _KEYS_PITCH = 34, 42
_CARD_ROW_H, _CARD_PITCH = 72, 90

def _settings_list_metrics(row_h: int, pitch: int, n: int):
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    inner_x = panel_x + 32
    inner_w = panel_w - 64
    top = panel_y + _SET_LIST_TOP
    bottom = panel_y + panel_h - _SET_LIST_BOTTOM_IN
    total_h = max(0, n) * pitch
    view_h = max(0, bottom - top)
    return inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h

def _keys_metrics():
    return _settings_list_metrics(_KEYS_ROW_H, _KEYS_PITCH, len(KEY_ACTION_LABELS))

def _theme_metrics():
    return _settings_list_metrics(_CARD_ROW_H, _CARD_PITCH, len(THEME_ORDER))

def _language_metrics():
    return _settings_list_metrics(_CARD_ROW_H, _CARD_PITCH, len(TEXTS))

def _tab_metrics():
    if settings_tab == 'keys':
        return _keys_metrics()
    if settings_tab == 'language':
        return _language_metrics()
    return _theme_metrics()

def _clamp_settings_scroll() -> None:
    global settings_scroll
    _ix, _iw, _top, _bot, _rh, _pitch, total_h, view_h = _tab_metrics()
    settings_scroll = max(0.0, min(settings_scroll, float(max(0, total_h - view_h))))

def _clamp_keys_scroll() -> None:
    _clamp_settings_scroll()

def _key_option_rects():
    inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h = _keys_metrics()
    rects = []
    for i, (aid, _lab) in enumerate(KEY_ACTION_LABELS):
        y = int(top + i * pitch - settings_scroll)
        rects.append((aid, pygame.Rect(inner_x, y, inner_w, row_h)))
    return rects
def _key_row_label_rect(rect):
    w = 92
    return pygame.Rect(rect.right - 12 - w, rect.y + 4, w, rect.h - 8)
def _reset_key(aid: str) -> None:
    dflt = _DEFAULT_KEYS[aid]
    other = _key_owner(aid, dflt)
    if other is not None:
        KEYMAP[other] = KEYMAP[aid]
    KEYMAP[aid] = dflt
    apply_keymap()
    _save_settings()
def _bind_key(aid: str, key: int) -> None:
    other = _key_owner(aid, key)
    if other is not None:
        KEYMAP[other] = KEYMAP[aid]
    KEYMAP[aid] = key
    apply_keymap()
    _save_settings()
def _theme_option_rects():
    inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h = _theme_metrics()
    rects = []
    for i, name in enumerate(THEME_ORDER):
        y = int(top + i * pitch - settings_scroll)
        rects.append((name, pygame.Rect(inner_x, y, inner_w, row_h)))
    return rects

def _draw_settings() -> None:
    _draw_ambient_menu(pygame.time.get_ticks())
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    title = MENU_FONT_BTN.render(trans('menu.settings'), True, COLOR_ON)
    screen.blit(title, (win_w // 2 - title.get_width() // 2, panel_y - _SET_TITLE_UP))
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill(_tint(COLOR_BG, 255))
    screen.blit(panel, (panel_x, panel_y))
    pygame.draw.rect(screen, COLOR_ON, (panel_x, panel_y, panel_w, panel_h), 2)
    label_map = dict(settings_tab_labels())
    for tid, rect in _settings_tab_rects():
        active = (tid == settings_tab)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_ON, 60 if active else 30))
        screen.blit(bg, rect.topleft)
        pygame.draw.rect(screen, COLOR_ON if active else COLOR_OFF, rect,
                         3 if active else 2, border_radius=8)
        lab = MENU_FONT_SEC.render(label_map[tid], True,
                                   COLOR_ON if active else COLOR_OFF)
        screen.blit(lab, (rect.centerx - lab.get_width() // 2,
                          rect.centery - lab.get_height() // 2))
    if settings_tab == 'theme':
        _draw_settings_theme(panel_x, panel_y, panel_w, panel_h)
    elif settings_tab == 'keys':
        _draw_settings_keys(panel_x, panel_y, panel_w, panel_h)
    else:
        _draw_settings_language(panel_x, panel_y, panel_w, panel_h)
    _s_ix, _s_iw, _s_top, _s_bot, _s_rh, _s_pitch, _s_th, _s_vh = _tab_metrics()
    _draw_scrollbar(pygame.Rect(panel_x + panel_w - 14, _s_top, 6, _s_vh),
                    _s_th, _s_vh, settings_scroll)
def _draw_settings_theme(panel_x, panel_y, panel_w, panel_h) -> None:
    _clamp_settings_scroll()
    _ix, _iw, _top, _bot, _rh, _pitch, _th, _vh = _theme_metrics()
    prev_clip = screen.get_clip()
    screen.set_clip(pygame.Rect(_ix, _top, _iw, _vh))
    for name, rect in _theme_option_rects():
        active = (name == current_theme)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_ON, 60 if active else 34))
        screen.blit(bg, rect.topleft)
        pygame.draw.rect(screen, COLOR_ON if active else COLOR_OFF, rect,
                         3 if active else 2, border_radius=8)
        label = MENU_FONT_SEC.render(theme_display(name), True,
                                     COLOR_ON if active else COLOR_OFF)
        screen.blit(label, (rect.x + 24, rect.centery - label.get_height() // 2))
        sw = THEMES[name]
        sw_size = 26
        sx = rect.right - 24 - sw_size * 3 - 16
        for _key in ('on', 'off', 'bg'):
            pygame.draw.rect(screen, sw[_key],
                             (sx, rect.centery - sw_size // 2, sw_size, sw_size),
                             border_radius=4)
            pygame.draw.rect(screen, COLOR_OFF,
                             (sx, rect.centery - sw_size // 2, sw_size, sw_size), 1,
                             border_radius=4)
            sx += sw_size + 8
    screen.set_clip(prev_clip)
    cur = MENU_FONT_SUB.render(trans('set.active', name=theme_display(current_theme)), True, COLOR_OFF)
    screen.blit(cur, (panel_x + 32, panel_y + panel_h - 34))
def _draw_settings_keys(panel_x, panel_y, panel_w, panel_h) -> None:
    _clamp_keys_scroll()
    inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h = _keys_metrics()
    label_of = dict(KEY_ACTION_LABELS)
    prev_clip = screen.get_clip()
    screen.set_clip(pygame.Rect(inner_x, top, inner_w, view_h))
    for aid, rect in _key_option_rects():
        active = (aid == settings_listen)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_ON, 70 if active else 26))
        screen.blit(bg, rect.topleft)
        pygame.draw.rect(screen, COLOR_ON if active else COLOR_OFF, rect,
                         3 if active else 1, border_radius=6)
        lab = MENU_FONT_BODY.render(label_of[aid], True,
                                    COLOR_ON if active else COLOR_OFF)
        screen.blit(lab, (rect.x + 12, rect.centery - lab.get_height() // 2))
        chip = _key_row_label_rect(rect)
        if active:
            cap = MENU_FONT_BODY.render(trans('set.keybind.listening'), True, COLOR_ON)
            screen.blit(cap, (chip.x, chip.centery - cap.get_height() // 2))
        else:
            kl = _key_label(KEYMAP[aid])
            chip_bg = pygame.Surface((chip.w, chip.h), pygame.SRCALPHA)
            pygame.draw.rect(chip_bg, _tint(COLOR_ON, 95),
                             (0, 0, chip.w, chip.h), border_radius=6)
            screen.blit(chip_bg, chip.topleft)
            pygame.draw.rect(screen, COLOR_OFF, chip, 1, border_radius=6)
            kt = MENU_FONT_BODY.render(kl, True, COLOR_ON)
            screen.blit(kt, (chip.centerx - kt.get_width() // 2,
                             chip.centery - kt.get_height() // 2))
    screen.set_clip(prev_clip)
    if settings_listen is not None:
        hint = MENU_FONT_SUB.render(trans('set.keybind.press'), True, COLOR_ON)
    else:
        hint = MENU_FONT_SUB.render(trans('set.keybind.hint'), True, COLOR_OFF)
    screen.blit(hint, (panel_x + 32, panel_y + panel_h - 34))
def _language_option_rects():
    inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h = _language_metrics()
    rects = []
    for i, lang in enumerate(TEXTS):
        y = int(top + i * pitch - settings_scroll)
        rects.append((lang, pygame.Rect(inner_x, y, inner_w, row_h)))
    return rects

def _draw_settings_language(panel_x, panel_y, panel_w, panel_h) -> None:
    _clamp_settings_scroll()
    _ix, _iw, _top, _bot, _rh, _pitch, _th, _vh = _language_metrics()
    prev_clip = screen.get_clip()
    screen.set_clip(pygame.Rect(_ix, _top, _iw, _vh))
    for lang, rect in _language_option_rects():
        active = (lang == _LANG)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_ON, 60 if active else 34))
        screen.blit(bg, rect.topleft)
        pygame.draw.rect(screen, COLOR_ON if active else COLOR_OFF, rect,
                         3 if active else 2, border_radius=8)
        label = MENU_FONT_SEC.render(_LANG_LABELS.get(lang, lang), True,
                                     COLOR_ON if active else COLOR_OFF)
        screen.blit(label, (rect.x + 24, rect.centery - label.get_height() // 2))
    screen.set_clip(prev_clip)
    cur = MENU_FONT_SUB.render(trans('set.active', name=_LANG_LABELS.get(_LANG, _LANG)),
                               True, COLOR_OFF)
    screen.blit(cur, (panel_x + 32, panel_y + panel_h - 34))

def handle_settings_event(event) -> None:
    global screen_state, WINDOW_WIDTH, WINDOW_HEIGHT, _game_esc_time
    global settings_tab, settings_listen, settings_scroll
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
        return
    if event.type == pygame.MOUSEWHEEL:
        settings_scroll += -15.0 * event.y
        _clamp_settings_scroll()
        return
    if event.type == pygame.KEYDOWN and settings_listen is not None:
        if event.key == KEY_BACK:
            settings_listen = None
        elif event.key == pygame.K_BACKSPACE:
            _reset_key(settings_listen)
            settings_listen = None
        else:
            _bind_key(settings_listen, event.key)
            settings_listen = None
        return
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        for tid, rect in _settings_tab_rects():
            if rect.collidepoint(event.pos):
                settings_tab = tid
                settings_listen = None
                settings_scroll = 0.0
                return
        if settings_tab == 'theme':
            _tx, _tw, _ttop, _tbot, _trh, _tp, _tth, _tvh = _theme_metrics()
            for name, rect in _theme_option_rects():
                if rect.bottom <= _ttop or rect.top >= _tbot:
                    continue
                if rect.collidepoint(event.pos):
                    if name != current_theme:
                        _apply_theme(name)
                        _save_settings()
                    return
        elif settings_tab == 'language':
            _lx, _lw, _ltop, _lbot, _lrh, _lp, _lth, _lvh = _language_metrics()
            for lang, rect in _language_option_rects():
                if rect.bottom <= _ltop or rect.top >= _lbot:
                    continue
                if rect.collidepoint(event.pos):
                    if lang != _LANG:
                        set_lang(lang)
                        _save_settings()
                    return
        else:
            _ix, _iw, _top, _bot, _rh, _pitch, _th, _vh = _keys_metrics()
            for aid, rect in _key_option_rects():
                if rect.bottom <= _top or rect.top >= _bot:
                    continue
                if rect.collidepoint(event.pos):
                    settings_listen = aid
                    return
        return
    if event.type == pygame.KEYDOWN:
        if event.key == KEY_BACK:
            screen_state = 'menu'
            _game_esc_time = 0
        elif settings_tab == 'theme':
            if event.key in (pygame.K_LEFT, pygame.K_UP):
                idx = (THEME_ORDER.index(current_theme) - 1) % len(THEME_ORDER)
                _apply_theme(THEME_ORDER[idx])
                _save_settings()
            elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                idx = (THEME_ORDER.index(current_theme) + 1) % len(THEME_ORDER)
                _apply_theme(THEME_ORDER[idx])
                _save_settings()
            elif event.key == pygame.K_TAB:
                settings_tab = 'keys'
                settings_listen = None
                settings_scroll = 0.0
        elif settings_tab == 'keys':
            if event.key in (pygame.K_TAB,):
                settings_tab = 'theme'
                settings_listen = None
                settings_scroll = 0.0
            elif event.key == pygame.K_UP:
                settings_scroll -= 42
                _clamp_keys_scroll()
            elif event.key == pygame.K_DOWN:
                settings_scroll += 42
                _clamp_keys_scroll()
        else:
            if event.key == pygame.K_UP:
                settings_scroll -= _CARD_PITCH / 2.0
                _clamp_settings_scroll()
            elif event.key == pygame.K_DOWN:
                settings_scroll += _CARD_PITCH / 2.0
                _clamp_settings_scroll()

_saveload_open = False
_saveload_sel = 1
SL_FONT_HEAD = _load_font(30)
SL_FONT_ROW = _load_font(22)
SL_FONT_SUB = _load_font(15)
SL_FONT_BTN = _load_font(18)
_SL_ROW_H, _SL_ROW_PITCH = 66, 74


def _open_saveload() -> None:
    global _saveload_open, _saveload_sel, _sl_scroll, _sl_edit_slot, _sl_edit_buf, _sl_del_confirm_slot
    _refresh_slot_status()
    if _sl_slots:
        _saveload_sel = last_slot if last_slot in _sl_slots else _sl_slots[0]
    else:
        _saveload_sel = 0
    _sl_scroll = 0
    _sl_edit_slot, _sl_edit_buf = -1, ''
    _sl_del_confirm_slot = -1
    _saveload_open = True


_SL_HEADER_H = 112
_SL_FOOTER_H = 52
_SL_BTN_W, _SL_BTN_GAP = 72, 6


def _sl_geom():
    win_w, win_h = screen.get_size()
    panel_w = min(760, max(420, win_w - 60))
    panel_x = win_w // 2 - panel_w // 2
    panel_y = 88
    panel_h = max(320, win_h - panel_y - 30)
    list_top = panel_y + _SL_HEADER_H
    list_bottom = panel_y + panel_h - _SL_FOOTER_H
    nb_w, nb_h = 120, 40
    new_btn = pygame.Rect(panel_x + panel_w - 28 - nb_w, panel_y + 16, nb_w, nb_h)
    return {'win_w': win_w, 'win_h': win_h, 'px': panel_x, 'py': panel_y,
            'pw': panel_w, 'ph': panel_h, 'list_top': list_top,
            'list_bottom': list_bottom, 'new_btn': new_btn}


def _sl_max_scroll(g):
    total = len(_sl_slots) * _SL_ROW_PITCH
    return max(0, total - (g['list_bottom'] - g['list_top']))


def _sl_clamp_scroll():
    global _sl_scroll
    _sl_scroll = max(0, min(_sl_scroll, _sl_max_scroll(_sl_geom())))


def _saveload_rows():
    global _sl_scroll
    g = _sl_geom()
    _sl_scroll = max(0, min(_sl_scroll, _sl_max_scroll(g)))
    top, bottom = g['list_top'], g['list_bottom']
    inner_x = g['px'] + 24
    inner_w = g['pw'] - 44
    rows = []
    for i, slot in enumerate(_sl_slots):
        y = top + i * _SL_ROW_PITCH - _sl_scroll
        if y + _SL_ROW_H < top or y > bottom:
            continue
        row = pygame.Rect(inner_x, y, inner_w, _SL_ROW_H)
        btn_h = 40
        by = row.y + (_SL_ROW_H - btn_h) // 2
        bx = row.right - 16
        btns = {}
        for act in ('save', 'load', 'ren', 'del'):
            r = pygame.Rect(bx - _SL_BTN_W, by, _SL_BTN_W, btn_h)
            btns[act] = r
            bx = r.x - _SL_BTN_GAP
        rows.append((slot, row, btns))
    return g, rows


def _slot_exists(slot: int) -> bool:
    meta = _slot_meta.get(slot) or {}
    return bool(meta) and not meta.get('bad') and meta.get('cells', 0) > 0


def _fit_text(text, font, maxw):
    if maxw <= 0 or font.size(text)[0] <= maxw:
        return text
    while text and font.size(text + '…')[0] > maxw:
        text = text[:-1]
    return (text + '…') if text else '…'


def _do_save_slot(slot: int) -> None:
    save_slot(slot)


def _do_load_slot(slot: int) -> None:
    if not os.path.exists(_slot_path(slot)):
        _note(trans('note.no_save'))
        return
    load_slot(slot)


def _do_delete_slot(slot: int) -> None:
    global last_slot, _sl_edit_slot, _sl_edit_buf, _saveload_sel, _sl_del_confirm_slot
    _sl_del_confirm_slot = -1
    path = _slot_path(slot)
    try:
        if os.path.exists(path):
            os.remove(path)
        if os.path.exists(path + '.tmp'):
            os.remove(path + '.tmp')
    except OSError as exc:
        _note(trans('note.del_fail', slot=slot, err=exc))
        return
    _slot_names.pop(slot, None)
    _slot_meta.pop(slot, None)
    if last_slot == slot:
        last_slot = 0
    if _sl_edit_slot == slot:
        _sl_edit_slot, _sl_edit_buf = -1, ''
    _note(trans('note.deleted', slot=_slot_display_name(slot)))
    _refresh_slot_status()
    if _sl_slots:
        if _saveload_sel not in _sl_slots:
            _saveload_sel = _sl_slots[min(len(_sl_slots) - 1, max(0, 0))]
        _ensure_selected_visible()
    else:
        _saveload_sel = 0


def _do_new_save() -> None:
    global _saveload_sel, _sl_edit_slot, _sl_edit_buf
    slot = _next_free_slot()
    nm = trans('sl.default_name', slot=slot)
    if save_slot(slot, name=nm):
        _saveload_sel = slot
        _sl_edit_slot, _sl_edit_buf = slot, nm
        _ensure_selected_visible()


def _begin_rename(slot: int) -> None:
    global _sl_edit_slot, _sl_edit_buf
    _sl_edit_slot, _sl_edit_buf = slot, _slot_display_name(slot)


def _commit_rename() -> None:
    global _sl_edit_slot, _sl_edit_buf
    if _sl_edit_slot < 0:
        return
    _rename_slot(_sl_edit_slot, _sl_edit_buf.strip())
    _sl_edit_slot, _sl_edit_buf = -1, ''


def _cancel_rename() -> None:
    global _sl_edit_slot, _sl_edit_buf
    _sl_edit_slot, _sl_edit_buf = -1, ''


def _ensure_selected_visible() -> None:
    global _sl_scroll
    if _saveload_sel not in _sl_slots:
        return
    g = _sl_geom()
    idx = _sl_slots.index(_saveload_sel)
    top, bottom = g['list_top'], g['list_bottom']
    row_top = top + idx * _SL_ROW_PITCH - _sl_scroll
    row_bot = row_top + _SL_ROW_H
    if row_top < top:
        _sl_scroll += (row_top - top)
    elif row_bot > bottom:
        _sl_scroll += (row_bot - bottom)
    _sl_clamp_scroll()


def _draw_saveload_row(slot, row, btns, mouse):
    meta = _slot_meta.get(slot) or {}
    selected = (slot == _saveload_sel)
    exists = _slot_exists(slot)
    bad = bool(meta.get('bad'))
    bg = pygame.Surface((row.w, row.h), pygame.SRCALPHA)
    bg.fill(_tint(COLOR_ON, 60 if selected else 24))
    screen.blit(bg, (row.x, row.y))
    pygame.draw.rect(screen, COLOR_ON if selected else COLOR_OFF, row, 2)
    editing = (_sl_edit_slot == slot)
    left_x = row.x + 16
    name_maxw = max(40, btns['del'].x - left_x - 16)
    if editing:
        disp = _sl_edit_buf + ('|' if (pygame.time.get_ticks() // 400) % 2 else '')
        text_top = row.y + 9
        nt = SL_FONT_ROW.render(_fit_text(disp, SL_FONT_ROW, name_maxw - 14), True, COLOR_ON)
        ib = pygame.Rect(left_x - 4, text_top - 4,
                         min(360, name_maxw) + 8, nt.get_height() + 8)
        pygame.draw.rect(screen, COLOR_BG, ib)
        pygame.draw.rect(screen, COLOR_ON, ib, 2)
        screen.blit(nt, (left_x, text_top))
        tip = SL_FONT_SUB.render(trans('sl.edit.tip'), True, COLOR_OFF)
        screen.blit(tip, (left_x, row.y + 42))
    else:
        name = _slot_display_name(slot)
        nt = SL_FONT_ROW.render(_fit_text(name, SL_FONT_ROW, name_maxw), True,
                                COLOR_ON if (exists or selected) else COLOR_OFF)
        screen.blit(nt, (left_x, row.y + 9))
        if bad:
            status = trans('sl.bad')
        elif exists:
            tstr = ''
            if meta.get('mtime'):
                tstr = '  ' + time.strftime('%m-%d %H:%M', time.localtime(meta['mtime']))
            status = trans('sl.cells', cells=meta.get('cells', 0)) + tstr
            if last_slot == slot:
                status += '  *'
        else:
            status = trans('sl.empty')
        st = SL_FONT_SUB.render(status, True, COLOR_ON if exists else COLOR_OFF)
        screen.blit(st, (left_x, row.y + 40))
    label_map = {'save': 'sl.btn.save', 'load': 'sl.btn.load',
                 'ren': 'sl.btn.rename', 'del': 'sl.btn.del'}
    for act, rect in btns.items():
        if act == 'save':
            enabled = True
        elif act == 'load':
            enabled = exists
        elif act == 'ren':
            enabled = True
        else:
            enabled = os.path.exists(_slot_path(slot))
        hov = enabled and rect.collidepoint(mouse)
        confirming = (act == 'del' and _sl_del_confirm_slot == slot)
        acc = COLOR_ON
        b = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        b.fill(_tint(acc, 110 if (hov or confirming) else (40 if enabled else 16)))
        screen.blit(b, (rect.x, rect.y))
        pygame.draw.rect(screen, acc if enabled else COLOR_OFF, rect,
                         2 if (hov or confirming) else 1)
        _lbl = label_map[act]
        if act == 'del' and _sl_del_confirm_slot == slot:
            _lbl = 'sl.btn.del.confirm'
        lt = SL_FONT_BTN.render(trans(_lbl), True,
                                COLOR_ON if enabled else COLOR_OFF)
        screen.blit(lt, (rect.x + rect.w // 2 - lt.get_width() // 2,
                         rect.y + rect.h // 2 - lt.get_height() // 2))


def _draw_saveload() -> None:
    g, rows = _saveload_rows()
    win_w, win_h = g['win_w'], g['win_h']
    px, py, pw, ph = g['px'], g['py'], g['pw'], g['ph']
    panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
    panel.fill(_tint(COLOR_BG, 255))
    screen.blit(panel, (px, py))
    pygame.draw.rect(screen, COLOR_ON, (px, py, pw, ph), 2)
    title = SL_FONT_HEAD.render(trans('sl.title'), True, COLOR_ON)
    screen.blit(title, (px + 28, py + 16))
    cur_txt = trans('sl.cur', cells=len(grid_data),
                    dirty=trans('sl.dirty') if world_dirty else '')
    cur = SL_FONT_SUB.render(cur_txt, True, COLOR_OFF)
    screen.blit(cur, (px + 30, py + 60))
    cnt = SL_FONT_SUB.render(trans('sl.count', n=len(_sl_slots)), True, COLOR_OFF)
    screen.blit(cnt, (px + 30, py + 82))
    mouse = pygame.mouse.get_pos()
    nb = g['new_btn']
    hov = nb.collidepoint(mouse)
    b = pygame.Surface((nb.w, nb.h), pygame.SRCALPHA)
    b.fill(_tint(COLOR_ON, 95 if hov else 42))
    screen.blit(b, nb)
    pygame.draw.rect(screen, COLOR_ON, nb, 2 if hov else 1)
    lt = SL_FONT_BTN.render(trans('sl.new'), True, COLOR_ON)
    screen.blit(lt, (nb.x + nb.w // 2 - lt.get_width() // 2,
                     nb.y + nb.h // 2 - lt.get_height() // 2))
    view = pygame.Rect(px, g['list_top'], pw, g['list_bottom'] - g['list_top'])
    old_clip = screen.get_clip()
    screen.set_clip(view)
    for slot, row, btns in rows:
        _draw_saveload_row(slot, row, btns, mouse)
    screen.set_clip(old_clip)
    track = pygame.Rect(px + pw - 14, g['list_top'], 6,
                        g['list_bottom'] - g['list_top'])
    _draw_scrollbar(track, len(_sl_slots) * _SL_ROW_PITCH,
                    g['list_bottom'] - g['list_top'], _sl_scroll)
    hint = SL_FONT_SUB.render(
        trans('sl.hint', cl=_key_label(KEYMAP['save_1'])),
        True, COLOR_OFF)
    screen.blit(hint, (win_w // 2 - hint.get_width() // 2, py + ph - 32))


def _handle_saveload_event(event) -> bool:
    global _saveload_open, _saveload_sel, _sl_scroll, _sl_edit_slot, _sl_edit_buf, _sl_del_confirm_slot
    if _sl_edit_slot >= 0:
        if event.type == pygame.TEXTINPUT:
            for ch in event.text:
                if ch.isprintable() and len(_sl_edit_buf) < 32:
                    _sl_edit_buf += ch
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                _sl_edit_buf = _sl_edit_buf[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                _commit_rename()
            elif event.key == pygame.K_ESCAPE:
                _cancel_rename()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            _commit_rename()
            return True
        return True
    if event.type == pygame.MOUSEWHEEL:
        g = _sl_geom()
        _sl_scroll = max(0, min(_sl_scroll - event.y * _SL_ROW_PITCH,
                                _sl_max_scroll(g)))
        return True
    if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:
            g = _sl_geom()
            if g['new_btn'].collidepoint(event.pos):
                _sl_del_confirm_slot = -1
                _do_new_save()
                return True
            _g, rows = _saveload_rows()
            for slot, row, btns in rows:
                for act, rect in btns.items():
                    if not rect.collidepoint(event.pos):
                        continue
                    if act == 'save':
                        _sl_del_confirm_slot = -1
                        _do_save_slot(slot)
                    elif act == 'load' and _slot_exists(slot):
                        _sl_del_confirm_slot = -1
                        _do_load_slot(slot)
                    elif act == 'ren':
                        _sl_del_confirm_slot = -1
                        _begin_rename(slot)
                    elif act == 'del' and os.path.exists(_slot_path(slot)):
                        if _sl_del_confirm_slot == slot:
                            _do_delete_slot(slot)
                        else:
                            _sl_del_confirm_slot = slot
                    return True
                if row.collidepoint(event.pos):
                    _saveload_sel = slot
                    _sl_del_confirm_slot = -1
                    return True
            if not pygame.Rect(g['px'], g['py'], g['pw'], g['ph']).collidepoint(event.pos):
                _saveload_open = False
                _sl_del_confirm_slot = -1
        return True
    if event.type == pygame.KEYDOWN:
        if event.key in (KEY_BACK, KEY_SAVE_MENU, pygame.K_ESCAPE):
            _saveload_open = False
            _sl_del_confirm_slot = -1
            return True
        if _sl_slots:
            idx = _sl_slots.index(_saveload_sel) if _saveload_sel in _sl_slots else 0
            if event.key == pygame.K_UP:
                _saveload_sel = _sl_slots[(idx - 1) % len(_sl_slots)]
                _ensure_selected_visible()
            elif event.key == pygame.K_DOWN:
                _saveload_sel = _sl_slots[(idx + 1) % len(_sl_slots)]
                _ensure_selected_visible()
        return True
    return True



_PERF: Dict[str, float] = {'solve_ms': 0.0}
perf_visible = False
PERF_FONT = _load_font(14)

def _draw_perf_panel() -> None:
    mouse_pos = pygame.mouse.get_pos()
    point_data = None
    if _is_ui_pos(mouse_pos):
        hover_txt = ' -- , -- '
    else:
        hr, hc = screen_to_grid(*mouse_pos)
        hover_txt = 'r%-4d c%-4d' % (hr, hc)
        point_data = grid_data.get((hr, hc))
    col1 = (
        'FPS   %5.1f' % clock.get_fps(),
        'solve %6.2f ms' % _PERF['solve_ms'],
        'undo  %d / %d' % (len(undo_stack), UNDO_LIMIT),
    )
    col2 = (
        'cells %d' % len(grid_data),
        'mouse %s' % hover_txt,
        'zoom  %.2fx' % zoom,
    )
    _dir_words = ('up', 'right', 'down', 'left')
    if point_data is None:
        col3 = ('type  --', 'dir   --', 'state --')
    else:
        _t = point_data.get('type', '?')
        _d = int(point_data.get('dir', 0)) % 4
        _state = 'LIT' if point_data.get('is_lit', False) else 'off'
        if _t == 'laser':
            _state += ' / sw:' + ('on' if point_data.get('is_on', True) else 'off')
        elif _t == 'latch':
            _state += ' / mem:' + str(int(point_data.get('state', 0)))
        elif _t == 'delay_line':
            _state += ' / n:' + str(int(point_data.get('ticks', 0)))
        elif _t == 'xor_gate':
            _state += ' / in:' + str(len(point_data.get('input_dirs') or ()))
        col3 = (
            'type  %s' % _t,
            'dir   %s(%d)' % (_dir_words[_d], _d),
            'state %s' % _state,
        )
    pad, line_h, col_gap = 6, 18, 16
    col1_w = max(PERF_FONT.size(s)[0] for s in col1)
    col2_w = max(PERF_FONT.size(s)[0] for s in col2)
    col3_w = max(PERF_FONT.size(s)[0] for s in col3)
    box_w = pad * 2 + col1_w + col_gap + col2_w + col_gap + col3_w
    box_h = pad * 2 + line_h * max(len(col1), len(col2), len(col3))
    box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    box.fill(_tint(COLOR_BG, 190))
    screen.blit(box, (10, 10))
    pygame.draw.rect(screen, COLOR_ON, (10, 10, box_w, box_h), 1)
    for i, line in enumerate(col1):
        screen.blit(PERF_FONT.render(line, True, COLOR_ON),
                    (10 + pad, 10 + pad + i * line_h))
    col2_x = 10 + pad + col1_w + col_gap
    for i, line in enumerate(col2):
        screen.blit(PERF_FONT.render(line, True, COLOR_ON),
                    (col2_x, 10 + pad + i * line_h))
    col3_x = col2_x + col2_w + col_gap
    for i, line in enumerate(col3):
        screen.blit(PERF_FONT.render(line, True, COLOR_ON),
                    (col3_x, 10 + pad + i * line_h))

def main():
    global grid_changed, cached_ray_segments, _pending_solve
    running = True
    last_tick_at = time.perf_counter()
    _prev_esc_active = False
    while running:
        dt = min(clock.tick(60) / 1000.0, MAX_FRAME_DT_S)
        _events = pygame.event.get()
        _got_event = bool(_events)
        for event in _events:
            if event.type == pygame.QUIT:
                running = False
            elif screen_state == 'menu':
                if not handle_menu_event(event):
                    running = False
            elif screen_state == 'tutorial':
                handle_tutorial_event(event)
            elif screen_state == 'settings':
                handle_settings_event(event)
            elif not handle_event(event):
                running = False
        if screen_state == 'menu':
            draw_menu()
            pygame.display.flip()
            continue
        if screen_state == 'tutorial':
            _draw_tutorial()
            pygame.display.flip()
            continue
        if screen_state == 'settings':
            _draw_settings()
            pygame.display.flip()
            continue
        prev_cam = (camera_x, camera_y, zoom)
        pan_camera(dt)
        if delete_held:
            delete_erase_at_cursor()
        if place_held:
            place_at_cursor()
        solved_this_frame = False
        if grid_changed:
            grid_changed = False
            last_tick_at = time.perf_counter()
            _pending_solve = None
            _solve_t0 = time.perf_counter()
            cached_ray_segments = step_tick(advance=not paused)
            _PERF['solve_ms'] = (time.perf_counter() - _solve_t0) * 1000.0
            solved_this_frame = True
        elif timeline_present and not paused:
            if _pending_solve is None and \
                    time.perf_counter() - last_tick_at >= TICK_INTERVAL_S:
                _start_sliced_solve(advance=True)
                last_tick_at = time.perf_counter()
        if _pending_solve is not None:
            _solve_t0 = time.perf_counter()
            _seg = _drive_sliced_solve()
            _PERF['solve_ms'] = (time.perf_counter() - _solve_t0) * 1000.0
            if _seg is not None:
                cached_ray_segments = _seg
                solved_this_frame = True
        cam_moved = (camera_x, camera_y, zoom) != prev_cam
        esc_active = _game_esc_time > 0 and \
                     pygame.time.get_ticks() - _game_esc_time < _ESC_RETURN_WIN
        scene_dirty = (_got_event or cam_moved or solved_this_frame or
                       delete_held or place_held or perf_visible or
                       esc_active or esc_active != _prev_esc_active or _saveload_open)
        _prev_esc_active = esc_active
        if scene_dirty:
            draw_scene(cached_ray_segments)
            _draw_game_esc_hint()
            if perf_visible:
                _draw_perf_panel()
            if _saveload_open:
                _draw_saveload()
            pygame.display.flip()

if __name__ == '__main__':
    _load_settings()
    apply_keymap()
    main()
    pygame.quit()
