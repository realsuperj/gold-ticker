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
    apply_frozen_basis,
    cleanup_old_history,
    clear_intraday_cache,
    freeze_day_basis,
    load_today_points,
    record_price_point,
)
from core.i18n import t, resolve_language, ticker_prefix
from core.product import VERSION, COPYRIGHT, resource_path
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
        self.product_icon = tk.PhotoImage(file=str(resource_path()))
        self.root.iconphoto(True, self.product_icon)

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

        self.root.geometry(f"{width}x200+{int(win_x)}+{int(win_y)}")

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
            text=ticker_prefix(self.config),
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
            text="--",
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
            text=self._text("refreshing"),
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
                text=self._text("chart_accumulating"),
                fill=TEXT_MUTED,
                font=("Segoe UI", 8),
            )
            return

        prices = [p[1] for p in self.intraday_points]
        # 基准参考价（昨收/今开，已由当日冻结基准保证稳定）
        change_basis = self.config.get("changeBasis", "prevClose")
        ref_price = 0.0
        if self.current_quote is not None:
            ref_price = (self.current_quote.prev_close if change_basis == "prevClose"
                         else self.current_quote.open_price)
        all_vals = list(prices) + ([ref_price] if ref_price > 0 else [])
        min_p, max_p = min(all_vals), max(all_vals)
        spread = max_p - min_p
        if spread < 1e-4:
            spread = 1.0

        pad_x = 4
        pad_y = 6
        draw_w = width - pad_x * 2
        draw_h = height - pad_y * 2
        step_x = draw_w / float(len(prices) - 1)

        def cy_of(price):
            return pad_y + (1.0 - (price - min_p) / spread) * draw_h

        # 获取曲线颜色
        diff, _ = calculate_quote_delta(self.current_quote, self.config.get("changeBasis", "prevClose"))
        line_color = get_quote_color(diff, self.config.get("colorMode", "cny"))

        # 基准虚线（在 Y 范围内时）
        if ref_price > 0:
            ry = cy_of(ref_price)
            if pad_y <= ry <= pad_y + draw_h:
                self.chart_canvas.create_line(
                    pad_x, ry, pad_x + draw_w, ry,
                    fill=TEXT_MUTED, width=1, dash=(3, 3),
                )

        # 当日走势：采样点等距铺满，便于一眼看全日形态
        coords: List[float] = []
        for idx, price in enumerate(prices):
            coords.extend([pad_x + idx * step_x, cy_of(price)])
        self.chart_canvas.create_line(
            coords,
            fill=line_color,
            width=2,
            smooth=True,
        )

        t_first, t_last = self.intraday_points[0][0], self.intraday_points[-1][0]
        first_dt = datetime.fromtimestamp(t_first / 1000.0)
        last_dt = datetime.fromtimestamp(t_last / 1000.0)
        self.chart_canvas.create_text(
            pad_x, height - 4, anchor="w",
            text=first_dt.strftime("%H:%M"), fill=TEXT_MUTED, font=("Segoe UI", 7),
        )
        self.chart_canvas.create_text(
            width - pad_x, height - 4, anchor="e",
            text=last_dt.strftime("%H:%M"), fill=TEXT_MUTED, font=("Segoe UI", 7),
        )

    # ---------------- 双入口互锁防幽灵右键菜单 ----------------

    def _init_context_menu(self) -> None:
        """初始化右键菜单与 Action Matrix。"""
        self.menu = tk.Menu(self.root, tearoff=0, bg="#2d333b", fg="#e6edf3", activebackground="#388bfd")

    def _text(self, key):
        return t(key, self.config.get("language", "auto"))

    def _menu_spec(self):
        """One action matrix for both the desktop and tray menus."""
        cfg = self.config
        def action(key, callback, checked=None, enabled=True):
            return dict(label=self._text(key), action=callback, checked=checked, enabled=enabled)
        def choices(key, values, current, setter):
            return dict(label=self._text(key), children=[
                dict(label=label, action=lambda value=value: setter(value),
                     checked=value == current, enabled=True) for value, label in values])
        desktop, tray = cfg["showOnDesktop"], cfg["showMenuBarIcon"]
        items = [action("refreshing", self._trigger_immediate_fetch),
            action("showOnDesktop", self._toggle_desktop, desktop, tray or not desktop),
            action("showMenuBar", self._toggle_tray_entry, tray, desktop or not tray),
            action("showChart", self._toggle_chart, cfg["showChart"]),
            action("showDetails", self._toggle_details, cfg["showDetails"]),
            action("alwaysOnTop", self._toggle_topmost, cfg["alwaysOnTop"])]
        lang = resolve_language(cfg.get("language", "auto"))
        names = [(s, SYMBOL_META[s]["name_cn" if lang == "zh" else "name_en"] +
                  (" " + self._text("estTag") if SYMBOL_META[s]["is_estimated"] else "")) for s in SUPPORTED_SYMBOLS]
        items += [choices("symbols", names, cfg["symbol"], self._set_symbol),
            choices("changeBasis", [("prevClose", self._text("prevClose")), ("open", self._text("openPrice"))], cfg["changeBasis"], self._set_change_basis),
            choices("colorMode", [("cny", self._text("cnyColors")), ("intl", self._text("intlColors"))], cfg["colorMode"], self._set_color_mode),
            choices("menu_language", [(v, self._text("menu_lang_" + v)) for v in ("auto", "zh", "en")], cfg["language"], self._set_language),
            choices("refreshInterval", [(v, f"{v} {self._text('seconds')}") for v in VALID_REFRESH_INTERVALS], cfg["refreshSeconds"], self._set_refresh_interval),
            choices("cardWidth", [(v, f"{v} pt") for v in VALID_WIDTHS], cfg["width"], self._set_width),
            choices("cardOpacity", [(v, f"{v:.0%}") for v in (0.60, 0.75, 0.88, 0.95, 1.0)], cfg["opacity"], self._set_opacity),
            action("openConfigFolder", self._open_config_dir), action("reloadConfig", self._reload_config),
            action("clearCache", self._clear_cache), action("resetPos", self._reset_position),
            action("aboutApp", self._show_about), action("viewDisclaimer", self._show_disclaimer),
            action("visitGithub", self._open_github), action("quitApp", self.quit)]
        return items

    def _on_right_click(self, event: tk.Event) -> None:
        self.menu.delete(0, tk.END)
        self._menu_vars = []
        def populate(menu, items):
            for item in items:
                if "children" in item:
                    sub = tk.Menu(menu, tearoff=0)
                    populate(sub, item["children"])
                    menu.add_cascade(label=item["label"], menu=sub)
                else:
                    args = dict(label=item["label"], command=item["action"],
                                state=tk.NORMAL if item["enabled"] else tk.DISABLED)
                    if item["checked"] is not None:
                        var = tk.BooleanVar(value=item["checked"])
                        self._menu_vars.append(var)
                        menu.add_checkbutton(variable=var, **args)
                    else:
                        menu.add_command(**args)
        populate(self.menu, self._menu_spec())
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _build_tray_menu(self):
        def convert(items):
            result = []
            for item in items:
                if "children" in item:
                    result.append(pystray.MenuItem(item["label"], convert(item["children"])))
                else:
                    callback = item["action"]
                    def dispatch(icon, menu_item, callback=callback):
                        self.msg_queue.put(callback)
                    result.append(pystray.MenuItem(item["label"], dispatch,
                        checked=(lambda menu_item, value=item["checked"]: value) if item["checked"] is not None else None,
                        enabled=item["enabled"]))
            return pystray.Menu(*result)
        return convert(self._menu_spec())

    def _set_language(self, language):
        self.config["language"] = language
        save_config(self.config)
        self._update_ui_with_quote()
        self._update_tray()

    def _show_dialog(self, title_key, body):
        dialog = tk.Toplevel(self.root)
        dialog.title(self._text(title_key))
        dialog.iconphoto(True, self.product_icon)
        dialog.transient(self.root)
        from PIL import Image, ImageTk
        icon = ImageTk.PhotoImage(Image.open(resource_path()).resize((64, 64)))
        label = tk.Label(dialog, image=icon)
        label.image = icon
        label.pack(padx=20, pady=(18, 8))
        tk.Label(dialog, text=self._text(title_key), font=("Segoe UI", 13, "bold")).pack()
        tk.Label(dialog, text=body, wraplength=390, justify=tk.CENTER).pack(padx=24, pady=12)
        tk.Button(dialog, text=self._text("ok"), command=dialog.destroy).pack(pady=(0, 16))
        dialog.grab_set()

    def _show_about(self):
        self._show_dialog("about_title", t("about_body", self.config.get("language", "auto"), version=VERSION, copyright=COPYRIGHT))

    def _show_disclaimer(self):
        self._show_dialog("disclaimer_title", DISCLAIMER_CN if resolve_language(self.config.get("language", "auto")) == "zh" else DISCLAIMER_EN)

    def _open_github(self):
        import webbrowser
        webbrowser.open("https://github.com/realsuperj/gold-ticker")

    # ---------------- 托盘集成与双入口防幽灵 ----------------

    def _init_tray(self) -> None:
        """初始化 pystray 任务栏动态宽托盘。"""
        if pystray is None:
            self.config["showMenuBarIcon"] = False
            self.config["showOnDesktop"] = True
            self.root.deiconify()
            return

        if not self.config.get("showMenuBarIcon", True):
            return

        def _setup_tray():
            # 初始图片
            img = create_tray_image(self.current_quote, self.config)
            tip = build_tray_tooltip(self.current_quote, self.config)

            self.tray_icon = pystray.Icon(
                "GoldTicker",
                icon=img,
                title=tip,
                menu=self._build_tray_menu(),
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
            self.tray_icon.menu = self._build_tray_menu()
            self.tray_icon.update_menu()
        except Exception:
            pass

    # ---------------- 菜单动作响应与互锁处理 ----------------

    def _toggle_desktop(self) -> None:
        cur_desktop = bool(self.config.get("showOnDesktop", True))
        cur_tray = bool(self.config.get("showMenuBarIcon", True))

        if not can_toggle_entry(cur_desktop, cur_tray, "desktop"):
            messagebox.showinfo(
                "GoldTicker", self._text("locked"),
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
        cur_tray = bool(self.config.get("showMenuBarIcon", True))

        if not can_toggle_entry(cur_desktop, cur_tray, "tray"):
            messagebox.showinfo(
                "GoldTicker", self._text("locked"),
            )
            return

        new_val = not cur_tray
        self.config["showMenuBarIcon"] = new_val
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
            self.chart_frame.pack(fill=tk.X, before=self.footer_frame)
            self._render_chart()
        else:
            self.chart_frame.pack_forget()
        self._adjust_card_height()

    def _toggle_details(self) -> None:
        val = not self.config.get("showDetails", True)
        self.config["showDetails"] = val
        save_config(self.config)
        if val:
            self.details_frame.pack(fill=tk.X, before=self.chart_frame if self.config["showChart"] else self.footer_frame)
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
        self.current_quote = None
        self._load_cached_points()
        self._update_ui_with_quote()
        self._update_tray()
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
        self.config["refreshSeconds"] = sec
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
        self.intraday_points = [(p["ts"], p["p"]) for p in pts]

    def _record_all_quotes(self, quotes) -> None:
        for s, q in quotes.items():
            if q and not q.error and q.price > 0:
                freeze_day_basis(s, q.prev_close, q.open_price)
                record_price_point(q.price, s)

    def _start_fetch_loop(self) -> None:
        def loop():
            while self.is_running:
                symbol = self.config.get("symbol", SYMBOL_ZS_JCJ)
                try:
                    quotes = self.pricing_engine.sample_all_quotes()
                    self._record_all_quotes(quotes)
                    quote = quotes.get(symbol) or self.pricing_engine.get_cached_quote(symbol)
                    if quote and quote.price > 0:
                        quote = apply_frozen_basis(quote)
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
                    int(self.config.get("refreshSeconds", 30)),
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
                quotes = self.pricing_engine.sample_all_quotes()
                self._record_all_quotes(quotes)
                q = quotes.get(symbol) or self.pricing_engine.get_cached_quote(symbol)
                if q and q.price > 0:
                    q = apply_frozen_basis(q)
                self.msg_queue.put(q)
            except Exception:
                pass
        threading.Thread(target=fetch_now, daemon=True).start()

    def _schedule_gui_update(self) -> None:
        """主线程定时检查消息队列并更新 UI。"""
        try:
            while not self.msg_queue.empty():
                quote = self.msg_queue.get_nowait()
                if callable(quote):
                    quote()
                    continue
                if quote and quote.symbol == self.config["symbol"]:
                    self.current_quote = quote
                    self._load_cached_points()
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
        prefix = ticker_prefix(self.config)
        self.lbl_prefix.config(text=prefix)

        if not is_quote_valid(quote):
            err_text = self._text("fetch_error" if quote and quote.error else "refreshing")
            self.lbl_price.config(text="--.--", fg=TEXT_MUTED)
            self.lbl_delta.config(text="--", fg=TEXT_MUTED)
            self.lbl_footer.config(text=err_text)
            self.lbl_details.config(text="--")
            self._render_chart()
            return

        # 计算涨跌
        change_basis = self.config.get("changeBasis", "prevClose")
        diff, pct = calculate_quote_delta(quote, change_basis)
        color = get_quote_color(diff, self.config.get("colorMode", "cny"))

        # 更新大字价格与涨跌幅
        self.lbl_price.config(text=f"{quote.price:.2f}", fg=TEXT_MAIN)
        sign = "+" if diff > 0 else ""
        self.lbl_delta.config(text=f"{sign}{diff:.2f} ({pct:+.2f}%)", fg=color)

        # 更新明细 (今开 / 昨收 / 最高 / 最低)
        basis_name = self._text("prev_close" if change_basis == "prevClose" else "open_price")
        base_price = quote.prev_close if change_basis == "prevClose" else quote.open_price
        self.lbl_details.config(text=f"{self._text('open_price')}: {quote.open_price:.2f}   {basis_name}: {base_price:.2f}\n"
                                     f"{self._text('high')}: {quote.high:.2f}   {self._text('low')}: {quote.low:.2f}")
        self._render_chart()
        lang = resolve_language(self.config.get("language", "auto"))
        meta = SYMBOL_META[symbol]
        sym_name = meta["name_cn" if lang == "zh" else "name_en"]
        estimate = " " + self._text("estTag") if quote.is_estimated else ""
        self.lbl_footer.config(text=f"{sym_name}{estimate} · {quote.time_str}")

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
