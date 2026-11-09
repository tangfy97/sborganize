"""Rules-first CLI with explicit optional cloud advice and guarded device writes."""

import asyncio
import getpass
import json
import os
import shlex
import sys
import warnings
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Annotated

import typer

from sborganize import __version__
from sborganize.apple import AppleProvider
from sborganize.config import Config, load_config
from sborganize.device import DeviceError, FixtureDevice, connect_usb
from sborganize.local import backups, config_app, guide, show
from sborganize.model import Layout, fingerprint, validate_target
from sborganize.openrouter import OpenRouterProvider
from sborganize.planner import Plan, build_plan
from sborganize.policy import build_policy_plan, export_policy
from sborganize.render import layout_summary, render_layout, render_plan, render_score
from sborganize.reorganization import build_reorganization, refresh_reorganization
from sborganize.review import recheck_report, render_review, review_layout
from sborganize.safety import SafetyError, apply_target, backup_layout, latest_backup, load_backup
from sborganize.score import score_layout
from sborganize.smart import refine_plan
from sborganize.storage import (
    layout_document,
    layout_from_document,
    read_json,
    select_plan,
    selected_plan,
    write_json,
)
from sborganize.terminal import plain_environment, set_plain, write_text
from sborganize.wire import prepare_device_plan, validate_wire_state

app = typer.Typer(
    help="Organize your iPhone Home Screen. Local rules, preview first.",
    no_args_is_help=False,
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
app.add_typer(config_app, name="config", rich_help_panel="Local files")
app.command("guide", rich_help_panel="Start here")(guide)
app.command("show", rich_help_panel="Inspect and plan")(show)
app.command("backups", rich_help_panel="Local files")(backups)
policy_app = typer.Typer(
    help="Export a draft for deliberate all-app redesign.", no_args_is_help=True
)
app.add_typer(policy_app, name="policy", rich_help_panel="Local files")
Fixture = Annotated[Path | None, typer.Option(help="Read a layout JSON; never contact USB.")]
Udid = Annotated[str | None, typer.Option(help="Select a trusted USB device.")]
JsonOutput = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


@dataclass
class Settings:
    root: Path
    config: Config
    config_path: Path


def version_callback(value: bool):
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def no_color_callback(ctx: typer.Context, value: bool):
    if value:
        ctx.with_resource(plain_environment())
    return value


@app.callback()
def setup(
    ctx: typer.Context,
    data_dir: Annotated[
        Path | None, typer.Option(help="Local plans, backups and config directory.")
    ] = None,
    config: Annotated[Path | None, typer.Option(help="Override config.toml path.")] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version.",
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option(
            "--no-color",
            help="Disable terminal colors; NO_COLOR also works.",
            callback=no_color_callback,
            is_eager=True,
        ),
    ] = False,
):
    set_plain(no_color)
    root = (data_dir or Path.home() / ".sborganize").expanduser()
    if (
        config is not None
        and not config.expanduser().is_file()
        and ctx.invoked_subcommand != "config"
    ):
        raise ValueError(f"Config file not found: {config}")
    path = config.expanduser() if config else root / "config.toml"
    ctx.obj = Settings(root, load_config(path), path)
    if ctx.invoked_subcommand is None:
        write_text(
            f"sborganize {__version__} · a calmer Home Screen\n\n"
            "Try     sborganize demo\n"
            "Learn   sborganize guide\n"
            "Help    sborganize --help\n\nRules first. Preview first. No phone writes."
        )


def demo_layout() -> Layout:
    data = json.loads(files("sborganize").joinpath("data/demo_layout.json").read_text("utf-8"))
    return layout_from_document(data)


@asynccontextmanager
async def open_device(fixture: Path | None, udid: str | None, *, allow_write=False):
    if fixture is not None:
        if udid:
            raise ValueError("Choose --fixture or --udid, not both.")
        yield FixtureDevice(layout_from_document(read_json(fixture.expanduser())))
    else:
        async with connect_usb(udid, allow_write=allow_write) as device:
            yield device


def read_layout(fixture, udid):
    async def read():
        async with open_device(fixture, udid) as device:
            return await device.read()

    return asyncio.run(read())


def emit(data: dict):
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


def cloud_provider(config: Config) -> OpenRouterProvider:
    provider = OpenRouterProvider(config.openrouter_model)
    if not provider.probe()["available"] and sys.stdin.isatty():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("OpenRouter API key (hidden; used for this command only): ")
        except (getpass.GetPassWarning, EOFError) as exc:
            raise ValueError(
                "Hidden key input unavailable. Set OPENROUTER_API_KEY locally."
            ) from exc
        provider = OpenRouterProvider(config.openrouter_model, api_key=key)
    return provider


@policy_app.command("export")
def policy_export(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    from_plan: Annotated[
        Path | None, typer.Option(help="Reuse a saved plan's original snapshot.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option(help="Draft JSON path; source is saved beside it.")
    ] = None,
):
    """Export an editable draft and source snapshot. Never change the phone."""
    if from_plan and (fixture or udid):
        raise ValueError("Choose --from-plan, --fixture or --udid.")
    destination = (output or ctx.obj.root / "policies/draft.json").expanduser()
    source = destination.with_suffix(".source.json")
    if destination.suffix != ".json" or destination.exists() or source.exists():
        raise ValueError("Choose a new .json output path; existing drafts are never overwritten.")
    if any(
        destination.resolve().is_relative_to((ctx.obj.root / name).resolve())
        for name in ("backups", "plans")
    ):
        raise ValueError("Policy drafts cannot be saved in backup or plan storage.")
    layout = (
        Plan.from_dict(read_json(from_plan.expanduser())).before
        if from_plan
        else read_layout(fixture, udid)
    )
    draft = export_policy(layout, ctx.obj.config)
    write_json(source, layout_document(layout))
    write_json(destination, draft)
    write_text(
        f"Policy draft saved: {destination}\nSource snapshot: {source}\n\n"
        "Review every destination and reason. Use unique emoji names and resolve REVIEW entries.\n"
        "Next: sborganize guide policy"
    )


@app.command(rich_help_panel="Start here")
def demo(
    ctx: typer.Context,
    json_output: JsonOutput = False,
    save: Annotated[
        bool, typer.Option("--save", help="Save a fixture and demo plan for offline rehearsal.")
    ] = False,
    details: Annotated[
        bool, typer.Option("--details", help="Show the source layout and every position change.")
    ] = False,
):
    """Try a bundled example. No phone, network or model needed."""
    config = Config()
    layout = demo_layout()
    proposal = build_plan(layout, config)
    sample = ctx.obj.root / "examples/demo.json"
    path = ctx.obj.root / "plans/demo.json"
    if save:
        write_json(sample, layout_document(layout))
        write_json(path, proposal.to_dict(config))
        select_plan(ctx.obj.root, path)
    if json_output:
        data = {"layout": layout_summary(layout), "plan": proposal.to_dict(config)}
        if save:
            data.update(fixture=str(sample), saved_to=str(path))
        emit(data)
        return
    write_text("sborganize · offline demo")
    if details:
        write_text(render_layout(layout) + "\n")
    write_text(
        "\n"
        + render_plan(
            proposal,
            score_layout(layout, config),
            score_layout(proposal.after, config),
            details=details,
        )
    )
    if save:
        write_text(f"\nFixture saved: {sample}\nPlan saved: {path}\n\nNext:")
        write_text(
            shlex.join(
                ["sborganize", "--data-dir", str(ctx.obj.root), "apply", "--fixture", str(sample)]
            )
        )
    else:
        write_text("\nNext: sborganize doctor\nRehearse without a phone: sborganize guide offline")


@app.command(rich_help_panel="Inspect and plan")
def scan(fixture: Fixture = None, udid: Udid = None, json_output: JsonOutput = False):
    """Read a layout without changing it."""
    layout = read_layout(fixture, udid)
    if json_output:
        emit({**layout_summary(layout), **layout_document(layout)})
    else:
        write_text(render_layout(layout))


@app.command(rich_help_panel="Inspect and plan")
def score(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    json_output: JsonOutput = False,
    existing_only: Annotated[
        bool, typer.Option("--existing-only", help="Report the grouping rate for existing folders.")
    ] = False,
):
    """Explain a layout score or the existing-only grouping rate."""
    config = (
        replace(ctx.obj.config, create_folders=False, compact_folders=False)
        if existing_only
        else ctx.obj.config
    )
    result = score_layout(read_layout(fixture, udid), config)
    emit(result.to_dict()) if json_output else write_text(render_score(result))


@app.command(rich_help_panel="Inspect and plan")
def plan(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    json_output: JsonOutput = False,
    smart: Annotated[
        bool,
        typer.Option(
            "--smart",
            help="Refine unresolved apps using Apple's on-device model; else rules.",
            rich_help_panel="Optional models",
        ),
    ] = False,
    cloud: Annotated[
        bool,
        typer.Option(
            "--cloud",
            help="Opt in to sending unresolved app/folder metadata to OpenRouter.",
            rich_help_panel="Optional models",
        ),
    ] = False,
    no_network: Annotated[
        bool,
        typer.Option(
            "--no-network",
            help="Stay offline; already the prototype default.",
            rich_help_panel="Optional models",
        ),
    ] = False,
    existing_only: Annotated[
        bool,
        typer.Option(
            "--existing-only",
            help="Reuse folders; keep existing apps in place, never create folders.",
        ),
    ] = False,
    device_ready: Annotated[
        bool,
        typer.Option(
            "--device-ready", help="Prepare USB target; compact loose slots after fixed anchors."
        ),
    ] = False,
    from_review: Annotated[
        Path | None,
        typer.Option(
            help="Locally validate a complete saved cloud review before planning.",
            rich_help_panel="Advanced workflows",
        ),
    ] = None,
    source_plan: Annotated[
        Path | None,
        typer.Option(
            help="Use the original snapshot in this plan with --from-review.",
            rich_help_panel="Advanced workflows",
        ),
    ] = None,
    refresh_device: Annotated[
        bool,
        typer.Option(
            "--refresh-device",
            help="Read USB again; allow only appended apps and bookkeeping changes.",
            rich_help_panel="Advanced workflows",
        ),
    ] = False,
    policy_file: Annotated[
        Path | None,
        typer.Option(
            "--policy",
            help="Exhaustive local policy for emoji names, order and packing.",
            rich_help_panel="Advanced workflows",
        ),
    ] = None,
    source_snapshot: Annotated[
        Path | None,
        typer.Option(
            help="Use a saved layout document with --policy; preserve its source.",
            rich_help_panel="Advanced workflows",
        ),
    ] = None,
    details: Annotated[
        bool, typer.Option("--details", help="List every proposed position change.")
    ] = False,
):
    """Preview a deterministic plan and save it locally. Never write to a phone."""
    settings = ctx.obj
    if smart and cloud:
        raise ValueError("Choose --smart (Apple only) or --cloud (OpenRouter opt-in).")
    if cloud and no_network:
        raise ValueError("--no-network blocks --cloud. No data was sent.")
    if from_review and (smart or cloud):
        raise ValueError("--from-review reuses saved advice locally; omit model flags.")
    if source_plan and (not from_review or fixture or udid):
        raise ValueError(
            "--source-plan requires --from-review and cannot mix with --fixture/--udid."
        )
    if refresh_device and not (source_plan and from_review):
        raise ValueError("--refresh-device requires --source-plan and --from-review.")
    if policy_file and (
        smart or cloud or from_review or source_plan or refresh_device or existing_only
    ):
        raise ValueError("--policy is a separate offline mode; omit other planning modes.")
    if source_snapshot and (not policy_file or fixture or udid):
        raise ValueError(
            "--source-snapshot requires --policy and cannot mix with --fixture/--udid."
        )
    config = (
        replace(settings.config, create_folders=False, compact_folders=False)
        if existing_only
        else settings.config
    )
    if source_snapshot:
        layout = layout_from_document(read_json(source_snapshot.expanduser()), fixture=False)
    elif source_plan:
        saved = Plan.from_dict(read_json(source_plan.expanduser()))
        layout = saved.before
        config = replace(config, pins=tuple(sorted(set(config.pins) | set(saved.pins))))
    else:
        layout = read_layout(fixture, udid)
    if policy_file:
        proposal, audit = build_policy_plan(layout, read_json(policy_file.expanduser()), config)
        write_json(settings.root / "reviews/domain-policy-audit.json", audit)
    elif from_review:
        saved_review = read_json(from_review.expanduser())
        proposal = (
            refresh_reorganization(layout, read_layout(None, None), saved_review, config)
            if refresh_device
            else build_reorganization(layout, saved_review, config)
        )
    else:
        proposal = build_plan(layout, config)
    if smart or cloud:
        if cloud:
            write_text(
                "Cloud opt-in: unresolved app names/IDs and folder labels/categories "
                "will be sent to OpenRouter and its routed provider.",
                err=True,
            )
        provider = cloud_provider(config) if cloud else None
        proposal = refine_plan(proposal, config, settings.root, cloud=cloud, provider=provider)
    if device_ready:
        proposal = prepare_device_plan(proposal)
    data = proposal.to_dict(config)
    if (smart or cloud) and not proposal.smart_info.get("available"):
        data["notice"] = proposal.smart_info["detail"] + " Rules retained."
    path = settings.root / (
        "plans/domain-policy.json"
        if policy_file
        else ("plans/reorganization.json" if from_review else "plans/latest.json")
    )
    write_json(path, data)
    select_plan(settings.root, path)
    if json_output:
        emit({**data, "saved_to": str(path)})
    else:
        write_text(
            render_plan(
                proposal,
                score_layout(proposal.before, config),
                score_layout(proposal.after, config),
                details=details,
            )
        )
        write_text(f"\nPlan saved: {path}")
        write_text("Next: sborganize show --after")


@app.command(rich_help_panel="Inspect and plan")
def review(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    json_output: JsonOutput = False,
    from_plan: Annotated[
        Path | None, typer.Option(help="Review the original snapshot in a saved plan; no USB read.")
    ] = None,
    cloud: Annotated[
        bool,
        typer.Option("--cloud", help="Send ALL app names/IDs and current folders to OpenRouter."),
    ] = False,
    no_network: Annotated[
        bool, typer.Option("--no-network", help="Reject cloud requests.")
    ] = False,
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Request all cloud batches again; bypass cache.")
    ] = False,
    recheck: Annotated[
        Path | None, typer.Option(help="Revalidate a saved report's original candidates locally.")
    ] = None,
):
    """Review every app, including grouped apps. Save advice, never an apply plan."""
    if cloud and no_network:
        raise ValueError("--no-network blocks --cloud. No data was sent.")
    if refresh and not cloud:
        raise ValueError("--refresh requires --cloud.")
    if recheck and (cloud or refresh):
        raise ValueError("--recheck is local; omit --cloud/--refresh.")
    if from_plan and (fixture or udid):
        raise ValueError("Choose --from-plan, --fixture or --udid.")
    config = ctx.obj.config
    if from_plan:
        saved = Plan.from_dict(read_json(from_plan.expanduser()))
        layout = saved.before
        config = replace(config, pins=tuple(sorted(set(config.pins) | set(saved.pins))))
    else:
        layout = read_layout(fixture, udid)
    if cloud:
        write_text(
            "Cloud opt-in: ALL Home Screen app names/IDs, current folder membership and "
            "folder summaries will be sent to OpenRouter and its routed provider. "
            "No raw layout or device identity. Complete cached batches are reused.",
            err=True,
        )

    def progress(index, total, cached):
        write_text(
            f"Review batch {index}/{total} · {'cached' if cached else 'OpenRouter'}", err=True
        )

    report = (
        recheck_report(layout, read_json(recheck.expanduser()), config)
        if recheck
        else review_layout(
            layout,
            config,
            ctx.obj.root,
            cloud=cloud,
            provider_factory=lambda: cloud_provider(config),
            refresh=refresh,
            progress=progress if cloud else None,
        )
    )
    path = ctx.obj.root / ("reviews/rechecked.json" if recheck else "reviews/latest.json")
    write_json(path, report)
    if json_output:
        emit({**report, "saved_to": str(path)})
    else:
        write_text(render_review(report))
        write_text(f"\nReview saved: {path}")
        if from_plan:
            write_text("Source: saved pre-plan snapshot; current phone layout was not re-read.")
    if not report["complete"]:
        raise typer.Exit(1)


@app.command(rich_help_panel="Local files")
def backup(
    ctx: typer.Context, fixture: Fixture = None, udid: Udid = None, json_output: JsonOutput = False
):
    """Save the exact layout locally without rearranging anything."""
    layout = read_layout(fixture, udid)
    path = backup_layout(layout, ctx.obj.root)
    data = {"backup": str(path), "fingerprint": fingerprint(layout.raw)}
    emit(data) if json_output else write_text(f"Backup saved: {path}")


def simulation_destination(settings: Settings, fixture: Path, output: Path | None) -> Path:
    destination = (output or settings.root / "simulations/latest.json").expanduser()
    if destination.resolve() == fixture.expanduser().resolve():
        raise SafetyError("Output must differ from the source fixture; the original stays intact.")
    if any(
        destination.resolve().is_relative_to((settings.root / name).resolve())
        for name in ("backups", "plans")
    ):
        raise SafetyError("Simulation output cannot overwrite the backup or plan storage.")
    if destination.is_file():
        try:
            existing = read_json(destination)
        except (ValueError, UnicodeError):
            existing = None
        if isinstance(existing, dict) and (
            existing.get("kind") == "backup" or "source_state_plist" in existing
        ):
            raise SafetyError("Simulation output cannot overwrite a backup or plan document.")
    return destination


def confirm_simulation(yes: bool, backup_path: Path) -> bool:
    write_text(f"Backup saved: {backup_path}")
    return yes or typer.confirm(
        "Run the fixture round-trip and save the simulated result?", default=False
    )


def require_fixture(fixture: Path | None, experimental_write=False) -> Path | None:
    if fixture is None and not experimental_write:
        raise SafetyError(
            "Phone writes are disabled by default. Use --experimental-write for USB, "
            "or --fixture PATH to simulate apply/restore."
        )
    if fixture is not None and experimental_write:
        raise SafetyError("Choose fixture simulation or --experimental-write, not both.")
    return fixture


def confirm_phone(yes: bool, backup_path: Path) -> bool:
    write_text(f"Backup saved: {backup_path}")
    return yes or typer.confirm(
        "Write the unchanged layout to verify round-trip, then apply this preview to your iPhone?",
        default=False,
    )


@app.command(rich_help_panel="Write with confirmation")
def apply(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    experimental_write: Annotated[
        bool,
        typer.Option(
            "--experimental-write", help="Enable real USB writes through the mandatory safety gate."
        ),
    ] = False,
    plan_file: Annotated[
        Path | None, typer.Option("--plan", help="Plan JSON (default: latest).")
    ] = None,
    output: Annotated[Path | None, typer.Option(help="Save simulated layout here.")] = None,
    yes: Annotated[
        bool, typer.Option("--yes", help="Skip confirmation; keep all safety checks.")
    ] = False,
):
    """Apply a preview through backup, confirmation, unchanged round-trip and read-back."""
    fixture = require_fixture(fixture, experimental_write)
    settings = ctx.obj
    path = plan_file.expanduser() if plan_file else selected_plan(settings.root)
    proposal = Plan.from_dict(read_json(path))
    config = proposal.score_config(settings.config)
    validate_target(
        proposal.before, proposal.after, settings.config.pins, folder_edits=proposal.folder_edits
    )
    if fixture is None:
        if output:
            raise SafetyError("--output is for fixture simulations only.")
        if proposal.before.source != "usb" or not proposal.device_ready:
            raise SafetyError(
                "Generate a USB plan with --device-ready before enabling phone writes."
            )
        validate_wire_state(proposal.before.raw)
        validate_wire_state(proposal.after.raw)
    destination = simulation_destination(settings, fixture, output) if fixture else None
    if destination and destination.resolve() == path.resolve():
        raise SafetyError("Output cannot overwrite the plan.")
    write_text(
        render_plan(
            proposal,
            score_layout(proposal.before, config),
            score_layout(proposal.after, config),
            applying=True,
        )
    )

    async def run():
        selected = udid or (proposal.before.udid if fixture is None else None)
        async with open_device(fixture, selected, allow_write=experimental_write) as device:
            path = await apply_target(
                device,
                proposal.before,
                proposal.after,
                settings.root,
                lambda p: confirm_phone(yes, p) if fixture is None else confirm_simulation(yes, p),
                tuple(set(proposal.pins) | set(settings.config.pins)),
                folder_edits=proposal.folder_edits,
                progress=write_text,
            )
            if destination:
                write_json(destination, layout_document(await device.read()))
            return path

    backup_path = asyncio.run(run())
    write_text(
        f"Simulation verified. No phone writes.\nLayout saved: {destination}"
        if destination
        else f"Phone layout verified.\nUndo backup: {backup_path}"
    )


@app.command(rich_help_panel="Write with confirmation")
def restore(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    experimental_write: Annotated[
        bool,
        typer.Option(
            "--experimental-write",
            help="Enable real USB restore through the mandatory safety gate.",
        ),
    ] = False,
    backup_file: Annotated[
        Path | None, typer.Option("--backup", help="Backup JSON (default: newest).")
    ] = None,
    output: Annotated[Path | None, typer.Option(help="Save restored simulation here.")] = None,
    yes: Annotated[
        bool, typer.Option("--yes", help="Skip confirmation; keep all safety checks.")
    ] = False,
):
    """Restore a backup through the same safety gate."""
    fixture = require_fixture(fixture, experimental_write)
    settings = ctx.obj
    if fixture is None and output:
        raise SafetyError("--output is for fixture simulations only.")
    destination = (
        simulation_destination(
            settings,
            fixture,
            output or settings.root / "simulations/restored.json",
        )
        if fixture
        else None
    )

    async def run():
        async with open_device(fixture, udid, allow_write=experimental_write) as device:
            current = await device.read()
            path = backup_file or latest_backup(settings.root, device.udid, device.source)
            if destination and destination.resolve() == path.resolve():
                raise SafetyError("Output cannot overwrite the backup.")
            target = load_backup(path)
            if fixture is None:
                validate_wire_state(current.raw)
                validate_wire_state(target.raw)
            write_text(
                f"Restore preview · {len(current.pages)} → {len(target.pages)} pages\n"
                f"From backup: {path}"
            )
            await apply_target(
                device,
                current,
                target,
                settings.root,
                lambda p: confirm_phone(yes, p) if fixture is None else confirm_simulation(yes, p),
                settings.config.pins,
                restore=True,
                progress=write_text,
            )
            if destination:
                write_json(destination, layout_document(await device.read()))

    asyncio.run(run())
    write_text(
        f"Restore simulation verified. No phone writes.\nLayout saved: {destination}"
        if destination
        else "Restored phone layout verified."
    )


@app.command(rich_help_panel="Start here")
def doctor(
    ctx: typer.Context,
    fixture: Fixture = None,
    udid: Udid = None,
    json_output: JsonOutput = False,
    smart: Annotated[
        bool, typer.Option("--smart", help="Probe Apple on-device model availability.")
    ] = False,
):
    """Check fixture or trusted USB read access. Never writes."""
    checks = {
        "version": __version__,
        "planning": "offline rules",
        "smart": "Apple → rules; use --smart to probe",
        "phone_writes": "experimental; explicit --experimental-write required",
    }
    if smart:
        checks["apple"] = AppleProvider(ctx.obj.root).probe()
    try:
        layout = read_layout(fixture, udid)
        checks.update({"ready": True, "source": layout.source, "apps": len(layout.apps())})
    except (DeviceError, TimeoutError, ValueError, OSError) as exc:
        checks.update(
            {"ready": False, "detail": str(exc) or "USB read timed out after 15 seconds."}
        )
    if json_output:
        emit(checks)
    else:
        write_text(
            f"sborganize {__version__}\n\nPlanning    offline rules\n"
            "Phone writes opt-in (experimental)"
        )
        write_text("Read access ready." if checks["ready"] else checks["detail"])
        if smart:
            write_text(checks["apple"]["detail"])
    if not checks["ready"]:
        raise typer.Exit(1)


def main():
    from contextlib import nullcontext

    try:
        with plain_environment() if "NO_COLOR" in os.environ else nullcontext():
            app()
    except TimeoutError:
        write_text(
            "Error: USB read timed out. Unlock the phone and check trust in Finder.", err=True
        )
        raise SystemExit(1) from None
    except (DeviceError, SafetyError, ValueError, OSError, KeyError, TypeError) as exc:
        write_text(f"Error: {exc}", err=True)
        raise SystemExit(1) from None
