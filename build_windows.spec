# Compatibility spec; both platforms share GoldTicker.spec.
from pathlib import Path
exec(compile((Path(SPECPATH) / "GoldTicker.spec").read_text(), "GoldTicker.spec", "exec"))
