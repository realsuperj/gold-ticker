using System.Text.Json;
using GoldTicker.WinUI.Services;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Graphics;
using ShapePath = Microsoft.UI.Xaml.Shapes.Path;
using Windows.System;
using Windows.UI;
using WinRT.Interop;

namespace GoldTicker.WinUI;

public sealed partial class MainWindow : Window
{
    private readonly CoreIpcClient _ipc;
    private readonly DispatcherTimer _timer = new();
    private JsonElement _config;
    private JsonElement? _meta;
    private JsonElement? _quote;
    private List<(long ts, double p, string t)> _samples = new();
    private bool _dragging;
    private PointInt32 _dragStartScreen;
    private PointInt32 _windowStart;
    private string _unavailable = "行情暂不可用";
    private string _disclaimer = "";

    private static readonly Color Up = Color.FromArgb(255, 255, 87, 81);
    private static readonly Color Down = Color.FromArgb(255, 71, 222, 135);
    private static readonly Color Muted = Color.FromArgb(255, 157, 165, 180);

    public MainWindow()
    {
        InitializeComponent();

        _ipc = CoreIpcClient.Start();

        ExtendsContentIntoTitleBar = true;
        SystemBackdrop = new DesktopAcrylicBackdrop();

        var hwnd = WindowNative.GetWindowHandle(this);
        var id = Win32Interop.GetWindowIdFromWindow(hwnd);
        var appWindow = AppWindow.GetFromWindowId(id);
        if (appWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.IsResizable = false;
            presenter.IsMaximizable = false;
            presenter.IsMinimizable = false;
            presenter.SetBorderAndTitleBar(false, false);
            presenter.IsAlwaysOnTop = true;
        }
        appWindow.Resize(new SizeInt32(232, 220));

        Closed += (_, _) =>
        {
            _timer.Stop();
            _ipc.Dispose();
        };

        _timer.Tick += async (_, _) => await RefreshAsync();
        _ = BootstrapAsync();
    }

    private async Task BootstrapAsync()
    {
        try
        {
            // Win: no tray price strip — desktop card only
            _config = await _ipc.CallAsync("set_config", new
            {
                patch = new Dictionary<string, object?>
                {
                    ["showMenuBarIcon"] = false,
                    ["showOnDesktop"] = true,
                }
            });
            _meta = await _ipc.CallAsync("meta");
            ApplyMeta();
            ApplyWindowChrome();
            await RefreshAsync();
            var sec = _config.TryGetProperty("refreshSeconds", out var rs) ? rs.GetInt32() : 10;
            _timer.Interval = TimeSpan.FromSeconds(Math.Max(10, sec));
            _timer.Start();
        }
        catch (Exception ex)
        {
            FooterText.Text = ex.Message;
            PriceText.Text = "--.--";
            TitleText.Text = "GoldTicker · IPC";
        }
    }

    private void ApplyMeta()
    {
        if (_meta is null) return;
        var m = _meta.Value;
        if (m.TryGetProperty("disclaimer", out var d)) _disclaimer = d.GetString() ?? "";
        if (m.TryGetProperty("strings", out var s) && s.TryGetProperty("unavailable", out var u))
            _unavailable = u.GetString() ?? _unavailable;

        MenuSymbols.Items.Clear();
        if (m.TryGetProperty("symbols", out var syms))
        {
            foreach (var sym in syms.EnumerateArray())
            {
                var id = sym.GetProperty("id").GetString()!;
                var name = sym.GetProperty("name").GetString()!;
                if (sym.TryGetProperty("is_estimated", out var est) && est.GetBoolean())
                    name += " (估算)";
                var item = new ToggleMenuFlyoutItem { Text = name, Tag = id };
                item.Click += Symbol_Click;
                MenuSymbols.Items.Add(item);
            }
        }

        MenuInterval.Items.Clear();
        if (m.TryGetProperty("refreshSeconds", out var intervals))
        {
            foreach (var v in intervals.EnumerateArray())
            {
                var sec = v.GetInt32();
                var item = new ToggleMenuFlyoutItem { Text = $"{sec} 秒", Tag = sec };
                item.Click += Interval_Click;
                MenuInterval.Items.Add(item);
            }
        }

        MenuWidth.Items.Clear();
        if (m.TryGetProperty("widths", out var widths))
        {
            foreach (var v in widths.EnumerateArray())
            {
                var w = v.GetInt32();
                var item = new ToggleMenuFlyoutItem { Text = $"{w} pt", Tag = w };
                item.Click += Width_Click;
                MenuWidth.Items.Add(item);
            }
        }

        MenuOpacity.Items.Clear();
        if (m.TryGetProperty("opacities", out var ops))
        {
            foreach (var v in ops.EnumerateArray())
            {
                var op = v.GetDouble();
                var item = new ToggleMenuFlyoutItem { Text = $"{op:P0}", Tag = op };
                item.Click += Opacity_Click;
                MenuOpacity.Items.Add(item);
            }
        }
    }

    private void ApplyWindowChrome()
    {
        var width = _config.TryGetProperty("width", out var w) ? w.GetInt32() : 216;
        var opacity = _config.TryGetProperty("opacity", out var o) ? o.GetDouble() : 0.88;
        var top = !_config.TryGetProperty("alwaysOnTop", out var t) || t.GetBoolean();

        var hwnd = WindowNative.GetWindowHandle(this);
        var appWindow = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
        var height = ChartCanvas.Visibility == Visibility.Visible ? 220 : 150;
        if (DetailsText.Visibility != Visibility.Visible) height -= 20;
        appWindow.Resize(new SizeInt32(width + 16, height));

        Root.Opacity = opacity;
        if (appWindow.Presenter is OverlappedPresenter p)
            p.IsAlwaysOnTop = top;

        MenuChart.IsChecked = !_config.TryGetProperty("showChart", out var sc) || sc.GetBoolean();
        MenuDetails.IsChecked = !_config.TryGetProperty("showDetails", out var sd) || sd.GetBoolean();
        MenuTop.IsChecked = top;
        ChartCanvas.Visibility = MenuChart.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
        DetailsText.Visibility = MenuDetails.IsChecked == true ? Visibility.Visible : Visibility.Collapsed;
    }

    private async Task RefreshAsync()
    {
        try
        {
            var result = await _ipc.CallAsync("fetch");
            if (result.TryGetProperty("config", out var cfg)) _config = cfg.Clone();
            _quote = result.TryGetProperty("quote", out var q) && q.ValueKind != JsonValueKind.Null
                ? q.Clone() : null;
            _samples.Clear();
            if (result.TryGetProperty("samples", out var samples))
            {
                foreach (var p in samples.EnumerateArray())
                {
                    if (!p.TryGetProperty("p", out var price) || price.GetDouble() <= 0) continue;
                    var ts = p.TryGetProperty("ts", out var tsv) ? tsv.GetInt64() : 0;
                    var t = p.TryGetProperty("t", out var tt) ? tt.GetString() ?? "" : "";
                    _samples.Add((ts, price.GetDouble(), t));
                }
            }
            RenderQuote();
            DrawChart();
            ApplyWindowChrome();
        }
        catch (Exception ex)
        {
            FooterText.Text = ex.Message;
        }
    }

    private void RenderQuote()
    {
        var langZh = true;
        if (_config.TryGetProperty("language", out var lang))
        {
            var l = lang.GetString() ?? "auto";
            langZh = l is "zh" or "auto" or "cn";
        }

        string name = "Gold";
        string unit = langZh ? "元/克" : "CNY/g";
        if (_meta is not null && _meta.Value.TryGetProperty("symbols", out var syms)
            && _config.TryGetProperty("symbol", out var sidEl))
        {
            var sid = sidEl.GetString();
            foreach (var s in syms.EnumerateArray())
            {
                if (s.GetProperty("id").GetString() == sid)
                {
                    name = s.GetProperty("name").GetString() ?? name;
                    unit = s.GetProperty("unit").GetString() ?? unit;
                    break;
                }
            }
        }

        if (_quote is null)
        {
            TitleText.Text = $"{name} · {unit}";
            PriceText.Text = "--.--";
            PriceText.Foreground = new SolidColorBrush(Muted);
            DeltaText.Text = "—";
            DeltaText.Foreground = new SolidColorBrush(Muted);
            DetailsText.Text = "";
            FooterText.Text = _unavailable;
            MenuRefresh.Text = _unavailable;
            return;
        }

        var q = _quote.Value;
        var price = q.GetProperty("price").GetDouble();
        var prev = q.GetProperty("prev_close").GetDouble();
        var open = q.GetProperty("open_price").GetDouble();
        var high = q.GetProperty("high").GetDouble();
        var low = q.GetProperty("low").GetDouble();
        var basisKey = _config.TryGetProperty("changeBasis", out var cb) ? cb.GetString() : "prevClose";
        var basis = basisKey == "open" ? open : prev;
        var change = price - basis;
        var pct = basis > 0 ? change / basis * 100.0 : 0.0;
        var colorMode = _config.TryGetProperty("colorMode", out var cm) ? cm.GetString() : "cny";
        var upIsRed = colorMode is null or "cny" or "red-up";
        Color tone;
        if (Math.Abs(change) < 1e-6) tone = Muted;
        else if (change > 0) tone = upIsRed ? Up : Down;
        else tone = upIsRed ? Down : Up;

        if (q.TryGetProperty("is_estimated", out var est) && est.GetBoolean())
            name += langZh ? " (点差估算)" : " (Est. Spread)";

        TitleText.Text = $"{name} · {unit}";
        PriceText.Text = price.ToString("0.00");
        PriceText.Foreground = new SolidColorBrush(tone);
        var sign = change >= 0 ? "+" : "";
        DeltaText.Text = $"{sign}{change:0.00}  ({sign}{pct:0.00}%)";
        DeltaText.Foreground = new SolidColorBrush(tone);

        var highL = langZh ? "高" : "High";
        var lowL = langZh ? "低" : "Low";
        var baseL = basisKey == "open" ? (langZh ? "今开" : "Open") : (langZh ? "昨收" : "Prev");
        DetailsText.Text = $"{highL} {high:0.00}  {lowL} {low:0.00}  {baseL} {basis:0.00}";
        FooterText.Text = q.TryGetProperty("time_str", out var ts) ? ts.GetString() : "";
        MenuRefresh.Text = $"{name} {price:0.00} ({sign}{pct:0.00}%)";
    }

    private void DrawChart()
    {
        ChartCanvas.Children.Clear();
        var w = Math.Max(ChartCanvas.ActualWidth, (_config.TryGetProperty("width", out var ww) ? ww.GetDouble() : 200) - 8);
        var h = ChartCanvas.Height;
        if (w <= 0 || h <= 0) return;

        Color tone = Up;
        double basis = 0;
        if (_quote is not null)
        {
            var q = _quote.Value;
            basis = (_config.TryGetProperty("changeBasis", out var cb) && cb.GetString() == "open")
                ? q.GetProperty("open_price").GetDouble()
                : q.GetProperty("prev_close").GetDouble();
            var price = q.GetProperty("price").GetDouble();
            var colorMode = _config.TryGetProperty("colorMode", out var cm) ? cm.GetString() : "cny";
            var upIsRed = colorMode is null or "cny";
            var change = price - basis;
            if (Math.Abs(change) < 1e-6) tone = Muted;
            else if (change > 0) tone = upIsRed ? Up : Down;
            else tone = upIsRed ? Down : Up;
        }

        if (_samples.Count < 2)
        {
            var dash = new Line
            {
                X1 = 0, Y1 = h / 2, X2 = w, Y2 = h / 2,
                Stroke = new SolidColorBrush(Color.FromArgb(40, 255, 255, 255)),
                StrokeThickness = 1,
                StrokeDashArray = new DoubleCollection { 4, 4 },
            };
            ChartCanvas.Children.Add(dash);
            return;
        }

        var prices = _samples.Select(s => s.p).ToList();
        if (basis > 0) prices.Add(basis);
        var lo = prices.Min();
        var hi = prices.Max();
        if (Math.Abs(hi - lo) < 1e-5) { lo -= 1; hi += 1; }
        var pad = Math.Max((hi - lo) * 0.12, 0.05);
        lo -= pad; hi += pad;

        double Y(double p) => h - (p - lo) / (hi - lo) * (h - 4) - 2;
        double X(int i) => i * (w - 2) / (_samples.Count - 1.0);

        if (basis > 0)
        {
            var yb = Y(basis);
            ChartCanvas.Children.Add(new Line
            {
                X1 = 0, Y1 = yb, X2 = w, Y2 = yb,
                Stroke = new SolidColorBrush(Color.FromArgb(50, 255, 255, 255)),
                StrokeThickness = 1,
                StrokeDashArray = new DoubleCollection { 3, 3 },
            });
        }

        var geo = new PathGeometry();
        var fig = new PathFigure { StartPoint = new Windows.Foundation.Point(X(0), Y(_samples[0].p)), IsClosed = false };
        for (var i = 1; i < _samples.Count; i++)
            fig.Segments.Add(new LineSegment { Point = new Windows.Foundation.Point(X(i), Y(_samples[i].p)) });
        geo.Figures.Add(fig);
        ChartCanvas.Children.Add(new ShapePath
        {
            Data = geo,
            Stroke = new SolidColorBrush(tone),
            StrokeThickness = 1.6,
            StrokeLineJoin = PenLineJoin.Round,
        });

        var last = _samples[^1];
        var dot = new Ellipse { Width = 5, Height = 5, Fill = new SolidColorBrush(tone) };
        Canvas.SetLeft(dot, X(_samples.Count - 1) - 2.5);
        Canvas.SetTop(dot, Y(last.p) - 2.5);
        ChartCanvas.Children.Add(dot);

        if (!string.IsNullOrEmpty(_samples[0].t) || !string.IsNullOrEmpty(last.t))
        {
            FooterText.Text = $"{_samples[0].t}  →  {last.t}";
        }
    }

    private async Task PatchAsync(Dictionary<string, object?> patch)
    {
        _config = await _ipc.CallAsync("set_config", new { patch });
        ApplyWindowChrome();
        await RefreshAsync();
        var sec = _config.TryGetProperty("refreshSeconds", out var rs) ? rs.GetInt32() : 10;
        _timer.Interval = TimeSpan.FromSeconds(Math.Max(10, sec));
    }

    private async void MenuRefresh_Click(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async void MenuChart_Click(object sender, RoutedEventArgs e)
        => await PatchAsync(new() { ["showChart"] = MenuChart.IsChecked == true });

    private async void MenuDetails_Click(object sender, RoutedEventArgs e)
        => await PatchAsync(new() { ["showDetails"] = MenuDetails.IsChecked == true });

    private async void MenuTop_Click(object sender, RoutedEventArgs e)
        => await PatchAsync(new() { ["alwaysOnTop"] = MenuTop.IsChecked == true });

    private async void Symbol_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is string id)
            await PatchAsync(new() { ["symbol"] = id });
    }

    private async void Basis_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is string tag)
            await PatchAsync(new() { ["changeBasis"] = tag });
    }

    private async void Color_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is string tag)
            await PatchAsync(new() { ["colorMode"] = tag });
    }

    private async void Lang_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is string tag)
        {
            await PatchAsync(new() { ["language"] = tag });
            _meta = await _ipc.CallAsync("meta");
            ApplyMeta();
            RenderQuote();
        }
    }

    private async void Interval_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is int sec)
            await PatchAsync(new() { ["refreshSeconds"] = sec });
    }

    private async void Width_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is int w)
            await PatchAsync(new() { ["width"] = w });
    }

    private async void Opacity_Click(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe && fe.Tag is double op)
            await PatchAsync(new() { ["opacity"] = op });
    }

    private async void OpenConfig_Click(object sender, RoutedEventArgs e)
        => await _ipc.CallAsync("open_data_dir");

    private async void ClearCache_Click(object sender, RoutedEventArgs e)
    {
        await _ipc.CallAsync("clear_cache");
        await RefreshAsync();
    }

    private void ResetPos_Click(object sender, RoutedEventArgs e)
    {
        var hwnd = WindowNative.GetWindowHandle(this);
        var appWindow = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
        var display = DisplayArea.GetFromWindowId(appWindow.Id, DisplayAreaFallback.Primary);
        var work = display.WorkArea;
        appWindow.Move(new PointInt32(work.X + work.Width - appWindow.Size.Width - 24, work.Y + 24));
    }

    private async void About_Click(object sender, RoutedEventArgs e)
    {
        var ver = "?";
        if (_meta is { } meta && meta.TryGetProperty("version", out var v))
            ver = v.GetString() ?? "?";
        var dlg = new ContentDialog
        {
            Title = "关于 GoldTicker",
            Content = $"版本：{ver}\nWinUI 3 桌面卡片 + Python core IPC\n无任务栏行情条（Win11 限制）",
            CloseButtonText = "确定",
            XamlRoot = Root.XamlRoot,
        };
        await dlg.ShowAsync();
    }

    private async void Disclaimer_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new ContentDialog
        {
            Title = "免责声明",
            Content = new ScrollViewer
            {
                Content = new TextBlock { Text = _disclaimer, TextWrapping = TextWrapping.Wrap, Width = 360 },
                MaxHeight = 280,
            },
            CloseButtonText = "确定",
            XamlRoot = Root.XamlRoot,
        };
        await dlg.ShowAsync();
    }

    private async void Github_Click(object sender, RoutedEventArgs e)
        => await Launcher.LaunchUriAsync(new Uri("https://github.com/realsuperj/gold-ticker"));

    private void Quit_Click(object sender, RoutedEventArgs e) => Close();

    private void Root_RightTapped(object sender, RightTappedRoutedEventArgs e) { /* ContextFlyout handles */ }

    private void Root_PointerPressed(object sender, PointerRoutedEventArgs e)
    {
        if (!e.GetCurrentPoint(Root).Properties.IsLeftButtonPressed) return;
        _dragging = true;
        Root.CapturePointer(e.Pointer);
        var hwnd = WindowNative.GetWindowHandle(this);
        var appWindow = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
        _windowStart = appWindow.Position;
        var pt = e.GetCurrentPoint(null).Position;
        // Approximate: use window position delta via AppWindow; store client point
        _dragStartScreen = new PointInt32((int)pt.X, (int)pt.Y);
    }

    private void Root_PointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (!_dragging) return;
        var pt = e.GetCurrentPoint(null).Position;
        var dx = (int)pt.X - _dragStartScreen.X;
        var dy = (int)pt.Y - _dragStartScreen.Y;
        var hwnd = WindowNative.GetWindowHandle(this);
        var appWindow = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
        appWindow.Move(new PointInt32(_windowStart.X + dx, _windowStart.Y + dy));
    }

    private void Root_PointerReleased(object sender, PointerRoutedEventArgs e)
    {
        if (!_dragging) return;
        _dragging = false;
        Root.ReleasePointerCapture(e.Pointer);
        var hwnd = WindowNative.GetWindowHandle(this);
        var appWindow = AppWindow.GetFromWindowId(Win32Interop.GetWindowIdFromWindow(hwnd));
        _ = PatchAsync(new()
        {
            ["windowX"] = appWindow.Position.X,
            ["windowY"] = appWindow.Position.Y,
        });
    }
}
