# GoldTicker Windows

## 正式观感：WinUI 包（不是 Tk）

解压 **`GoldTicker-WinUI-Windows-x64.zip`**，运行同目录 `GoldTicker.exe`（旁路 `GoldTicker.Core.exe` 走 Python core IPC）。  
无任务栏宽条行情。详见 [`../winui/README.md`](../winui/README.md)。

## 旧 Tk 壳

仅兼容/回退，**不要当当前交付物**。源码临时：`$env:GOLD_TICKER_UI='tk'; python goldticker.py`。
