import asyncio
import sys
from importlib.metadata import PackageNotFoundError
from types import ModuleType, SimpleNamespace

import pytest

from sborganize.device import DeviceError, connect_usb


@pytest.fixture
def usb_stubs(monkeypatch, layout):
    events = []

    class BackendError(Exception):
        pass

    class Lockdown:
        udid = "usb-demo"

        async def __aenter__(self):
            events.append("lockdown-enter")
            return self

        async def __aexit__(self, *args):
            events.append("lockdown-close")

    class Service:
        def __init__(self, lockdown):
            pass

        async def __aenter__(self):
            events.append("service-enter")
            return self

        async def __aexit__(self, *args):
            events.append("service-close")

        async def get_icon_state(self):
            events.append("read")
            return layout.raw

        async def set_icon_state(self, raw):
            pytest.fail("Read adapter must never write")

    async def create(**kwargs):
        events.append(kwargs)
        return Lockdown()

    usb = SimpleNamespace(is_usb=True, serial="usb-demo", matches_udid=lambda x: x == "usb-demo")
    wifi = SimpleNamespace(is_usb=False, serial="wifi-demo")
    devices = [usb, wifi]

    async def list_devices():
        return devices

    modules = {
        "pymobiledevice3": {},
        "pymobiledevice3.exceptions": {"PyMobileDevice3Exception": BackendError},
        "pymobiledevice3.lockdown": {"create_using_usbmux": create},
        "pymobiledevice3.services": {},
        "pymobiledevice3.services.springboard": {"SpringBoardServicesService": Service},
        "pymobiledevice3.usbmux": {"list_devices": list_devices},
    }
    for name, attributes in modules.items():
        module = ModuleType(name)
        vars(module).update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr("sborganize.device.version", lambda name: "11.50.2")
    return events, devices, BackendError, Service


def test_usb_read_filters_wifi_disables_autopair_and_closes(usb_stubs, layout):
    events, _, _, _ = usb_stubs

    async def read():
        async with connect_usb("usb-demo") as device:
            result = await device.read()
            assert result.raw == layout.raw
            assert result.udid == "usb-demo"
            assert result.source == "usb"

    asyncio.run(read())
    assert events == [
        {"serial": "usb-demo", "connection_type": "USB", "autopair": False},
        "lockdown-enter",
        "service-enter",
        "read",
        "service-close",
        "lockdown-close",
    ]


def test_usb_missing_or_ambiguous_device_never_opens_service(usb_stubs):
    events, devices, _, _ = usb_stubs

    async def read(udid=None):
        async with connect_usb(udid):
            pytest.fail("Unexpected connection")

    with pytest.raises(DeviceError, match="No matching"):
        asyncio.run(read("missing"))
    devices.append(devices[0])
    with pytest.raises(DeviceError, match="More than one"):
        asyncio.run(read())
    assert not events


def test_usb_failure_translates_and_closes_services(usb_stubs, monkeypatch):
    events, _, BackendError, Service = usb_stubs

    async def fail(self):
        raise BackendError("locked")

    monkeypatch.setattr(Service, "get_icon_state", fail)

    async def read():
        async with connect_usb() as device:
            await device.read()

    with pytest.raises(DeviceError, match="Trust This Computer"):
        asyncio.run(read())
    assert events[-2:] == ["service-close", "lockdown-close"]


def test_missing_optional_dependency_is_actionable(monkeypatch):
    def missing(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr("sborganize.device.version", missing)

    async def read():
        async with connect_usb():
            pytest.fail("Unexpected connection")

    with pytest.raises(DeviceError, match="optional"):
        asyncio.run(read())


def test_usb_service_permission_denial_does_not_misdiagnose_pairing(usb_stubs, monkeypatch):
    _, _, _, service = usb_stubs

    async def denied(self):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(service, "get_icon_state", denied)

    async def read():
        async with connect_usb() as device:
            await device.read()

    with pytest.raises(DeviceError, match="denied access to the USB service") as error:
        asyncio.run(read())
    assert "Trust This Computer" not in str(error.value)
