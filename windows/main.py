"""GoldTicker Windows 原生表现层入口 (windows/main.py)。

基于 Tkinter 构建无边框可拖动桌面悬浮卡片，并结合 Pillow/pystray 动态自绘任务栏宽托盘。
由 core 内核完全驱动，实现表现层与业务逻辑解耦、双入口互锁防幽灵机制与表现层纯净原则。
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 确保任意工作路径下均能正确定位并导入 core 与 windows 包
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import tkinter as tk
from tkinter import messagebox

from core.config import (
    DEFAULT_CONFIG,
    VALID_REFRESH_INTERVALS,
    VALID_WIDTHS,
    get_app_data_dir,
    get_default_config_path,
    load_config,
    save_config,
)
from core.constants import (
    DEFAULT_BANK_SPREADS,
    DISCLAIMER_CN,
    DISCLAIMER_EN,
    MIN_REFRESH_SECONDS,
    SUPPORTED_SYMBOLS,
    SYMBOL_AU9999,
    SYMBOL_META,
    SYMBOL_XAU_USD,
    SYMBOL_ZS_JCJ,
)
from core.pricing import PricingEngine, QuoteData, default_engine
from core.storage import (
    cleanup_old_history,
    clear_intraday_cache,
    load_today_points,
    record_price_point,
)
from windows.tray import (
    COLOR_GREEN,
    COLOR_MUTED,
    COLOR_RED,
    COLOR_WHITE,
    build_tray_tooltip,
    calculate_quote_delta,
    can_toggle_entry,
    create_tray_image,
    get_quote_color,
    is_quote_valid,
)

# 动态安全导入 pystray
try:
    import pystray
except ImportError:
    pystray = None


# 视觉样式常量
BG_DARK = "#191c23"
BG_CARD = "#21262d"
BG_BADGE = "#30363d"
BORDER_COLOR = "#30363d"
TEXT_MUTED = "#8b949e"
TEXT_MAIN = "#f0f6fc"


class GoldTickerWindowsApp:
    """Windows 原生悬浮窗与托盘调度核心控制器。"""

    def __init__(self, root: Optional[tk.Tk] = None) -> None:
        self.config: Dict[str, Any] = load_config()
        self.pricing_engine: PricingEngine = default_engine
        self.current_quote: Optional[QuoteData] = None
        self.intraday_points: List[Tuple[float, float]] = []

        # 线程与通信
        self.msg_queue: queue.Queue = queue.Queue()
        self.is_running: bool = True
        self.fetch_thread: Optional[threading.Thread] = None

        # 拖拽状态
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0

        # Tkinter GUI
        self.root: tk.Tk = root or tk.Tk()
        self.root.title("GoldTicker")
        self.root.configure(bg=BG_DARK)

        # 托盘对象
        self.tray_icon: Optional[Any] = None
        self.tray_thread: Optional[threading.Thread] = None

        # 初始化界面与事件
        self._init_window()
        self._init_widgets()
        self._init_context_menu()
        self._init_tray()

        # 启动后台刷新
        self._load_cached_points()
        self._start_fetch_loop()
        self._schedule_gui_update()

    # ---------------- 窗口基础属性与交互 ----------------

    def _init_window(self) -> None:
        """初始化窗口属性：无边框、置顶、透明度、几何尺寸。"""
        self.root.overrideredirect(True)  # 无边框悬浮窗

        # 置顶属性
        topmost = 1 if self.config.get("alwaysOnTop", True) else 0
        self.root.attributes("-topmost", topmost)

        # 透明度属性
        opacity = float(self.config.get("opacity", 0.95))
        try:
            self.root.attributes("-alpha", opacity)
        except Exception:
            pass

        # 尺寸与初始坐标
        width = int(self.config.get("width", 220))
        win_x = self.config.get("windowX")
        win_y = self.config.get("windowY")

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        if win_x is None or win_y is None or win_x < 0 or win_x > screen_w - 50:
            win_x = max(20, screen_w - width - 30)
            win_y = 60

        self.root.geometry(f"{width}x200+{win_x}+{win_y}")

        # 显示/隐藏卡片
        if not self.config.get("showOnDesktop", True):
            self.root.withdraw()

        # 绑定鼠标拖拽与右键菜单
        self.root.bind("<Button-1>", self._on_drag_start)
        self.root.bind("<B1-Motion>", self._on_drag_motion)
        self.root.bind("<ButtonRelease-1>", self._on_drag_end)
        self.root.bind("<Button-3>", self._on_right_click)

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag_motion(self, event: tk.Event) -> None:
        delta_x = event.x - self._drag_start_x
        delta_y = event.y - self._drag_start_y
        new_x = self.root.winfo_x() + delta_x
        new_y = self.root.winfo_y() + delta_y
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_drag_end(self, event: tk.Event) -> None:
        # 保存最终窗口位置
        self.config["windowX"] = self.root.winfo_x()
        self.config["windowY"] = self.root.winfo_y()
        save_config(self.config)

    # ---------------- 界面组件构建 ----------------

    def _init_widgets(self) -> None:
        """构建悬浮卡片内部组件。"""
        self.main_frame = tk.Frame(self.root, bg=BG_DARK, highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # 内部所有子组件也绑定鼠标拖动与右键
        for w in (self.main_frame,):
            w.bind("<Button-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_motion)
            w.bind("<ButtonRelease-1>", self._on_drag_end)
            w.bind("<Button-3>", self._on_right_click)

        # 1. 顶部主要价格行
        self.header_frame = tk.Frame(self.main_frame, bg=BG_DARK)
        self.header_frame.pack(fill=tk.X, padx=12, pady=(10, 4))
        self.header_frame.bind("<Button-1>", self._on_drag_start)
        self.header_frame.bind("<B1-Motion>", self._on_drag_motion)
        self.header_frame.bind("<ButtonRelease-1>", self._on_drag_end)
        self.header_frame.bind("<Button-3>", self._on_right_click)

        # 标的前缀徽标（“金”或“Au”）
        self.lbl_prefix = tk.Label(
            self.header_frame,
            text="金",
            font=("Segoe UI", 10, "bold"),
            bg=BG_BADGE,
            fg=TEXT_MAIN,
            width=3,
            relief=tk.FLAT,
        )
        self.lbl_prefix.pack(side=tk.LEFT, padx=(0, 6))

        # 主价格标签
        self.lbl_price = tk.Label(
            self.header_frame,
            text="--.--",
            font=("Segoe UI", 15, "bold"),
            bg=BG_DARK,
            fg=TEXT_MAIN,
        )
        self.lbl_price.pack(side=tk.LEFT)

        # 涨跌幅标签
        self.lbl_delta = tk.Label(
            self.header_frame,
            text="--",
            font=("Segoe UI", 10, "bold"),
            bg=BG_DARK,
            fg=TEXT_MUTED,
        )
        self.lbl_delta.pack(side=tk.RIGHT)

        # 2. 明细行情行（高/低/基准）
        self.details_frame = tk.Frame(self.main_frame, bg=BG_DARK)
        self.lbl_details = tk.Label(
            self.details_frame,
            text="今开: --  昨收: --\n最高: --  最低: --",
            font=("Segoe UI", 8),
            bg=BG_DARK,
            fg=TEXT_MUTED,
            justify=tk.LEFT,
        )
        self.lbl_details.pack(fill=tk.X, padx=12, pady=2)
        if self.config.get("showDetails", True):
            self.details_frame.pack(fill=tk.X)

        # 3. 分时走势折线 Canvas（纯净原则：绝对严禁出现采样计数）
        self.chart_frame = tk.Frame(self.main_frame, bg=BG_DARK)
        self.chart_canvas = tk.Canvas(
            self.chart_frame,
            bg=BG_CARD,
            height=60,
            highlightthickness=0,
        )
        self.chart_canvas.pack(fill=tk.X, padx=10, pady=4)
        self.chart_canvas.bind("<Button-1>", self._on_drag_start)
        self.chart_canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.chart_canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self.chart_canvas.bind("<Button-3>", self._on_right_click)

        if self.config.get("showChart", True):
            self.chart_frame.pack(fill=tk.X)

        # 4. 底部状态与免责提示行
        self.footer_frame = tk.Frame(self.main_frame, bg=BG_DARK)
        self.lbl_footer = tk.Label(
            self.footer_frame,
            text="获取中…",
            font=("Segoe UI", 8),
            bg=BG_DARK,
            fg=TEXT_MUTED,
        )
        self.lbl_footer.pack(side=tk.LEFT, padx=10, pady=(2, 6))
        self.footer_frame.pack(fill=tk.X)

        # 自动调整窗口几何高度以适配子控件
        self._adjust_card_height()

    def _adjust_card_height(self) -> None:
        """根据当前组件显示状态动态平滑适配悬浮卡片高度。"""
        width = int(self.config.get("width", 220))
        h = 52  # 基础 header + 边距
        if self.config.get("showDetails", True):
            h += 34
        if self.config.get("showChart", True):
            h += 68
        h += 24  # footer

        x = self.root.winfo_x()
        y = self.root.winfo_y()
        self.root.geometry(f"{width}x{h}+{x}+{y}")

    # ---------------- 分时图纯净渲染 ----------------

    def _render_chart(self) -> None:
        """基于 Tkinter Canvas 纯净渲染分时走势图。

        【表现层纯净原则】：严禁在画布上渲染点数采样等内部技术计数文本！
        """
        if not self.config.get("showChart", True):
            return

        self.chart_canvas.delete("all")
        width = self.chart_canvas.winfo_width()
        height = self.chart_canvas.winfo_height()
        if width <= 10 or height <= 10:
            width = int(self.config.get("width", 220)) - 20
            height = 60

        if len(self.intraday_points) < 2:
            self.chart_canvas.create_text(
                width / 2,
                height / 2,
                text="分时数据累积中…",
                fill=TEXT_MUTED,
                font=("Segoe UI", 8),
            )
            return

        prices = [p[1] for p in self.intraday_points]
        min_p = min(prices)
        max_p = max(prices)
        spread = max_p - min_p
        if spread < 1e-4:
            spread = 1.0

        pad_x = 4
        pad_y = 6
        draw_w = width - pad_x * 2
        draw_h = height - pad_y * 2

        coords: List[float] = []
        n = len(prices)
        for i, price in enumerate(prices):
            cx = pad_x + (i / (n - 1)) * draw_w
            cy = pad_y + (1.0 - (price - min_p) / spread) * draw_h
            coords.extend([cx, cy])

        # 获取曲线颜色
        diff, _ = calculate_quote_delta(self.current_quote, self.config.get("changeBasis", "prev_close"))
        line_color = get_quote_color(diff, self.config.get("colorMode", "red-up"))

        # 绘制半透明基底与折线
        self.chart_canvas.create_line(
            coords,
            fill=line_color,
            width=2,
            smooth=True,
        )

    # ---------------- 双入口互锁防幽灵右键菜单 ----------------

    def _init_context_menu(self) -> None:
        """初始化右键菜单与 Action Matrix。"""
        self.menu = tk.Menu(self.root, tearoff=0, bg="#2d333b", fg="#e6edf3", activebackground="#388bfd")

    def _on_right_click(self, event: tk.Event) -> None:
        """构建并弹出上下文菜单，实时计算互锁状态。"""
        self.menu.delete(0, tk.END)

        cur_desktop = bool(self.config.get("showOnDesktop", True))
        cur_tray = bool(self.config.get("showMenuBar", True))

        # 1. 核心视图开关（双入口互锁防幽灵）
        # 互锁逻辑：若当前 tray 已关闭，桌面开关不可关闭（置灰禁用）
        can_disable_desk = can_toggle_entry(cur_desktop, cur_tray, "desktop")
        desk_state = tk.NORMAL if (not cur_desktop or can_disable_desk) else tk.DISABLED

        self.menu.add_checkbutton(
            label="显示到桌面" + (" (唯一入口锁定)" if not can_disable_desk else ""),
            command=self._toggle_desktop,
            state=desk_state,
        )
        self.menu.entryconfigure(0, variable=tk.BooleanVar(value=cur_desktop))

        # 托盘入口开关
        can_disable_tr = can_toggle_entry(cur_desktop, cur_tray, "tray")
        tray_state = tk.NORMAL if (not cur_tray or can_disable_tr) else tk.DISABLED
        self.menu.add_checkbutton(
            label="显示到菜单栏/托盘" + (" (唯一入口锁定)" if not can_disable_tr else ""),
            command=self._toggle_tray_entry,
            state=tray_state,
        )
        self.menu.entryconfigure(1, variable=tk.BooleanVar(value=cur_tray))

        self.menu.add_separator()

        # 走势图开关
        show_chart = self.config.get("showChart", True)
        self.menu.add_command(
            label=f"{'✓ ' if show_chart else '   '}显示走势图",
            command=self._toggle_chart,
        )

        # 明细开关
        show_details = self.config.get("showDetails", True)
        self.menu.add_command(
            label=f"{'✓ ' if show_details else '   '}显示 高/低/基准价",
            command=self._toggle_details,
        )

        # 置顶开关
        topmost = self.config.get("alwaysOnTop", True)
        self.menu.add_command(
            label=f"{'✓ ' if topmost else '   '}窗口置顶",
            command=self._toggle_topmost,
        )

        self.menu.add_separator()

        # 标的切换子菜单
        sub_symbol = tk.Menu(self.menu, tearoff=0, bg="#2d333b", fg="#e6edf3")
        cur_sym = self.config.get("symbol", SYMBOL_ZS_JCJ)
        for sym_id in SUPPORTED_SYMBOLS:
            meta = SYMBOL_META.get(sym_id, {})
            name = meta.get("name_cn", sym_id)
            checked = "✓ " if sym_id == cur_sym else "   "
            sub_symbol.add_command(
                label=f"{checked}{name}",
                command=lambda s=sym_id: self._set_symbol(s),
            )
        self.menu.add_cascade(label="标的切换", menu=sub_symbol)

        # 涨跌幅基准子菜单
        sub_basis = tk.Menu(self.menu, tearoff=0, bg="#2d333b", fg="#e6edf3")
        cur_basis = self.config.get("changeBasis", "prev_close")
        for b_id, b_name in [("prev_close", "昨收价"), ("open_price", "今开价")]:
            checked = "✓ " if b_id == cur_basis else "   "
            sub_basis.add_command(
                label=f"{checked}{b_name}",
                command=lambda b=b_id: self._set_change_basis(b),
            )
        self.menu.add_cascade(label="涨跌基准", menu=sub_basis)

        # 颜色模式子菜单
        sub_color = tk.Menu(self.menu, tearoff=0, bg="#2d333b", fg="#e6edf3")
        cur_col = self.config.get("colorMode", "red-up")
        for c_id, c_name in [("red-up", "红涨绿跌 (国内习惯)"), ("green-up", "绿涨红跌 (国际习惯)")]:
            checked = "✓ " if c_id == cur_col else "   "
            sub_color.add_command(
                label=f"{checked}{c_name}",
                command=lambda c=c_id: self._set_color_mode(c),
            )
        self.menu.add_cascade(label="红绿配色", menu=sub_color)

        # 刷新频率子菜单 (≥10s)
        sub_interval = tk.Menu(self.menu, tearoff=0, bg="#2d333b", fg="#e6edf3")
        cur_inv = int(self.config.get("refreshInterval", 30))
        for inv in VALID_REFRESH_INTERVALS:
            checked = "✓ " if inv == cur_inv else "   "
            sub_interval.add_command(
                label=f"{checked}{inv} 秒",
                command=lambda i=inv: self._set_refresh_interval(i),
            )
        self.menu.add_cascade(label="刷新频率", menu=sub_interval)

        # 宽度子菜单
        sub_width = tk.Menu(self.menu, tearoff=0, bg="#2d333b", fg="#e6edf3")
        cur_w = int(self.config.get("width", 220))
        for w in VALID_WIDTHS:
            checked = "✓ " if w == cur_w else "   "
            sub_width.add_command(
                label=f"{checked}{w} pt",
                command=lambda width=w: self._set_width(width),
            )
        self.menu.add_cascade(label="卡片宽度", menu=sub_width)

        # 透明度子菜单
        sub_alpha = tk.Menu(self.menu, tearoff=0, bg="#2d333b", fg="#e6edf3")
        cur_op = float(self.config.get("opacity", 0.95))
        for op, label in [(1.0, "100%"), (0.9, "90%"), (0.8, "80%"), (0.7, "70%"), (0.5, "50%")]:
            checked = "✓ " if abs(op - cur_op) < 0.05 else "   "
            sub_alpha.add_command(
                label=f"{checked}{label}",
                command=lambda val=op: self._set_opacity(val),
            )
        self.menu.add_cascade(label="窗口透明度", menu=sub_alpha)

        self.menu.add_separator()

        # 系统与功能操作
        self.menu.add_command(label="打开配置目录", command=self._open_config_dir)
        self.menu.add_command(label="重新加载配置", command=self._reload_config)
        self.menu.add_command(label="清除今日走势缓存", command=self._clear_cache)
        self.menu.add_command(label="重置窗口位置", command=self._reset_position)
        self.menu.add_separator()
        self.menu.add_command(label="退出 GoldTicker", command=self.quit)

        self.menu.tk_popup(event.x_root, event.y_root)

    # ---------------- 托盘集成与双入口防幽灵 ----------------

    def _init_tray(self) -> None:
        """初始化 pystray 任务栏动态宽托盘。"""
        if pystray is None:
            return

        if not self.config.get("showMenuBar", True):
            return

        def _setup_tray():
            # 初始图片
            img = create_tray_image(self.current_quote, self.config)
            tip = build_tray_tooltip(self.current_quote, self.config)

            def get_tray_menu():
                cur_desktop = bool(self.config.get("showOnDesktop", True))
                cur_tray = bool(self.config.get("showMenuBar", True))

                can_disable_tr = can_toggle_entry(cur_desktop, cur_tray, "tray")
                can_disable_dk = can_toggle_entry(cur_desktop, cur_tray, "desktop")

                items = [
                    pystray.MenuItem(
                        "显示到桌面" + (" (唯一入口锁定)" if not can_disable_dk else ""),
                        self._toggle_desktop,
                        checked=lambda item: self.config.get("showOnDesktop", True),
                        enabled=can_disable_dk or not cur_desktop,
                    ),
                    pystray.MenuItem(
                        "显示到菜单栏/托盘" + (" (唯一入口锁定)" if not can_disable_tr else ""),
                        self._toggle_tray_entry,
                        checked=lambda item: self.config.get("showMenuBar", True),
                        enabled=can_disable_tr or not cur_tray,
                    ),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("打开配置目录", self._open_config_dir),
                    pystray.MenuItem("重置卡片位置", self._reset_position),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("退出应用", lambda: self.root.after(0, self.quit)),
                ]
                return pystray.Menu(*items)

            self.tray_icon = pystray.Icon(
                "GoldTicker",
                icon=img,
                title=tip,
                menu=get_tray_menu(),
            )
            try:
                self.tray_icon.run()
            except Exception:
                pass

        self.tray_thread = threading.Thread(target=_setup_tray, daemon=True)
        self.tray_thread.start()

    def _update_tray(self) -> None:
        """更新托盘图标位图与 Tooltip。"""
        if self.tray_icon is None:
            return
        try:
            new_img = create_tray_image(self.current_quote, self.config)
            new_tip = build_tray_tooltip(self.current_quote, self.config)
            self.tray_icon.icon = new_img
            self.tray_icon.title = new_tip
        except Exception:
            pass

    # ---------------- 菜单动作响应与互锁处理 ----------------

    def _toggle_desktop(self) -> None:
        cur_desktop = bool(self.config.get("showOnDesktop", True))
        cur_tray = bool(self.config.get("showMenuBar", True))

        if not can_toggle_entry(cur_desktop, cur_tray, "desktop"):
            messagebox.showinfo(
                "操作受限",
                "至少需要保留一个可见入口（桌面悬浮窗或状态栏托盘），无法关闭！",
            )
            return

        new_val = not cur_desktop
        self.config["showOnDesktop"] = new_val
        save_config(self.config)

        if new_val:
            self.root.deiconify()
        else:
            self.root.withdraw()

        self._update_tray()

    def _toggle_tray_entry(self) -> None:
        cur_desktop = bool(self.config.get("showOnDesktop", True))
        cur_tray = bool(self.config.get("showMenuBar", True))

        if not can_toggle_entry(cur_desktop, cur_tray, "tray"):
            messagebox.showinfo(
                "操作受限",
                "至少需要保留一个可见入口（桌面悬浮窗或状态栏托盘），无法关闭！",
            )
            return

        new_val = not cur_tray
        self.config["showMenuBar"] = new_val
        save_config(self.config)

        if not new_val and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        elif new_val and not self.tray_icon:
            self._init_tray()

    def _toggle_chart(self) -> None:
        val = not self.config.get("showChart", True)
        self.config["showChart"] = val
        save_config(self.config)
        if val:
            self.chart_frame.pack(fill=tk.X)
            self._render_chart()
        else:
            self.chart_frame.pack_forget()
        self._adjust_card_height()

    def _toggle_details(self) -> None:
        val = not self.config.get("showDetails", True)
        self.config["showDetails"] = val
        save_config(self.config)
        if val:
            self.details_frame.pack(fill=tk.X)
        else:
            self.details_frame.pack_forget()
        self._adjust_card_height()

    def _toggle_topmost(self) -> None:
        val = not self.config.get("alwaysOnTop", True)
        self.config["alwaysOnTop"] = val
        save_config(self.config)
        self.root.attributes("-topmost", 1 if val else 0)

    def _set_symbol(self, symbol: str) -> None:
        self.config["symbol"] = symbol
        save_config(self.config)
        self._load_cached_points()
        self._trigger_immediate_fetch()

    def _set_change_basis(self, basis: str) -> None:
        self.config["changeBasis"] = basis
        save_config(self.config)
        self._update_ui_with_quote()
        self._update_tray()

    def _set_color_mode(self, mode: str) -> None:
        self.config["colorMode"] = mode
        save_config(self.config)
        self._update_ui_with_quote()
        self._update_tray()

    def _set_refresh_interval(self, sec: int) -> None:
        if sec < MIN_REFRESH_SECONDS:
            sec = MIN_REFRESH_SECONDS
        self.config["refreshInterval"] = sec
        save_config(self.config)

    def _set_width(self, width: int) -> None:
        self.config["width"] = width
        save_config(self.config)
        self._adjust_card_height()
        self._render_chart()

    def _set_opacity(self, opacity: float) -> None:
        self.config["opacity"] = opacity
        save_config(self.config)
        try:
            self.root.attributes("-alpha", opacity)
        except Exception:
            pass

    def _open_config_dir(self) -> None:
        path = get_app_data_dir()
        if sys.platform.startswith("win"):
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def _reload_config(self) -> None:
        self.config = load_config()
        self._adjust_card_height()
        self._update_ui_with_quote()
        self._update_tray()

    def _clear_cache(self) -> None:
        clear_intraday_cache()
        self.intraday_points.clear()
        self._render_chart()

    def _reset_position(self) -> None:
        width = int(self.config.get("width", 220))
        screen_w = self.root.winfo_screenwidth()
        new_x = max(20, screen_w - width - 30)
        new_y = 60
        self.config["windowX"] = new_x
        self.config["windowY"] = new_y
        save_config(self.config)
        self.root.geometry(f"+{new_x}+{new_y}")

    # ---------------- 数据获取与后台轮询驱动 ----------------

    def _load_cached_points(self) -> None:
        symbol = self.config.get("symbol", SYMBOL_ZS_JCJ)
        pts = load_today_points(symbol)
        self.intraday_points = [(p.timestamp, p.price) for p in pts]

    def _start_fetch_loop(self) -> None:
        def loop():
            while self.is_running:
                symbol = self.config.get("symbol", SYMBOL_ZS_JCJ)
                try:
                    quote = self.pricing_engine.fetch_quote(symbol)
                    if quote and not quote.error and quote.price > 0:
                        record_price_point(quote.symbol, quote.price, time.time())
                    self.msg_queue.put(quote)
                except Exception as e:
                    self.msg_queue.put(QuoteData(
                        symbol=symbol,
                        price=0.0,
                        prev_close=0.0,
                        open_price=0.0,
                        high=0.0,
                        low=0.0,
                        change=0.0,
                        change_pct=0.0,
                        time_str=datetime.now().strftime("%H:%M:%S"),
                        source_id="error",
                        source_name="系统",
                        error=str(e),
                    ))

                # 间隔轮询 (严守 ≥10s 底线)
                interval = max(
                    MIN_REFRESH_SECONDS,
                    int(self.config.get("refreshInterval", 30)),
                )
                for _ in range(interval * 2):
                    if not self.is_running:
                        break
                    time.sleep(0.5)

        self.fetch_thread = threading.Thread(target=loop, daemon=True)
        self.fetch_thread.start()

    def _trigger_immediate_fetch(self) -> None:
        def fetch_now():
            symbol = self.config.get("symbol", SYMBOL_ZS_JCJ)
            try:
                q = self.pricing_engine.fetch_quote(symbol)
                self.msg_queue.put(q)
            except Exception:
                pass
        threading.Thread(target=fetch_now, daemon=True).start()

    def _schedule_gui_update(self) -> None:
        """主线程定时检查消息队列并更新 UI。"""
        try:
            while not self.msg_queue.empty():
                quote = self.msg_queue.get_nowait()
                if quote:
                    self.current_quote = quote
                    self._update_ui_with_quote()
                    self._update_tray()
        except Exception:
            pass

        if self.is_running:
            self.root.after(300, self._schedule_gui_update)

    def _update_ui_with_quote(self) -> None:
        """根据当前行情更新悬浮卡片视图。"""
        quote = self.current_quote
        symbol = self.config.get("symbol", SYMBOL_ZS_JCJ)

        # 徽标（国内模式“金”，国际模式“Au”）
        prefix = "Au" if symbol == SYMBOL_XAU_USD else "金"
        self.lbl_prefix.config(text=prefix)

        if not is_quote_valid(quote):
            err_text = quote.error if (quote and quote.error) else "获取中…"
            self.lbl_price.config(text="--.--", fg=TEXT_MUTED)
            self.lbl_delta.config(text="--", fg=TEXT_MUTED)
            self.lbl_footer.config(text=err_text)
            return

        # 计算涨跌
        change_basis = self.config.get("changeBasis", "prev_close")
        diff, pct = calculate_quote_delta(quote, change_basis)
        color = get_quote_color(diff, self.config.get("colorMode", "red-up"))

        # 更新大字价格与涨跌幅
        self.lbl_price.config(text=f"{quote.price:.2f}", fg=TEXT_MAIN)
        sign = "+" if diff > 0 else ""
        self.lbl_delta.config(text=f"{sign}{diff:.2f} ({pct:+.2f}%)", fg=color)

        # 更新明细 (今开 / 昨收 / 最高 / 最低)
        basis_name = "昨收" if change_basis == "prev_close" else "今开"
        self.lbl_details.config(
            text=f"今开: {quote.open_price:.2f}   {basis_name}: {quote.prev_close:.2f}\n"
                 f"最高: {quote.high:.2f}   最低: {quote.low:.2f}"
        )

        # 记录到分时并重绘折线
        self.intraday_points.append((time.time(), quote.price))
        if len(self.intraday_points) > 2000:
            self.intraday_points = self.intraday_points[-2000:]
        self._render_chart()

        # 底部状态行
        meta = SYMBOL_META.get(symbol, {})
        sym_name = meta.get("name_cn", symbol)
        self.lbl_footer.config(
            text=f"{sym_name} · {quote.time_str} · {quote.source_name}"
        )

    def quit(self) -> None:
        """安全退出 GoldTicker。"""
        self.is_running = False
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()


def main() -> None:
    app = GoldTickerWindowsApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
