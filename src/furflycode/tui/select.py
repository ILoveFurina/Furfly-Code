"""provider 选择界面 — 用 OptionList 在已配置的 provider 中挑选。"""

from __future__ import annotations

from textual.widgets import OptionList
from textual.widgets.option_list import Option

from furflycode.config import ProviderConfig


class ProviderSelect(OptionList):
    """用于展示已配置 provider 以供选择的 OptionList。"""

    DEFAULT_CSS = """
    ProviderSelect {
        height: 1fr;
        border: solid $primary;
        padding: 1 2;
    }
    """

    def __init__(self, providers: list[ProviderConfig]) -> None:
        options: list[Option | None] = []
        for i, p in enumerate(providers):
            options.append(Option(f"{p.name} ({p.model})", id=str(i)))
        super().__init__(*options)
        self._providers = providers

    def get_provider(self, option_id: str) -> ProviderConfig:
        """根据 option ID 查找对应的 ProviderConfig。"""
        idx = int(option_id)
        return self._providers[idx]
