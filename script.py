




"""
灵光一现 · 光线光学沙盘（pygame 单文件实现）

【一句话简介】
在一块 8000 x 8000 格的网格里摆放八类光学元件，程序实时求解光路：光沿直线走、被反射镜
反射、被分束器分光、把耦合器点亮、在光与门（AND Gate）上做 AND 运算、用光锁存器记住每一位电平、
并被延迟线按“刻”延后放行。本质上是一台用光线搭出来的可编程时序电路沙盘。

【运行环境与快速开始】
    依赖：Python 3.8+ 与 pygame（pip install pygame）；无其它第三方库，不联网，无素材文件。
    运行：python 本文件名.py        # 例如 python 灵光一现_耦合器分束版.py；窗口可拖大缩小，60 FPS
    存档：脚本同级的 saves/slot1-3.json（纯 JSON，可手工编辑；见 SAVE_VERSION）

【元件一览：数字键 0-7 选工具；dir 一律指“输出边 / 凸起所指边”，0=上 1=右 2=下 3=左，顺时针】
    0 wall      墙 Wall：吸收光线，无状态，用来挡光与砌墙。
    1 laser     激光器 Laser：沿 dir 发一束光；带手动开关（F），被别的光击中即熄灭。
    2 mirror    反射镜 Mirror：受光即开，按镜面朝向反射（dir 偶数画“/”，奇数画反斜）。
    3 splitter  分束器 Splitter：本束直行透射，同时派生一束反射光，受光即开——
                唯一“分光后主光仍直行”的器件（耦合器反向分束没有直行分量）。
    4 coupler 耦合器 Coupler：双向 1<->N 端口，正向汇聚 + 反向 T 型分束二合一——
                正向：1~3 条非逆向输入边有光即从输出边 dir 另发一束（三入一出）；
                反向：光从输出边逆向进，则从两条相邻输入边各发一束，正对边被吞（T 型分束）。
                同刻内正向 / 反向二选一（靠 is_lit 锁定），入射光一律停在本格。
    5 and_gate   光与门 AND Gate：信号光沿透光轴穿过，控制光垂直入射只当开关，
                两路在同一刻都到过才导通。
    6 latch     光锁存器 Latch：1 出 3 入；任一输入边出现新的 0->1 就翻转输出（记忆位），
                输出置 1 时自己就沿 dir 发一束光。
    7 delay_line  延迟线 Delay Line：正方形加正十字，四边都是端口；任一面进来的光一律被吸收，
                攒够 ticks 刻之后才从“进来的那一侧的对边”原方向放出
                ——全文件唯一真正跨刻的元件。

【状态约定（两套，分工明确）】
    用户态：is_on（只有激光器带手动开关）、state（光锁存器记忆位）、ticks（延迟刻度）、dir；
            只有这些会被写进存档。
    派生态：is_lit / axis_inputs / perp_inputs / input_dirs / pipe / out_ready / inject，
            一律由光路求解现算，不落盘。is_lit 恒等于“这一刻的光路算完之后它到底亮不亮”，
            渲染层只读它，因此贴图不可能再与真实状态不一致。

【时序模型：全文件只有这一套，而且只与延迟线有关】
    1. 全图只有一个“刻”，每刻固定 TICK_INTERVAL_S 秒（当前 0.1 秒）自动推进，不提供调速；
       “刻”是唯一的时序单位，换算关系只有一条：延迟刻度 n 刻 = n x TICK_INTERVAL_S 秒。
    2. 一刻 = 解一次光路（反射镜 / 分束器 / 耦合器 / 光与门 AND / 光锁存器 / 激光器熄灭全在这一刻之内
       迭代到不动点）+ 刻末统一推进一次延迟队列。除延迟线以外的元件一律零刻延迟：
       摆下去当场就是终态，光与门 AND 门同刻即亮即导通，不需要任何跨刻记忆。
    3. 跨刻的记忆只有延迟线的延迟队列 pipe 一件：第 t 刻注入、第 t+ticks 刻放出，
       ticks 只由刻数决定（1~12 刻），与光走了几格、这一刻解了几轮都无关。
    4. 其余元件一概不碰延迟：不读写 pipe / out_ready / inject，也不带跨刻状态。
       激光器被打灭、光锁存器翻转、光与门导通都只在本刻内成立，下一刻从头再解一次；
       于是“灯被对射打灭之后怎么都救不回来”这类死局在结构上就不存在了。
    5. 只有编辑动作会复位时序（刻号归零 + 清空全部延迟队列）。

【操作】
    右键放置 | 左键/Del擦除光标格 | 中键拖拽平移 | 滚轮以光标为锚缩放（0.4x~5.0x）| WASD / 方向键平移
    右键或 Enter 放置当前工具；Enter 长按连续铺、Del 长按连续擦，整段长按只记一步撤销（一次 Z 撤掉整条笔画）
        —— 鼠标左右键可用文件内常量 INVERT_MOUSE 一键互换（默认右放左擦，学习 Minecraft：左键拆除、右键放置）
    F12 切换性能面板：FPS / 每刻求解耗时(ms) / 元件数 / 撤销栈深
    0-7 选元件；Q / E 逆时针 / 顺时针旋转光标格元件
        —— 压在延迟线上 = 调它的延迟刻度（1~12 刻）；
        —— 当前工具是延迟线且光标压在空格上 = 调放置预设刻度，可连着摆一排同刻度块。
    F 激光器切手动开关 / 光锁存器复位输出 / 延迟线排空延迟队列
    M 小地图显隐；小地图内左键点击或拖拽直接跳转视口
    F1 / F2 / F3 存三个槽位（原子写盘）| F4 读最近一份
    V 粘贴图章：取存档 row/col 最小角对齐光标格整块平移并入当前世界（一步 Z 撤掉整块）
    Z 撤销 | X 重做（放置 / 擦除 / 旋转 / F 开关 / 粘贴 / 读档均可撤；delta 快照，栈深 200）

【HUD（左上角，纯 ASCII，规避中文字体缺失导致的渲染异常）】
    共 10 行：当前工具、工具条、鼠标操作、旋转与 F 键、小地图说明、存读与撤重、键位提示、
    时序行（tick N + 延迟预设 + 正在放行的延迟线数 + 复位提示）、槽位与撤销栈深、
    末行光路收尾状态（ok rN / TRUNC / MAXR）。

【光路求解与四道防卡死闸门】
    外层反复“重算一轮”直到无变化（上限 MAX_LIGHT_ROUNDS = 80 轮）；每轮做五件事：
    清动态态 -> 消化射线队列（点亮反射镜 / 分束器、记下被打灭的灯与受光的光锁存器输入边）
    -> 光与门 AND -> 光锁存器上升沿 -> 激光器熄灭锁定。
    四道硬预算：单轮射线数 2 万、总步数 100 万、光段数 5 万、墙钟 0.30 秒，任一触发就地
    截断（已画光路保留，绝不补画猜测几何），HUD 末行报 TRUNC；跑满 80 轮仍不收敛报 MAXR。
    去重键 ctx.seen 记“从哪格、朝哪个方向进入目标格”：同一轮里重复该状态必是重复几何且
    零新增记账，掐掉它既能防镜面回路死循环，又保证不丢任何有效光路。

【代码结构（章节号与文件内的分隔注释一一对应）】
    01 窗口与调色板           02 世界与相机           03 世界状态与时间步
    04 渲染资源（icon 预渲染 + 缩放缓存）            05 方向与坐标工具
    06 光路追踪与延迟线（核心：solve_tick / step_tick / _advance_delay_lines）
    07 渲染                   08 小地图（视口局部图，恒为主画面 0.05 倍）
    09 HUD                    10 输入处理             11 存读撤重（原子写盘 + delta 撤销）
    12 主循环
    全文件“时序”只有一个入口 step_tick()：解一次光路 + 推一次延迟队列 + 刻号加一；
    主循环按 TICK_INTERVAL_S 的固定节奏调它，没有模式分支、没有单步等待。

【名词对照（读代码前先对齐口径）】
    刻 tick            唯一的时序单位，长度固定为 TICK_INTERVAL_S 秒。
    注入 inject        本刻有光从某条边打进延迟线，只在求解上下文里记账。
    延迟队列 pipe        每个延迟线一条队列，每刻推进一格，长度上限就是它的刻数 ticks。
    放行 out_ready     刻末从延迟队列队头弹出的方向，下一刻作为种子射线补进光路。
    基线 _baseline_reset  把全图清回“这一刻开始时它应处的态”，口径全文件唯一。
    不动点 converged   一轮下来光与门导通集、光锁存器翻转、熄灭灯集都不再变化。
"""
import copy
import json
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Iterator, List, Optional, Set, Tuple

import pygame

pygame.init()

# ══════════════════════════════════════════════════════════════════
# 【全局参数 CONFIG】—— 全文件所有可调常量集中在这里，改参只看这一段。
# 依赖关系已按顺序排好：先基础量（颜色 / 窗口 / 世界尺寸），派生量紧随其后。
# 想要不同的手感 / 配色 / 节奏，只动本段即可，下面各节一律只读不改。
# ══════════════════════════════════════════════════════════════════

# ── 调色板（COLOR_ON 同时是“元件开态”与“光路本身”的颜色）──
COLOR_ON = (100, 149, 237)        # 主题色·开态 / 光路 / 选中 / 悬停高亮（蓝）
COLOR_OFF = (105, 105, 105)       # 主题色·关态 / 未选中 / 小地图未受光（灰）
COLOR_BG = (30, 30, 30)           # 深色底：屏幕背景与各面板半透明底的基色
COLOR_GRID = (60, 60, 60)         # 结构线：网格 / 小地图边框 / 世界边界线
CLEAR = (0, 0, 0, 0)              # 全透明：贴图挖空专用

# ── 窗口 ──
WINDOW_WIDTH, WINDOW_HEIGHT = 1400, 750   # 初始窗口尺寸（RESIZABLE，可拖拽改变）

# ── 世界与相机 ──
BASE_CELL_SIZE = 40               # zoom=1.0 时一格的像素尺寸
WORLD_HALF_COLS = WORLD_HALF_ROWS = 4000  # 行列各 -4000~3999，原点居中
WORLD_COLS, WORLD_ROWS = WORLD_HALF_COLS * 2, WORLD_HALF_ROWS * 2
WORLD_WIDTH_PX, WORLD_HEIGHT_PX = WORLD_COLS * BASE_CELL_SIZE, WORLD_ROWS * BASE_CELL_SIZE
WORLD_MIN_PX = -WORLD_HALF_COLS * BASE_CELL_SIZE   # 世界边界的世界像素坐标
WORLD_MAX_PX = WORLD_HALF_COLS * BASE_CELL_SIZE
WORLD_MIN_PY, WORLD_MAX_PY = WORLD_MIN_PX, WORLD_MAX_PX
MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 0.4, 5.0, 0.1   # 滚轮缩放范围与步进
PAN_SPEED_PX = 500                # WASD / 方向键平移速度（世界像素/秒）
MAX_FRAME_DT_S = 0.05             # 单帧 dt 上限，防切后台回来一步甩出世界

# ── 光路求解预算（四道防卡死闸门）──
MAX_RAY_STEPS = WORLD_COLS + WORLD_ROWS   # 单束上限＝世界曼哈顿直径，合法长折线不误截
MAX_LIGHT_ROUNDS = 80            # 外层迭代上限
MAX_RAYS_PER_ROUND = 20000       # 单轮射线数上限
MAX_STEPS_PER_ROUND = 1000000    # 单轮总步数上限
MAX_TRACE_SEGMENTS = 50000       # 光段数上限
TRACE_TIME_LIMIT_S = 0.30        # 单轮墙钟上限（秒）

# ── 时序（刻 / 延迟线）──
DELAY_LINE_DEFAULT_TICKS = 3                     # 放置时写入的默认延迟刻度（单位：刻）
DELAY_LINE_MIN_TICKS, DELAY_LINE_MAX_TICKS = 1, 12   # Q/E 调刻度的合法区间
TICK_INTERVAL_S = 0.1            # 每刻固定长度（秒），不提供调速
TICK_DISPLAY_WRAP = 100          # HUD 显示的刻号到达该值后归零（仅影响显示）

# ── 图标几何（全部由 BASE_CELL_SIZE 派生）──
ICON_SIZE = BASE_CELL_SIZE
ICON_MAIN = int(ICON_SIZE * 0.7)          # 激光器主体边长
ICON_WALL = int(ICON_SIZE * 0.8)
ICON_PROTRUDE = max(3, int(ICON_SIZE * 0.2))     # 输出方向凸起边长
ICON_LINE_W = max(2, int(ICON_SIZE * 0.1))
ICON_INSET = int(ICON_SIZE * 0.2)
ICON_BAR_LEN = int(ICON_SIZE * 0.88)      # 光与门栅条
ICON_BAR_W = max(2, int(ICON_SIZE * 0.08))
ICON_BAR_GAP = int(ICON_SIZE * 0.22)      # 透光槽宽
ICON_RING_R, ICON_RING_W = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.12)
ICON_LATCH_R, ICON_LATCH_CORE = int(ICON_SIZE * 0.4), int(ICON_SIZE * 0.25)

# ── 小地图 ──
MM_SIZE, MM_MARGIN = 180, 10     # 图幅边长与到窗口边缘的留白
MM_RELATIVE_SCALE = 0.05         # 缩略图相对主画面的倍率
MM_SCAN_CELL_LIMIT = 40000       # 逐格查表的格数上限，超过退回遍历元件表筛范围
MM_CROSS = 6                     # 中心十字臂长；其余颜色复用全局色板（见 _tint）
_MM_DBLCLICK_MS = 300            # 两次左键间隔小于此毫秒数即视为“双击小地图回原点”

# ── 快捷栏 ──
HOTBAR_CELL = 60                 # 单个格子的正方形边长
HOTBAR_GAP = 6                   # 格子水平间距
HOTBAR_BOTTOM_PAD = 10           # 栏底到窗口下沿留白

# ── 鼠标键位映射 ──
# 学习 Minecraft 的习惯：左键拆除、右键放置。想换回旧的“左放右擦”，把
# INVERT_MOUSE 改成 False 即可，其余代码一行不用动。
INVERT_MOUSE = True              # True=右键放/左键擦（Minecraft 习惯，默认）；False=左放右擦
PLACE_BTN = 3 if INVERT_MOUSE else 1   # 放置对应的鼠标键（1=左键, 3=右键）
ERASE_BTN = 1 if INVERT_MOUSE else 3   # 擦除对应的鼠标键

# ── 存档与撤销 ──
SAVE_VERSION = 1                 # 存档格式版本号
SAVE_SLOTS = (1, 2, 3)           # 可用槽位（F1/F2/F3 存，F4 读最近一份）
MAX_CELLS_LIMIT = 200000         # 单份存档的元件数上限，防坏档撑爆内存
UNDO_LIMIT = 200                 # delta 只记改动格，栈深放开到 200 也不吃内存
MESSAGE_TTL_S = 4.0              # 一次性提示的存活时长（秒）

# ── 主界面 / ESC 语义 ──
_ESC_RETURN_WIN = 600            # 毫秒：游戏内窗口内连按两次 ESC 才返回主界面
_MENU_DECOR_CELL = 92            # 随机氛围元件的栅格吸附间距（px），贴格摆放不漂移
_MENU_DECOR_MAX = 12             # 同屏存活的氛围元件数量上限
_MENU_DECOR_STEP_MS = 240        # 每隔多少毫秒做一次“刷新 / 删除”决策
_MENU_DECOR_FADE_MS = 520        # 元件出现 / 消失时的淡入淡出时长（毫秒）


# ── 01. 窗口与调色板 ──────────────────────────────────────────────
# 本节是全文件唯一的“常量入口”：窗口、配色、时钟都在这几行定完，后面各节只读不改。
# 配色口径：COLOR_ON 同时是“元件处于开态”和“光路本身”的颜色——亮着的元件和打在它
# 身上的光是同一种蓝，一眼就能看出“谁在因谁而亮”；COLOR_OFF 是灰，只表示“没工作”，
# 不区分“手动关”与“被光打灭”（两者的区别交给斜十字标记，见 _draw_element）。
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
# RESIZABLE：窗口尺寸变化会抛 VIDEORESIZE，由 handle_event 更新宽高并重新夹相机
pygame.display.set_caption("灵光一现")
clock = pygame.time.Clock()                      # 固定 60 FPS

# 全文件唯一色板，尽可能少：COLOR_ON / COLOR_OFF 是两个主题色，其余只留结构必需项。
# 各面板的半透明底（HUD / 小地图 / 快捷栏 / 悬停高亮）不再各存色常量，统一由 _tint 现算。

def _tint(color, alpha):
    """给不透明色加 alpha 通道，得到半透明面板底；alpha 是功能参数，不另存颜色常量。"""
    return (color[0], color[1], color[2], alpha)

# ── 02. 世界与相机 ────────────────────────────────────────────────
# 三套坐标系，全文件换算只走这几个量，不要在别处另算一套：
#   格坐标 (row, col)  —— 状态的唯一身份，行列各自 -4000~3999，原点格 (0,0) 在世界正中；
#   世界像素 (x, y)    —— 格坐标 x BASE_CELL_SIZE，光段端点用它（与 zoom 无关，可缓存）；
#   屏幕像素 (sx, sy)  —— 世界像素减相机再乘 zoom，只在一帧内有效，见 _draw_rays。
# camera_x / camera_y 记的是“视口左上角的世界像素坐标”，所以变大 = 往右下看过去。

camera_x = -WINDOW_WIDTH / 2.0                   # 初始让世界原点落在屏幕正中
camera_y = -WINDOW_HEIGHT / 2.0
zoom = 1.0
# 说明：dt 只用于 WASD 平移的位移折算，与“刻”无关——刻的推进是主循环里按墙钟判断的，
# 因此掉帧只会让平移变顿，不会让时序变快或变慢。

# ── 03. 世界状态与时间步 ──────────────────────────────────────────
# 本节立三条规矩，后面所有节都不得越界：
#   1) grid_data 是唯一数据源，(row, col) -> 元件 dict；没有任何第二份“影子表”，
#      渲染 / 光路 / 小地图 / 存档都直接读它，所以不存在“两边不一致”这类 bug 的容身之处。
#   2) 元件字段分用户态与派生态两套（字段清单见文件头 docstring）：派生态一律每刻重算，
#      既不许进存档，也不许当跨刻记忆用——这是“贴图与真实状态不会打架”的结构保证。
#   3) 时序只由 tick_index（刻号）与延迟线的 pipe（延迟队列）两样构成，
#      除延迟线外没有任何东西记得上一刻发生过什么。
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
current_tool = 1                                 # 默认拿激光器：一开机右键就能玩
grid_changed = True                              # 脏标记：元件变化时置 True，主循环据此补走一刻
cached_ray_segments: List[Segment] = []          # 上一次求解的光段结果，渲染只读它

TOOL_TYPES = ('wall', 'laser', 'mirror', 'splitter', 'coupler', 'and_gate', 'latch',
             'delay_line')
SWITCHABLE_TYPES = ('laser',)                    # 只有激光器带 F 手动开关
TOOL_SPECS = {                                   # 放置数据的唯一定义处（lambda 保证每格新对象）
    'wall': lambda: {'type': 'wall', 'dir': 0},
    'laser': lambda: {'type': 'laser', 'dir': 0, 'is_on': True},
    'mirror': lambda: {'type': 'mirror', 'dir': 0, 'is_lit': False},
    'splitter': lambda: {'type': 'splitter', 'dir': 0, 'is_lit': False},
    'coupler': lambda: {'type': 'coupler', 'dir': 0},
    'and_gate': lambda: {'type': 'and_gate', 'dir': 0},
    'latch': lambda: {'type': 'latch', 'dir': 0, 'is_lit': False, 'state': 0,
                      'in_levels': frozenset()},
    # delay_line 四向对称，dir 恒 0 只为与其余元件共用贴图与序列化口径；
    # inject / pipe / out_ready 都是时序态：inject 是本刻注入账，pipe 是延迟队列，
    # out_ready 是本刻该放行的方向。三者一律不写盘（见 PERSIST_FIELDS 注释）。
    'delay_line': lambda: {'type': 'delay_line', 'dir': 0, 'ticks': delay_line_setting,
                      'is_lit': False, 'inject': set(), 'pipe': [], 'out_ready': ()},
}
# 工具显示名表：HUD 为纯 ASCII，元件用英文短名（与文件头命名表一一对应）
TOOL_DISPLAY = ['Wall', 'Laser', 'Mirror', 'Splitter', 'Coupler', 'AND Gate', 'Latch',
                'Delay Line']
TOOL_NAMES = ['%d %s' % (i, name) for i, name in enumerate(TOOL_DISPLAY)]

# 防卡死硬预算：单束上限只 bound 住一条射线，分束器每过一次多派生一束，射线总数不受它约束。
# 故整轮另有四道闸门，任一触发就地截断（已画光路保留、不补画猜测几何），HUD 报 TRUNC。
trace_note = 'ok'                                # 上一轮光路收尾状态，HUD 末行直接显示

# 时序：全图只有一个“刻”，长度固定；跨刻记忆只有延迟线的延迟队列这一件
tick_index = 0                                   # 已推进的刻数（编辑 / 撤销 / 读档后归零，显示到阈值循环归零）
delay_line_ready = 0                                  # 上一刻结束时正在放行的延迟线数
timeline_present = False                         # 世界里是否存在延迟线（缓存标志）
tick_note = ''                                   # 复位提示，HUD 时序行显示
delay_line_setting = DELAY_LINE_DEFAULT_TICKS              # 下一个延迟线的刻度（Q/E 在空格上调它）

# ── 04. 渲染资源：icon 一律预渲染，四方向共用一套工厂 ──────────────
# 全文件没有一处“每帧即时 draw 元件”：每个元件图标只画一次，之后全部走 blit。
# 三层缓存逐级复用，缩放时也只重画一次：
#   基准图（dir=0，一种颜色） -> _icon_frames 转成四方向帧 -> on/off 两套色 -> 缩放缓存
# 因此 15 万元件级别的画面也只画 8 类 x 2 色 x 4 向 = 64 张基准图加当前缩放档位的副本；
# 元件的“亮 / 暗”是换贴图名（xxx_on / xxx_off），不是改像素，颜色永远只有两套。

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

def _plus(surf, color):
    """格内正十字（十字架）：横竖两条等长粗线，几何中心严格落在方块中心。

    改用两条居中对齐的矩形来画，而不是 pygame 粗线：粗线在“整数坐标 + 偶数线宽”时
    会朝右、朝下各多占半格，导致十字整体偏右下；矩形能把线段中心精确压回方块中心。
    """
    c = ICON_SIZE / 2.0
    w = ICON_LINE_W
    span = ICON_SIZE - 2 * ICON_INSET
    off = round(c - w / 2.0)                       # 线段中心对齐 c，两侧对称各占 w/2
    pygame.draw.rect(surf, color, (off, ICON_INSET, w, span))     # 竖线
    pygame.draw.rect(surf, color, (ICON_INSET, off, span, w))     # 横线


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
    """反射镜：一条镜面斜线，dir=0 画“/”。"""
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

# 延迟线的图标见 _make_delay_line_icon：正方形外框 + 正十字（十字架），四向对称不带凸起

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

# 六类带开 / 关两态的元件：同一几何配两套色，一次注册八组帧
for _name, _maker in (('laser', _make_laser_icon), ('mirror', _make_mirror_icon),
                      ('splitter', _make_splitter_icon), ('coupler', _make_coupler_icon),
                      ('and_gate', _make_and_gate_icon), ('latch', _make_latch_icon),
                      ('delay_line', _make_delay_line_icon)):
    for _suffix, _color in (('_on', COLOR_ON), ('_off', COLOR_OFF)):
        ICONS[_name + _suffix] = _icon_frames(_maker(_color))

ICONS['wall'] = _icon_frames(_make_wall_icon(COLOR_OFF))       # 墙不导光也无开态
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
# 方向统一用 0/1/2/3 表示上/右/下/左，顺时针 +1 即右转，转朝向就是 (dir + step) % 4。
# 反射镜与光与门的“形状语义”一律只看 dir 的奇偶（偶数 = “/” 或水平透光轴，奇数 = 反斜或竖直
# 透光轴），贴图与光路共用同一个判据，因此看到的形状与算出来的结果不可能不一致。
REFLECT_ON_SLASH = {0: 1, 1: 0, 2: 3, 3: 2}          # “/” 镜：上<->右、下<->左
REFLECT_ON_BACKSLASH = {0: 3, 3: 0, 2: 1, 1: 2}      # 反斜镜：上<->左、下<->右
STEP_BY_DIR = {0: (-1, 0), 1: (0, 1), 2: (1, 0), 3: (0, -1)}

def reflected_direction(direction, mirror_dir):
    """打到反射镜后的新方向：偶数 dir 画“/”、奇数画反斜（贴图与光路共用此判据）。"""
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

# ── 06. 光路追踪（本文件核心）─────────────────────────────────────
# 这一节回答唯一一个难题：给定此刻的世界，光到底走到哪、谁因此亮起来。
# 结构：外层反复“重算一轮”直到没有任何东西再变化（不动点）；每轮固定做五件事：
#   1 清动态态（把全图清回“这一刻开始时它应处的态”，口径见 _reset_cell_dynamic）
#   2 消化射线队列（点亮反射镜 / 分束器、记下被打灭的激光器、记下受光的光锁存器输入边、
#     记下延迟线本刻的注入方向）
#   3 光与门 AND 判定（信号光与控制光同格都到过才点亮）
#   4 光锁存器上升沿（电平集与上一轮基准比对，新增几条就翻几次）
#   5 激光器熄灭锁定（本刻被打灭的灯从发光集合里摘掉，只活到本刻结束）
# 为什么要多轮：反射镜 / 分束器 / 耦合器 / 光与门的状态本身要由光决定，而光又由状态决定，
# 一轮解不出的相互依赖，交给下一轮，直到两轮结论完全相同。
# 提速：首轮一次全表扫描顺带交出四份播种集合（亮灯 / 置位锁存器 / 全部锁存器 / 全部延迟线），
#       第二轮起只清上一轮真被光碰过的那几格——绝大多数格子没人读它的旧值。
# 防死循环：ctx.seen 记“从哪格、朝哪个方向进入目标格”的状态。

@dataclass
class TraceCtx:
    """一轮光路的记账本：待消化队列、各类记账集合与预算计数器。

    每轮新建一份（见 solve_tick 里的 ctx = TraceCtx()），上一轮的光段绝不带过来，
    于是“这一轮看到了什么”完全由这份对象决定，不会有跨轮残留。
    用带类型的 dataclass 而不是一个装五种 value 的 dict：字段名即文档，
    类型检查器能直接查出把 Set 塞进 Dict 这类错误。
    touched_* 三兄弟是增量清理的依据：本轮被光碰过的格子，下一轮开头才需要清。
    """
    segments: List[Segment] = field(default_factory=list)
    pending: Deque[RaySeed] = field(default_factory=deque)
    hit_lasers: Set[Coord] = field(default_factory=set)         # 本轮被击中的激光器格
    seen: Set[RayState] = field(default_factory=set)            # 本轮已走过的射线状态
    lit_relay: Set[Coord] = field(default_factory=set)          # 就地“开”的反射镜 / 分束器
    lit_focus: Set[Coord] = field(default_factory=set)          # 激活的耦合器
    touched_and_gates: Set[Coord] = field(default_factory=set)   # 记过入账的光与门
    touched_latchs: Set[Coord] = field(default_factory=set)     # 记过入账的光锁存器
    touched_delay_lines: Set[Coord] = field(default_factory=set)     # 本轮被光打进来的延迟线
    delay_line_injects: Dict[Coord, Set[int]] = field(default_factory=dict)  # 本轮各延迟线的注入方向
    rays: int = 0
    steps: int = 0
    deadline: float = 0.0
    aborted: bool = False
    abort_reason: str = ''

def _reset_cell_dynamic(coord: Coord, data: dict, dark: Optional[Set[Coord]] = None,
                        and_gate_lit: Optional[bool] = None) -> None:
    """全文件唯一的动态态清基线口径：把一格清回“这一刻开始时它应处的态”。

    除延迟线以外没有任何跨刻记忆，所以基线就是“全图静止”：激光器按 is_on、光与门一律不亮、
    光锁存器按记忆位、反射镜 / 分束器 / 耦合器一律不亮；只有延迟线的 out_ready（上一刻末排好的
    放行方向）要如实带进本刻。dark 与 and_gate_lit 只在同一刻的多轮迭代里用：本轮已判定
    熄灭的灯不再复亮、本轮已判定导通的光与门本轮就当它导通，跨刻一律不带。
    wall 无动态态、未知类型一律不碰。
    """
    element_type = data['type']                      # type 键由 TOOL_SPECS 与 _normalize_cell 保证存在
    if element_type == 'laser':
        data['is_lit'] = bool(data.get('is_on', True)) and not (dark and coord in dark)
    elif element_type == 'and_gate':
        data['axis_inputs'] = set()                  # 实际到达的信号光（沿透光轴）方向
        data['perp_inputs'] = set()                  # 实际到达的控制光（垂直透光轴）方向
        data['is_lit'] = False if and_gate_lit is None else bool(and_gate_lit)
    elif element_type == 'latch':
        data['is_lit'] = bool(data.get('state'))     # 画面亮暗只反映记忆位
        data['input_dirs'] = set()
    elif element_type in ('coupler', 'mirror', 'splitter'):
        data['is_lit'] = False                       # 受光即开 / 被照才激活，先当关
    elif element_type == 'delay_line':
        # 全图唯一带跨刻记忆的元件：out_ready 要带进本刻，注入账 inject 只活在 ctx 里，
        # 解完这一刻才落回 data（刻末由 _advance_delay_lines 统一消化）。
        data['is_lit'] = bool(data.get('out_ready'))


def _wipe(coord: Coord, dark: Optional[Set[Coord]] = None,
          and_gate_lit: Optional[bool] = None) -> Optional[dict]:
    """刻内轮间增量清态入口：口径与 _reset_cell_dynamic 完全同一份实现，不再有第二套。"""
    data = grid_data.get(coord)
    if data is None:
        return None
    _reset_cell_dynamic(coord, data, dark, and_gate_lit)
    return data


def _baseline_reset() -> Tuple[List[Coord], Set[Coord], List[Coord], List[Coord]]:
    """按“全图静止”清基线，一次遍历交出四份播种用集合
    （开着的激光器 / 记忆位置 1 的光锁存器 / 全部光锁存器 / 全部延迟线）。
    一刻的第 0 轮开头只调这一处；延迟线以外没有任何上一刻的结论要继承。
    """
    laser_on: List[Coord] = []
    emitting_stones: Set[Coord] = set()
    latch_coords: List[Coord] = []
    delay_line_coords: List[Coord] = []
    for coord, data in grid_data.items():
        _reset_cell_dynamic(coord, data)             # 口径唯一：与 _wipe 共用，不再有两份实现
        element_type = data['type']
        if element_type == 'laser':
            if data['is_lit']:
                laser_on.append(coord)
        elif element_type == 'latch':
            latch_coords.append(coord)
            if data['is_lit']:
                emitting_stones.add(coord)
        elif element_type == 'delay_line':
            delay_line_coords.append(coord)
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
    """播种本轮射线：每类“会发光”的元件各出一束。

    存活激光器与记忆位置 1 的光锁存器按其 dir 发一束，刻末到点的延迟线按 out_ready 补一束；
    被光打灭的灯与置 0 的光锁存器已由外层从集合里筛掉，天然不在这里出现。
    全部排序只为同一份世界每轮解出同一份结果（可复现、可对比截图）。
    """
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

    预算耗尽的后果只是“这条新束不再派生”，在途射线照常走完：既保住已经画出的光路，
    也让外层 while 必在有限步内退出（pending 只减不增）。
    """
    if ctx.aborted:
        return False
    if ctx.rays + len(ctx.pending) >= MAX_RAYS_PER_ROUND:
        _abort_trace(ctx, 'rays>%d' % MAX_RAYS_PER_ROUND)
        return False
    ctx.pending.append((row, col, direction))
    return True

# 七类处理器签名是注册表协议要求的，用不到的形参冠 _ 前缀（等价于就地声明协议位）。
def _handle_laser(ctx, coord, hit_data, _direction):
    """激光器：记入本轮“被打灭”集合；入射段已由派发方登记到灯心，光在此被灯身挡住。"""
    ctx.hit_lasers.add(coord)

def _handle_mirror(ctx, coord, hit_data, direction):
    """反射镜：光一到就地“开”，按镜面朝向改向，从本格格心继续传播。"""
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
    if hit_data['is_lit']:
        return None
    if direction == (output_dir + 2) % 4:
        # 反向分束：光从输出边逆向进 -> 两条相邻输入边各发一束，正对边（直行）被吞。
        hit_data['is_lit'] = True
        ctx.lit_focus.add(coord)
        _spawn_ray(ctx, coord[0], coord[1], (output_dir + 1) % 4)
        _spawn_ray(ctx, coord[0], coord[1], (output_dir + 3) % 4)
        return None
    # 正向汇聚：非逆向入射 -> 从输出边另发一束。
    hit_data['is_lit'] = True
    ctx.lit_focus.add(coord)
    _spawn_ray(ctx, coord[0], coord[1], output_dir)
    return None

def _handle_and_gate(ctx, coord, hit_data, direction):
    """光与门 AND Gate：信号光 + 控制光两路都到过，本刻才导通。

    控制光（垂直透光轴入射）只记进 perp_inputs 账，随后被栅条吸收，绝不改光路；
    信号光（沿透光轴入射）记进 axis_inputs，本格已点亮才透射到轴的另一端，否则被吸收。
    “两路都到过”这件事由 _collect_lit_and_gates 在整轮射线消化完后统一判定，
    因为单束光走到光与门时另一路可能还没进来，就地判定会漏掉 AND。
    同刻即时生效：判定完当轮就把 is_lit 置真，所以光与门不带任何门延迟。
    """
    axis_dirs, perp_dirs = and_gate_ports(hit_data['dir'])
    ctx.touched_and_gates.add(coord)
    if direction in perp_dirs:
        hit_data['perp_inputs'].add(direction)
        return None
    hit_data['axis_inputs'].add(direction)
    if hit_data['is_lit']:
        return coord, direction, _cell_center(coord[1], coord[0])

def _handle_latch(ctx, coord, hit_data, direction):
    """光锁存器：把“光从哪条边进来”记成该输入边的电平 1，本体的记忆位由外层翻转。

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
    """延迟线：全图唯一真正跟“刻”有关的元件。

    光一律被本体吸收，只在账上记一笔“这一轮从 direction 进来过”，放不放行由刻末
    _advance_delay_lines 按延迟队列决定，本刻绝不派生射线。其余元件的处理器都不碰这里。
    """
    ctx.delay_line_injects.setdefault(coord, set()).add(direction)
    hit_data['is_lit'] = True
    ctx.touched_delay_lines.add(coord)


def _handle_wall(ctx, coord, hit_data, direction):
    """墙：入射段登记完即止，既不透射也不派生新射线（兼作未登记类型的兜底）。"""

# 注册表：返回 None 表示光在此终止，返回 (格子, 新方向, 新起点) 表示继续传播
ELEMENT_HANDLERS: Dict[str, Callable[..., HandlerResult]] = {
    'wall': _handle_wall, 'laser': _handle_laser, 'mirror': _handle_mirror,
    'splitter': _handle_splitter, 'coupler': _handle_coupler,
    'and_gate': _handle_and_gate, 'latch': _handle_latch, 'delay_line': _handle_delay_line,
}

def _trace_one_ray(ctx: TraceCtx) -> None:
    """推进队首的一条射线，直到被吸收、出界、走满单束上限或撞到任一预算。

    去重与截断的口径：
      seen 记“从哪格、朝哪个方向进入目标格”。同一轮里重复该状态，后面必然是重复几何
      且零新增记账（反射镜与分束器只是改配色、耦合器一次性激活、光与门点亮要到轮末才生效），
      所以掐掉它既防住镜面回路的无限循环，又保证不丢任何一条有效光路。
      出界时把终点钉在世界边界上（_ray_end_at_world_edge），画面不会出现断头光。
      走满 MAX_RAY_STEPS 只就地截断，绝不从当前格补画一条到边界的假线——
      正常折线的状态数已被去重限制在“格数 x 4”以内，走到这里只剩病态布局一种解释。
      任一预算触发即就地收工，已登记的光段全部保留。
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
        handler = ELEMENT_HANDLERS.get(_etype(hit_data), _handle_wall)
        result = handler(ctx, (next_row, next_col), hit_data, direction)
        if result is None:
            return
        (cur_row, cur_col), direction, start = result

    # 走满单束上限只剩病态布局这一种解释（正常折线的状态数已被去重限制在 格数x4 内）
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
      in_levels 为 None 表示“刚放置 / 刚旋转 / 刚复位”，此时只记基准不补算上升沿，
        否则摆下去那一瞬间就会白翻一次（存档里 null 与 -1 也一律还原成 None）。
      翻转按“新出现的边数”取模 2：三条输入边同轮一起亮，本该翻一次而不是三次。
      candidates 从第二轮起要并上“上一轮电平非空”的那批（armed_latchs），否则光撤走之后
        电平永远落不回空集，下次再受光就不算上升沿了——锁存器会“变迟钝”。
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
        data['in_levels'] = levels                    # 本轮电平成为下一轮的基准
        if levels:
            armed.add(coord)
        else:
            armed.discard(coord)
    return flipped, armed

def solve_tick(delay_line_seeds: List[RaySeed]) -> Tuple[List[Segment], List[Coord], bool]:
    """解一次光路，并把光路、光与门导通、光锁存器记忆位、激光器熄灭收敛到一致（幂等）。

    这一层完全没有“时序”概念：一轮五件事（清动态态 -> 消化射线 -> 光与门 AND -> 光锁存器
    上升沿 -> 激光器熄灭锁定），反复迭代到不动点。于是除延迟线以外的元件都是零刻延迟的
    组合逻辑——摆下去当场就是终态，光与门 AND 门同刻即亮即导通，不需要任何跨刻记忆。
    返回（光段, 全部延迟线坐标, 是否被预算截断）；trace_note 就地写好，HUD 直接显示。
    """
    global trace_note, timeline_present
    laser_on, emitting_latchs, latch_coords, delay_line_coords = _baseline_reset()
    timeline_present = bool(delay_line_coords)
    emitting: Set[Coord] = set(laser_on)
    lit_and_gates: Set[Coord] = set()
    armed_latchs: Set[Coord] = set()
    dark: Set[Coord] = set()                          # 本刻内被打灭的灯（只活到本刻结束）
    ctx = TraceCtx()                                  # 循环外先建好，MAX_LIGHT_ROUNDS=0 也不引用未绑定
    used_rounds = 0
    converged = False
    segments: List[Segment] = []
    for round_index in range(MAX_LIGHT_ROUNDS):
        used_rounds = round_index + 1
        # 步 1 清动态态：第 0 轮按“全图静止”清基线，之后只清上一轮真被光碰过的格子
        if round_index:                               # 此刻 ctx 还是上一轮那本账，照它增量清理
            _incremental_reset(ctx, dark, lit_and_gates)
        ctx = TraceCtx()                              # 一轮一份新账，上一轮光段不带过来
        segments = ctx.segments
        # 步 2 消化射线：发激光器 = 存活激光器 + 记忆位置 1 的锁存器 + 刻末到点的延迟线
        ctx.pending = deque(_seed_rays(emitting, emitting_latchs, delay_line_seeds))
        ctx.deadline = time.perf_counter() + TRACE_TIME_LIMIT_S
        while ctx.pending and not ctx.aborted:
            _trace_one_ray(ctx)                        # 每次推进一束，派生束就地回灌进同一本账
        if ctx.aborted:                               # 再迭代也只是反复截断，直接收工
            trace_note = 'TRUNC r%d %s (rays %d steps %d segs %d)' % (
                used_rounds, ctx.abort_reason, ctx.rays, ctx.steps, len(segments))
            break
        # 步 3 光与门 AND：两路到齐当轮就导通，零刻延迟（不需要跨刻记忆）
        new_lit = _collect_lit_and_gates(ctx)
        for coord in new_lit:
            grid_data[coord]['is_lit'] = True
        # 步 4 光锁存器上升沿：电平集与上一轮基准比对，翻出来的结果立刻影响发光集合
        flipped, armed_latchs = _advance_latch_states(
            latch_coords if round_index == 0 else list(ctx.touched_latchs | armed_latchs),
            armed_latchs)
        # 步 5 激光器熄灭锁定：只统计“此刻还活着”的灯被打灭了几盏（dark 只活到本刻结束）
        newly_dark = ctx.hit_lasers & emitting
        dark |= newly_dark
        # 不动点判据：本刻三件会互相推动的事（灯灭、光与门导通、锁存器翻转）都没再变化
        if not newly_dark and new_lit == lit_and_gates and not flipped:
            converged = True
            break
        emitting -= newly_dark
        lit_and_gates = new_lit
        for coord in flipped:                         # 光锁存器发光集合跟着记忆位增量更新
            if grid_data[coord]['state']:
                emitting_latchs.add(coord)
            else:
                emitting_latchs.discard(coord)
    if not ctx.aborted:                # 跑满上限仍没收敛时如实报 MAXR，不冒充 ok
        trace_note = '%s r%d (rays %d steps %d segs %d)' % (
            'ok' if converged else 'MAXR', used_rounds, ctx.rays, ctx.steps, len(segments))
    # 收尾 A：本刻被打灭的灯当场就打灰，渲染层永远不必再替状态模型打补丁
    for coord in dark:
        data = grid_data.get(coord)
        if data is not None:
            data['is_lit'] = False
    # 收尾 B：把注入账从上下文落回元件——只留收敛那一轮的结论，
    # 中间轮里被后续光改出来的临时账一律不作数（刻末 _advance_delay_lines 按它推线）
    for coord, dirs in ctx.delay_line_injects.items():
        data = grid_data.get(coord)
        if data is not None and _etype(data) == 'delay_line':
            data['inject'] = set(dirs)
            data['is_lit'] = True
    return segments, delay_line_coords, ctx.aborted


def _delay_line_ticks(data: dict) -> int:
    """取延迟刻度并夹进合法区间：坏档 / 手改的乱值一律退回默认，绝不让 len(pipe) 比较崩掉。"""
    try:
        ticks = int(data.get('ticks', DELAY_LINE_DEFAULT_TICKS))
    except (TypeError, ValueError):
        ticks = DELAY_LINE_DEFAULT_TICKS
    return max(DELAY_LINE_MIN_TICKS, min(ticks, DELAY_LINE_MAX_TICKS))

def _advance_delay_lines(coords: List[Coord]) -> int:
    """刻末统一推进所有延迟队列，返回本刻结束时正在放行的延迟线数。

    口径：每一刻先收下本刻注入账（没有光也要记一个空位，否则“没光的刻”不计时，
    延迟就成了“光走过的刻数”而不是真实刻数），线满 n 位才出队一位作为放行方向，
    于是 t 刻注入、第 t+n 刻放出，正好是“等 n 刻”。n 只由延迟刻度决定，换算成秒
    就是 n x TICK_INTERVAL_S。必须在整刻解完之后统一做，不能放在处理器里就地推进，
    否则同一刻被碰两次就会多吃掉一格线位。
    """
    global delay_line_ready
    ready = 0
    for coord in coords:
        data = grid_data.get(coord)
        if data is None or _etype(data) != 'delay_line':   # 这一轮之间被擦掉的块直接跳过
            continue
        ticks = _delay_line_ticks(data)                    # 刻度先夹进合法区间，坏值不崩比较
        inject = tuple(sorted(data.get('inject') or ()))
        data['inject'] = set()                        # 注入账只活到本刻结束
        pipe: List[Tuple[int, ...]] = data.setdefault('pipe', [])
        pipe.append(inject)                           # 每刻必进一位（没光就是空位）-> 计真实刻数
        # 线满 n 位才出队：t 刻注入的位，正好在第 t+n 刻成为放行方向
        data['out_ready'] = pipe.pop(0) if len(pipe) >= ticks else ()
        if len(pipe) > ticks:                         # 刻度被 Q/E 调小后裁掉多余线位
            del pipe[:len(pipe) - ticks]
        if data['out_ready']:
            data['is_lit'] = True                     # 只有正在往外放光才亮
            ready += 1
    delay_line_ready = ready
    return ready


def _delay_line_coords() -> List[Coord]:
    """当前世界里全部延迟线坐标（延迟队列与复位都要按这张表走）。"""
    return [coord for coord, data in grid_data.items() if _etype(data) == 'delay_line']


def reset_timeline(reason: str = '') -> None:
    """把时序倒回第 0 刻：刻号归零 + 每条延迟队列清空，别的东西没有跨刻记忆、无需清理。

    放置 / 擦除 / 旋转 / 改刻度 / 撤销重做 / 读档 / 粘贴都走这里。旧布局攒了
    一半的延迟队列对新布局没有意义（延迟装满信号再撤掉，复原后会凭空往外吐光），
    所以一律从干净的起点重算。
    """
    global tick_index, tick_note, timeline_present
    tick_index = 0
    if not timeline_present:
        tick_note = ('reset: %s' % reason) if reason else 'timeline reset'
        return                                        # 没有延迟线：不必为 15 万元件白扫一遍
    for data in grid_data.values():
        if _etype(data) == 'delay_line':
            data['pipe'] = []
            data['out_ready'] = ()
            data['inject'] = set()
            data['is_lit'] = False
    tick_note = ('reset: %s' % reason) if reason else 'timeline reset'


def step_tick() -> List[Segment]:
    """推进一刻：解一次光路（除延迟线外全部当场收敛）+ 推一次延迟队列 + 刻号 +1。

    全文件“时序”只有这一步，而且只有延迟线真的跨了过去：其它元件在这一步里已经是
    终态，刻与刻之间唯一的差别就是各条延迟队列往前挪了一格。
    """
    global tick_index, tick_note
    coords = _delay_line_coords()
    delay_line_seeds = [(row, col, d) for (row, col) in sorted(coords)
                   for d in (grid_data[(row, col)].get('out_ready') or ())]
    segments, _, aborted = solve_tick(delay_line_seeds)
    if aborted:                                       # 被预算截断的这一刻不算数：不推线、刻号不动
        tick_note = 'aborted'
        return segments
    _advance_delay_lines(coords)
    tick_note = ''
    tick_index = (tick_index + 1) % TICK_DISPLAY_WRAP   # 刻号到阈值归零，HUD 数字循环显示
    return segments


# ── 07. 渲染 ──────────────────────────────────────────────────────
# 本层是纯读者：只读 grid_data 与 solve_tick 交回的光段，一个字段都不写。
# 一帧的顺序固定为：底色 -> 网格线与视口内元件 -> 光路 -> HUD -> 小地图。
# 小地图最后画，所以它永远压在 HUD 之上（左上角提示再长也盖不住导航图）。
# 高亮判定要在取光标格之前问小地图：光标压在缩略图上时不该再亮一格，
# 否则出现“看着亮一格、点下去却在跳视口”的错觉（哨兵用 None，-1 是合法格号）。
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
    任何“被光打灭但 is_on 仍为真”的特判——渲染层替状态模型打补丁正是 #2 的成因。
    手动关（is_on=False）叠斜十字，被光打灭只变暗灰，两种“不亮”仍可区分。
    """
    element_type = _etype(data)
    name = ('wall' if element_type == 'wall'
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

_game_glow_cache: dict = {}                   # (w, h) -> 已烘焙的四边蓝色光晕层，尺寸变化才重建


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
    _draw_game_glow()          # 最底层：主界面同款竖向渐变氛围底（不透明铺满，代替 screen.fill）
    mouse_pos = pygame.mouse.get_pos()
    # 光标压在缩略图上时不取格高亮，避免“看着亮一格、点的却是地图”；None 当哨兵（-1 也是合法格）
    _ui_hover = minimap_hit(mouse_pos) or hotbar_index_at(mouse_pos) is not None
    hover_row, hover_col = (None, None) if _ui_hover else screen_to_grid(*mouse_pos)
    _draw_cells_in_view(hover_row, hover_col)
    _draw_rays(ray_segments)
    draw_minimap(ray_segments)
    draw_hotbar()

# ── 08. 小地图（视口局部地图，恒为主画面的 0.05 倍）────────────────
# 图幅正中心始终是视口中心，它不是整张世界的缩略图，故元件能按所在格真实相对大小
# 画成小方块，光路只需 Liang-Barsky 裁到图幅内再画（只夹端点会在边框上画出假线）。
MM_FONT = pygame.font.SysFont('consolas,menlo,monospace', 12)

minimap_visible = True
minimap_dirty = True
_minimap_surface: Optional[pygame.Surface] = None
_minimap_key: Optional[Tuple[int, int, int]] = None
_minimap_dragging = False
_mm_last_click_ms = 0            # 上一次在小地图内按下左键的时刻，用于双击判定

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
    在框上画出根本不存在的“假光路”。参数化求交后只画真正落在图幅内的那一截，
    小地图上的光路才与主画面严格一致。
    """
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
    """重画缩略图并写进缓存：底色 -> 世界边界 -> 光路 -> 元件点 -> 边框。

    这是一张“视口局部图”而不是全图缩略图：图幅中心恒等于视口中心，倍率恒为主画面的
    0.05 倍。好处是元件能按所在格在图上的真实相对大小画成小方块（哪怕世界有 15 万元件，
    也不会糊成一片噪点），代价是看不出全貌，所以靠近世界尽头时会把边界线画出来当方位感。
    光路先裁进图幅再画；元件点的取源同样按“范围格数 vs 元件数”双向择优。
    """
    global _minimap_surface, minimap_dirty, _minimap_key
    scale = _mm_scale()
    center_x, center_y = _mm_center()
    half = (MM_SIZE / 2.0) / scale                    # 图幅半边长对应的世界像素范围
    surf = pygame.Surface((MM_SIZE, MM_SIZE), pygame.SRCALPHA)
    surf.fill(_tint(COLOR_BG, 140))
    for world_x in (WORLD_MIN_PX, WORLD_MAX_PX):      # 世界边界：平时在图外看不见
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
            cache.clear()                             # 文案基本是固定几条，超量整表重来
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
    if surf is None:                                  # 刚建缓存就失败（例如显存异常）：本帧跳过
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

# ── 08b. 底部快捷栏（Minecraft 式：元件图标 + 选中蓝框 / 未选灰框，点击即选中；选中名大字号居中显示在图标上方）──
# 与 HUD 文本互斥：元件"当前是什么、有哪些可切"改由此栏可视化承载，故 HUD 删去了工具两行。
# 纯绘制层 + 命中测试，不改任何状态模型；选中直接写 current_tool，与数字键 0-7 同一口径。
HOTBAR_FONT = pygame.font.SysFont('consolas,menlo,monospace', 11)
HOTBAR_NAME_FONT = pygame.font.SysFont('consolas,menlo,monospace', 24)  # 选中元件名的大号字
HOTBAR_NUM_FONT  = pygame.font.SysFont('consolas,menlo,monospace', 20, bold=True)  # 左上角序号：放大加粗

def _hotbar_rects() -> List[pygame.Rect]:
    """按当前窗口宽算出 n 个格子矩形：整体水平居中、贴窗口底部。"""
    n = len(TOOL_TYPES)
    step = HOTBAR_CELL + HOTBAR_GAP
    total = n * step - HOTBAR_GAP
    win_w, win_h = screen.get_size()
    x0 = max(4, (win_w - total) // 2)
    y0 = win_h - HOTBAR_CELL - HOTBAR_BOTTOM_PAD
    return [pygame.Rect(x0 + i * step, y0, HOTBAR_CELL, HOTBAR_CELL) for i in range(n)]

def hotbar_index_at(pos) -> Optional[int]:
    """屏幕坐标命中的快捷栏下标，未命中返回 None。"""
    for i, rect in enumerate(_hotbar_rects()):
        if rect.collidepoint(pos):
            return i
    return None

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
        side = HOTBAR_CELL - 8                 # 图标四周留 4px 内边距
        sx = rect.x + (rect.w - side) // 2
        sy = rect.y + (rect.h - side) // 2
        blit_icon(_hotbar_icon_name(TOOL_TYPES[i]), 0, sx, sy, side)
        pygame.draw.rect(screen, COLOR_ON if selected else COLOR_OFF,
                         rect, 3 if selected else 1)
        num_col = COLOR_ON if selected else COLOR_OFF
        shadow = HOTBAR_NUM_FONT.render(str(i), True, (0, 0, 0))
        num = HOTBAR_NUM_FONT.render(str(i), True, num_col)
        screen.blit(shadow, (rect.x + 4, rect.y + 3))
        screen.blit(num,    (rect.x + 3, rect.y + 2))
    # 选中元件名：大号字，水平居中于整排图标正上方（字体放大，靠整排宽度腾出空间）
    label = HOTBAR_NAME_FONT.render(TOOL_DISPLAY[current_tool], True, COLOR_ON)
    lx = (rects[0].x + rects[-1].right) // 2 - label.get_width() // 2
    ly = rects[0].top - label.get_height() - 4
    screen.blit(label, (lx, ly))

# ── 09. HUD 已按需求整体删除 ───────────────────────────────────────────
# 左上角纯 ASCII 提示层（HUD_FONT / HUD_LINES / hud_y / draw_hud）连同其 surface 缓存
# 一并移除：沙盘画面只保留底部快捷栏承载元件信息，光晕 / 网格 / 元件 / 光路 / 小地图照常。
# 光路求解、时序模型、存档、存读撤重与各一次性提示写入端均不受影响（只是不再上屏显示）。


# ── 10. 输入处理 ──────────────────────────────────────────────────
# 本节只做“事件 -> 动作”的派发，真正的状态改动全在被调用的函数里（放置 / 擦除 / 旋转 /
# 开关 / 存读 / 撤重做），因此加按键只需要多一个分支，不会牵动状态模型。
# 两条容易误解的派发优先级：
#   小地图优先——落在图内的点击一律当导航，绝不穿透成放置 / 擦除；
#   F4 与 Enter 各自独立——F4 单独键整盘读档，Enter 单独键在光标处粘贴，两者不再耦合。
# 一切改世界的动作都必须先 push_undo 再改，并置 grid_changed / world_dirty 两个脏标记。
TOOL_KEY_MAP = {pygame.K_0 + i: i for i in range(len(TOOL_TYPES))}   # 数字键 0-7 对应工具下标
# 鼠标键位：默认左键放置、右键擦除（与主流沙盒及右键菜单语义一致）。
is_dragging = False
last_mouse_pos = (0, 0)
delete_held = False        # Delete 长按标志：True 时每帧连续擦除光标格，光标移到哪删哪
place_held = False         # Enter 长按标志：True 时每帧连续放置当前工具，光标移到哪放到哪
_place_last_coord = None   # 长按连续放置的上一格：同格下一帧跳过，避免每帧重复压撤销栈

# 长按连铺 / 连删的事务：整段长按只记一步撤销。
# 按下第一个键时开事务并登记首格改前态；长按期间每移到新的一格补登一次（同格只登一次）；
# 松手时把整段收集到的改前态合并成“一步 delta”入栈——于是一次 Z 就能撤销整条长按笔画，
# 而不是按了多少格就要撤多少次。单击（鼠标点击 / 单次按键）仍走原 push_undo，行为不变。
_stroke_active = False
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
    grid_data[coord] = TOOL_SPECS[TOOL_TYPES[current_tool]]()
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
    grid_data.pop(coord)
    reset_timeline('erase')
    grid_changed = world_dirty = True

def delete_erase_at_cursor() -> None:
    """Delete 擦除入口：光标压在底部快捷栏或小地图上时不穿透误删。"""
    _mp = pygame.mouse.get_pos()
    if minimap_hit(_mp) or hotbar_index_at(_mp) is not None:
        return
    erase_element()                                 # 复用左键擦除：压栈+复位时序，行为一致

def place_at_cursor() -> None:
    """Enter 放置入口：光标压在底部快捷栏或小地图上时不穿透误放；
    长按时每格只放一次——停在同一格下一帧跳过，避免每帧重复压撤销栈。"""
    global _place_last_coord
    _mp = pygame.mouse.get_pos()
    if minimap_hit(_mp) or hotbar_index_at(_mp) is not None:
        return                                    # 与 Delete 同口径：落 UI 不穿透
    coord = _cursor_coord()
    if coord == _place_last_coord:
        return                                    # 长按停在同一格：本帧不重复放
    place_element()                               # 复用右键放置：压栈+复位时序，行为一致
    _place_last_coord = coord

def _cursor_coord() -> Coord:
    """光标所在格（撤销 delta 要按格登记，故坐标与数据各取一个助手）。"""
    return screen_to_grid(*pygame.mouse.get_pos())

def _cursor_element() -> Optional[dict]:
    """取光标所在格的元件数据，空格返回 None（旋转与 F 开关共用）。"""
    return grid_data.get(_cursor_coord())


def rotate_element(step: int) -> None:
    """Q(step=-1) / E(step+1)：一个键位干三件事，按“光标下是什么”分流。

    1) 光标下是普通元件：转朝向（dir 顺时针 +1 / 逆时针 -1）；光锁存器还要把 in_levels
       置 None，让新朝向的输入边只记基准、不补算上升沿，免得转一下白翻一次。
    2) 光标下是延迟线：它四向对称，转了没有任何可见差别，于是把这个键位让给
       “调延迟刻度”（1~12 刻），并把延迟队列清空——线长上限变了，旧线位没有意义。
    3) 光标压在空格上且当前工具是延迟线：调的是放置预设 delay_line_setting，
       可以先定好刻度再连着摆一排同刻度的块。
    三种情况都算“改世界”，一律压撤销步并复位时序。
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
        _note('delay preset now %d ticks' % delay_line_setting)
        return
    if _etype(data) == 'delay_line':
        new_ticks = _delay_line_ticks(data)
        new_ticks = max(DELAY_LINE_MIN_TICKS, min(new_ticks + step, DELAY_LINE_MAX_TICKS))
        if new_ticks == _delay_line_ticks(data):
            return
        push_undo([_cursor_coord()])
        data['ticks'] = new_ticks
        data['pipe'] = []                            # 改刻度等于重新拉一次延迟队列
        data['out_ready'] = ()
        _note('delay now %d ticks' % new_ticks)
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


def handle_event(event):
    """处理一个事件并派发到对应动作；返回 False 表示要退出主循环。"""
    global current_tool, WINDOW_WIDTH, WINDOW_HEIGHT, _minimap_dragging, is_dragging, delete_held, _mm_last_click_ms
    global place_held, _place_last_coord
    global last_mouse_pos, screen_state, _game_esc_time, perf_visible
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.VIDEORESIZE:              # 尺寸变化：只更新宽高并重夹相机
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
        clamp_camera()
    elif event.type == pygame.MOUSEBUTTONDOWN:
        if minimap_hit(event.pos):                    # 图内点击一律当导航，不穿透到放置/擦除
            if event.button == 1:
                now_ms = pygame.time.get_ticks()
                if now_ms - _mm_last_click_ms <= _MM_DBLCLICK_MS:
                    # 双击小地图：视口中心归零回世界原点，取消本次跳转与拖拽
                    _mm_last_click_ms = 0
                    _minimap_dragging = False
                    reset_view_to_origin()
                else:
                    _mm_last_click_ms = now_ms        # 记为第一击，仍执行原来的单击跳转
                    _minimap_dragging = True
                    focus_camera_on_map(*event.pos)
            return True
        hb_idx = hotbar_index_at(event.pos)           # 底部快捷栏：落在栏内一律当选择，不穿透到放置/擦除
        if hb_idx is not None:
            if event.button == 1:
                current_tool = hb_idx
            return True
        if event.button == 2:
            is_dragging = True                        # 中键：开始拖拽平移
            last_mouse_pos = pygame.mouse.get_pos()
        elif event.button == PLACE_BTN:
            place_element()                           # 放置键（默认左键；INVERT_MOUSE 时右键）
        elif event.button == ERASE_BTN:
            erase_element()                           # 擦除键（默认右键；INVERT_MOUSE 时左键）
    elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 2:
            is_dragging = False                       # 中键平移只认自己的抬起
        _minimap_dragging = False                     # 缩略图导航任何抬起都复位
    elif event.type == pygame.KEYUP:
        if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            delete_held = False                       # 松开 Delete/退格：停止长按连续擦除
            _stroke_commit()                          # 整段连删合并为一步撤销
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            place_held = False                        # 松开 Enter：停止长按连续放置
            _place_last_coord = None
            _stroke_commit()                          # 整段连铺合并为一步撤销
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
        elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            # Delete/退格：按下即开一次连删事务并删光标格，主循环据此逐帧连续擦除；松手合并为一步撤销
            delete_held = True
            _stroke_begin()
            delete_erase_at_cursor()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            # Enter：按下即开一次连铺事务并放当前工具，主循环据此逐帧连续放置；松手合并为一步撤销
            place_held = True
            _place_last_coord = None
            _stroke_begin()
            place_at_cursor()
        elif event.key == pygame.K_f:
            toggle_switch()
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
            save_slot(event.key - pygame.K_F1 + 1)    # 存槽只认功能键，与 Enter 粘贴互不干扰
        elif event.key == pygame.K_F4:
            load_recent_slot()                        # F4 单独键：整盘读取最近槽位
        elif event.key == pygame.K_F12:
            perf_visible = not perf_visible           # F12：性能面板显隐（FPS/求解耗时/元件数/撤销栈深）
        elif event.key == pygame.K_v:
            paste_slot_at_cursor()                    # V 单独键：在光标格粘贴图章（输入法不敏感，避开 Enter）
        elif event.key == pygame.K_ESCAPE:
            now = pygame.time.get_ticks()
            if now - _game_esc_time < _ESC_RETURN_WIN:     # 窗口内第二次 ESC：返回主界面
                delete_held = place_held = is_dragging = False
                _place_last_coord = None
                screen_state = 'menu'                      # 第二次按下即视为确认，返回主界面
                _game_esc_time = 0                         # 回菜单后重新上膛，不带旧时间戳
            else:
                _game_esc_time = now                       # 第一次 ESC：只记时，画布顶部给提示
    return True


# ── 11. 存档、读档与撤销重做 ──────────────────────────────────────
# 本节要同时守住三件事：存档要小、坏档不能崩、撤销不能卡。
#
# 存档口径（小）：只落用户字段（坐标 / type / dir / 激光器 is_on / 光锁存器 state 与
#   in_levels / 延迟 ticks）外加相机与工具。is_lit、axis_inputs、perp_inputs、input_dirs、
#   pipe、out_ready、inject 全是派生态或时序态，读回来由 solve_tick 与 reset_timeline
#   重建；存进去只会带来脏数据（最典型：一份静止存档读回来自己往外吐光）。
# 读档口径（不崩）：每一条 cell 都要过 _normalize_cell 消毒——未知类型丢弃、越界坐标剔除、
#   乱值夹回合法区间；整份文件读不通就退回“保持当前世界”并给一条 HUD 提示。
#   读档与粘贴共用同一份解析口径（_read_slot），两条路不会各自漂移。
# 写盘口径（不半截）：先写 slotN.json.tmp 再 os.replace 原子换名，中途崩溃只留 .tmp。
# 撤销口径（不卡）：一步只记“这次动了哪几格”的改前状态（delta），
#   单步成本 O(改动格数) 而不是 O(全图)，于是栈深能从 50 放开到 200 也不吃内存。
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves')

PERSIST_FIELDS = {
    'wall': ('dir',), 'laser': ('dir', 'is_on'), 'mirror': ('dir',), 'splitter': ('dir',),
    'coupler': ('dir',), 'and_gate': ('dir',), 'latch': ('dir', 'state', 'in_levels'),
    # 延迟线只落刻度：pipe / out_ready / inject 是时序态，等同于派生态——
    # 存进去会让一份静止的存档读回来自己往外吐光，一律由 reset_timeline 从零刻重建。
    'delay_line': ('dir', 'ticks'),
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
        _encode_levels 的逆运算：-1 与 null 都还原成 None（未定义基准）。null 若被当成空集，语义就变成“基准=没有输入边为 1”：读档当轮只要有一条输入边受光就会被算成上升沿，光锁存器凭空翻转一次。
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
    if etype == 'laser' and data.get('is_on') is None:
        data['is_on'] = True                            # null 的开关按“开”处理，别读成关
    try:
        data['dir'] = int(data['dir']) % 4
    except (TypeError, ValueError):
        data['dir'] = 0
    if etype == 'latch':
        data['state'] = int(data.get('state') or 0) % 2
    if etype == 'delay_line':
        data['ticks'] = _delay_line_ticks(data)              # 乱值 / 越界一律夹回合法区间
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
    """存到指定槽位：先写 slotN.json.tmp，再 os.replace 原子换名。

    分两步是为了“崩溃也只脏临时文件”：写到一半断电时，上一份能用的存档仍然完好，
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

    这里刻意不吞异常：调用方要能区分“槽位是空的”“文件坏了”“成功但一格都没有”，
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
    timeline_present = any(_etype(d) == 'delay_line' for d in cells.values())
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

# ── 00b. 启动主界面（标题 LightOptics + Start 按钮）───────────────
# 一个纯展示 + 单次命中的菜单状态：screen_state == 'menu' 时主循环只画这一屏，
# 点中 Start（或按 Enter / 空格）就切到 'game' 进入沙盘。配色沿用全局色板，不新增色常量。
MENU_FONT_TITLE = pygame.font.SysFont('consolas,menlo,monospace', 96, bold=True)
MENU_FONT_SUB = pygame.font.SysFont('consolas,menlo,monospace', 20)
MENU_FONT_BTN = pygame.font.SysFont('consolas,menlo,monospace', 40)
MENU_FONT_SEC = pygame.font.SysFont('consolas,menlo,monospace', 28, bold=True)
MENU_FONT_BODY = pygame.font.SysFont('consolas,menlo,monospace', 20)
screen_state = 'menu'                         # 'menu' 启动界面 / 'tutorial' 教学页 / 'game' 沙盘主程序
_game_esc_time = 0                            # 游戏态上一次按 ESC 的时刻（毫秒）：连按两次才回主界面
_tut_scroll = 0.0                             # 教学页滚动偏移（像素）
_tut_content_h = 0                            # 教学页内容总高（每帧重算，用于限制滚动）

# ---- 主界面程序化氛围背景 ----
# 不跑完整光路，只做质感：竖向渐变 + 与主画面同距的淡网格打底，上面散布若干暗色元件图标。
# 元件不移动——它们随机地「刷新出现 / 淡出删除」，出现与消失时各自淡入淡出，存活期间只做原地
# 明灭呼吸。全部用 _tint / 现算色 + 现成 ICONS，不引入素材文件，也不碰 step_tick 时序引擎——
# 守住「单文件、无素材」原则，且菜单态根本不走主时序路径。
_MENU_ICON_POOL = (   # 随机刷新的暗色元件（取各元件关态灰图，wall 无开态）
    'laser_off', 'mirror_off', 'splitter_off', 'coupler_off',
    'and_gate_off', 'latch_off', 'delay_line_off', 'wall',
)
_menu_bg_cache = {}                          # (w, h) -> 已烘焙的「渐变+网格」静态底层
_menu_decor = {}                             # (col, row) -> 存活元件 {'name','dir','side','born','dying','per','ph'}
_menu_decor_size = None                      # 上次布置时记录的窗口尺寸，尺寸变化即清空重摆
_menu_decor_last = -1                        # 上次刷新决策的时间戳（ms），驱动随机出现/删除

def _pulse(t_ms, period_ms, lo, hi, phase=0.0):
    """三角波：随时间在 [lo,hi] 来回折返，避开引入 math 库。"""
    ph = ((t_ms / period_ms) + phase) % 1.0
    tri = ph if ph < 0.5 else (1.0 - ph)          # 0->1->0 的折返曲线
    return lo + (hi - lo) * (tri * 2.0)

def _build_bg_gradient(win_w, win_h, with_grid=True) -> pygame.Surface:
    """全文件唯一的「氛围底」渲染逻辑：竖向渐变（顶部 COLOR_BG -> 底部略偏蓝），
    可选叠加一层与主画面同距的淡网格。主界面氛围背景与沙盘画面的光晕共用这一个函数，
    保证两边色调完全同源。纯现算，不新增色常量。"""
    surf = pygame.Surface((win_w, win_h))                          # 不透明，整屏铺满
    top = COLOR_BG                                                # 顶部：纯深色底
    bot = (COLOR_BG[0], COLOR_BG[1] + 8, COLOR_BG[2] + 28)        # 底部：略偏蓝
    denom = max(1, win_h - 1)
    for y in range(win_h):
        r = y / denom
        pygame.draw.line(
            surf,
            (int(top[0] + (bot[0] - top[0]) * r),
             int(top[1] + (bot[1] - top[1]) * r),
             int(top[2] + (bot[2] - top[2]) * r)),
            (0, y), (win_w, y))
    if with_grid:
        gc = (int((COLOR_BG[0] + COLOR_GRID[0]) / 2),              # 淡网格：介于底与结构线之间
              int((COLOR_BG[1] + COLOR_GRID[1]) / 2),
              int((COLOR_BG[2] + COLOR_GRID[2]) / 2))
        step = BASE_CELL_SIZE                                       # 与主画面网格同距，视觉呼应
        for gx in range(0, win_w, step):
            pygame.draw.line(surf, gc, (gx, 0), (gx, win_h), 1)
        for gy in range(0, win_h, step):
            pygame.draw.line(surf, gc, (0, gy), (win_w, gy), 1)
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
    if _menu_decor_size != (win_w, win_h):        # 窗口尺寸变了：清空旧布置重摆
        _menu_decor.clear()
        _menu_decor_size = (win_w, win_h)
        _menu_decor_last = t_ms
        return
    if _menu_decor_last < 0:
        _menu_decor_last = t_ms
    while t_ms - _menu_decor_last >= _MENU_DECOR_STEP_MS:
        _menu_decor_last += _MENU_DECOR_STEP_MS
        cur = _menu_decor_last
        # 未到上限偏向「刷新出现」；已满载则偏向「淡出删除」再补一枚
        place = random.random() < (0.72 if len(_menu_decor) < _MENU_DECOR_MAX else 0.28)
        if place:
            key = _menu_pick_free_cell(win_w, win_h)
            if key is not None:
                _menu_decor[key] = {
                    'name': random.choice(_MENU_ICON_POOL),
                    'dir': random.randrange(4),
                    'side': int(ICON_SIZE * (1.5 + random.random() * 0.8)),
                    'born': cur, 'dying': None,
                    'per': 2200.0 + random.random() * 1600.0,   # 原地呼吸周期
                    'ph': random.random(),                       # 明暗相位
                }
                continue
        # 不放（或放不下）= 删除：随机挑一枚还活着的标记淡出
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
    # 清掉淡出到期的元件
    for k in [k for k, v in _menu_decor.items()
              if v['dying'] is not None and t_ms - v['dying'] >= _MENU_DECOR_FADE_MS]:
        _menu_decor.pop(k, None)
    cell = _MENU_DECOR_CELL
    for (col, row), d in _menu_decor.items():
        # 淡入淡出包络：出现时 0->1，删除时 1->0，稳态为 1
        if d['dying'] is None:
            fade = min(1.0, (t_ms - d['born']) / _MENU_DECOR_FADE_MS)
        else:
            fade = 1.0 - min(1.0, (t_ms - d['dying']) / _MENU_DECOR_FADE_MS)
        breathe = _pulse(t_ms, d['per'], 0.35, 1.0, d['ph'])   # 原地明灭，不改变位置
        alpha = max(0, min(255, int(80 * fade * breathe)))
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
    btn_w, btn_h = 220, 64
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 + 30, btn_w, btn_h)

def _tutorial_button_rect() -> pygame.Rect:
    """教学按钮矩形：水平居中，位于 Start 按钮正下方，跟随窗口尺寸。"""
    win_w, win_h = screen.get_size()
    btn_w, btn_h = 220, 64
    return pygame.Rect(win_w // 2 - btn_w // 2, win_h // 2 + 120, btn_w, btn_h)

def _draw_menu_scrim() -> None:
    """主界面中央柔光暗底：在氛围背景之上、标题/副标题/Start 按钮之下铺一条竖向渐隐的暗带，
    使随机刷新的暗色元件即使摆到中央也不会压住文字与按钮（替代旧的中央保留区方案）。
    竖向 alpha 由中心向上下两侧线性淡出到 0，边缘无硬边；纯现算色，不新增色常量。"""
    win_w, win_h = screen.get_size()
    cy = win_h // 2 - 40                    # 暗带竖向中心：贴合标题到按钮的区块
    band = max(120, int(win_h * 0.30))      # 单侧厚度
    r, g, b = COLOR_BG
    scrim = pygame.Surface((win_w, 2 * band), pygame.SRCALPHA)
    for j in range(2 * band):
        d = abs(j - band) / band            # 0(中心) -> 1(边缘)
        a = int(120 * (1 - d)) if d < 1 else 0
        if a <= 0:
            continue
        pygame.draw.line(scrim, (r, g, b, a), (0, j), (win_w, j))
    screen.blit(scrim, (0, cy - band))


def draw_menu() -> None:
    """启动界面：程序化氛围背景 + 居中 LightOptics 标题 + 副标题 + Start 按钮 + 操作提示。"""
    _draw_ambient_menu(pygame.time.get_ticks())
    _draw_menu_scrim()          # 中央柔光暗底：把随机元件压到文字/按钮之下，保证可读
    win_w, win_h = screen.get_size()
    title = MENU_FONT_TITLE.render('LightOptics', True, COLOR_ON)
    screen.blit(title, (win_w // 2 - title.get_width() // 2, win_h // 2 - 150))
    sub = MENU_FONT_SUB.render('Light-based Logic Sandbox', True, COLOR_OFF)
    screen.blit(sub, (win_w // 2 - sub.get_width() // 2, win_h // 2 - 30))
    for rect, label in ((_start_button_rect(), 'Start'), (_tutorial_button_rect(), 'Tutorial')):
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        bg = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        bg.fill(_tint(COLOR_ON, 74 if hovered else 44))    # 氛围底较花，按钮底加厚以拉开层次
        screen.blit(bg, rect.topleft)
        pygame.draw.rect(screen, COLOR_ON, rect, 3 if hovered else 2)
        txt = MENU_FONT_BTN.render(label, True, COLOR_ON)
        screen.blit(txt, (rect.centerx - txt.get_width() // 2,
                          rect.centery - txt.get_height() // 2))
    hint = MENU_FONT_SUB.render('Start / Enter / Space to begin    ESC x2 in game returns here',
                                True, COLOR_OFF)
    screen.blit(hint, (win_w - hint.get_width() - 16, win_h - hint.get_height() - 12))

def handle_menu_event(event) -> bool:
    """菜单事件：点 Start 或按 Enter / 空格进入沙盘；点 Tutorial 进教学页；尺寸跟随窗口。
    主界面按一次 ESC 即请求退出程序（返回 False）。返回 False 即请求退出程序。
    """
    global screen_state, WINDOW_WIDTH, WINDOW_HEIGHT, _tut_scroll
    if event.type == pygame.QUIT:
        return False
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        if _start_button_rect().collidepoint(event.pos):
            screen_state = 'game'
        elif _tutorial_button_rect().collidepoint(event.pos):
            _tut_scroll = 0.0                     # 每次进教学页都从头看
            screen_state = 'tutorial'
    elif event.type == pygame.KEYDOWN:
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            screen_state = 'game'
        elif event.key == pygame.K_ESCAPE:
            return False                          # 主界面按一次 ESC 直接退出应用
    return True


# ── 00c. 教学页（screen_state == 'tutorial'）───────────────────────
# 纯展示态：背景与主界面完全一致（复用 _draw_ambient_menu + _draw_menu_scrim），
# 只是不画标题/按钮，改画一块半透明面板承载元件与操作说明。不进 step_tick，
# 背景呼吸动画靠 pygame.time.get_ticks() 驱动，时序引擎完全不受影响。
# 元件图标全部复用现成 ICONS（关态灰图），零素材、零新增色常量。
TUTORIAL_SECTIONS = [
    ('HOW TO PLAY', [
        ('', 'LMB / Enter place   RMB / Del erase'),
        ('', 'Number select tool   Q / E rotate   wheel zoom'),
        ('', 'arrows / W A S D / MMB move'),
        ('', 'Z undo  X redo   F1-F3 save   F4 load   V stamp-paste'),
        ('', 'M toggle minimap   ESC x2 returns to menu   ESC quit from menu'),
        ('', 'F12 perf panel: FPS / solve ms / cells / undo depth'),
        ('', 'Hold Enter / Del to lay/erase a run; one Z undoes the whole run'),
    ]),
    ('ELEMENTS', [
        ('wall', 'Wall: solid block, does not conduct light'),
        ('laser_off', 'Laser: light source, emits a beam each tick along its dir'),
        ('mirror_off', 'Mirror: reflects 45 degrees, bends the beam by 90 degrees'),
        ('splitter_off', 'Splitter: splits one beam into pass-through + reflected'),
        ('coupler_off', 'Coupler: merges several beams toward one output'),
        ('and_gate_off', 'AND gate: lights output only when inputs are present'),
        ('latch_off', 'Latch: self-holds on/off, one bit of memory'),
        ('delay_line_off', 'Delay line: the only time element, stores N ticks then emits'),
    ]),
    ('TIPS', [
        ('', 'Light is solved within one tick; only delay line carries state'),
        ('', 'Element dir decides optics; misplaced? press Z to undo'),
        ('', 'Hotbar top-left number = the number key to select it'),
    ]),
]


def _draw_game_esc_hint() -> None:
    """游戏态第一次按 ESC 后，在画面顶部短暂提示"再按一次返回主界面"。"""
    now = pygame.time.get_ticks()
    if now - _game_esc_time < _ESC_RETURN_WIN:
        win_w, _ = screen.get_size()
        msg = 'Unsaved changes - press ESC again to return' if (world_dirty and grid_data) \
            else 'Press ESC again to return to menu'
        t = MENU_FONT_SUB.render(msg, True, (235, 190, 70))
        screen.blit(t, (win_w // 2 - t.get_width() // 2, 12))


def handle_tutorial_event(event) -> None:
    """教学页事件：滚轮 / 方向键 / PgUp-Dn 滚动；ESC 直接返回主界面。不返回退出信号。"""
    global screen_state, _tut_scroll, WINDOW_WIDTH, WINDOW_HEIGHT, _game_esc_time
    if event.type == pygame.VIDEORESIZE:
        WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
    elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
        _tut_scroll += 90 if event.button == 4 else -90
    elif event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            screen_state = 'menu'
            _game_esc_time = 0                    # 回菜单重新上膛，避免被当作游戏内第一次 ESC
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
    _draw_ambient_menu(pygame.time.get_ticks())
    _draw_menu_scrim()
    win_w, win_h = screen.get_size()
    title = MENU_FONT_BTN.render('Help', True, COLOR_ON)
    screen.blit(title, (win_w // 2 - title.get_width() // 2, 22))
    close_hint = MENU_FONT_SUB.render(
        '[ESC] back to menu      wheel / arrows / PgUp-Dn scroll', True, COLOR_OFF)
    screen.blit(close_hint, (win_w // 2 - close_hint.get_width() // 2, win_h - 34))

    panel_w = min(760, win_w - 80)
    panel_x = win_w // 2 - panel_w // 2
    panel_y = 76
    panel_h = win_h - 76 - 46
    panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
    panel.fill(_tint(COLOR_BG, 226))               # 面板加深，压住底下随机刷新的元件
    screen.blit(panel, (panel_x, panel_y))
    pygame.draw.rect(screen, COLOR_ON, (panel_x, panel_y, panel_w, panel_h), 2)

    inner_w = panel_w - 48
    sec_line = 44
    body_line = 28
    total_h = 0
    for _, rows in TUTORIAL_SECTIONS:
        total_h += sec_line + body_line * len(rows) + 12
    _tut_content_h = total_h
    view_h = panel_h - 32
    _tut_scroll = max(0, min(_tut_scroll, max(0, total_h - view_h)))

    canvas = pygame.Surface((inner_w, max(1, total_h)))
    y = 0
    for sec, rows in TUTORIAL_SECTIONS:
        canvas.blit(MENU_FONT_SEC.render(sec, True, COLOR_ON), (0, y))
        y += sec_line
        for key, text in rows:
            if key and key in ICONS:
                ic = pygame.transform.scale(ICONS[key][0], (22, 22)).copy()
                ic.set_alpha(210)
                canvas.blit(ic, (0, y + 2))
                canvas.blit(MENU_FONT_BODY.render(text, True, COLOR_OFF), (30, y))
            else:
                canvas.blit(MENU_FONT_BODY.render(text, True, COLOR_OFF), (0, y))
            y += body_line
        y += 12

    clip = pygame.Rect(panel_x + 24, panel_y + 16, inner_w, view_h)
    screen.set_clip(clip)
    screen.blit(canvas, (panel_x + 24, panel_y + 16 - int(_tut_scroll)))
    screen.set_clip(None)

    if total_h > view_h:                            # 右侧细滚动条：滑块高度正比于可视占比
        bar_x = panel_x + panel_w - 14
        thumb_h = max(30, int(view_h * view_h / total_h))
        thumb_y = panel_y + 16 + int((panel_h - 32 - thumb_h) *
                                     (_tut_scroll / max(1, total_h - view_h)))
        pygame.draw.rect(screen, COLOR_OFF, (bar_x, thumb_y, 5, thumb_h))


# ── 11b. 性能面板（F12 显隐）───────────────────────────────────────
# 只做只读观测：FPS / 每刻求解耗时 / 元件数 / 撤销栈深，供后续优化定位热点，不改任何状态。
# 每刻求解耗时由主循环在调 step_tick 前后用 perf_counter 量一次，写进 _PERF；FPS 取 clock 现值。
_PERF: Dict[str, float] = {'solve_ms': 0.0}
perf_visible = False
PERF_FONT = pygame.font.SysFont('consolas,menlo,monospace', 14)

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


# ── 12. 主循环 ────────────────────────────────────────────────────
# 一帧四步：收事件 -> 键盘平移 -> 到点就走一刻 -> 渲染并翻页。
# 时序在这里只有一条路径：距上一次推进满 TICK_INTERVAL_S 秒就调 step_tick()，
# 没有模式分支、没有等待单步；这就是“三套模式归为 AUTO”之后剩下的全部调度逻辑。
def main():
    """收事件 -> 键盘平移 -> 按固定节奏推进时序 -> 渲染并翻页，固定 60 FPS。

    时序只有一条路径：每 TICK_INTERVAL_S 秒走一刻（解一次光路 + 推一次延迟队列），
    没有模式分支、没有单步等待。刚编辑完（grid_changed）时把计时拨到点，下一帧立刻
    补走一刻，保证右键放下去画面马上有反应，而刻与刻之间的间隔仍然是固定值。
    """
    global grid_changed, cached_ray_segments, minimap_dirty
    running = True
    last_tick_at = time.perf_counter()
    while running:
        dt = min(clock.tick(60) / 1000.0, MAX_FRAME_DT_S)   # 后台切回来的巨型 dt 要夹住
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif screen_state == 'menu':
                if not handle_menu_event(event):            # 启动界面：按一次 ESC 即退出
                    running = False
            elif screen_state == 'tutorial':
                handle_tutorial_event(event)                # 教学页：仅滚动 / ESC 返回，不碰时序
            elif not handle_event(event):
                running = False
        if screen_state == 'menu':
            draw_menu()
            pygame.display.flip()
            continue                                        # 菜单阶段不推时序，只重绘本屏
        if screen_state == 'tutorial':
            _draw_tutorial()
            pygame.display.flip()
            continue                                        # 教学页同样不推时序，背景动画靠 get_ticks
        pan_camera(dt)
        if delete_held:
            delete_erase_at_cursor()                  # 长按 Delete：光标移到哪删哪
        if place_held:
            place_at_cursor()                         # 长按 Enter：光标移到哪放到哪（同格不重复）
        if grid_changed:                                     # 编辑过：下一帧就补走一刻
            grid_changed = False                             # 把计时拨到“早就该走了”，下一帧立刻补
            last_tick_at = 0.0                               # 右键放下去画面马上有反应，刻长仍是固定值
        if time.perf_counter() - last_tick_at >= TICK_INTERVAL_S:
            _solve_t0 = time.perf_counter()           # 量一次“这一步时序”的墙钟耗时，供性能面板显示
            cached_ray_segments = step_tick()
            _PERF['solve_ms'] = (time.perf_counter() - _solve_t0) * 1000.0
            last_tick_at = time.perf_counter()
            minimap_dirty = True
        draw_scene(cached_ray_segments)
        _draw_game_esc_hint()                         # 第一次按 ESC 时顶部提示：再按一次返回主界面
        if perf_visible:
            _draw_perf_panel()                        # F12 打开：FPS / 求解耗时 / 元件数 / 撤销栈深
        pygame.display.flip()


if __name__ == '__main__':
    main()
    pygame.quit()
