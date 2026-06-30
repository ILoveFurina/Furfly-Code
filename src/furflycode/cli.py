"""入口 — 加载配置、渲染 banner、启动 TUI。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from furflycode.config import ConfigError, load
from furflycode.context import build_session_context
from furflycode.tool import new_default_registry
from furflycode.tui.app import furflycodeApp


def main() -> None:
    """
    应用入口
    config通过load(config_path) 获得可操作的config顶层对象
    """
    config_path = ".furflycode/config.yaml"
    try:
        config = load(config_path)
    except ConfigError as e:
        print(f"配置错误: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        registry = new_default_registry()
        # 会话启动时一次性预读环境信息与 FURFLY.md（向上查找至项目根），
        # 会话期间复用此快照不重读（D7）。
        session_context = build_session_context(Path(os.getcwd()))
        app = furflycodeApp(
            config.providers,
            registry,
            max_iterations=config.max_iterations,
            session_context=session_context,
        )
        app.run()
    except KeyboardInterrupt:
        # Ctrl+C 在应用内部已处理；这里兜底捕获异常情况
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        print(f"运行错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
