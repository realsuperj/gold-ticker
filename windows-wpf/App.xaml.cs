using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows;
using GoldTicker.Wpf.Core;

namespace GoldTicker.Wpf;

public partial class App : Application
{
    private Mutex _instanceMutex;
    private EventWaitHandle _activateEvent;
    private Thread _activateWatchThread;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        if (e.Args != null && e.Args.Contains("--smoke-test", StringComparer.OrdinalIgnoreCase))
        {
            RunSmokeTest();
            Shutdown(0);
            return;
        }

        const string mutexName = @"Local\GoldTicker_SingleInstance_Mutex";
        const string eventName = @"Local\GoldTicker_Activate_Event";

        _instanceMutex = new Mutex(true, mutexName, out bool createdNew);
        if (!createdNew)
        {
            try
            {
                using (var ev = EventWaitHandle.OpenExisting(eventName))
                    ev.Set();
            }
            catch { }
            Shutdown(0);
            return;
        }

        _activateEvent = new EventWaitHandle(false, EventResetMode.AutoReset, eventName);
        var win = new MainWindow();
        win.Closed += (_, _) => Shutdown(0);
        MainWindow = win;
        win.Show();

        _activateWatchThread = new Thread(() =>
        {
            while (true)
            {
                try
                {
                    if (_activateEvent == null || !_activateEvent.WaitOne()) break;
                    Dispatcher.BeginInvoke(new Action(() =>
                    {
                        if (Current?.MainWindow is MainWindow mw)
                            mw.BringToVisibleFront();
                    }));
                }
                catch { break; }
            }
        })
        { IsBackground = true };
        _activateWatchThread.Start();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        try { _activateEvent?.Dispose(); } catch { }
        try
        {
            if (_instanceMutex != null)
            {
                _instanceMutex.ReleaseMutex();
                _instanceMutex.Dispose();
            }
        }
        catch { }
        base.OnExit(e);
    }

    private static void RunSmokeTest()
    {
        var tmp = Path.Combine(Path.GetTempPath(), "goldticker-wpf-smoke-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tmp);
        try
        {
            Environment.SetEnvironmentVariable("GOLDTICKER_DATA_DIR", tmp);
            var cfg = GoldStorage.LoadConfig();
            GoldStorage.FreezeDayBasis(GoldConstants.SymbolZsJcj, 833.01, 834.00);
            GoldStorage.RecordPricePoint(835.20, GoldConstants.SymbolZsJcj, DateTimeOffset.UtcNow.AddMinutes(-3).ToUnixTimeMilliseconds());
            GoldStorage.RecordPricePoint(837.59, GoldConstants.SymbolZsJcj, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
            var pts = GoldStorage.LoadTodayPoints(GoldConstants.SymbolZsJcj);
            if (pts.Count < 2) throw new InvalidOperationException("Smoke points failed");

            var win = new MainWindow(smokeMode: true);
            foreach (var lang in new[] { "zh", "en" })
            {
                cfg.Language = lang;
                GoldStorage.SaveConfig(cfg);
                win.ApplySmokeSample(cfg, new QuoteData
                {
                    Symbol = GoldConstants.SymbolZsJcj,
                    Price = 837.59,
                    PrevClose = 833.01,
                    OpenPrice = 834.00,
                    High = 843.63,
                    Low = 831.97,
                    Change = 4.58,
                    ChangePct = 0.55,
                    TimeStr = "10:30",
                    SourceId = "tangdouz",
                    SourceName = "浙商银行积存金",
                });
            }
            win.Close();
            Console.WriteLine("{\"smoke\":\"passed\",\"platform\":\"win32-wpf\",\"single_exe\":true,\"version\":\"" + GoldConstants.Version + "\"}");
        }
        finally
        {
            try { Directory.Delete(tmp, true); } catch { }
        }
    }
}
