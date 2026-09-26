
"""GateOfLight —— 光路逻辑沙盒 (Light-based Logic Sandbox)

一个用 pygame 编写的单机沙盒游戏：在近乎无限的可缩放网格上摆放光学元件，让激光束
在空间中传播、反射、分束、组合，从而"用光拼出"可运行的数字逻辑电路。

核心元件（见 TOOL_TYPES）：
    wall        墙体        -- 阻挡光线
    laser       激光源      -- 沿朝向发出光束（可开关）（NOT门）
    mirror      反射镜      -- 按 "/" 或 "\" 朝向改变光路方向
    splitter    分束器      -- 一束光分成透射 + 反射两路
    coupler     耦合器      -- 光路交叉 / 合束的连通元件（OR门）
    and_gate    光与门      -- 信号光与控制光同时点亮才导通（组合逻辑 AND）
    latch       光锁存器    -- 带上升沿状态的记忆元件（1-bit 存储）
    delay_line  延迟线      -- 注入光延迟 n 刻后放出，引入时序维度

求解模型：每个 tick 先由 solve_tick() 做组合逻辑不动点迭代（清态 -> 消化射线 ->
AND 判定 -> 锁存上升沿 -> 灯灭锁定），再由 _advance_delay_lines() 统一推进延迟队列，
于是延迟线 t 刻注入、第 t+n 刻放出，构成同步时序逻辑。

程序结构（自上而下的功能区块，均以分节横幅注释标出）：
    常量与主题 / 键位系统 / 增量索引 / 元件图标绘制 / 光路几何 /
    追踪与求解 / 场景渲染 / 小地图 / HUD / 编辑操作 / 相机 / 事件分发 /
    存档读档 / 撤销重做 / 主菜单 / 教程 / 设置页 / 主循环

运行：script.py即可启动；打包见项目 README。
存档与设置固定写入可执行文件同级的 saves/ 目录（见 BASE_DIR 判定）。
"""

# ── 标准库 ──────────────────────────────────────────────
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

# ── 第三方 ──────────────────────────────────────────────
import pygame

pygame.init()

# 让 Windows 任务栏正确显示自定义图标（与 exe 图标解耦，仅 win32 生效）
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
# 依赖导入
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
MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 0.4, 5.0, 0.1
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
ICON_LATCH_R, ICON_LATCH_CORE = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.25)

MM_SIZE, MM_MARGIN = 180, 10
MM_RELATIVE_SCALE = 0.05
MM_SCAN_CELL_LIMIT = 40000
MM_CROSS = 6
_MM_DBLCLICK_MS = 300

HOTBAR_CELL = 60
HOTBAR_GAP = 6
HOTBAR_BOTTOM_PAD = 10

PLACE_BTN = 3
ERASE_BTN = 1

SAVE_VERSION = 1
SAVE_SLOTS = (1,)
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
KEY_TOGGLE_MINIMAP = pygame.K_m
KEY_PASTE_SLOT = pygame.K_v
KEY_UNDO = pygame.K_z
KEY_REDO = pygame.K_x
KEY_TOGGLE_PAUSE = pygame.K_SPACE
KEY_SAVE_SLOT_BASE = pygame.K_F1
KEY_SAVE_SLOTS = (pygame.K_F1,)
SAVE_SLOT_KEYS = {pygame.K_F1: 1}
KEY_LOAD_SLOT = pygame.K_F2
KEY_TOGGLE_PERF = pygame.K_F12
KEY_BACK = pygame.K_ESCAPE
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
    'minimap': KEY_TOGGLE_MINIMAP,
    'paste': KEY_PASTE_SLOT,
    'pause': KEY_TOGGLE_PAUSE,
    'perf': KEY_TOGGLE_PERF,
    'save_1': pygame.K_F1,
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
# KEY_ACTION_LABELS 在 TOOL_DISPLAY 之后构建（键位已拆分为逐工具/逐存档槽）
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
#======================================================================
#  键位系统：动作 -> 键码映射、标签与冲突检测
#======================================================================
    pygame.K_LALT: 'LAlt', pygame.K_RALT: 'RAlt',
}
def _key_label(key: int) -> str:
    """把 pygame 键码转为可读短标签：方向/空格/F 键等特殊键走映射，其余取 pygame 名称并大写。"""
    if key in _KEY_LABEL_SPECIAL:
        return _KEY_LABEL_SPECIAL[key]
    name = pygame.key.name(key)
    if name.startswith('f') and name[1:].isdigit():
        return name.upper()
    return name.upper() if len(name) <= 3 else name.capitalize()
def _key_owner(exclude_id: str, key: int) -> Optional[str]:
    """返回当前占用该键的另一个动作 id（排除 exclude_id），无冲突返回 None。"""
    for aid, k in KEYMAP.items():
        if k == key and aid != exclude_id:
            return aid
    return None
def apply_keymap() -> None:
    """把 KEYMAP 写回各 KEY_* 全局，并重建派生表（工具键 / 存档键 / 平移键）。"""
    g = globals()
    g['KEY_UNDO'] = KEYMAP['undo']
    g['KEY_REDO'] = KEYMAP['redo']
    g['KEY_ROTATE_ELEMENT'] = KEYMAP['rotate']
    g['KEY_CYCLE_PLACE_ROT'] = KEYMAP['cycle_rot']
    g['KEY_TOGGLE_SWITCH'] = KEYMAP['toggle_switch']
    g['KEY_TOGGLE_MINIMAP'] = KEYMAP['minimap']
    g['KEY_PASTE_SLOT'] = KEYMAP['paste']
    g['KEY_TOGGLE_PAUSE'] = KEYMAP['pause']
    g['KEY_TOGGLE_PERF'] = KEYMAP['perf']
    g['KEY_LOAD_SLOT'] = KEYMAP['load']
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
    'wall': ('dir',), 'laser': ('dir', 'is_on'), 'mirror': ('dir',), 'splitter': ('dir',),
    'coupler': ('dir',), 'and_gate': ('dir',), 'latch': ('dir', 'state', 'in_levels'),
    'delay_line': ('dir', 'ticks'),
}

def _resolve_base_dir() -> str:
    """程序根目录：打包(frozen)后取 exe 所在目录，直接跑源码时取脚本所在目录。
    存档与设置固定写入该目录下的 saves/，不做任何备选目录兜底——
    若该目录不可写（如放进 Program Files），存档会直接失败并给出提示，
    由用户自行把程序移到可写位置。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _resolve_base_dir()
SAVE_DIR = os.path.join(BASE_DIR, "saves")
SETTINGS_PATH = os.path.join(SAVE_DIR, "settings.json")

def _make_app_icon(size: int = 64) -> pygame.Surface:
    """程序化生成窗口 / 任务栏图标：蓝色发光光子 + 一束折射光，呼应 GateOfLight。"""
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(s, (12, 16, 30, 255), (size // 2, size // 2), size // 2)
    pygame.draw.circle(s, (60, 130, 255, 255), (size // 2, size // 2), size // 2,
                       max(2, size // 20))
    pygame.draw.circle(s, (90, 170, 255, 255), (size // 2, size // 2), size // 5)
    pygame.draw.line(s, (150, 210, 255, 255),
                     (size // 8, size - size // 6), (size - size // 8, size // 6),
                     max(2, size // 22))
    return s


def resource_path(rel: str) -> str:
    """资源文件绝对路径：打包(PyInstaller frozen)后优先取解包临时目录 sys._MEIPASS，
    找不到再退回 exe/脚本同级目录 BASE_DIR。"""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            cand = os.path.join(meipass, rel)
            if os.path.exists(cand):
                return cand
    return os.path.join(BASE_DIR, rel)


def _load_app_icon(fallback_size: int = 64):
    """优先使用项目自带的 GateOfLight.ico 作为窗口/任务栏图标；
    依次尝试 .ico/.png，全部缺失或加载失败时优雅降级为程序化绘制的图标，
    保证任何情况下都不会因为缺图标而崩溃。"""
    for name in ("GateOfLight.ico", "GateOfLight.png", "app.ico"):
        path = resource_path(name)
        if os.path.exists(path):
            try:
                return pygame.image.load(path)
            except Exception:
                pass
    return _make_app_icon(fallback_size)


screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
pygame.display.set_icon(_load_app_icon())
pygame.display.set_caption('GateOfLight')
clock = pygame.time.Clock()

def _tint(color, alpha):
    """返回带 alpha 通道的 RGBA 元组。"""
    return (color[0], color[1], color[2], alpha)
#======================================================================
#  相机 / 网格 / 时序等全局可变状态
#======================================================================


camera_x = -WINDOW_WIDTH / 2.0
camera_y = -WINDOW_HEIGHT / 2.0
zoom = 1.0

Coord = Tuple[int, int]
Point = Tuple[float, float]
Segment = Tuple[Point, Point]
RaySeed = RayState = Tuple[int, int, int]
HandlerResult = Optional[Tuple[Coord, int, Point]]

def _etype(data: dict) -> str:
    """取元件类型并保证是 str：坏档的异常值退化成空串，查表落默认分支而不抛 KeyError。"""
    element_type = data.get('type')
    return element_type if isinstance(element_type, str) else ''

grid_data: Dict[Coord, dict] = {}

_idx_laser: Set[Coord] = set()
_idx_latch: Set[Coord] = set()
_idx_delay: Set[Coord] = set()
_lit_relay: Set[Coord] = set()
_touched_and: Set[Coord] = set()
_RELAY_TYPES = ('mirror', 'splitter', 'coupler')
_idx_row_cols: Dict[int, list] = {}
_idx_col_rows: Dict[int, list] = {}
#======================================================================
#  增量索引：按元件类型维护坐标集合，避免全图扫描
#======================================================================


def _index_track(coord: Coord, data: dict) -> None:
    """把一格登记进增量索引：行列有序表 + 按类型(laser/latch/delay)分类集合。"""
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
    """把一格从增量索引中移除，与 _index_track 对称。"""
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
    """清空并从 grid_data 全量重建所有增量索引。"""
    _idx_laser.clear(); _idx_latch.clear(); _idx_delay.clear()
    _idx_row_cols.clear(); _idx_col_rows.clear()
    _lit_relay.clear(); _touched_and.clear()
    for coord, data in grid_data.items():
        _index_track(coord, data)
    _lit_relay.update(c for c, d in grid_data.items()
                    if d.get('type') in _RELAY_TYPES and d.get('is_lit'))
    _touched_and.update(c for c, d in grid_data.items()
                        if d.get('type') == 'and_gate'
                        and (d.get('is_lit') or d.get('axis_inputs') or d.get('perp_inputs')))
current_tool = 1
place_rot = 0
grid_changed = True
cached_ray_segments: List[Segment] = []
paused = False

TOOL_TYPES = ('wall', 'laser', 'mirror', 'splitter', 'coupler', 'and_gate', 'latch',
             'delay_line')
SWITCHABLE_TYPES = ('laser',)
TOOL_SPECS = {
    'wall': lambda: {'type': 'wall', 'dir': 0},
    'laser': lambda: {'type': 'laser', 'dir': 0, 'is_on': True},
    'mirror': lambda: {'type': 'mirror', 'dir': 0, 'is_lit': False},
    'splitter': lambda: {'type': 'splitter', 'dir': 0, 'is_lit': False},
    'coupler': lambda: {'type': 'coupler', 'dir': 0},
    'and_gate': lambda: {'type': 'and_gate', 'dir': 0},
    'latch': lambda: {'type': 'latch', 'dir': 0, 'is_lit': False, 'state': 0,
                      'in_levels': frozenset()},
    'delay_line': lambda: {'type': 'delay_line', 'dir': 0, 'ticks': delay_line_setting,
                      'is_lit': False, 'inject': set(), 'pipe': [], 'out_ready': ()},
}
_LANG = 'en'
_LANG_LABELS = {'en': 'English', 'zh': '简体中文'}
# 双语词条表：内部 id / 存档字段 / 物理键名一律不收进，只收给人看的字符串。
TEXTS = {
    'en': {
        'tool.wall': 'Wall', 'tool.laser': 'Laser', 'tool.mirror': 'Mirror',
        'tool.splitter': 'Splitter', 'tool.coupler': 'Coupler', 'tool.and_gate': 'AND Gate',
        'tool.latch': 'Latch', 'tool.delay_line': 'Delay Line',
        'ui.view_info': 'center {r},{c}  zoom {z}x',
        'key.select_tool': 'Select tool   {name}',
        'key.undo': 'Undo', 'key.redo': 'Redo',
        'key.rotate': 'Rotate element', 'key.cycle_rot': 'Cycle place rotation',
        'key.toggle_switch': 'Toggle switch / power', 'key.minimap': 'Toggle minimap',
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
        'tut.play.misc': '{minimap} toggle minimap   {pause} pause/resume',
        'tut.play.esc': 'ESC x2 returns to menu   ESC quit from menu',
        'tut.play.solver': 'solver recomputes only on change',
        'tut.play.perf': '{perf} perf panel: FPS / solve ms / cells / undo depth',
        'tut.play.hold': 'Hold Enter / Del to lay/erase a run; one {undo} undoes the whole run',
        'tut.el.wall': 'Wall: solid block, does not conduct light',
        'tut.el.laser': 'Laser: light source, emits a beam each tick along its dir',
        'tut.el.mirror': 'Mirror: reflects 45 degrees, bends the beam by 90 degrees',
        'tut.el.splitter': 'Splitter: splits one beam into pass-through + reflected',
        'tut.el.coupler': 'Coupler: merges several beams toward one output',
        'tut.el.and_gate': 'AND gate: lights output only when inputs are present',
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
        'tool.wall': '墙', 'tool.laser': '激光', 'tool.mirror': '反射镜',
        'tool.splitter': '分束器', 'tool.coupler': '耦合器',
        'tool.and_gate': '光与门', 'tool.latch': '光锁存器',
        'tool.delay_line': '延迟线',
        'ui.view_info': '中心坐标 {r},{c}  缩放 {z}x',
        'key.select_tool': '选择工具   {name}',
        'key.undo': '撤销', 'key.redo': '重做',
        'key.rotate': '旋转元件', 'key.cycle_rot': '切换放置朝向',
        'key.toggle_switch': '切换开关 / 电源',
        'key.minimap': '显示或隐藏小地图',
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
        'tut.play.misc': '{minimap} 小地图   {pause} 暂停/继续',
        'tut.play.esc': '连按两次 ESC 返回主菜单   主菜单按 ESC 退出程序',
        'tut.play.solver': '求解器仅在场景改动时重新计算',
        'tut.play.perf': '{perf} 性能面板：帧率 / 求解毫秒 / 元件数 / 撤销深度',
        'tut.play.hold': '按住 回车 / Del 可连铺或连擦；一次 {undo} 即可撤销整段',
        'tut.el.wall': '墙：实心方块，不透光',
        'tut.el.laser': '激光：光源，每个刻沿朝向发出一束光',
        'tut.el.mirror': '反射镜：以 45 度反射，使光束偏转 90 度',
        'tut.el.splitter': '分束器：把一束光分为透射与反射两路',
        'tut.el.coupler': '耦合器：把多束光汇聚到一个输出',
        'tut.el.and_gate': '光与门：仅当两路输入都有光时才点亮输出',
        'tut.el.latch': '光锁存器：自保持开或关，存储 1 个比特',
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
    """返回主题的用户可见译名；未知主题原样返回其 id。"""
    return trans(THEME_LABEL_KEYS.get(name, name))


def trans(key, **kw):
    """按当前语言取词条；缺失自动退回英文，再退回 key 本身；有占位符时做 format。"""
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
    """第 i 个工具的可显示名称（随语言变化）。"""
    return trans('tool.' + TOOL_TYPES[i])


def tool_names():
    """带序号的工具名列表。"""
    return ['%d %s' % (i + 1, tool_display(i)) for i in range(len(TOOL_TYPES))]


def build_key_action_labels():
    """按当前语言重建可绑定动作的显示标签（切语言后须重算）。"""
    names = tool_names()
    return (
        [('tool_%d' % i, trans('key.select_tool', name=names[i]))
         for i in range(len(TOOL_TYPES))]
        + [('undo', trans('key.undo')), ('redo', trans('key.redo')),
           ('rotate', trans('key.rotate')), ('cycle_rot', trans('key.cycle_rot')),
           ('toggle_switch', trans('key.toggle_switch')), ('minimap', trans('key.minimap')),
           ('paste', trans('key.paste')), ('pause', trans('key.pause')),
           ('perf', trans('key.perf'))]
        + [('save_1', trans('key.save_1'))]
        + [('load', trans('key.load')), ('pan_up', trans('key.pan_up')),
           ('pan_down', trans('key.pan_down')),
           ('pan_left', trans('key.pan_left')), ('pan_right', trans('key.pan_right')),
           ('pan_up_alt', trans('key.pan_up_alt')), ('pan_down_alt', trans('key.pan_down_alt')),
           ('pan_left_alt', trans('key.pan_left_alt')),
           ('pan_right_alt', trans('key.pan_right_alt')),
           ('zoom_in', trans('key.zoom_in')), ('zoom_out', trans('key.zoom_out'))]
    )


KEY_ACTION_LABELS = build_key_action_labels()


def set_lang(lang):
    """切换界面语言：更新 _LANG 并重建依赖语言的派生表 / 文本缓存。"""
    global _LANG, KEY_ACTION_LABELS
    if lang not in TEXTS:
        return
    _LANG = lang
    KEY_ACTION_LABELS = build_key_action_labels()
    _MM_INFO_CACHE.clear()
    _MM_LABEL_CACHE.clear()

trace_note = 'ok'

tick_index = 0
delay_line_ready = 0
timeline_present = False
tick_note = ''
delay_line_setting = DELAY_LINE_DEFAULT_TICKS
#======================================================================
#  元件图标绘制：各类元件的精灵帧与缓存
#======================================================================


def _surf() -> pygame.Surface:
    """创建与格子等大的透明底画布。"""
    return pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)

def _icon_frames(base: pygame.Surface) -> Dict[int, pygame.Surface]:
    """将 dir=0 基准图展开为四方向帧。"""
    return {d: (base if d == 0 else pygame.transform.rotate(base, -90 * d)) for d in range(4)}

def _rect(surf, color, size):
    """在画布正中画实心方块。"""
    off = (ICON_SIZE - size) // 2
    pygame.draw.rect(surf, color, (off, off, size, size))

def _protrude(surf, color):
    """画上边缘居中的输出方向凸起。"""
    off = (ICON_SIZE - ICON_PROTRUDE) // 2
    pygame.draw.rect(surf, color, (off, 0, ICON_PROTRUDE, ICON_PROTRUDE))

def _slash(surf, color, slash):
    """画镜面斜线：slash=True 为 '/'，False 为 '\\'。"""
    if slash:
        a, b = (ICON_INSET, ICON_SIZE - ICON_INSET), (ICON_SIZE - ICON_INSET, ICON_INSET)
    else:
        a, b = (ICON_INSET, ICON_INSET), (ICON_SIZE - ICON_INSET, ICON_SIZE - ICON_INSET)
    pygame.draw.line(surf, color, a, b, ICON_LINE_W)

def _plus(surf, color):
    """画格内正十字。用矩形代替粗线以避免偶数线宽时的偏移问题。"""
    c = ICON_SIZE / 2.0
    w = ICON_LINE_W
    span = ICON_SIZE - 2 * ICON_INSET
    off = round(c - w / 2.0)
    pygame.draw.rect(surf, color, (off, ICON_INSET, w, span))
    pygame.draw.rect(surf, color, (ICON_INSET, off, span, w))


def _diamond(surf, color, radius):
    """以格心为顶点的菱形（顶点上下左右各 radius）。"""
    cx = cy = ICON_SIZE // 2
    pygame.draw.polygon(surf, color, [(cx, cy - radius), (cx + radius, cy),
                                      (cx, cy + radius), (cx - radius, cy)])

def _make_laser_icon(color):
    """激光器：居中主体 + 上沿凸起，凸起所指即 dir=0 时的发射方向。"""
    surf = _surf(); _rect(surf, color, ICON_MAIN); _protrude(surf, color); return surf

def _make_wall_icon(color):
    """墙：实心方块，无开关态，只注册一套色。"""
    surf = _surf(); _rect(surf, color, ICON_WALL); return surf

def _make_mirror_icon(color):
    """反射镜：一条镜面斜线，dir=0 画"/"。"""
    surf = _surf(); _slash(surf, color, True); return surf

def _make_splitter_icon(color):
    """分束器：方形外框 + 内部一条镜面斜线，关态时框与线一起变暗灰。"""
    surf = _surf()
    inner = pygame.Rect(ICON_INSET, ICON_INSET, ICON_SIZE - 2 * ICON_INSET,
                        ICON_SIZE - 2 * ICON_INSET)
    pygame.draw.rect(surf, color, inner, ICON_LINE_W)
    _slash(surf, color, True)
    return surf

def _make_coupler_icon(color):
    """耦合器：空心圆环 + 上沿凸起（环内盖一张透明圆挖空中心）。"""
    surf = _surf(); c = ICON_SIZE // 2
    pygame.draw.circle(surf, color, (c, c), ICON_RING_R)
    pygame.draw.circle(surf, CLEAR, (c, c), ICON_RING_R - ICON_RING_W)
    _protrude(surf, color)
    return surf

def _make_and_gate_icon(color):
    """光与门 AND Gate：两条竖向栅条夹一条透光槽（dir=0 时透光轴水平）。"""
    surf = _surf(); cx = cy = ICON_SIZE // 2
    top = cy - ICON_BAR_LEN // 2
    for left in (cx - ICON_BAR_GAP // 2 - ICON_BAR_W, cx + ICON_BAR_GAP // 2):
        pygame.draw.rect(surf, color, (left, top, ICON_BAR_W, ICON_BAR_LEN))
    return surf

def _make_latch_icon(color):
    """光锁存器：空心菱形（大小两菱形叠出边框，掏空用透明色故不留死黑）+ 上沿输出凸起。"""
    surf = _surf()
    _diamond(surf, color, ICON_LATCH_R)
    if ICON_LATCH_R - ICON_LINE_W > 0:
        _diamond(surf, CLEAR, ICON_LATCH_R - ICON_LINE_W)
    if color == COLOR_ON:
        _diamond(surf, color, ICON_LATCH_CORE)
    _protrude(surf, color)
    return surf


def _make_delay_line_icon(color):
    """延迟线：正方形外框 + 框内正十字（十字架）。四向对称，四边既是入边也是出边，故不带凸起。"""
    surf = _surf()
    inner = pygame.Rect(ICON_INSET, ICON_INSET, ICON_SIZE - 2 * ICON_INSET,
                        ICON_SIZE - 2 * ICON_INSET)
    pygame.draw.rect(surf, color, inner, ICON_LINE_W)
    _plus(surf, color)
    return surf

def _make_off_mark_icon(color):
    """手动关闭标记：两条对角线交成斜十字，绘制时叠在元件之上。"""
    surf = _surf(); _slash(surf, color, True); _slash(surf, color, False); return surf

ICONS: Dict[str, Dict[int, pygame.Surface]] = {}

for _name, _maker in (('laser', _make_laser_icon), ('mirror', _make_mirror_icon),
                      ('splitter', _make_splitter_icon), ('coupler', _make_coupler_icon),
                      ('and_gate', _make_and_gate_icon), ('latch', _make_latch_icon),
                      ('delay_line', _make_delay_line_icon)):
    for _suffix, _color in (('_on', COLOR_ON), ('_off', COLOR_OFF)):
        ICONS[_name + _suffix] = _icon_frames(_maker(_color))

ICONS['wall'] = _icon_frames(_make_wall_icon(COLOR_OFF))
ICONS['off_mark'] = _icon_frames(_make_off_mark_icon(COLOR_ON))

_SCALED_CACHE: Dict[Tuple[str, int, int], pygame.Surface] = {}
SCALED_CACHE_LIMIT = 3000

def blit_icon(name: str, direction: int, screen_x: int, screen_y: int,
              cell_size: int) -> None:
    """按名取帧、缩放（带缓存）、blit 到屏幕。"""
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
#======================================================================
#  光路几何与端口：反射方向、端口分配、坐标换算
#======================================================================


def reflected_direction(direction, mirror_dir):
    """打到反射镜后的新方向：偶数 dir 画"/"、奇数画反斜（贴图与光路共用此判据）。"""
    table = REFLECT_ON_SLASH if mirror_dir % 2 == 0 else REFLECT_ON_BACKSLASH
    return table.get(direction, direction)

def and_gate_ports(out_dir):
    """光与门只看 dir 奇偶，返回（信号光方向, 控制光方向）：偶数 dir 透光轴水平。"""
    return ((1, 3), (0, 2)) if out_dir % 2 == 0 else ((0, 2), (1, 3))

def latch_ports(out_dir):
    """光锁存器端口分配：dir 所指的边是输出边，其余三条边为输入边。"""
    out_dir %= 4
    return out_dir, tuple(d for d in range(4) if d != out_dir)

def _next_cell(row, col, direction):
    """沿 direction 前进一格，返回新的 (row, col)。"""
    d_row, d_col = STEP_BY_DIR[direction]
    return row + d_row, col + d_col

def _cell_center(col, row):
    """格心世界坐标 (x, y)。"""
    return (col + 0.5) * BASE_CELL_SIZE, (row + 0.5) * BASE_CELL_SIZE


def _ray_end_at_world_edge(col, row, direction):
    """光线从当前格沿 direction 射出后，钉在世界边界上的终点坐标。"""
    axis, value = EDGE_PX[direction]
    end_x, end_y = _cell_center(col, row)
    return (value, end_y) if axis == 'x' else (end_x, value)

def _in_world_bounds(row, col):
    """判断 (row, col) 是否落在世界边界内。"""
    return -WORLD_HALF_COLS <= col < WORLD_HALF_COLS and -WORLD_HALF_ROWS <= row < WORLD_HALF_ROWS

def _add_segment(segments: List[Segment], start: Point, end: Point) -> None:
    """登记一段光路（世界坐标）；全文件只有这一个写入口。"""
    segments.append((start, end))

def _view_range():
    """当前视口的格范围 (r0, c0, r1, c1)。

    用 // 而不是 int(x / size)：向负无穷取整对负坐标同样成立，跨世界原点不会多算或少算一格。
    右下多带 2 格余量，免得平移与缩放时边缘元件一帧有一帧无地闪烁。
    """
    r0 = max(-WORLD_HALF_ROWS, int(camera_y // BASE_CELL_SIZE))
    c0 = max(-WORLD_HALF_COLS, int(camera_x // BASE_CELL_SIZE))
    r1 = min(WORLD_ROWS - WORLD_HALF_ROWS,
             int((camera_y + WINDOW_HEIGHT / zoom) // BASE_CELL_SIZE) + 2)
    c1 = min(WORLD_COLS - WORLD_HALF_COLS,
             int((camera_x + WINDOW_WIDTH / zoom) // BASE_CELL_SIZE) + 2)
    return r0, c0, r1, c1

def _cells_in_range(r0, r1, c0, c1, scan_by_bounds: bool) -> Iterator:
    """遍历给定格范围内的元件：范围比元件表小就逐格查表，否则遍历元件表筛范围——两头都不空转。视口绘制与小地图共用。"""
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

def screen_to_grid(mouse_x, mouse_y):
    """屏幕像素 -> 世界格坐标 (row, col)。"""
    return (int((mouse_y / zoom + camera_y) // BASE_CELL_SIZE),
            int((mouse_x / zoom + camera_x) // BASE_CELL_SIZE))

def clamp_camera():
    """把相机夹回世界边界内；某轴视口比世界还大时该轴直接钉在世界左（上）边界。"""
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

#======================================================================
#  追踪上下文 TraceCtx：一轮追踪的全部临时状态
#======================================================================

@dataclass
class TraceCtx:
    """单轮光路记账本：射线队列、命中集合、预算计数器。每轮新建。"""
    segments: List[Segment] = field(default_factory=list)
    pending: Deque[RaySeed] = field(default_factory=deque)
    hit_lasers: Set[Coord] = field(default_factory=set)
    seen: Set[RayState] = field(default_factory=set)
    lit_relay: Set[Coord] = field(default_factory=set)
    lit_focus: Set[Coord] = field(default_factory=set)
    touched_and_gates: Set[Coord] = field(default_factory=set)
    touched_latchs: Set[Coord] = field(default_factory=set)
    touched_delay_lines: Set[Coord] = field(default_factory=set)
    delay_line_injects: Dict[Coord, Set[int]] = field(default_factory=dict)
    rays: int = 0
    steps: int = 0
    deadline: float = 0.0
    aborted: bool = False
#======================================================================
#  光线追踪：逐格传播与各类元件处理 (_handle_*)
#======================================================================
    abort_reason: str = ''

def _reset_cell_dynamic(coord: Coord, data: dict, dark: Optional[Set[Coord]] = None,
                        and_gate_lit: Optional[bool] = None) -> None:
    """将一格清回本刻初始态。dark/and_gate_lit 仅用于刻内多轮迭代。"""
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
    elif element_type in ('coupler', 'mirror', 'splitter'):
        data['is_lit'] = False
    elif element_type == 'delay_line':
        data['is_lit'] = bool(data.get('out_ready'))


def _wipe(coord: Coord, dark: Optional[Set[Coord]] = None,
          and_gate_lit: Optional[bool] = None) -> Optional[dict]:
    """增量清态入口，委托 _reset_cell_dynamic。"""
    data = grid_data.get(coord)
    if data is None:
        return None
    _reset_cell_dynamic(coord, data, dark, and_gate_lit)
    return data


def _baseline_reset() -> Tuple[List[Coord], Set[Coord], List[Coord], List[Coord]]:
    """清基线，返回(亮灯, 发光锁存器, 全部锁存器, 全部延迟线)。
    只走增量索引: 激光器/锁存器/延迟线各扫自己的小桶; 反射镜-分束器-耦合器与光与门
    只清"上一刻真被点亮/真被碰过"的那批(从没亮过的本就是关态, 无从回退)。成本与相关
    元件数成正比, 与整盘规模无关——这是闪烁器大规模提速的关键。"""
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
    for coord in _touched_and:
        data = grid_data.get(coord)
        if data is not None and data.get('type') == 'and_gate':
            data['axis_inputs'] = set()
            data['perp_inputs'] = set()
            data['is_lit'] = False
    return laser_on, emitting_stones, latch_coords, delay_line_coords


def _incremental_reset(prev: TraceCtx, dark: Set[Coord], lit_and_gates: Set[Coord]) -> None:
    """第 1 轮起的增量清态：只动上一轮真被光碰过的格子，与 _baseline_reset 等价。

    其余格子这一轮没人读旧值：反射镜与分束器要么这轮被照到（处理器会重置 True），
    要么压根没光进来（保持关态就是正确答案）。
    """
    for coord in prev.lit_relay | prev.lit_focus:
        _wipe(coord, dark)
    for coord in prev.touched_and_gates | lit_and_gates:
        _wipe(coord, dark, and_gate_lit=coord in lit_and_gates)
    for coord in prev.touched_latchs | prev.touched_delay_lines:
        _wipe(coord, dark)


def _seed_rays(emitting_lasers: Set[Coord], emitting_stones: Set[Coord],
               delay_line_seeds: Optional[List[RaySeed]] = None) -> List[RaySeed]:
    """播种本轮射线：存活激光器、记忆位 1 的光锁存器各按 dir 发一束，刻末到点的延迟线按 out_ready 补一束。
    全部排序保证同一世界每轮解出同一结果。"""
    return [(r, c, grid_data[(r, c)]['dir'])
            for group in (sorted(emitting_lasers), sorted(emitting_stones)) for r, c in group] \
        + sorted(delay_line_seeds or [])

def _abort_trace(ctx: TraceCtx, reason: str) -> None:
    """标记本轮被预算截断并记下原因；只记第一次，之后的预算判定直接短路。"""
    if not ctx.aborted:
        ctx.aborted = True
        ctx.abort_reason = reason

def _spawn_ray(ctx: TraceCtx, row: int, col: int, direction: int) -> bool:
    """回灌一条派生射线（分束器反射、耦合器激活都走这里），受单轮射线数预算约束。

    预算耗尽的后果只是"这条新束不再派生"，在途射线照常走完：既保住已经画出的光路，
    也让外层 while 必在有限步内退出（pending 只减不增）。
    """
    if ctx.aborted:
        return False
    if ctx.rays + len(ctx.pending) >= MAX_RAYS_PER_ROUND:
        _abort_trace(ctx, 'rays>%d' % MAX_RAYS_PER_ROUND)
        return False
    ctx.pending.append((row, col, direction))
    return True

def _handle_laser(ctx, coord, hit_data, _direction):
    """激光器：记入本轮"被打灭"集合；入射段已由派发方登记到灯心，光在此被灯身挡住。"""
    ctx.hit_lasers.add(coord)

def _handle_mirror(ctx, coord, hit_data, direction):
    """反射镜：光一到就地"开"，按镜面朝向改向，从本格格心继续传播。"""
    hit_data['is_lit'] = True
    ctx.lit_relay.add(coord)
    return coord, reflected_direction(direction, hit_data['dir']), _cell_center(coord[1], coord[0])

def _handle_splitter(ctx, coord, hit_data, direction):
    """分束器：本束原方向直行透射，同时把反射方向回灌成一条新射线。"""
    hit_data['is_lit'] = True
    ctx.lit_relay.add(coord)
    _spawn_ray(ctx, coord[0], coord[1], reflected_direction(direction, hit_data['dir']))
    return coord, direction, _cell_center(coord[1], coord[0])

def _handle_coupler(ctx, coord, hit_data, direction):
    """耦合器 Coupler：一个双向 1<->N 端口器件，正向汇聚 / 反向 T 型分束二合一。

    正向（汇聚，1~3 入 -> 1 出）：光从任意非逆向输入边进来 -> 从输出边 dir 另发一束，
    入射光本身被吸收。
    反向（分束，1 入 -> 2 出）：光从输出边逆向进来 -> 从与输出边相邻的两条输入边
    （(dir+1)%4 与 (dir+3)%4）各发一束，与输出边正对的那条输入边（(dir+2)%4）仍吸收，
    即"光从上方打进、从左和右两边走出去"的 T 型分束（吞掉直行分量）。

    两种角色靠同一个 is_lit 互斥锁定：本格本轮一旦激活（无论被哪条边先点亮），
    另一条边再照进来都视作已处理，绝不再另发——既防正向汇聚时下游回灌自激，
    也防反向分束在两种角色间来回跳。无论走哪支，入射光都停在本格不再透射。
    """
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
    """光与门 AND Gate：信号光 + 控制光两路都到过，本刻才导通。

    控制光（垂直透光轴入射）只记进 perp_inputs 账，随后被栅条吸收，绝不改光路；
    信号光（沿透光轴入射）记进 axis_inputs，本格已点亮才透射到轴的另一端，否则被吸收。
    "两路都到过"这件事由 _collect_lit_and_gates 在整轮射线消化完后统一判定，
    因为单束光走到光与门时另一路可能还没进来，就地判定会漏掉 AND。
    同刻即时生效：判定完当轮就把 is_lit 置真，所以光与门不带任何门延迟。
    """
    axis_dirs, perp_dirs = and_gate_ports(hit_data['dir'])
    ctx.touched_and_gates.add(coord)
    if direction in perp_dirs:
        hit_data.setdefault('perp_inputs', set()).add(direction)
        return None
    hit_data.setdefault('axis_inputs', set()).add(direction)
    if hit_data.get('is_lit'):
        return coord, direction, _cell_center(coord[1], coord[0])

def _handle_latch(ctx, coord, hit_data, direction):
    """光锁存器：把"光从哪条边进来"记成该输入边的电平 1，本体的记忆位由外层翻转。

    入射边 = 行进方向的反向（光朝下走说明它从上边进来）。入射光一律被菱形本体吸收，
    只有锁存器自己会发光（见 _seed_rays）。光打到输出边同样被吸收，但输出端不记电平——
    否则它的输出会自激成上升沿，翻转个不停。
    """
    _, input_dirs = latch_ports(hit_data['dir'])
    entry_edge = (direction + 2) % 4
    if entry_edge in input_dirs:
        hit_data['input_dirs'].add(entry_edge)
        ctx.touched_latchs.add(coord)

def _handle_delay_line(ctx, coord, hit_data, direction):
    """延迟线：全图唯一真正跟"刻"有关的元件。

    光一律被本体吸收，只在账上记一笔"这一轮从 direction 进来过"，放不放行由刻末
    _advance_delay_lines 按延迟队列决定，本刻绝不派生射线。其余元件的处理器都不碰这里。
    """
    ctx.delay_line_injects.setdefault(coord, set()).add(direction)
    hit_data['is_lit'] = True
    ctx.touched_delay_lines.add(coord)


def _handle_wall(ctx, coord, hit_data, direction):
    """墙：入射段登记完即止，既不透射也不派生新射线（兼作未登记类型的兜底）。"""

ELEMENT_HANDLERS: Dict[str, Callable[..., HandlerResult]] = {
    'wall': _handle_wall, 'laser': _handle_laser, 'mirror': _handle_mirror,
    'splitter': _handle_splitter, 'coupler': _handle_coupler,
    'and_gate': _handle_and_gate, 'latch': _handle_latch, 'delay_line': _handle_delay_line,
}

def _next_occupied(row: int, col: int, direction: int) -> Optional[Coord]:
    """沿 direction 在同一条光线(同行或同列)上找严格在本格之前的最近元件格；无则 None。
    上/下扫本列 _idx_col_rows，左/右扫本行 _idx_row_cols，bisect 直接定位，跳过所有空档。"""
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
    """推进队首一条射线直到被吸收/出界/走满单束上限/撞预算。
    不再逐格走空档：用行列空间索引(bisect)一跳就到同一条光线上的下一个元件或世界边界，
    单束成本从 O(光程格数) 降到 O(命中元件数 x log)——这是稀疏大世界里卡帧的总根源。
    seen 按(命中格,方向)去重防镜面回路死循环；出界钉在世界边界，画面无断头光。"""
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
    """AND 判定：同一格内信号光与控制光都到过才点亮。

    只遍历本轮真被光碰过的光与门（touched_and_gates），没光照到的光与门连查都不用查；
    判出的集合既用于本轮就地生效（置 is_lit），也用于外层比对是否收敛。
    """
    lit: Set[Coord] = set()
    for coord in ctx.touched_and_gates:
        data = grid_data.get(coord)
        if data is not None and data.get('axis_inputs') and data.get('perp_inputs'):
            lit.add(coord)
    return lit

def _advance_latch_states(candidates: List[Coord], armed_latchs: Set[Coord]
                          ) -> Tuple[Set[Coord], Set[Coord]]:
    """比对本轮与上一轮的输入边电平，按上升沿个数翻转输出状态（奇换偶不换）。

    三个容易踩的坑都在这段里处理掉：
      in_levels 为 None 表示"刚放置 / 刚旋转 / 刚复位"，此时只记基准不补算上升沿，
        否则摆下去那一瞬间就会白翻一次（存档里 null 与 -1 也一律还原成 None）。
      翻转按"新出现的边数"取模 2：三条输入边同轮一起亮，本该翻一次而不是三次。
      candidates 从第二轮起要并上"上一轮电平非空"的那批（armed_latchs），否则光撤走之后
        电平永远落不回空集，下次再受光就不算上升沿了——锁存器会"变迟钝"。
    返回值同时交回新的发光集合（armed）与被翻翻转的格子，外层据此增删 emitting_latchs。
    """
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
#======================================================================
#  光路求解 solve_tick：组合逻辑不动点迭代
#======================================================================
    return flipped, armed

def _solve_tick_iter(delay_line_seeds: List[RaySeed],
                     deadline: List[float]) -> Iterator[Tuple[List[Segment], List[Coord], bool]]:
    """把一次光路求解拆成可分帧续跑的状态机：与旧 solve_tick 逻辑完全等价，只是在射线
    追踪循环里按 deadline 让出控制权——一帧跑不完下帧接着跑，消除单帧长时间阻塞。
    跑完时以 return 交回 (光段, 延迟线坐标, 是否截断)。deadline=[时刻] 由驱动方逐帧刷新。"""
    global trace_note, timeline_present
    laser_on, emitting_latchs, latch_coords, delay_line_coords = _baseline_reset()
    timeline_present = bool(delay_line_coords)
    emitting: Set[Coord] = set(laser_on)
    lit_and_gates: Set[Coord] = set()
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
        flipped, armed_latchs = _advance_latch_states(
            latch_coords if round_index == 0 else list(ctx.touched_latchs | armed_latchs),
            armed_latchs)
        newly_dark = ctx.hit_lasers & emitting
        dark |= newly_dark
        if not newly_dark and new_lit == lit_and_gates and not flipped:
            converged = True
            break
        emitting -= newly_dark
        lit_and_gates = new_lit
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
    return segments, delay_line_coords, ctx.aborted


def solve_tick(delay_line_seeds: List[RaySeed]) -> Tuple[List[Segment], List[Coord], bool]:
    """同步跑完一次求解（编辑/即时反馈路径用）：内部驱动 _solve_tick_iter 到完成。
    逻辑与分帧版完全一致，只是不设每帧预算、一次性算到底。"""
    gen = _solve_tick_iter(delay_line_seeds, [float('inf')])
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value


#======================================================================
#  方案 E：时序求解分帧摊销——把每刻的全量 solve 摊到多帧，抹平单帧帧率尖峰
#======================================================================
SOLVE_SLICE_BUDGET_S = 0.006   # 每帧最多分给 solve 的时间预算(秒)，超出即交回主循环渲染


class _SolveJob:
    """一次正在分帧续跑的求解任务：持有生成器、逐帧刷新的让出时刻、以及收尾所需信息。"""
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
    """开一个分帧求解任务。若已有在途任务，直接作废重来——世界可能已变，旧结果作废。"""
    global _pending_solve
    _pending_solve = _SolveJob(advance=advance)


def _finalize_sliced_solve(job: _SolveJob, segments: List[Segment],
                           aborted: bool) -> List[Segment]:
    """分帧任务跑完后的收尾：与 step_tick 后半段等价——按 advance 决定是否推延迟线与刻号。"""
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
    """本帧最多喂 SOLVE_SLICE_BUDGET_S 给正在续跑的求解任务。
    跑完则返回最终光段并触发收尾；没跑完返回 None，下帧继续。"""
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
    """取延迟刻度并夹进合法区间：坏档 / 手改的乱值一律退回默认，绝不让 len(pipe) 比较崩掉。"""
    try:
        ticks = int(data.get('ticks', DELAY_LINE_DEFAULT_TICKS))
    except (TypeError, ValueError):
        ticks = DELAY_LINE_DEFAULT_TICKS
    return max(DELAY_LINE_MIN_TICKS, min(ticks, DELAY_LINE_MAX_TICKS))

def _advance_delay_lines(coords: List[Coord]) -> int:
    """刻末统一推进全部延迟队列：每刻进一位(无光记空位以计真实刻数)，线满 n 位才出队放行，
    于是 t 刻注入、第 t+n 刻放出。返回正在放行的延迟线数。"""
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
    """当前世界里全部延迟线坐标(走增量索引, 不再扫全图); 过滤索引偶发滞后。"""
    return [coord for coord in _idx_delay if coord in grid_data]


def reset_timeline(reason: str = '') -> None:
    """时序倒回第 0 刻：刻号归零、每条延迟队列清空。放置/擦除/旋转/改刻度/撤重/读档/粘贴都走这里。
    无延迟线时直接返回，不白扫全图。"""
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
    """解一次光路（组合逻辑当场收敛）；advance=True 再推延迟队列并刻号 +1。

    暂停时以 advance=False 调用：光路照常重解，延迟队列与刻号冻结。于是暂停态下
    网格没改时主循环干脆不调本函数，改了也只重解不推线。
    """
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


#======================================================================
#  场景渲染：元件 / 光路 / 辉光 / draw_scene 总装
#======================================================================
_HOVER_CACHE: Dict[int, pygame.Surface] = {}

def _hover_surface(cell_size: int) -> pygame.Surface:
    """按格子尺寸取（或新建）半透明高亮层，尺寸不变时复用缓存。"""
    surf = _HOVER_CACHE.get(cell_size)
    if surf is None:
        surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
        surf.fill(_tint(COLOR_ON, 45))
        _HOVER_CACHE[cell_size] = surf
    return surf

def _draw_element(data: dict, screen_x: int, screen_y: int, cell_size: int) -> None:
    """贴本体 icon（按 is_lit 取 on/off 套色，墙单态）；手动关着的激光器再叠斜十字标记。

    is_lit 已由 _baseline_reset / solve_tick 保证等于本刻真实生效态，所以这里不需要
    任何"被光打灭但 is_on 仍为真"的特判——渲染层替状态模型打补丁正是 #2 的成因。
    手动关（is_on=False）叠斜十字，被光打灭只变暗灰，两种"不亮"仍可区分。
    """
    element_type = _etype(data)
    name = ('wall' if element_type == 'wall'
            else '%s_%s' % (element_type, 'on' if data.get('is_lit', False) else 'off'))
    blit_icon(name, data['dir'], screen_x, screen_y, cell_size)
    if element_type in SWITCHABLE_TYPES and not data.get('is_on', True):
        blit_icon('off_mark', 0, screen_x, screen_y, cell_size)

def _draw_cells_in_view(hover_row, hover_col) -> None:
    """画视口：整屏画行列网格线（调用数＝行数+列数）-> 光标格高亮 -> 视口内元件贴图。"""
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

    scan = len(grid_data) > (end_row - start_row) * (end_col - start_col)
    for row, col, data in _cells_in_range(start_row, end_row, start_col, end_col, scan):
        _draw_element(data, int(round((col * BASE_CELL_SIZE - camera_x) * zoom)),
                      int(round((row * BASE_CELL_SIZE - camera_y) * zoom)), cell_size)

def _draw_rays(ray_segments: List[Segment]) -> None:
    """世界坐标 -> 屏幕坐标画光路。

    光段是 solve_tick 交回的世界坐标，每帧只做一次仿射变换再取整，因此缓存的光段
    在平移与缩放时不必重算。线宽随 zoom 走，放大后不糊成一片、缩小时也不消失。
    """
    if not ray_segments:
        return
    line_width = max(2, int(BASE_CELL_SIZE * 0.1 * zoom))
    for (x1, y1), (x2, y2) in ray_segments:
        pygame.draw.line(screen, COLOR_ON,
                         (int(round((x1 - camera_x) * zoom)), int(round((y1 - camera_y) * zoom))),
                         (int(round((x2 - camera_x) * zoom)), int(round((y2 - camera_y) * zoom))),
                         line_width)

_game_glow_cache: dict = {}


def _build_game_glow(win_w, win_h) -> pygame.Surface:
    """沙盘画面的「光晕」= 照搬主界面的背景渲染逻辑：直接复用 _build_bg_gradient 的竖向渐变底
    （顶部 COLOR_BG -> 底部略偏蓝），与主界面同一函数、同一色调。不叠加烘焙死网格——沙盘自己会
    按相机画可平移/缩放的活动网格，两套网格叠在一起会错位重影。不透明整屏，作为最底层铺底。"""
    return _build_bg_gradient(win_w, win_h, with_grid=False)

def _draw_game_glow() -> None:
    """把烘焙好的渐变光晕 blit 到沙盘画面最底层（最先画，位于网格/元件/光路/HUD 之下）：铺氛围不糊 UI。"""
    win_w, win_h = screen.get_size()
    key = (win_w, win_h)
    glow = _game_glow_cache.get(key)
    if glow is None:
        _game_glow_cache.clear()
        glow = _build_game_glow(win_w, win_h)
        _game_glow_cache[key] = glow
    screen.blit(glow, (0, 0))


def draw_scene(ray_segments: List[Segment]) -> None:
    """渲染一帧：光晕底（最底层，照搬主界面竖向渐变）-> 网格与元件 -> 光路 -> HUD -> 缩略图。"""
    _draw_game_glow()
    mouse_pos = pygame.mouse.get_pos()
    _ui_hover = minimap_hit(mouse_pos) or hotbar_index_at(mouse_pos) is not None
    hover_row, hover_col = (None, None) if _ui_hover else screen_to_grid(*mouse_pos)
    _draw_cells_in_view(hover_row, hover_col)
    _draw_rays(ray_segments)
    draw_minimap(ray_segments)
    draw_hotbar()

# 字体加载：优先使用内置思源黑体 SourceHanSansSC.otf（可正常渲染中文），
# 缺失/加载失败时优雅退回系统等宽字体，保证任何环境都不因缺字体而崩溃。
# 候选相对路径：先找 fonts/ 子目录，再找程序同级目录；均通过 resource_path
# 定位，兼容 PyInstaller 打包（sys._MEIPASS）与源码直跑两种情况。
_CN_FONT_CANDIDATES = (
    os.path.join('fonts', 'SourceHanSansSC.otf'),
    'SourceHanSansSC.otf',
)
_font_cache = {}

def _load_font(size, bold=False):
    """加载字体：优先内置 SourceHanSansSC.otf，失败退回系统 monospace。
    size 为像素字号，bold=True 时通过 set_bold 做算法加粗。
    同一 (size, bold) 复用缓存，避免每次渲染重复解析 otf 文件。"""
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

MM_FONT = _load_font(12)

minimap_visible = True
minimap_dirty = True
_minimap_surface: Optional[pygame.Surface] = None
_minimap_key: Optional[Tuple[int, int, int]] = None
_minimap_dragging = False
#======================================================================
#  小地图 Minimap：缩略渲染、命中与相机跳转
#======================================================================
_mm_last_click_ms = 0

def _mm_scale() -> float:
    """世界像素 -> 缩略图像素：主画面 1 倍，缩略图恒取其 0.05 倍。"""
    return MM_RELATIVE_SCALE * zoom

def _mm_rect():
    """缩略图屏幕矩形，贴窗口右上角并跟随窗口尺寸。"""
    width, height = screen.get_size()
    return pygame.Rect(width - MM_SIZE - MM_MARGIN, MM_MARGIN, MM_SIZE, MM_SIZE)

def _mm_center():
    """当前视口中心的世界坐标，同时也是图幅正中心。"""
    return camera_x + (WINDOW_WIDTH / zoom) / 2.0, camera_y + (WINDOW_HEIGHT / zoom) / 2.0

def _mm_key():
    """缓存键：视口中心（取整）与倍率，任一变化说明局部内容已经换了一批。"""
    center_x, center_y = _mm_center()
    return int(center_x), int(center_y), round(zoom, 3)

def _mm_to_map(world_x, world_y):
    """世界坐标 -> 图幅坐标（浮点，以图幅中心为锚点），不做裁剪。"""
    scale, (center_x, center_y) = _mm_scale(), _mm_center()
    return (MM_SIZE / 2.0 + (world_x - center_x) * scale,
            MM_SIZE / 2.0 + (world_y - center_y) * scale)

def _mm_point(world_x, world_y):
    """世界坐标 -> 图幅坐标（整数并夹进图幅内），用于画不需要精确端点的点状物。"""
    map_x, map_y = _mm_to_map(world_x, world_y)
    return min(MM_SIZE - 1, max(0, int(map_x))), min(MM_SIZE - 1, max(0, int(map_y)))

def _mm_clip_segment(p1, p2):
    """用 Liang-Barsky 把一段光路裁到图幅 [0, MM_SIZE] 内，完全在图外返回 None。

    为什么不能只把两端点各自夹进图幅：一条斜穿图幅的光段会被拉成贴着边框的折线，
    在框上画出根本不存在的"假光路"。参数化求交后只画真正落在图幅内的那一截，
    小地图上的光路才与主画面严格一致。
    """
    x1, y1 = _mm_to_map(*p1)
    x2, y2 = _mm_to_map(*p2)
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1), (dx, MM_SIZE - x1), (-dy, y1), (dy, MM_SIZE - y1)):
        if p == 0:
            if q < 0:
                return None
        else:
            t = q / p
            if p < 0:
                if t > t1:
                    return None
                t0 = max(t0, t)
            else:
                if t < t0:
                    return None
                t1 = min(t1, t)
    return (x1 + dx * t0, y1 + dy * t0), (x1 + dx * t1, y1 + dy * t1)

def build_minimap(ray_segments) -> None:
    """重画缩略图并写进缓存：底色 -> 世界边界 -> 光路 -> 元件点 -> 边框。

    这是一张"视口局部图"而不是全图缩略图：图幅中心恒等于视口中心，倍率恒为主画面的
    0.05 倍。好处是元件能按所在格在图上的真实相对大小画成小方块（哪怕世界有 15 万元件，
    也不会糊成一片噪点），代价是看不出全貌，所以靠近世界尽头时会把边界线画出来当方位感。
    光路先裁进图幅再画；元件点的取源同样按"范围格数 vs 元件数"双向择优。
    """
    global _minimap_surface, minimap_dirty, _minimap_key
    scale = _mm_scale()
    center_x, center_y = _mm_center()
    half = (MM_SIZE / 2.0) / scale
    surf = pygame.Surface((MM_SIZE, MM_SIZE), pygame.SRCALPHA)
    surf.fill(_tint(COLOR_BG, 140))
    for world_x in (WORLD_MIN_PX, WORLD_MAX_PX):
        map_x, _ = _mm_to_map(world_x, center_y)
        if -1 <= map_x <= MM_SIZE:
            pygame.draw.line(surf, COLOR_GRID, (int(map_x), 0), (int(map_x), MM_SIZE - 1), 1)
    for world_y in (WORLD_MIN_PY, WORLD_MAX_PY):
        _, map_y = _mm_to_map(center_x, world_y)
        if -1 <= map_y <= MM_SIZE:
            pygame.draw.line(surf, COLOR_GRID, (0, int(map_y)), (MM_SIZE - 1, int(map_y)), 1)
    ray_width = max(1, int(round(BASE_CELL_SIZE * 0.1 * zoom * MM_RELATIVE_SCALE)))
    for (x1, y1), (x2, y2) in ray_segments:
        clipped = _mm_clip_segment((x1, y1), (x2, y2))
        if clipped:
            (mx1, my1), (mx2, my2) = clipped
            pygame.draw.line(surf, COLOR_ON, (int(mx1), int(my1)), (int(mx2), int(my2)),
                             ray_width)
    dot = max(2, int(round(BASE_CELL_SIZE * scale)))
    lo_row = max(-WORLD_HALF_ROWS, int((center_y - half) // BASE_CELL_SIZE) - 1)
    hi_row = min(WORLD_HALF_ROWS, int((center_y + half) // BASE_CELL_SIZE) + 2)
    lo_col = max(-WORLD_HALF_COLS, int((center_x - half) // BASE_CELL_SIZE) - 1)
    hi_col = min(WORLD_HALF_COLS, int((center_x + half) // BASE_CELL_SIZE) + 2)
    span = (hi_row - lo_row) * (hi_col - lo_col)
    scan = len(grid_data) > span and span <= MM_SCAN_CELL_LIMIT
    for row, col, data in _cells_in_range(lo_row, hi_row, lo_col, hi_col, scan):
        cell_x, cell_y = _cell_center(col, row)
        map_x, map_y = _mm_point(cell_x, cell_y)
        working = data.get('is_lit', False) or data.get('is_on', False)
        pygame.draw.rect(surf, COLOR_ON if working else COLOR_OFF,
                         (map_x - dot // 2, map_y - dot // 2, dot, dot))
    pygame.draw.rect(surf, COLOR_GRID, surf.get_rect(), 1)
    _minimap_surface = surf
    minimap_dirty = False
    _minimap_key = _mm_key()

def _text(font, text, cache, limit, bg_pad=None):
    """按文本缓存 render 结果（可选配一张半透明底）。

    HUD 与小地图读数绝大多数帧一字不变，60 FPS 下每帧重建 Surface 纯属白烧；
    文案总共固定十几条，超上限整表重来也不会有可感知的抖动。
    需要半透明底时交回 (文字, 底) 一对，尺寸必须用调用方那把字体量——
    借另一号字的缓存会算错底框大小，在文字边上压出黑斑。
    """
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

_MM_LABEL_CACHE: Dict[str, pygame.Surface] = {}
_MM_INFO_CACHE: Dict[str, Tuple[pygame.Surface, pygame.Surface]] = {}

def draw_minimap(ray_segments) -> None:
    """渲染缩略图：需要时先重建缓存 -> blit 到右上角 -> 叠视口框、中心十字与读数。"""
    if not minimap_visible:
        return
    surf = _minimap_surface
    if minimap_dirty or surf is None or _minimap_key != _mm_key():
        build_minimap(ray_segments)
        surf = _minimap_surface
    if surf is None:
        return
    rect = _mm_rect()
    screen.blit(surf, rect.topleft)
    scale = _mm_scale()
    view_w = max(2, min(MM_SIZE - 2, int((WINDOW_WIDTH / zoom) * scale)))
    view_h = max(2, min(MM_SIZE - 2, int((WINDOW_HEIGHT / zoom) * scale)))
    center_x, center_y = rect.center
    pygame.draw.rect(screen, COLOR_ON,
                     pygame.Rect(center_x - view_w // 2, center_y - view_h // 2, view_w, view_h), 1)
    pygame.draw.line(screen, COLOR_ON, (center_x - MM_CROSS, center_y),
                     (center_x + MM_CROSS, center_y), 1)
    pygame.draw.line(screen, COLOR_ON, (center_x, center_y - MM_CROSS),
                     (center_x, center_y + MM_CROSS), 1)
    view_row, view_col = screen_to_grid(WINDOW_WIDTH / 2.0, WINDOW_HEIGHT / 2.0)
    info, info_bg = _text(MM_FONT, trans('ui.view_info', r=view_row, c=view_col,
                                         z='%.1f' % zoom),
                          _MM_INFO_CACHE, 64, (8, 2))
    screen.blit(info_bg, (rect.right - info.get_width() - 10, rect.bottom + 2))
    screen.blit(info, (rect.right - info.get_width() - 6, rect.bottom + 3))

def minimap_hit(mouse_pos) -> bool:
    """鼠标是否落在缩略图内；落在图内的点击一律当导航，不再触发放置 / 擦除。"""
    return minimap_visible and _mm_rect().collidepoint(mouse_pos)

def focus_camera_on_map(mouse_x: float, mouse_y: float) -> None:
    """缩略图导航：以图幅中心为锚点把点击处换算成新的视口中心，再反算相机左上角。"""
    global camera_x, camera_y
    rect = _mm_rect()
    scale = _mm_scale()
    center_x, center_y = _mm_center()
    camera_x = center_x + (mouse_x - rect.centerx) / scale - (WINDOW_WIDTH / zoom) / 2.0
    camera_y = center_y + (mouse_y - rect.centery) / scale - (WINDOW_HEIGHT / zoom) / 2.0
    clamp_camera()

def reset_view_to_origin() -> None:
    """双击小地图：把视口中心拉回世界像素原点 (0,0)，再夹回世界边界。

    视口中心的世界坐标 = camera + (窗口尺寸 / zoom) / 2；要让它等于 0，
    只需把相机左上角设为该半视口尺寸的反面，口径与 _mm_center 完全一致。
    """
    global camera_x, camera_y
    camera_x = -(WINDOW_WIDTH / zoom) / 2.0
    camera_y = -(WINDOW_HEIGHT / zoom) / 2.0
    clamp_camera()

def toggle_minimap() -> None:
    """M 键：切换显隐；重新显示时置脏，保证画面上是最新的光路。"""
    global minimap_visible, minimap_dirty
    minimap_visible = not minimap_visible
    minimap_dirty = True

HOTBAR_FONT = _load_font(11)
HOTBAR_NAME_FONT = _load_font(24)
#======================================================================
#  HUD：快捷栏、旋转按钮与命中判定
#======================================================================
HOTBAR_NUM_FONT  = _load_font(20, bold=True)

def _hotbar_rects() -> List[pygame.Rect]:
    """按当前窗口宽算出 n 个格子矩形：整体水平居中、贴窗口底部。"""
    n = len(TOOL_TYPES)
    step = HOTBAR_CELL + HOTBAR_GAP
    total = n * step - HOTBAR_GAP
    win_w, win_h = screen.get_size()
    # 整组宽度含左侧旋转按钮，使「旋转按钮 + 元件格排」整体水平居中
    group_total = HOTBAR_CELL + HOTBAR_GAP + total
    left = max(4, (win_w - group_total) // 2)
    x0 = left + HOTBAR_CELL + HOTBAR_GAP
    y0 = win_h - HOTBAR_CELL - HOTBAR_BOTTOM_PAD
    return [pygame.Rect(x0 + i * step, y0, HOTBAR_CELL, HOTBAR_CELL) for i in range(n)]

def hotbar_index_at(pos) -> Optional[int]:
    """屏幕坐标命中的快捷栏下标，未命中返回 None。"""
    for i, rect in enumerate(_hotbar_rects()):
        if rect.collidepoint(pos):
            return i
    return None

def _rotate_btn_rect() -> pygame.Rect:
    """快捷栏左侧旋转按钮矩形。"""
    rects = _hotbar_rects()
    first = rects[0]
    return pygame.Rect(max(4, first.x - HOTBAR_GAP - HOTBAR_CELL), first.y, HOTBAR_CELL, HOTBAR_CELL)

def _is_ui_pos(pos) -> bool:
    """光标是否压在任一 UI 上（小地图 / 快捷栏 / 左右侧键）——放置与擦除据此防穿透。"""
    if minimap_hit(pos):
        return True
    if hotbar_index_at(pos) is not None:
        return True
    return _rotate_btn_rect().collidepoint(pos)

def _hotbar_icon_name(tool_type: str) -> str:
    """快捷栏图标取该元件的"亮态"贴图；墙无开态，直接取其单一贴图名。"""
    return tool_type if tool_type == 'wall' else tool_type + '_on'

def draw_hotbar() -> None:
    """画底部快捷栏：逐格 半透明底 + 图标 + 左上角序号；选中蓝粗框、未选灰细框。
    不再逐格显示元件名——把当前选中元件的名字用大号字居中画在整排图标的正上方。"""
    rects = _hotbar_rects()
    for i, rect in enumerate(rects):
        selected = (i == current_tool)
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_BG, 130))
        screen.blit(bg, rect.topleft)
        side = HOTBAR_CELL - 8
        sx = rect.x + (rect.w - side) // 2
        sy = rect.y + (rect.h - side) // 2
        blit_icon(_hotbar_icon_name(TOOL_TYPES[i]), place_rot, sx, sy, side)
        pygame.draw.rect(screen, COLOR_ON if selected else COLOR_OFF,
                         rect, 3 if selected else 1)
        num_col = COLOR_ON if selected else COLOR_OFF
        key_str = _key_label(KEYMAP['tool_%d' % i])
        shadow = HOTBAR_NUM_FONT.render(key_str, True, (0, 0, 0))
        num = HOTBAR_NUM_FONT.render(key_str, True, num_col)
        screen.blit(shadow, (rect.x + 4, rect.y + 3))
        screen.blit(num,    (rect.x + 3, rect.y + 2))
    label = HOTBAR_NAME_FONT.render(tool_display(current_tool), True, COLOR_ON)
    rot_btn = _rotate_btn_rect()
    lx = (rot_btn.x + rects[-1].right) // 2 - label.get_width() // 2
    ly = rects[0].top - label.get_height() - 4
    screen.blit(label, (lx, ly))
    _draw_rotate_btn()

def _draw_ui_button(rect, active, draw_icon, label) -> None:
    """快捷栏同款按钮绘制（旋转按钮，与底部元件格子完全同一口径）：
    半透明底 -> 图标 -> 选中蓝粗框 / 未选灰细框 -> 左上角带阴影序号。
    draw_icon(active) 由调用方传入，只画图标本身；底 / 外框 / 序号统一在此处理。"""
    bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    bg.fill(_tint(COLOR_BG, 130))
    screen.blit(bg, rect.topleft)
    draw_icon(active)
    col = COLOR_ON if active else COLOR_OFF
    pygame.draw.rect(screen, col, rect, 3 if active else 1)
    if label:
        shadow = HOTBAR_NUM_FONT.render(label, True, (0, 0, 0))
        txt = HOTBAR_NUM_FONT.render(label, True, col)
        screen.blit(shadow, (rect.x + 4, rect.y + 3))
        screen.blit(txt, (rect.x + 3, rect.y + 2))

def _draw_rotate_btn() -> None:
    """左侧旋转按钮：循环箭头图标；place_rot≠0 时高亮，提示放置朝向已预设旋转。
    底 / 外框 / 左上角序号一律走快捷栏同款 _draw_ui_button（序号为 E）。"""
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

_stroke_active = False
#======================================================================
#  编辑操作：描边放置 / 擦除 / 删除 / 旋转 / 开关切换
#======================================================================
_stroke_capture: Dict[Coord, Optional[dict]] = {}

def _stroke_begin() -> None:
    """长按开始：开启事务并清空本段捕获表。"""
    global _stroke_active
    _stroke_active = True
    _stroke_capture.clear()

def _stroke_capture_cell(coord: Coord) -> None:
    """事务内登记一格的改前态；同一格只记第一次（防长按中途回绕覆盖掉初始态）。"""
    if coord not in _stroke_capture:
        _stroke_capture[coord] = copy.deepcopy(grid_data.get(coord))

def _stroke_commit() -> None:
    """长按松手：把本段所有改前态合并为一步 delta 入栈（空段不占撤销步数）。"""
    global _stroke_active
    if not _stroke_active:
        return
    _stroke_active = False
    if _stroke_capture:
        undo_stack.append(list(_stroke_capture.items()))
        del undo_stack[:-UNDO_LIMIT]
        del redo_stack[:]
    _stroke_capture.clear()

def place_element() -> None:
    """放置当前工具的元件（默认左键；INVERT_MOUSE=True 时为右键）。
    长按连铺时把本格改前态并入当前事务（松手统一记一步撤销），单次点击仍即时压栈。"""
    global grid_changed, world_dirty
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

def erase_element() -> None:
    """擦除光标格（默认右键；INVERT_MOUSE=True 时为左键）；空格不登记，长按连删并入当前事务。"""
    global grid_changed, world_dirty
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
    """Delete 擦除入口：光标压在底部快捷栏或小地图上时不穿透误删。"""
    _mp = pygame.mouse.get_pos()
    if _is_ui_pos(_mp):
        return
    erase_element()

def place_at_cursor() -> None:
    """放置入口（右键 / Enter 长按）：光标压在快捷栏 / 左右侧键 / 小地图上时不穿透误放；
    长按时每格只放一次——停在同一格下一帧跳过，避免每帧重复压撤销栈。"""
    global _place_last_coord
    _mp = pygame.mouse.get_pos()
    if _is_ui_pos(_mp):
        return
    coord = _cursor_coord()
    if coord == _place_last_coord:
        return
    place_element()
    _place_last_coord = coord

def _cursor_coord() -> Coord:
    """光标所在格（撤销 delta 要按格登记，故坐标与数据各取一个助手）。"""
    return screen_to_grid(*pygame.mouse.get_pos())

def _cursor_element() -> Optional[dict]:
    """取光标所在格的元件数据，空格返回 None（旋转与 F 开关共用）。"""
    return grid_data.get(_cursor_coord())


def rotate_element(step: int) -> None:
    """Q(step=-1) / E(step+1)：一个键位干三件事，按"光标下是什么"分流。

    1) 光标下是普通元件：转朝向（dir 顺时针 +1 / 逆时针 -1）；光锁存器还要把 in_levels
       置 None，让新朝向的输入边只记基准、不补算上升沿，免得转一下白翻一次。
    2) 光标下是延迟线：它四向对称，转了没有任何可见差别，于是把这个键位让给
       "调延迟刻度"（1~12 刻），并把延迟队列清空——线长上限变了，旧线位没有意义。
    3) 光标压在空格上且当前工具是延迟线：调的是放置预设 delay_line_setting，
       可以先定好刻度再连着摆一排同刻度的块。
    三种情况都算"改世界"，一律压撤销步并复位时序。
    """
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
    """F 键：激光器切手动开关；光锁存器复位输出为 0；延迟线清空手上那条延迟队列（吐光卡住时手动排空）。

    反射镜与分束器由光驱动，不处理。
    """
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
        data['state'] = 0
        data['in_levels'] = None
    else:
        data['pipe'] = []
        data['out_ready'] = ()
        data['inject'] = set()
        _note(trans('note.delay_flush'))
    reset_timeline('toggle')
#======================================================================
#  相机控制：平移 / 缩放 / 回原点
#======================================================================
    grid_changed = world_dirty = True

def drag_camera() -> None:
    """中键拖拽中：把鼠标位移除以 zoom 后反向加到相机上，并夹回世界边界。"""
    global camera_x, camera_y, last_mouse_pos
    mouse_x, mouse_y = pygame.mouse.get_pos()
    camera_x -= (mouse_x - last_mouse_pos[0]) / zoom
    camera_y -= (mouse_y - last_mouse_pos[1]) / zoom
    last_mouse_pos = (mouse_x, mouse_y)
    clamp_camera()

def zoom_camera(wheel_y: int) -> None:
    """滚轮缩放：先定新 zoom，再修正相机使鼠标指着的那点保持不动。"""
    global zoom, camera_x, camera_y
    mouse_x, mouse_y = pygame.mouse.get_pos()
    old_zoom = zoom
    zoom = max(MIN_ZOOM, min(zoom + wheel_y * ZOOM_STEP, MAX_ZOOM))
    camera_x += mouse_x * (1 / old_zoom - 1 / zoom)
    camera_y += mouse_y * (1 / old_zoom - 1 / zoom)
    clamp_camera()

PAN_KEYS = ((KEY_PAN_LEFT, KEY_PAN_LEFT_ALT, 'x', -1), (KEY_PAN_RIGHT, KEY_PAN_RIGHT_ALT, 'x', 1),
            (KEY_PAN_UP, KEY_PAN_UP_ALT, 'y', -1), (KEY_PAN_DOWN, KEY_PAN_DOWN_ALT, 'y', 1))

def pan_camera(dt: float) -> None:
    """键盘连续平移：WASD 或方向键，速度按 dt 与 zoom 折算成世界像素位移。"""
    global camera_x, camera_y
    keys = pygame.key.get_pressed()
    pan_speed = PAN_SPEED_PX * dt / zoom
    for key_a, key_b, axis, factor in PAN_KEYS:
        if keys[key_a] or keys[key_b]:
            if axis == 'x':
                camera_x += pan_speed * factor
            else:
                camera_y += pan_speed * factor
#======================================================================
#  游戏内事件分发 handle_event
#======================================================================


def handle_event(event):
    """处理一个事件并派发到对应动作；返回 False 表示要退出主循环。"""
    global current_tool, WINDOW_WIDTH, WINDOW_HEIGHT, _minimap_dragging, is_dragging, delete_held, _mm_last_click_ms
    global place_held, _place_last_coord, place_rot
    global last_mouse_pos, screen_state, _game_esc_time, perf_visible, paused
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
        clamp_camera()
    elif event.type == pygame.MOUSEBUTTONDOWN:
        if minimap_hit(event.pos):
            if event.button == 1:
                now_ms = pygame.time.get_ticks()
                if now_ms - _mm_last_click_ms <= _MM_DBLCLICK_MS:
                    _mm_last_click_ms = 0
                    _minimap_dragging = False
                    reset_view_to_origin()
                else:
                    _mm_last_click_ms = now_ms
                    _minimap_dragging = True
                    focus_camera_on_map(*event.pos)
            return True
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
            _stroke_commit()
        elif event.button == ERASE_BTN:
            delete_held = False
            _stroke_commit()
        _minimap_dragging = False
    elif event.type == pygame.MOUSEMOTION:
        buttons = event.buttons
        if _minimap_dragging:
            if buttons[0]:
                focus_camera_on_map(*event.pos)
            else:
                _minimap_dragging = False
        elif is_dragging:
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
        elif event.key == KEY_TOGGLE_MINIMAP:
            toggle_minimap()
        elif event.key == KEY_ROTATE_ELEMENT:
            rotate_element(1)
        elif event.key == KEY_CYCLE_PLACE_ROT:
            place_rot = (place_rot + 1) % 4
        elif event.key == KEY_UNDO:
            undo()
        elif event.key == KEY_REDO:
            redo()
        elif event.key in SAVE_SLOT_KEYS:
            save_slot(SAVE_SLOT_KEYS[event.key])
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
_message = ''
#======================================================================
#  存档与读档 Save/Load：三个槽位 + 剪贴板粘贴
#======================================================================
_message_until = 0.0

def _note(msg: str) -> None:
    """写一条 HUD 一次性提示并给出失效时刻；过期由 draw_hud 负责让它消失。"""
    global _message, _message_until
    _message = msg
    _message_until = time.perf_counter() + MESSAGE_TTL_S

def _slot_path(slot: int) -> str:
    """返回指定存档槽位对应的文件路径。"""
    return os.path.join(SAVE_DIR, 'slot%d.json' % slot)

def _encode_levels(value):
    """in_levels 三态编码：None -> -1；frozenset -> 方向列表（空集就是空列表）。"""
    return -1 if value is None else sorted(int(d) for d in value)

def _decode_levels(value) -> Optional[frozenset]:
    """
        _encode_levels 的逆运算：-1 与 null 都还原成 None（未定义基准）。null 若被当成空集，语义就变成"基准=没有输入边为 1"：读档当轮只要有一条输入边受光就会被算成上升沿，光锁存器凭空翻转一次。
    """
    if value is None or value == -1:
        return None
    try:
        return frozenset(int(d) for d in value)
    except (TypeError, ValueError):
        return None

def serialize_world(with_camera: bool = True) -> dict:
    """grid_data -> 可 JSON 化的 dict。

    坐标写成 "row,col" 字符串键（JSON 的对象键只能是字符串），值只带 PERSIST_FIELDS
    里登记的字段，未知类型整格不写，避免把手改出来的怪类型元件污染存档。
    带 with_camera 时才附相机与工具：整盘存档要还原视角，粘贴图章则一概不搬
    （那是那份存档自己的视角，不该盖掉玩家当前的画面）。
    """
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
            # 与默认值相同的字段不写，读档时用 TOOL_SPECS 默认补齐，省长度且向后兼容
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
                         'current_tool': current_tool, 'minimap_visible': minimap_visible}
    return out

def _normalize_cell(key, item):
    """读档消毒：补默认字段、丢未知类型、剔越界坐标；以 TOOL_SPECS 的新默认为底，派生态留空。"""
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
    """相机值可能是字符串 / null / 乱码，取不出来就沿用当前值，绝不让读档崩掉。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback

def _refresh_slot_status():
    """扫一遍存档目录，刷新 HUD 上每个槽位的文案与 F4 兜底槽位；坏档标 BAD 不外抛。"""
    global _last_slot_by_mtime
    newest_mtime, newest_slot = 0.0, 0
    for slot in SAVE_SLOTS:
        path = _slot_path(slot)
        if not os.path.exists(path):
            save_status[slot] = '%d:-' % slot
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
            if mtime >= newest_mtime:
                newest_mtime, newest_slot = mtime, slot
        except (ValueError, OSError, TypeError, AttributeError):
            save_status[slot] = '%d:BAD' % slot
    _last_slot_by_mtime = newest_slot

def save_slot(slot: int) -> bool:
    """存到指定槽位：先写 slotN.json.tmp，再 os.replace 原子换名。

    分两步是为了"崩溃也只脏临时文件"：写到一半断电时，上一份能用的存档仍然完好，
    目录里只是多出一个 .tmp，绝不会留下半截 JSON 把槽位变成 BAD。
    成功后清脏标记、记住本槽位（F4 默认读它）并刷新 HUD 上的槽位文案。
    """
    global world_dirty, last_slot
    if slot not in SAVE_SLOTS:
        return False
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        path = _slot_path(slot)
        with open(path + '.tmp', 'w', encoding='utf-8') as fh:
            json.dump(serialize_world(), fh, ensure_ascii=False, separators=(',', ':'))
        os.replace(path + '.tmp', path)
    except OSError as exc:
        _note(trans('note.save_fail', slot=slot, err=exc))
        return False
    world_dirty = False
    last_slot = slot
    _note(trans('note.saved', slot=slot, cells=len(grid_data), dir=SAVE_DIR))
    _refresh_slot_status()
    return True

def _read_slot(slot: int) -> Tuple[Dict[Coord, dict], dict]:
    """读一份存档并消毒成干净的 cells；缺文件 / 半截 JSON / 乱码统一抛异常，由调用方兜住。

    这里刻意不吞异常：调用方要能区分"槽位是空的""文件坏了""成功但一格都没有"，
    三种情况给出的 HUD 提示完全不同。读档（整盘替换）与粘贴（平移到光标格）共用
    这一套解析口径，两条路不会各自漂移；元件数超过 MAX_CELLS_LIMIT 的部分直接不取。
    """
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
    """F4 系列的选档口径：最近存 / 读过的那一槽优先，空了就退修改时间最新的一份，全空返回 0。"""
    _refresh_slot_status()
    seen: Set[int] = set()
    for slot in [last_slot, _last_slot_by_mtime] + list(SAVE_SLOTS):
        if slot in SAVE_SLOTS and slot not in seen:
            seen.add(slot)
            if os.path.exists(_slot_path(slot)):
                return slot
    return 0


def load_slot(slot: int) -> bool:
    """读档：消毒 -> 整盘替换 grid_data -> 还原相机与工具 -> 置脏重算光路。"""
    global grid_data, camera_x, camera_y, zoom, current_tool, minimap_visible
    global world_dirty, last_slot, grid_changed, minimap_dirty, timeline_present
    if slot not in SAVE_SLOTS:
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
        minimap_visible = bool(cam.get('minimap_visible', minimap_visible))
        clamp_camera()
    world_dirty = False
    last_slot = slot
    timeline_present = any(_etype(d) == 'delay_line' for d in cells.values())
    reset_timeline('load slot %d' % slot)
    _note(trans('note.loaded', slot=slot, cells=len(grid_data)))
    _refresh_slot_status()
    grid_changed = minimap_dirty = True
    return True


def load_recent_slot() -> bool:
    """F4 读取：整盘替换为存档内容（相机与工具也跟着还原）。"""
    slot = _f4_target_slot()
    if not slot:
        _note(trans('note.no_save'))
        return False
    return load_slot(slot)


def paste_slot_at_cursor(slot: int = 0) -> bool:
    """Enter 粘贴：把存档当成一块图章盖在当前光标格上，整块平移、相对位置保持不变。

    对齐口径：取存档里 row 与 col 的最小值当作这块内容的左上角，平移量 = 光标格 - 这个角，
    于是存档的左上角正好落在光标格上，其余元件按同一个偏移量跟着平移。
    只搬元件：存档里的相机 / 工具 / 小地图显隐一概不动，那是那份存档自己的视角。
    越界格剔除；与已有元件同格时覆盖，和右键放置的口径一致。
    整次粘贴只压一步快照，一次 Z 就能把这一整块撤掉。
    """
    global grid_changed, minimap_dirty, world_dirty, last_slot
    target = slot if slot in SAVE_SLOTS else _f4_target_slot()
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
    grid_changed = minimap_dirty = True
    return True
#======================================================================
#  撤销 / 重做 Undo-Redo：基于格子增量的快照栈
#======================================================================


def _snapshot_cells(coords: List[Coord]) -> List[Tuple[Coord, Optional[dict]]]:
    """按格取改前状态。单格小 dict 的深拷贝成本可忽略，却保证了栈里的值不会被后续原地改动串改。"""
    return [(coord, copy.deepcopy(grid_data.get(coord))) for coord in sorted(set(coords))]

def push_undo(coords: List[Coord]) -> None:
    """改动前调用：只登记"即将被动的那几格"的改前状态，并清空重做栈。"""
    if not coords:
        return
    undo_stack.append(_snapshot_cells(coords))
    del undo_stack[:-UNDO_LIMIT]
    del redo_stack[:]

def push_undo_replaced(before: Dict[Coord, dict], after: Dict[Coord, dict]) -> None:
    """整盘替换（读档）专用：delta = 新盘涉及的格（恢复用旧值）+ 旧盘独有的格（撤销时要删掉）。

    旧格子对象直接进 delta 而不深拷：替换后没人再引用它们，深拷只是白花钱。
    """
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
    """应用一步 delta，并顺手交回"对面那口栈要的东西"（应用前的当前状态）。"""
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
    """撤销 / 重做的公共部分：按格回滚、时序归零、把反向 delta 塞进对面那口栈（相机不动，免得视角乱跳）。
    label 为内部 id（供 reset_timeline 用），label_key 为对应词条 key（供界面提示用）。"""
    global grid_data, world_dirty, grid_changed, minimap_dirty
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
    grid_changed = minimap_dirty = True
    return True

def undo() -> bool:
    """Z 键：弹出撤销栈顶恢复到上一步，当前状态顺手压进重做栈。"""
    return _restore(undo_stack, redo_stack, 'undo', 'key.undo')

def redo() -> bool:
    """X 键：把刚撤销掉的那一步放回去，同时重新压进撤销栈。"""
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
    'laser_off', 'mirror_off', 'splitter_off', 'coupler_off',
    'and_gate_off', 'latch_off', 'delay_line_off', 'wall',
)
_menu_bg_cache = {}
_menu_decor = {}
_menu_decor_size = None
#======================================================================
#  主菜单 Menu：氛围背景动画、按钮与交互
#======================================================================
_menu_decor_last = -1

def _build_bg_gradient(win_w, win_h, with_grid=True) -> pygame.Surface:
    """全文件唯一的「氛围底」渲染逻辑：竖向渐变（顶部 COLOR_BG -> 底部略偏蓝），
    可选叠加一层与主画面同距的淡网格。主界面氛围背景与沙盘画面的光晕共用这一个函数，
    保证两边色调完全同源。纯现算，不新增色常量。"""
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
        gc = tuple(max(0, min(255, int((COLOR_BG[i] + COLOR_GRID[i]) / 2))) for i in range(3))
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
    """主界面底图：直接复用共享的竖向渐变 + 淡网格（烘焙静态底，尺寸变化才重建）。"""
    return _build_bg_gradient(win_w, win_h, with_grid=True)

def _menu_pick_free_cell(win_w, win_h):
    """在栅格候选格里随机挑一个未占用的格；挑不出返回 None。"""
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
    """时间驱动地随机刷新一枚 / 淡出删除一枚氛围元件；元件位置一次定终身，不再移动。"""
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
                    # 生成时即确定一枚固定的随机透明度系数(0.35~1.0)，之后保持不变
                    'base': 0.35 + random.random() * 0.65,
                }
                continue
        alive = [k for k, v in _menu_decor.items() if v['dying'] is None]
        if alive:
            _menu_decor[random.choice(alive)]['dying'] = cur


def _draw_ambient_menu(t_ms) -> None:
    """程序化氛围背景：缓存底图 + 随机刷新/删除、位置固定的暗色元件（无漂移、无光带）。"""
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
        # 透明度只随出现/消失淡入淡出(fade)变化，叠加固定的随机 base，不再呼吸脉动
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
    """Start 按钮矩形：水平居中，位于标题下方，尺寸固定，跟随窗口尺寸。"""
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 480, 60
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 - 60, btn_w, btn_h)

def _tutorial_button_rect() -> pygame.Rect:
    """教学按钮矩形：水平居中，位于 Start 按钮正下方，跟随窗口尺寸。"""
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 480, 60
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 + 20, btn_w, btn_h)

def _settings_button_rect() -> pygame.Rect:
    """设置按钮矩形：水平居中，位于 Tutorial 按钮正下方，跟随窗口尺寸。"""
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 480, 60
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 + 100, btn_w, btn_h)


def draw_menu() -> None:
    """启动界面：程序化氛围背景 + 居中 GATE OF LIGHT 标题 + Start/Tutorial/Settings 按钮 + 操作提示。"""
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
    """菜单事件：点 Start 或按 Enter / 空格进入沙盘；点 Tutorial 进教学页；尺寸跟随窗口。
    主界面按一次 ESC 即请求退出程序（返回 False）。返回 False 即请求退出程序。
    """
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
#======================================================================
#  教程页 Tutorial：分节教学内容与绘制
#======================================================================


def build_tutorial_sections():
    """教学内容：按当前 KEYMAP 动态生成与键位相关的文本，修改键位后教学/提示随之变化。"""
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
            ('', trans('tut.play.misc', minimap=_key_label(KEYMAP['minimap']),
                       pause=_key_label(KEYMAP['pause']))),
            ('', trans('tut.play.esc')),
            ('', trans('tut.play.solver')),
            ('', trans('tut.play.perf', perf=_key_label(KEYMAP['perf']))),
            ('', trans('tut.play.hold', undo=_key_label(KEYMAP['undo']))),
        ]),
        (trans('tut.sec.elements'), [
            ('wall', trans('tut.el.wall')),
            ('laser_off', trans('tut.el.laser')),
            ('mirror_off', trans('tut.el.mirror')),
            ('splitter_off', trans('tut.el.splitter')),
            ('coupler_off', trans('tut.el.coupler')),
            ('and_gate_off', trans('tut.el.and_gate')),
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
    """把一段教程文本按「完整句子」拆行：以 . ! ? ; 作为句末标点，每句独占一行；
    冒号只作标签分隔（如 'Wall: ...'）不当作断句，因此一句完整的话不会被截断。"""
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
    """游戏态顶部提示：第一次 ESC 提示再按一次返回；暂停时右上角亮 PAUSED。"""
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
    """教学页事件：滚轮 / 方向键 / PgUp-Dn 滚动；ESC 直接返回主界面。不返回退出信号。"""
    global screen_state, _tut_scroll, WINDOW_WIDTH, WINDOW_HEIGHT, _game_esc_time
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
        _tut_scroll += 90 if event.button == 4 else -90
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
    """教学页：主界面同款氛围背景 + 中央半透明面板 + 分段内容（元件行配关态图标）。"""
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
    panel.fill((0, 0, 0, 0))
    screen.blit(panel, (panel_x, panel_y))
    pygame.draw.rect(screen, COLOR_ON, (panel_x, panel_y, panel_w, panel_h), 2)

    inner_w = panel_w - 48
    sec_line = 44
    body_line = 28
    # 教程换行：按完整句子拆行，一句占一行（不再按字符数硬折，避免把句子截断）
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

    if total_h > view_h:
        bar_x = panel_x + panel_w - 14
        thumb_h = max(30, int(view_h * view_h / total_h))
        thumb_y = panel_y + 16 + int((panel_h - 32 - thumb_h) *
                                     (_tut_scroll / max(1, total_h - view_h)))
        pygame.draw.rect(screen, COLOR_OFF, (bar_x, thumb_y, 5, thumb_h))
#======================================================================
#  设置页 Settings：主题 / 键位双子菜单、滚动与改键
#======================================================================


def _rebuild_icons() -> None:
    """按当前全局色重烘所有元件图标帧，并清空缩放缓存（换肤后图标须随色更新）。"""
    for _name, _maker in (('laser', _make_laser_icon), ('mirror', _make_mirror_icon),
                          ('splitter', _make_splitter_icon), ('coupler', _make_coupler_icon),
                          ('and_gate', _make_and_gate_icon), ('latch', _make_latch_icon),
                          ('delay_line', _make_delay_line_icon)):
        for _suffix, _color in (('_on', COLOR_ON), ('_off', COLOR_OFF)):
            ICONS[_name + _suffix] = _icon_frames(_maker(_color))
    ICONS['wall'] = _icon_frames(_make_wall_icon(COLOR_OFF))
    ICONS['off_mark'] = _icon_frames(_make_off_mark_icon(COLOR_ON))
    _SCALED_CACHE.clear()


def _apply_theme(name: str) -> None:
    """切换到指定主题：重着色四色全局 -> 重烘图标 -> 清空背景/光晕缓存 -> 令缩略图失效。"""
    global COLOR_ON, COLOR_OFF, COLOR_BG, COLOR_GRID, current_theme
    global minimap_dirty, _minimap_surface
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
    _minimap_surface = None
    minimap_dirty = True


def _save_settings() -> None:
    """把当前主题与键位写入脚本同级 settings.json（与 saves/ 存档分离）。失败静默。"""
    try:
        payload = {'theme': current_theme, 'lang': _LANG,
                   'keys': {aid: KEYMAP.get(aid) for aid, _ in KEY_ACTION_LABELS}}
        os.makedirs(SAVE_DIR, exist_ok=True)
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
def _load_settings() -> None:
    """启动时读 settings.json 套用主题与键位；缺失/损坏/冲突一律回退默认。"""
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
def _settings_layout():
    """设置页面板几何：与教学页同款（同尺寸、同内边距），保证两页背景与面板一致。"""
    win_w, win_h = screen.get_size()
    panel_w = min(760, win_w - 80)
    panel_x = win_w // 2 - panel_w // 2
    panel_y = 76
    panel_h = win_h - 76 - 46
    return win_w, win_h, panel_x, panel_y, panel_w, panel_h


settings_tab = 'theme'
settings_listen = None
settings_scroll = 0.0
def settings_tab_labels():
    """设置顶部子菜单标签（随语言变化）。"""
    return [('theme', trans('set.tab.theme')), ('keys', trans('set.tab.keys')),
            ('language', trans('set.tab.language'))]
def _settings_tab_rects():
    """设置顶部两个子菜单按钮（主题 / 键位）的矩形。"""
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    inner_x = panel_x + 32
    inner_w = panel_w - 64
    labels = settings_tab_labels()
    n = max(1, len(labels))
    bw = (inner_w - 16 * (n - 1)) // n
    y = panel_y + 70
    rects = []
    for _i, (_tid, _lbl) in enumerate(labels):
        rects.append((_tid, pygame.Rect(inner_x + _i * (bw + 16), y, bw, 40)))
    return rects
def _keys_metrics():
    """键位子页可视区与内容几何：固定行高，内容可超出可视区，由 settings_scroll 上下滚动。"""
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    inner_x = panel_x + 32
    inner_w = panel_w - 64
    top = panel_y + 148
    bottom = panel_y + panel_h - 46
    n = len(KEY_ACTION_LABELS)
    row_h = 34
    pitch = 42
    total_h = n * pitch
    view_h = max(0, bottom - top)
    return inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h

def _clamp_keys_scroll() -> None:
    """把键位滚动量限制在 [0, 内容超出可视区的高度] 之间。"""
    global settings_scroll
    _ix, _iw, _top, _bot, _rh, _pitch, total_h, view_h = _keys_metrics()
    settings_scroll = max(0.0, min(settings_scroll, float(max(0, total_h - view_h))))

def _key_option_rects():
    """键位子页：每个可绑定动作独占一行（单列、固定行高），坐标已套用当前滚动偏移。"""
    inner_x, inner_w, top, bottom, row_h, pitch, total_h, view_h = _keys_metrics()
    rects = []
    for i, (aid, _lab) in enumerate(KEY_ACTION_LABELS):
        y = int(top + i * pitch - settings_scroll)
        rects.append((aid, pygame.Rect(inner_x, y, inner_w, row_h)))
    return rects
def _key_row_label_rect(rect):
    """键位行右侧键名胶囊矩形。"""
    w = 92
    return pygame.Rect(rect.right - 12 - w, rect.y + 4, w, rect.h - 8)
def _reset_key(aid: str) -> None:
    """把某动作重置为默认键（默认键被占用则互换）。"""
    dflt = _DEFAULT_KEYS[aid]
    other = _key_owner(aid, dflt)
    if other is not None:
        KEYMAP[other] = KEYMAP[aid]
    KEYMAP[aid] = dflt
    apply_keymap()
    _save_settings()
def _bind_key(aid: str, key: int) -> None:
    """绑定新键：冲突则与占用者互换，保持全局唯一。"""
    other = _key_owner(aid, key)
    if other is not None:
        KEYMAP[other] = KEYMAP[aid]
    KEYMAP[aid] = key
    apply_keymap()
    _save_settings()
def _theme_option_rects():
    """按当前窗口尺寸返回 [(主题名, 可点击矩形)]，供绘制与命中测试共用同一套坐标。"""
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    inner_x = panel_x + 32
    inner_w = panel_w - 64
    row_h, gap = 72, 18
    y = panel_y + 150
    rects = []
    for name in THEME_ORDER:
        rects.append((name, pygame.Rect(inner_x, y, inner_w, row_h)))
        y += row_h + gap
    return rects


def _draw_settings() -> None:
    """设置页：主界面/教学页同款氛围背景 + 中央半透明面板；顶部两个子菜单（主题 / 键位）。"""
    _draw_ambient_menu(pygame.time.get_ticks())
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    title = MENU_FONT_BTN.render(trans('menu.settings'), True, COLOR_ON)
    screen.blit(title, (win_w // 2 - title.get_width() // 2, 22))
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill(_tint(COLOR_BG, 226))
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
def _draw_settings_theme(panel_x, panel_y, panel_w, panel_h) -> None:
    """主题子页：配色可选列表 + 当前主题色块。"""
    # head = MENU_FONT_SEC.render('THEME', True, COLOR_ON)
    # screen.blit(head, (panel_x + 32, panel_y + 118))
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
    cur = MENU_FONT_SUB.render(trans('set.active', name=theme_display(current_theme)), True, COLOR_OFF)
    screen.blit(cur, (panel_x + 32, panel_y + panel_h - 34))
def _draw_settings_keys(panel_x, panel_y, panel_w, panel_h) -> None:
    """键位子页：逐行展示可绑定动作 + 当前键；点一行进入监听态；内容超出时上下滚动。"""
    _clamp_keys_scroll()
    # head = MENU_FONT_SEC.render('KEYBINDINGS', True, COLOR_ON)
    # screen.blit(head, (panel_x + 32, panel_y + 118))
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
    """语言子页：每种语言一行可点击矩形。"""
    win_w, win_h, panel_x, panel_y, panel_w, panel_h = _settings_layout()
    inner_x = panel_x + 32
    inner_w = panel_w - 64
    row_h, gap = 72, 18
    y = panel_y + 150
    rects = []
    for lang in TEXTS:
        rects.append((lang, pygame.Rect(inner_x, y, inner_w, row_h)))
        y += row_h + gap
    return rects


def _draw_settings_language(panel_x, panel_y, panel_w, panel_h) -> None:
    """语言子页：语言可选列表 + 当前语言。"""
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
    cur = MENU_FONT_SUB.render(trans('set.active', name=_LANG_LABELS.get(_LANG, _LANG)),
                               True, COLOR_OFF)
    screen.blit(cur, (panel_x + 32, panel_y + panel_h - 34))


def handle_settings_event(event) -> None:
    """设置页事件：子菜单切换 / 主题切换写盘 / 键位监听重绑；ESC 返回。"""
    global screen_state, WINDOW_WIDTH, WINDOW_HEIGHT, _game_esc_time
    global settings_tab, settings_listen, settings_scroll
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
        return
    if event.type == pygame.MOUSEWHEEL and settings_tab == 'keys':
        settings_scroll += -15.0 * event.y
        _clamp_keys_scroll()
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
            for name, rect in _theme_option_rects():
                if rect.collidepoint(event.pos):
                    if name != current_theme:
                        _apply_theme(name)
                        _save_settings()
                    return
        elif settings_tab == 'language':
            for lang, rect in _language_option_rects():
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

_PERF: Dict[str, float] = {'solve_ms': 0.0}
perf_visible = False
PERF_FONT = _load_font(14)

def _draw_perf_panel() -> None:
    """左上角半透明读数框：FPS、每刻求解耗时(ms)、当前元件数、撤销栈深/上限。"""
    lines = (
        'FPS   %5.1f' % clock.get_fps(),
        'solve %6.2f ms' % _PERF['solve_ms'],
        'cells %d' % len(grid_data),
        'undo  %d / %d' % (len(undo_stack), UNDO_LIMIT),
    )
    pad, line_h, box_w = 6, 18, 168
    box_h = pad * 2 + line_h * len(lines)
    box = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    box.fill(_tint(COLOR_BG, 190))
    screen.blit(box, (10, 10))
    pygame.draw.rect(screen, COLOR_ON, (10, 10, box_w, box_h), 1)
    for i, line in enumerate(lines):
        screen.blit(PERF_FONT.render(line, True, COLOR_ON), (10 + pad, 10 + pad + i * line_h))
#======================================================================
#  主循环 main：固定 60 FPS 的 事件 -> 推进 -> 渲染
#======================================================================


def main():
    """固定 60 FPS：收事件 -> 平移 -> 按需推进时序 -> 渲染并翻页。"""
    global grid_changed, cached_ray_segments, minimap_dirty, _pending_solve
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
        # 编辑(grid_changed)：当场一次性解完，保证放置/擦除的即时反馈。
        # 时序推进(timeline)：改为分帧摊销，把每刻全量 solve 摊到多帧，抹平帧率尖峰。
        solved_this_frame = False
        if grid_changed:
            grid_changed = False
            last_tick_at = time.perf_counter()
            _pending_solve = None      # 作废在途的时序任务，避免脏结果
            _solve_t0 = time.perf_counter()
            cached_ray_segments = step_tick(advance=not paused)
            _PERF['solve_ms'] = (time.perf_counter() - _solve_t0) * 1000.0
            minimap_dirty = True
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
                minimap_dirty = True
                solved_this_frame = True
        cam_moved = (camera_x, camera_y, zoom) != prev_cam
        esc_active = _game_esc_time > 0 and \
                     pygame.time.get_ticks() - _game_esc_time < _ESC_RETURN_WIN
        scene_dirty = (_got_event or cam_moved or solved_this_frame or
                       delete_held or place_held or perf_visible or
                       esc_active or esc_active != _prev_esc_active)
        _prev_esc_active = esc_active
        if scene_dirty:
            draw_scene(cached_ray_segments)
            _draw_game_esc_hint()
            if perf_visible:
                _draw_perf_panel()
            pygame.display.flip()


if __name__ == '__main__':
    _load_settings()
    apply_keymap()
    main()
    pygame.quit()
