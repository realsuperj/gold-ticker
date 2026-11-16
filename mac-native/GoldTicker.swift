import AppKit
import CoreFoundation
import Foundation

// MARK: - Shared Spec Models (loaded from Bundle Resources/spec.json)

struct SharedSpec: Decodable {
    struct Product: Decodable {
        let name: String
        let version: String
        let bundleId: String
        let copyright: String
        let githubUrl: String
    }
    struct Limits: Decodable {
        let minRefreshSeconds: Int
        let defaultRefreshSeconds: Int
        let coolDownSeconds: Int
        let maxFailuresBeforeCooldown: Int
        let historyKeepDays: Int
        let troyOunceToGram: Double
    }
    struct Defaults: Decodable {
        let symbol: String
        let showOnDesktop: Bool
        let showMenuBarIcon: Bool
        let showChart: Bool
        let showDetails: Bool
        let alwaysOnTop: Bool
        let macWidth: Int
        let winWidth: Int
        let opacity: Double
        let refreshSeconds: Int
        let colorMode: String
        let changeBasis: String
        let language: String
        let windowX: Double
        let windowY: Double
    }
    struct Options: Decodable {
        let macWidths: [Int]
        let winWidths: [Int]
        let refreshIntervals: [Int]
        let opacities: [Double]
    }
    struct Endpoints: Decodable {
        let tangdouzUrl: String
        let sinaHqUrl: String
        let sinaReferer: String
    }
    struct SymbolItem: Decodable {
        let id: String
        let name_cn: String
        let name_en: String
        let card_en: String
        let market: String
        let unit_cn: String
        let unit_en: String
        let prefix_cn: String
        let prefix_en: String
        let is_estimated: Bool
        let spread: Double
    }

    let product: Product
    let limits: Limits
    let defaults: Defaults
    let options: Options
    let endpoints: Endpoints
    let symbols: [SymbolItem]
    let legacySymbolMap: [String: String]
    let disclaimers: [String: String]
    let i18n: [String: [String: String]]

    static let shared: SharedSpec = {
        let fm = FileManager.default
        var candidates: [URL] = []
        if let resUrl = Bundle.main.url(forResource: "spec", withExtension: "json") {
            candidates.append(resUrl)
        }
        let exeUrl = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath()
        let contentsRes = exeUrl.deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("Resources/spec.json")
        candidates.append(contentsRes)
        let repoSpec = URL(fileURLWithPath: fm.currentDirectoryPath).appendingPathComponent("shared/spec.json")
        candidates.append(repoSpec)

        for url in candidates where fm.fileExists(atPath: url.path) {
            if let data = try? Data(contentsOf: url),
               let parsed = try? JSONDecoder().decode(SharedSpec.self, from: data) {
                return parsed
            }
        }
        fatalError("Unable to load shared spec.json from bundle or workspace")
    }()

    func meta(for id: String) -> SymbolItem {
        symbols.first(where: { $0.id == id }) ?? symbols[0]
    }
}

// MARK: - i18n Helper

enum I18n {
    static func detectSystemLanguage() -> String {
        if let env = ProcessInfo.processInfo.environment["LANG"] ?? ProcessInfo.processInfo.environment["LC_ALL"],
           env.lowercased().contains("zh") {
            return "zh"
        }
        if let first = Locale.preferredLanguages.first?.lowercased(), first.hasPrefix("zh") {
            return "zh"
        }
        return "en"
    }

    static func resolve(_ setting: String) -> String {
        let s = setting.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["zh", "cn", "zh_cn", "zh-cn", "chinese"].contains(s) { return "zh" }
        if ["en", "english", "us", "uk"].contains(s) { return "en" }
        return detectSystemLanguage()
    }

    static func t(_ key: String, lang setting: String, replacements: [String: String] = [:]) -> String {
        let lang = resolve(setting)
        let entry = SharedSpec.shared.i18n[key]
        var text = entry?[lang] ?? entry?["zh"] ?? key
        for (k, v) in replacements {
            text = text.replacingOccurrences(of: "{\(k)}", with: v)
        }
        return text
    }

    static func tickerPrefix(_ cfg: AppConfig) -> String {
        resolve(cfg.language) == "zh" ? "金" : "Au"
    }
}

// MARK: - Config & Intraday Storage

struct AppConfig {
    var symbol: String
    var showOnDesktop: Bool
    var showMenuBarIcon: Bool
    var showChart: Bool
    var showDetails: Bool
    var alwaysOnTop: Bool
    var width: Int
    var opacity: Double
    var refreshSeconds: Int
    var colorMode: String
    var changeBasis: String
    var language: String
    var windowX: Double
    var windowY: Double

    static func makeDefault() -> AppConfig {
        let d = SharedSpec.shared.defaults
        return AppConfig(
            symbol: d.symbol,
            showOnDesktop: d.showOnDesktop,
            showMenuBarIcon: d.showMenuBarIcon,
            showChart: d.showChart,
            showDetails: d.showDetails,
            alwaysOnTop: d.alwaysOnTop,
            width: d.macWidth,
            opacity: d.opacity,
            refreshSeconds: d.refreshSeconds,
            colorMode: d.colorMode,
            changeBasis: d.changeBasis,
            language: d.language,
            windowX: d.windowX,
            windowY: d.windowY
        )
    }
}

struct QuoteData {
    var symbol: String
    var price: Double
    var prevClose: Double
    var openPrice: Double
    var high: Double
    var low: Double
    var change: Double
    var changePct: Double
    var timeStr: String
    var sourceId: String
    var sourceName: String
    var isEstimated: Bool
    var fxRate: Double = 0
    var usdPrice: Double = 0
    var error: String?
}

struct IntradayPoint {
    var ts: Int64
    var t: String
    var p: Double
    var s: String
}

enum Storage {
    private static let lock = NSLock()

    static func appDataDir() -> URL {
        let fm = FileManager.default
        if let override = ProcessInfo.processInfo.environment["GOLDTICKER_DATA_DIR"], !override.isEmpty {
            let expanded = (override as NSString).expandingTildeInPath
            let url = URL(fileURLWithPath: expanded, isDirectory: true)
            try? fm.createDirectory(at: url, withIntermediateDirectories: true)
            return url
        }
        let base = fm.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/GoldTicker", isDirectory: true)
        try? fm.createDirectory(at: base, withIntermediateDirectories: true)
        return base
    }

    static func configURL() -> URL {
        appDataDir().appendingPathComponent("config.json")
    }

    static func sanitize(_ raw: [String: Any]?) -> AppConfig {
        var c = AppConfig.makeDefault()
        guard let d = raw else { return c }
        let spec = SharedSpec.shared
        let supported = Set(spec.symbols.map(\.id))

        func str(_ k: String, alt: String? = nil) -> String? {
            if let v = d[k] { return "\(v)" }
            if let a = alt, let v2 = d[a] { return "\(v2)" }
            return nil
        }
        func boolVal(_ k: String, alt: String? = nil) -> Bool? {
            let v = d[k] ?? (alt != nil ? d[alt!] : nil)
            if let b = v as? Bool { return b }
            if let n = v as? NSNumber { return n.boolValue }
            if let s = v as? String { return (s as NSString).boolValue }
            return nil
        }
        func dblVal(_ k: String, alt: String? = nil) -> Double? {
            let v = d[k] ?? (alt != nil ? d[alt!] : nil)
            if let n = v as? NSNumber { return n.doubleValue }
            if let s = v as? String { return Double(s) }
            return nil
        }

        if let sym = str("symbol", alt: "dataSource")?.trimmingCharacters(in: .whitespacesAndNewlines),
           supported.contains(sym) {
            c.symbol = sym
        }
        if let v = boolVal("showOnDesktop") { c.showOnDesktop = v }
        if let v = boolVal("showMenuBarIcon", alt: "showMenuBar") { c.showMenuBarIcon = v }
        if let v = boolVal("showChart") { c.showChart = v }
        if let v = boolVal("showDetails") { c.showDetails = v }
        if let v = boolVal("alwaysOnTop") { c.alwaysOnTop = v }
        if !c.showOnDesktop && !c.showMenuBarIcon { c.showOnDesktop = true }

        if let w = dblVal("width") {
            let wi = Int(w.rounded())
            c.width = spec.options.macWidths.min(by: { abs($0 - wi) < abs($1 - wi) }) ?? spec.defaults.macWidth
        }
        if let op = dblVal("opacity") {
            c.opacity = min(1.0, max(0.60, op))
        }
        if let rf = dblVal("refreshSeconds", alt: "refreshInterval") {
            c.refreshSeconds = max(spec.limits.minRefreshSeconds, Int(rf.rounded()))
        }
        let cm = (str("colorMode") ?? "cny").lowercased()
        c.colorMode = (cm == "intl" || cm == "green-up") ? "intl" : "cny"

        let cb = (str("changeBasis") ?? "prevClose")
        c.changeBasis = (cb == "open" || cb == "open_price") ? "open" : "prevClose"

        let lang = (str("language") ?? "auto").lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        c.language = ["auto", "zh", "en"].contains(lang) ? lang : "auto"

        if let wx = dblVal("windowX") { c.windowX = wx }
        if let wy = dblVal("windowY") { c.windowY = wy }
        return c
    }

    static func loadConfig() -> AppConfig {
        let url = configURL()
        guard FileManager.default.fileExists(atPath: url.path) else {
            let def = AppConfig.makeDefault()
            saveConfig(def)
            return def
        }
        guard let data = try? Data(contentsOf: url),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return AppConfig.makeDefault()
        }
        return sanitize(obj)
    }

    static func saveConfig(_ cfg: AppConfig) {
        var dict: [String: Any] = [
            "symbol": cfg.symbol,
            "showOnDesktop": cfg.showOnDesktop,
            "showMenuBarIcon": cfg.showMenuBarIcon,
            "showChart": cfg.showChart,
            "showDetails": cfg.showDetails,
            "alwaysOnTop": cfg.alwaysOnTop,
            "width": cfg.width,
            "opacity": (cfg.opacity * 100).rounded() / 100.0,
            "refreshSeconds": max(SharedSpec.shared.limits.minRefreshSeconds, cfg.refreshSeconds),
            "colorMode": cfg.colorMode,
            "changeBasis": cfg.changeBasis,
            "language": cfg.language,
            "windowX": (cfg.windowX * 10).rounded() / 10.0,
            "windowY": (cfg.windowY * 10).rounded() / 10.0,
        ]
        if let data = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted, .sortedKeys]) {
            atomicWrite(data, to: configURL())
        }
    }

    private static func atomicWrite(_ data: Data, to url: URL) {
        let tmp = url.appendingPathExtension("tmp")
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: tmp, options: .atomic)
            if FileManager.default.fileExists(atPath: url.path) {
                _ = try FileManager.default.replaceItemAt(url, withItemAt: tmp)
            } else {
                try FileManager.default.moveItem(at: tmp, to: url)
            }
        } catch {
            try? data.write(to: url, options: .atomic)
        }
    }

    private static let dateFmt: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static let hmFmt: DateFormatter = {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "HH:mm"
        return f
    }()

    static func todayString(for date: Date = Date()) -> String {
        dateFmt.string(from: date)
    }

    static func intradayURL(dateStr: String? = nil) -> URL {
        appDataDir().appendingPathComponent("intraday-\(dateStr ?? todayString()).json")
    }

    static func normalizeSymbol(_ sym: String) -> String {
        SharedSpec.shared.legacySymbolMap[sym] ?? sym
    }

    static func cleanupOldHistory(keepDays: Int = SharedSpec.shared.limits.historyKeepDays) {
        let dir = appDataDir()
        guard let files = try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil) else { return }
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        for file in files {
            let name = file.lastPathComponent
            guard name.hasPrefix("intraday-"), name.hasSuffix(".json") else { continue }
            let mid = String(name.dropFirst("intraday-".count).dropLast(".json".count))
            if let fDate = dateFmt.date(from: mid) {
                let days = cal.dateComponents([.day], from: cal.startOfDay(for: fDate), to: today).day ?? 0
                if days > keepDays {
                    try? FileManager.default.removeItem(at: file)
                }
            }
        }
    }

    private static func readDayDoc(_ url: URL) -> (points: [IntradayPoint], basis: [String: (prevClose: Double, open: Double)]) {
        guard FileManager.default.fileExists(atPath: url.path),
              let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) else {
            return ([], [:])
        }

        let name = url.lastPathComponent
        var fileDate = todayString()
        if name.hasPrefix("intraday-"), name.hasSuffix(".json") {
            fileDate = String(name.dropFirst("intraday-".count).dropLast(".json".count))
        }

        var rawPts: [[String: Any]] = []
        var basisMap: [String: (Double, Double)] = [:]

        if let dict = json as? [String: Any] {
            if let arr = dict["points"] as? [[String: Any]] { rawPts = arr }
            if let bDict = dict["basis"] as? [String: [String: Any]] {
                for (k, v) in bDict {
                    let pc = (v["prev_close"] as? NSNumber)?.doubleValue ?? 0
                    let op = (v["open"] as? NSNumber)?.doubleValue ?? 0
                    if pc > 0 { basisMap[k] = (pc, op) }
                }
            }
        } else if let arr = json as? [[String: Any]] {
            rawPts = arr
        }

        var migrated: [IntradayPoint] = []
        migrated.reserveCapacity(rawPts.count)
        for item in rawPts {
            guard let p = (item["p"] as? NSNumber)?.doubleValue, p > 0 else { continue }
            let s = normalizeSymbol((item["s"] as? String) ?? "")
            var tStr = (item["t"] as? String) ?? ""
            var ts: Int64 = 0
            if let n = item["ts"] as? NSNumber, n.int64Value > 0 {
                ts = n.int64Value
            } else if !tStr.isEmpty {
                let parts = tStr.split(separator: ":")
                if parts.count >= 2, let hh = Int(parts[0]), let mm = Int(parts[1]),
                   let baseDay = dateFmt.date(from: fileDate),
                   let combined = Calendar.current.date(bySettingHour: hh, minute: mm, second: 0, of: baseDay) {
                    ts = Int64(combined.timeIntervalSince1970 * 1000.0)
                    tStr = String(format: "%02d:%02d", hh, mm)
                }
            }
            if ts > 0 {
                migrated.append(IntradayPoint(ts: ts, t: tStr, p: p, s: s))
            }
        }
        return (migrated, basisMap)
    }

    private static func writeDayDoc(_ url: URL, points: [IntradayPoint], basis: [String: (prevClose: Double, open: Double)]) {
        let ptsArr: [[String: Any]] = points.map {
            ["ts": $0.ts, "t": $0.t, "p": ($0.p * 100).rounded() / 100.0, "s": $0.s]
        }
        var bObj: [String: [String: Double]] = [:]
        for (k, v) in basis {
            bObj[k] = [
                "prev_close": (v.prevClose * 100).rounded() / 100.0,
                "open": (v.open * 100).rounded() / 100.0,
            ]
        }
        let doc: [String: Any] = ["points": ptsArr, "basis": bObj]
        if let data = try? JSONSerialization.data(withJSONObject: doc, options: [.prettyPrinted]) {
            atomicWrite(data, to: url)
        }
    }

    static func loadTodayPoints(symbol: String) -> [IntradayPoint] {
        lock.lock()
        defer { lock.unlock() }
        let want = normalizeSymbol(symbol)
        return readDayDoc(intradayURL()).points.filter { $0.s == want && $0.p > 0 && $0.ts > 0 }
    }

    static func recordPricePoint(price: Double, symbol: String) {
        guard price > 0 else { return }
        lock.lock()
        defer { lock.unlock() }
        let now = Date()
        let ts = Int64(now.timeIntervalSince1970 * 1000.0)
        let url = intradayURL(dateStr: todayString(for: now))
        var (pts, basis) = readDayDoc(url)
        let norm = normalizeSymbol(symbol)
        let minKey = hmFmt.string(from: now)

        pts.append(IntradayPoint(ts: ts, t: minKey, p: (price * 100).rounded() / 100.0, s: norm))
        pts.sort { $0.ts < $1.ts }

        var merged: [IntradayPoint] = []
        merged.reserveCapacity(pts.count)
        for pt in pts {
            let ptMin = hmFmt.string(from: Date(timeIntervalSince1970: Double(pt.ts) / 1000.0))
            if let last = merged.last, last.s == pt.s {
                let lastMin = hmFmt.string(from: Date(timeIntervalSince1970: Double(last.ts) / 1000.0))
                if lastMin == ptMin {
                    merged[merged.count - 1] = IntradayPoint(ts: pt.ts, t: pt.t.isEmpty ? ptMin : pt.t, p: pt.p, s: pt.s)
                    continue
                }
            }
            merged.append(pt)
        }
        writeDayDoc(url, points: merged, basis: basis)
    }

    static func freezeDayBasis(symbol: String, prevClose: Double, openPrice: Double) {
        guard prevClose > 0 else { return }
        lock.lock()
        defer { lock.unlock() }
        let url = intradayURL()
        var (pts, basis) = readDayDoc(url)
        if let existing = basis[symbol], existing.prevClose > 0 { return }
        basis[symbol] = ((prevClose * 100).rounded() / 100.0, (openPrice * 100).rounded() / 100.0)
        writeDayDoc(url, points: pts, basis: basis)
    }

    static func applyFrozenBasis(_ quote: QuoteData) -> QuoteData {
        guard quote.price > 0 else { return quote }
        lock.lock()
        let basis = readDayDoc(intradayURL()).basis[quote.symbol]
        lock.unlock()
        guard let b = basis, b.prevClose > 0 else { return quote }
        var q = quote
        q.prevClose = b.prevClose
        if b.open > 0 { q.openPrice = b.open }
        q.change = ((q.price - q.prevClose) * 100).rounded() / 100.0
        q.changePct = q.prevClose > 0 ? ((q.change / q.prevClose * 100.0) * 100).rounded() / 100.0 : 0.0
        return q
    }

    static func clearIntradayCache() {
        lock.lock()
        defer { lock.unlock() }
        try? FileManager.default.removeItem(at: intradayURL())
    }
}

// MARK: - Pricing Engine (Multi-source + Cooldown + Spreads)

final class PricingEngine {
    static let shared = PricingEngine()

    private struct Pack {
        let price: Double
        let prev: Double
        let open: Double
        let high: Double
        let low: Double
        let change: Double
        let pct: Double
        let tm: String
    }

    private let lock = NSLock()
    private var failures: [String: (fails: Int, until: Date)] = [:]
    private var cache: [String: QuoteData] = [:]
    private let session: URLSession = {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 5
        cfg.timeoutIntervalForResource = 6
        return URLSession(configuration: cfg)
    }()

    func cachedQuote(_ symbol: String) -> QuoteData? {
        lock.lock()
        defer { lock.unlock() }
        return cache[symbol]
    }

    func sampleAllQuotes() -> [String: QuoteData] {
        let spec = SharedSpec.shared
        var out: [String: QuoteData] = [:]

        do {
            let (usdPack, rawUsd, rate) = try fetchSinaXauRaw()
            recordSuccess("sina_xau")
            out["xau_usd"] = buildQuote(symbol: "xau_usd", pack: usdPack, sourceId: "sina_xau", sourceName: "伦敦金现货", fx: rate, usd: rawUsd)
        } catch {
            recordFailure("sina_xau")
            if let c = cachedQuote("xau_usd") { out["xau_usd"] = c }
        }

        var zsOk = false
        if !isCoolingDown("tangdouz") {
            do {
                let pack = try fetchTangdouzRaw()
                recordSuccess("tangdouz")
                out["zs_jcj"] = buildQuote(symbol: "zs_jcj", pack: pack, sourceId: "tangdouz", sourceName: "浙商银行直连")
                zsOk = true
            } catch {
                recordFailure("tangdouz")
            }
        }
        if !zsOk, let c = cachedQuote("zs_jcj") { out["zs_jcj"] = c }

        do {
            let (pack, sid, sname) = try fetchBenchmarkAu9999()
            for sym in ["au9999", "icbc_jcj", "ccb_jcj"] {
                out[sym] = buildQuote(symbol: sym, pack: pack, sourceId: sid, sourceName: sname)
            }
            if out["zs_jcj"] == nil {
                out["zs_jcj"] = buildQuote(symbol: "zs_jcj", pack: pack, sourceId: sid, sourceName: sname)
            }
        } catch {
            for sym in ["au9999", "icbc_jcj", "ccb_jcj"] {
                if let c = cachedQuote(sym) { out[sym] = c }
            }
        }

        for sym in spec.symbols.map(\.id) where out[sym] == nil {
            if let c = cachedQuote(sym) { out[sym] = c }
        }
        return out
    }

    private func buildQuote(symbol: String, pack: Pack, sourceId: String, sourceName: String, fx: Double = 0, usd: Double = 0) -> QuoteData {
        let meta = SharedSpec.shared.meta(for: symbol)
        var p = pack.price, prev = pack.prev, op = pack.open, h = pack.high, l = pack.low, chg = pack.change, pct = pack.pct
        var sname = sourceName
        var isEst = meta.is_estimated
        if meta.spread > 0 {
            p = ((p + meta.spread) * 100).rounded() / 100.0
            prev = ((prev + meta.spread) * 100).rounded() / 100.0
            op = ((op + meta.spread) * 100).rounded() / 100.0
            h = ((h + meta.spread) * 100).rounded() / 100.0
            l = ((l + meta.spread) * 100).rounded() / 100.0
            chg = ((p - prev) * 100).rounded() / 100.0
            pct = prev > 0 ? ((chg / prev * 100.0) * 100).rounded() / 100.0 : 0.0
            sname += " (点差估算)"
            isEst = true
        }
        let q = QuoteData(
            symbol: symbol, price: p, prevClose: prev, openPrice: op, high: h, low: l,
            change: chg, changePct: pct, timeStr: pack.tm, sourceId: sourceId, sourceName: sname,
            isEstimated: isEst, fxRate: fx, usdPrice: usd, error: nil
        )
        lock.lock()
        cache[symbol] = q
        lock.unlock()
        return q
    }

    private func fetchBenchmarkAu9999() throws -> (Pack, String, String) {
        let sources: [(String, String, () throws -> Pack)] = [
            ("sina_au9999", "上金所 Au99.99", fetchSinaAu9999Raw),
            ("sina_autd", "上金所 Au(T+D)", fetchSinaAutdRaw),
            ("tangdouz", "浙商积存金", fetchTangdouzRaw),
        ]
        var lastErr: Error?
        for (sid, sname, fn) in sources where !isCoolingDown(sid) {
            do {
                let p = try fn()
                recordSuccess(sid)
                return (p, sid, sname)
            } catch {
                recordFailure(sid)
                lastErr = error
            }
        }
        do {
            return (try fetchSinaAu9999Raw(), "sina_au9999", "上金所 Au99.99")
        } catch {
            throw lastErr ?? error
        }
    }

    private func httpGet(_ urlStr: String, referer: String? = nil) throws -> Data {
        guard let url = URL(string: urlStr) else { throw URLError(.badURL) }
        var req = URLRequest(url: url)
        req.setValue("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", forHTTPHeaderField: "User-Agent")
        if let ref = referer { req.setValue(ref, forHTTPHeaderField: "Referer") }

        let sem = DispatchSemaphore(value: 0)
        var resData: Data?
        var resErr: Error?
        session.dataTask(with: req) { d, resp, err in
            if let err = err { resErr = err }
            else if let http = resp as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                resErr = URLError(.badServerResponse)
            } else {
                resData = d
            }
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 7)
        if let err = resErr { throw err }
        guard let data = resData, !data.isEmpty else { throw URLError(.zeroByteResource) }
        return data
    }

    private static func decodeGB18030(_ data: Data) -> String {
        let cfEnc = CFStringConvertEncodingToNSStringEncoding(CFStringEncoding(CFStringEncodings.GB_18030_2000.rawValue))
        return String(data: data, encoding: String.Encoding(rawValue: cfEnc))
            ?? String(decoding: data, as: UTF8.self)
    }

    private static func calcPack(price: Double, prev: Double, open: Double, high: Double, low: Double, tm: String) -> Pack {
        let p = (price * 100).rounded() / 100.0
        var pv = (prev * 100).rounded() / 100.0
        if pv <= 0 { pv = ((open > 0 ? open : price) * 100).rounded() / 100.0 }
        let op = (open * 100).rounded() / 100.0
        let hi = (high * 100).rounded() / 100.0
        let lo = (low * 100).rounded() / 100.0
        let chg = ((p - pv) * 100).rounded() / 100.0
        let pct = pv > 0 ? ((chg / pv * 100.0) * 100).rounded() / 100.0 : 0.0
        return Pack(price: p, prev: pv, open: op, high: hi, low: lo, change: chg, pct: pct, tm: tm.isEmpty ? "--:--" : tm)
    }

    private static func parseTime(_ raw: String) -> String {
        let tail = raw.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: " ").last.map(String.init) ?? ""
        let bits = tail.split(separator: ":")
        if bits.count >= 2, let h = Int(bits[0]), let m = Int(bits[1]) {
            return String(format: "%02d:%02d", h, m)
        }
        return "--:--"
    }

    private func fetchTangdouzRaw() throws -> Pack {
        let raw = try httpGet(SharedSpec.shared.endpoints.tangdouzUrl)
        let text = String(data: raw, encoding: .utf8) ?? Self.decodeGB18030(raw)
        var lines: [String: String] = [:]
        for line in text.components(separatedBy: .newlines) {
            if let idx = line.firstIndex(of: ":") {
                let k = line[..<idx].trimmingCharacters(in: .whitespaces)
                let v = line[line.index(after: idx)...].trimmingCharacters(in: .whitespaces)
                lines[k] = v
            }
        }
        func val(_ k: String) -> Double {
            guard let s = lines[k] else { return 0 }
            let filtered = s.filter { $0.isNumber || $0 == "." || $0 == "-" }
            return Double(filtered) ?? 0
        }
        let price = val("最新价格")
        guard price > 0 else { throw URLError(.cannotParseResponse) }
        let tm = Self.parseTime(lines["更新时间"] ?? "")
        return Self.calcPack(price: price, prev: val("前收盘价"), open: val("开盘价"), high: val("最高价"), low: val("最低价"), tm: tm)
    }

    private func fetchSinaList(_ codes: String) throws -> [String: [String]] {
        let ep = SharedSpec.shared.endpoints
        let raw = try httpGet(ep.sinaHqUrl + codes, referer: ep.sinaReferer)
        let text = Self.decodeGB18030(raw)
        var out: [String: [String]] = [:]
        for line in text.components(separatedBy: .newlines) {
            guard let r1 = line.range(of: "hq_str_"), let r2 = line.range(of: "=\"") else { continue }
            let key = line[r1.upperBound..<r2.lowerBound].trimmingCharacters(in: .whitespaces)
            var body = String(line[r2.upperBound...])
            while let last = body.last, [";", "\"", " ", "\r"].contains(last) { body.removeLast() }
            out[key] = body.components(separatedBy: ",")
        }
        return out
    }

    private func fetchSinaAu9999Raw() throws -> Pack {
        guard let d = try fetchSinaList("SGE_AU9999")["SGE_AU9999"], d.count >= 10 else {
            throw URLError(.cannotParseResponse)
        }
        let price = Double(d[3]) ?? 0
        guard price > 0 else { throw URLError(.cannotParseResponse) }
        let tm = d.count > 16 ? Self.parseTime(d[16]) : "--:--"
        return Self.calcPack(price: price, prev: Double(d[5]) ?? 0, open: Double(d[9]) ?? 0, high: Double(d[7]) ?? 0, low: Double(d[8]) ?? 0, tm: tm)
    }

    private func fetchSinaAutdRaw() throws -> Pack {
        guard let d = try fetchSinaList("gds_AUTD")["gds_AUTD"], d.count >= 9 else {
            throw URLError(.cannotParseResponse)
        }
        let price = Double(d[0]) ?? 0
        guard price > 0 else { throw URLError(.cannotParseResponse) }
        return Self.calcPack(price: price, prev: Double(d[7]) ?? 0, open: Double(d[8]) ?? 0, high: Double(d[4]) ?? 0, low: Double(d[5]) ?? 0, tm: Self.parseTime(d[6]))
    }

    private func fetchSinaXauRaw() throws -> (Pack, Double, Double) {
        let map = try fetchSinaList("hf_XAU,fx_susdcny")
        guard let xau = map["hf_XAU"], xau.count >= 9, let fx = map["fx_susdcny"], fx.count >= 2 else {
            throw URLError(.cannotParseResponse)
        }
        let rate = Double(fx[1]) ?? 0
        let rawUsd = Double(xau[0]) ?? 0
        guard rate > 0, rawUsd > 0 else { throw URLError(.cannotParseResponse) }
        let pack = Self.calcPack(price: rawUsd, prev: Double(xau[7]) ?? 0, open: Double(xau[8]) ?? 0, high: Double(xau[4]) ?? 0, low: Double(xau[5]) ?? 0, tm: Self.parseTime(xau[6]))
        return (pack, rawUsd, rate)
    }

    private func isCoolingDown(_ sid: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let rec = failures[sid] else { return false }
        return Date() < rec.until
    }

    private func recordFailure(_ sid: String) {
        lock.lock()
        defer { lock.unlock() }
        let cur = failures[sid] ?? (0, .distantPast)
        let fails = cur.fails + 1
        let lim = SharedSpec.shared.limits
        let until = fails >= lim.maxFailuresBeforeCooldown ? Date().addingTimeInterval(TimeInterval(lim.coolDownSeconds)) : cur.until
        failures[sid] = (fails, until)
    }

    private func recordSuccess(_ sid: String) {
        lock.lock()
        defer { lock.unlock() }
        failures.removeValue(forKey: sid)
    }
}

// MARK: - Native AppKit Card View (Pixel-identical to mac/card.py)

final class GoldCardView: NSView {
    weak var controller: AppController?
    private var dragStartMouse: NSPoint?
    private var dragStartOrigin: NSPoint?

    private static let upColor = NSColor(srgbRed: 0.96, green: 0.28, blue: 0.28, alpha: 1.0)
    private static let downColor = NSColor(srgbRed: 0.18, green: 0.80, blue: 0.44, alpha: 1.0)

    override var isFlipped: Bool { true }

    override func mouseDown(with event: NSEvent) {
        guard let win = window else { return }
        dragStartMouse = NSEvent.mouseLocation
        dragStartOrigin = win.frame.origin
    }

    override func mouseDragged(with event: NSEvent) {
        guard let sMouse = dragStartMouse, let sOrigin = dragStartOrigin, let win = window else { return }
        let cur = NSEvent.mouseLocation
        win.setFrameOrigin(NSPoint(x: sOrigin.x + (cur.x - sMouse.x), y: sOrigin.y + (cur.y - sMouse.y)))
    }

    override func mouseUp(with event: NSEvent) {
        if let ctrl = controller, let win = window {
            ctrl.config.windowX = Double(win.frame.origin.x)
            ctrl.config.windowY = Double(win.frame.origin.y)
            Storage.saveConfig(ctrl.config)
        }
        dragStartMouse = nil
        dragStartOrigin = nil
    }

    override func rightMouseDown(with event: NSEvent) {
        guard let ctrl = controller else { return }
        let menu = ctrl.buildMenu()
        NSMenu.popUpContextMenu(menu, with: event, for: self)
    }

    private func drawText(_ s: String, x: CGFloat, top: CGFloat, w: CGFloat, h: CGFloat, size: CGFloat, color: NSColor, bold: Bool = false, mono: Bool = false, align: NSTextAlignment = .left) {
        var font: NSFont = mono
            ? NSFont.monospacedDigitSystemFont(ofSize: size, weight: bold ? .bold : .medium)
            : NSFont.systemFont(ofSize: size, weight: bold ? .bold : .regular)
        let ns = s as NSString
        let measured = ns.size(withAttributes: [.font: font]).width
        if measured > w && measured > 0 {
            font = NSFont(descriptor: font.fontDescriptor, size: size * w / measured) ?? font
        }
        let ps = NSMutableParagraphStyle()
        ps.alignment = align
        ps.lineBreakMode = .byTruncatingTail
        ns.draw(in: NSRect(x: x, y: top, width: w, height: h), withAttributes: [
            .font: font,
            .foregroundColor: color,
            .paragraphStyle: ps,
        ])
    }

    override func draw(_ dirtyRect: NSRect) {
        guard let ctrl = controller else { return }
        let cfg = ctrl.config
        let W = bounds.width
        let H = bounds.height
        let pad: CGFloat = 14

        let bg = NSBezierPath(roundedRect: NSRect(x: 0.5, y: 0.5, width: W - 1, height: H - 1), xRadius: 12, yRadius: 12)
        NSColor(srgbRed: 0.08, green: 0.11, blue: 0.16, alpha: CGFloat(cfg.opacity)).setFill()
        bg.fill()
        NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.12).setStroke()
        bg.lineWidth = 1.0
        bg.stroke()

        let lang = I18n.resolve(cfg.language)
        let isEn = (lang == "en")

        guard let q = ctrl.currentQuote, q.price > 0 else {
            let key = (ctrl.currentQuote?.error != nil) ? "fetch_error" : "refreshing"
            drawText(I18n.t(key, lang: cfg.language), x: pad, top: H / 2 - 8, w: W - pad * 2, h: 16, size: 10.5, color: NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.62), align: .center)
            return
        }

        let useOpen = (cfg.changeBasis == "open" && q.openPrice > 0)
        let basis = useOpen ? q.openPrice : q.prevClose
        let basisLabel = useOpen ? "今开" : "昨收"
        let change = basis > 0 ? (q.price - basis) : q.change
        let pct = basis > 0 ? (change / basis * 100.0) : q.changePct
        let up = change >= 0
        let tone: NSColor = (cfg.colorMode == "cny")
            ? (up ? Self.upColor : Self.downColor)
            : (up ? Self.downColor : Self.upColor)

        var top: CGFloat = 9
        let meta = SharedSpec.shared.meta(for: q.symbol)
        let dispName: String
        let dispUnit: String
        if isEn {
            dispName = meta.card_en
            dispUnit = meta.unit_en
        } else {
            dispName = meta.name_cn + (q.isEstimated ? " (点差估算)" : "")
            dispUnit = meta.unit_cn
        }

        drawText("\(dispName) · \(dispUnit)", x: pad, top: top, w: W - pad * 2, h: 12, size: 11.0, color: NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.70))
        top += 14

        let priceSize: CGFloat = W >= 200 ? 28.0 : 26.0
        drawText(String(format: "%.2f", q.price), x: pad - 1, top: top, w: W - pad * 2 + 2, h: 34, size: priceSize, color: tone, bold: true, mono: true)
        top += 34

        let sign = up ? "+" : ""
        drawText(String(format: "%@%.2f  (%@%.2f%%)", sign, change, sign, pct), x: pad, top: top, w: W - pad * 2, h: 14, size: 12.0, color: tone.withAlphaComponent(0.95), mono: true)
        top += 16

        if cfg.showDetails {
            let hTag = isEn ? "High" : "高"
            let lTag = isEn ? "Low" : "低"
            let bTag = isEn ? (basisLabel == "今开" ? "Open" : "Prev") : basisLabel
            let detail = String(format: "%@ %.2f  %@ %.2f  %@ %.2f", hTag, q.high, lTag, q.low, bTag, basis)
            drawText(detail, x: pad, top: top, w: W - pad * 2, h: 12, size: 10.0, color: NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.50), mono: true)
            top += 16
        }

        if cfg.showChart {
            let samples = Storage.loadTodayPoints(symbol: q.symbol)
            drawChart(samples: samples, x: pad, y: top + 2, w: W - pad * 2, h: 44, tone: tone, basis: basis)
            top += 48
            if let first = samples.first, let last = samples.last, samples.count >= 2 {
                let hmFmt = DateFormatter()
                hmFmt.locale = Locale(identifier: "en_US_POSIX")
                hmFmt.timeZone = .current
                hmFmt.dateFormat = "HH:mm"
                let fStr = hmFmt.string(from: Date(timeIntervalSince1970: Double(first.ts) / 1000.0))
                let lStr = hmFmt.string(from: Date(timeIntervalSince1970: Double(last.ts) / 1000.0))
                let axisColor = NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.38)
                drawText(fStr, x: pad, top: top, w: 80, h: 11, size: 8.5, color: axisColor, mono: true, align: .left)
                drawText(lStr, x: W - pad - 80, top: top, w: 80, h: 11, size: 8.5, color: axisColor, mono: true, align: .right)
            }
        }
    }

    private func drawChart(samples: [IntradayPoint], x: CGFloat, y: CGFloat, w: CGFloat, h: CGFloat, tone: NSColor, basis: Double) {
        if samples.count < 2 {
            let mid = y + h / 2.0
            let dash = NSBezierPath()
            dash.move(to: NSPoint(x: x, y: mid))
            dash.line(to: NSPoint(x: x + w, y: mid))
            let pattern: [CGFloat] = [4.0, 4.0]
            dash.setLineDash(pattern, count: 2, phase: 0)
            dash.lineWidth = 1.0
            NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.15).setStroke()
            dash.stroke()
            return
        }

        let prices = samples.map(\.p)
        var allVals = prices
        if basis > 0 { allVals.append(basis) }
        var lo = allVals.min() ?? 0
        var hi = allVals.max() ?? 1
        if abs(hi - lo) < 1e-5 { lo -= 1.0; hi += 1.0 }
        let inset = max((hi - lo) * 0.12, 0.05)
        lo -= inset
        hi += inset
        let span = max(hi - lo, 0.001)
        let stepX = w / CGFloat(prices.count - 1)

        func py(_ v: Double) -> CGFloat {
            y + h - CGFloat((v - lo) / span) * h
        }

        if basis > 0 && lo < basis && basis < hi {
            let yy = py(basis)
            let dash = NSBezierPath()
            dash.move(to: NSPoint(x: x, y: yy))
            dash.line(to: NSPoint(x: x + w, y: yy))
            let pattern: [CGFloat] = [2.0, 3.0]
            dash.setLineDash(pattern, count: 2, phase: 0)
            dash.lineWidth = 0.8
            NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.22).setStroke()
            dash.stroke()
        }

        let line = NSBezierPath()
        var pts: [NSPoint] = []
        pts.reserveCapacity(prices.count)
        for (idx, price) in prices.enumerated() {
            let pt = NSPoint(x: x + CGFloat(idx) * stepX, y: py(price))
            pts.append(pt)
            if idx == 0 { line.move(to: pt) } else { line.line(to: pt) }
        }

        let fill = NSBezierPath()
        fill.move(to: pts[0])
        for pt in pts.dropFirst() { fill.line(to: pt) }
        fill.line(to: NSPoint(x: pts.last!.x, y: y + h))
        fill.line(to: NSPoint(x: pts[0].x, y: y + h))
        fill.close()
        if let grad = NSGradient(starting: tone.withAlphaComponent(0.22), ending: tone.withAlphaComponent(0.02)) {
            grad.draw(in: fill, angle: 90.0)
        }

        line.lineWidth = 1.5
        line.lineJoinStyle = .round
        line.lineCapStyle = .round
        tone.setStroke()
        line.stroke()

        let last = pts.last!
        let dot = NSBezierPath(ovalIn: NSRect(x: last.x - 2, y: last.y - 2, width: 4, height: 4))
        tone.setFill()
        dot.fill()
    }
}

// MARK: - Application Controller & Menu Matrix

final class AppController: NSObject, NSApplicationDelegate, NSMenuDelegate {
    var config: AppConfig = Storage.loadConfig()
    var currentQuote: QuoteData?
    var window: NSWindow!
    var cardView: GoldCardView!
    var statusItem: NSStatusItem!

    private var fetchGen: Int = 0
    private var isFetching: Bool = false
    private let stateLock = NSLock()
    private var pollTimer: DispatchSourceTimer?

    func calcWindowHeight(_ cfg: AppConfig) -> CGFloat {
        var h: CGFloat = 9 + 14 + 36 + 17
        if cfg.showDetails { h += 16 }
        if cfg.showChart { h += 2 + 44 + 12 }
        return h + 12
    }

    func setupUI() {
        let w = CGFloat(config.width)
        let h = calcWindowHeight(config)

        window = NSWindow(
            contentRect: NSRect(x: 100, y: 100, width: w, height: h),
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.isMovableByWindowBackground = false
        window.hasShadow = true
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]

        cardView = GoldCardView(frame: NSRect(x: 0, y: 0, width: w, height: h))
        cardView.controller = self
        window.contentView = cardView

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.menu = buildMenu()

        positionWindowDefault()
        applyAllConfig()
    }

    func startPolling() {
        Storage.cleanupOldHistory()
        triggerFetchNow(force: true)

        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
        let sec = max(SharedSpec.shared.limits.minRefreshSeconds, config.refreshSeconds)
        timer.schedule(deadline: .now() + .seconds(sec), repeating: .seconds(sec))
        timer.setEventHandler { [weak self] in
            self?.triggerFetchNow()
        }
        timer.resume()
        pollTimer = timer
    }

    private func rescheduleTimer() {
        pollTimer?.cancel()
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.global(qos: .utility))
        let sec = max(SharedSpec.shared.limits.minRefreshSeconds, config.refreshSeconds)
        timer.schedule(deadline: .now() + .seconds(sec), repeating: .seconds(sec))
        timer.setEventHandler { [weak self] in
            self?.triggerFetchNow()
        }
        timer.resume()
        pollTimer = timer
    }

    func positionWindowDefault() {
        let w = CGFloat(config.width)
        let h = calcWindowHeight(config)
        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let nx: CGFloat
        let ny: CGFloat
        if config.windowX < 0 || config.windowY < 0 {
            nx = screenFrame.origin.x + screenFrame.size.width - w - 24.0
            ny = screenFrame.origin.y + screenFrame.size.height - h - 24.0
        } else {
            nx = CGFloat(config.windowX)
            ny = CGFloat(config.windowY)
        }
        window.setFrame(NSRect(x: nx, y: ny, width: w, height: h), display: true)
    }

    func updateWindowSize() {
        let w = CGFloat(config.width)
        let h = calcWindowHeight(config)
        let origin = window.frame.origin
        window.setFrame(NSRect(x: origin.x, y: origin.y, width: w, height: h), display: true)
        cardView.frame = NSRect(x: 0, y: 0, width: w, height: h)
        cardView.needsDisplay = true
    }

    func applyWindowLevel() {
        window.level = config.alwaysOnTop ? .floating : .normal
    }

    func applyDisplayVisibility() {
        if config.showOnDesktop {
            window.orderFront(nil)
        } else {
            window.orderOut(nil)
        }
        statusItem.isVisible = config.showMenuBarIcon
    }

    func updateStatusBar() {
        guard let button = statusItem.button else { return }
        guard let q = currentQuote, q.price > 0 else {
            button.title = I18n.tickerPrefix(config) + " --"
            return
        }
        let prefix = I18n.tickerPrefix(config)
        let basePrice = (config.changeBasis == "open" && q.openPrice > 0) ? q.openPrice : q.prevClose
        let chg = basePrice > 0 ? (q.price - basePrice) : 0.0
        let pct = basePrice > 0 ? (chg / basePrice * 100.0) : 0.0
        button.title = String(format: "%@ %.2f %+.2f%%", prefix, q.price, pct)
    }

    func applyAllConfig() {
        updateWindowSize()
        applyWindowLevel()
        applyDisplayVisibility()
        updateStatusBar()
    }

    func triggerFetchNow(force: Bool = false) {
        stateLock.lock()
        if isFetching && !force {
            stateLock.unlock()
            return
        }
        fetchGen += 1
        let gen = fetchGen
        let sym = config.symbol
        isFetching = true
        stateLock.unlock()

        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self = self else { return }
            defer {
                self.stateLock.lock()
                if self.fetchGen == gen { self.isFetching = false }
                self.stateLock.unlock()
            }
            let quotes = PricingEngine.shared.sampleAllQuotes()
            self.stateLock.lock()
            let curGen = self.fetchGen
            self.stateLock.unlock()
            guard gen == curGen else { return }

            for (s, q) in quotes where q.price > 0 && q.error == nil {
                Storage.freezeDayBasis(symbol: s, prevClose: q.prevClose, openPrice: q.openPrice)
                Storage.recordPricePoint(price: q.price, symbol: s)
            }
            var picked = quotes[sym] ?? PricingEngine.shared.cachedQuote(sym)
            if let pq = picked, pq.price > 0 {
                picked = Storage.applyFrozenBasis(pq)
            }
            DispatchQueue.main.async {
                guard gen == self.fetchGen && sym == self.config.symbol else { return }
                if let pq = picked {
                    self.currentQuote = pq
                } else if self.currentQuote == nil {
                    self.currentQuote = QuoteData(
                        symbol: sym, price: 0, prevClose: 0, openPrice: 0, high: 0, low: 0,
                        change: 0, changePct: 0, timeStr: "--:--", sourceId: "none", sourceName: "",
                        isEstimated: false, error: "unavailable"
                    )
                }
                self.cardView.needsDisplay = true
                self.updateStatusBar()
            }
        }
    }

    // MARK: NSMenu Construction

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        populateMenu(menu)
    }

    func buildMenu() -> NSMenu {
        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.delegate = self
        populateMenu(menu)
        return menu
    }

    private func txt(_ key: String) -> String {
        I18n.t(key, lang: config.language)
    }

    private func populateMenu(_ menu: NSMenu) {
        let lang = I18n.resolve(config.language)
        let spec = SharedSpec.shared

        let headerTitle: String
        if let q = currentQuote, q.price > 0 {
            let meta = spec.meta(for: q.symbol)
            let sname = lang == "zh" ? meta.name_cn : meta.name_en
            let basePrice = (config.changeBasis == "open" && q.openPrice > 0) ? q.openPrice : q.prevClose
            let pct = basePrice > 0 ? ((q.price - basePrice) / basePrice * 100.0) : q.changePct
            headerTitle = String(format: "%@ %.2f (%+.2f%%)", sname, q.price, pct)
        } else {
            headerTitle = txt("refreshing")
        }

        let head = NSMenuItem(title: headerTitle, action: #selector(onForceRefresh(_:)), keyEquivalent: "")
        head.target = self
        menu.addItem(head)
        menu.addItem(.separator())

        let mDesktop = NSMenuItem(title: txt("showOnDesktop"), action: #selector(onToggleDesktop(_:)), keyEquivalent: "")
        mDesktop.target = self
        mDesktop.state = config.showOnDesktop ? .on : .off
        mDesktop.isEnabled = config.showMenuBarIcon
        menu.addItem(mDesktop)

        let mMenuBar = NSMenuItem(title: txt("showMenuBar"), action: #selector(onToggleMenuBar(_:)), keyEquivalent: "")
        mMenuBar.target = self
        mMenuBar.state = config.showMenuBarIcon ? .on : .off
        mMenuBar.isEnabled = config.showOnDesktop
        menu.addItem(mMenuBar)

        let mTop = NSMenuItem(title: txt("alwaysOnTop"), action: #selector(onToggleTop(_:)), keyEquivalent: "")
        mTop.target = self
        mTop.state = config.alwaysOnTop ? .on : .off
        menu.addItem(mTop)
        menu.addItem(.separator())

        let mChart = NSMenuItem(title: txt("showChart"), action: #selector(onToggleChart(_:)), keyEquivalent: "")
        mChart.target = self
        mChart.state = config.showChart ? .on : .off
        menu.addItem(mChart)

        let mDetails = NSMenuItem(title: txt("showDetails"), action: #selector(onToggleDetails(_:)), keyEquivalent: "")
        mDetails.target = self
        mDetails.state = config.showDetails ? .on : .off
        menu.addItem(mDetails)

        let wSub = NSMenu()
        for wVal in spec.options.macWidths {
            let wi = NSMenuItem(title: "\(wVal) pt", action: #selector(onSelectWidth(_:)), keyEquivalent: "")
            wi.target = self
            wi.tag = wVal
            wi.state = (config.width == wVal) ? .on : .off
            wSub.addItem(wi)
        }
        let mWidth = NSMenuItem(title: txt("cardWidth"), action: nil, keyEquivalent: "")
        mWidth.submenu = wSub
        menu.addItem(mWidth)

        let opSub = NSMenu()
        for opVal in spec.options.opacities {
            let pctTag = Int((opVal * 100).rounded())
            let opi = NSMenuItem(title: "\(pctTag)%", action: #selector(onSelectOpacity(_:)), keyEquivalent: "")
            opi.target = self
            opi.tag = pctTag
            opi.state = abs(config.opacity - opVal) < 0.03 ? .on : .off
            opSub.addItem(opi)
        }
        let mOp = NSMenuItem(title: txt("cardOpacity"), action: nil, keyEquivalent: "")
        mOp.submenu = opSub
        menu.addItem(mOp)

        let mReset = NSMenuItem(title: txt("resetPos"), action: #selector(onResetPos(_:)), keyEquivalent: "")
        mReset.target = self
        menu.addItem(mReset)
        menu.addItem(.separator())

        let symSub = NSMenu()
        for meta in spec.symbols {
            if meta.id == "xau_usd" { symSub.addItem(.separator()) }
            var title = lang == "zh" ? meta.name_cn : meta.name_en
            if meta.is_estimated { title += " " + txt("estTag") }
            let si = NSMenuItem(title: title, action: #selector(onSelectSymbol(_:)), keyEquivalent: "")
            si.target = self
            si.representedObject = meta.id
            si.state = (config.symbol == meta.id) ? .on : .off
            symSub.addItem(si)
        }
        let mSyms = NSMenuItem(title: txt("symbols"), action: nil, keyEquivalent: "")
        mSyms.submenu = symSub
        menu.addItem(mSyms)

        let basisSub = NSMenu()
        for (val, key) in [("prevClose", "prevClose"), ("open", "openPrice")] {
            let bi = NSMenuItem(title: txt(key), action: #selector(onSelectBasis(_:)), keyEquivalent: "")
            bi.target = self
            bi.representedObject = val
            bi.state = (config.changeBasis == val) ? .on : .off
            basisSub.addItem(bi)
        }
        let mBasis = NSMenuItem(title: txt("changeBasis"), action: nil, keyEquivalent: "")
        mBasis.submenu = basisSub
        menu.addItem(mBasis)

        let colorSub = NSMenu()
        for (val, key) in [("cny", "cnyColors"), ("intl", "intlColors")] {
            let ci = NSMenuItem(title: txt(key), action: #selector(onSelectColor(_:)), keyEquivalent: "")
            ci.target = self
            ci.representedObject = val
            ci.state = (config.colorMode == val) ? .on : .off
            colorSub.addItem(ci)
        }
        let mColor = NSMenuItem(title: txt("colorMode"), action: nil, keyEquivalent: "")
        mColor.submenu = colorSub
        menu.addItem(mColor)

        let langSub = NSMenu()
        for choice in ["auto", "zh", "en"] {
            let li = NSMenuItem(title: txt("menu_lang_" + choice), action: #selector(onSelectLanguage(_:)), keyEquivalent: "")
            li.target = self
            li.representedObject = choice
            li.state = (config.language == choice) ? .on : .off
            langSub.addItem(li)
        }
        let mLang = NSMenuItem(title: txt("menu_language"), action: nil, keyEquivalent: "")
        mLang.submenu = langSub
        menu.addItem(mLang)

        let refSub = NSMenu()
        for sec in spec.options.refreshIntervals {
            var label = "\(sec) \(txt("seconds"))"
            if sec == 10 { label += " (\(txt("recommend")))" }
            let ri = NSMenuItem(title: label, action: #selector(onSelectRefresh(_:)), keyEquivalent: "")
            ri.target = self
            ri.tag = sec
            ri.state = (config.refreshSeconds == sec) ? .on : .off
            refSub.addItem(ri)
        }
        let mRef = NSMenuItem(title: txt("refreshInterval"), action: nil, keyEquivalent: "")
        mRef.submenu = refSub
        menu.addItem(mRef)
        menu.addItem(.separator())

        let advSub = NSMenu()
        let mFolder = NSMenuItem(title: txt("openConfigFolder"), action: #selector(onOpenFolder(_:)), keyEquivalent: "")
        mFolder.target = self
        advSub.addItem(mFolder)
        let mReload = NSMenuItem(title: txt("reloadConfig"), action: #selector(onReloadConfig(_:)), keyEquivalent: "")
        mReload.target = self
        advSub.addItem(mReload)
        let mClear = NSMenuItem(title: txt("clearCache"), action: #selector(onClearCache(_:)), keyEquivalent: "")
        mClear.target = self
        advSub.addItem(mClear)
        let mAdv = NSMenuItem(title: txt("advanced"), action: nil, keyEquivalent: "")
        mAdv.submenu = advSub
        menu.addItem(mAdv)

        let aboutSub = NSMenu()
        let mAbt = NSMenuItem(title: txt("aboutApp"), action: #selector(onAbout(_:)), keyEquivalent: "")
        mAbt.target = self
        aboutSub.addItem(mAbt)
        let mDisc = NSMenuItem(title: txt("viewDisclaimer"), action: #selector(onDisclaimer(_:)), keyEquivalent: "")
        mDisc.target = self
        aboutSub.addItem(mDisc)
        let mGh = NSMenuItem(title: txt("visitGithub"), action: #selector(onGithub(_:)), keyEquivalent: "")
        mGh.target = self
        aboutSub.addItem(mGh)
        let mAbout = NSMenuItem(title: txt("aboutMenu"), action: nil, keyEquivalent: "")
        mAbout.submenu = aboutSub
        menu.addItem(mAbout)

        menu.addItem(.separator())
        let mQuit = NSMenuItem(title: txt("quitApp"), action: #selector(onQuit(_:)), keyEquivalent: "q")
        mQuit.target = self
        menu.addItem(mQuit)
    }

    // MARK: Menu Actions

    @objc func onForceRefresh(_ sender: Any?) { triggerFetchNow(force: true) }

    @objc func onToggleDesktop(_ sender: Any?) {
        config.showOnDesktop.toggle()
        Storage.saveConfig(config)
        applyDisplayVisibility()
    }

    @objc func onToggleMenuBar(_ sender: Any?) {
        config.showMenuBarIcon.toggle()
        Storage.saveConfig(config)
        applyDisplayVisibility()
    }

    @objc func onToggleTop(_ sender: Any?) {
        config.alwaysOnTop.toggle()
        Storage.saveConfig(config)
        applyWindowLevel()
    }

    @objc func onToggleChart(_ sender: Any?) {
        config.showChart.toggle()
        Storage.saveConfig(config)
        updateWindowSize()
    }

    @objc func onToggleDetails(_ sender: Any?) {
        config.showDetails.toggle()
        Storage.saveConfig(config)
        updateWindowSize()
    }

    @objc func onSelectWidth(_ sender: NSMenuItem) {
        config.width = sender.tag
        Storage.saveConfig(config)
        updateWindowSize()
    }

    @objc func onSelectOpacity(_ sender: NSMenuItem) {
        config.opacity = Double(sender.tag) / 100.0
        Storage.saveConfig(config)
        cardView.needsDisplay = true
    }

    @objc func onResetPos(_ sender: Any?) {
        config.windowX = -1
        config.windowY = -1
        Storage.saveConfig(config)
        positionWindowDefault()
    }

    @objc func onSelectSymbol(_ sender: NSMenuItem) {
        guard let sym = sender.representedObject as? String else { return }
        config.symbol = sym
        Storage.saveConfig(config)
        if let cached = PricingEngine.shared.cachedQuote(sym), cached.price > 0 {
            currentQuote = Storage.applyFrozenBasis(cached)
        } else {
            let pts = Storage.loadTodayPoints(symbol: sym)
            if let last = pts.last {
                let meta = SharedSpec.shared.meta(for: sym)
                let hi = pts.map(\.p).max() ?? last.p
                let lo = pts.map(\.p).min() ?? last.p
                let stub = QuoteData(
                    symbol: sym, price: last.p, prevClose: last.p, openPrice: last.p,
                    high: hi, low: lo, change: 0, changePct: 0, timeStr: last.t,
                    sourceId: "cache", sourceName: meta.name_cn, isEstimated: meta.is_estimated, error: nil
                )
                currentQuote = Storage.applyFrozenBasis(stub)
            }
        }
        applyAllConfig()
        triggerFetchNow(force: true)
    }

    @objc func onSelectBasis(_ sender: NSMenuItem) {
        guard let b = sender.representedObject as? String else { return }
        config.changeBasis = b
        Storage.saveConfig(config)
        cardView.needsDisplay = true
        updateStatusBar()
    }

    @objc func onSelectColor(_ sender: NSMenuItem) {
        guard let c = sender.representedObject as? String else { return }
        config.colorMode = c
        Storage.saveConfig(config)
        cardView.needsDisplay = true
    }

    @objc func onSelectLanguage(_ sender: NSMenuItem) {
        guard let l = sender.representedObject as? String else { return }
        config.language = l
        Storage.saveConfig(config)
        applyAllConfig()
    }

    @objc func onSelectRefresh(_ sender: NSMenuItem) {
        config.refreshSeconds = max(SharedSpec.shared.limits.minRefreshSeconds, sender.tag)
        Storage.saveConfig(config)
        rescheduleTimer()
    }

    @objc func onOpenFolder(_ sender: Any?) {
        NSWorkspace.shared.open(Storage.appDataDir())
    }

    @objc func onReloadConfig(_ sender: Any?) {
        config = Storage.loadConfig()
        applyAllConfig()
        rescheduleTimer()
    }

    @objc func onClearCache(_ sender: Any?) {
        Storage.clearIntradayCache()
        cardView.needsDisplay = true
    }

    func makeAlert(titleKey: String, body: String) -> NSAlert {
        let alert = NSAlert()
        alert.icon = NSApplication.shared.applicationIconImage
        alert.messageText = txt(titleKey)
        alert.informativeText = body
        alert.addButton(withTitle: txt("ok"))
        return alert
    }

    @objc func onAbout(_ sender: Any?) {
        let prod = SharedSpec.shared.product
        let body = I18n.t("about_body", lang: config.language, replacements: [
            "version": prod.version,
            "copyright": prod.copyright,
        ])
        NSApp.activate(ignoringOtherApps: true)
        makeAlert(titleKey: "about_title", body: body).runModal()
    }

    @objc func onDisclaimer(_ sender: Any?) {
        let lang = I18n.resolve(config.language)
        let text = SharedSpec.shared.disclaimers[lang] ?? SharedSpec.shared.disclaimers["zh"] ?? ""
        NSApp.activate(ignoringOtherApps: true)
        makeAlert(titleKey: "disclaimer_title", body: text).runModal()
    }

    @objc func onGithub(_ sender: Any?) {
        if let url = URL(string: SharedSpec.shared.product.githubUrl) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc func onQuit(_ sender: Any?) {
        NSApplication.shared.terminate(nil)
    }
}

// MARK: - Main Entry & Isolated Smoke Test

@main
struct GoldTickerMain {
    static func main() {
        if CommandLine.arguments.contains("--smoke-test") {
            runSmokeTest()
            return
        }

        let app = NSApplication.shared
        if let iconUrl = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let img = NSImage(contentsOf: iconUrl) {
            app.applicationIconImage = img
        }
        app.setActivationPolicy(.accessory)

        let controller = AppController()
        app.delegate = controller
        controller.setupUI()
        controller.startPolling()
        app.run()
    }

    private static func runSmokeTest() {
        let tmp = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("goldticker-mac-smoke-\(UUID().uuidString)", isDirectory: true)
        try? FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmp) }

        setenv("GOLDTICKER_DATA_DIR", tmp.path, 1)
        let app = NSApplication.shared
        if let iconUrl = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let img = NSImage(contentsOf: iconUrl) {
            app.applicationIconImage = img
        }
        let ctrl = AppController()
        ctrl.setupUI()
        for (lang, prefix) in [("zh", "金"), ("en", "Au")] {
            ctrl.config.language = lang
            ctrl.applyAllConfig()
            ctrl.window.display()
            assert(ctrl.statusItem.button?.title == "\(prefix) --", "Status bar title mismatch")
            let alert = ctrl.makeAlert(titleKey: "about_title", body: SharedSpec.shared.product.version)
            assert(alert.buttons.first?.title == (lang == "zh" ? "确定" : "OK"), "Alert button mismatch")
        }
        ctrl.window.orderOut(nil)
        NSStatusBar.system.removeStatusItem(ctrl.statusItem)

        let payload: [String: Any] = [
            "smoke": "passed",
            "platform": "darwin-swift-universal2",
            "version": SharedSpec.shared.product.version,
            "data_isolated": true,
        ]
        if let data = try? JSONSerialization.data(withJSONObject: payload),
           let s = String(data: data, encoding: .utf8) {
            print(s)
        }
    }
}
