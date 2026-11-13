# GoldTicker Windows

下载 `GoldTicker.exe`，或解压 `GoldTicker-Windows-x64.zip` 后运行其中的 EXE，无需安装 Python。桌面卡片与通知区域托盘均可打开完整设置菜单，至少保留一个可见入口。托盘图标由系统通知区域按系统尺寸显示，不承诺任务栏内常驻完整文字。

支持切换标的、走势图、明细、置顶、宽度、透明度、涨跌基准、配色、刷新间隔、跟随系统/中文/英文，以及关于、免责声明和数据维护。中文前缀为“金”，英文为“Au”。产品图标与版本和 macOS 共用。

配置位于 `%APPDATA%\GoldTicker\config.json`；分时数据沿用本地采样与存储格式。浙商积存金、Au99.99 与美元报价的国际金相互独立；工行/建行按共享核心点差估算并明确标记。

源码：`python goldticker.py`。构建：先安装 `requirements.txt` 和 `pyinstaller>=6.11,<7`，再运行 `python tools/build.py`。本地和 CI 使用同一 `GoldTicker.spec`，输出 `dist/windows/GoldTicker.exe`、ZIP 和 SHA-256 文件。`python goldticker.py --smoke-test` 使用隔离临时数据执行离线原生界面冒烟。Wine 脚本仅为辅助构建，不替代真实 Windows GUI 验证。
