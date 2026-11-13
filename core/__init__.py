"""GoldTicker 跨平台通用核心业务内核 (core)。

禁止在此包内引入任何特定 GUI 表现层库 (如 AppKit, tkinter, pystray 等)。
纯标准库实现，提供标的定义、多源容灾轮询、点差折算、配置管理及分时持久化。
"""

__version__ = "1.0.0"
