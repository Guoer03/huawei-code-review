#!/usr/bin/env python3
"""CLI compatibility wrapper for the reusable huawei-code-review engine."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CLI_VERSION = "0.4.0"

# Direct execution (python scripts/check.py) and package imports both work.
try:
    from .config import ConfigError, load_config, merge_cli
    from .engine import RULES, SOURCE, check, exit_code, files_for, language_for, render
    from .xlsx_export import write_xlsx
except ImportError:  # pragma: no cover
    from config import ConfigError, load_config, merge_cli
    from engine import RULES, SOURCE, check, exit_code, files_for, language_for, render
    from xlsx_export import write_xlsx


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="huawei-code-review",
        description="Deterministic Huawei/OpenHarmony code review",
        epilog=(
            "Examples: huawei-code-review src/ --format json; "
            "huawei-code-review src/ --format sarif --require-tool ruff"
        ),
    )
    parser.add_argument("--version", action="version", version=f"huawei-code-review {CLI_VERSION}")
    parser.add_argument("inputs", nargs="*", help="files, directories, or - for stdin")
    parser.add_argument("--ruleset", choices=["catalog", "legacy"], help="default: imported catalog; legacy runs only the original 17 checks")
    parser.add_argument("--list-rules", action="store_true", help="show imported rule implementation inventory without scanning")
    parser.add_argument("--select", action="append", default=None, help="execute only this imported rule ID or identity key (repeatable)")
    parser.add_argument('--rule-option', action='append', default=[], metavar='RULE:OPTION=VALUE',
                        help='override one declared catalog option (repeatable)')
    parser.add_argument("--language", choices=["auto", *RULES], default=None)
    parser.add_argument("--profile", choices=["balanced", "strict"], default=None)
    parser.add_argument("--format", choices=["json", "markdown", "sarif", "xlsx"], default=None)
    parser.add_argument("--output", help="write the rendered report to a file (required for xlsx)")
    parser.add_argument("--config", help="TOML/JSON project configuration")
    parser.add_argument("--exclude", action="append", default=None, help="glob/path to exclude (repeatable)")
    parser.add_argument("--ignore", action="append", default=None, help="rule ID or path pattern to ignore (repeatable)")
    parser.add_argument("--fail-on", choices=["none", "info", "warning", "error"], default=None)
    parser.add_argument("--allow-uncovered", action="store_true", help="do not fail when a file cannot be classified/read")
    parser.add_argument("--tool", action="append", default=None, help="run an optional external adapter (repeatable)")
    parser.add_argument("--require-tool", action="append", default=None, help="run an external adapter and fail if missing (repeatable)")
    parser.add_argument("--tool-path", action="append", default=[], metavar="TOOL=PATH", help="explicit external executable path")
    parser.add_argument("--tool-arg", action="append", default=[], metavar="TOOL=ARG", help="one literal external argument per occurrence")
    parser.add_argument("--tool-timeout", type=float, help="external tool timeout in seconds")
    args = parser.parse_args(argv)
    try:
        loaded = load_config(args.config)
        config = merge_cli(loaded, language=args.language, profile=args.profile, format=args.format,
                           exclude=args.exclude, ignore=args.ignore, fail_on=args.fail_on,
                           ruleset=args.ruleset, enabled_rules=args.select, tool_timeout=args.tool_timeout,
                           allow_uncovered=True if args.allow_uncovered else None)
        config.rule_options = {key: dict(value) for key, value in config.rule_options.items()}
        for argument in args.rule_option:
            target, equals, value = argument.partition('=')
            identity, colon, name = target.rpartition(':')
            if not equals or not colon or not identity or not name:
                raise ConfigError('--rule-option requires RULE:OPTION=VALUE')
            config.rule_options.setdefault(identity, {})[name] = value
        import math
        if config.ruleset == 'legacy' and config.enabled_rules is not None:
            raise ConfigError('--select/enabled_rules requires the catalog ruleset')
        if config.ruleset == 'legacy' and config.rule_options:
            raise ConfigError('rule options require the catalog ruleset')
        if not math.isfinite(config.tool_timeout) or config.tool_timeout <= 0:
            raise ConfigError("tool_timeout must be a finite positive number")
        paths = dict(config.tool_paths)
        tool_args = {name: list(values) for name, values in config.tool_args.items()}
        for value in args.tool_path:
            name, separator, path = value.partition('=')
            if not separator or not name or not path:
                raise ConfigError('--tool-path requires TOOL=PATH')
            paths[name] = path
        for value in args.tool_arg:
            name, separator, argument = value.partition('=')
            if not separator or not name:
                raise ConfigError('--tool-arg requires TOOL=ARG')
            tool_args.setdefault(name, []).append(argument)
        if args.list_rules:
            if config.ruleset != 'catalog':
                raise ConfigError('--list-rules requires the catalog ruleset')
            try:
                from .catalog_engine import inventory_report
            except ImportError:
                from catalog_engine import inventory_report
            report = inventory_report(config)
        else:
            if not args.inputs:
                raise ConfigError('at least one input is required unless --list-rules is used')
            report = check(args.inputs, config=config, language=config.language, profile=config.profile)
        requested = list(dict.fromkeys(config.tools + config.required_tools))
        if args.tool:
            requested.extend(args.tool)
        if args.require_tool:
            requested.extend(args.require_tool)
        if requested and not args.list_rules:
            try:
                from ..adapters.runner import run_adapter
            except ImportError:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from adapters.runner import run_adapter
            adapter_results = []
            required = set(config.required_tools + (args.require_tool or []))
            for name in dict.fromkeys(requested):
                result = run_adapter(name, args.inputs, executable=paths.get(name),
                                     extra_args=tool_args.get(name, []), timeout=config.tool_timeout)
                adapter_results.append(result)
                report["findings"].extend(result.get("findings", []))
                if result.get("status") in {"missing", "timeout", "error", "skipped"} and name in required:
                    report.setdefault("uncovered", []).append({"path": "<tool>", "reason": f"required adapter {name}: {result.get('status')}"})
            report["summary"]["findings"] = len(report["findings"])
            for severity in ("error", "warning", "info"):
                report["summary"][f"{severity}s"] = sum(x.get("severity") == severity for x in report["findings"])
            report["summary"]["pass"] = exit_code(report, config.fail_on, config.allow_uncovered) == 0
            if report.get('uncovered'):
                report.setdefault('coverage_summary', {})['complete'] = False
            report["toolchain"]["adapters"] = adapter_results
        if config.format == "xlsx":
            if not args.output:
                raise ValueError("--output is required when --format xlsx")
            output_path = write_xlsx(report, args.output)
            # Keep stdout text-only and machine-readable for callers that need
            # to discover the artifact path while the exit code remains the
            # authoritative pass/fail signal.
            print(output_path)
        else:
            rendered = render(report, config.format)
            if args.output:
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(rendered, encoding="utf-8")
            else:
                print(rendered)
        return 0 if args.list_rules else exit_code(report, config.fail_on, config.allow_uncovered)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"huawei-code-review: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
