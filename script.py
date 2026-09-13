

"""灵光一现 —— 光线光学沙盘（pygame 实现）

在 8000 x 8000 格、以世界原点 (0,0) 为中心的网格里放置八类光学元件，求解光路并渲染：
直线传播、镜面反射、半透分光、聚光激活、光敏晶体 AND 门、存储石上升沿翻转、延时块按刻放行。
安装 pygame 后直接执行本文件，窗口可拖大缩小。

元件（数字键 0-7 = 工具下标；dir 一律指“输出边 / 凸起所指边”，0=上 1=右 2=下 3=左顺时针）：
    0 block 方块：吸收光线，无状态            1 light 光源：沿 dir 发射，带手动开关，被光击中即熄灭
    2 mirror 折光镜：受光即开，按朝向反射      3 splitter 半透：直行透射 + 派生一束反射光，受光即开
    4 collector 聚光镜：三入一出，激活后从输出边发射
    5 crystal 光敏晶体：AND 门，信号光沿透光轴穿过，控制光垂直入射只当开关
    6 store 存储石：1 出 3 入，输入边出现新的 0->1 就翻转输出（记忆位）
    7 delay 延时块：正方形加叉号，四边都是端口；任一面进来的光一律被吸收，
      攒够 delay 刻之后才从“进来的那一侧的对边”原方向放出（真正的延迟线）
状态约定（两套，分工明确）：
    用户态：is_on（只有光源带手动开关）、state（存储石记忆位）、delay（延时刻度）、dir；
    派生态：is_lit —— 恒等于“这一刻的光路算完之后它到底亮不亮”，渲染层只读它，
            因此贴图不可能再与真实状态不一致。

时序模型（全文件只有这一套，而且只与延时块有关）：
    1. 全图只有一个“刻”，每刻长度固定为 TICK_INTERVAL_S 秒，自动往前推进，不提供调速；
       “刻”是唯一的时序单位，换算关系就一条：延时刻度 n 刻 = n x TICK_INTERVAL_S 秒。
    2. 一刻 = 解一次光路（镜 / 半透 / 聚光 / 晶体 AND / 存储石 / 光源熄灭全在这一刻之内
       迭代到不动点）+ 刻末统一推进一次延迟线。除延时块以外的元件一律零刻延迟：
       摆下去当场就是终态，晶体 AND 门也不再带任何门延迟。
    3. 跨刻的记忆只有延时块的延迟线 pipe 一件：第 t 刻注入、第 t+delay 刻放出，
       delay 只由刻数决定（1~12 刻），与光走了几格、这一刻解了几轮都无关。
    4. 其余元件一概不碰延时：不读写 pipe / out_ready / inject，也不带跨刻状态。
       光源被打灭、存储石翻转、晶体导通都只在本刻内成立，下一刻从头再解一次；
       于是“灯被对射打灭之后怎么都救不回来”这类死局在结构上就不存在了。
    5. 只有编辑动作和 R 键会复位时序（刻号归零 + 清空全部延迟线）。

元件一律预渲染 icon：基准图 -> 四方向帧 -> on/off 两套色 -> 缩放缓存后 blit，没有每帧即时 draw。

按键：右键放置 | 左键擦除 | 中键拖拽平移 | 滚轮以光标为锚缩放 | WASD/方向键平移
     Q 逆时针 E 顺时针旋转光标格（压在延时块上 = 调延时刻度 1-12 刻）
     F 光源切开关 / 存储石复位输出 / 延时块排空延迟线 | M 小地图显隐
     R 复位时序：刻号归零 + 清空全部延迟线
     F1 / F2 / F3 存三个槽位（saves/slot1-3.json，原子写盘）| F4 读最近一份
     Enter+F4 粘贴：取存档 row/col 最小角对齐光标格，整块平移并入当前世界（一步 Z 撤掉整块）
     Z 撤销 | X 重做（放置 / 擦除 / 旋转 / F 开关 / 粘贴 / 读档均可撤；delta 快照，栈深 200）
     小地图内左键点击或拖拽跳转视口

光路求解有四道防卡死闸门（单轮射线数 / 总步数 / 光段数 / 墙钟），超限就地截断并在 HUD 末行报 TRUNC。

章节：01 窗口调色板 02 世界相机 03 世界状态与时间步 04 渲染资源 05 几何工具
     06 光路追踪与延时刻线 07 渲染 08 小地图 09 HUD 10 输入 11 存读撤重 12 主循环
"""
import copy
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Iterator, List, Optional, Set, Tuple

import pygame

pygame.init()

# ── 01. 窗口与调色板 ──────────────────────────────────────────────
WINDOW_WIDTH, WINDOW_HEIGHT = 1400, 750
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("灵光一现")
clock = pygame.time.Clock()                      # 固定 60 FPS

COLOR_BG = (30, 30, 30)
COLOR_GRID = (60, 60, 60)
COLOR_ON = (100, 149, 237)                       # 元件“开”态与光路颜色
COLOR_OFF = (105, 105, 105)                      # 元件“关”态
COLOR_HOVER = (255, 255, 255, 30)
COLOR_HUD_TEXT = COLOR_ON
COLOR_HUD_BG = (0, 0, 0, 80)

# ── 02. 世界与相机 ────────────────────────────────────────────────
BASE_CELL_SIZE = 40                              # zoom=1.0 时一格的像素尺寸
WORLD_HALF_COLS = WORLD_HALF_ROWS = 4000         # 行列均为 -4000 到 3999，原点居中
WORLD_COLS, WORLD_ROWS = WORLD_HALF_COLS * 2, WORLD_HALF_ROWS * 2
WORLD_WIDTH_PX, WORLD_HEIGHT_PX = WORLD_COLS * BASE_CELL_SIZE, WORLD_ROWS * BASE_CELL_SIZE
WORLD_MIN_PX = -WORLD_HALF_COLS * BASE_CELL_SIZE  # 世界边界的世界像素坐标
WORLD_MAX_PX = WORLD_HALF_COLS * BASE_CELL_SIZE
WORLD_MIN_PY, WORLD_MAX_PY = WORLD_MIN_PX, WORLD_MAX_PX

camera_x = -WINDOW_WIDTH / 2.0                   # 初始让世界原点落在屏幕正中
camera_y = -WINDOW_HEIGHT / 2.0
zoom = 1.0
MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 0.4, 5.0, 0.1
PAN_SPEED_PX = 500                               # WASD / 方向键平移速度（世界像素/秒）
MAX_FRAME_DT_S = 0.05                            # 单帧 dt 上限，防切后台回来一步甩出世界

# ── 03. 世界状态与时间步 ──────────────────────────────────────────
Coord = Tuple[int, int]                          # 格坐标 (row, col)
Point = Tuple[float, float]                      # 世界像素坐标 (x, y)
Segment = Tuple[Point, Point]                    # 一段光路
RaySeed = RayState = Tuple[int, int, int]        # 射线 / 射线状态：(row, col, direction)
HandlerResult = Optional[Tuple[Coord, int, Point]]

def _etype(data: dict) -> str:
    """取元件类型并保证是 str：坏档的异常值退化成空串，查表落默认分支而不抛 KeyError。"""
    element_type = data.get('type')
    return element_type if isinstance(element_type, str) else ''

grid_data: Dict[Coord, dict] = {}                # (row, col) -> 元件数据（唯一数据源）
current_tool = 1
grid_changed = True                              # 脏标记：元件变化时置 True
cached_ray_segments: List[Segment] = []          # 光路缓存，元件没变就不重算

TOOL_TYPES = ('block', 'light', 'mirror', 'splitter', 'collector', 'crystal', 'store',
             'delay')
SWITCHABLE_TYPES = ('light',)                    # 只有光源带 F 手动开关
TOOL_SPECS = {                                   # 放置数据的唯一定义处（lambda 保证每格新对象）
    'block': lambda: {'type': 'block', 'dir': 0},
    'light': lambda: {'type': 'light', 'dir': 0, 'is_on': True},
    'mirror': lambda: {'type': 'mirror', 'dir': 0, 'is_lit': False},
    'splitter': lambda: {'type': 'splitter', 'dir': 0, 'is_lit': False},
    'collector': lambda: {'type': 'collector', 'dir': 0},
    'crystal': lambda: {'type': 'crystal', 'dir': 0},
    'store': lambda: {'type': 'store', 'dir': 0, 'is_lit': False, 'state': 0,
                      'in_levels': frozenset()},
    # delay 四向对称，dir 恒 0 只为与其余元件共用贴图与序列化口径；
    # inject / pipe / out_ready 都是时序态：inject 是本刻注入账，pipe 是延迟线，
    # out_ready 是本刻该放行的方向。三者一律不写盘（见 PERSIST_FIELDS 注释）。
    'delay': lambda: {'type': 'delay', 'dir': 0, 'delay': delay_setting,
                      'is_lit': False, 'inject': set(), 'pipe': [], 'out_ready': ()},
}
TOOL_NAMES = ['%d %s' % (i, name) for i, name in enumerate(TOOL_TYPES)]

MAX_RAY_STEPS = WORLD_COLS + WORLD_ROWS          # 单束上限＝世界曼哈顿直径，合法长折线不误截
MAX_LIGHT_ROUNDS = 80                            # 外层迭代上限
# 防卡死硬预算：单束上限只 bound 住一条射线，半透每过一次多派生一束，射线总数不受它约束。
# 故整轮另有四道闸门，任一触发就地截断（已画光路保留、不补画猜测几何），HUD 报 TRUNC。
MAX_RAYS_PER_ROUND = 20000
MAX_STEPS_PER_ROUND = 1000000
MAX_TRACE_SEGMENTS = 50000
TRACE_TIME_LIMIT_S = 0.30
trace_note = 'ok'                                # 上一轮光路收尾状态，HUD 末行直接显示

# 时序：全图只有一个“刻”，长度固定；跨刻记忆只有延时块的延迟线这一件
DELAY_DEFAULT_TICKS = 3                          # 放置时写入的默认延时刻度（单位：刻）
DELAY_MIN_TICKS, DELAY_MAX_TICKS = 1, 12         # Q / E 调刻度的合法区间
TICK_INTERVAL_S = 0.1                            # 每刻固定长度（秒），不提供调速按键
tick_index = 0                                   # 已推进的刻数（编辑 / 撤销 / 读档 / R 后归零）
delay_ready = 0                                  # 上一刻结束时正在放行的延时块数
timeline_present = False                         # 世界里是否存在延时块（缓存标志）
tick_note = ''                                   # 复位提示，HUD 时序行显示
delay_setting = DELAY_DEFAULT_TICKS              # 下一个延时块的刻度（Q/E 在空格上调它）

# ── 04. 渲染资源：icon 一律预渲染，四方向共用一套工厂 ──────────────
ICON_SIZE = BASE_CELL_SIZE
ICON_MAIN = int(ICON_SIZE * 0.7)                 # 光源主体边长
ICON_BLOCK = int(ICON_SIZE * 0.8)
ICON_PROTRUDE = max(3, int(ICON_SIZE * 0.2))     # 输出方向凸起边长
ICON_LINE_W = max(2, int(ICON_SIZE * 0.1))
ICON_INSET = int(ICON_SIZE * 0.2)
ICON_BAR_LEN = int(ICON_SIZE * 0.88)             # 晶体栅条
ICON_BAR_W = max(2, int(ICON_SIZE * 0.08))
ICON_BAR_GAP = int(ICON_SIZE * 0.22)             # 透光槽宽
ICON_RING_R, ICON_RING_W = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.12)
ICON_STORE_R, ICON_STORE_CORE = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.25)

CLEAR = (0, 0, 0, 0)

def _surf() -> pygame.Surface:
    """与格子等大的透明底画布（SRCALPHA，便于层层叠加）。"""
    return pygame.Surface((ICON_SIZE, ICON_SIZE), pygame.SRCALPHA)

def _icon_frames(base: pygame.Surface) -> Dict[int, pygame.Surface]:
    """基准朝向（dir=0）展开成四方向帧；pygame 的 rotate 逆时针为正，dir 顺时针，故取 -90 倍数。"""
    return {d: (base if d == 0 else pygame.transform.rotate(base, -90 * d)) for d in range(4)}

def _rect(surf, color, size):
    """在画布正中画一个 size x size 的实心方块。"""
    off = (ICON_SIZE - size) // 2
    pygame.draw.rect(surf, color, (off, off, size, size))

def _protrude(surf, color):
    """上边缘居中的小方块凸起；dir=0 指向上，旋转四方向帧即改变所指边。"""
    off = (ICON_SIZE - ICON_PROTRUDE) // 2
    pygame.draw.rect(surf, color, (off, 0, ICON_PROTRUDE, ICON_PROTRUDE))

def _slash(surf, color, slash):
    """镜面斜线：slash=True 为“/”（左下->右上），False 为反斜。"""
    if slash:
        a, b = (ICON_INSET, ICON_SIZE - ICON_INSET), (ICON_SIZE - ICON_INSET, ICON_INSET)
    else:
        a, b = (ICON_INSET, ICON_INSET), (ICON_SIZE - ICON_INSET, ICON_SIZE - ICON_INSET)
    pygame.draw.line(surf, color, a, b, ICON_LINE_W)

def _diamond(surf, color, radius):
    """以格心为顶点的菱形（顶点上下左右各 radius）。"""
    cx = cy = ICON_SIZE // 2
    pygame.draw.polygon(surf, color, [(cx, cy - radius), (cx + radius, cy),
                                      (cx, cy + radius), (cx - radius, cy)])

def _make_light_icon(color):
    """光源：居中主体 + 上沿凸起，凸起所指即 dir=0 时的发射方向。"""
    surf = _surf(); _rect(surf, color, ICON_MAIN); _protrude(surf, color); return surf

def _make_block_icon(color):
    """方块：实心方块，无开关态，只注册一套色。"""
    surf = _surf(); _rect(surf, color, ICON_BLOCK); return surf

def _make_mirror_icon(color):
    """折光镜：一条镜面斜线，dir=0 画“/”。"""
    surf = _surf(); _slash(surf, color, True); return surf

def _make_splitter_icon(color):
    """半透镜：方形外框 + 内部一条镜面斜线，关态时框与线一起变暗灰。"""
    surf = _surf()
    inner = pygame.Rect(ICON_INSET, ICON_INSET, ICON_SIZE - 2 * ICON_INSET,
                        ICON_SIZE - 2 * ICON_INSET)
    pygame.draw.rect(surf, color, inner, ICON_LINE_W)
    _slash(surf, color, True)
    return surf

def _make_collector_icon(color):
    """聚光镜：空心圆环 + 上沿凸起（环内盖一张透明圆挖空中心）。"""
    surf = _surf(); c = ICON_SIZE // 2
    pygame.draw.circle(surf, color, (c, c), ICON_RING_R)
    pygame.draw.circle(surf, CLEAR, (c, c), ICON_RING_R - ICON_RING_W)
    _protrude(surf, color)
    return surf

def _make_crystal_icon(color):
    """光敏晶体：两条竖向栅条夹一条透光槽（dir=0 时透光轴水平）。"""
    surf = _surf(); cx = cy = ICON_SIZE // 2
    top = cy - ICON_BAR_LEN // 2
    for left in (cx - ICON_BAR_GAP // 2 - ICON_BAR_W, cx + ICON_BAR_GAP // 2):
        pygame.draw.rect(surf, color, (left, top, ICON_BAR_W, ICON_BAR_LEN))
    return surf

def _make_store_icon(color):
    """存储石：空心菱形（大小两菱形叠出边框，掏空用透明色故不留死黑）+ 上沿输出凸起。"""
    surf = _surf()
    _diamond(surf, color, ICON_STORE_R)
    if ICON_STORE_R - ICON_LINE_W > 0:
        _diamond(surf, CLEAR, ICON_STORE_R - ICON_LINE_W)
    if color == COLOR_ON:
        _diamond(surf, color, ICON_STORE_CORE)
    _protrude(surf, color)
    return surf

# 延时块的图标见 _make_delay_icon：正方形外框 + 叉号，四向对称不带凸起

def _make_delay_icon(color):
    """延时块：正方形外框 + 框内叉号。四向对称，四边既是入边也是出边，故不带凸起。"""
    surf = _surf()
    inner = pygame.Rect(ICON_INSET, ICON_INSET, ICON_SIZE - 2 * ICON_INSET,
                        ICON_SIZE - 2 * ICON_INSET)
    pygame.draw.rect(surf, color, inner, ICON_LINE_W)
    _slash(surf, color, True)
    _slash(surf, color, False)
    return surf

def _make_off_mark_icon(color):
    """手动关闭标记：两条对角线交成斜十字，绘制时叠在元件之上。"""
    surf = _surf(); _slash(surf, color, True); _slash(surf, color, False); return surf

ICONS: Dict[str, Dict[int, pygame.Surface]] = {}

# 六类带开 / 关两态的元件：同一几何配两套色，一次注册八组帧
for _name, _maker in (('light', _make_light_icon), ('mirror', _make_mirror_icon),
                      ('splitter', _make_splitter_icon), ('collector', _make_collector_icon),
                      ('crystal', _make_crystal_icon), ('store', _make_store_icon),
                      ('delay', _make_delay_icon)):
    for _suffix, _color in (('_on', COLOR_ON), ('_off', COLOR_OFF)):
        ICONS[_name + _suffix] = _icon_frames(_maker(_color))

ICONS['block'] = _icon_frames(_make_block_icon(COLOR_OFF))       # 方块不导光也无开态
ICONS['off_mark'] = _icon_frames(_make_off_mark_icon(COLOR_ON))  # 标记不随朝向变化

_SCALED_CACHE: Dict[Tuple[str, int, int], pygame.Surface] = {}   # (icon名, 方向, 屏幕边长) -> 已缩放
SCALED_CACHE_LIMIT = 3000                       # 连续滚轮会不断产生新边长，超量整表丢弃

def blit_icon(name: str, direction: int, screen_x: int, screen_y: int,
              cell_size: int) -> None:
    """统一落图入口：按名取帧 -> 缩到当前格子尺寸（带缓存，超上限整表丢弃）-> blit 到屏幕。"""
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

# ── 05. 方向与坐标工具 ────────────────────────────────────────────
REFLECT_ON_SLASH = {0: 1, 1: 0, 2: 3, 3: 2}          # “/” 镜：上<->右、下<->左
REFLECT_ON_BACKSLASH = {0: 3, 3: 0, 2: 1, 1: 2}      # 反斜镜：上<->左、下<->右
STEP_BY_DIR = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}

def reflected_direction(direction, mirror_dir):
    """打到镜子后的新方向：偶数 dir 画“/”、奇数画反斜（贴图与光路共用此判据）。"""
    table = REFLECT_ON_SLASH if mirror_dir % 2 == 0 else REFLECT_ON_BACKSLASH
    return table.get(direction, direction)

def crystal_ports(out_dir):
    """晶体只看 dir 奇偶，返回（信号光方向, 控制光方向）：偶数 dir 透光轴水平。"""
    return ((1, 3), (0, 2)) if out_dir % 2 == 0 else ((0, 2), (1, 3))

def store_ports(out_dir):
    """存储石端口分配：dir 所指的边是输出边，其余三条边为输入边。"""
    out_dir %= 4
    return out_dir, tuple(d for d in range(4) if d != out_dir)

def _next_cell(row, col, direction):
    d_row, d_col = STEP_BY_DIR[direction]
    return row + d_row, col + d_col

def _cell_center(col, row):
    """格心世界坐标 (x, y)。"""
    return (col + 0.5) * BASE_CELL_SIZE, (row + 0.5) * BASE_CELL_SIZE

EDGE_PX = {0: ('y', WORLD_MIN_PY), 1: ('x', WORLD_MAX_PX),
           2: ('y', WORLD_MAX_PY), 3: ('x', WORLD_MIN_PX)}   # 方向 -> 该方向上的世界边界


def _ray_end_at_world_edge(col, row, direction):
    """光线从当前格沿 direction 射出后，钉在世界边界上的终点坐标。"""
    axis, value = EDGE_PX[direction]
    end_x, end_y = _cell_center(col, row)
    return (value, end_y) if axis == 'x' else (end_x, value)

def _in_world_bounds(row, col):
    return -WORLD_HALF_COLS <= col < WORLD_HALF_COLS and -WORLD_HALF_ROWS <= row < WORLD_HALF_ROWS

def _add_segment(segments: List[Segment], start: Point, end: Point) -> None:
    """登记一段光路（世界坐标）；全文件只有这一个写入口。"""
    segments.append((start, end))

def _view_range():
    """当前视口的格范围 (r0, c0, r1, c1)：floor 除法对负坐标同样成立，右下多带 2 格余量防平移缩放时边缘闪烁。"""
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

# ── 06. 光路追踪（本文件核心）─────────────────────────────────────
# 外层反复“重算一帧”直到无变化；每轮做五件事：清动态态 -> 消化射线（点亮镜/半透、记下
# 被击中的光源与受光的存储石输入边）-> 晶体 AND -> 存储石上升沿 -> 光源熄灭锁定。
# 提速：首轮一次全表扫描同时交出三份集合，第二轮起只清上一轮真被光碰过的格子。
# 防卡死：ctx.seen 记“从哪格、朝哪个方向进入目标格”的状态，重复状态必是重复几何且零新增

@dataclass
class TraceCtx:
    """一轮光路的记账本：待消化队列、各类记账集合与预算计数器（带类型，取代异构 dict）。"""
    segments: List[Segment] = field(default_factory=list)
    pending: Deque[RaySeed] = field(default_factory=deque)
    hit_lights: Set[Coord] = field(default_factory=set)         # 本轮被击中的光源格
    seen: Set[RayState] = field(default_factory=set)            # 本轮已走过的射线状态
    lit_relay: Set[Coord] = field(default_factory=set)          # 就地“开”的镜 / 半透
    lit_focus: Set[Coord] = field(default_factory=set)          # 激活的聚光镜
    touched_crystals: Set[Coord] = field(default_factory=set)   # 记过入账的晶体
    touched_stores: Set[Coord] = field(default_factory=set)     # 记过入账的存储石
    touched_delays: Set[Coord] = field(default_factory=set)     # 本轮被光打进来的延时块
    delay_injects: Dict[Coord, Set[int]] = field(default_factory=dict)  # 本轮各延时块的注入方向
    rays: int = 0
    steps: int = 0
    deadline: float = 0.0
    aborted: bool = False
    abort_reason: str = ''

def _reset_cell_dynamic(coord: Coord, data: dict, dark: Optional[Set[Coord]] = None,
                        crystal_lit: Optional[bool] = None) -> None:
    """全文件唯一的动态态清基线口径：把一格清回“这一刻开始时它应处的态”。

    除延时块以外没有任何跨刻记忆，所以基线就是“全图静止”：光源按 is_on、晶体一律不亮、
    存储石按记忆位、镜 / 半透 / 聚光一律不亮；只有延时块的 out_ready（上一刻末排好的
    放行方向）要如实带进本刻。dark 与 crystal_lit 只在同一刻的多轮迭代里用：本轮已判定
    熄灭的灯不再复亮、本轮已判定导通的晶体本轮就当它导通，跨刻一律不带。
    block 无动态态、未知类型一律不碰。
    """
    element_type = data['type']                      # type 键由 TOOL_SPECS 与 _normalize_cell 保证存在
    if element_type == 'light':
        data['is_lit'] = bool(data.get('is_on', True)) and not (dark and coord in dark)
    elif element_type == 'crystal':
        data['axis_inputs'] = set()                  # 实际到达的信号光（沿透光轴）方向
        data['perp_inputs'] = set()                  # 实际到达的控制光（垂直透光轴）方向
        data['is_lit'] = False if crystal_lit is None else bool(crystal_lit)
    elif element_type == 'store':
        data['is_lit'] = bool(data.get('state'))     # 画面亮暗只反映记忆位
        data['input_dirs'] = set()
    elif element_type in ('collector', 'mirror', 'splitter'):
        data['is_lit'] = False                       # 受光即开 / 被照才激活，先当关
    elif element_type == 'delay':
        # 全图唯一带跨刻记忆的元件：out_ready 要带进本刻，注入账 inject 只活在 ctx 里，
        # 解完这一刻才落回 data（刻末由 _advance_delay_lines 统一消化）。
        data['is_lit'] = bool(data.get('out_ready'))


def _wipe(coord: Coord, dark: Optional[Set[Coord]] = None,
          crystal_lit: Optional[bool] = None) -> Optional[dict]:
    """刻内轮间增量清态入口：口径与 _reset_cell_dynamic 完全同一份实现，不再有第二套。"""
    data = grid_data.get(coord)
    if data is None:
        return None
    _reset_cell_dynamic(coord, data, dark, crystal_lit)
    return data


def _baseline_reset() -> Tuple[List[Coord], Set[Coord], List[Coord], List[Coord]]:
    """按“全图静止”清基线，一次遍历交出四份播种用集合
    （开着的光源 / 记忆位置 1 的存储石 / 全部存储石 / 全部延时块）。
    一刻的第 0 轮开头只调这一处；延时块以外没有任何上一刻的结论要继承。
    """
    light_on: List[Coord] = []
    emitting_stones: Set[Coord] = set()
    store_coords: List[Coord] = []
    delay_coords: List[Coord] = []
    for coord, data in grid_data.items():
        _reset_cell_dynamic(coord, data)             # 口径唯一：与 _wipe 共用，不再有两份实现
        element_type = data['type']
        if element_type == 'light':
            if data['is_lit']:
                light_on.append(coord)
        elif element_type == 'store':
            store_coords.append(coord)
            if data['is_lit']:
                emitting_stones.add(coord)
        elif element_type == 'delay':
            delay_coords.append(coord)
    return light_on, emitting_stones, store_coords, delay_coords


def _incremental_reset(prev: TraceCtx, dark: Set[Coord], lit_crystals: Set[Coord]) -> None:
    """第 1 轮起的增量清态：只动上一轮真被光碰过的格子，与 _baseline_reset 等价。

    其余格子这一轮没人读旧值：镜与半透要么这轮被照到（处理器会重置 True），
    要么压根没光进来（保持关态就是正确答案）。
    """
    for coord in prev.lit_relay | prev.lit_focus:
        _wipe(coord, dark)
    for coord in prev.touched_crystals | lit_crystals:
        _wipe(coord, dark, crystal_lit=coord in lit_crystals)
    for coord in prev.touched_stores | prev.touched_delays:
        _wipe(coord, dark)


def _seed_rays(emitting_lights: Set[Coord], emitting_stones: Set[Coord],
               delay_seeds: Optional[List[RaySeed]] = None) -> List[RaySeed]:
    """播种本轮射线：存活光源与置位存储石各按其 dir 发一束，刻末到点的延时块按放行方向补一束（排序只为结果稳定）；被光打灭的灯与置 0 的存储石已由外层筛掉，天然不在集合里。"""
    return [(r, c, grid_data[(r, c)]['dir'])
            for group in (sorted(emitting_lights), sorted(emitting_stones)) for r, c in group] \
        + sorted(delay_seeds or [])

def _abort_trace(ctx: TraceCtx, reason: str) -> None:
    """标记本轮被预算截断并记下原因；只记第一次，之后的预算判定直接短路。"""
    if not ctx.aborted:
        ctx.aborted = True
        ctx.abort_reason = reason

def _spawn_ray(ctx: TraceCtx, row: int, col: int, direction: int) -> bool:
    """回灌一条派生射线（半透反射、聚光镜激活都走这里），受单轮射线数预算约束。预算耗尽只是这条新束不再派生，在途射线照常走完：既保住已画光路，也保证外层 while 必在有限步内退出。"""
    if ctx.aborted:
        return False
    if ctx.rays + len(ctx.pending) >= MAX_RAYS_PER_ROUND:
        _abort_trace(ctx, 'rays>%d' % MAX_RAYS_PER_ROUND)
        return False
    ctx.pending.append((row, col, direction))
    return True

# 七类处理器签名是注册表协议要求的，用不到的形参冠 _ 前缀（等价于就地声明协议位）。
def _handle_light(ctx, coord, hit_data, _direction):
    """光源：记入本轮“被打灭”集合；入射段已由派发方登记到灯心，光在此被灯身挡住。"""
    ctx.hit_lights.add(coord)

def _handle_mirror(ctx, coord, hit_data, direction):
    """折光镜：光一到就地“开”，按镜面朝向改向，从本格格心继续传播。"""
    hit_data['is_lit'] = True
    ctx.lit_relay.add(coord)
    return coord, reflected_direction(direction, hit_data['dir']), _cell_center(coord[1], coord[0])

def _handle_splitter(ctx, coord, hit_data, direction):
    """半透镜：本束原方向直行透射，同时把反射方向回灌成一条新射线。"""
    hit_data['is_lit'] = True
    ctx.lit_relay.add(coord)
    _spawn_ray(ctx, coord[0], coord[1], reflected_direction(direction, hit_data['dir']))
    return coord, direction, _cell_center(coord[1], coord[0])

def _handle_collector(ctx, coord, hit_data, direction):
    """聚光镜：非逆向入射（不从输出边进）且本轮未点亮时激活，并朝输出方向回灌一束；无论激活与否，入射光都停在该格不再透射。"""
    output_dir = hit_data['dir']
    if direction != (output_dir + 2) % 4 and not hit_data['is_lit']:
        hit_data['is_lit'] = True
        ctx.lit_focus.add(coord)
        _spawn_ray(ctx, coord[0], coord[1], output_dir)

def _handle_crystal(ctx, coord, hit_data, direction):
    """
        光敏晶体 AND 门：控制光（垂直透光轴）只入 perp_inputs 账并被栅条吸收；信号光（沿透光轴）记 axis_inputs，本格已点亮才透射到轴另一端，未点亮则被吸收。点亮与否由 _collect_lit_crystals 按“两路都到过”统一判定。
    """
    axis_dirs, perp_dirs = crystal_ports(hit_data['dir'])
    ctx.touched_crystals.add(coord)
    if direction in perp_dirs:
        hit_data['perp_inputs'].add(direction)
        return None
    hit_data['axis_inputs'].add(direction)
    if hit_data['is_lit']:
        return coord, direction, _cell_center(coord[1], coord[0])

def _handle_store(ctx, coord, hit_data, direction):
    """存储石：按“光从哪条边进入本格”记电平 1，入射光一律被菱形本体吸收。入射边＝行进方向的反向；光打到输出边同样被吸收，但输出端不记电平。"""
    _, input_dirs = store_ports(hit_data['dir'])
    entry_edge = (direction + 2) % 4
    if entry_edge in input_dirs:
        hit_data['input_dirs'].add(entry_edge)
        ctx.touched_stores.add(coord)

def _handle_delay(ctx, coord, hit_data, direction):
    """延时块：全图唯一真正跟“刻”有关的元件。

    光一律被本体吸收，只在账上记一笔“这一轮从 direction 进来过”，放不放行由刻末
    _advance_delay_lines 按延迟线决定，本刻绝不派生射线。其余元件的处理器都不碰这里。
    """
    ctx.delay_injects.setdefault(coord, set()).add(direction)
    hit_data['is_lit'] = True
    ctx.touched_delays.add(coord)


def _handle_block(ctx, coord, hit_data, direction):
    """方块：入射段登记完即止，既不透射也不派生新射线（兼作未登记类型的兜底）。"""

# 注册表：返回 None 表示光在此终止，返回 (格子, 新方向, 新起点) 表示继续传播
ELEMENT_HANDLERS: Dict[str, Callable[..., HandlerResult]] = {
    'block': _handle_block, 'light': _handle_light, 'mirror': _handle_mirror,
    'splitter': _handle_splitter, 'collector': _handle_collector,
    'crystal': _handle_crystal, 'store': _handle_store, 'delay': _handle_delay,
}

def _trace_one_ray(ctx: TraceCtx) -> None:
    """
        推进队首的一条射线，直到被吸收、出界、走满 MAX_RAY_STEPS 或撞到任一预算。ctx.seen 记“从哪格、朝哪个方向进入目标格”，同一轮重复该状态必是重复几何且零新增记账（镜与半透只改配色、聚光镜一次性激活、晶体点亮到轮末才生效），故掐掉不丢光路；走满上限只就地截断，绝不从当前格补画到边界的假线。
    """
    segments, pending, seen = ctx.segments, ctx.pending, ctx.seen
    cur_row, cur_col, direction = pending.popleft()
    ctx.rays += 1
    start = _cell_center(cur_col, cur_row)

    for _step in range(MAX_RAY_STEPS):
        next_row, next_col = _next_cell(cur_row, cur_col, direction)
        if not _in_world_bounds(next_row, next_col):
            _add_segment(segments, start, _ray_end_at_world_edge(cur_col, cur_row, direction))
            return
        state = (next_row, next_col, direction)
        if state in seen:                             # 同一轮已原样走过 -> 后面全是重复几何
            return
        seen.add(state)
        ctx.steps += 1
        if ctx.steps >= MAX_STEPS_PER_ROUND:
            _abort_trace(ctx, 'steps>%d' % MAX_STEPS_PER_ROUND)
        elif len(segments) >= MAX_TRACE_SEGMENTS:
            _abort_trace(ctx, 'segments>%d' % MAX_TRACE_SEGMENTS)
        elif not (ctx.steps & 0xFFF) and time.perf_counter() > ctx.deadline:
            _abort_trace(ctx, 'time>%.2fs' % TRACE_TIME_LIMIT_S)
        if ctx.aborted:                               # 就地收工，不补画猜测的几何
            return
        hit_data = grid_data.get((next_row, next_col))
        if hit_data is None:                          # 空格：继续前进
            cur_row, cur_col = next_row, next_col
            continue
        _add_segment(segments, start, _cell_center(next_col, next_row))  # 入射段全类型通用
        handler = ELEMENT_HANDLERS.get(_etype(hit_data), _handle_block)
        result = handler(ctx, (next_row, next_col), hit_data, direction)
        if result is None:
            return
        (cur_row, cur_col), direction, start = result

    # 走满单束上限只剩病态布局这一种解释（正常折线的状态数已被去重限制在 格数x4 内）
    _abort_trace(ctx, 'ray steps>%d' % MAX_RAY_STEPS)

def _collect_lit_crystals(ctx: TraceCtx) -> Set[Coord]:
    """AND 判定：同一格里信号光与控制光都到过才点亮；只查本轮真被光碰过的晶体。"""
    lit: Set[Coord] = set()
    for coord in ctx.touched_crystals:
        data = grid_data.get(coord)
        if data is not None and data.get('axis_inputs') and data.get('perp_inputs'):
            lit.add(coord)
    return lit

def _advance_store_states(candidates: List[Coord], armed_stores: Set[Coord]
                          ) -> Tuple[Set[Coord], Set[Coord]]:
    """
        比对本轮与上一轮的输入边电平，按上升沿个数翻转输出状态（奇换偶不换）。in_levels 为 None 表示刚放置 / 刚旋转 / 刚复位，只记基准不补算上升沿；candidates 后续轮要并上“上一轮电平非空”的一批，否则光撤走后电平落不回空集，下次受光就不算上升沿了。
    """
    flipped: Set[Coord] = set()
    armed: Set[Coord] = set(armed_stores)
    for coord in candidates:
        data = grid_data.get(coord)
        if data is None:
            continue
        _, input_dirs = store_ports(data['dir'])
        levels = frozenset(d for d in data.get('input_dirs') or () if d in input_dirs)
        previous = data['in_levels']
        if previous is not None:
            rising = len([edge for edge in levels if edge not in previous])
            if rising:
                data['state'] = (data['state'] + rising) % 2
                data['is_lit'] = bool(data['state'])
                flipped.add(coord)
        data['in_levels'] = levels                    # 本轮电平成为下一轮的基准
        if levels:
            armed.add(coord)
        else:
            armed.discard(coord)
    return flipped, armed

def solve_tick(delay_seeds: List[RaySeed]) -> Tuple[List[Segment], List[Coord], bool]:
    """解一次光路，并把光路、晶体导通、存储石记忆位、光源熄灭收敛到一致（幂等）。

    这一层完全没有“时序”概念：一轮五件事（清动态态 -> 消化射线 -> 晶体 AND -> 存储石
    上升沿 -> 光源熄灭锁定），反复迭代到不动点。于是除延时块以外的元件都是零刻延迟的
    组合逻辑——摆下去当场就是终态，晶体 AND 门同刻即亮即导通，不需要任何跨刻记忆。
    返回（光段, 全部延时块坐标, 是否被预算截断）；trace_note 就地写好，HUD 直接显示。
    """
    global trace_note, timeline_present
    light_on, emitting_stores, store_coords, delay_coords = _baseline_reset()
    timeline_present = bool(delay_coords)
    emitting: Set[Coord] = set(light_on)
    lit_crystals: Set[Coord] = set()
    armed_stores: Set[Coord] = set()
    dark: Set[Coord] = set()                          # 本刻内被打灭的灯（只活到本刻结束）
    ctx = TraceCtx()                                  # 循环外先建好，MAX_LIGHT_ROUNDS=0 也不引用未绑定
    used_rounds = 0
    converged = False
    segments: List[Segment] = []
    for round_index in range(MAX_LIGHT_ROUNDS):
        used_rounds = round_index + 1
        if round_index:                               # 此刻 ctx 还是上一轮那本账，照它增量清理
            _incremental_reset(ctx, dark, lit_crystals)
        ctx = TraceCtx()                              # 一轮一份新账，上一轮光段不带过来
        segments = ctx.segments
        ctx.pending = deque(_seed_rays(emitting, emitting_stores, delay_seeds))
        ctx.deadline = time.perf_counter() + TRACE_TIME_LIMIT_S
        while ctx.pending and not ctx.aborted:
            _trace_one_ray(ctx)
        if ctx.aborted:                               # 再迭代也只是反复截断，直接收工
            trace_note = 'TRUNC r%d %s (rays %d steps %d segs %d)' % (
                used_rounds, ctx.abort_reason, ctx.rays, ctx.steps, len(segments))
            break
        new_lit = _collect_lit_crystals(ctx)          # 同刻即时生效：两路到齐当轮就导通
        for coord in new_lit:
            grid_data[coord]['is_lit'] = True
        flipped, armed_stores = _advance_store_states(
            store_coords if round_index == 0 else list(ctx.touched_stores | armed_stores),
            armed_stores)
        newly_dark = ctx.hit_lights & emitting
        dark |= newly_dark
        if not newly_dark and new_lit == lit_crystals and not flipped:
            converged = True
            break
        emitting -= newly_dark
        lit_crystals = new_lit
        for coord in flipped:                         # 存储石发光集合跟着记忆位增量更新
            if grid_data[coord]['state']:
                emitting_stores.add(coord)
            else:
                emitting_stores.discard(coord)
    if not ctx.aborted:                # 跑满上限仍没收敛时如实报 MAXR，不冒充 ok
        trace_note = '%s r%d (rays %d steps %d segs %d)' % (
            'ok' if converged else 'MAXR', used_rounds, ctx.rays, ctx.steps, len(segments))
    for coord in dark:                                # 熄灭的灯当场就打灰，渲染层不再特判
        data = grid_data.get(coord)
        if data is not None:
            data['is_lit'] = False
    for coord, dirs in ctx.delay_injects.items():     # 注入账只留收敛那一轮的结论
        data = grid_data.get(coord)
        if data is not None and _etype(data) == 'delay':
            data['inject'] = set(dirs)
            data['is_lit'] = True
    return segments, delay_coords, ctx.aborted


def _delay_ticks(data: dict) -> int:
    """取延时刻度并夹进合法区间：坏档 / 手改的乱值一律退回默认，绝不让 len(pipe) 比较崩掉。"""
    try:
        ticks = int(data.get('delay', DELAY_DEFAULT_TICKS))
    except (TypeError, ValueError):
        ticks = DELAY_DEFAULT_TICKS
    return max(DELAY_MIN_TICKS, min(ticks, DELAY_MAX_TICKS))

def _advance_delay_lines(coords: List[Coord]) -> int:
    """刻末统一推进所有延迟线，返回本刻结束时正在放行的延时块数。

    口径：每一刻先收下本刻注入账（没有光也要记一个空位，否则“没光的刻”不计时，
    延时就成了“光走过的刻数”而不是真实刻数），线满 n 位才出队一位作为放行方向，
    于是 t 刻注入、第 t+n 刻放出，正好是“等 n 刻”。n 只由延时刻度决定，换算成秒
    就是 n x TICK_INTERVAL_S。必须在整刻解完之后统一做，不能放在处理器里就地推进，
    否则同一刻被碰两次就会多吃掉一格线位。
    """
    global delay_ready
    ready = 0
    for coord in coords:
        data = grid_data.get(coord)
        if data is None or _etype(data) != 'delay':
            continue
        ticks = _delay_ticks(data)
        inject = tuple(sorted(data.get('inject') or ()))
        data['inject'] = set()                        # 注入账只活到本刻结束
        pipe: List[Tuple[int, ...]] = data.setdefault('pipe', [])
        pipe.append(inject)
        data['out_ready'] = pipe.pop(0) if len(pipe) >= ticks else ()
        if len(pipe) > ticks:                         # 刻度被 Q/E 调小后裁掉多余线位
            del pipe[:len(pipe) - ticks]
        if data['out_ready']:
            data['is_lit'] = True                     # 正在往外放光才亮
            ready += 1
    delay_ready = ready
    return ready


def _delay_coords() -> List[Coord]:
    """当前世界里全部延时块坐标（延迟线与复位都要按这张表走）。"""
    return [coord for coord, data in grid_data.items() if _etype(data) == 'delay']


def reset_timeline(reason: str = '') -> None:
    """把时序倒回第 0 刻：刻号归零 + 每条延迟线清空，别的东西没有跨刻记忆、无需清理。

    放置 / 擦除 / 旋转 / 改刻度 / 撤销重做 / 读档 / 粘贴 / R 键都走这里。旧布局攒了
    一半的延迟线对新布局没有意义（延时装满信号再撤掉，复原后会凭空往外吐光），
    所以一律从干净的起点重算。
    """
    global tick_index, tick_note, timeline_present
    tick_index = 0
    if not timeline_present:
        tick_note = ('reset: %s' % reason) if reason else 'timeline reset'
        return                                        # 没有延时块：不必为 15 万元件白扫一遍
    for data in grid_data.values():
        if _etype(data) == 'delay':
            data['pipe'] = []
            data['out_ready'] = ()
            data['inject'] = set()
            data['is_lit'] = False
    tick_note = ('reset: %s' % reason) if reason else 'timeline reset'


def manual_reset_timeline() -> None:
    """R 键：显式复位时序（刻号归零 + 清空全部延迟线），想从头看一遍信号走向时用。"""
    global grid_changed, minimap_dirty
    reset_timeline('manual R')
    _note('timeline reset: tick 0, all delay lines cleared')
    grid_changed = minimap_dirty = True


def step_tick() -> List[Segment]:
    """推进一刻：解一次光路（除延时块外全部当场收敛）+ 推一次延迟线 + 刻号 +1。

    全文件“时序”只有这一步，而且只有延时块真的跨了过去：其它元件在这一步里已经是
    终态，刻与刻之间唯一的差别就是各条延迟线往前挪了一格。
    """
    global tick_index, tick_note
    coords = _delay_coords()
    delay_seeds = [(row, col, d) for (row, col) in sorted(coords)
                   for d in (grid_data[(row, col)].get('out_ready') or ())]
    segments, _, aborted = solve_tick(delay_seeds)
    if aborted:                                       # 被预算截断的这一刻不算数：不推线、刻号不动
        tick_note = 'aborted'
        return segments
    _advance_delay_lines(coords)
    tick_note = ''
    tick_index += 1
    return segments


# ── 07. 渲染 ──────────────────────────────────────────────────────
_HOVER_CACHE: Dict[int, pygame.Surface] = {}

def _hover_surface(cell_size: int) -> pygame.Surface:
    """按格子尺寸取（或新建）半透明高亮层，尺寸不变时复用缓存。"""
    surf = _HOVER_CACHE.get(cell_size)
    if surf is None:
        surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
        surf.fill(COLOR_HOVER)
        _HOVER_CACHE[cell_size] = surf
    return surf

def _draw_element(data: dict, screen_x: int, screen_y: int, cell_size: int) -> None:
    """贴本体 icon（按 is_lit 取 on/off 套色，方块单态）；手动关着的光源再叠斜十字标记。

    is_lit 已由 _baseline_reset / solve_tick 保证等于本刻真实生效态，所以这里不需要
    任何“被光打灭但 is_on 仍为真”的特判——渲染层替状态模型打补丁正是 #2 的成因。
    手动关（is_on=False）叠斜十字，被光打灭只变暗灰，两种“不亮”仍可区分。
    """
    element_type = _etype(data)
    name = ('block' if element_type == 'block'
            else '%s_%s' % (element_type, 'on' if data.get('is_lit', False) else 'off'))
    blit_icon(name, data['dir'], screen_x, screen_y, cell_size)
    if element_type in SWITCHABLE_TYPES and not data.get('is_on', True):
        blit_icon('off_mark', 0, screen_x, screen_y, cell_size)   # 手动关才叠标记；被光打灭只变暗灰

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

    if hover_row is not None:                          # 高亮先垫底，再压元件图
        screen.blit(_hover_surface(cell_size),
                    (int(round((hover_col * BASE_CELL_SIZE - camera_x) * zoom)),
                     int(round((hover_row * BASE_CELL_SIZE - camera_y) * zoom))))

    scan = len(grid_data) > (end_row - start_row) * (end_col - start_col)
    for row, col, data in _cells_in_range(start_row, end_row, start_col, end_col, scan):
        _draw_element(data, int(round((col * BASE_CELL_SIZE - camera_x) * zoom)),
                      int(round((row * BASE_CELL_SIZE - camera_y) * zoom)), cell_size)

def _draw_rays(ray_segments: List[Segment]) -> None:
    """世界坐标 -> 屏幕坐标画光路；线宽随 zoom 走，放大后不糊成一片。"""
    if not ray_segments:
        return
    line_width = max(2, int(BASE_CELL_SIZE * 0.1 * zoom))
    for (x1, y1), (x2, y2) in ray_segments:
        pygame.draw.line(screen, COLOR_ON,
                         (int(round((x1 - camera_x) * zoom)), int(round((y1 - camera_y) * zoom))),
                         (int(round((x2 - camera_x) * zoom)), int(round((y2 - camera_y) * zoom))),
                         line_width)

def draw_scene(ray_segments: List[Segment]) -> None:
    """渲染一帧：背景 -> 网格与元件 -> 光路 -> HUD -> 缩略图（压在 HUD 之上，始终可见）。"""
    screen.fill(COLOR_BG)
    mouse_pos = pygame.mouse.get_pos()
    # 光标压在缩略图上时不取格高亮，避免“看着亮一格、点的却是地图”；None 当哨兵（-1 也是合法格）
    hover_row, hover_col = (None, None) if minimap_hit(mouse_pos) else screen_to_grid(*mouse_pos)
    _draw_cells_in_view(hover_row, hover_col)
    _draw_rays(ray_segments)
    draw_hud()
    draw_minimap(ray_segments)

# ── 08. 小地图（视口局部地图，恒为主画面的 0.05 倍）────────────────
# 图幅正中心始终是视口中心，它不是整张世界的缩略图，故元件能按所在格真实相对大小
# 画成小方块，光路只需 Liang-Barsky 裁到图幅内再画（只夹端点会在边框上画出假线）。
MM_SIZE, MM_MARGIN = 180, 10
MM_RELATIVE_SCALE = 0.05             # 缩略图相对主画面的倍率
MM_SCAN_CELL_LIMIT = 40000           # 逐格查表的格数上限，超过就退回遍历元件表筛范围
MM_BG = (0, 0, 0, 140)
MM_DOT_LIT = COLOR_ON
MM_DOT_IDLE = (175, 175, 175)        # 未受光的元件与方块
MM_VIEW = (255, 255, 255)            # 视口框与中心十字
MM_CROSS = 6
MM_BORDER = COLOR_GRID
MM_EDGE = (168, 132, 66)             # 世界边界线（靠近世界尽头时才出现在图上）
MM_FONT = pygame.font.SysFont('consolas,menlo,monospace', 12)

minimap_visible = True
minimap_dirty = True
_minimap_surface: Optional[pygame.Surface] = None
_minimap_key: Optional[Tuple[int, int, int]] = None
_minimap_dragging = False

def _mm_scale() -> float:
    """世界像素 -> 缩略图像素：主画面 1 倍，缩略图恒取其 0.05 倍。"""
    return MM_RELATIVE_SCALE * zoom

def _mm_rect():
    """缩略图屏幕矩形，贴窗口右上角并跟随窗口尺寸。"""
    width, height = screen.get_size()
    return pygame.Rect(width - MM_SIZE - MM_MARGIN, MM_MARGIN, MM_SIZE, MM_SIZE)

def _mm_center():
    """当前视口中心的世界坐标，同时也是图幅正中心。"""
    return (camera_x + (WINDOW_WIDTH / zoom) / 2.0, camera_y + (WINDOW_HEIGHT / zoom) / 2.0)

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
    """用 Liang-Barsky 把一段光路裁到图幅 [0, MM_SIZE] 内，完全在图外返回 None。只把两端点夹进图幅会在边框上画出假线，裁剪后才与主画面一致。"""
    x1, y1 = _mm_to_map(*p1)
    x2, y2 = _mm_to_map(*p2)
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1), (dx, MM_SIZE - x1), (-dy, y1), (dy, MM_SIZE - y1)):
        if p == 0:
            if q < 0:
                return None                          # 与该边平行且在图外，整段弃掉
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
    """
        重画缩略图并写进缓存：底色 -> 世界边界 -> 光路 -> 元件点 -> 边框。只画视口附近局部（图幅中心即视口中心），元件按所在格在图上的实际大小画成小方块，光路先裁进图幅再画。
    """
    global _minimap_surface, minimap_dirty, _minimap_key
    scale = _mm_scale()
    center_x, center_y = _mm_center()
    half = (MM_SIZE / 2.0) / scale                    # 图幅半边长对应的世界像素范围
    surf = pygame.Surface((MM_SIZE, MM_SIZE), pygame.SRCALPHA)
    surf.fill(MM_BG)
    for world_x in (WORLD_MIN_PX, WORLD_MAX_PX):      # 世界边界：平时在图外看不见
        map_x, _ = _mm_to_map(world_x, center_y)
        if -1 <= map_x <= MM_SIZE:
            pygame.draw.line(surf, MM_EDGE, (int(map_x), 0), (int(map_x), MM_SIZE - 1), 1)
    for world_y in (WORLD_MIN_PY, WORLD_MAX_PY):
        _, map_y = _mm_to_map(center_x, world_y)
        if -1 <= map_y <= MM_SIZE:
            pygame.draw.line(surf, MM_EDGE, (0, int(map_y)), (MM_SIZE - 1, int(map_y)), 1)
    ray_width = max(1, int(round(BASE_CELL_SIZE * 0.1 * zoom * MM_RELATIVE_SCALE)))
    for (x1, y1), (x2, y2) in ray_segments:
        clipped = _mm_clip_segment((x1, y1), (x2, y2))
        if clipped:
            (mx1, my1), (mx2, my2) = clipped
            pygame.draw.line(surf, MM_DOT_LIT, (int(mx1), int(my1)), (int(mx2), int(my2)),
                             ray_width)
    # 元件点：先框定图幅覆盖到的行列范围，再按“范围大小 vs 元件数”择优取源
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
        pygame.draw.rect(surf, MM_DOT_LIT if working else MM_DOT_IDLE,
                         (map_x - dot // 2, map_y - dot // 2, dot, dot))
    pygame.draw.rect(surf, MM_BORDER, surf.get_rect(), 1)
    _minimap_surface = surf
    minimap_dirty = False
    _minimap_key = _mm_key()

def _text(font, text, cache, limit, bg_pad=None):
    """按文本缓存 render 结果（可选配一张半透明底）：HUD 与小地图读数文案绝大多数帧不变，60 FPS 下不必每帧重建 Surface。"""
    pair = cache.get(text)
    if pair is None:
        surf = font.render(text, True, COLOR_HUD_TEXT)
        if bg_pad is None:
            value = surf
        else:
            bg = pygame.Surface((surf.get_width() + bg_pad[0], surf.get_height() + bg_pad[1]),
                                pygame.SRCALPHA)
            bg.fill(COLOR_HUD_BG)
            value = (surf, bg)
        if len(cache) >= limit:
            cache.clear()                             # 文案基本是固定几条，超量整表重来
        cache[text] = value
        return value
    return pair

_MM_LABEL_CACHE: Dict[str, pygame.Surface] = {}
_MM_INFO_CACHE: Dict[str, Tuple[pygame.Surface, pygame.Surface]] = {}
_HUD_SURFACE_CACHE: Dict[str, Tuple[pygame.Surface, pygame.Surface]] = {}

def draw_minimap(ray_segments) -> None:
    """渲染缩略图：需要时先重建缓存 -> blit 到右上角 -> 叠视口框、中心十字与读数。"""
    if not minimap_visible:
        return
    surf = _minimap_surface
    if minimap_dirty or surf is None or _minimap_key != _mm_key():
        build_minimap(ray_segments)
        surf = _minimap_surface
    if surf is None:                                  # 刚建缓存就失败（例如显存异常）：本帧跳过
        return
    rect = _mm_rect()
    screen.blit(surf, rect.topleft)
    scale = _mm_scale()
    view_w = max(2, min(MM_SIZE - 2, int((WINDOW_WIDTH / zoom) * scale)))
    view_h = max(2, min(MM_SIZE - 2, int((WINDOW_HEIGHT / zoom) * scale)))
    center_x, center_y = rect.center
    pygame.draw.rect(screen, MM_VIEW,
                     pygame.Rect(center_x - view_w // 2, center_y - view_h // 2, view_w, view_h), 1)
    pygame.draw.line(screen, MM_VIEW, (center_x - MM_CROSS, center_y),
                     (center_x + MM_CROSS, center_y), 1)
    pygame.draw.line(screen, MM_VIEW, (center_x, center_y - MM_CROSS),
                     (center_x, center_y + MM_CROSS), 1)
    label = _text(MM_FONT, 'MAP x%.2f' % MM_RELATIVE_SCALE, _MM_LABEL_CACHE, 32)
    screen.blit(label, (rect.x + 3, rect.bottom - label.get_height() - 2))
    view_row, view_col = screen_to_grid(WINDOW_WIDTH / 2.0, WINDOW_HEIGHT / 2.0)
    # 读数底必须用 MM_FONT 量出来：借 HUD 那对缓存会按 16 号字算尺寸，压出黑斑
    info, info_bg = _text(MM_FONT, 'view %d,%d  zoom %.1fx' % (view_row, view_col, zoom),
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

def toggle_minimap() -> None:
    """M 键：切换显隐；重新显示时置脏，保证画面上是最新的光路。"""
    global minimap_visible, minimap_dirty
    minimap_visible = not minimap_visible
    minimap_dirty = True

# ── 09. HUD（ASCII 文本，规避中文字体缺失导致的渲染异常）───────────
HUD_FONT = pygame.font.SysFont('consolas,menlo,monospace', 16)
HUD_KEY_HINTS = 'R reset timeline | Z undo | X redo'
# ↑ 键位行固定展示：只剩复位与撤重做；模式切换 / 单步 / 调速按键都随模式精简一起取消
HUD_LINES = [
    'tool: ' + TOOL_NAMES[1],
    ' | '.join(TOOL_NAMES),                                  # 1 工具条
    'RMB place | LMB delete | MMB drag | wheel zoom',
    'Q / E rotate element | F toggles light, F on store resets its output',
    'M minimap on/off (local map = 0.05x view) | LMB on MAP jumps the view',
    'Z undo | X redo | F1/F2/F3 save | F4 load | Enter+F4 paste at cursor',
    HUD_KEY_HINTS,
    'tick 0  delay preset 3 ticks',
    'slots: - | undo 0 redo 0',
    'trace: -',
]
hud_y = 8


def draw_hud():
    """左上角操作提示层：纯展示，不参与取格。

    时序只占一行（第 7 行）：当前刻号 + 延时预设 + 复位提示；模式、刻间隔、导通门数、
    熄灭灯数这些以前各占一行的东西全部删掉，光路收尾状态仍由末行 trace 显示。
    """
    HUD_LINES[0] = 'tool: ' + TOOL_NAMES[current_tool]
    # 索引与静态模板逐行对齐：7 时序、8 槽位与栈深、9 提示与光路收尾
    HUD_LINES[7] = ('tick %d  delay preset %d ticks  ready %d%s' % (
        tick_index, delay_setting, delay_ready, ('  [%s]' % tick_note) if tick_note else ''))
    HUD_LINES[8] = ('slots: %s | %s | undo %d redo %d' % (
        '  '.join(save_status.get(s, '%d:-' % s) for s in SAVE_SLOTS),
        'unsaved *' if world_dirty else 'saved',
        len(undo_stack), len(redo_stack)))
    note = _message if (_message and time.perf_counter() <= _message_until) else ''
    HUD_LINES[9] = ('%s | trace %s' % (note, trace_note)) if note else ('trace ' + trace_note)
    y = hud_y
    for text_line in HUD_LINES:
        surf, bg = _text(HUD_FONT, text_line, _HUD_SURFACE_CACHE, 256, (10, 3))
        screen.blit(bg, (6, y - 2))                   # 文字下垫半透明底，深背景上也看得清
        screen.blit(surf, (11, y))
        y += surf.get_height() + 5


# ── 10. 输入处理 ──────────────────────────────────────────────────
TOOL_KEY_MAP = {pygame.K_0 + i: i for i in range(len(TOOL_TYPES))}   # 数字键 0-7 对应工具下标
is_dragging = False
last_mouse_pos = (0, 0)

def place_element() -> None:
    """右键放置当前工具的元件；改之前先把这一格的改前状态压栈（同格覆盖也记一步）。"""
    global grid_changed, world_dirty
    coord = _cursor_coord()
    if not _in_world_bounds(*coord):
        return
    push_undo([coord])
    grid_data[coord] = TOOL_SPECS[TOOL_TYPES[current_tool]]()
    reset_timeline('place')
    grid_changed = world_dirty = True

def erase_element() -> None:
    """左键擦除；格上本来没东西就不压 delta，免得空操作占掉撤销步数。"""
    global grid_changed, world_dirty
    coord = _cursor_coord()
    if coord not in grid_data:
        return
    push_undo([coord])
    grid_data.pop(coord)
    reset_timeline('erase')
    grid_changed = world_dirty = True

def _cursor_coord() -> Coord:
    """光标所在格（撤销 delta 要按格登记，故坐标与数据各取一个助手）。"""
    return screen_to_grid(*pygame.mouse.get_pos())

def _cursor_element() -> Optional[dict]:
    """取光标所在格的元件数据，空格返回 None（旋转与 F 开关共用）。"""
    return grid_data.get(_cursor_coord())


def rotate_element(step: int) -> None:
    """Q(step=-1) / E(step+1)：普通元件转朝向；延时块四向对称转了也没用，改成调它的延时刻度。

    光标压在空格上且当前工具是延时块时，调的是放置预设 delay_setting，
    于是可以先调好刻度再连着摆一排同刻度的延时块。
    """
    global grid_changed, world_dirty, delay_setting
    data = _cursor_element()
    if data is None:
        if TOOL_TYPES[current_tool] != 'delay':
            return
        new_setting = max(DELAY_MIN_TICKS, min(delay_setting + step, DELAY_MAX_TICKS))
        if new_setting == delay_setting:
            return
        delay_setting = new_setting
        _note('delay preset now %d ticks' % delay_setting)
        return
    if _etype(data) == 'delay':
        new_ticks = _delay_ticks(data)
        new_ticks = max(DELAY_MIN_TICKS, min(new_ticks + step, DELAY_MAX_TICKS))
        if new_ticks == _delay_ticks(data):
            return
        push_undo([_cursor_coord()])
        data['delay'] = new_ticks
        data['pipe'] = []                            # 改刻度等于重新拉一次延迟线
        data['out_ready'] = ()
        _note('delay now %d ticks' % new_ticks)
    else:
        push_undo([_cursor_coord()])
        data['dir'] = (data['dir'] + step) % 4
        if _etype(data) == 'store':
            data['in_levels'] = None
    reset_timeline('rotate')
    grid_changed = world_dirty = True

def toggle_switch() -> None:
    """F 键：光源切手动开关；存储石复位输出为 0；延时块清空手上那条延迟线（吐光卡住时手动排空）。

    镜与半透由光驱动，不处理。
    """
    global grid_changed, world_dirty
    data = _cursor_element()
    if data is None:
        return
    element_type = _etype(data)
    if element_type not in SWITCHABLE_TYPES and element_type not in ('store', 'delay'):
        return
    push_undo([_cursor_coord()])
    if element_type in SWITCHABLE_TYPES:
        data['is_on'] = not data.get('is_on', True)
    elif element_type == 'store':
        data['state'] = 0
        data['in_levels'] = None
    else:
        data['pipe'] = []
        data['out_ready'] = ()
        data['inject'] = set()
        _note('delay line flushed')
    reset_timeline('toggle')
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

PAN_KEYS = ((pygame.K_LEFT, pygame.K_a, 'x', -1), (pygame.K_RIGHT, pygame.K_d, 'x', 1),
            (pygame.K_UP, pygame.K_w, 'y', -1), (pygame.K_DOWN, pygame.K_s, 'y', 1))

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

_f4_armed = False
_f4_armed_at = 0.0
F4_COMMIT_S = 0.12           # F4 延时提交窗口：窗口内等到 Enter 就算粘贴，等不到才算读档


def commit_pending_f4() -> None:
    """主循环里调用：F4 按下后过了提交窗口仍没有 Enter 跟随，才执行普通读档。

    先按 Enter 还是先按 F4 都判成粘贴 —— 先 Enter 时靠 F4 落下瞬间 get_pressed 里 Enter 仍按住，
    先 F4 时靠这口延时闸把读档压住；否则两种按法会打架，出现"先整盘读档、又再粘贴"的双触发。
    """
    global _f4_armed
    if _f4_armed and time.perf_counter() - _f4_armed_at > F4_COMMIT_S:
        _f4_armed = False
        load_recent_slot()


def handle_event(event):
    """处理一个事件并派发到对应动作；返回 False 表示要退出主循环。"""
    global current_tool, WINDOW_WIDTH, WINDOW_HEIGHT, _minimap_dragging, is_dragging
    global last_mouse_pos, _f4_armed, _f4_armed_at
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.VIDEORESIZE:              # 尺寸变化：只更新宽高并重夹相机
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
        clamp_camera()
    elif event.type == pygame.MOUSEBUTTONDOWN:
        if minimap_hit(event.pos):                    # 图内点击一律当导航，不穿透到放置/擦除
            if event.button == 1:
                _minimap_dragging = True
                focus_camera_on_map(*event.pos)
            return True
        if event.button == 2:
            is_dragging = True                        # 中键：开始拖拽平移
            last_mouse_pos = pygame.mouse.get_pos()
        elif event.button == 3:
            place_element()                           # 右键放置
        elif event.button == 1:
            erase_element()                           # 左键擦除
    elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 2:
            is_dragging = False                       # 中键平移只认自己的抬起
        _minimap_dragging = False                     # 缩略图导航任何抬起都复位
    elif event.type == pygame.MOUSEMOTION:
        buttons = event.buttons                       # 按键当前状态，据此能在窗口外松手时退出
        if _minimap_dragging:
            if buttons[0]:
                focus_camera_on_map(*event.pos)       # 缩略图拖拽优先于画面拖拽
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
        elif event.key == pygame.K_f:
            toggle_switch()
        elif event.key == pygame.K_r:
            manual_reset_timeline()                 # 显式复位时序：刻号归零 + 清空全部延迟线
        elif event.key == pygame.K_m:
            toggle_minimap()
        elif event.key == pygame.K_q:
            rotate_element(-1)
        elif event.key == pygame.K_e:
            rotate_element(1)
        elif event.key == pygame.K_z:
            undo()
        elif event.key == pygame.K_x:
            redo()
        elif event.key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
            save_slot(event.key - pygame.K_F1 + 1)    # 存槽不分流：按 Enter 也照常存，绝不误触粘贴
        elif event.key == pygame.K_F4:
            if pygame.key.get_pressed()[pygame.K_RETURN]:
                _f4_armed = False
                paste_slot_at_cursor()                # 先 Enter 后 F4 -> 粘贴
            else:
                _f4_armed, _f4_armed_at = True, time.perf_counter()   # 先 F4 -> 开延时闸等 Enter
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if _f4_armed or pygame.key.get_pressed()[pygame.K_F4]:
                _f4_armed = False
                paste_slot_at_cursor()                # 先 F4 后 Enter -> 粘贴
    return True


# ── 11. 存档、读档与撤销重做 ──────────────────────────────────────
# 字段分工：只落用户字段（坐标 / type / dir / 光源 is_on / 存储石 state 与 in_levels /
# 相机与工具）；is_lit、axis_inputs、perp_inputs、input_dirs 都是派生态，读档后置脏由
# solve_tick 重建，存进去只会带来脏数据。写盘一律先写 .tmp 再 os.replace 原子换名。
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')
SAVE_VERSION = 1
SAVE_SLOTS = (1, 2, 3)
MAX_CELLS_LIMIT = 200000                     # 单份存档的元件数上限，防坏档撑爆内存
UNDO_LIMIT = 200                           # delta 只记改动格，栈深放开到 200 也不吃内存
MESSAGE_TTL_S = 4.0                          # 一次性提示在 HUD 上停多久

PERSIST_FIELDS = {
    'block': ('dir',), 'light': ('dir', 'is_on'), 'mirror': ('dir',), 'splitter': ('dir',),
    'collector': ('dir',), 'crystal': ('dir',), 'store': ('dir', 'state', 'in_levels'),
    # 延时块只落刻度：pipe / out_ready / inject 是时序态，等同于派生态——
    # 存进去会让一份静止的存档读回来自己往外吐光，一律由 reset_timeline 从零刻重建。
    'delay': ('dir', 'delay'),
}

# 撤销栈：一步 = 若干条 (格子, 改前数据)；改前数据为 None 表示那格原本空着。
# 早先是每步 copy.deepcopy(整个 grid_data)，50 步栈在 15 万元件下按数百 MB 到 GB 计，
# 而且每点一次右键都要全图深拷一遍（点下去能感到卡）。改成只记“这次动了哪几格”之后，
# 单步成本从 O(全图) 降到 O(改动格数)，栈深反而从 50 放开到 200。
undo_stack: List[List[Tuple[Coord, Optional[dict]]]] = []
redo_stack: List[List[Tuple[Coord, Optional[dict]]]] = []
world_dirty = False
last_slot = 0                                # 最近一次存 / 读的槽位，F4 默认读它
_last_slot_by_mtime = 0                      # 三份存档里最新的一份，F4 兜底用
save_status: Dict[int, str] = {}
_message = ''
_message_until = 0.0

def _note(msg: str) -> None:
    """写一条 HUD 一次性提示并给出失效时刻；过期由 draw_hud 负责让它消失。"""
    global _message, _message_until
    _message = msg
    _message_until = time.perf_counter() + MESSAGE_TTL_S

def _slot_path(slot: int) -> str:
    return os.path.join(SAVE_DIR, 'slot%d.json' % slot)

def _encode_levels(value):
    """in_levels 三态编码：None -> -1；frozenset -> 方向列表（空集就是空列表）。"""
    return -1 if value is None else sorted(int(d) for d in value)

def _decode_levels(value) -> Optional[frozenset]:
    """
        _encode_levels 的逆运算：-1 与 null 都还原成 None（未定义基准）。null 若被当成空集，语义就变成“基准=没有输入边为 1”：读档当轮只要有一条输入边受光就会被算成上升沿，存储石凭空翻转一次。
    """
    if value is None or value == -1:
        return None
    try:
        return frozenset(int(d) for d in value)
    except (TypeError, ValueError):
        return None

def serialize_world(with_camera: bool = True) -> dict:
    """grid_data -> 可 JSON 化的 dict：坐标写成 "row,col" 字符串，只带 PERSIST_FIELDS 的字段。"""
    cells = {}
    for (row, col), data in grid_data.items():
        etype = _etype(data)
        fields = PERSIST_FIELDS.get(etype)
        if fields is None:                              # 未知类型不写，避免污染存档
            continue
        item = {'type': etype}
        for f in fields:
            item[f] = _encode_levels(data[f]) if f == 'in_levels' else data.get(f)
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
    if etype == 'light' and data.get('is_on') is None:
        data['is_on'] = True                            # null 的开关按“开”处理，别读成关
    try:
        data['dir'] = int(data['dir']) % 4
    except (TypeError, ValueError):
        data['dir'] = 0
    if etype == 'store':
        data['state'] = int(data.get('state') or 0) % 2
    if etype == 'delay':
        data['delay'] = _delay_ticks(data)              # 乱值 / 越界一律夹回合法区间
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
                raise ValueError('cells 不是对象')       # 半截档 / 手写档
            count = sum(1 for v in raw.values()
                        if isinstance(v, dict) and v.get('type') in TOOL_SPECS)
            save_status[slot] = '%d:%dc' % (slot, count)
            if mtime >= newest_mtime:
                newest_mtime, newest_slot = mtime, slot
        except (ValueError, OSError, TypeError, AttributeError):
            save_status[slot] = '%d:BAD' % slot
    _last_slot_by_mtime = newest_slot

def save_slot(slot: int) -> bool:
    """存到指定槽位：先写 slotN.json.tmp 再 os.replace，中途崩溃只会留下 .tmp，不会把上一份能用的存档写成半截 JSON。"""
    global world_dirty, last_slot
    if slot not in SAVE_SLOTS:
        return False
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        path = _slot_path(slot)
        with open(path + '.tmp', 'w', encoding='utf-8') as fh:
            json.dump(serialize_world(), fh, ensure_ascii=False, indent=1)
        os.replace(path + '.tmp', path)
    except OSError as exc:
        _note('save slot %d FAILED: %s' % (slot, exc))
        return False
    world_dirty = False
    last_slot = slot
    _note('saved slot %d  (%d cells)' % (slot, len(grid_data)))
    _refresh_slot_status()
    return True

def _read_slot(slot: int) -> Tuple[Dict[Coord, dict], dict]:
    """读一份存档并消毒成干净的 cells；缺文件 / 半截 JSON / 乱码统一抛异常，由调用方兜住。

    读档（整盘替换）与粘贴（平移到光标格）共用这一套解析口径，两条路不会各自漂移。
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
        _note('slot %d BROKEN: %s' % (slot, exc))
        return False
    push_undo_replaced(grid_data, cells)                # 读档本身也记一步，可 Z 撤回去
    grid_data = cells
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
    timeline_present = any(_etype(d) == 'delay' for d in cells.values())
    reset_timeline('load slot %d' % slot)
    _note('loaded slot %d  (%d cells)' % (slot, len(grid_data)))
    _refresh_slot_status()
    grid_changed = minimap_dirty = True                 # 下一帧全部重算
    return True


def load_recent_slot() -> bool:
    """F4 读取：整盘替换为存档内容（相机与工具也跟着还原）。"""
    slot = _f4_target_slot()
    if not slot:
        _note('no save yet  (F1 / F2 / F3 to save)')
        return False
    return load_slot(slot)


def paste_slot_at_cursor(slot: int = 0) -> bool:
    """Enter+F4 粘贴：把存档当成一块图章盖在当前光标格上，整块平移、相对位置保持不变。

    对齐口径：取存档里 row 与 col 的最小值当作这块内容的左上角，平移量 = 光标格 - 这个角，
    于是存档的左上角正好落在光标格上，其余元件按同一个偏移量跟着平移。
    只搬元件：存档里的相机 / 工具 / 小地图显隐一概不动，那是那份存档自己的视角。
    越界格剔除；与已有元件同格时覆盖，和右键放置的口径一致。
    整次粘贴只压一步快照，一次 Z 就能把这一整块撤掉。
    """
    global grid_changed, minimap_dirty, world_dirty, last_slot
    target = slot if slot in SAVE_SLOTS else _f4_target_slot()
    if not target:
        _note('no save to paste  (F1 / F2 / F3 to save)')
        return False
    try:
        cells, _doc = _read_slot(target)
    except (ValueError, OSError, TypeError, AttributeError, FileNotFoundError) as exc:
        _note('paste slot %d BROKEN: %s' % (target, exc))
        return False
    if not cells:
        _note('paste slot %d has no cell' % target)
        return False
    anchor_row, anchor_col = screen_to_grid(*pygame.mouse.get_pos())
    delta_row = anchor_row - min(row for row, _col in cells)      # 存档左上角 -> 光标格
    delta_col = anchor_col - min(col for _row, col in cells)
    moved, dropped = [], 0
    for (row, col), data in cells.items():
        coord = (row + delta_row, col + delta_col)
        if _in_world_bounds(*coord):
            moved.append((coord, data))
        else:
            dropped += 1                                # 贴到世界边界外的格子直接丢弃
    if not moved:                                       # 一整块全在世界外：不占撤销步数
        _note('paste slot %d -> r%d,c%d  all %d cells out of world' % (
            target, anchor_row, anchor_col, dropped))
        return False
    push_undo([coord for coord, _data in moved])       # 整块粘贴只登记涉及到的那些格
    pasted = covered = 0
    for coord, data in moved:
        if coord in grid_data:
            covered += 1
        grid_data[coord] = data
        pasted += 1
    reset_timeline('paste')
    world_dirty = True
    last_slot = target
    _note('pasted slot %d -> r%d,c%d  +%d cells (%d over, %d out)' % (
        target, anchor_row, anchor_col, pasted, covered, dropped))
    _refresh_slot_status()
    grid_changed = minimap_dirty = True
    return True


def _snapshot_cells(coords: List[Coord]) -> List[Tuple[Coord, Optional[dict]]]:
    """按格取改前状态。单格小 dict 的深拷贝成本可忽略，却保证了栈里的值不会被后续原地改动串改。"""
    return [(coord, copy.deepcopy(grid_data.get(coord))) for coord in sorted(set(coords))]

def push_undo(coords: List[Coord]) -> None:
    """改动前调用：只登记“即将被动的那几格”的改前状态，并清空重做栈。"""
    if not coords:
        return
    undo_stack.append(_snapshot_cells(coords))
    del undo_stack[:-UNDO_LIMIT]                        # 超栈深上限就丢最老的一步
    del redo_stack[:]                                   # 新改动落地，重做链作废

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
    """应用一步 delta，并顺手交回“对面那口栈要的东西”（应用前的当前状态）。"""
    reverse: List[Tuple[Coord, Optional[dict]]] = []
    for coord, before in entries:
        reverse.append((coord, copy.deepcopy(grid_data.get(coord))))
        if before is None:
            grid_data.pop(coord, None)                  # 那一步原本是放上来 -> 撤回即删掉
        else:
            grid_data[coord] = before                   # delta 马上被 pop，对象没人再引用
    return reverse

def _restore(stack: List[List[Tuple[Coord, Optional[dict]]]],
             other: List[List[Tuple[Coord, Optional[dict]]]], label: str) -> bool:
    """撤销 / 重做的公共部分：按格回滚、时序归零、把反向 delta 塞进对面那口栈（相机不动，免得视角乱跳）。"""
    global grid_data, world_dirty, grid_changed, minimap_dirty
    if not stack:
        _note('nothing to %s' % label)
        return False
    entries = stack.pop()
    other.append(_apply_delta(entries))
    del other[:-UNDO_LIMIT]
    reset_timeline(label)
    world_dirty = True
    _note('%s  %d cells (%d cells now)' % (label, len(entries), len(grid_data)))
    grid_changed = minimap_dirty = True
    return True

def undo() -> bool:
    """Z 键：弹出撤销栈顶恢复到上一步，当前状态顺手压进重做栈。"""
    return _restore(undo_stack, redo_stack, 'undo')

def redo() -> bool:
    """X 键：把刚撤销掉的那一步放回去，同时重新压进撤销栈。"""
    return _restore(redo_stack, undo_stack, 'redo')

_refresh_slot_status()                                  # 启动即扫档，HUD 一开就有槽位状态

# ── 12. 主循环 ────────────────────────────────────────────────────
def main():
    """收事件 -> 提交延时中的 F4 -> 键盘平移 -> 按固定节奏推进时序 -> 渲染并翻页，固定 60 FPS。

    时序只有一条路径：每 TICK_INTERVAL_S 秒走一刻（解一次光路 + 推一次延迟线），
    没有模式分支、没有单步等待。刚编辑完（grid_changed）时把计时拨到点，下一帧立刻
    补走一刻，保证右键放下去画面马上有反应，而刻与刻之间的间隔仍然是固定值。
    """
    global grid_changed, cached_ray_segments, minimap_dirty
    running = True
    last_tick_at = time.perf_counter()
    while running:
        dt = min(clock.tick(60) / 1000.0, MAX_FRAME_DT_S)   # 后台切回来的巨型 dt 要夹住
        for event in pygame.event.get():
            if not handle_event(event):
                running = False
        commit_pending_f4()                                  # F4 单独按满 0.12s 才真读档
        pan_camera(dt)
        if grid_changed:                                     # 编辑过：下一帧就补走一刻
            grid_changed = False
            last_tick_at = 0.0
        if time.perf_counter() - last_tick_at >= TICK_INTERVAL_S:
            cached_ray_segments = step_tick()
            last_tick_at = time.perf_counter()
            minimap_dirty = True
        draw_scene(cached_ray_segments)
        pygame.display.flip()


if __name__ == '__main__':
    main()
    pygame.quit()