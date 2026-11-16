# GoldTicker Windows（原生单文件版）

基于系统内置 **`.NET Framework 4.8 + WPF`** 原生构建，编译产物仅**单个 `GoldTicker.exe`**（不到 1 MB），零伴随 `.dll` / `.json` 文件，下载后直接双击即可运行。

- **视觉与交互**：与 macOS 版对齐的圆角深色卡片、高分屏矢量抗锯齿排版、渐变填充当日分时折线图、深色圆角右键菜单；无任务栏显示。
- **配置与缓存**：自动隐藏存储于 `%APPDATA%\GoldTicker\config.json` 与 `intraday-YYYY-MM-DD.json`（与 Python `core/` 格式完全兼容）。

## 本地构建（Windows）

```powershell
.\tools\build_windows_wpf.ps1
```

产物输出至 `dist\windows\GoldTicker.exe`。
