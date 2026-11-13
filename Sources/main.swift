//
//  GoldTicker — 桌面置顶半透明金价悬浮窗
//  价格来源：浙商银行积存金（元 / 克），接口 api.tangdouz.com/a/zsgold.php
//  走势图：本地按刷新间隔采样累积当日分时（跨重启保留），无需第三方分时源
//

import Cocoa
import CoreFoundation

let CFG_DIR = (("~/Library/Application Support/GoldTicker") as NSString).expandingTildeInPath
let CFG_PATH = CFG_DIR + "/config.json"
let PRICE_URL = "https://api.tangdouz.com/a/zsgold.php"
let UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

func ensureDir() {
    try? FileManager.default.createDirectory(atPath: CFG_DIR, withIntermediateDirectories: true)
}

// MARK: - 配置

final class Config {
    var showOnDesktop = true          // 是否显示到桌面（悬浮窗开关）
    var showChart = true              // 是否显示今日走势图
    var showDetails = true            // 是否显示最高/最低
    var alwaysOnTop = true
    var opacity: Double = 0.88
    var refreshSeconds: Double = 10
    var width: CGFloat = 216
    var fontScale: CGFloat = 1.0
    var showMenuBarIcon = true
    var windowX: CGFloat = -1
    var windowY: CGFloat = -1

    var height: CGFloat {
        var h: CGFloat = 9 + 14 + 36 + 17          // title + price + change
        if showDetails { h += 16 }
        if showChart { h += 2 + 48 + 12 }
        h += 8
        return h
    }

    static func load() -> Config {
        let c = Config()
        guard let data = FileManager.default.contents(atPath: CFG_PATH),
              let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            ensureDir()
            c.save()
            return c
        }
        func b(_ k: String) -> Bool? { obj[k] as? Bool }
        func d(_ k: String) -> Double? { obj[k] as? Double }

        if let v = b("showOnDesktop") { c.showOnDesktop = v }
        if let v = b("showChart") { c.showChart = v }
        if let v = b("showDetails") { c.showDetails = v }
        if let v = b("alwaysOnTop") { c.alwaysOnTop = v }
        if let v = b("showMenuBarIcon") { c.showMenuBarIcon = v }
        if let v = d("opacity") { c.opacity = min(max(v, 0.25), 1.0) }
        if let v = d("refreshSeconds"), v >= 2 { c.refreshSeconds = v }
        if let v = d("width"), v >= 140, v <= 480 { c.width = CGFloat(v) }
        if let v = d("fontScale"), v > 0.5, v < 2.0 { c.fontScale = CGFloat(v) }
        if let v = d("windowX") { c.windowX = CGFloat(v) }
        if let v = d("windowY") { c.windowY = CGFloat(v) }
        return c
    }

    func save() {
        ensureDir()
        let dict: [String: Any] = [
            "showOnDesktop": showOnDesktop,
            "showChart": showChart,
            "showDetails": showDetails,
            "alwaysOnTop": alwaysOnTop,
            "opacity": opacity,
            "refreshSeconds": refreshSeconds,
            "width": Double(width),
            "fontScale": Double(fontScale),
            "showMenuBarIcon": showMenuBarIcon,
            "windowX": Double(windowX),
            "windowY": Double(windowY)
        ]
        if let data = try? JSONSerialization.data(withJSONObject: dict,
                                                  options: [.prettyPrinted, .sortedKeys]) {
            try? data.write(to: URL(fileURLWithPath: CFG_PATH))
        }
    }
}

// MARK: - 行情模型

struct Quote {
    var price: Double = 0          // 元 / 克
    var prevClose: Double = 0
    var open: Double = 0
    var high: Double = 0
    var low: Double = 0
    var change: Double = 0
    var changePct: Double = 0
    var time: String = "--:--"
    var updated: Date? = nil
    var error: String? = nil

    var hasData: Bool { price > 0 }
    var isUp: Bool { change >= 0 }
}

struct Sample: Codable {
    let t: String      // HH:mm
    let p: Double
}

// MARK: - 当日分时采样（本地累积）

final class IntradayStore {
    private(set) var samples: [Sample] = []
    private var dayKey: String = ""

    private static func dayString(_ date: Date = Date()) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }

    private static func clockString(_ date: Date = Date()) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "HH:mm"
        return f.string(from: date)
    }

    private var filePath: String { CFG_DIR + "/intraday-\(dayKey).json" }

    init() { reload() }

    func reload() {
        dayKey = IntradayStore.dayString()
        samples = []
        guard let data = FileManager.default.contents(atPath: filePath),
              let arr = (try? JSONDecoder().decode([Sample].self, from: data)) else { return }
        samples = arr
    }

    /// 追加一个采样点（同一分钟只保留最后一个值）
    func append(_ price: Double, at date: Date = Date()) {
        guard price > 0 else { return }
        let key = IntradayStore.dayString(date)
        if key != dayKey {                 // 跨天重置
            rotateOldFiles()
            dayKey = key
            samples = []
        }
        let t = IntradayStore.clockString(date)
        if let last = samples.last, last.t == t {
            samples[samples.count - 1] = Sample(t: t, p: price)
        } else {
            samples.append(Sample(t: t, p: price))
        }
        save()
    }

    private func save() {
        ensureDir()
        if let data = try? JSONEncoder().encode(samples) {
            try? data.write(to: URL(fileURLWithPath: filePath))
        }
    }

    /// 只保留最近 3 天的分时文件
    private func rotateOldFiles() {
        guard let files = try? FileManager.default.contentsOfDirectory(atPath: CFG_DIR) else { return }
        let mine = files.filter { $0.hasPrefix("intraday-") && $0.hasSuffix(".json") }.sorted()
        if mine.count > 3 {
            for name in mine.prefix(mine.count - 3) {
                try? FileManager.default.removeItem(atPath: CFG_DIR + "/" + name)
            }
        }
    }
}

// MARK: - 网络

enum Net {
    static func get(_ url: String, completion: @escaping (String?) -> Void) {
        guard let u = URL(string: url) else { completion(nil); return }
        var req = URLRequest(url: u)
        req.timeoutInterval = 12
        req.setValue(UA, forHTTPHeaderField: "User-Agent")
        req.setValue("https://www.tangdouz.com/", forHTTPHeaderField: "Referer")
        URLSession.shared.dataTask(with: req) { data, resp, err in
            guard err == nil, let data = data, !data.isEmpty else { completion(nil); return }
            let enc = CFStringConvertEncodingToNSStringEncoding(
                CFStringEncoding(CFStringEncodings.GB_18030_2000.rawValue))
            let s = String(data: data, encoding: String.Encoding(rawValue: enc))
                ?? String(data: data, encoding: .utf8)
            completion(s)
        }.resume()
    }

    static func firstNumber(_ s: String) -> Double? {
        var cur = ""
        for ch in s {
            if ch.isNumber || ch == "." { cur.append(ch) }
            else if ch == "-" && cur.isEmpty { cur.append(ch) }
            else if !cur.isEmpty { break }
        }
        return Double(cur)
    }

    static func field(_ text: String, _ key: String) -> String? {
        for line in text.split(separator: "\n") {
            let l = String(line)
            if l.contains(key + ":") || l.contains(key + "：") {
                return l
            }
        }
        return nil
    }
}

final class Fetcher {
    func fetchPrice(completion: @escaping (Quote) -> Void) {
        Net.get(PRICE_URL) { text in
            DispatchQueue.main.async {
                guard let text = text else {
                    var q = Quote()
                    q.error = "网络请求失败，重试中…"
                    completion(q)
                    return
                }
                var q = Quote()
                if let l = Net.field(text, "最新价格") { q.price = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "前收盘价") { q.prevClose = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "开盘价") { q.open = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "最高价") { q.high = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "最低价") { q.low = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "涨跌额") { q.change = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "涨跌幅") { q.changePct = Net.firstNumber(l) ?? 0 }
                if let l = Net.field(text, "更新时间") {
                    let parts = l.components(separatedBy: " ").last ?? ""
                    let t = parts.components(separatedBy: ":")
                    if t.count >= 2 {
                        q.time = String(format: "%02d:%02d",
                                        Int(t[0].trimmingCharacters(in: .whitespaces)) ?? 0,
                                        Int(t[1]) ?? 0)
                    }
                }
                guard q.price > 0 else {
                    q.error = "解析失败，重试中…"
                    completion(q)
                    return
                }
                if q.prevClose <= 0 { q.prevClose = q.open > 0 ? q.open : q.price - q.change }
                if q.change == 0 { q.change = q.price - q.prevClose }
                if q.changePct == 0, q.prevClose > 0 {
                    q.changePct = q.change / q.prevClose * 100
                }
                q.updated = Date()
                q.error = nil
                completion(q)
            }
        }
    }

    func fetchPriceSync() -> Quote {
        let sem = DispatchSemaphore(value: 0)
        var result = Quote()
        fetchPrice { q in
            result = q
            sem.signal()
        }
        _ = sem.wait(timeout: .now() + 20)
        return result
    }
}

// MARK: - 视图

final class TickerView: NSView {
    var cfg: Config
    var quote = Quote()
    var samples: [Sample] = []

    private var dragStartMouse = NSPoint.zero
    private var dragStartOrigin = NSPoint.zero
    private var menuBuilder: (() -> NSMenu)?

    init(cfg: Config) {
        self.cfg = cfg
        super.init(frame: NSRect(x: 0, y: 0, width: cfg.width, height: cfg.height))
    }
    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }

    var upColor: NSColor { NSColor(srgbRed: 1.00, green: 0.34, blue: 0.30, alpha: 1) }
    var downColor: NSColor { NSColor(srgbRed: 0.28, green: 0.87, blue: 0.53, alpha: 1) }

    private func text(_ s: String, x: CGFloat, top: CGFloat, w: CGFloat, h: CGFloat,
                      size: CGFloat, weight: NSFont.Weight = .regular,
                      color: NSColor, align: NSTextAlignment = .left, mono: Bool = false) {
        let f: NSFont = mono
            ? NSFont.monospacedDigitSystemFont(ofSize: size * cfg.fontScale, weight: weight)
            : NSFont.systemFont(ofSize: size * cfg.fontScale, weight: weight)
        let ps = NSMutableParagraphStyle()
        ps.alignment = align
        ps.lineBreakMode = .byClipping
        let attrs: [NSAttributedString.Key: Any] = [
            .font: f, .foregroundColor: color, .paragraphStyle: ps
        ]
        (s as NSString).draw(in: NSRect(x: x, y: top, width: w, height: h), withAttributes: attrs)
    }

    override func draw(_ dirtyRect: NSRect) {
        let W = bounds.width, H = bounds.height
        let pad: CGFloat = 11

        let bg = NSBezierPath(roundedRect: NSRect(x: 0.5, y: 0.5, width: W - 1, height: H - 1),
                              xRadius: 14, yRadius: 14)
        NSColor(srgbRed: 0.07, green: 0.08, blue: 0.10, alpha: 0.74).setFill()
        bg.fill()
        NSColor(white: 1, alpha: 0.10).setStroke()
        bg.lineWidth = 1
        bg.stroke()

        guard quote.hasData else {
            text(quote.error ?? "正在获取积存金价格…", x: pad, top: H / 2 - 9, w: W - pad * 2, h: 18,
                 size: 11, color: NSColor(white: 1, alpha: 0.55), align: .center)
            return
        }

        let tone = quote.isUp ? upColor : downColor
        var top: CGFloat = 9

        text("浙商积存金 · 元/克", x: pad, top: top, w: 150, h: 12,
             size: 9.5, color: NSColor(white: 1, alpha: 0.55))
        text(quote.time, x: W - pad - 80, top: top, w: 80, h: 12,
             size: 9.5, color: NSColor(white: 1, alpha: 0.40), align: .right)
        top += 14

        text(String(format: "%.2f", quote.price), x: pad - 1, top: top, w: W - pad * 2 + 2, h: 36,
             size: 30, weight: .bold, color: tone, mono: true)
        top += 36

        let sign = quote.change >= 0 ? "+" : ""
        let cs = String(format: "%@%.2f  %@%.2f%%", sign, quote.change, sign, quote.changePct)
        text(cs, x: pad, top: top, w: W - pad * 2, h: 14,
             size: 11, weight: .medium, color: tone.withAlphaComponent(0.92))
        top += 17

        if cfg.showDetails {
            let dim = NSColor(white: 1, alpha: 0.38)
            text(String(format: "高 %.2f", quote.high), x: pad, top: top, w: 80, h: 12,
                 size: 9, color: dim, mono: true)
            text(String(format: "低 %.2f", quote.low), x: pad + 78, top: top, w: 80, h: 12,
                 size: 9, color: dim, mono: true)
            text(String(format: "昨收 %.2f", quote.prevClose), x: W - pad - 100, top: top, w: 100, h: 12,
                 size: 9, color: dim, align: .right, mono: true)
            top += 16
        }

        if cfg.showChart {
            drawChart(NSRect(x: pad, y: top + 2, width: W - pad * 2, height: 48), tone: tone)
            top += 50
            let first = samples.first?.t ?? ""
            let last = samples.last?.t ?? ""
            text(first, x: pad, top: top, w: 80, h: 11, size: 8.5,
                 color: NSColor(white: 1, alpha: 0.32))
            text(samples.isEmpty ? "" : ("\(last) · \(samples.count) 点"),
                 x: W - pad - 110, top: top, w: 110, h: 11, size: 8.5,
                 color: NSColor(white: 1, alpha: 0.32), align: .right)
        }
    }

    private func drawChart(_ rect: NSRect, tone: NSColor) {
        let pts = samples.map { $0.p }
        guard pts.count > 1 else {
            text("今日走势累积中（每 \(Int(cfg.refreshSeconds)) 秒采样）",
                 x: rect.minX, top: rect.midY - 7, w: rect.width, h: 14,
                 size: 8.5, color: NSColor(white: 1, alpha: 0.30), align: .center)
            return
        }
        var lo = pts.min()!, hi = pts.max()!
        var inset = (hi - lo) * 0.18
        if inset < 0.05 { inset = 0.05 }
        lo -= inset
        hi += inset
        let span = max(hi - lo, 0.001)
        let n = pts.count

        func pointAt(_ i: Int) -> NSPoint {
            let x = rect.minX + rect.width * CGFloat(i) / CGFloat(n - 1)
            let v = (pts[i] - lo) / span
            return NSPoint(x: x, y: rect.maxY - CGFloat(v) * rect.height)
        }

        // 昨收基准虚线
        if quote.prevClose > lo && quote.prevClose < hi {
            let y = rect.maxY - CGFloat((quote.prevClose - lo) / span) * rect.height
            let dash = NSBezierPath()
            dash.move(to: NSPoint(x: rect.minX, y: y))
            dash.line(to: NSPoint(x: rect.maxX, y: y))
            var pattern: [CGFloat] = [2, 3]
            dash.setLineDash(&pattern, count: 2, phase: 0)
            dash.lineWidth = 0.8
            NSColor(white: 1, alpha: 0.22).setStroke()
            dash.stroke()
        }

        // 渐变填充
        let fill = NSBezierPath()
        fill.move(to: NSPoint(x: rect.minX, y: rect.maxY))
        for i in 0..<n { fill.line(to: pointAt(i)) }
        fill.line(to: NSPoint(x: rect.maxX, y: rect.maxY))
        fill.close()
        NSGraphicsContext.saveGraphicsState()
        fill.addClip()
        if let grad = NSGradient(colors: [tone.withAlphaComponent(0.38),
                                          tone.withAlphaComponent(0.03)]) {
            grad.draw(in: rect, angle: -90)
        }
        NSGraphicsContext.restoreGraphicsState()

        // 折线
        let line = NSBezierPath()
        line.move(to: pointAt(0))
        for i in 1..<n { line.line(to: pointAt(i)) }
        line.lineWidth = 1.4
        line.lineJoinStyle = .round
        line.lineCapStyle = .round
        tone.setStroke()
        line.stroke()

        let last = pointAt(n - 1)
        let dot = NSBezierPath(ovalIn: NSRect(x: last.x - 2, y: last.y - 2, width: 4, height: 4))
        tone.setFill()
        dot.fill()
    }

    // MARK: 拖动 / 交互

    override func mouseDown(with event: NSEvent) {
        dragStartMouse = NSEvent.mouseLocation
        dragStartOrigin = window?.frame.origin ?? .zero
    }

    override func mouseDragged(with event: NSEvent) {
        guard let win = window else { return }
        let m = NSEvent.mouseLocation
        win.setFrameOrigin(NSPoint(x: dragStartOrigin.x + (m.x - dragStartMouse.x),
                                   y: dragStartOrigin.y + (m.y - dragStartMouse.y)))
    }

    override func mouseUp(with event: NSEvent) {
        if let o = window?.frame.origin {
            cfg.windowX = o.x
            cfg.windowY = o.y
            cfg.save()
        }
    }

    override func rightMouseDown(with event: NSEvent) {
        guard let build = menuBuilder else { return }
        let p = convert(event.locationInWindow, from: nil)
        build().popUp(positioning: nil, at: NSPoint(x: p.x, y: p.y), in: self)
    }

    func setMenuBuilder(_ b: @escaping () -> NSMenu) { menuBuilder = b }
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate {
    var cfg = Config.load()
    var view: TickerView!
    var window: NSWindow!
    var statusItem: NSStatusItem?
    var timer: Timer?
    var store = IntradayStore()
    var fetcher = Fetcher()

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildWindow()
        buildStatusItem()
        scheduleTimer()
        refresh()
    }

    // MARK: 窗口

    func buildWindow() {
        let w = cfg.width, h = cfg.height
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: w, height: h),
                          styleMask: [.borderless],
                          backing: .buffered,
                          defer: false)
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.level = cfg.alwaysOnTop ? .floating : .normal
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        window.alphaValue = cfg.opacity
        window.isMovableByWindowBackground = false
        window.isReleasedWhenClosed = false

        view = TickerView(cfg: cfg)
        view.samples = store.samples
        view.setMenuBuilder { [weak self] in self?.buildMenu() ?? NSMenu() }
        window.contentView = view

        var origin: NSPoint
        if cfg.windowX != -1, cfg.windowY != -1 {
            origin = NSPoint(x: cfg.windowX, y: cfg.windowY)
        } else if let vf = NSScreen.main?.visibleFrame {
            origin = NSPoint(x: vf.maxX - w - 24, y: vf.maxY - h - 24)
        } else {
            origin = NSPoint(x: 200, y: 600)
        }
        window.setFrameOrigin(origin)
        if cfg.showOnDesktop { window.orderFrontRegardless() }
    }

    func applyLayout() {
        guard let win = window else { return }
        let w = cfg.width, h = cfg.height
        let topY = win.frame.maxY
        win.setFrame(NSRect(x: win.frame.minX, y: topY - h, width: w, height: h), display: true)
        view.frame = NSRect(x: 0, y: 0, width: w, height: h)
        view.cfg = cfg
        view.needsDisplay = true
    }

    func applyVisibility() {
        guard let win = window else { return }
        if cfg.showOnDesktop {
            win.orderFrontRegardless()
        } else {
            win.orderOut(nil)
        }
    }

    // MARK: 数据

    func scheduleTimer() {
        timer?.invalidate()
        let t = Timer(timeInterval: cfg.refreshSeconds, repeats: true) { [weak self] _ in
            self?.refresh()
        }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    func refresh() {
        fetcher.fetchPrice { [weak self] q in
            guard let self = self else { return }
            if q.hasData {
                self.view.quote = q
                self.store.append(q.price)
                self.view.samples = self.store.samples
            } else if !self.view.quote.hasData {
                self.view.quote = q
            }
            self.view.needsDisplay = true
            if q.hasData {
                self.statusItem?.button?.title = String(format: "%.2f", q.price)
            } else if self.statusItem?.button?.title == nil ||
                        self.statusItem?.button?.title == "金 --" {
                self.statusItem?.button?.title = "金 --"
            }
        }
    }

    // MARK: 菜单栏

    func buildStatusItem() {
        // 悬浮窗隐藏时必须保留菜单栏入口，避免无从操作
        guard cfg.showMenuBarIcon || !cfg.showOnDesktop else { return }
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "金 --"
        item.button?.font = NSFont.monospacedDigitSystemFont(ofSize: 11, weight: .medium)
        statusItem = item
        statusItem?.menu = buildMenu()
    }

    func refreshMenus() {
        statusItem?.menu = buildMenu()
    }

    // MARK: 菜单

    func buildMenu() -> NSMenu {
        let m = NSMenu()

        let desk = NSMenuItem(title: "显示到桌面", action: #selector(toggleDesktop), keyEquivalent: "d")
        desk.state = cfg.showOnDesktop ? .on : .off
        desk.target = self
        m.addItem(desk)

        let chart = NSMenuItem(title: "显示走势图", action: #selector(toggleChart), keyEquivalent: "t")
        chart.state = cfg.showChart ? .on : .off
        chart.target = self
        m.addItem(chart)

        let detail = NSMenuItem(title: "显示高/低/昨收", action: #selector(toggleDetails), keyEquivalent: "")
        detail.state = cfg.showDetails ? .on : .off
        detail.target = self
        m.addItem(detail)

        let topItem = NSMenuItem(title: "窗口置顶", action: #selector(toggleTop), keyEquivalent: "")
        topItem.state = cfg.alwaysOnTop ? .on : .off
        topItem.target = self
        m.addItem(topItem)

        m.addItem(.separator())

        let rateRoot = NSMenuItem(title: "刷新频率", action: nil, keyEquivalent: "")
        let rateMenu = NSMenu()
        for sec in [5, 10, 15, 30, 60] {
            let it = NSMenuItem(title: "\(sec) 秒", action: #selector(setRate(_:)), keyEquivalent: "")
            it.tag = sec
            it.state = (Int(cfg.refreshSeconds) == sec) ? .on : .off
            it.target = self
            rateMenu.addItem(it)
        }
        rateRoot.submenu = rateMenu
        m.addItem(rateRoot)

        let sizeRoot = NSMenuItem(title: "宽度", action: nil, keyEquivalent: "")
        let sizeMenu = NSMenu()
        for w in [180, 200, 216, 240, 280] {
            let it = NSMenuItem(title: "\(w) pt", action: #selector(setWidth(_:)), keyEquivalent: "")
            it.tag = w
            it.state = (Int(cfg.width) == w) ? .on : .off
            it.target = self
            sizeMenu.addItem(it)
        }
        sizeRoot.submenu = sizeMenu
        m.addItem(sizeRoot)

        let opRoot = NSMenuItem(title: "透明度", action: nil, keyEquivalent: "")
        let opMenu = NSMenu()
        for v in [60, 75, 85, 95, 100] {
            let it = NSMenuItem(title: "\(v)%", action: #selector(setOpacity(_:)), keyEquivalent: "")
            it.tag = v
            it.state = (abs(cfg.opacity * 100 - Double(v)) < 1) ? .on : .off
            it.target = self
            opMenu.addItem(it)
        }
        opRoot.submenu = opMenu
        m.addItem(opRoot)

        m.addItem(.separator())

        let cfgItem = NSMenuItem(title: "打开配置文件夹", action: #selector(openConfig), keyEquivalent: "")
        cfgItem.target = self
        m.addItem(cfgItem)

        let reloadItem = NSMenuItem(title: "重新加载配置", action: #selector(reloadConfig), keyEquivalent: "")
        reloadItem.target = self
        m.addItem(reloadItem)

        m.addItem(.separator())

        let quitItem = NSMenuItem(title: "退出", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        m.addItem(quitItem)
        return m
    }

    @objc func toggleDesktop() {
        cfg.showOnDesktop.toggle()
        cfg.save()
        applyVisibility()
        refreshMenus()
    }

    @objc func toggleChart() {
        cfg.showChart.toggle()
        cfg.save()
        applyLayout()
        refreshMenus()
    }

    @objc func toggleDetails() {
        cfg.showDetails.toggle()
        cfg.save()
        applyLayout()
        refreshMenus()
    }

    @objc func toggleTop() {
        cfg.alwaysOnTop.toggle()
        window.level = cfg.alwaysOnTop ? .floating : .normal
        cfg.save()
        refreshMenus()
    }

    @objc func setRate(_ sender: NSMenuItem) {
        cfg.refreshSeconds = Double(sender.tag)
        cfg.save()
        scheduleTimer()
        refreshMenus()
    }

    @objc func setWidth(_ sender: NSMenuItem) {
        cfg.width = CGFloat(sender.tag)
        cfg.save()
        applyLayout()
        refreshMenus()
    }

    @objc func setOpacity(_ sender: NSMenuItem) {
        cfg.opacity = Double(sender.tag) / 100.0
        window.alphaValue = cfg.opacity
        cfg.save()
        refreshMenus()
    }

    @objc func openConfig() {
        cfg.save()
        ensureDir()
        NSWorkspace.shared.open(URL(fileURLWithPath: CFG_DIR))
    }

    @objc func reloadConfig() {
        cfg = Config.load()
        window.alphaValue = cfg.opacity
        window.level = cfg.alwaysOnTop ? .floating : .normal
        applyLayout()
        applyVisibility()
        scheduleTimer()
        refresh()
        refreshMenus()
    }

    @objc func quit() { NSApp.terminate(nil) }
}

// MARK: - 入口

let args = CommandLine.arguments
let app = NSApplication.shared
app.setActivationPolicy(.accessory)

if let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count {
    let out = args[i + 1]
    let cfg = Config.load()
    let q = Fetcher().fetchPriceSync()
    let store = IntradayStore()
    if q.hasData { store.append(q.price) }
    let v = TickerView(cfg: cfg)
    v.quote = q
    v.samples = store.samples
    let size = NSSize(width: cfg.width, height: cfg.height)
    let img = NSImage(size: size)
    img.lockFocus()
    NSColor(srgbRed: 0.16, green: 0.18, blue: 0.22, alpha: 1).setFill()
    NSRect(origin: .zero, size: size).fill()
    v.draw(v.bounds)
    img.unlockFocus()
    if let tiff = img.tiffRepresentation,
       let rep = NSBitmapImageRep(data: tiff),
       let png = rep.representation(using: .png, properties: [:]) {
        try? png.write(to: URL(fileURLWithPath: out))
        print("snapshot -> \(out) price=\(String(format: "%.2f", q.price)) samples=\(store.samples.count) err=\(q.error ?? "-")")
    }
    exit(0)
} else {
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
