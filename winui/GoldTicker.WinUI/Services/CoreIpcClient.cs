using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace GoldTicker.WinUI.Services;

/// <summary>
/// Talks to GoldTicker.Core.exe (packaged) or <c>python -m core.ipc_worker</c> (dev)
/// over newline-delimited JSON on stdio.
/// </summary>
public sealed class CoreIpcClient : IDisposable
{
    private readonly Process _proc;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private int _nextId = 1;
    private bool _disposed;

    private CoreIpcClient(Process proc)
    {
        _proc = proc;
        _ = Task.Run(DrainStderr);
    }

    public static CoreIpcClient Start()
    {
        var baseDir = AppContext.BaseDirectory;
        var coreExe = Path.Combine(baseDir, "GoldTicker.Core.exe");
        if (File.Exists(coreExe))
            return StartProcess(coreExe, arguments: "", workingDirectory: baseDir, pythonPath: null);

        var repo = FindRepoRoot();
        var py = FindPython();
        return StartProcess(py, arguments: "-u -m core.ipc_worker", workingDirectory: repo, pythonPath: repo);
    }

    private static CoreIpcClient StartProcess(string fileName, string arguments, string workingDirectory, string? pythonPath)
    {
        var psi = new ProcessStartInfo
        {
            FileName = fileName,
            Arguments = arguments,
            WorkingDirectory = workingDirectory,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            StandardInputEncoding = Encoding.UTF8,
            StandardOutputEncoding = Encoding.UTF8,
        };
        psi.Environment["PYTHONUTF8"] = "1";
        if (!string.IsNullOrEmpty(pythonPath))
            psi.Environment["PYTHONPATH"] = pythonPath;

        var proc = Process.Start(psi) ?? throw new InvalidOperationException($"Failed to start {fileName}");
        return new CoreIpcClient(proc);
    }

    private async Task DrainStderr()
    {
        try
        {
            while (!_proc.HasExited)
            {
                var line = await _proc.StandardError.ReadLineAsync().ConfigureAwait(false);
                if (line is null) break;
                Debug.WriteLine("[ipc] " + line);
            }
        }
        catch { /* ignore */ }
    }

    public async Task<JsonElement> CallAsync(string method, object? parameters = null, CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var id = Interlocked.Increment(ref _nextId);
            var req = JsonSerializer.Serialize(new Dictionary<string, object?>
            {
                ["id"] = id,
                ["method"] = method,
                ["params"] = parameters ?? new Dictionary<string, object>(),
            });
            await _proc.StandardInput.WriteLineAsync(req).ConfigureAwait(false);
            await _proc.StandardInput.FlushAsync(ct).ConfigureAwait(false);

            var line = await _proc.StandardOutput.ReadLineAsync(ct).ConfigureAwait(false)
                       ?? throw new InvalidOperationException("IPC worker closed stdout");
            using var doc = JsonDocument.Parse(line);
            var root = doc.RootElement;
            if (!root.GetProperty("ok").GetBoolean())
                throw new InvalidOperationException(root.GetProperty("error").GetString() ?? "IPC error");
            return root.GetProperty("result").Clone();
        }
        finally
        {
            _gate.Release();
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        try
        {
            if (!_proc.HasExited)
            {
                _proc.StandardInput.WriteLine(JsonSerializer.Serialize(new { id = 0, method = "quit" }));
                _proc.StandardInput.Flush();
                if (!_proc.WaitForExit(1500))
                    _proc.Kill(entireProcessTree: true);
            }
        }
        catch { /* ignore */ }
        _proc.Dispose();
        _gate.Dispose();
    }

    public static string FindPython()
    {
        var env = Environment.GetEnvironmentVariable("GOLDTICKER_PYTHON");
        if (!string.IsNullOrWhiteSpace(env) && File.Exists(env)) return env;

        foreach (var name in new[] { "python", "python3", "py" })
        {
            try
            {
                var probe = new ProcessStartInfo
                {
                    FileName = name,
                    Arguments = name == "py" ? "-3 -c \"import sys;print(sys.executable)\"" : "-c \"import sys;print(sys.executable)\"",
                    RedirectStandardOutput = true,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                using var p = Process.Start(probe);
                if (p is null) continue;
                var path = p.StandardOutput.ReadLine()?.Trim();
                p.WaitForExit(3000);
                if (!string.IsNullOrWhiteSpace(path) && File.Exists(path)) return path;
            }
            catch { /* try next */ }
        }
        throw new FileNotFoundException("Python not found. Set GOLDTICKER_PYTHON or install Python 3.");
    }

    public static string FindRepoRoot()
    {
        var env = Environment.GetEnvironmentVariable("GOLDTICKER_ROOT");
        if (!string.IsNullOrWhiteSpace(env) && Directory.Exists(Path.Combine(env, "core")))
            return Path.GetFullPath(env);

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "goldticker.py"))
                && Directory.Exists(Path.Combine(dir.FullName, "core")))
                return dir.FullName;
            dir = dir.Parent;
        }
        throw new DirectoryNotFoundException("Cannot locate gold-ticker repo root (goldticker.py). Set GOLDTICKER_ROOT.");
    }
}
