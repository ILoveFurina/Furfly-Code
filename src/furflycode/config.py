"""furflycode 的配置加载与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


@dataclass
class ProviderConfig:
    """单个 LLM provider 的配置。"""

    name: str  # 状态栏左侧显示的名称
    protocol: Literal["anthropic", "openai"]
    api_key: str
    model: str  # 状态栏右侧显示的名称
    base_url: str | None = None  # 覆盖 SDK 的默认端点
    thinking: bool = False  # 仅对 anthropic 生效


@dataclass
class Config:
    """顶层配置。"""

    providers: list[ProviderConfig] = field(default_factory=list)


class ConfigError(Exception):
    """当配置无效或缺失时抛出。"""


_VALID_PROTOCOLS = {"anthropic", "openai"}


def _validate_providers(providers: list[dict]) -> list[str]:
    """校验 provider 条目并返回错误信息列表。"""
    errors: list[str] = []
    if not providers:
        errors.append("providers 列表不能为空")
        return errors

    for i, p in enumerate(providers):
        prefix = f"providers[{i}]"
        for key in ("name", "protocol", "api_key", "model"):
            value = p.get(key)
            if not value or (isinstance(value, str) and not value.strip()):
                errors.append(f"{prefix}.{key} 不能为空")
        protocol = p.get("protocol", "")
        if protocol and protocol not in _VALID_PROTOCOLS:
            errors.append(
                f"{prefix}.protocol 必须是 {_VALID_PROTOCOLS} 之一，实际为 {protocol!r}"
            )
    return errors


def _from_dict(data: dict) -> Config:
    """将解析后的 YAML 字典转换为 Config，并进行校验。"""
    providers_raw = data.get("providers", [])
    if not isinstance(providers_raw, list):
        raise ConfigError("providers 必须是列表")

    errors = _validate_providers(providers_raw)
    if errors:
        raise ConfigError("\n".join(errors))

    providers = [
        ProviderConfig(
            name=p["name"],
            protocol=p["protocol"],
            api_key=p["api_key"],
            model=p["model"],
            base_url=p.get("base_url"),
            thinking=p.get("thinking", False),
        )
        for p in providers_raw
    ]
    return Config(providers=providers)


def load(path: str) -> Config:
    """从 YAML 文件加载并校验配置。

    参数：
        path: YAML 配置文件的路径。

    返回：
        校验后的 Config 对象。

    抛出：
        ConfigError: 文件缺失、格式错误或内容无效时抛出。
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"无法读取配置文件: {e}") from e

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML 格式错误: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError("配置文件顶层必须是映射（key-value）")

    return _from_dict(data)
