"""
贪吃蛇游戏 - 使用 pygame 实现
功能：玩家选择、游戏记录保存、游戏说明、可调网格大小
控制：方向键 ↑ ↓ ← → 或 W A S D 控制蛇的移动方向
      P 键暂停/继续  |  R 键重新开始
      M 键返回菜单    |  Q 键退出       
窗口可自由缩放，网格会自动适配大小。
"""

import pygame
import random
import sys
import json
import os
from datetime import datetime
from collections import deque

# ============================================================
# 常量配置
# ============================================================

# 网格大小预设（名称, 宽度, 高度）
GRID_PRESETS = [
    ("小 (25×18)", 25, 18),
    ("中 (30×20)", 30, 20),
    ("大 (40×25)", 40, 25),
]
DEFAULT_GRID_INDEX = 1  # 默认选中 "中 (30×20)"

INITIAL_WINDOW_W = 900
INITIAL_WINDOW_H = 600
MIN_CELL_SIZE = 10
FPS = 10

# 颜色
COLOR_BG = (30, 30, 30)
COLOR_GRID = (50, 50, 50)
COLOR_SNAKE_HEAD = (100, 200, 100)
COLOR_SNAKE_BODY = (80, 180, 80)
COLOR_FOOD = (220, 60, 60)
COLOR_WHITE = (220, 220, 220)
COLOR_GRAY = (150, 150, 150)
COLOR_RED = (255, 80, 80)
COLOR_YELLOW = (255, 255, 100)
COLOR_GREEN = (100, 220, 100)
COLOR_CYAN = (100, 200, 220)
COLOR_ORANGE = (255, 180, 60)
COLOR_DIM = (20, 20, 20)
COLOR_INPUT_BG = (50, 50, 60)
COLOR_SELECTED = (80, 160, 80)
COLOR_MENU_OVERLAY = (0, 0, 0, 160)

# 方向向量
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)

# 游戏状态
MENU = "menu"
PLAYER_SELECT = "player_select"
HELP = "help"
RECORDS = "records"
PLAYING = "playing"
GAME_OVER = "game_over"

# 记录文件路径（与脚本同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDS_FILE = os.path.join(SCRIPT_DIR, "snake_records.json")
HELP_FILE = os.path.join(SCRIPT_DIR, "help.txt")

# ============================================================
# 中文字体加载
# ============================================================
_CJK_FONT_NAMES = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Noto Sans CJK TC",
    "AR PL UKai CN",
    "AR PL UMing CN",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "SimHei",
    "Droid Sans Fallback",
]
_FONT_PATH_CACHE: dict[tuple[bool, bool], str | None] = {}


def _load_font(size: int, bold: bool = False) -> pygame.font.Font:
    """加载支持中文的可缩放字体，并按当前字号重新栅格化。"""
    cache_key = (bold, False)
    cached_path = _FONT_PATH_CACHE.get(cache_key)
    if cached_path:
        font = pygame.font.Font(cached_path, size)
        font.set_bold(bold)
        return font

    for bold_lookup in (bold, False):
        for name in _CJK_FONT_NAMES:
            path = pygame.font.match_font(name, bold=bold_lookup)
            if not path:
                continue
            font = pygame.font.Font(path, size)
            font.set_bold(bold)
            test_surf = font.render("中", True, (255, 255, 255))
            if test_surf.get_width() > size * 0.6:
                _FONT_PATH_CACHE[cache_key] = path
                return font

    for name in _CJK_FONT_NAMES:
        font = pygame.font.SysFont(name, size, bold=bold)
        test_surf = font.render("中", True, (255, 255, 255))
        if test_surf.get_width() > size * 0.6:
            _FONT_PATH_CACHE[cache_key] = None
            return font
    return pygame.font.SysFont(None, size, bold=bold)


# ============================================================
# 游戏记录管理
# ============================================================
class RecordManager:
    """管理游戏记录的 JSON 持久化存储"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._records: list[dict] = []
        self._load()

    def _load(self):
        """从 JSON 文件加载记录"""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self._records = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._records = []

    def _save(self):
        """保存记录到 JSON 文件"""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self._records, f, ensure_ascii=False, indent=2)

    def add_record(self, name: str, score: int, duration_seconds: int):
        """添加一条游戏记录并保存"""
        record = {
            "name": name,
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "score": score,
            "duration_seconds": duration_seconds,
        }
        self._records.append(record)
        self._save()

    def get_all_records(self) -> list[dict]:
        """返回所有记录（最新在前）"""
        return list(reversed(self._records))

    def get_top_scores(self, limit: int = 20) -> list[dict]:
        """返回分数最高的 N 条记录"""
        sorted_records = sorted(self._records, key=lambda r: r["score"], reverse=True)
        return sorted_records[:limit]

    def get_unique_players(self) -> list[str]:
        """返回去重的玩家名列表（最近玩的在前）"""
        seen = set()
        players = []
        for r in reversed(self._records):
            name = r["name"]
            if name not in seen:
                seen.add(name)
                players.append(name)
        return players

    @property
    def record_count(self) -> int:
        return len(self._records)


# ============================================================
# 蛇类
# ============================================================
class Snake:
    """管理蛇的状态与移动"""

    def __init__(self, x: int, y: int):
        self.body = deque([(x, y)])
        self.direction = RIGHT
        self.next_direction = RIGHT
        self.growing = False

    @property
    def head(self):
        return self.body[-1]

    def set_direction(self, new_dir: tuple[int, int]):
        # 长度大于 1 时禁止 180 度掉头；长度为 1 时允许任意方向
        if len(self.body) == 1:
            self.next_direction = new_dir
        elif (new_dir[0] + self.direction[0], new_dir[1] + self.direction[1]) != (0, 0):
            self.next_direction = new_dir

    def move(self) -> bool:
        self.direction = self.next_direction
        head_x, head_y = self.head
        new_head = (head_x + self.direction[0], head_y + self.direction[1])

        # 非增长时尾部即将被弹出，应从碰撞检测中排除
        if self.growing:
            if new_head in self.body:
                return False
        else:
            # body[0] 是尾部，本帧会被弹出，不应算作碰撞
            if new_head in self.body and new_head != self.body[0]:
                return False

        self.body.append(new_head)
        if self.growing:
            self.growing = False
        else:
            self.body.popleft()
        return True

    def grow(self):
        self.growing = True

    def draw(self, surface: pygame.Surface, cell_size: int,
             offset_x: int, offset_y: int):
        for i, segment in enumerate(self.body):
            x = offset_x + segment[0] * cell_size
            y = offset_y + segment[1] * cell_size
            rect = pygame.Rect(x, y, cell_size, cell_size)
            if i == len(self.body) - 1:
                pygame.draw.rect(surface, COLOR_SNAKE_HEAD, rect)
                pygame.draw.rect(surface, (150, 230, 150), rect,
                                 max(1, cell_size // 12))
                self._draw_eyes(surface, segment, cell_size, offset_x, offset_y)
            else:
                pygame.draw.rect(surface, COLOR_SNAKE_BODY, rect)
                pygame.draw.rect(surface, (120, 200, 120), rect,
                                 max(1, cell_size // 20))

    def _draw_eyes(self, surface, head_pos, cell_size, offset_x, offset_y):
        hx = offset_x + head_pos[0] * cell_size
        hy = offset_y + head_pos[1] * cell_size
        eye_r = max(1, cell_size // 8)
        q = cell_size // 4
        if self.direction == RIGHT:
            pts = [(hx + 3 * q, hy + q), (hx + 3 * q, hy + 3 * q)]
        elif self.direction == LEFT:
            pts = [(hx + q, hy + q), (hx + q, hy + 3 * q)]
        elif self.direction == UP:
            pts = [(hx + q, hy + q), (hx + 3 * q, hy + q)]
        else:
            pts = [(hx + q, hy + 3 * q), (hx + 3 * q, hy + 3 * q)]
        for p in pts:
            pygame.draw.circle(surface, (255, 255, 255), p, eye_r)


# ============================================================
# 食物类（不在边界生成）
# ============================================================
class Food:
    def __init__(self, grid_w: int, grid_h: int):
        self.grid_w = grid_w
        self.grid_h = grid_h
        self.position = (0, 0)

    def respawn(self, snake_body: set):
        """在非蛇身且非边界的位置随机生成食物"""
        while True:
            # 排除边界 (x=0, x=grid_w-1, y=0, y=grid_h-1)
            x = random.randint(1, self.grid_w - 2)
            y = random.randint(1, self.grid_h - 2)
            if (x, y) not in snake_body:
                self.position = (x, y)
                break

    def update_grid(self, grid_w: int, grid_h: int):
        """更新网格尺寸（可能使食物位置不合法，需要重新生成）"""
        self.grid_w = grid_w
        self.grid_h = grid_h

    def draw(self, surface: pygame.Surface, cell_size: int,
             offset_x: int, offset_y: int):
        cx = offset_x + self.position[0] * cell_size + cell_size // 2
        cy = offset_y + self.position[1] * cell_size + cell_size // 2
        radius = max(2, cell_size // 2 - 2)
        if radius > 3:
            pygame.draw.circle(surface, (255, 100, 100), (cx, cy), radius + 2, 1)
        pygame.draw.circle(surface, COLOR_FOOD, (cx, cy), radius)
        hl_r = max(1, radius // 3)
        if hl_r > 0:
            pygame.draw.circle(surface, (255, 150, 150),
                               (cx - radius // 3, cy - radius // 3), hl_r)


# ============================================================
# 按钮/菜单项辅助
# ============================================================
class MenuButton:
    """菜单按钮"""
    def __init__(self, text: str, y: float, font: pygame.font.Font,
                 color: tuple = COLOR_WHITE, hover_color: tuple = COLOR_GREEN):
        self.text = text
        self.y_ratio = y  # 屏幕高度的比例
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.hovered = False
        self.rect = pygame.Rect(0, 0, 0, 0)

    def update(self, window_w: int, window_h: int, mouse_pos: tuple[int, int]):
        """更新按钮位置和 hover 状态"""
        surf = self.font.render(self.text, True, (255, 255, 255))
        self.rect = surf.get_rect(center=(window_w // 2, int(window_h * self.y_ratio)))
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surface: pygame.Surface):
        color = self.hover_color if self.hovered else self.color
        text_surf = self.font.render(self.text, True, color)
        surface.blit(text_surf, self.rect)


# ============================================================
# 主游戏类
# ============================================================
class Game:
    """游戏主类，管理状态机、渲染和事件循环"""

    def __init__(self):
        pygame.init()
        self.records = RecordManager(RECORDS_FILE)
        self.window_w = INITIAL_WINDOW_W
        self.window_h = INITIAL_WINDOW_H
        self.screen = pygame.display.set_mode(
            (self.window_w, self.window_h), pygame.RESIZABLE
        )
        pygame.display.set_caption("贪吃蛇")
        self.clock = pygame.time.Clock()

        # 自适应字体缓存（窗口缩放时刷新）
        self._adaptive_fonts: dict[str, pygame.font.Font] = {}
        self._font_sizes: dict[str, int] = {}
        self._font_bold: dict[str, bool] = {}
        self._last_font_window_w = 0
        self._last_font_window_h = 0
        self._update_adaptive_fonts()

        # 网格配置
        self.grid_index = DEFAULT_GRID_INDEX
        _, self.grid_w, self.grid_h = GRID_PRESETS[self.grid_index]

        # 游戏运行时变量
        self.player_name = ""
        self.state = MENU
        self.snake: Snake = None
        self.food: Food = None
        self.score = 0
        self.paused = False
        self.frame_count = 0
        self.start_ticks = 0  # 游戏开始的 pygame ticks
        self.pause_started_ticks = 0
        self.total_paused_ticks = 0

        # 菜单/UI 状态
        self._menu_selection = 0        # 菜单当前选中项索引
        self._input_text = ""           # 玩家选择时的输入缓冲区
        self._cursor_visible = True     # 光标闪烁
        self._cursor_timer = 0
        self._recent_players: list[str] = []
        self._select_index = 0          # 玩家选择中的列表索引
        self._help_sections: list[dict] = []
        self._help_scroll_y = 0      # 游戏说明的像素级滚动偏移
        self._records_scroll = 0        # 记录查看的滚动位置
        self._menu_buttons: list[MenuButton] = []
        self._pause_button_rect = pygame.Rect(0, 0, 0, 0)

    # ---- 网格配置 ----
    def _apply_grid_preset(self):
        _, self.grid_w, self.grid_h = GRID_PRESETS[self.grid_index]

    def cycle_grid_preset(self, delta: int):
        """切换网格预设"""
        self.grid_index = (self.grid_index + delta) % len(GRID_PRESETS)

    @property
    def cell_size(self) -> int:
        w_cell = self.window_w // self.grid_w
        h_cell = self.window_h // self.grid_h
        return max(MIN_CELL_SIZE, min(w_cell, h_cell))

    @property
    def grid_offset(self) -> tuple[int, int]:
        grid_px_w = self.cell_size * self.grid_w
        grid_px_h = self.cell_size * self.grid_h
        return ((self.window_w - grid_px_w) // 2,
                (self.window_h - grid_px_h) // 2)

    @property
    def elapsed_seconds(self) -> int:
        """返回当前游戏已进行的秒数"""
        if self.start_ticks == 0:
            return 0
        now = self.pause_started_ticks if self.paused else pygame.time.get_ticks()
        active_ticks = max(0, now - self.start_ticks - self.total_paused_ticks)
        return active_ticks // 1000

    def _format_duration(self, seconds: int) -> str:
        """格式化秒数为 mm:ss"""
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    # ---- 游戏状态切换 ----
    def _start_game(self):
        """切换到游戏状态，初始化蛇和食物"""
        _, self.grid_w, self.grid_h = GRID_PRESETS[self.grid_index]
        cx = self.grid_w // 2
        cy = self.grid_h // 2
        self.snake = Snake(cx, cy)
        self.food = Food(self.grid_w, self.grid_h)
        self.food.respawn(set(self.snake.body))
        self.score = 0
        self.paused = False
        self.frame_count = 0
        self.state = PLAYING
        self.start_ticks = pygame.time.get_ticks()
        self.pause_started_ticks = 0
        self.total_paused_ticks = 0
        self._pause_button_rect = pygame.Rect(0, 0, 0, 0)

    def _go_menu(self):
        """返回菜单"""
        self.state = MENU
        self._menu_selection = 0
        self._update_menu_buttons()

    def _go_player_select(self):
        """进入玩家选择界面"""
        self.state = PLAYER_SELECT
        self._input_text = self.player_name
        self._recent_players = self.records.get_unique_players()
        self._select_index = -1  # -1 表示焦点在输入框
        self._cursor_timer = 0
        self._cursor_visible = True

    def _go_help(self):
        """进入游戏说明界面（将 help.txt 解析为结构化段落）"""
        self.state = HELP
        self._help_scroll_y = 0
        try:
            with open(HELP_FILE, "r", encoding="utf-8") as f:
                raw_lines = f.read().splitlines()
        except FileNotFoundError:
            raw_lines = ["【错误】", "游戏说明文件未找到。"]

        # 解析为段落：每个段落有 type 和 lines
        # type: "title"(【xxx】), "body"(普通行), "keyval"(key ... val), "blank"
        sections: list[dict] = []  # {type, lines, title_text?}
        cur_type = "body"
        cur_lines: list[str] = []
        cur_title = ""

        def flush():
            nonlocal cur_type, cur_lines, cur_title
            if cur_lines:
                sections.append({
                    "type": cur_type,
                    "lines": cur_lines.copy(),
                    "title": cur_title,
                })
                cur_lines.clear()
            cur_title = ""
            cur_type = "body"

        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                flush()
                cur_type = "blank"
                cur_lines.append("")
                flush()
                continue

            # 检测段落标题 【xxx】
            if stripped.startswith("【") and "】" in stripped:
                flush()
                cur_type = "title"
                cur_title = stripped
                cur_lines.append(stripped)
                flush()
                continue

            if stripped.startswith("·") or stripped.startswith("-"):
                cur_type = "body"
                cur_lines.append(stripped)
            # 检测键值对（含连续空格分隔，如 "↑ / W  向上移动"）
            elif "  " in stripped:
                cur_type = "keyval"
                cur_lines.append(stripped)
            # 子标题：单行无空格短词，后跟 keyval 行（如 "方向控制"）
            elif " " not in stripped and len(stripped) <= 8:
                flush()
                cur_type = "keyval"
                cur_lines.append(stripped)
            else:
                # 续行（上一行的延续）
                if cur_type == "body" and cur_lines:
                    cur_lines[-1] = cur_lines[-1] + stripped
                else:
                    cur_type = "body"
                    cur_lines.append(stripped)

        flush()
        self._help_sections = sections

    def _go_records(self):
        """进入查看记录界面"""
        self.state = RECORDS
        self._records_scroll = 0

    def _update_menu_buttons(self):
        """重建菜单按钮列表"""
        name = self.player_name if self.player_name else "游客"
        self._menu_buttons = [
            MenuButton(f"玩家选择（当前：{name}）", 0.24, self.font_lg),
            MenuButton("开始游戏", 0.33, self.font_lg),
            MenuButton("查看记录", 0.42, self.font_lg),
            MenuButton("游戏说明", 0.51, self.font_lg),
            MenuButton(f"网格设置（{GRID_PRESETS[self.grid_index][0]}）",
                       0.60, self.font_lg),
        ]
        self._layout_menu_buttons()

    def _layout_menu_buttons(self, mouse_pos: tuple[int, int] | None = None):
        """根据当前窗口和鼠标位置刷新菜单按钮矩形。"""
        if mouse_pos is None:
            mouse_pos = (-1, -1)
        for btn in self._menu_buttons:
            btn.update(self.window_w, self.window_h, mouse_pos)

    # ================================================================
    # 事件处理
    # ================================================================
    def handle_events(self) -> bool:
        """返回 False 表示退出程序"""
        mouse_pos = pygame.mouse.get_pos()

        # 先更新按钮 hover 状态（确保点击事件拿到正确的 hover）
        if self.state == MENU:
            self._layout_menu_buttons(mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.VIDEORESIZE:
                self.window_w = max(1, event.w)
                self.window_h = max(1, event.h)
                self.screen = pygame.display.set_mode(
                    (self.window_w, self.window_h), pygame.RESIZABLE
                )
                self._update_adaptive_fonts()
                self._update_menu_buttons()

            # ---- 按状态分发 ----
            if self.state == MENU:
                if not self._handle_menu_events(event, mouse_pos):
                    return False
            elif self.state == PLAYER_SELECT:
                if not self._handle_player_select_events(event):
                    return False
            elif self.state == HELP:
                if not self._handle_help_events(event):
                    return False
            elif self.state == RECORDS:
                if not self._handle_records_events(event):
                    return False
            elif self.state == PLAYING:
                if not self._handle_playing_events(event):
                    return False
            elif self.state == GAME_OVER:
                if not self._handle_gameover_events(event):
                    return False

        return True

    def _handle_menu_events(self, event, mouse_pos) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                return False
            elif event.key == pygame.K_UP:
                self._menu_selection = (self._menu_selection - 1) % 5
            elif event.key == pygame.K_DOWN:
                self._menu_selection = (self._menu_selection + 1) % 5
            elif event.key == pygame.K_LEFT:
                if self._menu_selection == 4:
                    self.cycle_grid_preset(-1)
                    self._update_menu_buttons()
            elif event.key == pygame.K_RIGHT:
                if self._menu_selection == 4:
                    self.cycle_grid_preset(1)
                    self._update_menu_buttons()
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._execute_menu_action(self._menu_selection)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, btn in enumerate(self._menu_buttons):
                if btn.hovered:
                    self._execute_menu_action(i)
                    break
        return True

    def _execute_menu_action(self, index: int):
        if index == 0:
            self._go_player_select()
        elif index == 1:
            self._start_game()
        elif index == 2:
            self._go_records()
        elif index == 3:
            self._go_help()
        elif index == 4:
            self.cycle_grid_preset(1)
            self._update_menu_buttons()

    def _handle_player_select_events(self, event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._go_menu()
            elif event.key == pygame.K_RETURN:
                self._confirm_player_selection()
            elif event.key == pygame.K_TAB:
                # 切换焦点：输入框 <-> 玩家列表
                if self._select_index == -1 and self._recent_players:
                    self._select_index = 0
                else:
                    self._select_index = -1
            elif event.key == pygame.K_UP:
                if self._select_index > 0:
                    self._select_index -= 1
                elif self._select_index == 0:
                    self._select_index = -1
            elif event.key == pygame.K_DOWN:
                if self._select_index == -1 and self._recent_players:
                    self._select_index = 0
                elif self._select_index >= 0 and self._select_index < len(self._recent_players) - 1:
                    self._select_index += 1
            elif self._select_index == -1:
                # 在输入框中键入
                if event.key == pygame.K_BACKSPACE:
                    self._input_text = self._input_text[:-1]
                elif len(self._input_text) < 12 and event.unicode.isprintable():
                    self._input_text += event.unicode
            elif self._select_index >= 0 and event.key == pygame.K_RETURN:
                self._confirm_player_selection()
        return True

    def _confirm_player_selection(self):
        if self._select_index >= 0 and self._select_index < len(self._recent_players):
            self.player_name = self._recent_players[self._select_index]
        elif self._input_text.strip():
            self.player_name = self._input_text.strip()
        else:
            self.player_name = "游客"
        self._go_menu()
        self._update_menu_buttons()

    def _handle_help_events(self, event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_b):
                self._go_menu()
            elif event.key == pygame.K_DOWN:
                self._help_scroll_y += 40
            elif event.key == pygame.K_UP:
                self._help_scroll_y = max(0, self._help_scroll_y - 40)
            elif event.key == pygame.K_PAGEDOWN:
                self._help_scroll_y += 250
            elif event.key == pygame.K_PAGEUP:
                self._help_scroll_y = max(0, self._help_scroll_y - 250)
        elif event.type == pygame.MOUSEWHEEL:
            self._help_scroll_y = max(0, self._help_scroll_y - event.y * 35)
        return True

    def _handle_records_events(self, event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_b):
                self._go_menu()
            elif event.key == pygame.K_DOWN:
                self._records_scroll += 1
            elif event.key == pygame.K_UP:
                self._records_scroll = max(0, self._records_scroll - 1)
            elif event.key == pygame.K_PAGEUP:
                self._records_scroll = max(0, self._records_scroll - 10)
            elif event.key == pygame.K_PAGEDOWN:
                self._records_scroll += 10
        elif event.type == pygame.MOUSEWHEEL:
            self._records_scroll = max(0, self._records_scroll - event.y)
        return True

    def _handle_playing_events(self, event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                return False
            elif event.key == pygame.K_p:
                self._toggle_pause()
            elif event.key in (pygame.K_UP, pygame.K_w):
                self._try_set_direction(UP)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._try_set_direction(DOWN)
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._try_set_direction(LEFT)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._try_set_direction(RIGHT)
            elif event.key == pygame.K_r:
                self._start_game()
            elif event.key == pygame.K_m:
                self._go_menu()
                self._update_menu_buttons()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._pause_button_rect.collidepoint(event.pos):
                self._toggle_pause()
        return True

    def _handle_gameover_events(self, event) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                return False
            elif event.key == pygame.K_r:
                self._start_game()
            elif event.key == pygame.K_m:
                self._go_menu()
                self._update_menu_buttons()
        return True

    def _try_set_direction(self, new_dir):
        if self.state == PLAYING and not self.paused:
            self.snake.set_direction(new_dir)

    def _toggle_pause(self):
        """切换暂停状态，并从游戏时长中扣除暂停时间。"""
        if self.state != PLAYING:
            return
        now = pygame.time.get_ticks()
        if self.paused:
            if self.pause_started_ticks:
                self.total_paused_ticks += now - self.pause_started_ticks
            self.pause_started_ticks = 0
            self.paused = False
        else:
            self.pause_started_ticks = now
            self.paused = True

    # ================================================================
    # 游戏逻辑更新
    # ================================================================
    def update(self):
        if self.state != PLAYING:
            return

        # 光标动画（在玩家选择界面也用到，这里仅在 playing 时处理光标重置）
        if self.paused:
            return

        self.frame_count += 1

        if not self.snake.move():
            self._on_game_over()
            return

        if self.snake.head == self.food.position:
            self.snake.grow()
            self.score += 10
            self.food.respawn(set(self.snake.body))

        head_x, head_y = self.snake.head
        if head_x < 0 or head_x >= self.grid_w or head_y < 0 or head_y >= self.grid_h:
            self._on_game_over()

    def _on_game_over(self):
        """游戏结束：保存记录，切换到 GAME_OVER 状态"""
        self.state = GAME_OVER
        name = self.player_name if self.player_name else "游客"
        self.records.add_record(name, self.score, self.elapsed_seconds)

    # ================================================================
    # 渲染
    # ================================================================
    def draw(self):
        self.screen.fill(COLOR_BG)

        # 所有状态下都绘制网格背景
        self._draw_grid_background()

        if self.state == MENU:
            self._draw_menu()
            self._update_cursor()
        elif self.state == PLAYER_SELECT:
            self._draw_player_select()
            self._update_cursor()
        elif self.state == HELP:
            self._draw_help()
        elif self.state == RECORDS:
            self._draw_records()
        elif self.state == PLAYING:
            self._draw_playing()
        elif self.state == GAME_OVER:
            self._draw_playing()
            self._draw_game_over()

        pygame.display.flip()

    def _draw_grid_background(self):
        """绘制网格（作为背景）"""
        cs = self.cell_size
        ox, oy = self.grid_offset
        grid_px_w = cs * self.grid_w
        grid_px_h = cs * self.grid_h

        # 边框
        pygame.draw.rect(self.screen, COLOR_GRID,
                         (ox - 1, oy - 1, grid_px_w + 2, grid_px_h + 2), 1)

        # 网格线
        if cs >= 15:
            for col in range(self.grid_w + 1):
                x = ox + col * cs
                pygame.draw.line(self.screen, COLOR_GRID, (x, oy), (x, oy + grid_px_h))
            for row in range(self.grid_h + 1):
                y = oy + row * cs
                pygame.draw.line(self.screen, COLOR_GRID, (ox, y), (ox + grid_px_w, y))

    def _draw_semi_transparent_overlay(self):
        """绘制半透明遮罩"""
        overlay = pygame.Surface((self.window_w, self.window_h), pygame.SRCALPHA)
        overlay.fill((10, 10, 20, 180))
        self.screen.blit(overlay, (0, 0))

    # ---- 菜单 ----
    def _draw_menu(self):
        self._draw_semi_transparent_overlay()
        self._layout_menu_buttons(pygame.mouse.get_pos())

        # 标题
        title = self._render_fit("贪吃蛇", "huge", COLOR_GREEN, self.window_w - 24)
        title_rect = title.get_rect(center=(self.window_w // 2, int(self.window_h * 0.12)))
        self.screen.blit(title, title_rect)

        # 副标题（自适应字体）
        sub = self._render_fit("经典街机游戏", "sub", COLOR_GRAY, self.window_w - 24)
        sub_rect = sub.get_rect(center=(self.window_w // 2, int(self.window_h * 0.19)))
        self.screen.blit(sub, sub_rect)

        # 按钮
        for i, btn in enumerate(self._menu_buttons):
            # 高亮当前选中项（键盘导航或鼠标悬浮）
            if self._menu_selection == i:
                btn.hovered = True
            btn.draw(self.screen)

        # 底部提示（自适应字体）
        hint = self._render_fit(
            "↑↓ 选择   Enter 确认   ←→ 调网格   Q 退出",
            "hint", COLOR_GRAY, self.window_w - 24
        )
        hint_rect = hint.get_rect(
            center=(self.window_w // 2, self.window_h - hint.get_height())
        )
        self.screen.blit(hint, hint_rect)

    # ---- 玩家选择 ----
    def _draw_player_select(self):
        self._draw_semi_transparent_overlay()

        margin_x = max(12, min(40, int(self.window_w * 0.06)))
        form_w = max(20, min(560, self.window_w - margin_x * 2))
        form_left = (self.window_w - form_w) // 2
        title_y = max(self.font_lg.get_height(), int(self.window_h * 0.10))

        title = self.font_lg.render("玩家选择", True, COLOR_CYAN)
        title_rect = title.get_rect(center=(self.window_w // 2, title_y))
        self.screen.blit(title, title_rect)

        # 输入框
        input_label = self.font_md.render("输入玩家名：", True, COLOR_WHITE)
        label_y = title_y + self.font_lg.get_height() + max(10, int(self.window_h * 0.03))
        self.screen.blit(input_label, (form_left, label_y))

        input_x = form_left
        input_y = label_y + input_label.get_height() + 6
        input_w = form_w
        input_h = max(32, self.font_md.get_height() + 12)
        # 输入框背景
        pygame.draw.rect(self.screen, COLOR_INPUT_BG,
                         (input_x, input_y, input_w, input_h))
        pygame.draw.rect(self.screen,
                         COLOR_CYAN if self._select_index == -1 else COLOR_GRAY,
                         (input_x, input_y, input_w, input_h), 2)

        # 输入框文字
        display_text = self._input_text
        if self._select_index == -1 and self._cursor_visible:
            display_text = self._input_text + "│"
        elif self._select_index == -1:
            display_text = self._input_text + " "

        text_surf = self._render_fit(display_text, "md", COLOR_WHITE, input_w - 16)
        text_y = input_y + (input_h - text_surf.get_height()) // 2
        self.screen.blit(text_surf, (input_x + 8, text_y))

        # 最近玩家列表
        list_y = input_y + input_h + max(14, int(self.window_h * 0.035))
        list_label = self.font_md.render("或选择已有玩家：", True, COLOR_WHITE)
        self.screen.blit(list_label, (form_left, list_y))

        hint_font = self._adaptive_fonts["hint"]
        bottom_limit = self.window_h - hint_font.get_height() * 2 - 10
        row_h = max(self.font_md.get_height() + 8, int(self.window_h * 0.055))
        first_row_y = list_y + list_label.get_height() + 8
        visible_players = max(0, min(10, (bottom_limit - first_row_y) // row_h))
        if self._recent_players:
            for i, name in enumerate(self._recent_players[:visible_players]):
                y = first_row_y + i * row_h
                color = COLOR_SELECTED if i == self._select_index else COLOR_WHITE
                prefix = ">> " if i == self._select_index else "   "
                line = self._render_fit(f"{prefix}{name}", "md", color, form_w)
                self.screen.blit(line, (form_left, y))
        else:
            no_data = self._render_fit("（暂无历史玩家）", "hint", COLOR_GRAY, form_w)
            self.screen.blit(no_data, (form_left, first_row_y))

        # 底部提示（自适应字体）
        hint = self._render_fit(
            "输入名称后按 Enter   |   Tab 切换焦点   |   Esc 返回",
            "hint", COLOR_GRAY, self.window_w - 24
        )
        hint_rect = hint.get_rect(
            center=(self.window_w // 2, self.window_h - hint.get_height())
        )
        self.screen.blit(hint, hint_rect)

    # ---- 游戏说明 ----
    def _draw_help(self):
        self._draw_semi_transparent_overlay()

        title_font = self._adaptive_fonts["help_title"]
        body_font = self._adaptive_fonts["help_body"]
        hint_font = self._adaptive_fonts["hint"]

        # 标题栏
        title = self._render_fit("游戏说明", "help_title", COLOR_CYAN, self.window_w - 24)
        title_h = title_font.get_height() + 16
        title_rect = title.get_rect(center=(self.window_w // 2, title_h // 2))
        self.screen.blit(title, title_rect)

        # 内容卡片（居中、宽度适中）
        card_margin = min(max(8, int(self.window_w * 0.10)), 80,
                          max(2, self.window_w // 4))
        card_left = card_margin
        card_right = self.window_w - card_margin
        card_width = max(1, card_right - card_left)
        card_center = (card_left + card_right) // 2
        content_top = title_h + 10
        content_bottom = self.window_h - hint_font.get_height() - 20

        gap = int(body_font.get_height() * 0.6)
        sec_gap = int(body_font.get_height() * 1.3)
        line_h = body_font.get_height() + gap
        tbl_line_h = int(body_font.get_height() * 2.0)  # 表格行高加倍（键+说明双行）

        # 表格列布局参数
        tbl_pad = max(6, min(12, int(card_width * 0.025)))  # 表格内边距
        tbl_left = card_left + 16
        tbl_right = card_right - 16
        tbl_w = max(1, tbl_right - tbl_left)
        col_gap = 8
        col_w = max(1, (tbl_w - col_gap * 2) // 3)   # 等分为三列

        # 收集各 keyval 段落为独立分组
        keyval_groups = []  # [[(type, key, val), ...], ...]
        for sec in self._help_sections:
            if sec["type"] == "keyval":
                group = []
                for raw in sec["lines"]:
                    stripped = raw.strip()
                    # 用连续空格分隔键和值
                    if "  " in stripped:
                        idx = stripped.index("  ")
                        key = stripped[:idx].rstrip()
                        val = stripped[idx:].lstrip()
                        group.append(("key", key, val))
                    else:
                        group.append(("sub", stripped, ""))
                keyval_groups.append(group)
        # 只取前 3 组（方向控制、功能控制、菜单操作）
        keyval_groups = keyval_groups[:3]

        # 计算表格行数（取各组行数最大值，含标题行）
        tbl_rows = max((len(g) for g in keyval_groups), default=0) if keyval_groups else 0
        tbl_height = tbl_rows * tbl_line_h + tbl_pad * 2 + (tbl_rows - 1) * 1 + 4 if tbl_rows > 0 else 0

        # 预计算总高度（keyval 全部合并为一张三列表格）
        total_h = 0
        for sec in self._help_sections:
            if sec["type"] == "title":
                total_h += line_h + sec_gap
            elif sec["type"] == "keyval":
                pass  # 归入统一表格，后面统一加
            elif sec["type"] == "body":
                total_h += len(sec["lines"]) * line_h + sec_gap // 2
            elif sec["type"] == "blank":
                total_h += line_h // 2
        # 追加三列表格的总高度（放在所有 keyval 内容之后）
        first_keyval_seen = False
        for sec in self._help_sections:
            if sec["type"] == "keyval" and not first_keyval_seen:
                first_keyval_seen = True
                total_h += tbl_height + 8
                break

        content_h = max(1, content_bottom - content_top)
        max_scroll = max(0, total_h - content_h)
        self._help_scroll_y = max(0, min(self._help_scroll_y, max_scroll))

        # 卡片背景
        card_rect = pygame.Rect(card_left, content_top, card_width, content_h)
        pygame.draw.rect(self.screen, (18, 22, 38), card_rect)
        pygame.draw.rect(self.screen, (60, 65, 80), card_rect, 1)

        self.screen.set_clip(card_rect)
        y = content_top + 12 - self._help_scroll_y

        table_drawn = False  # 三列表格只画一次
        for sec in self._help_sections:
            if sec["type"] == "blank":
                y += line_h // 2
                continue
            if sec["type"] == "keyval":
                if table_drawn:
                    continue  # 已在第一次 keyval 处绘制三列表格
                table_drawn = True
                if not keyval_groups:
                    continue

                tbl_top = y + tbl_pad // 2
                tbl_bottom = tbl_top + tbl_height

                # 表格外框 + 背景
                tbl_bg = pygame.Rect(tbl_left, tbl_top, tbl_w, tbl_height)
                pygame.draw.rect(self.screen, (22, 26, 42), tbl_bg)
                pygame.draw.rect(self.screen, (70, 75, 90), tbl_bg, 1)

                # 垂直列分隔线
                for ci in range(1, len(keyval_groups)):
                    vx = tbl_left + ci * (col_w + col_gap) - col_gap // 2
                    pygame.draw.line(self.screen, (55, 60, 70),
                                     (vx, tbl_top + tbl_pad // 2),
                                     (vx, tbl_bottom - tbl_pad // 2), 1)

                # 每列独立渲染
                for ci, group in enumerate(keyval_groups):
                    col_x = tbl_left + ci * (col_w + col_gap) + col_gap // 2
                    row_y = tbl_top + tbl_pad // 2

                    for ri, (rtype, k, v) in enumerate(group):
                        row_rect = pygame.Rect(col_x, row_y, col_w, tbl_line_h)

                        if rtype == "sub":
                            # 列标题行：深色背景
                            pygame.draw.rect(self.screen, (35, 40, 60), row_rect)
                            sub_text = self._render_fit(k, "help_body", COLOR_CYAN,
                                                        max(10, col_w - 8))
                            sub_rect = sub_text.get_rect(center=row_rect.center)
                            self.screen.blit(sub_text, sub_rect)
                        else:
                            # 数据行：键（上）+ 说明（下）双行显示
                            if ri % 2 == 0:
                                pygame.draw.rect(self.screen, (28, 32, 50), row_rect)

                            # 上半行：按键名（青色）
                            key_text = self._render_fit(k, "help_body", COLOR_CYAN,
                                                        max(10, col_w - 8))
                            k_rect = key_text.get_rect(
                                center=(row_rect.centerx, row_y + tbl_line_h * 0.35))
                            self.screen.blit(key_text, k_rect)

                            # 下半行：功能说明（白色，小字）
                            if v:
                                desc_text = self._render_fit(v, "hint", COLOR_WHITE,
                                                             max(10, col_w - 8))
                                d_rect = desc_text.get_rect(
                                    center=(row_rect.centerx, row_y + tbl_line_h * 0.72))
                                self.screen.blit(desc_text, d_rect)

                        row_y += tbl_line_h

                # 行间分隔线（全表统一）
                row_y = tbl_top + tbl_pad // 2
                for ri in range(tbl_rows - 1):
                    row_y += tbl_line_h
                    pygame.draw.line(self.screen, (50, 55, 65),
                                     (tbl_left + 8, row_y),
                                     (tbl_right - 8, row_y), 1)

                y = tbl_bottom + 8
                continue

            if sec["type"] == "title":
                # 段落标题：居中，两侧装饰线
                raw = sec["lines"][0]
                display = raw.strip()
                text = self._render_fit(display, "help_body", COLOR_ORANGE,
                                        max(20, card_width - 32))
                t_rect = text.get_rect(center=(card_center, y + line_h // 2))
                left_line_end = t_rect.left - 12
                if left_line_end > card_left + 20:
                    pygame.draw.line(self.screen, COLOR_ORANGE,
                                     (card_left + 20, t_rect.centery),
                                     (left_line_end, t_rect.centery), 1)
                right_line_start = t_rect.right + 12
                if right_line_start < card_right - 20:
                    pygame.draw.line(self.screen, COLOR_ORANGE,
                                     (right_line_start, t_rect.centery),
                                     (card_right - 20, t_rect.centery), 1)
                self.screen.blit(text, t_rect)
                y += line_h + sec_gap

            elif sec["type"] == "body":
                for raw in sec["lines"]:
                    display = raw.strip()
                    if display.startswith("·") or display.startswith("-"):
                        color = COLOR_WHITE
                    else:
                        color = COLOR_WHITE

                    text = self._render_fit(display, "help_body", color,
                                            max(20, card_width - 32))
                    t_rect = text.get_rect(center=(card_center, y + line_h // 2))
                    self.screen.blit(text, t_rect)
                    y += line_h
                y += sec_gap // 2

        self.screen.set_clip(None)

        # 滚动条
        if max_scroll > 0:
            bar_h = max(30, int(content_h * content_h / total_h))
            bar_y = content_top + int(self._help_scroll_y / max_scroll * (content_h - bar_h))
            bar_rect = pygame.Rect(card_right + 4, bar_y, 5, bar_h)
            pygame.draw.rect(self.screen, (100, 100, 120), bar_rect, border_radius=2)

        # 底部提示
        scroll_msg = "鼠标滚轮 / ↑↓ PgUp PgDn 滚动    B / Esc 返回"
        hint = self._render_fit(scroll_msg, "hint", COLOR_GRAY, self.window_w - 24)
        hint_rect = hint.get_rect(
            center=(self.window_w // 2, self.window_h - hint.get_height())
        )
        self.screen.blit(hint, hint_rect)

    # ---- 查看记录 ----
    def _draw_records(self):
        self._draw_semi_transparent_overlay()

        title_font = self._adaptive_fonts["help_title"]
        body_font = self._adaptive_fonts["help_body"]
        hint_font = self._adaptive_fonts["hint"]

        # 标题
        title = self._render_fit("历史记录", "help_title", COLOR_CYAN, self.window_w - 24)
        title_rect = title.get_rect(center=(self.window_w // 2, title_font.get_height()))
        self.screen.blit(title, title_rect)

        all_records = self.records.get_top_scores(200)

        if not all_records:
            msg = self._render_fit("暂无游戏记录", "help_body", COLOR_GRAY,
                                   self.window_w - 24)
            msg_rect = msg.get_rect(center=(self.window_w // 2, self.window_h // 2))
            self.screen.blit(msg, msg_rect)
        else:
            # 列坐标（占窗口宽度的比例 + 对齐方式）
            # 居中左对齐布局：所有列构成一个整体块居中
            cols = [
                ("排名", 0.08, "left"),     # 排名
                ("玩家", 0.24, "left"),     # 玩家名
                ("分数", 0.50, "center"),   # 分数
                ("日期", 0.65, "left"),     # 日期
                ("时长", 0.88, "center"),   # 时长
            ]

            # 计算表头各列像素 x 坐标
            header_x = []
            for _, ratio, align in cols:
                header_x.append(int(self.window_w * ratio))
            col_limits = [
                max(28, int(self.window_w * 0.12)),
                max(40, int(self.window_w * 0.22)),
                max(34, int(self.window_w * 0.10)),
                max(70, int(self.window_w * 0.20)),
                max(42, int(self.window_w * 0.10)),
            ]

            # 表头背景
            header_y = title_font.get_height() + 32
            header_h = int(body_font.get_height() * 1.5)
            header_bg = pygame.Rect(
                int(self.window_w * 0.05), header_y,
                int(self.window_w * 0.90), header_h
            )
            pygame.draw.rect(self.screen, (40, 50, 70), header_bg)
            pygame.draw.rect(self.screen, COLOR_GRAY, header_bg, 1)

            # 表头文字
            for (label, ratio, align), px, limit in zip(cols, header_x, col_limits):
                text = self._render_fit(label, "help_body", COLOR_CYAN, limit)
                if align == "center":
                    t_rect = text.get_rect(center=(px, header_y + header_h // 2))
                else:
                    t_rect = text.get_rect(midleft=(px, header_y + header_h // 2))
                self.screen.blit(text, t_rect)

            # 分隔线
            sep_y = header_y + header_h

            # 可用行数
            line_h = int(body_font.get_height() * 1.5)
            table_top = sep_y + 4
            bottom_margin = hint_font.get_height() + 30
            visible_rows = max(1, (self.window_h - table_top - bottom_margin) // line_h)
            max_scroll = max(0, len(all_records) - visible_rows)
            self._records_scroll = max(0, min(self._records_scroll, max_scroll))

            # 数据行
            for i, rec in enumerate(all_records):
                idx = i - self._records_scroll
                if idx < 0 or idx >= visible_rows:
                    continue

                row_y = table_top + idx * line_h
                row_rect = pygame.Rect(
                    int(self.window_w * 0.05), row_y,
                    int(self.window_w * 0.90), line_h
                )

                # 隔行底色
                if i % 2 == 0:
                    pygame.draw.rect(self.screen, (30, 35, 50), row_rect)
                else:
                    pygame.draw.rect(self.screen, (22, 25, 38), row_rect)

                # 前三名高亮
                rank = i + 1
                if rank == 1:
                    rank_color = COLOR_ORANGE
                elif rank == 2:
                    rank_color = COLOR_GRAY
                elif rank == 3:
                    rank_color = (180, 140, 100)
                else:
                    rank_color = COLOR_WHITE

                dur = self._format_duration(rec["duration_seconds"])
                values = [
                    str(rank),
                    rec["name"],
                    str(rec["score"]),
                    rec["datetime"],
                    dur,
                ]

                for (_, ratio, align), px, val, limit in zip(cols, header_x, values, col_limits):
                    color = rank_color if align == "left" else COLOR_WHITE
                    text = self._render_fit(val, "help_body", color, limit)
                    if align == "center":
                        t_rect = text.get_rect(center=(px, row_y + line_h // 2))
                    else:
                        t_rect = text.get_rect(midleft=(px, row_y + line_h // 2))
                    self.screen.blit(text, t_rect)

            # 滚动条
            if max_scroll > 0:
                bar_area_h = visible_rows * line_h
                bar_h = max(20, int(visible_rows / len(all_records) * bar_area_h))
                bar_y = table_top + int(self._records_scroll / max_scroll * (bar_area_h - bar_h))
                bar_x = int(self.window_w * 0.95) + 4
                bar_rect = pygame.Rect(bar_x, bar_y, 5, bar_h)
                pygame.draw.rect(self.screen, (100, 100, 120), bar_rect, border_radius=2)

        # 底部提示
        total = self.records.record_count
        if total > 0:
            scroll_msg = (
                f"共 {total} 条记录    ↑↓ 滚动    PgUp/PgDn 翻页    B/Esc 返回"
            )
        else:
            scroll_msg = "B/Esc 返回菜单"
        hint = self._render_fit(scroll_msg, "hint", COLOR_GRAY, self.window_w - 24)
        hint_rect = hint.get_rect(
            center=(self.window_w // 2, self.window_h - hint.get_height())
        )
        self.screen.blit(hint, hint_rect)

    # ---- 游戏中 ----
    def _draw_playing(self):
        cs = self.cell_size
        ox, oy = self.grid_offset
        margin = max(6, int(min(self.window_w, self.window_h) * 0.012))
        pause_rect = None

        if self.state == PLAYING:
            pause_rect = self._get_pause_button_rect(margin)
            self._pause_button_rect = pause_rect

        # 食物和蛇
        if self.food:
            self.food.draw(self.screen, cs, ox, oy)
        if self.snake:
            self.snake.draw(self.screen, cs, ox, oy)

        # 左上角：玩家名 + 分数
        name = self.player_name if self.player_name else "游客"
        info_max_w = max(20, self.window_w - margin * 2)
        if pause_rect:
            info_max_w = max(20, pause_rect.left - margin * 2)
        info = self._render_fit(
            f"玩家: {name}    分数: {self.score}",
            "md", COLOR_WHITE, info_max_w
        )
        info_x = min(max(margin, ox), max(margin, self.window_w - info.get_width() - margin))
        self.screen.blit(info, (info_x, margin))

        if pause_rect:
            self._draw_pause_button(pause_rect)

        # 右上角：时长
        dur = self._format_duration(self.elapsed_seconds)
        dur_text = self._render_fit(
            f"时长: {dur}", "hint", COLOR_GRAY, max(20, self.window_w - margin * 2)
        )
        dur_x = self.window_w - dur_text.get_width() - margin
        dur_y = margin
        if pause_rect:
            dur_y = pause_rect.bottom + 3
        elif info.get_width() + dur_text.get_width() + margin * 4 > self.window_w:
            dur_y = margin + info.get_height() + 2
        self.screen.blit(dur_text, (dur_x, dur_y))

        if self.state == PLAYING and self.paused:
            center_y = self.window_h // 2
            self._draw_center_text_fit("已暂停", "xl", COLOR_YELLOW,
                                       center_y - self.font_xl.get_height() // 2)
            self._draw_center_text_fit("按 P 继续", "md", COLOR_WHITE,
                                       center_y + self.font_md.get_height())

    def _get_pause_button_rect(self, margin: int) -> pygame.Rect:
        label = "继续" if self.paused else "暂停"
        text = self._render_fit(label, "hint", COLOR_WHITE, max(32, self.window_w // 3))
        pad_x = max(10, text.get_height() // 2)
        pad_y = max(4, text.get_height() // 4)
        width = text.get_width() + pad_x * 2
        height = text.get_height() + pad_y * 2
        return pygame.Rect(self.window_w - width - margin, margin, width, height)

    def _draw_pause_button(self, rect: pygame.Rect):
        label = "继续" if self.paused else "暂停"
        mouse_pos = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse_pos)
        bg = (48, 70, 58) if self.paused else (38, 52, 68)
        border = COLOR_GREEN if hovered else COLOR_CYAN
        pygame.draw.rect(self.screen, bg, rect, border_radius=4)
        pygame.draw.rect(self.screen, border, rect, 1, border_radius=4)
        text = self._render_fit(label, "hint", COLOR_WHITE, max(10, rect.width - 12))
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)

    # ---- 游戏结束叠层 ----
    def _draw_game_over(self):
        self._draw_semi_transparent_overlay()

        center_y = self.window_h // 2
        gap = max(8, int(self.window_h * 0.035))
        self._draw_center_text_fit("游戏结束!", "huge", COLOR_RED,
                                   center_y - self.font_huge.get_height() - gap)
        name = self.player_name if self.player_name else "游客"
        self._draw_center_text_fit(
            f"玩家: {name}    分数: {self.score}    时长: {self._format_duration(self.elapsed_seconds)}",
            "md", COLOR_WHITE, center_y)
        self._draw_center_text_fit("按 R 再来一局    按 M 返回菜单    按 Q 退出",
                                   "md", COLOR_GRAY,
                                   center_y + self.font_md.get_height() + gap)

    # ---- 工具 ----
    def _draw_center_text(self, text, font, color, y_offset):
        surf = font.render(text, True, color)
        rect = surf.get_rect(center=(self.window_w // 2, self.window_h // 2 + y_offset))
        self.screen.blit(surf, rect)

    def _draw_center_text_fit(self, text: str, font_key: str, color, y: int):
        """居中绘制文字，窗口过窄时自动降字号保持清晰。"""
        surf = self._render_fit(text, font_key, color, max(20, self.window_w - 24))
        rect = surf.get_rect(center=(self.window_w // 2, y))
        self.screen.blit(surf, rect)

    def _render_fit(self, text: str, font_key: str, color,
                    max_width: int) -> pygame.Surface:
        """渲染文字；如果太宽，重新加载较小字号而不是缩放位图。"""
        font = self._adaptive_fonts[font_key]
        surf = font.render(text, True, color)
        if surf.get_width() <= max_width:
            return surf

        size = self._font_sizes.get(font_key, font.get_height())
        bold = self._font_bold.get(font_key, False)
        for smaller in range(size - 2, 11, -2):
            test_font = _load_font(smaller, bold=bold)
            surf = test_font.render(text, True, color)
            if surf.get_width() <= max_width:
                return surf
        return surf

    def _update_adaptive_fonts(self):
        """根据窗口大小计算自适应字体尺寸（窗口缩放时调用）"""
        if (self.window_w == self._last_font_window_w and
                self.window_h == self._last_font_window_h):
            return
        self._last_font_window_w = self.window_w
        self._last_font_window_h = self.window_h
        base = min(self.window_w, self.window_h)

        md_size = max(16, min(28, int(base * 0.040)))
        lg_size = max(22, min(40, int(base * 0.060)))
        xl_size = max(28, min(52, int(base * 0.080)))
        huge_size = max(34, min(64, int(base * 0.092)))
        self.font_md = _load_font(md_size, bold=True)
        self.font_lg = _load_font(lg_size, bold=True)
        self.font_xl = _load_font(xl_size, bold=True)
        self.font_huge = _load_font(huge_size, bold=True)

        self._adaptive_fonts["md"] = self.font_md
        self._adaptive_fonts["lg"] = self.font_lg
        self._adaptive_fonts["xl"] = self.font_xl
        self._adaptive_fonts["huge"] = self.font_huge
        self._font_sizes.update({
            "md": md_size,
            "lg": lg_size,
            "xl": xl_size,
            "huge": huge_size,
        })
        self._font_bold.update({
            "md": True,
            "lg": True,
            "xl": True,
            "huge": True,
        })

        # 底部提示字体：窗口短边的 3%，最小 14，最大 26
        hint_size = max(16, min(26, int(base * 0.030)))
        self._adaptive_fonts["hint"] = _load_font(hint_size)
        self._font_sizes["hint"] = hint_size
        self._font_bold["hint"] = False

        # 游戏说明 / 记录正文字体：窗口短边的 3.6%，最小 18，最大 30
        help_body_size = max(18, min(30, int(base * 0.036)))
        self._adaptive_fonts["help_body"] = _load_font(help_body_size)
        self._font_sizes["help_body"] = help_body_size
        self._font_bold["help_body"] = False

        # 游戏说明标题：窗口短边的 5%，最小 28，最大 48
        help_title_size = max(28, min(48, int(base * 0.050)))
        self._adaptive_fonts["help_title"] = _load_font(help_title_size, bold=True)
        self._font_sizes["help_title"] = help_title_size
        self._font_bold["help_title"] = True

        # 菜单副标题
        sub_size = max(16, min(22, int(base * 0.025)))
        self._adaptive_fonts["sub"] = _load_font(sub_size)
        self._font_sizes["sub"] = sub_size
        self._font_bold["sub"] = False

    def _update_cursor(self):
        """更新光标闪烁（在 MENU 和 PLAYER_SELECT 中调用）"""
        self._cursor_timer += 1
        if self._cursor_timer >= 15:
            self._cursor_timer = 0
            self._cursor_visible = not self._cursor_visible

    # ================================================================
    # 主循环
    # ================================================================
    def run(self):
        self._go_menu()
        self._update_menu_buttons()

        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    game = Game()
    game.run()
