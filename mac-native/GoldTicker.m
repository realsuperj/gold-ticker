// GoldTicker — native AppKit, single-file Objective-C (ARC).
// Build: clang -fobjc-arc -Os -mmacosx-version-min=12.0 -arch arm64 -arch x86_64 -framework AppKit -framework Foundation -o GoldTicker GoldTicker.m
#import <AppKit/AppKit.h>

#define UA @"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15"

#pragma mark - Small helpers

static double R2(double v) { return round(v * 100) / 100.0; }
static NSString *Trim(NSString *s) { return [s stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet]; }
static NSArray<NSString *> *Split(NSString *s, NSString *sep) {
    return [[s componentsSeparatedByString:sep] filteredArrayUsingPredicate:[NSPredicate predicateWithFormat:@"length > 0"]];
}
static BOOL ScanInt(NSString *s, NSInteger *out) {
    NSScanner *sc = [NSScanner scannerWithString:s];
    sc.charactersToBeSkipped = nil;
    return [sc scanInteger:out] && sc.isAtEnd;
}
static BOOL ScanDbl(NSString *s, double *out) {
    NSScanner *sc = [NSScanner scannerWithString:s];
    sc.charactersToBeSkipped = nil;
    return [sc scanDouble:out] && sc.isAtEnd;
}
static double ParseDbl(NSString *s) { double v = 0; return ScanDbl(s, &v) ? v : 0; }
static NSString *HMStr(NSInteger h, NSInteger m) { return [NSString stringWithFormat:@"%02ld:%02ld", (long)h, (long)m]; }
static NSString *ParseTime(NSString *raw) {
    NSArray *bits = Split(Split(Trim(raw), @" ").lastObject ?: @"", @":");
    NSInteger h, m;
    return bits.count >= 2 && ScanInt(bits[0], &h) && ScanInt(bits[1], &m) ? HMStr(h, m) : @"--:--";
}

#pragma mark - Shared spec (Bundle Resources / Contents/Resources / cwd/shared)

static NSDictionary *gSpec;

static NSDictionary *Spec(void) {
    if (gSpec) return gSpec;
    NSFileManager *fm = NSFileManager.defaultManager;
    NSMutableArray<NSString *> *c = [NSMutableArray array];
    NSString *res = [NSBundle.mainBundle pathForResource:@"spec" ofType:@"json"];
    if (res) [c addObject:res];
    NSString *exe = [NSProcessInfo.processInfo.arguments[0] stringByResolvingSymlinksInPath];
    [c addObject:[[[exe stringByDeletingLastPathComponent] stringByDeletingLastPathComponent] stringByAppendingPathComponent:@"Resources/spec.json"]];
    [c addObject:[fm.currentDirectoryPath stringByAppendingPathComponent:@"shared/spec.json"]];
    for (NSString *p in c) {
        NSData *data = [NSData dataWithContentsOfFile:p];
        if (!data) continue;
        NSDictionary *d = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        if (d) return gSpec = d;
    }
    NSLog(@"Unable to load shared spec.json from bundle or workspace");
    abort();
}

static NSDictionary *Lim(void) { return Spec()[@"limits"]; }
static NSInteger MinRefresh(void) { return [Lim()[@"minRefreshSeconds"] integerValue]; }
static NSDictionary *Meta(NSString *sid) {
    NSArray *syms = Spec()[@"symbols"];
    for (NSDictionary *s in syms) if ([s[@"id"] isEqualToString:sid]) return s;
    return syms[0];
}

#pragma mark - i18n

static NSString *Lang(NSString *setting) {
    NSString *s = Trim(setting).lowercaseString;
    if ([@[@"zh", @"cn", @"zh_cn", @"zh-cn", @"chinese"] containsObject:s]) return @"zh";
    if ([@[@"en", @"english", @"us", @"uk"] containsObject:s]) return @"en";
    NSDictionary *env = NSProcessInfo.processInfo.environment;
    NSString *e = env[@"LANG"] ?: env[@"LC_ALL"];
    if (e && [e.lowercaseString containsString:@"zh"]) return @"zh";
    return [NSLocale.preferredLanguages.firstObject.lowercaseString hasPrefix:@"zh"] ? @"zh" : @"en";
}

static NSString *TR(NSString *key, NSString *setting, NSDictionary<NSString *, NSString *> *repl) {
    NSDictionary *entry = Spec()[@"i18n"][key];
    NSString *text = entry[Lang(setting)] ?: entry[@"zh"] ?: key;
    for (NSString *k in repl) text = [text stringByReplacingOccurrencesOfString:[NSString stringWithFormat:@"{%@}", k] withString:repl[k]];
    return text;
}
static NSString *T(NSString *key, NSString *setting) { return TR(key, setting, nil); }

#pragma mark - Models

@interface Cfg : NSObject
@property (nonatomic, copy) NSString *symbol, *colorMode, *changeBasis, *language;
@property (nonatomic) BOOL showOnDesktop, showMenuBarIcon, showChart, showDetails, alwaysOnTop;
@property (nonatomic) NSInteger width, refreshSeconds;
@property (nonatomic) double opacity, windowX, windowY;
@end
@implementation Cfg
+ (instancetype)makeDefault {
    NSDictionary *d = Spec()[@"defaults"];
    Cfg *c = [Cfg new];
    c.symbol = d[@"symbol"]; c.showOnDesktop = [d[@"showOnDesktop"] boolValue]; c.showMenuBarIcon = [d[@"showMenuBarIcon"] boolValue];
    c.showChart = [d[@"showChart"] boolValue]; c.showDetails = [d[@"showDetails"] boolValue]; c.alwaysOnTop = [d[@"alwaysOnTop"] boolValue];
    c.width = [d[@"macWidth"] integerValue]; c.opacity = [d[@"opacity"] doubleValue]; c.refreshSeconds = [d[@"refreshSeconds"] integerValue];
    c.colorMode = d[@"colorMode"]; c.changeBasis = d[@"changeBasis"]; c.language = d[@"language"];
    c.windowX = [d[@"windowX"] doubleValue]; c.windowY = [d[@"windowY"] doubleValue];
    return c;
}
@end

@interface Quote : NSObject
@property (nonatomic, copy) NSString *symbol, *timeStr, *sourceId, *sourceName, *error;
@property (nonatomic) double price, prevClose, openPrice, high, low, change, changePct, fxRate, usdPrice;
@property (nonatomic) BOOL isEstimated;
@end
@implementation Quote
- (Quote *)clone {
    Quote *q = [Quote new];
    q.symbol = _symbol; q.timeStr = _timeStr; q.sourceId = _sourceId; q.sourceName = _sourceName; q.error = _error;
    q.price = _price; q.prevClose = _prevClose; q.openPrice = _openPrice; q.high = _high; q.low = _low;
    q.change = _change; q.changePct = _changePct; q.fxRate = _fxRate; q.usdPrice = _usdPrice; q.isEstimated = _isEstimated;
    return q;
}
@end

@interface Pt : NSObject
@property (nonatomic) int64_t ts;
@property (nonatomic, copy) NSString *t, *s;
@property (nonatomic) double p;
+ (instancetype)ts:(int64_t)ts t:(NSString *)t p:(double)p s:(NSString *)s;
@end
@implementation Pt
+ (instancetype)ts:(int64_t)ts t:(NSString *)t p:(double)p s:(NSString *)s {
    Pt *x = [Pt new]; x.ts = ts; x.t = t; x.p = p; x.s = s; return x;
}
@end

#pragma mark - Config & intraday storage

typedef NSMutableDictionary<NSString *, NSArray<NSNumber *> *> Basis;   // symbol -> [prev_close, open]

static NSDateFormatter *Fmt(NSString *f) {
    NSDateFormatter *d = [NSDateFormatter new];
    d.locale = [NSLocale localeWithLocaleIdentifier:@"en_US_POSIX"];
    d.timeZone = NSTimeZone.localTimeZone;
    d.dateFormat = f;
    return d;
}
static NSDateFormatter *DateFmt(void) { static NSDateFormatter *f; static dispatch_once_t o; dispatch_once(&o, ^{ f = Fmt(@"yyyy-MM-dd"); }); return f; }
static NSString *HM(NSDate *d) { static NSDateFormatter *f; static dispatch_once_t o; dispatch_once(&o, ^{ f = Fmt(@"HH:mm"); }); return [f stringFromDate:d]; }
static NSString *HMms(int64_t ms) { return HM([NSDate dateWithTimeIntervalSince1970:ms / 1000.0]); }

static NSObject *gStorageLock;
static NSURL *AppDataDir(void) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSString *ov = NSProcessInfo.processInfo.environment[@"GOLDTICKER_DATA_DIR"];
    NSString *path = ov.length ? ov.stringByExpandingTildeInPath
                               : [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Application Support/GoldTicker"];
    NSURL *url = [NSURL fileURLWithPath:path isDirectory:YES];
    [fm createDirectoryAtURL:url withIntermediateDirectories:YES attributes:nil error:nil];
    return url;
}
static NSURL *ConfigURL(void) { return [AppDataDir() URLByAppendingPathComponent:@"config.json"]; }
static NSString *Today(NSDate *d) { return [DateFmt() stringFromDate:d ?: [NSDate date]]; }
static NSURL *IntradayURL(NSString *day) {
    return [AppDataDir() URLByAppendingPathComponent:[NSString stringWithFormat:@"intraday-%@.json", day ?: Today(nil)]];
}
static NSString *NormSym(NSString *s) { return Spec()[@"legacySymbolMap"][s] ?: s; }

static void AtomicWrite(NSData *data, NSURL *url) { [data writeToURL:url options:NSDataWritingAtomic error:nil]; }

static Cfg *Sanitize(NSDictionary *d) {
    Cfg *c = [Cfg makeDefault];
    NSDictionary *spec = Spec();
    NSString * (^str)(NSString *, NSString *) = ^NSString *(NSString *k, NSString *alt) {
        id v = d[k] ?: (alt ? d[alt] : nil);
        return v ? [NSString stringWithFormat:@"%@", v] : nil;
    };
    NSNumber * (^boolVal)(NSString *, NSString *) = ^NSNumber *(NSString *k, NSString *alt) {
        id v = d[k] ?: (alt ? d[alt] : nil);
        if ([v isKindOfClass:NSNumber.class]) return @([v boolValue]);
        if ([v isKindOfClass:NSString.class]) return @([v boolValue]);
        return nil;
    };
    NSNumber * (^dblVal)(NSString *, NSString *) = ^NSNumber *(NSString *k, NSString *alt) {
        id v = d[k] ?: (alt ? d[alt] : nil);
        if ([v isKindOfClass:NSNumber.class]) return @([v doubleValue]);
        double x;
        if ([v isKindOfClass:NSString.class] && ScanDbl(v, &x)) return @(x);
        return nil;
    };
    NSString *sym = Trim(str(@"symbol", @"dataSource") ?: @"");
    if ([[spec[@"symbols"] valueForKey:@"id"] containsObject:sym]) c.symbol = sym;
    NSNumber *n;
    if ((n = boolVal(@"showOnDesktop", nil))) c.showOnDesktop = n.boolValue;
    if ((n = boolVal(@"showMenuBarIcon", @"showMenuBar"))) c.showMenuBarIcon = n.boolValue;
    if ((n = boolVal(@"showChart", nil))) c.showChart = n.boolValue;
    if ((n = boolVal(@"showDetails", nil))) c.showDetails = n.boolValue;
    if ((n = boolVal(@"alwaysOnTop", nil))) c.alwaysOnTop = n.boolValue;
    if (!c.showOnDesktop && !c.showMenuBarIcon) c.showOnDesktop = YES;

    if ((n = dblVal(@"width", nil))) {
        NSInteger wi = (NSInteger)round(n.doubleValue), best = [spec[@"defaults"][@"macWidth"] integerValue], bd = NSIntegerMax;
        for (NSNumber *w in spec[@"options"][@"macWidths"]) if (labs(w.integerValue - wi) < bd) { bd = labs(w.integerValue - wi); best = w.integerValue; }
        c.width = best;
    }
    if ((n = dblVal(@"opacity", nil))) c.opacity = MIN(1.0, MAX(0.60, n.doubleValue));
    if ((n = dblVal(@"refreshSeconds", @"refreshInterval"))) c.refreshSeconds = MAX(MinRefresh(), (NSInteger)round(n.doubleValue));
    NSString *cm = (str(@"colorMode", nil) ?: @"cny").lowercaseString;
    c.colorMode = [cm isEqual:@"intl"] || [cm isEqual:@"green-up"] ? @"intl" : @"cny";
    NSString *cb = str(@"changeBasis", nil) ?: @"prevClose";
    c.changeBasis = [cb isEqual:@"open"] || [cb isEqual:@"open_price"] ? @"open" : @"prevClose";
    NSString *lang = Trim((str(@"language", nil) ?: @"auto").lowercaseString);
    c.language = [@[@"auto", @"zh", @"en"] containsObject:lang] ? lang : @"auto";
    if ((n = dblVal(@"windowX", nil))) c.windowX = n.doubleValue;
    if ((n = dblVal(@"windowY", nil))) c.windowY = n.doubleValue;
    return c;
}

static void SaveConfig(Cfg *c) {
    NSDictionary *d = @{
        @"symbol": c.symbol, @"showOnDesktop": @(c.showOnDesktop), @"showMenuBarIcon": @(c.showMenuBarIcon),
        @"showChart": @(c.showChart), @"showDetails": @(c.showDetails), @"alwaysOnTop": @(c.alwaysOnTop),
        @"width": @(c.width), @"opacity": @(round(c.opacity * 100) / 100.0),
        @"refreshSeconds": @(MAX(MinRefresh(), c.refreshSeconds)), @"colorMode": c.colorMode,
        @"changeBasis": c.changeBasis, @"language": c.language,
        @"windowX": @(round(c.windowX * 10) / 10.0), @"windowY": @(round(c.windowY * 10) / 10.0),
    };
    AtomicWrite([NSJSONSerialization dataWithJSONObject:d options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil], ConfigURL());
}

static Cfg *LoadConfig(void) {
    NSURL *url = ConfigURL();
    if (![NSFileManager.defaultManager fileExistsAtPath:url.path]) {
        Cfg *def = [Cfg makeDefault];
        SaveConfig(def);
        return def;
    }
    NSData *data = [NSData dataWithContentsOfURL:url];
    NSDictionary *obj = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    return [obj isKindOfClass:NSDictionary.class] ? Sanitize(obj) : [Cfg makeDefault];
}

static void CleanupOldHistory(void) {
    NSInteger keep = [Lim()[@"historyKeepDays"] integerValue];
    NSCalendar *cal = NSCalendar.currentCalendar;
    NSDate *today = [cal startOfDayForDate:[NSDate date]];
    for (NSURL *f in [NSFileManager.defaultManager contentsOfDirectoryAtURL:AppDataDir() includingPropertiesForKeys:nil options:0 error:nil]) {
        NSString *name = f.lastPathComponent;
        if (![name hasPrefix:@"intraday-"] || ![name hasSuffix:@".json"]) continue;
        NSDate *fd = [DateFmt() dateFromString:[name substringWithRange:NSMakeRange(9, name.length - 14)]];
        if (!fd) continue;
        NSInteger days = [cal components:NSCalendarUnitDay fromDate:[cal startOfDayForDate:fd] toDate:today options:0].day;
        if (days > keep) [NSFileManager.defaultManager removeItemAtURL:f error:nil];
    }
}

static NSArray<Pt *> *ReadDay(NSURL *url, Basis **basisOut) {
    Basis *basis = [Basis dictionary];
    if (basisOut) *basisOut = basis;
    NSData *data = [NSData dataWithContentsOfURL:url];
    id json = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
    if (!json) return @[];

    NSString *name = url.lastPathComponent, *fileDate = Today(nil);
    if ([name hasPrefix:@"intraday-"] && [name hasSuffix:@".json"]) fileDate = [name substringWithRange:NSMakeRange(9, name.length - 14)];

    NSArray *raw = @[];
    if ([json isKindOfClass:NSDictionary.class]) {
        if ([json[@"points"] isKindOfClass:NSArray.class]) raw = json[@"points"];
        for (NSString *k in [json[@"basis"] isKindOfClass:NSDictionary.class] ? json[@"basis"] : @{}) {
            NSDictionary *v = json[@"basis"][k];
            double pc = [v[@"prev_close"] isKindOfClass:NSNumber.class] ? [v[@"prev_close"] doubleValue] : 0;
            double op = [v[@"open"] isKindOfClass:NSNumber.class] ? [v[@"open"] doubleValue] : 0;
            if (pc > 0) basis[k] = @[@(pc), @(op)];
        }
    } else if ([json isKindOfClass:NSArray.class]) raw = json;

    NSCalendar *cal = NSCalendar.currentCalendar;
    NSMutableArray<Pt *> *out = [NSMutableArray arrayWithCapacity:raw.count];
    for (NSDictionary *item in raw) {
        if (![item isKindOfClass:NSDictionary.class] || ![item[@"p"] isKindOfClass:NSNumber.class]) continue;
        double p = [item[@"p"] doubleValue];
        if (p <= 0) continue;
        NSString *s = NormSym([item[@"s"] isKindOfClass:NSString.class] ? item[@"s"] : @"");
        NSString *t = [item[@"t"] isKindOfClass:NSString.class] ? item[@"t"] : @"";
        int64_t ts = [item[@"ts"] isKindOfClass:NSNumber.class] ? [item[@"ts"] longLongValue] : 0;
        if (ts <= 0 && t.length) {
            NSArray *parts = Split(t, @":");
            NSInteger hh, mm;
            NSDate *day = [DateFmt() dateFromString:fileDate];
            NSDate *comb = parts.count >= 2 && ScanInt(parts[0], &hh) && ScanInt(parts[1], &mm) && day
                ? [cal dateBySettingHour:hh minute:mm second:0 ofDate:day options:0] : nil;
            if (comb) { ts = (int64_t)(comb.timeIntervalSince1970 * 1000.0); t = HMStr(hh, mm); }
        }
        if (ts > 0) [out addObject:[Pt ts:ts t:t p:p s:s]];
    }
    return out;
}

static void WriteDay(NSURL *url, NSArray<Pt *> *pts, Basis *basis) {
    NSMutableArray *arr = [NSMutableArray arrayWithCapacity:pts.count];
    for (Pt *p in pts) [arr addObject:@{@"ts": @(p.ts), @"t": p.t, @"p": @(R2(p.p)), @"s": p.s}];
    NSMutableDictionary *b = [NSMutableDictionary dictionary];
    for (NSString *k in basis) b[k] = @{@"prev_close": @(R2([basis[k][0] doubleValue])), @"open": @(R2([basis[k][1] doubleValue]))};
    AtomicWrite([NSJSONSerialization dataWithJSONObject:@{@"points": arr, @"basis": b} options:NSJSONWritingPrettyPrinted error:nil], url);
}

static NSArray<Pt *> *LoadTodayPoints(NSString *symbol) {
    @synchronized(gStorageLock) {
        NSString *want = NormSym(symbol);
        return [ReadDay(IntradayURL(nil), NULL) filteredArrayUsingPredicate:
                [NSPredicate predicateWithBlock:^BOOL(Pt *p, id _) { return [p.s isEqual:want] && p.p > 0 && p.ts > 0; }]];
    }
}

static void RecordPricePoint(double price, NSString *symbol) {
    if (price <= 0) return;
    @synchronized(gStorageLock) {
        NSDate *now = [NSDate date];
        int64_t ts = (int64_t)(now.timeIntervalSince1970 * 1000.0);
        NSURL *url = IntradayURL(Today(now));
        Basis *basis;
        NSMutableArray<Pt *> *pts = [ReadDay(url, &basis) mutableCopy];
        [pts addObject:[Pt ts:ts t:HM(now) p:R2(price) s:NormSym(symbol)]];
        [pts sortUsingComparator:^NSComparisonResult(Pt *a, Pt *b) { return a.ts < b.ts ? NSOrderedAscending : a.ts > b.ts ? NSOrderedDescending : NSOrderedSame; }];

        NSMutableArray<Pt *> *merged = [NSMutableArray arrayWithCapacity:pts.count];
        for (Pt *pt in pts) {
            NSString *ptMin = HMms(pt.ts);
            Pt *last = merged.lastObject;
            if (last && [last.s isEqual:pt.s] && [HMms(last.ts) isEqual:ptMin]) {
                merged[merged.count - 1] = [Pt ts:pt.ts t:pt.t.length ? pt.t : ptMin p:pt.p s:pt.s];
                continue;
            }
            [merged addObject:pt];
        }
        WriteDay(url, merged, basis);
    }
}

static void FreezeDayBasis(NSString *symbol, double prevClose, double openPrice) {
    if (prevClose <= 0) return;
    @synchronized(gStorageLock) {
        NSURL *url = IntradayURL(nil);
        Basis *basis;
        NSArray<Pt *> *pts = ReadDay(url, &basis);
        if ([basis[symbol][0] doubleValue] > 0) return;
        basis[symbol] = @[@(R2(prevClose)), @(R2(openPrice))];
        WriteDay(url, pts, basis);
    }
}

static Quote *ApplyFrozenBasis(Quote *quote) {
    if (quote.price <= 0) return quote;
    NSArray<NSNumber *> *b;
    @synchronized(gStorageLock) {
        Basis *basis;
        ReadDay(IntradayURL(nil), &basis);
        b = basis[quote.symbol];
    }
    if ([b[0] doubleValue] <= 0) return quote;
    Quote *q = [quote clone];
    q.prevClose = [b[0] doubleValue];
    if ([b[1] doubleValue] > 0) q.openPrice = [b[1] doubleValue];
    q.change = R2(q.price - q.prevClose);
    q.changePct = q.prevClose > 0 ? R2(q.change / q.prevClose * 100.0) : 0.0;
    return q;
}

static void ClearIntradayCache(void) {
    @synchronized(gStorageLock) { [NSFileManager.defaultManager removeItemAtURL:IntradayURL(nil) error:nil]; }
}

#pragma mark - Pricing engine (multi-source + cooldown + spreads)

@interface Pack : NSObject
@property (nonatomic) double price, prev, open, high, low, change, pct;
@property (nonatomic, copy) NSString *tm;
@end
@implementation Pack
+ (instancetype)price:(double)price prev:(double)prev open:(double)open high:(double)high low:(double)low tm:(NSString *)tm {
    Pack *k = [Pack new];
    k.price = R2(price);
    k.prev = R2(prev);
    if (k.prev <= 0) k.prev = R2(open > 0 ? open : price);
    k.open = R2(open); k.high = R2(high); k.low = R2(low);
    k.change = R2(k.price - k.prev);
    k.pct = k.prev > 0 ? R2(k.change / k.prev * 100.0) : 0.0;
    k.tm = tm.length ? tm : @"--:--";
    return k;
}
@end

static NSString *DecodeGB(NSData *d) {
    NSStringEncoding enc = CFStringConvertEncodingToNSStringEncoding(kCFStringEncodingGB_18030_2000);
    return [[NSString alloc] initWithData:d encoding:enc] ?: [[NSString alloc] initWithData:d encoding:NSUTF8StringEncoding] ?: @"";
}

@interface Engine : NSObject
+ (instancetype)shared;
- (Quote *)cached:(NSString *)sym;
- (NSDictionary<NSString *, Quote *> *)sampleAll;
@end

@implementation Engine {
    NSLock *_lock;
    NSMutableDictionary<NSString *, NSArray *> *_failures;   // sid -> [fails, until]
    NSMutableDictionary<NSString *, Quote *> *_cache;
    NSURLSession *_session;
}
+ (instancetype)shared { static Engine *e; static dispatch_once_t o; dispatch_once(&o, ^{ e = [Engine new]; }); return e; }
- (instancetype)init {
    if (!(self = [super init])) return nil;
    _lock = [NSLock new]; _failures = [NSMutableDictionary dictionary]; _cache = [NSMutableDictionary dictionary];
    NSURLSessionConfiguration *cfg = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    cfg.timeoutIntervalForRequest = 5;
    cfg.timeoutIntervalForResource = 6;
    _session = [NSURLSession sessionWithConfiguration:cfg];
    return self;
}
- (Quote *)cached:(NSString *)sym { [_lock lock]; Quote *q = _cache[sym]; [_lock unlock]; return q; }

- (BOOL)isCoolingDown:(NSString *)sid {
    [_lock lock]; NSArray *r = _failures[sid]; [_lock unlock];
    return r && [NSDate.date compare:r[1]] == NSOrderedAscending;
}
- (void)fail:(NSString *)sid {
    [_lock lock];
    NSArray *cur = _failures[sid];
    NSInteger fails = [cur[0] integerValue] + 1;
    NSDate *until = fails >= [Lim()[@"maxFailuresBeforeCooldown"] integerValue]
        ? [NSDate dateWithTimeIntervalSinceNow:[Lim()[@"coolDownSeconds"] doubleValue]] : (cur[1] ?: NSDate.distantPast);
    _failures[sid] = @[@(fails), until];
    [_lock unlock];
}
- (void)ok:(NSString *)sid { [_lock lock]; [_failures removeObjectForKey:sid]; [_lock unlock]; }

- (Quote *)build:(NSString *)symbol pack:(Pack *)pk sid:(NSString *)sid sname:(NSString *)sname fx:(double)fx usd:(double)usd {
    NSDictionary *meta = Meta(symbol);
    double sp = [meta[@"spread"] doubleValue];
    double p = pk.price, prev = pk.prev, op = pk.open, h = pk.high, l = pk.low, chg = pk.change, pct = pk.pct;
    BOOL est = [meta[@"is_estimated"] boolValue];
    if (sp > 0) {
        p = R2(p + sp); prev = R2(prev + sp); op = R2(op + sp); h = R2(h + sp); l = R2(l + sp);
        chg = R2(p - prev);
        pct = prev > 0 ? R2(chg / prev * 100.0) : 0.0;
        sname = [sname stringByAppendingString:@" (点差估算)"];
        est = YES;
    }
    Quote *q = [Quote new];
    q.symbol = symbol; q.price = p; q.prevClose = prev; q.openPrice = op; q.high = h; q.low = l; q.change = chg; q.changePct = pct;
    q.timeStr = pk.tm; q.sourceId = sid; q.sourceName = sname; q.isEstimated = est; q.fxRate = fx; q.usdPrice = usd;
    [_lock lock]; _cache[symbol] = q; [_lock unlock];
    return q;
}

- (NSData *)get:(NSString *)urlStr referer:(NSString *)referer {
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:urlStr]];
    [req setValue:UA forHTTPHeaderField:@"User-Agent"];
    if (referer) [req setValue:referer forHTTPHeaderField:@"Referer"];
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block NSData *out;
    [[_session dataTaskWithRequest:req completionHandler:^(NSData *d, NSURLResponse *r, NSError *e) {
        NSInteger code = [(NSHTTPURLResponse *)r statusCode];
        if (!e && code >= 200 && code <= 299 && d.length) out = d;
        dispatch_semaphore_signal(sem);
    }] resume];
    dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, 7 * NSEC_PER_SEC));
    return out;
}

- (Pack *)fetchTangdouz {
    NSData *raw = [self get:Spec()[@"endpoints"][@"tangdouzUrl"] referer:nil];
    if (!raw) return nil;
    NSString *text = [[NSString alloc] initWithData:raw encoding:NSUTF8StringEncoding] ?: DecodeGB(raw);
    NSMutableDictionary<NSString *, NSString *> *lines = [NSMutableDictionary dictionary];
    NSCharacterSet *ws = NSCharacterSet.whitespaceCharacterSet;
    for (NSString *line in [text componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        NSRange r = [line rangeOfString:@":"];
        if (r.location == NSNotFound) continue;
        lines[[[line substringToIndex:r.location] stringByTrimmingCharactersInSet:ws]] = [[line substringFromIndex:NSMaxRange(r)] stringByTrimmingCharactersInSet:ws];
    }
    NSCharacterSet *keep = [NSCharacterSet characterSetWithCharactersInString:@"0123456789.-"];
    double (^val)(NSString *) = ^double(NSString *k) {
        NSMutableString *f = [NSMutableString string];
        NSString *s = lines[k] ?: @"";
        for (NSUInteger i = 0; i < s.length; i++) if ([keep characterIsMember:[s characterAtIndex:i]]) [f appendFormat:@"%C", [s characterAtIndex:i]];
        return ParseDbl(f);
    };
    double price = val(@"最新价格");
    if (price <= 0) return nil;
    return [Pack price:price prev:val(@"前收盘价") open:val(@"开盘价") high:val(@"最高价") low:val(@"最低价") tm:ParseTime(lines[@"更新时间"] ?: @"")];
}

- (NSDictionary<NSString *, NSArray<NSString *> *> *)sinaList:(NSString *)codes {
    NSDictionary *ep = Spec()[@"endpoints"];
    NSData *raw = [self get:[ep[@"sinaHqUrl"] stringByAppendingString:codes] referer:ep[@"sinaReferer"]];
    if (!raw) return nil;
    NSMutableDictionary *out = [NSMutableDictionary dictionary];
    NSCharacterSet *tail = [NSCharacterSet characterSetWithCharactersInString:@";\" \r"];
    for (NSString *line in [DecodeGB(raw) componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet]) {
        NSRange r1 = [line rangeOfString:@"hq_str_"], r2 = [line rangeOfString:@"=\""];
        if (r1.location == NSNotFound || r2.location == NSNotFound || r2.location < NSMaxRange(r1)) continue;
        NSString *key = Trim([line substringWithRange:NSMakeRange(NSMaxRange(r1), r2.location - NSMaxRange(r1))]);
        NSString *body = [line substringFromIndex:NSMaxRange(r2)];
        while (body.length && [tail characterIsMember:[body characterAtIndex:body.length - 1]]) body = [body substringToIndex:body.length - 1];
        out[key] = [body componentsSeparatedByString:@","];
    }
    return out;
}

- (Pack *)fetchSinaAu9999 {
    NSArray<NSString *> *d = [self sinaList:@"SGE_AU9999"][@"SGE_AU9999"];
    if (d.count < 10 || ParseDbl(d[3]) <= 0) return nil;
    return [Pack price:ParseDbl(d[3]) prev:ParseDbl(d[5]) open:ParseDbl(d[9]) high:ParseDbl(d[7]) low:ParseDbl(d[8]) tm:d.count > 16 ? ParseTime(d[16]) : @"--:--"];
}
- (Pack *)fetchSinaAutd {
    NSArray<NSString *> *d = [self sinaList:@"gds_AUTD"][@"gds_AUTD"];
    if (d.count < 9 || ParseDbl(d[0]) <= 0) return nil;
    return [Pack price:ParseDbl(d[0]) prev:ParseDbl(d[7]) open:ParseDbl(d[8]) high:ParseDbl(d[4]) low:ParseDbl(d[5]) tm:ParseTime(d[6])];
}
- (Pack *)fetchSinaXau:(double *)rawUsd rate:(double *)rate {
    NSDictionary *m = [self sinaList:@"hf_XAU,fx_susdcny"];
    NSArray<NSString *> *xau = m[@"hf_XAU"], *fx = m[@"fx_susdcny"];
    if (xau.count < 9 || fx.count < 2) return nil;
    *rate = ParseDbl(fx[1]); *rawUsd = ParseDbl(xau[0]);
    if (*rate <= 0 || *rawUsd <= 0) return nil;
    return [Pack price:*rawUsd prev:ParseDbl(xau[7]) open:ParseDbl(xau[8]) high:ParseDbl(xau[4]) low:ParseDbl(xau[5]) tm:ParseTime(xau[6])];
}

- (Pack *)benchmark:(NSString **)sid sname:(NSString **)sname {
    NSArray *sources = @[
        @[@"sina_au9999", @"上金所 Au99.99", ^Pack *{ return [self fetchSinaAu9999]; }],
        @[@"sina_autd", @"上金所 Au(T+D)", ^Pack *{ return [self fetchSinaAutd]; }],
        @[@"tangdouz", @"浙商积存金", ^Pack *{ return [self fetchTangdouz]; }],
    ];
    for (NSArray *s in sources) {
        if ([self isCoolingDown:s[0]]) continue;
        Pack *(^fn)(void) = s[2];
        Pack *p = fn();
        if (p) { [self ok:s[0]]; *sid = s[0]; *sname = s[1]; return p; }
        [self fail:s[0]];
    }
    Pack *p = [self fetchSinaAu9999];
    *sid = @"sina_au9999"; *sname = @"上金所 Au99.99";
    return p;
}

- (NSDictionary<NSString *, Quote *> *)sampleAll {
    NSMutableDictionary<NSString *, Quote *> *out = [NSMutableDictionary dictionary];
    double usd = 0, rate = 0;
    Pack *xp = [self fetchSinaXau:&usd rate:&rate];
    if (xp) {
        [self ok:@"sina_xau"];
        out[@"xau_usd"] = [self build:@"xau_usd" pack:xp sid:@"sina_xau" sname:@"伦敦金现货" fx:rate usd:usd];
    } else {
        [self fail:@"sina_xau"];
        if ([self cached:@"xau_usd"]) out[@"xau_usd"] = [self cached:@"xau_usd"];
    }

    if (![self isCoolingDown:@"tangdouz"]) {
        Pack *zp = [self fetchTangdouz];
        if (zp) {
            [self ok:@"tangdouz"];
            out[@"zs_jcj"] = [self build:@"zs_jcj" pack:zp sid:@"tangdouz" sname:@"浙商银行直连" fx:0 usd:0];
        } else [self fail:@"tangdouz"];
    }
    if (!out[@"zs_jcj"] && [self cached:@"zs_jcj"]) out[@"zs_jcj"] = [self cached:@"zs_jcj"];

    NSString *sid, *sname;
    Pack *bp = [self benchmark:&sid sname:&sname];
    for (NSString *sym in @[@"au9999", @"icbc_jcj", @"ccb_jcj"]) {
        if (bp) out[sym] = [self build:sym pack:bp sid:sid sname:sname fx:0 usd:0];
        else if ([self cached:sym]) out[sym] = [self cached:sym];
    }
    if (bp && !out[@"zs_jcj"]) out[@"zs_jcj"] = [self build:@"zs_jcj" pack:bp sid:sid sname:sname fx:0 usd:0];

    for (NSString *sym in [Spec()[@"symbols"] valueForKey:@"id"])
        if (!out[sym] && [self cached:sym]) out[sym] = [self cached:sym];
    return out;
}
@end

#pragma mark - Card view

@class AppController;
@interface AppController : NSObject <NSApplicationDelegate, NSMenuDelegate>
@property (nonatomic, strong) Cfg *config;
@property (nonatomic, strong) Quote *currentQuote;
@property (nonatomic, strong) NSWindow *window;
@property (nonatomic, strong) NSStatusItem *statusItem;
- (NSMenu *)buildMenu;
- (void)setupUI;
- (void)startPolling;
- (void)applyAllConfig;
- (NSAlert *)makeAlert:(NSString *)titleKey body:(NSString *)body;
@end

static NSColor *White(CGFloat a) { return [NSColor colorWithSRGBRed:1 green:1 blue:1 alpha:a]; }
static NSColor *UpColor(void) { return [NSColor colorWithSRGBRed:0.96 green:0.28 blue:0.28 alpha:1]; }
static NSColor *DownColor(void) { return [NSColor colorWithSRGBRed:0.18 green:0.80 blue:0.44 alpha:1]; }

static void DrawText(NSString *s, CGFloat x, CGFloat top, CGFloat w, CGFloat h, CGFloat size, NSColor *color, BOOL bold, BOOL mono, NSTextAlignment align) {
    NSFont *font = mono ? [NSFont monospacedDigitSystemFontOfSize:size weight:bold ? NSFontWeightBold : NSFontWeightMedium]
                        : [NSFont systemFontOfSize:size weight:bold ? NSFontWeightBold : NSFontWeightRegular];
    CGFloat measured = [s sizeWithAttributes:@{NSFontAttributeName: font}].width;
    if (measured > w && measured > 0) font = [NSFont fontWithDescriptor:font.fontDescriptor size:size * w / measured] ?: font;
    // Allow descenders (e.g. English "CNY/g") — never clip below glyph bounds.
    CGFloat lineH = MAX(h, ceil(font.ascender - font.descender + 2.0));
    NSMutableParagraphStyle *ps = [NSMutableParagraphStyle new];
    ps.alignment = align;
    ps.lineBreakMode = NSLineBreakByTruncatingTail;
    [s drawInRect:NSMakeRect(x, top, w, lineH) withAttributes:@{NSFontAttributeName: font, NSForegroundColorAttributeName: color, NSParagraphStyleAttributeName: ps}];
}

static void StrokeDash(CGFloat x1, CGFloat x2, CGFloat y, CGFloat on, CGFloat off, CGFloat lw, CGFloat alpha) {
    NSBezierPath *p = [NSBezierPath bezierPath];
    [p moveToPoint:NSMakePoint(x1, y)];
    [p lineToPoint:NSMakePoint(x2, y)];
    CGFloat pat[2] = {on, off};
    [p setLineDash:pat count:2 phase:0];
    p.lineWidth = lw;
    [White(alpha) setStroke];
    [p stroke];
}

static void DrawChart(NSArray<Pt *> *samples, CGFloat x, CGFloat y, CGFloat w, CGFloat h, NSColor *tone, double basis) {
    if (samples.count < 2) { StrokeDash(x, x + w, y + h / 2.0, 4, 4, 1.0, 0.15); return; }
    double lo = DBL_MAX, hi = -DBL_MAX;
    for (Pt *p in samples) { lo = MIN(lo, p.p); hi = MAX(hi, p.p); }
    if (basis > 0) { lo = MIN(lo, basis); hi = MAX(hi, basis); }
    if (fabs(hi - lo) < 1e-5) { lo -= 1.0; hi += 1.0; }
    double inset = MAX((hi - lo) * 0.12, 0.05);
    lo -= inset; hi += inset;
    double span = MAX(hi - lo, 0.001);
    NSUInteger n = samples.count;
    CGFloat stepX = w / (CGFloat)(n - 1);
    CGFloat (^py)(double) = ^CGFloat(double v) { return y + h - (CGFloat)((v - lo) / span) * h; };

    if (basis > 0 && lo < basis && basis < hi) StrokeDash(x, x + w, py(basis), 2, 3, 0.8, 0.22);

    NSBezierPath *line = [NSBezierPath bezierPath], *fill = [NSBezierPath bezierPath];
    NSPoint first = NSZeroPoint, last = NSZeroPoint;
    for (NSUInteger i = 0; i < n; i++) {
        NSPoint pt = NSMakePoint(x + i * stepX, py(samples[i].p));
        if (i == 0) { first = pt; [line moveToPoint:pt]; [fill moveToPoint:pt]; }
        else { [line lineToPoint:pt]; [fill lineToPoint:pt]; }
        last = pt;
    }
    [fill lineToPoint:NSMakePoint(last.x, y + h)];
    [fill lineToPoint:NSMakePoint(first.x, y + h)];
    [fill closePath];
    [[[NSGradient alloc] initWithStartingColor:[tone colorWithAlphaComponent:0.22] endingColor:[tone colorWithAlphaComponent:0.02]] drawInBezierPath:fill angle:90];

    line.lineWidth = 1.5;
    line.lineJoinStyle = NSLineJoinStyleRound;
    line.lineCapStyle = NSLineCapStyleRound;
    [tone setStroke];
    [line stroke];
    [tone setFill];
    [[NSBezierPath bezierPathWithOvalInRect:NSMakeRect(last.x - 2, last.y - 2, 4, 4)] fill];
}

@interface CardView : NSView
@property (nonatomic, weak) AppController *controller;
@end

@implementation CardView {
    NSPoint _dragMouse, _dragOrigin;
    BOOL _dragging;
}
- (BOOL)isFlipped { return YES; }

- (void)mouseDown:(NSEvent *)e {
    _dragMouse = NSEvent.mouseLocation;
    _dragOrigin = self.window.frame.origin;
    _dragging = YES;
}
- (void)mouseDragged:(NSEvent *)e {
    if (!_dragging) return;
    NSPoint cur = NSEvent.mouseLocation;
    [self.window setFrameOrigin:NSMakePoint(_dragOrigin.x + cur.x - _dragMouse.x, _dragOrigin.y + cur.y - _dragMouse.y)];
}
- (void)mouseUp:(NSEvent *)e {
    Cfg *c = _controller.config;
    c.windowX = self.window.frame.origin.x;
    c.windowY = self.window.frame.origin.y;
    SaveConfig(c);
    _dragging = NO;
}
- (void)rightMouseDown:(NSEvent *)e { [NSMenu popUpContextMenu:[_controller buildMenu] withEvent:e forView:self]; }

- (void)drawRect:(NSRect)dirty {
    Cfg *cfg = _controller.config;
    CGFloat W = self.bounds.size.width, H = self.bounds.size.height, pad = 14;

    NSBezierPath *bg = [NSBezierPath bezierPathWithRoundedRect:NSMakeRect(0.5, 0.5, W - 1, H - 1) xRadius:12 yRadius:12];
    [[NSColor colorWithSRGBRed:0.08 green:0.11 blue:0.16 alpha:cfg.opacity] setFill];
    [bg fill];
    [White(0.12) setStroke];
    bg.lineWidth = 1.0;
    [bg stroke];

    BOOL isEn = [Lang(cfg.language) isEqual:@"en"];
    Quote *q = _controller.currentQuote;
    if (q.price <= 0) {
        DrawText(T(q.error ? @"fetch_error" : @"refreshing", cfg.language), pad, H / 2 - 8, W - pad * 2, 16, 10.5, White(0.62), NO, NO, NSTextAlignmentCenter);
        return;
    }

    BOOL useOpen = [cfg.changeBasis isEqual:@"open"] && q.openPrice > 0;
    double basis = useOpen ? q.openPrice : q.prevClose;
    double change = basis > 0 ? q.price - basis : q.change;
    double pct = basis > 0 ? change / basis * 100.0 : q.changePct;
    BOOL up = change >= 0;
    NSColor *tone = [cfg.colorMode isEqual:@"cny"] ? (up ? UpColor() : DownColor()) : (up ? DownColor() : UpColor());

    CGFloat top = 9;
    NSDictionary *meta = Meta(q.symbol);
    NSString *name = isEn ? meta[@"card_en"] : [meta[@"name_cn"] stringByAppendingString:q.isEstimated ? @" (点差估算)" : @""];
    DrawText([NSString stringWithFormat:@"%@ · %@", name, isEn ? meta[@"unit_en"] : meta[@"unit_cn"]], pad, top, W - pad * 2, 16, 11.0, White(0.70), NO, NO, NSTextAlignmentLeft);
    top += 17;

    DrawText([NSString stringWithFormat:@"%.2f", q.price], pad - 1, top, W - pad * 2 + 2, 34, W >= 200 ? 28.0 : 26.0, tone, YES, YES, NSTextAlignmentLeft);
    top += 34;

    NSString *sign = up ? @"+" : @"";
    DrawText([NSString stringWithFormat:@"%@%.2f  (%@%.2f%%)", sign, change, sign, pct], pad, top, W - pad * 2, 14, 12.0, [tone colorWithAlphaComponent:0.95], NO, YES, NSTextAlignmentLeft);
    top += 16;

    if (cfg.showDetails) {
        NSString *bTag = isEn ? (useOpen ? @"Open" : @"Prev") : (useOpen ? @"今开" : @"昨收");
        DrawText([NSString stringWithFormat:@"%@ %.2f  %@ %.2f  %@ %.2f", isEn ? @"High" : @"高", q.high, isEn ? @"Low" : @"低", q.low, bTag, basis],
                 pad, top, W - pad * 2, 12, 10.0, White(0.50), NO, YES, NSTextAlignmentLeft);
        top += 16;
    }

    if (cfg.showChart) {
        NSArray<Pt *> *samples = LoadTodayPoints(q.symbol);
        DrawChart(samples, pad, top + 2, W - pad * 2, 44, tone, basis);
        top += 48;
        if (samples.count >= 2) {
            DrawText(HMms(samples.firstObject.ts), pad, top, 80, 11, 8.5, White(0.38), NO, YES, NSTextAlignmentLeft);
            DrawText(HMms(samples.lastObject.ts), W - pad - 80, top, 80, 11, 8.5, White(0.38), NO, YES, NSTextAlignmentRight);
        }
    }
}
@end

#pragma mark - App controller & menus

static NSMenuItem *Add(NSMenu *m, NSString *title, id target, SEL sel) {
    NSMenuItem *i = [[NSMenuItem alloc] initWithTitle:title action:sel keyEquivalent:@""];
    i.target = target;
    [m addItem:i];
    return i;
}
static NSMenu *AddSub(NSMenu *m, NSString *title) {
    NSMenu *sub = [NSMenu new];
    Add(m, title, nil, nil).submenu = sub;
    return sub;
}
static NSControlStateValue On(BOOL b) { return b ? NSControlStateValueOn : NSControlStateValueOff; }

@implementation AppController {
    CardView *_cardView;
    NSInteger _fetchGen;
    BOOL _isFetching;
    BOOL _updating;
    NSLock *_stateLock;
    dispatch_source_t _pollTimer;
}

- (instancetype)init {
    if (!(self = [super init])) return nil;
    _config = LoadConfig();
    _stateLock = [NSLock new];
    return self;
}

- (NSString *)txt:(NSString *)key { return T(key, _config.language); }

- (CGFloat)windowHeight {
    CGFloat h = 9 + 17 + 36 + 17; // header (descender-safe) + price + delta
    if (_config.showDetails) h += 16;
    if (_config.showChart) h += 2 + 44 + 12;
    return h + 12;
}

- (void)setupUI {
    CGFloat w = _config.width, h = [self windowHeight];
    _window = [[NSWindow alloc] initWithContentRect:NSMakeRect(100, 100, w, h) styleMask:NSWindowStyleMaskBorderless backing:NSBackingStoreBuffered defer:NO];
    _window.releasedWhenClosed = NO;
    _window.opaque = NO;
    _window.backgroundColor = NSColor.clearColor;
    _window.movableByWindowBackground = NO;
    _window.hasShadow = YES;
    _window.collectionBehavior = NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary | NSWindowCollectionBehaviorStationary;

    _cardView = [[CardView alloc] initWithFrame:NSMakeRect(0, 0, w, h)];
    _cardView.controller = self;
    _window.contentView = _cardView;

    _statusItem = [NSStatusBar.systemStatusBar statusItemWithLength:NSVariableStatusItemLength];
    _statusItem.menu = [self buildMenu];

    [self positionWindowDefault];
    [self applyAllConfig];
}

- (void)startPolling {
    CleanupOldHistory();
    [self triggerFetchNow:YES];
    [self rescheduleTimer];
}

- (void)rescheduleTimer {
    if (_pollTimer) dispatch_source_cancel(_pollTimer);
    uint64_t sec = MAX(MinRefresh(), _config.refreshSeconds);
    dispatch_source_t t = dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER, 0, 0, dispatch_get_global_queue(QOS_CLASS_UTILITY, 0));
    dispatch_source_set_timer(t, dispatch_time(DISPATCH_TIME_NOW, sec * NSEC_PER_SEC), sec * NSEC_PER_SEC, 0);
    __weak AppController *w = self;
    dispatch_source_set_event_handler(t, ^{ [w triggerFetchNow:NO]; });
    dispatch_resume(t);
    _pollTimer = t;
}

- (void)positionWindowDefault {
    CGFloat w = _config.width, h = [self windowHeight];
    NSRect sf = NSScreen.mainScreen ? NSScreen.mainScreen.visibleFrame : NSMakeRect(0, 0, 1440, 900);
    BOOL reset = _config.windowX < 0 || _config.windowY < 0;
    CGFloat nx = reset ? sf.origin.x + sf.size.width - w - 24 : _config.windowX;
    CGFloat ny = reset ? sf.origin.y + sf.size.height - h - 24 : _config.windowY;
    [_window setFrame:NSMakeRect(nx, ny, w, h) display:YES];
}

- (void)updateWindowSize {
    CGFloat w = _config.width, h = [self windowHeight];
    NSPoint o = _window.frame.origin;
    [_window setFrame:NSMakeRect(o.x, o.y, w, h) display:YES];
    _cardView.frame = NSMakeRect(0, 0, w, h);
    _cardView.needsDisplay = YES;
}

- (void)applyWindowLevel { _window.level = _config.alwaysOnTop ? NSFloatingWindowLevel : NSNormalWindowLevel; }

- (void)applyDisplayVisibility {
    if (_config.showOnDesktop) [_window orderFront:nil]; else [_window orderOut:nil];
    _statusItem.visible = _config.showMenuBarIcon;
}

- (void)updateStatusBar {
    NSStatusBarButton *b = _statusItem.button;
    NSString *prefix = [Lang(_config.language) isEqual:@"zh"] ? @"金" : @"Au";
    Quote *q = _currentQuote;
    if (q.price <= 0) { b.title = [prefix stringByAppendingString:@" --"]; return; }
    double base = [_config.changeBasis isEqual:@"open"] && q.openPrice > 0 ? q.openPrice : q.prevClose;
    double pct = base > 0 ? (q.price - base) / base * 100.0 : 0.0;
    b.title = [NSString stringWithFormat:@"%@ %.2f %+.2f%%", prefix, q.price, pct];
}

- (void)applyAllConfig {
    [self updateWindowSize];
    [self applyWindowLevel];
    [self applyDisplayVisibility];
    [self updateStatusBar];
}

- (void)triggerFetchNow:(BOOL)force {
    [_stateLock lock];
    if (_isFetching && !force) { [_stateLock unlock]; return; }
    NSInteger gen = ++_fetchGen;
    NSString *sym = _config.symbol;
    _isFetching = YES;
    [_stateLock unlock];

    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        [self fetchGen:gen symbol:sym];
        [self->_stateLock lock];
        if (self->_fetchGen == gen) self->_isFetching = NO;
        [self->_stateLock unlock];
    });
}

- (void)fetchGen:(NSInteger)gen symbol:(NSString *)sym {
    NSDictionary<NSString *, Quote *> *quotes = [Engine.shared sampleAll];
    [_stateLock lock]; NSInteger cur = _fetchGen; [_stateLock unlock];
    if (gen != cur) return;

    [quotes enumerateKeysAndObjectsUsingBlock:^(NSString *s, Quote *q, BOOL *stop) {
        if (q.price <= 0 || q.error) return;
        FreezeDayBasis(s, q.prevClose, q.openPrice);
        RecordPricePoint(q.price, s);
    }];
    Quote *picked = quotes[sym] ?: [Engine.shared cached:sym];
    if (picked.price > 0) picked = ApplyFrozenBasis(picked);
    dispatch_async(dispatch_get_main_queue(), ^{
        if (gen != self->_fetchGen || ![sym isEqual:self->_config.symbol]) return;
        if (picked) self.currentQuote = picked;
        else if (!self.currentQuote) {
            Quote *q = [Quote new];
            q.symbol = sym; q.timeStr = @"--:--"; q.sourceId = @"none"; q.sourceName = @""; q.error = @"unavailable";
            self.currentQuote = q;
        }
        self->_cardView.needsDisplay = YES;
        [self updateStatusBar];
    });
}

#pragma mark Menu

- (void)menuNeedsUpdate:(NSMenu *)menu { [menu removeAllItems]; [self populateMenu:menu]; }

- (NSMenu *)buildMenu {
    NSMenu *m = [NSMenu new];
    m.autoenablesItems = NO;
    m.delegate = self;
    [self populateMenu:m];
    return m;
}

- (void)populateMenu:(NSMenu *)menu {
    BOOL zh = [Lang(_config.language) isEqual:@"zh"];
    NSDictionary *spec = Spec();
    Quote *q = _currentQuote;

    NSString *head = [self txt:@"refreshing"];
    if (q.price > 0) {
        NSDictionary *meta = Meta(q.symbol);
        double base = [_config.changeBasis isEqual:@"open"] && q.openPrice > 0 ? q.openPrice : q.prevClose;
        double pct = base > 0 ? (q.price - base) / base * 100.0 : q.changePct;
        head = [NSString stringWithFormat:@"%@ %.2f (%+.2f%%)", zh ? meta[@"name_cn"] : meta[@"name_en"], q.price, pct];
    }
    Add(menu, head, self, @selector(onForceRefresh:));
    [menu addItem:NSMenuItem.separatorItem];

    NSMenuItem *i = Add(menu, [self txt:@"showOnDesktop"], self, @selector(onToggleDesktop:));
    i.state = On(_config.showOnDesktop); i.enabled = _config.showMenuBarIcon;
    i = Add(menu, [self txt:@"showMenuBar"], self, @selector(onToggleMenuBar:));
    i.state = On(_config.showMenuBarIcon); i.enabled = _config.showOnDesktop;
    Add(menu, [self txt:@"alwaysOnTop"], self, @selector(onToggleTop:)).state = On(_config.alwaysOnTop);
    [menu addItem:NSMenuItem.separatorItem];

    Add(menu, [self txt:@"showChart"], self, @selector(onToggleChart:)).state = On(_config.showChart);
    Add(menu, [self txt:@"showDetails"], self, @selector(onToggleDetails:)).state = On(_config.showDetails);

    NSMenu *sub = AddSub(menu, [self txt:@"cardWidth"]);
    for (NSNumber *w in spec[@"options"][@"macWidths"]) {
        i = Add(sub, [NSString stringWithFormat:@"%@ pt", w], self, @selector(onSelectWidth:));
        i.tag = w.integerValue; i.state = On(_config.width == w.integerValue);
    }

    sub = AddSub(menu, [self txt:@"cardOpacity"]);
    for (NSNumber *op in spec[@"options"][@"opacities"]) {
        NSInteger pctTag = (NSInteger)round(op.doubleValue * 100);
        i = Add(sub, [NSString stringWithFormat:@"%ld%%", (long)pctTag], self, @selector(onSelectOpacity:));
        i.tag = pctTag; i.state = On(fabs(_config.opacity - op.doubleValue) < 0.03);
    }

    Add(menu, [self txt:@"resetPos"], self, @selector(onResetPos:));
    [menu addItem:NSMenuItem.separatorItem];

    sub = AddSub(menu, [self txt:@"symbols"]);
    for (NSDictionary *meta in spec[@"symbols"]) {
        if ([meta[@"id"] isEqual:@"xau_usd"]) [sub addItem:NSMenuItem.separatorItem];
        NSString *title = zh ? meta[@"name_cn"] : meta[@"name_en"];
        if ([meta[@"is_estimated"] boolValue]) title = [NSString stringWithFormat:@"%@ %@", title, [self txt:@"estTag"]];
        i = Add(sub, title, self, @selector(onSelectSymbol:));
        i.representedObject = meta[@"id"]; i.state = On([_config.symbol isEqual:meta[@"id"]]);
    }

    sub = AddSub(menu, [self txt:@"changeBasis"]);
    for (NSArray *p in @[@[@"prevClose", @"prevClose"], @[@"open", @"openPrice"]]) {
        i = Add(sub, [self txt:p[1]], self, @selector(onSelectBasis:));
        i.representedObject = p[0]; i.state = On([_config.changeBasis isEqual:p[0]]);
    }

    sub = AddSub(menu, [self txt:@"colorMode"]);
    for (NSArray *p in @[@[@"cny", @"cnyColors"], @[@"intl", @"intlColors"]]) {
        i = Add(sub, [self txt:p[1]], self, @selector(onSelectColor:));
        i.representedObject = p[0]; i.state = On([_config.colorMode isEqual:p[0]]);
    }

    sub = AddSub(menu, [self txt:@"menu_language"]);
    for (NSString *c in @[@"auto", @"zh", @"en"]) {
        i = Add(sub, [self txt:[@"menu_lang_" stringByAppendingString:c]], self, @selector(onSelectLanguage:));
        i.representedObject = c; i.state = On([_config.language isEqual:c]);
    }

    sub = AddSub(menu, [self txt:@"refreshInterval"]);
    for (NSNumber *sec in spec[@"options"][@"refreshIntervals"]) {
        NSString *label = [NSString stringWithFormat:@"%@ %@", sec, [self txt:@"seconds"]];
        if (sec.integerValue == 10) label = [label stringByAppendingFormat:@" (%@)", [self txt:@"recommend"]];
        i = Add(sub, label, self, @selector(onSelectRefresh:));
        i.tag = sec.integerValue; i.state = On(_config.refreshSeconds == sec.integerValue);
    }
    [menu addItem:NSMenuItem.separatorItem];

    sub = AddSub(menu, [self txt:@"advanced"]);
    Add(sub, [self txt:@"openConfigFolder"], self, @selector(onOpenFolder:));
    Add(sub, [self txt:@"reloadConfig"], self, @selector(onReloadConfig:));
    Add(sub, [self txt:@"clearCache"], self, @selector(onClearCache:));

    sub = AddSub(menu, [self txt:@"aboutMenu"]);
    Add(sub, [self txt:@"aboutApp"], self, @selector(onAbout:));
    Add(sub, [self txt:@"checkUpdate"], self, @selector(onCheckUpdate:));
    Add(sub, [self txt:@"viewDisclaimer"], self, @selector(onDisclaimer:));
    Add(sub, [self txt:@"visitGithub"], self, @selector(onGithub:));

    [menu addItem:NSMenuItem.separatorItem];
    Add(menu, [self txt:@"quitApp"], self, @selector(onQuit:)).keyEquivalent = @"q";
}

#pragma mark Actions

- (void)onForceRefresh:(id)s { [self triggerFetchNow:YES]; }
- (void)onToggleDesktop:(id)s { _config.showOnDesktop = !_config.showOnDesktop; SaveConfig(_config); [self applyDisplayVisibility]; }
- (void)onToggleMenuBar:(id)s { _config.showMenuBarIcon = !_config.showMenuBarIcon; SaveConfig(_config); [self applyDisplayVisibility]; }
- (void)onToggleTop:(id)s { _config.alwaysOnTop = !_config.alwaysOnTop; SaveConfig(_config); [self applyWindowLevel]; }
- (void)onToggleChart:(id)s { _config.showChart = !_config.showChart; SaveConfig(_config); [self updateWindowSize]; }
- (void)onToggleDetails:(id)s { _config.showDetails = !_config.showDetails; SaveConfig(_config); [self updateWindowSize]; }
- (void)onSelectWidth:(NSMenuItem *)s { _config.width = s.tag; SaveConfig(_config); [self updateWindowSize]; }
- (void)onSelectOpacity:(NSMenuItem *)s { _config.opacity = s.tag / 100.0; SaveConfig(_config); _cardView.needsDisplay = YES; }
- (void)onResetPos:(id)s { _config.windowX = -1; _config.windowY = -1; SaveConfig(_config); [self positionWindowDefault]; }

- (void)onSelectSymbol:(NSMenuItem *)s {
    NSString *sym = s.representedObject;
    _config.symbol = sym;
    SaveConfig(_config);
    Quote *cached = [Engine.shared cached:sym];
    if (cached.price > 0) {
        _currentQuote = ApplyFrozenBasis(cached);
    } else {
        NSArray<Pt *> *pts = LoadTodayPoints(sym);
        if (pts.count) {
            double hi = -DBL_MAX, lo = DBL_MAX;
            for (Pt *p in pts) { hi = MAX(hi, p.p); lo = MIN(lo, p.p); }
            NSDictionary *meta = Meta(sym);
            Quote *stub = [Quote new];
            stub.symbol = sym; stub.price = pts.lastObject.p; stub.prevClose = stub.price; stub.openPrice = stub.price;
            stub.high = hi; stub.low = lo; stub.timeStr = pts.lastObject.t; stub.sourceId = @"cache";
            stub.sourceName = meta[@"name_cn"]; stub.isEstimated = [meta[@"is_estimated"] boolValue];
            _currentQuote = ApplyFrozenBasis(stub);
        }
    }
    [self applyAllConfig];
    [self triggerFetchNow:YES];
}

- (void)onSelectBasis:(NSMenuItem *)s { _config.changeBasis = s.representedObject; SaveConfig(_config); _cardView.needsDisplay = YES; [self updateStatusBar]; }
- (void)onSelectColor:(NSMenuItem *)s { _config.colorMode = s.representedObject; SaveConfig(_config); _cardView.needsDisplay = YES; }
- (void)onSelectLanguage:(NSMenuItem *)s { _config.language = s.representedObject; SaveConfig(_config); [self applyAllConfig]; }
- (void)onSelectRefresh:(NSMenuItem *)s { _config.refreshSeconds = MAX(MinRefresh(), s.tag); SaveConfig(_config); [self rescheduleTimer]; }
- (void)onOpenFolder:(id)s { [NSWorkspace.sharedWorkspace openURL:AppDataDir()]; }
- (void)onReloadConfig:(id)s { _config = LoadConfig(); [self applyAllConfig]; [self rescheduleTimer]; }
- (void)onClearCache:(id)s { ClearIntradayCache(); _cardView.needsDisplay = YES; }

- (NSAlert *)makeAlert:(NSString *)titleKey body:(NSString *)body {
    NSAlert *a = [NSAlert new];
    a.icon = NSApplication.sharedApplication.applicationIconImage;
    a.messageText = [self txt:titleKey];
    a.informativeText = body;
    [a addButtonWithTitle:[self txt:@"ok"]];
    return a;
}

- (void)onAbout:(id)s {
    NSDictionary *prod = Spec()[@"product"];
    NSString *body = TR(@"about_body", _config.language, @{@"version": prod[@"version"], @"copyright": prod[@"copyright"]});
    [NSApp activateIgnoringOtherApps:YES];
    [[self makeAlert:@"about_title" body:body] runModal];
}

- (void)onDisclaimer:(id)s {
    NSDictionary *d = Spec()[@"disclaimers"];
    [NSApp activateIgnoringOtherApps:YES];
    [[self makeAlert:@"disclaimer_title" body:d[Lang(_config.language)] ?: d[@"zh"] ?: @""] runModal];
}

- (void)onGithub:(id)s { [NSWorkspace.sharedWorkspace openURL:[NSURL URLWithString:Spec()[@"product"][@"githubUrl"]]]; }
- (void)onQuit:(id)s { [NSApplication.sharedApplication terminate:nil]; }

#pragma mark Auto-update

static NSDictionary *FetchLatestRelease(NSError **outErr);
static NSString *DownloadURL(NSString *urlStr, NSString *filename, NSError **outErr);
static NSString *ApplyMacUpdate(NSString *dmgPath);
static NSString *ShellQuote(NSString *s);

static NSInteger VerPart(NSString *s, NSUInteger i) {
    NSArray<NSString *> *p = [s componentsSeparatedByString:@"."];
    return i < p.count ? p[i].integerValue : 0;
}
static NSComparisonResult CmpVer(NSString *a, NSString *b) {
    NSString *aa = [a hasPrefix:@"v"] || [a hasPrefix:@"V"] ? [a substringFromIndex:1] : a;
    NSString *bb = [b hasPrefix:@"v"] || [b hasPrefix:@"V"] ? [b substringFromIndex:1] : b;
    for (NSUInteger i = 0; i < 3; i++) {
        NSInteger x = VerPart(aa, i), y = VerPart(bb, i);
        if (x < y) return NSOrderedAscending;
        if (x > y) return NSOrderedDescending;
    }
    return NSOrderedSame;
}

- (void)onCheckUpdate:(id)s {
    if (_updating) return;
    _updating = YES;
    [NSApp activateIgnoringOtherApps:YES];
    if (!_window.isVisible) [_window orderFront:nil];

    // Immediate feedback sheet (formal releases only; drafts ignored by /releases/latest).
    NSAlert *busy = [NSAlert new];
    busy.messageText = [self txt:@"checkingUpdate"];
    busy.informativeText = [self txt:@"checkingUpdateHint"];
    [busy beginSheetModalForWindow:_window completionHandler:^(__unused NSModalResponse r) {}];

    __weak AppController *wself = self;
    NSWindow *host = _window;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSError *err = nil;
        NSDictionary *rel = FetchLatestRelease(&err);
        dispatch_async(dispatch_get_main_queue(), ^{
            AppController *me = wself;
            if (!me) return;
            if (host.attachedSheet) [host endSheet:host.attachedSheet];

            NSString *local = Spec()[@"product"][@"version"];
            if (err || !rel) {
                me->_updating = NO;
                NSString *body;
                if (err.code == 404 && [err.domain isEqual:@"GoldTicker"])
                    body = TR(@"noPublishedRelease", me.config.language, @{@"version": local});
                else
                    body = [me txt:@"updateNetworkError"];
                NSAlert *a = [me makeAlert:@"checkUpdate" body:body];
                [a addButtonWithTitle:[me txt:@"openReleasesPage"]];
                // makeAlert already added OK as first button; openReleases as second.
                if ([a runModal] == NSAlertSecondButtonReturn) {
                    NSString *url = [Spec()[@"product"][@"githubUrl"] stringByAppendingString:@"/releases"];
                    [NSWorkspace.sharedWorkspace openURL:[NSURL URLWithString:url]];
                }
                return;
            }
            // Defense: ignore draft / prerelease payloads if API ever returns them.
            if ([rel[@"draft"] boolValue] || [rel[@"prerelease"] boolValue]) {
                me->_updating = NO;
                [[me makeAlert:@"checkUpdate" body:TR(@"noPublishedRelease", me.config.language, @{@"version": local})] runModal];
                return;
            }
            NSString *remote = rel[@"tag_name"] ?: rel[@"name"] ?: @"";
            if (CmpVer(remote, local) != NSOrderedDescending) {
                me->_updating = NO;
                [[me makeAlert:@"checkUpdate" body:TR(@"upToDate", me.config.language, @{@"version": local})] runModal];
                return;
            }
            NSAlert *ask = [NSAlert new];
            ask.messageText = [me txt:@"checkUpdate"];
            ask.informativeText = TR(@"updateAvailable", me.config.language, @{@"version": remote, @"current": local});
            [ask addButtonWithTitle:[me txt:@"updateDownload"]];
            [ask addButtonWithTitle:[me txt:@"updateLater"]];
            if ([ask runModal] != NSAlertFirstButtonReturn) { me->_updating = NO; return; }
            [me installUpdateFromRelease:rel];
        });
    });
}

static NSDictionary *FetchLatestRelease(NSError **outErr) {
    NSString *api = Spec()[@"product"][@"releasesApi"];
    if (!api.length) api = [Spec()[@"product"][@"githubUrl"] stringByAppendingString:@"/releases/latest"];
    // Only /releases/latest — published formal releases; drafts/prereleases excluded by GitHub.
    if (![api containsString:@"api.github.com"]) {
        NSString *gh = Spec()[@"product"][@"githubUrl"];
        NSString *path = [[NSURL URLWithString:gh] path];
        api = [NSString stringWithFormat:@"https://api.github.com/repos%@/releases/latest", path ?: @""];
    }
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:api]];
    [req setValue:UA forHTTPHeaderField:@"User-Agent"];
    [req setValue:@"application/vnd.github+json" forHTTPHeaderField:@"Accept"];
    req.timeoutInterval = 10;
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block NSData *data = nil;
    __block NSError *err = nil;
    [[NSURLSession.sharedSession dataTaskWithRequest:req completionHandler:^(NSData *d, NSURLResponse *r, NSError *e) {
        data = d; err = e;
        if (!e && [r isKindOfClass:NSHTTPURLResponse.class]) {
            NSInteger code = ((NSHTTPURLResponse *)r).statusCode;
            if (code < 200 || code >= 300)
                err = [NSError errorWithDomain:@"GoldTicker" code:code userInfo:@{NSLocalizedDescriptionKey: [NSString stringWithFormat:@"HTTP %ld", (long)code]}];
        }
        dispatch_semaphore_signal(sem);
    }] resume];
    if (dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, 12 * NSEC_PER_SEC)) != 0) {
        if (outErr) *outErr = [NSError errorWithDomain:@"GoldTicker" code:-1 userInfo:@{NSLocalizedDescriptionKey: @"timeout"}];
        return nil;
    }
    if (err) { if (outErr) *outErr = err; return nil; }
    if (!data.length) { if (outErr) *outErr = [NSError errorWithDomain:@"GoldTicker" code:1 userInfo:@{NSLocalizedDescriptionKey: @"empty"}]; return nil; }
    id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:&err];
    if (outErr) *outErr = err;
    return [obj isKindOfClass:NSDictionary.class] ? obj : nil;
}

- (void)installUpdateFromRelease:(NSDictionary *)rel {
    NSString *hint = Spec()[@"product"][@"macAssetHint"] ?: @"macOS-Universal2.dmg";
    NSString *urlStr = nil;
    for (NSDictionary *a in rel[@"assets"] ?: @[]) {
        NSString *name = a[@"name"] ?: @"";
        if ([name.lowercaseString containsString:hint.lowercaseString] || [name.lowercaseString hasSuffix:@".dmg"]) {
            urlStr = a[@"browser_download_url"];
            if ([name.lowercaseString containsString:hint.lowercaseString]) break;
        }
    }
    if (!urlStr.length) {
        _updating = NO;
        [[self makeAlert:@"checkUpdate" body:[self txt:@"updateNoAsset"]] runModal];
        return;
    }
    if (!_window.isVisible) [_window orderFront:nil];
    NSAlert *busy = [NSAlert new];
    busy.messageText = [self txt:@"updating"];
    busy.informativeText = [self txt:@"checkingUpdateHint"];
    [busy beginSheetModalForWindow:_window completionHandler:^(__unused NSModalResponse r) {}];
    __weak AppController *wself = self;
    NSWindow *host = _window;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSError *err = nil;
        NSString *dmg = DownloadURL(urlStr, @"GoldTicker-update.dmg", &err);
        dispatch_async(dispatch_get_main_queue(), ^{
            AppController *me = wself;
            if (!me) return;
            if (host.attachedSheet) [host endSheet:host.attachedSheet];
            if (err || !dmg) {
                me->_updating = NO;
                [[me makeAlert:@"checkUpdate" body:[me txt:@"updateNetworkError"]] runModal];
                return;
            }
            NSString *fail = ApplyMacUpdate(dmg);
            if (fail) {
                me->_updating = NO;
                [[me makeAlert:@"checkUpdate" body:TR(@"updateFailed", me.config.language, @{@"error": fail})] runModal];
                return;
            }
        });
    });
}

static NSString *DownloadURL(NSString *urlStr, NSString *filename, NSError **outErr) {
    NSString *tmp = [NSTemporaryDirectory() stringByAppendingPathComponent:filename];
    [[NSFileManager defaultManager] removeItemAtPath:tmp error:nil];
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:urlStr]];
    [req setValue:UA forHTTPHeaderField:@"User-Agent"];
    req.timeoutInterval = 120;
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block NSError *err = nil;
    __block NSURL *loc = nil;
    [[[NSURLSession sharedSession] downloadTaskWithRequest:req completionHandler:^(NSURL *location, NSURLResponse *response, NSError *e) {
        err = e;
        if (!e && location) {
            [[NSFileManager defaultManager] removeItemAtPath:tmp error:nil];
            [[NSFileManager defaultManager] moveItemAtURL:location toURL:[NSURL fileURLWithPath:tmp] error:&err];
            loc = [NSURL fileURLWithPath:tmp];
        }
        dispatch_semaphore_signal(sem);
    }] resume];
    dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, 180 * NSEC_PER_SEC));
    if (outErr) *outErr = err;
    return (!err && loc) ? tmp : nil;
}

static NSString *ShellQuote(NSString *s) {
    return [NSString stringWithFormat:@"'%@'", [s stringByReplacingOccurrencesOfString:@"'" withString:@"'\"'\"'"]];
}

/// Mount DMG, replace running .app, relaunch. Returns error string or nil on success (process will exit).
static NSString *ApplyMacUpdate(NSString *dmgPath) {
    NSString *appPath = NSBundle.mainBundle.bundlePath;
    if (![appPath.pathExtension.lowercaseString isEqual:@"app"]) {
        [NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:dmgPath]];
        return nil;
    }
    NSString *mount = [NSTemporaryDirectory() stringByAppendingPathComponent:[NSString stringWithFormat:@"gt-mnt-%@", NSUUID.UUID.UUIDString]];
    [[NSFileManager defaultManager] createDirectoryAtPath:mount withIntermediateDirectories:YES attributes:nil error:nil];
    NSTask *attach = [NSTask new];
    attach.launchPath = @"/usr/bin/hdiutil";
    attach.arguments = @[@"attach", dmgPath, @"-nobrowse", @"-readonly", @"-mountpoint", mount];
    attach.standardOutput = [NSPipe pipe];
    attach.standardError = [NSPipe pipe];
    [attach launch]; [attach waitUntilExit];
    if (attach.terminationStatus != 0) return @"hdiutil attach failed";

    NSString *srcApp = nil;
    for (NSString *name in [[NSFileManager defaultManager] contentsOfDirectoryAtPath:mount error:nil]) {
        if ([name.pathExtension.lowercaseString isEqual:@"app"]) { srcApp = [mount stringByAppendingPathComponent:name]; break; }
    }
    if (!srcApp) {
        NSTask *detach = [NSTask new];
        detach.launchPath = @"/usr/bin/hdiutil";
        detach.arguments = @[@"detach", mount, @"-quiet"];
        [detach launch]; [detach waitUntilExit];
        return @"no .app in DMG";
    }

    NSString *script = [NSString stringWithFormat:
        @"#!/bin/bash\n"
        @"set -e\n"
        @"SRC=%@\n"
        @"DST=%@\n"
        @"MNT=%@\n"
        @"STAGE=\"${TMPDIR:-/tmp}/GoldTicker-update-stage.app\"\n"
        @"sleep 1\n"
        @"rm -rf \"$STAGE\"\n"
        @"ditto \"$SRC\" \"$STAGE\"\n"
        @"hdiutil detach \"$MNT\" -quiet || true\n"
        @"rm -rf \"$DST\"\n"
        @"ditto \"$STAGE\" \"$DST\"\n"
        @"rm -rf \"$STAGE\"\n"
        @"xattr -dr com.apple.quarantine \"$DST\" 2>/dev/null || true\n"
        @"open \"$DST\"\n"
        @"rm -f \"$0\"\n",
        ShellQuote(srcApp), ShellQuote(appPath), ShellQuote(mount)];

    NSString *helper = [NSTemporaryDirectory() stringByAppendingPathComponent:@"goldticker-apply-update.sh"];
    [script writeToFile:helper atomically:YES encoding:NSUTF8StringEncoding error:nil];
    [[NSFileManager defaultManager] setAttributes:@{NSFilePosixPermissions: @0755} ofItemAtPath:helper error:nil];
    NSTask *run = [NSTask new];
    run.launchPath = @"/bin/bash";
    run.arguments = @[helper];
    [run launch];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        [NSApp terminate:nil];
    });
    return nil;
}
@end

#pragma mark - Entry & isolated smoke test

static AppController *gController;   // NSApplication.delegate is weak

static void SmokeCheck(BOOL ok, NSString *msg) {
    if (ok) return;
    fprintf(stderr, "smoke-test failed: %s\n", msg.UTF8String);
    exit(1);
}

static void SetAppIcon(void) {
    NSURL *u = [NSBundle.mainBundle URLForResource:@"AppIcon" withExtension:@"icns"];
    NSImage *img = u ? [[NSImage alloc] initWithContentsOfURL:u] : nil;
    if (img) NSApplication.sharedApplication.applicationIconImage = img;
}

static void RunSmokeTest(void) {
    NSString *tmp = [NSTemporaryDirectory() stringByAppendingPathComponent:[@"goldticker-mac-smoke-" stringByAppendingString:NSUUID.UUID.UUIDString]];
    [NSFileManager.defaultManager createDirectoryAtPath:tmp withIntermediateDirectories:YES attributes:nil error:nil];
    setenv("GOLDTICKER_DATA_DIR", tmp.UTF8String, 1);
    (void)NSApplication.sharedApplication;
    SetAppIcon();
    AppController *ctrl = [AppController new];
    [ctrl setupUI];
    for (NSArray *lp in @[@[@"zh", @"金"], @[@"en", @"Au"]]) {
        ctrl.config.language = lp[0];
        [ctrl applyAllConfig];
        [ctrl.window display];
        SmokeCheck([ctrl.statusItem.button.title isEqual:[lp[1] stringByAppendingString:@" --"]], @"Status bar title mismatch");
        NSAlert *a = [ctrl makeAlert:@"about_title" body:Spec()[@"product"][@"version"]];
        SmokeCheck([a.buttons.firstObject.title isEqual:[lp[0] isEqual:@"zh"] ? @"确定" : @"OK"], @"Alert button mismatch");
    }
    [ctrl.window orderOut:nil];
    [NSStatusBar.systemStatusBar removeStatusItem:ctrl.statusItem];

    NSDictionary *payload = @{@"smoke": @"passed", @"platform": @"darwin-objc-universal2", @"version": Spec()[@"product"][@"version"], @"data_isolated": @YES};
    printf("%s\n", [[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:payload options:0 error:nil] encoding:NSUTF8StringEncoding].UTF8String);
    [NSFileManager.defaultManager removeItemAtPath:tmp error:nil];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        gStorageLock = [NSObject new];
        if ([NSProcessInfo.processInfo.arguments containsObject:@"--smoke-test"]) { RunSmokeTest(); return 0; }
        NSApplication *app = NSApplication.sharedApplication;
        SetAppIcon();
        app.activationPolicy = NSApplicationActivationPolicyAccessory;
        gController = [AppController new];
        app.delegate = gController;
        [gController setupUI];
        [gController startPolling];
        [app run];
    }
    return 0;
}
