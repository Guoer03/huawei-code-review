"""Configuration and path filtering for huawei-code-review.

The checker intentionally uses only the Python standard library.  A project can
configure it with ``.huawei-code-review.toml`` (preferred) or JSON.  The same
options are available as CLI flags and CLI values take precedence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import json
from pathlib import Path
from typing import Any, Iterable

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only old Python runtimes
    tomllib = None


class ConfigError(ValueError):
    """A configuration file cannot be loaded or has an invalid shape."""


DEFAULT_CONFIG_NAMES = (
    ".huawei-code-review.toml",
    ".huawei-code-review.json",
    "huawei-code-review.toml",
    "huawei-code-review.json",
)
DEFAULT_EXCLUDES = (".git", ".hg", ".svn", "node_modules", "dist", "build", "coverage", ".worktrees")


@dataclass
class Config:
    ruleset: str = "catalog"
    language: str = "auto"
    profile: str = "balanced"
    format: str = "json"
    fail_on: str = "error"
    ignore: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    disabled_rules: list[str] = field(default_factory=list)
    enabled_rules: list[str] | None = None
    include_hidden: bool = False
    allow_uncovered: bool = False
    source: str | None = None
    tools: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    tool_paths: dict[str, str] = field(default_factory=dict)
    tool_args: dict[str, list[str]] = field(default_factory=dict)
    tool_timeout: float = 60.0
    rule_options: dict[str, dict[str, str | int]] = field(default_factory=dict)


def _as_list(value: Any, key: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a string or list of strings")
    return list(value)


def _parse_mapping(raw: Any, source: str | None = None) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError("configuration root must be an object/table")
    # Permit a [checker] table while accepting flat configuration for ease of use.
    values = raw.get("checker", raw)
    if not isinstance(values, dict):
        raise ConfigError("checker configuration must be an object/table")
    config = Config(source=source)
    string_choices = {"language", "profile", "format", "fail_on", "ruleset"}
    for key in string_choices:
        if key in values:
            if not isinstance(values[key], str):
                raise ConfigError(f"{key} must be a string")
            setattr(config, key, values[key])
    for key in ("ignore", "exclude", "disabled_rules", "enabled_rules"):
        if key in values:
            parsed = _as_list(values[key], key)
            if key == "enabled_rules":
                config.enabled_rules = parsed
            else:
                setattr(config, key, parsed)
    for key in ("include_hidden", "allow_uncovered"):
        if key in values:
            if not isinstance(values[key], bool):
                raise ConfigError(f"{key} must be a boolean")
            setattr(config, key, values[key])
    tools = values.get("tools")
    if isinstance(tools, dict):
        config.tools = _as_list(tools.get("optional"), "tools.optional")
        config.required_tools = _as_list(tools.get("required"), "tools.required")
    elif tools is not None:
        config.tools = _as_list(tools, "tools")
    if "required_tools" in values:
        config.required_tools = _as_list(values["required_tools"], "required_tools")
    for key in ("tool_paths", "tool_args"):
        if key not in values:
            continue
        mapping = values[key]
        if not isinstance(mapping, dict) or not all(isinstance(k, str) for k in mapping):
            raise ConfigError(f"{key} must be an object/table")
        for name, value in mapping.items():
            if key == "tool_paths" and not isinstance(value, str):
                raise ConfigError(f"tool_paths.{name} must be a string")
            if key == "tool_args" and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
                raise ConfigError(f"tool_args.{name} must be a list of strings")
        setattr(config, key, mapping)
    if "tool_timeout" in values:
        import math
        value = values["tool_timeout"]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ConfigError("tool_timeout must be a finite positive number")
        config.tool_timeout = float(value)
    # A convenient aliases used by several linters.
    if "ignore_patterns" in values:
        config.ignore.extend(_as_list(values["ignore_patterns"], "ignore_patterns"))
    rules = values.get("rules")
    if rules is not None and not isinstance(rules, dict):
        raise ConfigError('rules must be an object/table')
    if isinstance(rules, dict):
        for rule_id, setting in rules.items():
            if isinstance(setting, str) and setting.lower() in {"off", "disable", "disabled"}:
                config.disabled_rules.append(rule_id)
            elif isinstance(setting, dict):
                if 'enabled' in setting and not isinstance(setting['enabled'], bool):
                    raise ConfigError(f'rules.{rule_id}.enabled must be a boolean')
                if setting.get('enabled') is False:
                    config.disabled_rules.append(rule_id)
                if 'severity' in setting:
                    if not isinstance(setting['severity'], str) or setting['severity'] not in {'info', 'warning', 'error'}:
                        raise ConfigError(f'rules.{rule_id}.severity must be info, warning or error')
                    config.ignore.append(f"__severity__:{rule_id}={setting['severity']}")
                if 'options' in setting:
                    if not isinstance(setting['options'], dict):
                        raise ConfigError(f'rules.{rule_id}.options must be an object/table')
                    config.rule_options[rule_id] = dict(setting['options'])
                unknown = set(setting) - {'enabled', 'severity', 'options'}
                if unknown:
                    raise ConfigError(f'unknown rule setting for {rule_id}: {sorted(unknown)}')
            elif setting not in (None, True, "on", "enable", "enabled"):
                raise ConfigError(f"rules.{rule_id} must be enabled/disabled or a table")
    allowed = {"auto", "java", "javascript", "typescript", "python"}
    if config.ruleset not in {"catalog", "legacy"}:
        raise ConfigError(f"unsupported ruleset: {config.ruleset}")
    if config.language not in allowed:
        raise ConfigError(f"unsupported language: {config.language}")
    if config.profile not in {"balanced", "strict"}:
        raise ConfigError(f"unsupported profile: {config.profile}")
    if config.format not in {"json", "markdown", "sarif", "xlsx"}:
        raise ConfigError(f"unsupported format: {config.format}")
    if config.fail_on not in {"none", "info", "warning", "error"}:
        raise ConfigError(f"unsupported fail_on: {config.fail_on}")
    return config


def load_config(path: str | Path | None = None, cwd: str | Path | None = None) -> Config:
    """Load project config, returning defaults when no config exists."""
    base = Path(cwd or Path.cwd())
    selected = Path(path) if path else next((base / name for name in DEFAULT_CONFIG_NAMES if (base / name).is_file()), None)
    if selected is None:
        return Config()
    try:
        raw_bytes = selected.read_bytes()
        if selected.suffix.lower() == ".json":
            raw = json.loads(raw_bytes.decode("utf-8"))
        elif tomllib is not None:
            raw = tomllib.loads(raw_bytes.decode("utf-8"))
        else:  # pragma: no cover
            raise ConfigError("TOML config requires Python 3.11 or newer; use JSON instead")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"cannot read {selected}: {exc}") from exc
    return _parse_mapping(raw, str(selected))


def merge_cli(config: Config, **values: Any) -> Config:
    """Apply non-None CLI values to a config without mutating the input."""
    result = Config(**{name: getattr(config, name) for name in config.__dataclass_fields__})
    for name, value in values.items():
        if value is None or not hasattr(result, name):
            continue
        if name in {"ignore", "exclude", "disabled_rules"}:
            current = list(getattr(result, name))
            current.extend(value if isinstance(value, list) else [value])
            setattr(result, name, current)
        else:
            setattr(result, name, value)
    return result


def path_is_ignored(path: str | Path, patterns: Iterable[str], root: str | Path | None = None) -> bool:
    """Match a path against gitignore-like glob patterns and exact rule IDs."""
    path_obj = Path(path)
    text = path_obj.as_posix()
    root_obj = Path(root).resolve() if root else None
    if root_obj:
        try:
            text = path_obj.resolve().relative_to(root_obj).as_posix()
        except ValueError:
            pass
    candidates = {text, path_obj.name}
    ignored = False
    for pattern in patterns:
        pattern = pattern.strip()
        if not pattern or pattern.startswith("#") or pattern.startswith("__severity__:"):
            continue
        negate = pattern.startswith("!")
        if negate:
            pattern = pattern[1:]
        pattern = pattern.lstrip("/")
        if any(fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(candidate, f"*/{pattern}") for candidate in candidates):
            ignored = not negate
    return ignored
