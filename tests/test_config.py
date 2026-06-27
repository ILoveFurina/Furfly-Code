"""Tests for the config module."""

from __future__ import annotations

import pytest
import yaml

from furflycode.config import ConfigError, load


def _write_config(tmp_path, data: str):
    path = tmp_path / "config.yaml"
    path.write_text(data, encoding="utf-8")
    return str(path)


def test_load_valid_single_provider(tmp_path):
    """A valid single-provider config loads correctly."""
    path = _write_config(
        tmp_path,
        yaml.dump(
            {
                "providers": [
                    {
                        "name": "Claude",
                        "protocol": "anthropic",
                        "api_key": "sk-test",
                        "model": "claude-sonnet-4-20250514",
                        "thinking": True,
                    }
                ]
            }
        ),
    )
    config = load(path)
    assert len(config.providers) == 1
    p = config.providers[0]
    assert p.name == "Claude"
    assert p.protocol == "anthropic"
    assert p.api_key == "sk-test"
    assert p.thinking is True
    assert p.base_url is None


def test_load_valid_multiple_providers(tmp_path):
    """A valid multi-provider config loads all entries."""
    path = _write_config(
        tmp_path,
        yaml.dump(
            {
                "providers": [
                    {
                        "name": "Claude",
                        "protocol": "anthropic",
                        "api_key": "sk-test",
                        "model": "claude-sonnet-4-20250514",
                    },
                    {
                        "name": "GPT",
                        "protocol": "openai",
                        "api_key": "sk-test2",
                        "model": "gpt-4o",
                        "base_url": "https://api.openai.com/v1",
                    },
                ]
            }
        ),
    )
    config = load(path)
    assert len(config.providers) == 2
    assert config.providers[1].base_url == "https://api.openai.com/v1"
    assert config.providers[1].thinking is False


def test_load_missing_file(tmp_path):
    """A missing config file raises ConfigError."""
    with pytest.raises(ConfigError, match="不存在"):
        load(str(tmp_path / "nope.yaml"))


def test_load_empty_providers(tmp_path):
    """An empty providers list raises ConfigError."""
    path = _write_config(tmp_path, yaml.dump({"providers": []}))
    with pytest.raises(ConfigError, match="不能为空"):
        load(path)


def test_load_missing_api_key(tmp_path):
    """A missing api_key raises ConfigError mentioning the field."""
    path = _write_config(
        tmp_path,
        yaml.dump(
            {
                "providers": [
                    {
                        "name": "Claude",
                        "protocol": "anthropic",
                        "model": "claude-sonnet-4-20250514",
                    }
                ]
            }
        ),
    )
    with pytest.raises(ConfigError, match="api_key"):
        load(path)


def test_load_invalid_protocol(tmp_path):
    """An invalid protocol raises ConfigError."""
    path = _write_config(
        tmp_path,
        yaml.dump(
            {
                "providers": [
                    {
                        "name": "X",
                        "protocol": "weird",
                        "api_key": "sk-test",
                        "model": "m",
                    }
                ]
            }
        ),
    )
    with pytest.raises(ConfigError, match="protocol"):
        load(path)


def test_load_malformed_yaml(tmp_path):
    """Malformed YAML raises ConfigError."""
    path = _write_config(tmp_path, "providers: [unclosed")
    with pytest.raises(ConfigError, match="YAML"):
        load(path)
