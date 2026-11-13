"""GoldTicker macOS 原生表现层入口 (mac/main.py)。

基于 PyObjC / AppKit 构建原生无边框半透明悬浮窗与 MenuBar 状态栏。
由 core 内核驱动，彻底实现表现层与业务逻辑解耦、双入口互锁防幽灵机制与表现层纯净原则。
"""
from __future__ import annotations

import locale
import math
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保任意工作路径下均能正确定位并导入 core 包
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    get_day_basis,
    load_today_points,
    record_price_point,
)

import objc
from AppKit import (
    NSEvent,
    NSAlert,
    NSAlertFirstButtonReturn,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFloatingWindowLevel,
    NSFont,
    NSFontWeightBold,
    NSFontWeightMedium,
    NSFontWeightRegular,
    NSGradient,
    NSGraphicsContext,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSMutableParagraphStyle,
    NSNormalWindowLevel,
    NSOffState,
    NSOnState,
    NSPoint,
    NSRect,
    NSRectFill,
    NSScreen,
    NSStatusBar,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSVariableStatusItemLength,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
)
from Foundation import NSMakePoint, NSMakeRect, NSMakeSize, NSObject, NSString


# ---------------- 多语言字典 ----------------

from core.i18n import TRANSLATIONS, resolve_language, ticker_prefix, t
from core.product import VERSION, COPYRIGHT, resource_path
from mac.card import draw_card
I18N = {lang: {key: value[lang] for key, value in TRANSLATIONS.items()} for lang in ("zh", "en")}
def get_current_lang(cfg):
    return resolve_language(cfg.get("language", "auto"))


def calc_window_height(cfg: Dict[str, Any]) -> float:
    """根据配置动态计算悬浮窗自适应高度。"""
    h = 9 + 14 + 36 + 17  # 标题栏、主价格大字、涨跌幅行
    if cfg.get("showDetails", True):
        h += 16           # 次要数据行 (高/低/基准)
    if cfg.get("showChart", True):
        h += 2 + 44 + 12  # 走势图区域 (纯净折线画布)
    return h + 12


# ---------------- 悬浮窗绘图视图 ----------------

class GoldCardView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(GoldCardView, self).initWithFrame_(frame)
        if self:
            self.app_controller = None
            self._drag_start_mouse = None
            self._drag_start_win = None
        return self

    @objc.python_method
    def set_controller(self, controller):
        self.app_controller = controller

    # 鼠标拖动与坐标持久化
    def mouseDown_(self, event):
        if not self.window():
            return
        self._drag_start_mouse = NSEvent.mouseLocation()
        self._drag_start_win = self.window().frame().origin

    def mouseDragged_(self, event):
        if not self._drag_start_mouse or not self._drag_start_win or not self.window():
            return
        cur_mouse = NSEvent.mouseLocation()
        dx = cur_mouse.x - self._drag_start_mouse.x
        dy = cur_mouse.y - self._drag_start_mouse.y
        new_origin = NSMakePoint(self._drag_start_win.x + dx, self._drag_start_win.y + dy)
        self.window().setFrameOrigin_(new_origin)

    def mouseUp_(self, event):
        if self.app_controller and self.window():
            origin = self.window().frame().origin
            self.app_controller.config["windowX"] = float(origin.x)
            self.app_controller.config["windowY"] = float(origin.y)
            save_config(self.app_controller.config)
        self._drag_start_mouse = None
        self._drag_start_win = None

    def rightMouseDown_(self, event):
        """右键弹出跨端统一配置菜单。"""
        if self.app_controller:
            self.app_controller.menu_controller.show_menu_for_view(self, event)

    def isFlipped(self):
        return True

    def drawRect_(self, dirtyRect):
        if not self.app_controller:
            return
        self.cfg = self.app_controller.config
        q = self.app_controller.current_quote
        self.quote = {} if not q else {
            "price": q.price, "prevClose": q.prev_close, "open": q.open_price,
            "high": q.high, "low": q.low, "source": q.symbol,
            "sourceName": SYMBOL_META[q.symbol]["name_cn"] + (" (点差估算)" if q.is_estimated else ""),
            "error": q.error,
        }
        self.samples = load_today_points(q.symbol if q else self.cfg["symbol"])
        draw_card(self)


# ---------------- 统一菜单控制器 (实现 Menu Action Matrix 与双入口互锁) ----------------

class MenuController(NSObject):
    def initWithAppController_(self, app_controller):
        self = objc.super(MenuController, self).init()
        if self:
            self.app = app_controller
        return self

    @objc.python_method
    def show_menu_for_view(self, view, event):
        menu = self.build_menu()
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, view)

    def menuNeedsUpdate_(self, menu):
        """每次打开菜单前按最新 config 重绘勾选/互锁状态。"""
        menu.removeAllItems()
        self._populate_menu(menu)

    @objc.python_method
    def build_menu(self) -> NSMenu:
        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)
        menu.setDelegate_(self)
        self._populate_menu(menu)
        return menu

    @objc.python_method
    def _mark_radio_repr(self, sender, selected):
        parent = sender.menu()
        if not parent:
            return
        for item in parent.itemArray():
            if item.isSeparatorItem():
                continue
            obj = item.representedObject()
            if obj is None:
                continue
            item.setState_(NSOnState if str(obj) == str(selected) else NSOffState)

    @objc.python_method
    def _mark_radio_tag(self, sender, selected_tag):
        parent = sender.menu()
        if not parent:
            return
        for item in parent.itemArray():
            if item.isSeparatorItem():
                continue
            item.setState_(NSOnState if int(item.tag()) == int(selected_tag) else NSOffState)

    @objc.python_method
    def _populate_menu(self, menu: NSMenu) -> None:
        cfg = self.app.config
        quote = self.app.current_quote
        lang = get_current_lang(cfg)
        txt = I18N[lang]

        # 1. 顶部只读概览与点击刷新
        if quote and quote.price > 0:
            meta = SYMBOL_META.get(quote.symbol, SYMBOL_META[SYMBOL_AU9999])
            sname = meta["name_cn"] if lang == "zh" else meta["name_en"]
            header_title = f"{sname} {quote.price:.2f} ({quote.change:+.2f}%)"
        else:
            header_title = txt["refreshing"]

        head_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(header_title, "onForceRefresh:", "")
        head_item.setTarget_(self)
        head_item.setEnabled_(True)
        menu.addItem_(head_item)

        menu.addItem_(NSMenuItem.separatorItem())

        # 2. 双入口显隐控制（互锁防幽灵核心实现）
        show_desktop = cfg.get("showOnDesktop", True)
        show_menubar = cfg.get("showMenuBarIcon", True)

        m_desktop = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["showOnDesktop"], "onToggleDesktop:", "")
        m_desktop.setTarget_(self)
        m_desktop.setState_(NSOnState if show_desktop else NSOffState)
        # 互锁规则：若当前菜单栏已关闭，桌面入口置灰锁定禁止取消！
        m_desktop.setEnabled_(show_menubar)
        menu.addItem_(m_desktop)

        m_menubar = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["showMenuBar"], "onToggleMenuBar:", "")
        m_menubar.setTarget_(self)
        m_menubar.setState_(NSOnState if show_menubar else NSOffState)
        # 互锁规则：若当前桌面窗口已关闭，菜单栏入口置灰锁定禁止取消！
        m_menubar.setEnabled_(show_desktop)
        menu.addItem_(m_menubar)

        m_top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["alwaysOnTop"], "onToggleTop:", "")
        m_top.setTarget_(self)
        m_top.setState_(NSOnState if cfg.get("alwaysOnTop", True) else NSOffState)
        menu.addItem_(m_top)

        menu.addItem_(NSMenuItem.separatorItem())

        # 3. 视觉折叠与层级
        m_chart = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["showChart"], "onToggleChart:", "")
        m_chart.setTarget_(self)
        m_chart.setState_(NSOnState if cfg.get("showChart", True) else NSOffState)
        menu.addItem_(m_chart)

        m_details = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["showDetails"], "onToggleDetails:", "")
        m_details.setTarget_(self)
        m_details.setState_(NSOnState if cfg.get("showDetails", True) else NSOffState)
        menu.addItem_(m_details)

        # 宽度二级子菜单
        w_sub = NSMenu.alloc().init()
        cur_w = int(cfg.get("width", 216))
        for w_val in VALID_WIDTHS:
            wi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"{w_val} pt", "onSelectWidth:", "")
            wi.setTarget_(self)
            wi.setTag_(w_val)
            wi.setState_(NSOnState if cur_w == w_val else NSOffState)
            w_sub.addItem_(wi)
        m_width = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["cardWidth"], None, "")
        m_width.setSubmenu_(w_sub)
        menu.addItem_(m_width)

        # 透明度二级子菜单
        op_sub = NSMenu.alloc().init()
        cur_op = float(cfg.get("opacity", 0.88))
        for op_val in (0.60, 0.75, 0.88, 0.95, 1.00):
            opi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(f"{int(op_val*100)}%", "onSelectOpacity:", "")
            opi.setTarget_(self)
            opi.setTag_(int(op_val * 100))
            opi.setState_(NSOnState if math.isclose(cur_op, op_val, abs_tol=0.03) else NSOffState)
            op_sub.addItem_(opi)
        m_op = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["cardOpacity"], None, "")
        m_op.setSubmenu_(op_sub)
        menu.addItem_(m_op)

        # 重置窗口位置
        m_reset = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["resetPos"], "onResetPos:", "")
        m_reset.setTarget_(self)
        menu.addItem_(m_reset)

        menu.addItem_(NSMenuItem.separatorItem())

        # 4. 行情标的子菜单
        sym_sub = NSMenu.alloc().init()
        cur_sym = cfg.get("symbol", SYMBOL_AU9999)
        for sym_id in SUPPORTED_SYMBOLS:
            meta = SYMBOL_META[sym_id]
            title = meta["name_cn"] if lang == "zh" else meta["name_en"]
            if meta["is_estimated"]:
                title += f" {txt['estTag']}"
            if sym_id == SYMBOL_XAU_USD:
                sym_sub.addItem_(NSMenuItem.separatorItem())
            si = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "onSelectSymbol:", "")
            si.setTarget_(self)
            si.setRepresentedObject_(sym_id)
            si.setState_(NSOnState if cur_sym == sym_id else NSOffState)
            sym_sub.addItem_(si)
        m_symbols = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["symbols"], None, "")
        m_symbols.setSubmenu_(sym_sub)
        menu.addItem_(m_symbols)

        # 涨跌对比子菜单
        basis_sub = NSMenu.alloc().init()
        cur_basis = cfg.get("changeBasis", "prevClose")
        b_prev = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["prevClose"], "onSelectBasis:", "")
        b_prev.setTarget_(self); b_prev.setRepresentedObject_("prevClose")
        b_prev.setState_(NSOnState if cur_basis == "prevClose" else NSOffState)
        basis_sub.addItem_(b_prev)
        b_open = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["openPrice"], "onSelectBasis:", "")
        b_open.setTarget_(self); b_open.setRepresentedObject_("open")
        b_open.setState_(NSOnState if cur_basis == "open" else NSOffState)
        basis_sub.addItem_(b_open)
        m_basis = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["changeBasis"], None, "")
        m_basis.setSubmenu_(basis_sub)
        menu.addItem_(m_basis)

        # 涨跌配色子菜单
        color_sub = NSMenu.alloc().init()
        cur_color = cfg.get("colorMode", "cny")
        c_cny = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["cnyColors"], "onSelectColor:", "")
        c_cny.setTarget_(self); c_cny.setRepresentedObject_("cny")
        c_cny.setState_(NSOnState if cur_color == "cny" else NSOffState)
        color_sub.addItem_(c_cny)
        c_intl = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["intlColors"], "onSelectColor:", "")
        c_intl.setTarget_(self); c_intl.setRepresentedObject_("intl")
        c_intl.setState_(NSOnState if cur_color == "intl" else NSOffState)
        color_sub.addItem_(c_intl)
        m_color = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["colorMode"], None, "")
        m_color.setSubmenu_(color_sub)
        menu.addItem_(m_color)

        language_menu = NSMenu.alloc().init()
        for choice in ("auto", "zh", "en"):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(t("menu_lang_" + choice, lang), "onSelectLanguage:", "")
            item.setTarget_(self)
            item.setRepresentedObject_(choice)
            item.setState_(NSOnState if cfg.get("language", "auto") == choice else NSOffState)
            language_menu.addItem_(item)
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(t("menu_language", lang), None, "")
        item.setSubmenu_(language_menu)
        menu.addItem_(item)

        # 刷新频率子菜单 (严格 >= 10 秒)
        ref_sub = NSMenu.alloc().init()
        cur_ref = int(cfg.get("refreshSeconds", 10))
        for ref_s in VALID_REFRESH_INTERVALS:
            label = f"{ref_s} {txt['seconds']}"
            if ref_s == 10:
                label += f" ({txt['recommend']})"
            ri = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, "onSelectRefresh:", "")
            ri.setTarget_(self); ri.setTag_(ref_s)
            ri.setState_(NSOnState if cur_ref == ref_s else NSOffState)
            ref_sub.addItem_(ri)
        m_ref = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["refreshInterval"], None, "")
        m_ref.setSubmenu_(ref_sub)
        menu.addItem_(m_ref)

        menu.addItem_(NSMenuItem.separatorItem())

        # 5. 高级配置与关于
        adv_sub = NSMenu.alloc().init()
        m_folder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["openConfigFolder"], "onOpenFolder:", "")
        m_folder.setTarget_(self); adv_sub.addItem_(m_folder)
        m_reload = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["reloadConfig"], "onReloadConfig:", "")
        m_reload.setTarget_(self); adv_sub.addItem_(m_reload)
        m_clear = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["clearCache"], "onClearCache:", "")
        m_clear.setTarget_(self); adv_sub.addItem_(m_clear)
        m_adv = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["advanced"], None, "")
        m_adv.setSubmenu_(adv_sub)
        menu.addItem_(m_adv)

        about_sub = NSMenu.alloc().init()
        m_abt = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["aboutApp"], "onAbout:", "")
        m_abt.setTarget_(self); about_sub.addItem_(m_abt)
        m_disc = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["viewDisclaimer"], "onDisclaimer:", "")
        m_disc.setTarget_(self); about_sub.addItem_(m_disc)
        m_gh = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["visitGithub"], "onGithub:", "")
        m_gh.setTarget_(self); about_sub.addItem_(m_gh)
        m_about = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["aboutMenu"], None, "")
        m_about.setSubmenu_(about_sub)
        menu.addItem_(m_about)

        menu.addItem_(NSMenuItem.separatorItem())

        # 6. 退出
        m_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(txt["quitApp"], "onQuit:", "q")
        m_quit.setTarget_(self)
        menu.addItem_(m_quit)

    # 动作响应
    def onForceRefresh_(self, sender):
        self.app.trigger_fetch_now()

    def onToggleDesktop_(self, sender):
        cur = self.app.config.get("showOnDesktop", True)
        self.app.config["showOnDesktop"] = not cur
        save_config(self.app.config)
        self.app.apply_display_visibility()

    def onToggleMenuBar_(self, sender):
        cur = self.app.config.get("showMenuBarIcon", True)
        self.app.config["showMenuBarIcon"] = not cur
        save_config(self.app.config)
        self.app.apply_display_visibility()

    def onToggleChart_(self, sender):
        cur = self.app.config.get("showChart", True)
        self.app.config["showChart"] = not cur
        save_config(self.app.config)
        sender.setState_(NSOnState if self.app.config["showChart"] else NSOffState)
        self.app.update_window_size()
        self.app.refresh_status_menu()

    def onToggleDetails_(self, sender):
        cur = self.app.config.get("showDetails", True)
        self.app.config["showDetails"] = not cur
        save_config(self.app.config)
        sender.setState_(NSOnState if self.app.config["showDetails"] else NSOffState)
        self.app.update_window_size()
        self.app.refresh_status_menu()

    def onToggleTop_(self, sender):
        cur = self.app.config.get("alwaysOnTop", True)
        self.app.config["alwaysOnTop"] = not cur
        save_config(self.app.config)
        sender.setState_(NSOnState if self.app.config["alwaysOnTop"] else NSOffState)
        self.app.apply_window_level()
        self.app.refresh_status_menu()

    def onSelectWidth_(self, sender):
        w = int(sender.tag())
        self.app.config["width"] = w
        save_config(self.app.config)
        self._mark_radio_tag(sender, w)
        self.app.update_window_size()
        self.app.refresh_status_menu()

    def onSelectOpacity_(self, sender):
        op = float(sender.tag()) / 100.0
        self.app.config["opacity"] = op
        save_config(self.app.config)
        self._mark_radio_tag(sender, int(sender.tag()))
        self.app.card_view.setNeedsDisplay_(True)
        self.app.refresh_status_menu()

    def onResetPos_(self, sender):
        self.app.config["windowX"] = -1
        self.app.config["windowY"] = -1
        save_config(self.app.config)
        self.app.position_window_default()

    def onSelectSymbol_(self, sender):
        sym = str(sender.representedObject())
        self.app.config["symbol"] = sym
        save_config(self.app.config)
        self._mark_radio_repr(sender, sym)
        # 先上屏缓存/本地末点，避免清空后干等网络
        cached = default_engine.get_cached_quote(sym)
        if cached and cached.price > 0:
            self.app.current_quote = apply_frozen_basis(cached)
        else:
            pts = load_today_points(sym)
            if pts:
                last = pts[-1]
                meta = SYMBOL_META.get(sym, SYMBOL_META[SYMBOL_AU9999])
                stub = QuoteData(
                    symbol=sym, price=float(last["p"]), prev_close=0.0, open_price=0.0,
                    high=float(last["p"]), low=float(last["p"]), change=0.0, change_pct=0.0,
                    time_str=str(last.get("t") or "--:--"), source_id="cache",
                    source_name=meta["name_cn"], is_estimated=meta.get("is_estimated", False),
                )
                self.app.current_quote = apply_frozen_basis(stub)
        self.app.apply_all_config()
        self.app.trigger_fetch_now(force=True)

    def onSelectBasis_(self, sender):
        basis = str(sender.representedObject())
        self.app.config["changeBasis"] = basis
        save_config(self.app.config)
        self._mark_radio_repr(sender, basis)
        self.app.card_view.setNeedsDisplay_(True)
        self.app.update_status_bar()

    def onSelectColor_(self, sender):
        cm = str(sender.representedObject())
        self.app.config["colorMode"] = cm
        save_config(self.app.config)
        self._mark_radio_repr(sender, cm)
        self.app.card_view.setNeedsDisplay_(True)
        self.app.refresh_status_menu()

    def onSelectLanguage_(self, sender):
        self.app.config["language"] = str(sender.representedObject())
        save_config(self.app.config)
        self._mark_radio_repr(sender, self.app.config["language"])
        self.app.apply_all_config()

    def onSelectRefresh_(self, sender):
        ref = int(sender.tag())
        self.app.config["refreshSeconds"] = max(MIN_REFRESH_SECONDS, ref)
        save_config(self.app.config)
        self._mark_radio_tag(sender, self.app.config["refreshSeconds"])
        self.app.refresh_status_menu()

    def onOpenFolder_(self, sender):
        subprocess.run(["open", str(get_app_data_dir())])

    def onReloadConfig_(self, sender):
        self.app.config = load_config()
        self.app.apply_all_config()

    def onClearCache_(self, sender):
        clear_intraday_cache()
        self.app.card_view.setNeedsDisplay_(True)

    @objc.python_method
    def make_alert(self, title, body):
        lang = get_current_lang(self.app.config)
        alert = NSAlert.alloc().init()
        alert.setIcon_(NSImage.alloc().initWithContentsOfFile_(str(resource_path())))
        alert.setMessageText_(t(title, lang))
        alert.setInformativeText_(body)
        alert.addButtonWithTitle_(t("ok", lang))
        return alert

    def onAbout_(self, sender):
        lang = get_current_lang(self.app.config)
        self.make_alert("about_title", t("about_body", lang, version=VERSION, copyright=COPYRIGHT)).runModal()

    def onDisclaimer_(self, sender):
        lang = get_current_lang(self.app.config)
        text = DISCLAIMER_CN if lang == "zh" else DISCLAIMER_EN
        self.make_alert("disclaimer_title", text).runModal()

    def onGithub_(self, sender):
        subprocess.run(["open", "https://github.com/realsuperj/gold-ticker"])

    def onQuit_(self, sender):
        NSApplication.sharedApplication().terminate_(self)


# ---------------- 主应用程序控制器 ----------------

class GoldTickerApp:
    def __init__(self):
        self.config = load_config()
        self.current_quote: Optional[QuoteData] = None
        self.window: Optional[NSWindow] = None
        self.card_view: Optional[GoldCardView] = None
        self.status_item: Optional[Any] = None
        self.menu_controller = MenuController.alloc().initWithAppController_(self)
        self._is_fetching = False
        self._fetch_gen = 0

    def setup_ui(self):
        # 1. 初始化无边框半透明窗口
        w = float(self.config.get("width", 216))
        h = calc_window_height(self.config)
        rect = NSMakeRect(100, 100, w, h)

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            0,  # 无边框 Borderless
            NSBackingStoreBuffered,
            False,
        )
        self.window.setOpaque_(False)
        self.window.setBackgroundColor_(NSColor.clearColor())
        self.window.setMovableByWindowBackground_(False)
        self.window.setHasShadow_(True)
        self.window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorFullScreenAuxiliary |
            NSWindowCollectionBehaviorStationary
        )

        self.card_view = GoldCardView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        self.card_view.set_controller(self)
        self.window.setContentView_(self.card_view)

        # 2. 初始化 MenuBar 状态栏
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = self.status_item.button()
        if button:
            button.setTarget_(self.menu_controller)
            button.setAction_("onForceRefresh:")
            # 挂载右键或点击菜单
            self.status_item.setMenu_(self.menu_controller.build_menu())

        # 3. 初始摆放位置与层级
        self.position_window_default()
        self.apply_all_config()

    def position_window_default(self):
        if not self.window:
            return
        wx = float(self.config.get("windowX", -1))
        wy = float(self.config.get("windowY", -1))
        w = float(self.config.get("width", 216))
        h = calc_window_height(self.config)

        main_screen = NSScreen.mainScreen()
        screen_frame = main_screen.visibleFrame() if main_screen else NSMakeRect(0, 0, 1440, 900)

        if wx < 0 or wy < 0:
            # 屏幕右上角默认位置 (离右边 24pt，顶边 24pt)
            new_x = screen_frame.origin.x + screen_frame.size.width - w - 24.0
            new_y = screen_frame.origin.y + screen_frame.size.height - h - 24.0
        else:
            new_x = wx
            new_y = wy

        self.window.setFrame_display_(NSMakeRect(new_x, new_y, w, h), True)

    def update_window_size(self):
        if not self.window or not self.card_view:
            return
        w = float(self.config.get("width", 216))
        h = calc_window_height(self.config)
        origin = self.window.frame().origin
        self.window.setFrame_display_(NSMakeRect(origin.x, origin.y, w, h), True)
        self.card_view.setFrame_(NSMakeRect(0, 0, w, h))
        self.card_view.setNeedsDisplay_(True)

    def apply_window_level(self):
        if not self.window:
            return
        is_top = self.config.get("alwaysOnTop", True)
        self.window.setLevel_(NSFloatingWindowLevel if is_top else NSNormalWindowLevel)

    def apply_display_visibility(self):
        show_desktop = self.config.get("showOnDesktop", True)
        show_menubar = self.config.get("showMenuBarIcon", True)

        if self.window:
            if show_desktop:
                self.window.orderFront_(None)
            else:
                self.window.orderOut_(None)

        if self.status_item:
            self.status_item.setVisible_(show_menubar)

        self.refresh_status_menu()

    def refresh_status_menu(self):
        if self.status_item:
            self.status_item.setMenu_(self.menu_controller.build_menu())

    def apply_all_config(self):
        self.update_window_size()
        self.apply_window_level()
        self.apply_display_visibility()
        self.update_status_bar()

    def update_status_bar(self):
        if not self.status_item:
            return
        quote = self.current_quote
        if not quote or quote.price <= 0:
            self.status_item.button().setTitle_(ticker_prefix(self.config) + " --")
            self.refresh_status_menu()
            return

        lang = get_current_lang(self.config)
        prefix = "金" if lang == "zh" else "Au"

        basis = self.config.get("changeBasis", "prevClose")
        base_price = quote.prev_close if basis == "prevClose" else quote.open_price
        chg = (quote.price - base_price) if base_price > 0 else 0.0
        pct = (chg / base_price * 100.0) if base_price > 0 else 0.0

        bar_text = f"{prefix} {quote.price:.2f} {pct:+.2f}%"
        self.status_item.button().setTitle_(bar_text)
        self.refresh_status_menu()

    def trigger_fetch_now(self, force: bool = False):
        # 切标的 force=True：不排队等待旧请求，直接开新一代取数
        if self._is_fetching and not force:
            return
        self._fetch_gen += 1
        gen = self._fetch_gen
        self._is_fetching = True
        threading.Thread(target=self._async_fetch, args=(gen,), daemon=True).start()

    def _async_fetch(self, gen: int):
        self._is_fetching = True
        try:
            sym = self.config.get("symbol", SYMBOL_AU9999)
            # 一轮采样写入全部标的，避免只记当前标的造成分时断层
            quotes = default_engine.sample_all_quotes()
            if gen != self._fetch_gen:
                return
            for s, q in quotes.items():
                if q and q.price > 0 and not q.error:
                    freeze_day_basis(s, q.prev_close, q.open_price)
                    record_price_point(q.price, s)
            quote = quotes.get(sym) or default_engine.get_cached_quote(sym)
            if quote and quote.price > 0:
                quote = apply_frozen_basis(quote)
            if gen != self._fetch_gen or sym != self.config.get("symbol", SYMBOL_AU9999):
                return
            if quote is not None:
                self.current_quote = quote
            from PyObjCTools import AppHelper
            AppHelper.callAfter(self.perform_ui_update_on_main)
        except Exception as e:
            sys.stderr.write(f"Fetch error: {e}\n")
        finally:
            if gen == self._fetch_gen:
                self._is_fetching = False

    def perform_ui_update_on_main(self):
        def _update():
            if self.card_view:
                self.card_view.setNeedsDisplay_(True)
            self.update_status_bar()
        if threading.current_thread() is threading.main_thread():
            _update()
        else:
            # 借由 card_view 触发主线程更新
            pass

    def run_poll_loop(self):
        """后台轮询定时线程。"""
        cleanup_old_history(keep_days=3)
        self.trigger_fetch_now()

        while True:
            interval = max(MIN_REFRESH_SECONDS, int(self.config.get("refreshSeconds", 10)))
            time.sleep(interval)
            self.trigger_fetch_now()


def main():
    app = NSApplication.sharedApplication()
    app.setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(str(resource_path())))
    # Accessory 模式：不占 Dock 栏，常驻后台
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    ticker = GoldTickerApp()
    ticker.setup_ui()

    # 启动后台轮询守护线程
    t = threading.Thread(target=ticker.run_poll_loop, daemon=True)
    t.start()

    app.run()


if __name__ == "__main__":
    main()
