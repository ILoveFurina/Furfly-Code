"""入口 — 加载配置、渲染 banner、启动 TUI。"""

from __future__ import annotations

import sys

from furflycode.config import ConfigError, load
from furflycode.tui.app import furflycodeApp


def main() -> None:
    """应用入口。"""
    config_path = ".furflycode/config.yaml"
    try:
        config = load(config_path)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        app = furflycodeApp(config.providers)
        app.run()
    except KeyboardInterrupt:
        # Ctrl+C 在应用内部已处理；这里兜底捕获异常情况
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        print(f"运行错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
