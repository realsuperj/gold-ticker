using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace GoldTicker.Wpf.Core;

public sealed class SymbolMeta
{
    public string Id { get; set; } = "";
    public string NameCn { get; set; } = "";
    public string NameEn { get; set; } = "";
    public string CardEn { get; set; } = "";
    public string UnitCn { get; set; } = "";
    public string UnitEn { get; set; } = "";
    public bool IsEstimated { get; set; }
    public double Spread { get; set; }
}

public sealed class QuoteData
{
    public string Symbol { get; set; } = "au9999";
    public double Price { get; set; }
    public double PrevClose { get; set; }
    public double OpenPrice { get; set; }
    public double High { get; set; }
    public double Low { get; set; }
    public double Change { get; set; }
    public double ChangePct { get; set; }
    public string TimeStr { get; set; } = "--:--";
    public string SourceId { get; set; } = "";
    public string SourceName { get; set; } = "";
    public bool IsEstimated { get; set; }
    public double FxRate { get; set; }
    public double UsdPrice { get; set; }
    public string Error { get; set; }

    public QuoteData Clone() => (QuoteData)MemberwiseClone();
}

public sealed class IntradayPoint
{
    public long Ts { get; set; }
    public string T { get; set; } = "";
    public double P { get; set; }
    public string S { get; set; } = "";
}

public sealed class AppConfig
{
    public string Symbol { get; set; } = GoldConstants.SymbolAu9999;
    public bool ShowOnDesktop { get; set; } = true;
    public bool ShowMenuBarIcon { get; set; } = true;
    public bool ShowChart { get; set; } = true;
    public bool ShowDetails { get; set; } = true;
    public bool AlwaysOnTop { get; set; } = true;
    public int Width { get; set; } = 216;
    public double Opacity { get; set; } = 0.88;
    public int RefreshSeconds { get; set; } = 10;
    public string ColorMode { get; set; } = "cny";
    public string ChangeBasis { get; set; } = "prevClose";
    public string Language { get; set; } = "auto";
    public double WindowX { get; set; } = -1;
    public double WindowY { get; set; } = -1;
}

public static class GoldConstants
{
    public const string Version = "1.0.6";
    public const string Copyright = "Copyright © 2026 realsuperj. MIT License.";
    public const string GithubUrl = "https://github.com/realsuperj/gold-ticker";

    public const string SymbolAu9999 = "au9999";
    public const string SymbolZsJcj = "zs_jcj";
    public const string SymbolIcbcJcj = "icbc_jcj";
    public const string SymbolCcbJcj = "ccb_jcj";
    public const string SymbolXauUsd = "xau_usd";

    public static readonly string[] SupportedSymbols =
    {
        SymbolAu9999, SymbolZsJcj, SymbolIcbcJcj, SymbolCcbJcj, SymbolXauUsd
    };

    public static readonly int[] ValidWidths = { 180, 200, 216, 240, 280 };
    public static readonly int[] ValidRefreshIntervals = { 10, 15, 30, 60, 300 };
    public static readonly double[] ValidOpacities = { 0.60, 0.75, 0.88, 0.95, 1.00 };

    public const int MinRefreshSeconds = 10;
    public const int CoolDownSeconds = 180;

    public const string DisclaimerCn =
        "【免责声明】本软件仅供个人行情参考与学习交流，不构成任何投资建议或交易依据。" +
        "积存金价格基于基准行情或常规点差估算，遇极端行情或非交易时段，银行可能调整点差，实际成交以各银行客户端为准。" +
        "数据来源于公开公共网络接口，存在网络传输延迟，据此操作风险自担。";

    public const string DisclaimerEn =
        "[Disclaimer] GoldTicker is provided solely for personal market tracking and educational purposes, and does not constitute investment or trading advice. " +
        "Commercial bank gold quotes may use standard spread estimates and differ from actual execution prices during volatile or off-market hours. " +
        "Market feeds come from public internet endpoints subject to latency; trade at your own risk.";

    public static readonly Dictionary<string, SymbolMeta> Meta = new Dictionary<string, SymbolMeta>
    {
        [SymbolAu9999] = new SymbolMeta { Id = SymbolAu9999, NameCn = "上金所 Au99.99", NameEn = "SGE Au99.99", CardEn = "SGE · Au99.99", UnitCn = "元/克", UnitEn = "CNY/g" },
        [SymbolZsJcj] = new SymbolMeta { Id = SymbolZsJcj, NameCn = "浙商银行积存金", NameEn = "Zheshang Gold", CardEn = "CZBank · Gold", UnitCn = "元/克", UnitEn = "CNY/g" },
        [SymbolIcbcJcj] = new SymbolMeta { Id = SymbolIcbcJcj, NameCn = "工商银行积存金", NameEn = "ICBC Gold", CardEn = "ICBC · Gold (Est. Spread)", UnitCn = "元/克", UnitEn = "CNY/g", IsEstimated = true, Spread = 0.80 },
        [SymbolCcbJcj] = new SymbolMeta { Id = SymbolCcbJcj, NameCn = "建设银行积存金", NameEn = "CCB Gold", CardEn = "CCB · Gold (Est. Spread)", UnitCn = "元/克", UnitEn = "CNY/g", IsEstimated = true, Spread = 0.75 },
        [SymbolXauUsd] = new SymbolMeta { Id = SymbolXauUsd, NameCn = "伦敦金现货 (XAU)", NameEn = "XAU/USD Spot", CardEn = "Spot Gold · XAU/USD", UnitCn = "美元/盎司", UnitEn = "USD/oz" },
    };
}

public static class GoldI18n
{
    private static readonly Dictionary<string, (string zh, string en)> Dict = new Dictionary<string, (string, string)>
    {
        ["refreshing"] = ("刷新中...", "Refreshing..."),
        ["fetch_error"] = ("行情暂不可用", "Quote unavailable"),
        ["alwaysOnTop"] = ("窗口置顶", "Always on Top"),
        ["showChart"] = ("显示走势图", "Show Chart"),
        ["showDetails"] = ("显示 高/低/基准价", "Show High/Low/Base Price"),
        ["cardWidth"] = ("卡片宽度", "Card Width"),
        ["cardOpacity"] = ("卡片透明度", "Card Opacity"),
        ["resetPos"] = ("重置窗口位置", "Reset Window Position"),
        ["symbols"] = ("行情标的", "Gold Symbols"),
        ["changeBasis"] = ("涨跌对比", "Price Change Basis"),
        ["prevClose"] = ("较昨收价 (prevClose)", "vs Prev Close (prevClose)"),
        ["openPrice"] = ("较今开盘 (open)", "vs Open Price (open)"),
        ["colorMode"] = ("涨跌配色", "Color Mode"),
        ["cnyColors"] = ("红涨绿跌 (国内习惯)", "Red Up / Green Down (CN)"),
        ["intlColors"] = ("绿涨红跌 (国际习惯)", "Green Up / Red Down (Intl)"),
        ["menu_language"] = ("语言 (Language)", "Language (语言)"),
        ["menu_lang_auto"] = ("跟随系统 (Auto)", "Auto (System Default)"),
        ["menu_lang_zh"] = ("简体中文", "Simplified Chinese (简体中文)"),
        ["menu_lang_en"] = ("English", "English"),
        ["refreshInterval"] = ("刷新频率", "Refresh Interval"),
        ["seconds"] = ("秒", "seconds"),
        ["recommend"] = ("推荐", "Recommended"),
        ["advanced"] = ("高级与配置", "Advanced Settings"),
        ["openConfigFolder"] = ("打开配置文件所在目录", "Open Configuration Directory"),
        ["reloadConfig"] = ("重新加载配置 (免重启)", "Reload Configuration (No Restart)"),
        ["clearCache"] = ("清除走势缓存与历史", "Clear Intraday Trend Cache"),
        ["aboutMenu"] = ("关于与免责", "About & Disclaimer"),
        ["aboutApp"] = ("关于 GoldTicker...", "About GoldTicker..."),
        ["viewDisclaimer"] = ("查看免责声明...", "View Financial Disclaimer..."),
        ["visitGithub"] = ("访问 GitHub 仓库", "Visit GitHub Repository"),
        ["quitApp"] = ("退出 GoldTicker", "Quit GoldTicker"),
        ["estTag"] = ("(估算)", "(Est)"),
        ["estSpreadCn"] = ("(点差估算)", "(Est. Spread)"),
        ["about_title"] = ("关于 GoldTicker", "About GoldTicker"),
        ["about_body"] = ("版本：{0}\n轻量桌面黄金行情小组件\n{1}", "Version: {0}\nLightweight desktop gold price widget\n{1}"),
        ["disclaimer_title"] = ("免责声明与数据说明", "Disclaimer & Data Sources"),
        ["ok"] = ("确定", "OK"),
    };

    public static string ResolveLanguage(string setting)
    {
        var s = (setting ?? "auto").Trim().ToLowerInvariant();
        if (s == "zh" || s == "cn" || s == "zh-cn" || s == "zh_cn") return "zh";
        if (s == "en" || s == "english") return "en";
        var sys = CultureInfo.CurrentUICulture.Name.ToLowerInvariant();
        return sys.StartsWith("zh") ? "zh" : "en";
    }

    public static string T(string key, string langSetting)
    {
        var lang = ResolveLanguage(langSetting);
        if (!Dict.TryGetValue(key, out var pair)) return key;
        return lang == "en" ? pair.en : pair.zh;
    }
}

public static class GoldStorage
{
    private static readonly UTF8Encoding Utf8NoBom = new UTF8Encoding(false);
    private static readonly Regex DayFileRegex = new Regex(@"^intraday-(\d{4}-\d{2}-\d{2})\.json$", RegexOptions.Compiled);

    public static string GetAppDataDir()
    {
        var env = Environment.GetEnvironmentVariable("GOLDTICKER_DATA_DIR");
        string dir;
        if (!string.IsNullOrWhiteSpace(env))
        {
            dir = Path.GetFullPath(env);
        }
        else
        {
            var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            dir = !string.IsNullOrWhiteSpace(appData)
                ? Path.Combine(appData, "GoldTicker")
                : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".gold-ticker");
        }
        Directory.CreateDirectory(dir);
        return dir;
    }

    public static string GetConfigPath() => Path.Combine(GetAppDataDir(), "config.json");

    public static AppConfig LoadConfig()
    {
        var path = GetConfigPath();
        if (!File.Exists(path))
        {
            var def = new AppConfig();
            SaveConfig(def);
            return def;
        }
        try
        {
            var raw = File.ReadAllText(path, Encoding.UTF8);
            var dict = MiniJson.Parse(raw) as IDictionary<string, object>;
            return SanitizeConfig(dict);
        }
        catch
        {
            return new AppConfig();
        }
    }

    public static AppConfig SanitizeConfig(IDictionary<string, object> d)
    {
        var c = new AppConfig();
        if (d == null) return c;

        string GetStr(string k, string alt = null)
        {
            if (d.TryGetValue(k, out var v) && v != null) return v.ToString();
            if (alt != null && d.TryGetValue(alt, out var v2) && v2 != null) return v2.ToString();
            return null;
        }

        var sym = (GetStr("symbol", "dataSource") ?? "").Trim();
        if (Array.IndexOf(GoldConstants.SupportedSymbols, sym) >= 0) c.Symbol = sym;

        if (TryBool(d, "showOnDesktop", out var sod)) c.ShowOnDesktop = sod;
        if (TryBool(d, "showMenuBarIcon", out var smb) || TryBool(d, "showMenuBar", out smb)) c.ShowMenuBarIcon = smb;
        if (TryBool(d, "showChart", out var sc)) c.ShowChart = sc;
        if (TryBool(d, "showDetails", out var sd)) c.ShowDetails = sd;
        if (TryBool(d, "alwaysOnTop", out var aot)) c.AlwaysOnTop = aot;
        if (!c.ShowOnDesktop && !c.ShowMenuBarIcon) c.ShowOnDesktop = true;

        if (TryDouble(d, "width", out var w))
        {
            var wi = (int)Math.Round(w);
            c.Width = GoldConstants.ValidWidths.OrderBy(x => Math.Abs(x - wi)).First();
        }

        if (TryDouble(d, "opacity", out var op))
            c.Opacity = Math.Max(0.60, Math.Min(1.0, op));

        if (TryDouble(d, "refreshSeconds", out var rs) || TryDouble(d, "refreshInterval", out rs))
            c.RefreshSeconds = Math.Max(GoldConstants.MinRefreshSeconds, (int)Math.Round(rs));

        var cm = (GetStr("colorMode") ?? "cny").Trim().ToLowerInvariant();
        c.ColorMode = (cm == "intl" || cm == "green-up") ? "intl" : "cny";

        var cb = (GetStr("changeBasis") ?? "prevClose").Trim();
        c.ChangeBasis = (cb == "open" || cb == "open_price") ? "open" : "prevClose";

        var lang = (GetStr("language") ?? "auto").Trim().ToLowerInvariant();
        c.Language = (lang == "zh" || lang == "en" || lang == "auto") ? lang : "auto";

        if (TryDouble(d, "windowX", out var wx)) c.WindowX = wx;
        if (TryDouble(d, "windowY", out var wy)) c.WindowY = wy;

        return c;
    }

    public static void SaveConfig(AppConfig cfg)
    {
        try
        {
            var path = GetConfigPath();
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"symbol\": \"{0}\",\n", EscapeJson(cfg.Symbol));
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"showOnDesktop\": {0},\n", cfg.ShowOnDesktop ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"showMenuBarIcon\": {0},\n", cfg.ShowMenuBarIcon ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"showChart\": {0},\n", cfg.ShowChart ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"showDetails\": {0},\n", cfg.ShowDetails ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"alwaysOnTop\": {0},\n", cfg.AlwaysOnTop ? "true" : "false");
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"width\": {0},\n", cfg.Width);
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"opacity\": {0:0.##},\n", cfg.Opacity);
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"refreshSeconds\": {0},\n", Math.Max(GoldConstants.MinRefreshSeconds, cfg.RefreshSeconds));
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"colorMode\": \"{0}\",\n", EscapeJson(cfg.ColorMode));
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"changeBasis\": \"{0}\",\n", EscapeJson(cfg.ChangeBasis));
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"language\": \"{0}\",\n", EscapeJson(cfg.Language));
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"windowX\": {0:0.#},\n", cfg.WindowX);
            sb.AppendFormat(CultureInfo.InvariantCulture, "  \"windowY\": {0:0.#}\n", cfg.WindowY);
            sb.Append("}");
            AtomicWrite(path, sb.ToString());
        }
        catch
        {
            // Ignore IO transient lock
        }
    }

    private static readonly object StorageLock = new object();

    public static string GetIntradayPath(string dateStr = null)
    {
        var d = dateStr ?? DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        return Path.Combine(GetAppDataDir(), $"intraday-{d}.json");
    }

    public static void CleanupOldHistory(int keepDays = 3)
    {
        try
        {
            var dir = GetAppDataDir();
            var today = DateTime.Today;
            foreach (var file in Directory.GetFiles(dir, "intraday-*.json"))
            {
                var name = Path.GetFileName(file);
                var m = DayFileRegex.Match(name);
                if (!m.Success) continue;
                if (DateTime.TryParseExact(m.Groups[1].Value, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var dt))
                {
                    if ((today - dt.Date).TotalDays > keepDays)
                        File.Delete(file);
                }
            }
        }
        catch { }
    }

    public static List<IntradayPoint> LoadTodayPoints(string symbol)
    {
        lock (StorageLock)
        {
            var path = GetIntradayPath();
            var (pts, _) = ReadDayDoc(path);
            var want = NormalizeSymbol(symbol);
            return string.IsNullOrEmpty(want) ? pts : pts.Where(p => p.S == want && p.P > 0 && p.Ts > 0).ToList();
        }
    }

    public static void RecordPricePoint(double price, string symbol, long? tsMs = null)
    {
        if (price <= 0 || string.IsNullOrEmpty(symbol)) return;
        lock (StorageLock)
        {
            var ts = tsMs ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            var localDt = DateTimeOffset.FromUnixTimeMilliseconds(ts).LocalDateTime;
            var dateStr = localDt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            var minuteKey = localDt.ToString("HH:mm", CultureInfo.InvariantCulture);
            var path = GetIntradayPath(dateStr);
            var (pts, basis) = ReadDayDoc(path);
            var normSym = NormalizeSymbol(symbol);

            pts.Add(new IntradayPoint
            {
                Ts = ts,
                T = minuteKey,
                P = Math.Round(price, 2),
                S = normSym,
            });
            pts.Sort((a, b) => a.Ts.CompareTo(b.Ts));

            var merged = new List<IntradayPoint>(pts.Count);
            foreach (var pt in pts)
            {
                var ptMin = DateTimeOffset.FromUnixTimeMilliseconds(pt.Ts).LocalDateTime.ToString("HH:mm", CultureInfo.InvariantCulture);
                var prev = merged.Count > 0 ? merged[merged.Count - 1] : null;
                if (prev != null && prev.S == pt.S)
                {
                    var prevMin = DateTimeOffset.FromUnixTimeMilliseconds(prev.Ts).LocalDateTime.ToString("HH:mm", CultureInfo.InvariantCulture);
                    if (prevMin == ptMin)
                    {
                        prev.P = pt.P;
                        prev.Ts = pt.Ts;
                        prev.T = string.IsNullOrEmpty(pt.T) ? ptMin : pt.T;
                        continue;
                    }
                }
                merged.Add(pt);
            }

            WriteDayDoc(path, merged, basis);
        }
    }

    public static void FreezeDayBasis(string symbol, double prevClose, double openPrice)
    {
        if (prevClose <= 0 || string.IsNullOrEmpty(symbol)) return;
        lock (StorageLock)
        {
            var path = GetIntradayPath();
            var (pts, basis) = ReadDayDoc(path);
            if (basis.TryGetValue(symbol, out var existing) && existing.prevClose > 0)
                return;
            basis[symbol] = (Math.Round(prevClose, 2), Math.Round(openPrice, 2));
            WriteDayDoc(path, pts, basis);
        }
    }

    public static QuoteData ApplyFrozenBasis(QuoteData quote)
    {
        if (quote == null || quote.Price <= 0 || string.IsNullOrEmpty(quote.Symbol)) return quote;
        (double prevClose, double open) entry;
        lock (StorageLock)
        {
            var (_, basis) = ReadDayDoc(GetIntradayPath());
            if (!basis.TryGetValue(quote.Symbol, out entry) || entry.prevClose <= 0)
                return quote;
        }
        var q = quote.Clone();
        q.PrevClose = entry.prevClose;
        if (entry.open > 0) q.OpenPrice = entry.open;
        q.Change = Math.Round(q.Price - q.PrevClose, 2);
        q.ChangePct = q.PrevClose > 0 ? Math.Round(q.Change / q.PrevClose * 100.0, 2) : 0.0;
        return q;
    }

    public static void ClearIntradayCache()
    {
        lock (StorageLock)
        {
            var path = GetIntradayPath();
            if (File.Exists(path)) File.Delete(path);
        }
    }

    private static string NormalizeSymbol(string s)
    {
        if (s == "sina_au9999" || s == "tangdouz") return GoldConstants.SymbolAu9999;
        return s;
    }

    private static (List<IntradayPoint> points, Dictionary<string, (double prevClose, double open)> basis) ReadDayDoc(string path)
    {
        var pts = new List<IntradayPoint>();
        var basis = new Dictionary<string, (double prevClose, double open)>();
        if (!File.Exists(path)) return (pts, basis);

        var dateStr = DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        var m = DayFileRegex.Match(Path.GetFileName(path));
        if (m.Success) dateStr = m.Groups[1].Value;

        try
        {
            var raw = File.ReadAllText(path, Encoding.UTF8);
            var root = MiniJson.Parse(raw);
            IEnumerable rawPoints = null;
            if (root is IDictionary<string, object> dict)
            {
                if (dict.TryGetValue("points", out var pObj)) rawPoints = pObj as IEnumerable;
                if (dict.TryGetValue("basis", out var bObj) && bObj is IDictionary<string, object> bDict)
                {
                    foreach (var kv in bDict)
                    {
                        if (kv.Value is IDictionary<string, object> entry && TryDouble(entry, "prev_close", out var pc) && pc > 0)
                        {
                            TryDouble(entry, "open", out var op);
                            basis[kv.Key] = (pc, op);
                        }
                    }
                }
            }
            else if (root is IEnumerable arr)
            {
                rawPoints = arr;
            }

            if (rawPoints != null)
            {
                foreach (var item in rawPoints)
                {
                    if (!(item is IDictionary<string, object> pd)) continue;
                    if (!TryDouble(pd, "p", out var price) || price <= 0) continue;
                    var sym = NormalizeSymbol(pd.TryGetValue("s", out var sv) && sv != null ? sv.ToString() : "");
                    var tStr = pd.TryGetValue("t", out var tv) && tv != null ? tv.ToString() : "";
                    long ts = 0;
                    if (TryDouble(pd, "ts", out var tsv) && tsv > 0)
                    {
                        ts = (long)tsv;
                    }
                    else if (!string.IsNullOrEmpty(tStr))
                    {
                        var bits = tStr.Split(':');
                        if (bits.Length >= 2
                            && int.TryParse(bits[0], out var hh)
                            && int.TryParse(bits[1], out var mm)
                            && DateTime.TryParseExact(dateStr, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var day))
                        {
                            var local = new DateTime(day.Year, day.Month, day.Day, hh, mm, 0, DateTimeKind.Local);
                            ts = new DateTimeOffset(local).ToUnixTimeMilliseconds();
                            tStr = $"{hh:D2}:{mm:D2}";
                        }
                    }
                    if (ts > 0)
                        pts.Add(new IntradayPoint { Ts = ts, T = tStr, P = price, S = sym });
                }
            }
        }
        catch { }

        return (pts, basis);
    }

    private static void WriteDayDoc(string path, List<IntradayPoint> points, Dictionary<string, (double prevClose, double open)> basis)
    {
        var sb = new StringBuilder(points.Count * 64 + 256);
        sb.AppendLine("{");
        sb.AppendLine("  \"points\": [");
        for (int i = 0; i < points.Count; i++)
        {
            var p = points[i];
            var comma = i < points.Count - 1 ? "," : "";
            sb.AppendFormat(CultureInfo.InvariantCulture,
                "    {{\"ts\": {0}, \"t\": \"{1}\", \"p\": {2:0.##}, \"s\": \"{3}\"}}{4}\n",
                p.Ts, EscapeJson(p.T), p.P, EscapeJson(p.S), comma);
        }
        sb.AppendLine("  ],");
        sb.AppendLine("  \"basis\": {");
        var keys = basis.Keys.ToList();
        for (int i = 0; i < keys.Count; i++)
        {
            var k = keys[i];
            var v = basis[k];
            var comma = i < keys.Count - 1 ? "," : "";
            sb.AppendFormat(CultureInfo.InvariantCulture,
                "    \"{0}\": {{\"prev_close\": {1:0.##}, \"open\": {2:0.##}}}{3}\n",
                EscapeJson(k), v.prevClose, v.open, comma);
        }
        sb.AppendLine("  }");
        sb.Append("}");
        AtomicWrite(path, sb.ToString());
    }

    private static void AtomicWrite(string path, string content)
    {
        var dir = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        var tmp = path + ".tmp";
        File.WriteAllText(tmp, content, Utf8NoBom);
        if (File.Exists(path)) File.Delete(path);
        File.Move(tmp, path);
    }

    private static string EscapeJson(string s) => (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"");

    private static bool TryBool(IDictionary<string, object> d, string key, out bool val)
    {
        val = false;
        if (!d.TryGetValue(key, out var o) || o == null) return false;
        if (o is bool b) { val = b; return true; }
        return bool.TryParse(o.ToString(), out val);
    }

    private static bool TryDouble(IDictionary<string, object> d, string key, out double val)
    {
        val = 0;
        if (!d.TryGetValue(key, out var o) || o == null) return false;
        if (o is int i) { val = i; return true; }
        if (o is long l) { val = l; return true; }
        if (o is double db) { val = db; return true; }
        if (o is decimal dc) { val = (double)dc; return true; }
        return double.TryParse(Convert.ToString(o, CultureInfo.InvariantCulture), NumberStyles.Any, CultureInfo.InvariantCulture, out val);
    }
}

public sealed class PricingEngine
{
    private const string TangdouzUrl = "https://api.tangdouz.com/a/zsgold.php";
    private const string SinaHqUrl = "https://hq.sinajs.cn/list=";
    private const string UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

    private static readonly HttpClient Http;
    private static readonly UTF8Encoding StrictUtf8 = new UTF8Encoding(false, true);

    private readonly Dictionary<string, (int fails, DateTime until)> _failures = new Dictionary<string, (int, DateTime)>();
    private readonly Dictionary<string, QuoteData> _cache = new Dictionary<string, QuoteData>();
    private readonly object _sync = new object();

    static PricingEngine()
    {
        ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12 | SecurityProtocolType.Tls11;
        var handler = new HttpClientHandler
        {
            AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate,
            UseProxy = true,
        };
        Http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(6) };
        Http.DefaultRequestHeaders.TryAddWithoutValidation("User-Agent", UserAgent);
    }

    public QuoteData GetCachedQuote(string symbol)
    {
        lock (_sync)
            return _cache.TryGetValue(symbol, out var q) ? q.Clone() : null;
    }

    public async Task<Dictionary<string, QuoteData>> SampleAllQuotesAsync()
    {
        var result = new Dictionary<string, QuoteData>();

        try
        {
            var (xauPack, rawUsd, rate) = await FetchSinaXauRawAsync().ConfigureAwait(false);
            RecordSuccess("sina_xau");
            result[GoldConstants.SymbolXauUsd] = BuildQuote(GoldConstants.SymbolXauUsd, xauPack, "sina_xau", "伦敦金现货", rate, rawUsd);
        }
        catch (Exception ex)
        {
            RecordFailure("sina_xau", ex.Message);
            var cached = GetCachedQuote(GoldConstants.SymbolXauUsd);
            if (cached != null) result[GoldConstants.SymbolXauUsd] = cached;
        }

        bool zsOk = false;
        if (!IsCoolingDown("tangdouz"))
        {
            try
            {
                var pack = await FetchTangdouzRawAsync().ConfigureAwait(false);
                RecordSuccess("tangdouz");
                result[GoldConstants.SymbolZsJcj] = BuildQuote(GoldConstants.SymbolZsJcj, pack, "tangdouz", "浙商银行直连");
                zsOk = true;
            }
            catch (Exception ex)
            {
                RecordFailure("tangdouz", ex.Message);
            }
        }
        if (!zsOk)
        {
            var cached = GetCachedQuote(GoldConstants.SymbolZsJcj);
            if (cached != null) result[GoldConstants.SymbolZsJcj] = cached;
        }

        try
        {
            var (pack, sid, sname) = await FetchBenchmarkAu9999Async().ConfigureAwait(false);
            foreach (var sym in new[] { GoldConstants.SymbolAu9999, GoldConstants.SymbolIcbcJcj, GoldConstants.SymbolCcbJcj })
                result[sym] = BuildQuote(sym, pack, sid, sname);
            if (!result.ContainsKey(GoldConstants.SymbolZsJcj))
                result[GoldConstants.SymbolZsJcj] = BuildQuote(GoldConstants.SymbolZsJcj, pack, sid, sname);
        }
        catch
        {
            foreach (var sym in new[] { GoldConstants.SymbolAu9999, GoldConstants.SymbolIcbcJcj, GoldConstants.SymbolCcbJcj })
            {
                var cached = GetCachedQuote(sym);
                if (cached != null) result[sym] = cached;
            }
        }

        foreach (var sym in GoldConstants.SupportedSymbols)
        {
            if (!result.ContainsKey(sym))
            {
                var cached = GetCachedQuote(sym);
                if (cached != null) result[sym] = cached;
            }
        }

        return result;
    }

    private struct Pack
    {
        public double Price, Prev, Open, High, Low, Change, Pct;
        public string TimeStr;
    }

    private QuoteData BuildQuote(string symbol, Pack pack, string sourceId, string sourceName, double fx = 0, double usd = 0)
    {
        var meta = GoldConstants.Meta[symbol];
        double p = pack.Price, prev = pack.Prev, op = pack.Open, h = pack.High, l = pack.Low, chg = pack.Change, pct = pack.Pct;
        bool isEst = meta.IsEstimated;
        if (meta.Spread > 0)
        {
            p = Math.Round(p + meta.Spread, 2);
            prev = Math.Round(prev + meta.Spread, 2);
            op = Math.Round(op + meta.Spread, 2);
            h = Math.Round(h + meta.Spread, 2);
            l = Math.Round(l + meta.Spread, 2);
            chg = Math.Round(p - prev, 2);
            pct = prev > 0 ? Math.Round(chg / prev * 100.0, 2) : 0.0;
            sourceName = sourceName + " (点差估算)";
            isEst = true;
        }
        var q = new QuoteData
        {
            Symbol = symbol,
            Price = p,
            PrevClose = prev,
            OpenPrice = op,
            High = h,
            Low = l,
            Change = chg,
            ChangePct = pct,
            TimeStr = pack.TimeStr,
            SourceId = sourceId,
            SourceName = sourceName,
            IsEstimated = isEst,
            FxRate = fx,
            UsdPrice = usd,
        };
        lock (_sync)
            _cache[symbol] = q.Clone();
        return q;
    }

    private async Task<(Pack pack, string sid, string sname)> FetchBenchmarkAu9999Async()
    {
        var sources = new (string id, string name, Func<Task<Pack>> fn)[]
        {
            ("sina_au9999", "上金所 Au99.99", FetchSinaAu9999RawAsync),
            ("sina_autd", "上金所 Au(T+D)", FetchSinaAutdRawAsync),
            ("tangdouz", "浙商积存金", FetchTangdouzRawAsync),
        };
        Exception last = null;
        foreach (var src in sources)
        {
            if (IsCoolingDown(src.id)) continue;
            try
            {
                var p = await src.fn().ConfigureAwait(false);
                RecordSuccess(src.id);
                return (p, src.id, src.name);
            }
            catch (Exception ex)
            {
                RecordFailure(src.id, ex.Message);
                last = ex;
            }
        }
        return (await FetchSinaAu9999RawAsync().ConfigureAwait(false), "sina_au9999", "上金所 Au99.99");
    }

    private static async Task<byte[]> HttpGetBytesAsync(string url, string referer = null)
    {
        using (var req = new HttpRequestMessage(HttpMethod.Get, url))
        {
            if (!string.IsNullOrEmpty(referer))
                req.Headers.TryAddWithoutValidation("Referer", referer);
            using (var resp = await Http.SendAsync(req).ConfigureAwait(false))
            {
                resp.EnsureSuccessStatusCode();
                return await resp.Content.ReadAsByteArrayAsync().ConfigureAwait(false);
            }
        }
    }

    private static async Task<Pack> FetchTangdouzRawAsync()
    {
        var raw = await HttpGetBytesAsync(TangdouzUrl).ConfigureAwait(false);
        string text;
        try { text = StrictUtf8.GetString(raw); }
        catch { text = DecodeGb(raw); }

        var lines = new Dictionary<string, string>();
        foreach (var line in text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var idx = line.IndexOf(':');
            if (idx > 0)
                lines[line.Substring(0, idx).Trim()] = line.Substring(idx + 1).Trim();
        }

        double Val(string k)
        {
            if (!lines.TryGetValue(k, out var v)) return 0;
            var sb = new StringBuilder();
            foreach (var ch in v)
                if (char.IsDigit(ch) || ch == '.' || ch == '-') sb.Append(ch);
            return ParseNum(sb.ToString());
        }

        var price = Val("最新价格");
        if (price <= 0) throw new InvalidOperationException("Tangdouz empty price");
        var tm = ParseTimeSuffix(lines.TryGetValue("更新时间", out var u) ? u : "");
        return CalcPack(price, Val("前收盘价"), Val("开盘价"), Val("最高价"), Val("最低价"), tm);
    }

    private static async Task<Dictionary<string, string[]>> FetchSinaListAsync(string codes)
    {
        var raw = await HttpGetBytesAsync(SinaHqUrl + codes, "https://finance.sina.com.cn").ConfigureAwait(false);
        var text = DecodeGb(raw);
        var map = new Dictionary<string, string[]>();
        foreach (var line in text.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var p1 = line.IndexOf("hq_str_", StringComparison.Ordinal);
            var p2 = line.IndexOf("=\"", StringComparison.Ordinal);
            if (p1 < 0 || p2 < 0) continue;
            var key = line.Substring(p1 + 7, p2 - (p1 + 7)).Trim();
            var body = line.Substring(p2 + 2).TrimEnd(';', '"', ' ');
            map[key] = body.Split(',');
        }
        return map;
    }

    private static async Task<Pack> FetchSinaAu9999RawAsync()
    {
        var map = await FetchSinaListAsync("SGE_AU9999").ConfigureAwait(false);
        if (!map.TryGetValue("SGE_AU9999", out var d) || d.Length < 10)
            throw new InvalidOperationException("Sina SGE_AU9999 invalid");
        var price = ParseNum(d[3]);
        if (price <= 0) throw new InvalidOperationException("Sina SGE_AU9999 zero price");
        var tm = d.Length > 16 ? ParseTimeSuffix(d[16]) : "--:--";
        return CalcPack(price, ParseNum(d[5]), ParseNum(d[9]), ParseNum(d[7]), ParseNum(d[8]), tm);
    }

    private static async Task<Pack> FetchSinaAutdRawAsync()
    {
        var map = await FetchSinaListAsync("gds_AUTD").ConfigureAwait(false);
        if (!map.TryGetValue("gds_AUTD", out var d) || d.Length < 9)
            throw new InvalidOperationException("Sina gds_AUTD invalid");
        var price = ParseNum(d[0]);
        if (price <= 0) throw new InvalidOperationException("Sina gds_AUTD zero price");
        return CalcPack(price, ParseNum(d[7]), ParseNum(d[8]), ParseNum(d[4]), ParseNum(d[5]), ParseTimeSuffix(d[6]));
    }

    private static async Task<(Pack pack, double rawUsd, double rate)> FetchSinaXauRawAsync()
    {
        var map = await FetchSinaListAsync("hf_XAU,fx_susdcny").ConfigureAwait(false);
        if (!map.TryGetValue("hf_XAU", out var xau) || xau.Length < 9 || !map.TryGetValue("fx_susdcny", out var fx) || fx.Length < 2)
            throw new InvalidOperationException("Sina XAU invalid");
        var rate = ParseNum(fx[1]);
        var rawUsd = ParseNum(xau[0]);
        if (rate <= 0 || rawUsd <= 0) throw new InvalidOperationException("Sina XAU zero");
        return (CalcPack(rawUsd, ParseNum(xau[7]), ParseNum(xau[8]), ParseNum(xau[4]), ParseNum(xau[5]), ParseTimeSuffix(xau[6])), rawUsd, rate);
    }

    private static Pack CalcPack(double price, double prev, double op, double high, double low, string tm)
    {
        price = Math.Round(price, 2);
        prev = Math.Round(prev, 2);
        if (prev <= 0) prev = Math.Round(op > 0 ? op : price, 2);
        op = Math.Round(op, 2);
        high = Math.Round(high, 2);
        low = Math.Round(low, 2);
        var chg = Math.Round(price - prev, 2);
        var pct = prev > 0 ? Math.Round(chg / prev * 100.0, 2) : 0.0;
        return new Pack { Price = price, Prev = prev, Open = op, High = high, Low = low, Change = chg, Pct = pct, TimeStr = string.IsNullOrEmpty(tm) ? "--:--" : tm };
    }

    private static string DecodeGb(byte[] raw)
    {
        try { return Encoding.GetEncoding(54936).GetString(raw); }
        catch
        {
            try { return Encoding.GetEncoding(936).GetString(raw); }
            catch { return Encoding.UTF8.GetString(raw); }
        }
    }

    private static double ParseNum(string s) =>
        double.TryParse((s ?? "").Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out var v) ? v : 0.0;

    private static string ParseTimeSuffix(string s)
    {
        if (string.IsNullOrWhiteSpace(s)) return "--:--";
        var tail = s.Trim();
        var sp = tail.LastIndexOf(' ');
        if (sp >= 0) tail = tail.Substring(sp + 1);
        var bits = tail.Split(':');
        if (bits.Length >= 2 && int.TryParse(bits[0], out var hh) && int.TryParse(bits[1], out var mm))
            return $"{hh:D2}:{mm:D2}";
        return "--:--";
    }

    private bool IsCoolingDown(string id)
    {
        lock (_sync)
            return _failures.TryGetValue(id, out var r) && DateTime.UtcNow < r.until;
    }

    private void RecordFailure(string id, string err)
    {
        lock (_sync)
        {
            _failures.TryGetValue(id, out var r);
            var fails = r.fails + 1;
            var until = fails >= 2 ? DateTime.UtcNow.AddSeconds(GoldConstants.CoolDownSeconds) : r.until;
            _failures[id] = (fails, until);
        }
    }

    private void RecordSuccess(string id)
    {
        lock (_sync) _failures.Remove(id);
    }
}

internal static class MiniJson
{
    public static object Parse(string json)
    {
        if (string.IsNullOrWhiteSpace(json)) return null;
        int idx = 0;
        return ReadValue(json, ref idx);
    }

    private static void SkipWs(string s, ref int i)
    {
        while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
    }

    private static object ReadValue(string s, ref int i)
    {
        SkipWs(s, ref i);
        if (i >= s.Length) return null;
        char c = s[i];
        if (c == '{') return ReadObject(s, ref i);
        if (c == '[') return ReadArray(s, ref i);
        if (c == '"') return ReadString(s, ref i);
        if (c == 't' || c == 'f') return ReadBool(s, ref i);
        if (c == 'n') { i += 4; return null; }
        return ReadNumber(s, ref i);
    }

    private static Dictionary<string, object> ReadObject(string s, ref int i)
    {
        var map = new Dictionary<string, object>();
        i++; // '{'
        SkipWs(s, ref i);
        if (i < s.Length && s[i] == '}') { i++; return map; }
        while (i < s.Length)
        {
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; break; }
            var key = ReadString(s, ref i);
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ':') i++;
            var val = ReadValue(s, ref i);
            map[key] = val;
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ',') { i++; continue; }
            if (i < s.Length && s[i] == '}') { i++; break; }
            break;
        }
        return map;
    }

    private static List<object> ReadArray(string s, ref int i)
    {
        var list = new List<object>();
        i++; // '['
        SkipWs(s, ref i);
        if (i < s.Length && s[i] == ']') { i++; return list; }
        while (i < s.Length)
        {
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; break; }
            list.Add(ReadValue(s, ref i));
            SkipWs(s, ref i);
            if (i < s.Length && s[i] == ',') { i++; continue; }
            if (i < s.Length && s[i] == ']') { i++; break; }
            break;
        }
        return list;
    }

    private static string ReadString(string s, ref int i)
    {
        if (s[i] == '"') i++;
        var sb = new StringBuilder();
        while (i < s.Length)
        {
            char c = s[i++];
            if (c == '"') break;
            if (c == '\\' && i < s.Length)
            {
                char esc = s[i++];
                switch (esc)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u':
                        if (i + 4 <= s.Length && int.TryParse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var hex))
                        {
                            sb.Append((char)hex);
                            i += 4;
                        }
                        break;
                    default: sb.Append(esc); break;
                }
            }
            else sb.Append(c);
        }
        return sb.ToString();
    }

    private static bool ReadBool(string s, ref int i)
    {
        if (s.Substring(i).StartsWith("true", StringComparison.Ordinal)) { i += 4; return true; }
        i += 5;
        return false;
    }

    private static double ReadNumber(string s, ref int i)
    {
        int start = i;
        while (i < s.Length && "0123456789+-.eE".IndexOf(s[i]) >= 0) i++;
        double.TryParse(s.Substring(start, i - start), NumberStyles.Any, CultureInfo.InvariantCulture, out var d);
        return d;
    }
}
