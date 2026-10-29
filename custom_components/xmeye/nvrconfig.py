"""The NVR's own configuration for the settings page: read and write the
config tree, network, time, users, disks and reboot.

Stored passwords never leave the server: they are replaced by SECRET when
read, and a SECRET sent back keeps the value the NVR has.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Any

import voluptuous as vol

from .commands import APIError, Services, _nvr, command
from .dvrip import RET_OK, DVRIPClient, DVRIPError, sofia_hash

SECRET = "•" * 8
# PassWord, Password, DDNSKey, ARSPKey, Wi-Fi Key
SECRET_KEY = re.compile(r"(pass(word)?|key)$", re.I)
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9.]*(\.\[\d+\])?$")
# what the settings page may change (NetWork.NetCommon goes through network_set)
WRITABLE = re.compile(
    r"^(General\.(General|Location|AutoMaintain)|System\.TimeZone"
    r"|NetWork\.(NetDHCP|NetDNS|NetNTP|Upnp|RTSP|Nat|NetEmail|PMS|NetIPFilter|OnlineUpgrade|NetFTP"
    r"|NetDDNS|DigManagerShow|IPAdaptive)"
    r"|NetWork\.RemoteDeviceV3\.\[\d+\]|AVEnc\.VideoWidget\.\[\d+\]|Camera\.Param\.\[\d+\]"
    r"|(Record|ExtRecord)\.\[\d+\]"
    r"|Detect\.(MotionDetect|BlindDetect|LossDetect|FaceDetection|CarShapeDetection)\.\[\d+\]"
    r"|Alarm\.IPCAlarm\.\[\d+\]|Storage\.Storage(NotExist|Failure|LowSpace)"
    r"|fVideo\.(Volume\.\[\d+\]|GUISet|Tour)|Snap)$"
)

MSG_TITLE_SET = 1046
MSG_TIME_QUERY = 1452
MSG_SYSTEM = 1450  # OPMachine, OPTimeSetting
MSG_DISK = 1460
MSG_AUTHORITIES = 1470
MSG_USERS = 1472
MSG_GROUPS = 1474
MSG_USER_ADD = 1482
MSG_USER_MODIFY = 1484
MSG_USER_DELETE = 1486
MSG_PASSWORD = 1488
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def hide_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: SECRET if SECRET_KEY.search(k) and isinstance(v, str) and v else hide_secrets(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [hide_secrets(v) for v in value]
    return value


def keep_secrets(new: Any, old: Any) -> Any:
    """`new` with every SECRET replaced by the value at the same place in `old`."""
    if new == SECRET:
        return old
    if isinstance(new, dict) and isinstance(old, dict):
        return {k: keep_secrets(v, old.get(k)) for k, v in new.items()}
    if isinstance(new, list) and isinstance(old, list):
        return [keep_secrets(v, old[i] if i < len(old) else None) for i, v in enumerate(new)]
    return new


def ip_from_hex(value: str) -> str:
    """The NVR writes IPv4 addresses as little-endian hex: 0x6401A8C0 = 192.168.1.100."""
    n = int(value, 16)
    return ".".join(str((n >> shift) & 255) for shift in (0, 8, 16, 24))


async def _request(client: DVRIPClient, msg_id: int, name: str, body: Any = None) -> dict[str, Any]:
    try:
        reply = await client.query(msg_id, name, body)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    if reply.get("Ret") not in RET_OK:
        raise APIError(f"The NVR refused {name or 'the request'} (code {reply.get('Ret')})")
    return reply


async def _get(client: DVRIPClient, name: str) -> Any:
    try:
        return await client.config_get(name)
    except DVRIPError as err:
        raise APIError(str(err)) from err


# read-only requests for diagnostics: info, config, ability, time
QUERY_MESSAGES = {1020, 1042, 1048, 1360, 1452}


@command(
    "query",
    {vol.Required("entry_id"): str, vol.Required("msg"): vol.In(QUERY_MESSAGES), vol.Required("name"): str},
    admin=True,
)
async def query(svc: Services, msg: dict[str, Any]) -> Any:
    """Read anything the NVR exposes (stored passwords hidden)."""
    try:
        reply = await _nvr(svc, msg["entry_id"]).client.query(msg["msg"], msg["name"])
    except DVRIPError as err:
        raise APIError(str(err)) from err
    return hide_secrets(reply)


@command(
    "config",
    {vol.Required("entry_id"): str, vol.Required("names"): [vol.Match(NAME)]},
    admin=True,
)
async def config(svc: Services, msg: dict[str, Any]) -> Any:
    """Several configs at once; one that fails is {"error": …}."""
    client = _nvr(svc, msg["entry_id"]).client
    out: dict[str, Any] = {}
    for name in msg["names"]:
        try:
            out[name] = hide_secrets(await client.config_get(name))
        except DVRIPError as err:
            out[name] = {"error": str(err)}
    return out


@command(
    "config_set",
    {vol.Required("entry_id"): str, vol.Required("name"): vol.Match(WRITABLE), vol.Required("value"): object},
    admin=True,
)
async def config_set(svc: Services, msg: dict[str, Any]) -> Any:
    data = _nvr(svc, msg["entry_id"])
    old = await _get(data.client, msg["name"])
    value = keep_secrets(msg["value"], old)
    try:
        await data.client.config_set(msg["name"], value)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    if msg["name"].startswith(("Record.", "Detect.")):
        data.invalidate()
    return hide_secrets(await _get(data.client, msg["name"]))


@command(
    "network_set",
    {
        vol.Required("entry_id"): str,
        vol.Required("value"): dict,
        vol.Optional("dhcp"): bool,
    },
    admin=True,
)
async def network_set(svc: Services, msg: dict[str, Any]) -> Any:
    """The NVR's address, ports and DHCP. Moves our own connection to the new address."""
    data = _nvr(svc, msg["entry_id"])
    client = data.client
    old = await _get(client, "NetWork.NetCommon")
    value = keep_secrets(msg["value"], old)
    try:
        host = ip_from_hex(value["HostIP"])
        ipaddress.IPv4Address(host)
        ip_from_hex(value["Submask"])
        ip_from_hex(value["GateWay"])
        port = int(value["TCPPort"])
    except (KeyError, TypeError, ValueError) as err:
        raise APIError(f"Invalid address: {err}") from err
    try:
        if "dhcp" in msg:
            dhcp = await client.config_get("NetWork.NetDHCP")
            for item in dhcp:
                if item.get("Interface") == "eth0":
                    item["Enable"] = msg["dhcp"]
            await client.config_set("NetWork.NetDHCP", dhcp)
        await client.config_set("NetWork.NetCommon", value)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    moved = host != data.host or port != data.client.port
    if moved and svc.credentials_changed:
        await svc.credentials_changed(msg["entry_id"], {"host": host, "port": port})
    return {"host": host, "port": port, "moved": moved}


@command("titles_set", {vol.Required("entry_id"): str, vol.Required("titles"): {vol.Coerce(int): str}}, admin=True)
async def titles_set(svc: Services, msg: dict[str, Any]) -> Any:
    """Channel names on the NVR (1-based channel → name)."""
    client = _nvr(svc, msg["entry_id"]).client
    titles = await client.channel_titles()
    for channel, name in msg["titles"].items():
        if not 1 <= channel <= len(titles):
            raise APIError("unknown channel")
        titles[channel - 1] = name.strip()
    await _request(client, MSG_TITLE_SET, "ChannelTitle", titles)
    return await client.channel_titles()


@command("time", {vol.Required("entry_id"): str}, admin=True)
async def time_get(svc: Services, msg: dict[str, Any]) -> Any:
    client = _nvr(svc, msg["entry_id"]).client
    reply = await _request(client, MSG_TIME_QUERY, "OPTimeQuery")
    return {"nvr": reply.get("OPTimeQuery"), "here": svc.now().strftime(TIME_FORMAT)}


@command("time_set", {vol.Required("entry_id"): str, vol.Optional("time"): str}, admin=True)
async def time_set(svc: Services, msg: dict[str, Any]) -> Any:
    """Set the NVR's clock, by default to this computer's."""
    client = _nvr(svc, msg["entry_id"]).client
    when = msg.get("time") or svc.now().strftime(TIME_FORMAT)
    try:
        datetime.strptime(when, TIME_FORMAT)
    except ValueError as err:
        raise APIError("Use YYYY-MM-DD HH:MM:SS") from err
    await _request(client, MSG_SYSTEM, "OPTimeSetting", when)
    return await time_get(svc, msg)


@command("reboot", {vol.Required("entry_id"): str}, admin=True)
async def reboot(svc: Services, msg: dict[str, Any]) -> Any:
    client = _nvr(svc, msg["entry_id"]).client
    await _request(client, MSG_SYSTEM, "OPMachine", {"Action": "Reboot"})
    return None


@command(
    "disk_format",
    {vol.Required("entry_id"): str, vol.Required("disk"): int, vol.Required("partition"): int},
    admin=True,
)
async def disk_format(svc: Services, msg: dict[str, Any]) -> Any:
    """Erase a partition: all recordings on it are gone."""
    data = _nvr(svc, msg["entry_id"])
    body = {"Action": "Clear", "SerialNo": msg["disk"], "PartNo": msg["partition"], "Type": "Data"}
    await _request(data.client, MSG_DISK, "OPStorageManager", body)
    data.invalidate()
    return None


# --- users ------------------------------------------------------------------


# everything else in a user (Password, PasswordV2, …) is a hash of the password
USER_PUBLIC = ("Name", "Group", "Memo", "AuthorityList", "Reserved", "Sharable")


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {k: user[k] for k in USER_PUBLIC if k in user}


@command("users", {vol.Required("entry_id"): str}, admin=True)
async def users(svc: Services, msg: dict[str, Any]) -> Any:
    data = _nvr(svc, msg["entry_id"])
    client = data.client
    user_list = (await _request(client, MSG_USERS, "")).get("Users") or []
    groups = (await _request(client, MSG_GROUPS, "")).get("Groups") or []
    rights = (await _request(client, MSG_AUTHORITIES, "")).get("AuthorityList") or []
    return {
        "users": [_public_user(u) for u in user_list],
        "groups": groups,
        "rights": rights,
        "me": data.username,
    }


USER_FIELDS = {
    vol.Required("name"): vol.All(str, vol.Length(min=1, max=31)),
    vol.Optional("group", default="user"): str,
    vol.Optional("memo", default=""): str,
    vol.Optional("rights"): [str],
    vol.Optional("sharable", default=True): bool,
}


@command(
    "user_add",
    {vol.Required("entry_id"): str, vol.Required("password"): str, **USER_FIELDS},
    admin=True,
)
async def user_add(svc: Services, msg: dict[str, Any]) -> Any:
    client = _nvr(svc, msg["entry_id"]).client
    rights = msg.get("rights")
    if rights is None:
        groups = (await _request(client, MSG_GROUPS, "")).get("Groups") or []
        group = next((g for g in groups if g.get("Name") == msg["group"]), {})
        rights = group.get("AuthorityList") or []
    user = {
        "AuthorityList": rights,
        "Group": msg["group"],
        "Memo": msg["memo"],
        "Name": msg["name"],
        "Password": sofia_hash(msg["password"]),
        "Reserved": False,
        "Sharable": msg["sharable"],
    }
    await _request(client, MSG_USER_ADD, "User", user)
    return await users(svc, msg)


@command(
    "user_modify",
    {
        vol.Required("entry_id"): str,
        vol.Required("user"): str,
        vol.Optional("group"): str,
        vol.Optional("memo"): str,
        vol.Optional("rights"): [str],
        vol.Optional("sharable"): bool,
    },
    admin=True,
)
async def user_modify(svc: Services, msg: dict[str, Any]) -> Any:
    client = _nvr(svc, msg["entry_id"]).client
    current = (await _request(client, MSG_USERS, "")).get("Users") or []
    user = next((u for u in current if u.get("Name") == msg["user"]), None)
    if user is None:
        raise APIError("unknown user")
    for key, field_name in (("group", "Group"), ("memo", "Memo"), ("rights", "AuthorityList"), ("sharable", "Sharable")):
        if key in msg:
            user[field_name] = msg[key]
    await _send(client, MSG_USER_MODIFY, {"Name": "User", "User": user, "UserName": msg["user"]})
    return await users(svc, msg)


async def _send(client: DVRIPClient, msg_id: int, payload: dict[str, Any]) -> None:
    try:
        reply = await client.request(msg_id, payload)
    except DVRIPError as err:
        raise APIError(str(err)) from err
    if reply.get("Ret") not in RET_OK:
        raise APIError(f"The NVR refused the change (code {reply.get('Ret')})")


@command("user_delete", {vol.Required("entry_id"): str, vol.Required("user"): str}, admin=True)
async def user_delete(svc: Services, msg: dict[str, Any]) -> Any:
    data = _nvr(svc, msg["entry_id"])
    if msg["user"] == data.username:
        raise APIError("This is the user the app logs in with.")
    await _request(data.client, MSG_USER_DELETE, msg["user"])
    return await users(svc, msg)


@command(
    "user_password",
    {
        vol.Required("entry_id"): str,
        vol.Required("user"): str,
        vol.Required("old"): str,
        vol.Required("new"): str,
    },
    admin=True,
)
async def user_password(svc: Services, msg: dict[str, Any]) -> Any:
    data = _nvr(svc, msg["entry_id"])
    payload = {
        "EncryptType": "MD5",
        "NewPassWord": sofia_hash(msg["new"]),
        "PassWord": sofia_hash(msg["old"]),
        "UserName": msg["user"],
    }
    await _send(data.client, MSG_PASSWORD, payload)
    if msg["user"] == data.username and svc.credentials_changed:
        await svc.credentials_changed(msg["entry_id"], {"password": msg["new"]})
    return None
