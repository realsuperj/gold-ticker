using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Shapes;
using System.Windows.Threading;
using GoldTicker.Wpf.Core;

namespace GoldTicker.Wpf;

public partial class MainWindow : Window
{
    private static readonly Color UpColor = Color.FromRgb(245, 71, 71);
    private static readonly Color DownColor = Color.FromRgb(46, 204, 113);

    private readonly PricingEngine _engine = new PricingEngine();
    private readonly DispatcherTimer _timer = new DispatcherTimer();
    private readonly bool _smokeMode;

    private AppConfig _config;
    private QuoteData _currentQuote;
    private List<IntradayPoint> _samples = new List<IntradayPoint>();
    private int _fetchGen;
    private bool _isFetching;
    private bool _initialPlaced;
    private bool _updating;

    public MainWindow(bool smokeMode = false)
    {
        _smokeMode = smokeMode;
        InitializeComponent();

        GoldStorage.CleanupOldHistory(3);
        _config = GoldStorage.LoadConfig();

        ApplyWindowConfig();
        RebuildContextMenu();
        RenderCard();

        Loaded += (_, _) =>
        {
            ApplyInitialPosition();
            if (!_smokeMode)
            {
                _timer.Interval = TimeSpan.FromSeconds(Math.Max(GoldConstants.MinRefreshSeconds, _config.RefreshSeconds));
                _timer.Tick += (_, _) => TriggerFetchNow();
                _timer.Start();
                TriggerFetchNow(force: true);
            }
        };
    }

    public void ApplySmokeSample(AppConfig cfg, QuoteData quote)
    {
        _config = cfg;
        _currentQuote = GoldStorage.ApplyFrozenBasis(quote);
        _samples = GoldStorage.LoadTodayPoints(cfg.Symbol);
        ApplyWindowConfig();
        RebuildContextMenu();
        RenderCard();
    }

    public void BringToVisibleFront()
    {
        EnsureInsideWorkArea(resetToCorner: false);
        Show();
        Activate();
    }

    private void ApplyInitialPosition()
    {
        if (_initialPlaced) return;
        _initialPlaced = true;

        UpdateLayout();
        if (_config.WindowX >= 0 && _config.WindowY >= 0)
        {
            Left = _config.WindowX;
            Top = _config.WindowY;
            EnsureInsideWorkArea(resetToCorner: false);
        }
        else
        {
            EnsureInsideWorkArea(resetToCorner: true);
        }
    }

    private void EnsureInsideWorkArea(bool resetToCorner)
    {
        var work = SystemParameters.WorkArea;
        var winW = ActualWidth > 20 ? ActualWidth : (_config.Width + 16);
        var winH = ActualHeight > 20 ? ActualHeight : 160;

        if (resetToCorner
            || double.IsNaN(Left) || double.IsNaN(Top)
            || Left + winW < work.Left + 24
            || Left > work.Right - 24
            || Top + winH < work.Top + 24
            || Top > work.Bottom - 24)
        {
            Left = work.Right - winW - 20;
            Top = work.Top + 20;
            _config.WindowX = Left;
            _config.WindowY = Top;
            GoldStorage.SaveConfig(_config);
        }
    }

    private void ApplyWindowConfig()
    {
        Topmost = _config.AlwaysOnTop;
        CardBorder.Width = _config.Width;
        var alpha = (byte)Math.Round(Math.Max(0.60, Math.Min(1.0, _config.Opacity)) * 255.0);
        CardBorder.Background = new SolidColorBrush(Color.FromArgb(alpha, 20, 28, 41));

        double emptyH = 42;
        if (_config.ShowDetails) emptyH += 12;
        if (_config.ShowChart) emptyH += 36;
        EmptyPanel.MinHeight = emptyH;

        _timer.Interval = TimeSpan.FromSeconds(Math.Max(GoldConstants.MinRefreshSeconds, _config.RefreshSeconds));
    }

    private void TriggerFetchNow(bool force = false)
    {
        if (_isFetching && !force) return;
        var gen = Interlocked.Increment(ref _fetchGen);
        _isFetching = true;
        _ = FetchAllAsync(gen);
    }

    private async Task FetchAllAsync(int gen)
    {
        try
        {
            var quotes = await _engine.SampleAllQuotesAsync();
            if (gen != _fetchGen) return;

            foreach (var kv in quotes)
            {
                var q = kv.Value;
                if (q != null && q.Price > 0 && string.IsNullOrEmpty(q.Error))
                {
                    GoldStorage.FreezeDayBasis(kv.Key, q.PrevClose, q.OpenPrice);
                    GoldStorage.RecordPricePoint(q.Price, kv.Key);
                }
            }

            await Dispatcher.InvokeAsync(() =>
            {
                if (gen != _fetchGen) return;
                var sym = _config.Symbol;
                if (quotes.TryGetValue(sym, out var picked) && picked != null)
                {
                    _currentQuote = GoldStorage.ApplyFrozenBasis(picked);
                }
                else if (_currentQuote == null || _currentQuote.Symbol != sym)
                {
                    _currentQuote = new QuoteData
                    {
                        Symbol = sym,
                        Error = GoldI18n.T("fetch_error", _config.Language),
                    };
                }
                _samples = GoldStorage.LoadTodayPoints(sym);
                RenderCard();
            });
        }
        catch (Exception ex)
        {
            await Dispatcher.InvokeAsync(() =>
            {
                if (gen != _fetchGen) return;
                if (_currentQuote == null)
                    _currentQuote = new QuoteData { Symbol = _config.Symbol, Error = ex.Message };
                RenderCard();
            });
        }
        finally
        {
            if (gen == _fetchGen) _isFetching = false;
        }
    }

    private (double change, double pct, double basis, bool isOpenBasis) ComputeDelta(QuoteData q)
    {
        bool openMode = _config.ChangeBasis == "open" && q.OpenPrice > 0;
        double basis = openMode ? q.OpenPrice : q.PrevClose;
        if (basis <= 0) basis = q.OpenPrice > 0 ? q.OpenPrice : q.Price;
        double change = Math.Round(q.Price - basis, 2);
        double pct = basis > 0 ? Math.Round(change / basis * 100.0, 2) : 0.0;
        return (change, pct, basis, openMode);
    }

    private Color GetToneColor(bool up)
    {
        bool cny = _config.ColorMode != "intl";
        if (cny) return up ? UpColor : DownColor;
        return up ? DownColor : UpColor;
    }

    private void RenderCard()
    {
        var lang = GoldI18n.ResolveLanguage(_config.Language);
        bool isEn = lang == "en";
        var q = _currentQuote;

        if (q == null || q.Price <= 0)
        {
            QuotePanel.Visibility = Visibility.Collapsed;
            EmptyPanel.Visibility = Visibility.Visible;
            bool hasErr = q != null && !string.IsNullOrEmpty(q.Error);
            EmptyTitleText.Text = GoldI18n.T(hasErr ? "fetch_error" : "refreshing", _config.Language);
            if (hasErr)
            {
                EmptySubText.Text = GoldConstants.Meta.TryGetValue(_config.Symbol, out var m0)
                    ? (isEn ? m0.CardEn : m0.NameCn)
                    : "";
                EmptySubText.Visibility = Visibility.Visible;
            }
            else
            {
                EmptySubText.Visibility = Visibility.Collapsed;
            }
            return;
        }

        EmptyPanel.Visibility = Visibility.Collapsed;
        QuotePanel.Visibility = Visibility.Visible;

        var meta = GoldConstants.Meta.TryGetValue(q.Symbol, out var m) ? m : GoldConstants.Meta[GoldConstants.SymbolAu9999];
        string dispName, dispUnit;
        if (isEn)
        {
            dispName = meta.CardEn;
            dispUnit = meta.UnitEn;
        }
        else
        {
            dispName = meta.NameCn + (q.IsEstimated ? " " + GoldI18n.T("estSpreadCn", "zh") : "");
            dispUnit = meta.UnitCn;
        }
        HeaderText.Text = $"{dispName} · {dispUnit}";

        var (change, pct, basis, isOpenBasis) = ComputeDelta(q);
        bool up = change >= 0;
        var tone = GetToneColor(up);
        var toneBrush = new SolidColorBrush(tone);
        toneBrush.Freeze();

        PriceText.FontSize = _config.Width >= 168 ? 22.0 : (_config.Width >= 136 ? 20.0 : 18.0);
        PriceText.Text = q.Price.ToString("0.00", CultureInfo.InvariantCulture);
        PriceText.Foreground = toneBrush;

        string sign = up ? "+" : "";
        var deltaBrush = new SolidColorBrush(Color.FromArgb(242, tone.R, tone.G, tone.B));
        deltaBrush.Freeze();
        DeltaText.Text = string.Format(CultureInfo.InvariantCulture, "{0}{1:0.00}  ({0}{2:0.00}%)", sign, change, pct);
        DeltaText.Foreground = deltaBrush;

        if (_config.ShowDetails)
        {
            DetailsBox.Visibility = Visibility.Visible;
            string hTag = isEn ? "High" : "高";
            string lTag = isEn ? "Low" : "低";
            string bTag = isEn ? (isOpenBasis ? "Open" : "Prev") : (isOpenBasis ? "今开" : "昨收");
            DetailsText.Text = string.Format(CultureInfo.InvariantCulture,
                "{0} {1:0.00}  {2} {3:0.00}  {4} {5:0.00}",
                hTag, q.High, lTag, q.Low, bTag, basis);
        }
        else
        {
            DetailsBox.Visibility = Visibility.Collapsed;
        }

        if (_config.ShowChart)
        {
            ChartPanel.Visibility = Visibility.Visible;
            DrawChart(tone, basis);
        }
        else
        {
            ChartPanel.Visibility = Visibility.Collapsed;
        }
    }

    private void DrawChart(Color tone, double basis)
    {
        ChartCanvas.Children.Clear();
        double w = Math.Max(96, _config.Width - 16.0);
        double h = 28.0;
        ChartCanvas.Width = w;
        ChartCanvas.Height = h;

        var valid = _samples.Where(s => s.P > 0 && s.Ts > 0).ToList();
        if (valid.Count < 2)
        {
            var midLine = new Line
            {
                X1 = 0, Y1 = h / 2.0, X2 = w, Y2 = h / 2.0,
                Stroke = new SolidColorBrush(Color.FromArgb(38, 255, 255, 255)),
                StrokeThickness = 1.0,
                StrokeDashArray = new DoubleCollection { 4, 4 },
            };
            ChartCanvas.Children.Add(midLine);
            StartTimeText.Text = "";
            EndTimeText.Text = "";
            TimeAxisRow.Visibility = Visibility.Collapsed;
            return;
        }

        TimeAxisRow.Visibility = Visibility.Visible;
        StartTimeText.Text = DateTimeOffset.FromUnixTimeMilliseconds(valid[0].Ts).LocalDateTime.ToString("HH:mm", CultureInfo.InvariantCulture);
        EndTimeText.Text = DateTimeOffset.FromUnixTimeMilliseconds(valid[valid.Count - 1].Ts).LocalDateTime.ToString("HH:mm", CultureInfo.InvariantCulture);

        double lo = valid.Min(p => p.P);
        double hi = valid.Max(p => p.P);
        if (basis > 0)
        {
            if (basis < lo) lo = basis;
            if (basis > hi) hi = basis;
        }
        if (Math.Abs(hi - lo) < 1e-5)
        {
            lo -= 1.0;
            hi += 1.0;
        }
        double inset = Math.Max((hi - lo) * 0.12, 0.05);
        lo -= inset;
        hi += inset;
        double span = Math.Max(hi - lo, 0.001);
        double stepX = w / (valid.Count - 1.0);

        double Py(double v) => h - (v - lo) / span * h;

        if (basis > 0 && lo < basis && basis < hi)
        {
            double by = Py(basis);
            var baseLine = new Line
            {
                X1 = 0, Y1 = by, X2 = w, Y2 = by,
                Stroke = new SolidColorBrush(Color.FromArgb(56, 255, 255, 255)),
                StrokeThickness = 0.85,
                StrokeDashArray = new DoubleCollection { 2, 3 },
            };
            ChartCanvas.Children.Add(baseLine);
        }

        var pts = new Point[valid.Count];
        for (int i = 0; i < valid.Count; i++)
            pts[i] = new Point(i * stepX, Py(valid[i].P));

        var fillGeo = new StreamGeometry();
        using (var ctx = fillGeo.Open())
        {
            ctx.BeginFigure(pts[0], isFilled: true, isClosed: true);
            for (int i = 1; i < pts.Length; i++)
                ctx.LineTo(pts[i], isStroked: false, isSmoothJoin: false);
            ctx.LineTo(new Point(pts[pts.Length - 1].X, h), isStroked: false, isSmoothJoin: false);
            ctx.LineTo(new Point(pts[0].X, h), isStroked: false, isSmoothJoin: false);
        }
        fillGeo.Freeze();

        var grad = new LinearGradientBrush(
            Color.FromArgb(56, tone.R, tone.G, tone.B),
            Color.FromArgb(5, tone.R, tone.G, tone.B),
            new Point(0, 0),
            new Point(0, 1));
        grad.Freeze();
        ChartCanvas.Children.Add(new Path { Data = fillGeo, Fill = grad });

        var lineGeo = new StreamGeometry();
        using (var ctx = lineGeo.Open())
        {
            ctx.BeginFigure(pts[0], isFilled: false, isClosed: false);
            for (int i = 1; i < pts.Length; i++)
                ctx.LineTo(pts[i], isStroked: true, isSmoothJoin: true);
        }
        lineGeo.Freeze();

        var strokeBrush = new SolidColorBrush(tone);
        strokeBrush.Freeze();
        ChartCanvas.Children.Add(new Path
        {
            Data = lineGeo,
            Stroke = strokeBrush,
            StrokeThickness = 1.5,
            StrokeLineJoin = PenLineJoin.Round,
            StrokeStartLineCap = PenLineCap.Round,
            StrokeEndLineCap = PenLineCap.Round,
        });

        var lastPt = pts[pts.Length - 1];
        var dot = new Ellipse { Width = 4.4, Height = 4.4, Fill = strokeBrush };
        Canvas.SetLeft(dot, lastPt.X - 2.2);
        Canvas.SetTop(dot, lastPt.Y - 2.2);
        ChartCanvas.Children.Add(dot);
    }

    private void CardBorder_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState != MouseButtonState.Pressed) return;
        try { DragMove(); } catch (InvalidOperationException) { return; }
        _config.WindowX = Left;
        _config.WindowY = Top;
        GoldStorage.SaveConfig(_config);
    }

    private void CardMenu_Opened(object sender, RoutedEventArgs e) => RebuildContextMenu();

    private string Txt(string key) => GoldI18n.T(key, _config.Language);

    private void RebuildContextMenu()
    {
        CardMenu.Items.Clear();
        var lang = GoldI18n.ResolveLanguage(_config.Language);

        string headerTitle;
        if (_currentQuote != null && _currentQuote.Price > 0)
        {
            var meta = GoldConstants.Meta[_currentQuote.Symbol];
            var sname = lang == "zh" ? meta.NameCn : meta.NameEn;
            var (_, pct, _, _) = ComputeDelta(_currentQuote);
            var sign = pct >= 0 ? "+" : "";
            headerTitle = string.Format(CultureInfo.InvariantCulture, "{0} {1:0.00} ({2}{3:0.00}%)", sname, _currentQuote.Price, sign, pct);
        }
        else
        {
            headerTitle = Txt("refreshing");
        }
        CardMenu.Items.Add(MakeAction(headerTitle, () => TriggerFetchNow(force: true)));
        CardMenu.Items.Add(new Separator());

        CardMenu.Items.Add(MakeCheck(Txt("alwaysOnTop"), _config.AlwaysOnTop, () => UpdateCfg(c => c.AlwaysOnTop = !c.AlwaysOnTop)));
        CardMenu.Items.Add(MakeCheck(Txt("showChart"), _config.ShowChart, () => UpdateCfg(c => c.ShowChart = !c.ShowChart)));
        CardMenu.Items.Add(MakeCheck(Txt("showDetails"), _config.ShowDetails, () => UpdateCfg(c => c.ShowDetails = !c.ShowDetails)));

        var widthSub = new MenuItem { Header = Txt("cardWidth") };
        foreach (var w in GoldConstants.ValidWidths)
        {
            int wVal = w;
            widthSub.Items.Add(MakeCheck($"{wVal} pt", _config.Width == wVal, () => UpdateCfg(c => c.Width = wVal)));
        }
        CardMenu.Items.Add(widthSub);

        var opSub = new MenuItem { Header = Txt("cardOpacity") };
        foreach (var op in GoldConstants.ValidOpacities)
        {
            double opVal = op;
            int pctLabel = (int)Math.Round(opVal * 100);
            opSub.Items.Add(MakeCheck($"{pctLabel}%", Math.Abs(_config.Opacity - opVal) < 0.03, () => UpdateCfg(c => c.Opacity = opVal)));
        }
        CardMenu.Items.Add(opSub);

        CardMenu.Items.Add(MakeAction(Txt("resetPos"), () => EnsureInsideWorkArea(resetToCorner: true)));
        CardMenu.Items.Add(new Separator());

        var symSub = new MenuItem { Header = Txt("symbols") };
        foreach (var symId in GoldConstants.SupportedSymbols)
        {
            var id = symId;
            if (id == GoldConstants.SymbolXauUsd)
                symSub.Items.Add(new Separator());
            var meta = GoldConstants.Meta[id];
            var title = lang == "zh" ? meta.NameCn : meta.NameEn;
            if (meta.IsEstimated) title += " " + Txt("estTag");
            symSub.Items.Add(MakeCheck(title, _config.Symbol == id, () => SelectSymbol(id)));
        }
        CardMenu.Items.Add(symSub);

        var basisSub = new MenuItem { Header = Txt("changeBasis") };
        basisSub.Items.Add(MakeCheck(Txt("prevClose"), _config.ChangeBasis == "prevClose", () => UpdateCfg(c => c.ChangeBasis = "prevClose")));
        basisSub.Items.Add(MakeCheck(Txt("openPrice"), _config.ChangeBasis == "open", () => UpdateCfg(c => c.ChangeBasis = "open")));
        CardMenu.Items.Add(basisSub);

        var colorSub = new MenuItem { Header = Txt("colorMode") };
        colorSub.Items.Add(MakeCheck(Txt("cnyColors"), _config.ColorMode == "cny", () => UpdateCfg(c => c.ColorMode = "cny")));
        colorSub.Items.Add(MakeCheck(Txt("intlColors"), _config.ColorMode == "intl", () => UpdateCfg(c => c.ColorMode = "intl")));
        CardMenu.Items.Add(colorSub);

        var langSub = new MenuItem { Header = Txt("menu_language") };
        foreach (var l in new[] { "auto", "zh", "en" })
        {
            var lv = l;
            langSub.Items.Add(MakeCheck(Txt("menu_lang_" + lv), _config.Language == lv, () => UpdateCfg(c => c.Language = lv)));
        }
        CardMenu.Items.Add(langSub);

        var refSub = new MenuItem { Header = Txt("refreshInterval") };
        foreach (var sec in GoldConstants.ValidRefreshIntervals)
        {
            int sVal = sec;
            var label = $"{sVal} {Txt("seconds")}" + (sVal == 10 ? $" ({Txt("recommend")})" : "");
            refSub.Items.Add(MakeCheck(label, _config.RefreshSeconds == sVal, () => UpdateCfg(c => c.RefreshSeconds = sVal)));
        }
        CardMenu.Items.Add(refSub);

        CardMenu.Items.Add(new Separator());

        var advSub = new MenuItem { Header = Txt("advanced") };
        advSub.Items.Add(MakeAction(Txt("openConfigFolder"), () =>
        {
            Process.Start(new ProcessStartInfo { FileName = GoldStorage.GetAppDataDir(), UseShellExecute = true });
        }));
        advSub.Items.Add(MakeAction(Txt("reloadConfig"), () =>
        {
            _config = GoldStorage.LoadConfig();
            ApplyWindowConfig();
            SelectSymbol(_config.Symbol);
        }));
        advSub.Items.Add(MakeAction(Txt("clearCache"), () =>
        {
            GoldStorage.ClearIntradayCache();
            _samples.Clear();
            TriggerFetchNow(force: true);
            RenderCard();
        }));
        CardMenu.Items.Add(advSub);

        var aboutSub = new MenuItem { Header = Txt("aboutMenu") };
        aboutSub.Items.Add(MakeAction(Txt("aboutApp"), ShowAboutDialog));
        aboutSub.Items.Add(MakeAction(Txt("checkUpdate"), () => _ = CheckForUpdateAsync()));
        aboutSub.Items.Add(MakeAction(Txt("viewDisclaimer"), ShowDisclaimerDialog));
        aboutSub.Items.Add(MakeAction(Txt("visitGithub"), () =>
        {
            Process.Start(new ProcessStartInfo { FileName = GoldConstants.GithubUrl, UseShellExecute = true });
        }));
        CardMenu.Items.Add(aboutSub);

        CardMenu.Items.Add(new Separator());
        CardMenu.Items.Add(MakeAction(Txt("quitApp"), () => Application.Current.Shutdown()));
    }

    private void SelectSymbol(string sym)
    {
        _config.Symbol = sym;
        GoldStorage.SaveConfig(_config);
        _samples = GoldStorage.LoadTodayPoints(sym);
        var cached = _engine.GetCachedQuote(sym);
        if (cached != null)
        {
            _currentQuote = GoldStorage.ApplyFrozenBasis(cached);
        }
        else if (_samples.Count > 0)
        {
            var last = _samples[_samples.Count - 1];
            var meta = GoldConstants.Meta[sym];
            var stub = new QuoteData
            {
                Symbol = sym,
                Price = last.P,
                PrevClose = last.P,
                OpenPrice = last.P,
                High = _samples.Max(p => p.P),
                Low = _samples.Min(p => p.P),
                TimeStr = last.T,
                SourceName = meta.NameCn,
                IsEstimated = meta.IsEstimated,
            };
            _currentQuote = GoldStorage.ApplyFrozenBasis(stub);
        }
        else
        {
            _currentQuote = null;
        }
        RenderCard();
        TriggerFetchNow(force: true);
    }

    private void UpdateCfg(Action<AppConfig> mutator)
    {
        mutator(_config);
        GoldStorage.SaveConfig(_config);
        ApplyWindowConfig();
        RenderCard();
    }

    private void ShowAboutDialog()
    {
        var body = Txt("about_body")
            .Replace("{version}", GoldConstants.Version)
            .Replace("{copyright}", GoldConstants.Copyright);
        var dlg = new InfoWindow(Txt("about_title"), body, Txt("ok")) { Owner = this };
        dlg.ShowDialog();
    }

    private void ShowDisclaimerDialog()
    {
        var lang = GoldI18n.ResolveLanguage(_config.Language);
        var body = lang == "en" ? GoldConstants.DisclaimerEn : GoldConstants.DisclaimerCn;
        var dlg = new InfoWindow(Txt("disclaimer_title"), body, Txt("ok"), alignLeft: true) { Owner = this };
        dlg.ShowDialog();
    }

    private async Task CheckForUpdateAsync()
    {
        if (_updating || _smokeMode) return;
        _updating = true;
        var wait = new InfoWindow(Txt("checkingUpdate"), Txt("checkingUpdateHint"), Txt("ok")) { Owner = this };
        wait.Show();
        try
        {
            var result = await UpdateChecker.FetchLatestAsync().ConfigureAwait(true);
            wait.Close();
            wait = null;

            if (result.Kind == UpdateChecker.CheckKind.NoPublishedRelease)
            {
                var body = Txt("noPublishedRelease").Replace("{version}", GoldConstants.Version);
                var choice = MessageBox.Show(body + "\n\n" + Txt("openReleasesPage") + "?", Txt("checkUpdate"),
                    MessageBoxButton.YesNo, MessageBoxImage.Information);
                if (choice == MessageBoxResult.Yes)
                    Process.Start(new ProcessStartInfo { FileName = GoldConstants.GithubUrl.TrimEnd('/') + "/releases", UseShellExecute = true });
                return;
            }
            if (result.Kind != UpdateChecker.CheckKind.Ok || result.Release == null)
            {
                MessageBox.Show(Txt("updateNetworkError"), Txt("checkUpdate"), MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var rel = result.Release;
            if (UpdateChecker.CompareVersion(rel.Tag, GoldConstants.Version) <= 0)
            {
                MessageBox.Show(Txt("upToDate").Replace("{version}", GoldConstants.Version), Txt("checkUpdate"), MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            var ask = MessageBox.Show(
                Txt("updateAvailable").Replace("{version}", rel.Tag).Replace("{current}", GoldConstants.Version),
                Txt("checkUpdate"),
                MessageBoxButton.YesNo,
                MessageBoxImage.Question);
            if (ask != MessageBoxResult.Yes) return;
            if (string.IsNullOrWhiteSpace(rel.DownloadUrl))
            {
                MessageBox.Show(Txt("updateNoAsset"), Txt("checkUpdate"), MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var downloading = new InfoWindow(Txt("updating"), Txt("checkingUpdateHint"), Txt("ok")) { Owner = this };
            downloading.Show();
            var tmp = Path.Combine(Path.GetTempPath(), "GoldTicker-update.exe");
            try
            {
                await UpdateChecker.DownloadToFileAsync(rel.DownloadUrl, tmp).ConfigureAwait(true);
            }
            catch
            {
                downloading.Close();
                MessageBox.Show(Txt("updateNetworkError"), Txt("checkUpdate"), MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            downloading.Close();

            var target = Process.GetCurrentProcess().MainModule?.FileName;
            if (string.IsNullOrEmpty(target) || !File.Exists(target))
            {
                MessageBox.Show(Txt("updateFailed").Replace("{error}", "cannot locate running exe"), Txt("checkUpdate"), MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }

            var bat = UpdateChecker.WriteApplyScript(tmp, target, Process.GetCurrentProcess().Id);
            Process.Start(new ProcessStartInfo
            {
                FileName = bat,
                UseShellExecute = true,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            });
            Application.Current.Shutdown();
        }
        finally
        {
            wait?.Close();
            _updating = false;
        }
    }

    private static MenuItem MakeAction(string title, Action onClick)
    {
        var item = new MenuItem { Header = title };
        item.Click += (_, _) => onClick();
        return item;
    }

    private static MenuItem MakeCheck(string title, bool isChecked, Action onClick)
    {
        var item = new MenuItem { Header = title, IsChecked = isChecked };
        item.Click += (_, _) => onClick();
        return item;
    }
}
