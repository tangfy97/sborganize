"""Local inspection and onboarding commands; no device connections."""

import os
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer

from sborganize.guides import GUIDES
from sborganize.planner import Plan
from sborganize.render import layout_summary, render_layout, render_plan
from sborganize.safety import SafetyError, load_backup
from sborganize.score import score_layout
from sborganize.storage import ensure_private_dir, read_json, selected_plan
from sborganize.terminal import write_guide, write_text

config_app = typer.Typer(help="Create or inspect local preferences.", no_args_is_help=True)
JsonOutput = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


def emit(data):
    import json

    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@config_app.command("path")
def config_path(ctx: typer.Context):
    """Print the configuration file path."""
    typer.echo(str(ctx.obj.config_path))


@config_app.command("init")
def config_init(ctx: typer.Context):
    """Create a documented config; never overwrite your preferences."""
    path = ctx.obj.config_path
    if path.exists():
        write_text(f"Config already exists: {path}\nNext: sborganize config show")
        return
    ensure_private_dir(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(files("sborganize").joinpath("data/default_config.toml").read_text("utf-8"))
    write_text(f"Config saved: {path}\nEdit this file, then run sborganize plan.")


@config_app.command("show")
def config_show(ctx: typer.Context, json_output: JsonOutput = False):
    """Show effective preferences. Never displays an API key."""
    data = asdict(ctx.obj.config)
    if json_output:
        emit(data)
        return
    write_text(f"Configuration · {ctx.obj.config_path}\n")
    for key, value in data.items():
        if isinstance(value, dict):
            write_text(f"{key}  ·  {len(value)} entries")
            for name, setting in value.items():
                write_text(f"  {name}  →  {setting}")
        else:
            write_text(f"{key}  {value}")


def guide(
    topic: Annotated[
        str, typer.Argument(help="start, offline, config, policy, cloud or safety.")
    ] = "start",
):
    """Read a short offline guide in your terminal."""
    if topic not in GUIDES:
        raise typer.BadParameter("Choose: " + ", ".join(GUIDES), param_hint="TOPIC")
    write_guide(GUIDES[topic])


def show(
    ctx: typer.Context,
    plan_file: Annotated[
        Path | None, typer.Option("--plan", help="Inspect a particular plan.")
    ] = None,
    after: Annotated[
        bool, typer.Option("--after", help="Show the complete proposed layout.")
    ] = False,
    details: Annotated[
        bool, typer.Option("--details", help="Show every icon position change.")
    ] = False,
    json_output: JsonOutput = False,
):
    """Inspect the selected plan without a phone or another model call."""
    path = plan_file.expanduser() if plan_file else selected_plan(ctx.obj.root)
    proposal = Plan.from_dict(read_json(path))
    config = proposal.score_config(ctx.obj.config)
    if json_output:
        emit(layout_summary(proposal.after) if after else proposal.to_dict(config))
    elif after:
        write_text(render_layout(proposal.after))
    else:
        write_text(
            render_plan(
                proposal,
                score_layout(proposal.before, config),
                score_layout(proposal.after, config),
                details=details,
            )
        )
        write_text(f"\nPlan: {path}\nNext: sborganize show --after")


def backups(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(min=1, max=100, help="Maximum recent backups.")] = 10,
    json_output: JsonOutput = False,
):
    """List recent local backups without connecting to a phone."""
    rows, invalid = [], []
    for path in sorted((ctx.obj.root / "backups").glob("*.json"), reverse=True)[:limit]:
        try:
            layout = load_backup(path)
            rows.append(
                {
                    "path": str(path),
                    "source": layout.source,
                    "apps": len(layout.apps()),
                    "pages": len(layout.pages),
                }
            )
        except (SafetyError, ValueError, OSError, KeyError, TypeError) as exc:
            invalid.append({"path": str(path), "reason": str(exc)})
    if json_output:
        emit({"backups": rows, "invalid": invalid})
        return
    if not rows and not invalid:
        write_text("No backups yet. Run sborganize backup to save the current layout.")
    for row in rows:
        write_text(f"{row['source']} · {row['apps']} apps · {row['pages']} pages\n  {row['path']}")
    for row in invalid:
        write_text(f"Unreadable backup: {row['path']}\n  {row['reason']}", err=True)
