# GoldTicker WinUI（Windows 表现层）

桌面卡片：**WinUI 3 + Acrylic**。行情/配置/分时：旁路进程 **`GoldTicker.Core.exe`**（Python `core/`，JSON Lines IPC）。

**不做**任务栏宽条行情。

## 发布包（推荐）

解压 `GoldTicker-WinUI-Windows-x64.zip` 后运行其中的 `GoldTicker.exe`（同目录需有 `GoldTicker.Core.exe`）。

CI：`.github/workflows/winui-package.yml`。

## 开发运行

```powershell
pip install -r requirements.txt
.\winui\run.ps1
```

需 [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)。开发态会启动 `python -m core.ipc_worker`。

本地打发布包（仅 Windows）：

```powershell
.\tools\package_winui.ps1
```
