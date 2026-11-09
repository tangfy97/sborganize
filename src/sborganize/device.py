"""USB read adapter and an isolated in-memory fixture device."""

import asyncio
import errno
from contextlib import AsyncExitStack, asynccontextmanager
from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version

from sborganize.model import Layout


class DeviceError(RuntimeError):
    pass


class FixtureDevice:
    def __init__(self, layout: Layout):
        self.layout = layout
        self.udid = layout.udid
        self.source = "fixture"

    async def read(self) -> Layout:
        return Layout.from_raw(self.layout.raw, self.udid, self.source)

    async def write(self, raw: list) -> None:
        self.layout = Layout.from_raw(deepcopy(raw), self.udid, self.source)


class USBDevice:
    source = "usb"
    settle_timeout = 5.0

    def __init__(self, lockdown, service, *, allow_write=False):
        self.lockdown = lockdown
        self.service = service
        self.udid = lockdown.udid
        self.allow_write = allow_write

    async def read(self) -> Layout:
        raw = await asyncio.wait_for(self.service.get_icon_state(), timeout=15)
        return Layout.from_raw(raw, self.udid, self.source)

    async def write(self, raw: list) -> None:
        if not self.allow_write:
            raise DeviceError("Phone writes are disabled for this connection.")
        from sborganize.wire import validate_wire_state

        validate_wire_state(raw)
        await asyncio.wait_for(self.service.set_icon_state(raw), timeout=15)


@asynccontextmanager
async def connect_usb(udid: str | None = None, *, allow_write=False):
    try:
        installed = version("pymobiledevice3")
    except PackageNotFoundError as exc:
        raise DeviceError('USB support is optional. Install: pip install -e ".[device]"') from exc
    if installed != "11.50.2":
        raise DeviceError('This prototype needs pymobiledevice3==11.50.2; install ".[device]".')
    try:
        from pymobiledevice3.exceptions import PyMobileDevice3Exception
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.springboard import SpringBoardServicesService
        from pymobiledevice3.usbmux import list_devices
    except ImportError as exc:
        raise DeviceError(
            'USB dependencies are incomplete. Install: pip install -e ".[device]"'
        ) from exc

    try:
        async with AsyncExitStack() as stack:
            async with asyncio.timeout(15):
                devices = [d for d in await list_devices() if d.is_usb]
                if udid:
                    devices = [d for d in devices if d.matches_udid(udid)]
                if not devices:
                    raise DeviceError(
                        "No matching USB device. Connect, unlock, and Trust This Computer."
                    )
                if len(devices) > 1:
                    raise DeviceError("More than one USB device. Select one with --udid.")
                lockdown = await create_using_usbmux(
                    serial=devices[0].serial,
                    connection_type="USB",
                    autopair=False,
                )
                await stack.enter_async_context(lockdown)
                service = await stack.enter_async_context(SpringBoardServicesService(lockdown))
            yield USBDevice(lockdown, service, allow_write=allow_write)
    except (PyMobileDevice3Exception, OSError) as exc:
        if isinstance(exc, PermissionError) or getattr(exc, "errno", None) in (
            errno.EACCES,
            errno.EPERM,
        ):
            raise DeviceError(
                "macOS denied access to the USB service. Run from a local terminal "
                "with USB access. See sborganize guide safety."
            ) from exc
        raise DeviceError(
            "USB operation failed. Unlock your iPhone and Trust This Computer in Finder. "
            "Pair with `python -m pymobiledevice3 lockdown pair` if needed. "
            "See docs/research/springboard-icon-state.md."
        ) from exc
