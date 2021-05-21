from contextlib import asynccontextmanager, contextmanager
import aiohttp
import re
import asyncio
import logging
import time
from app.utils.cached import cacheMethodForQuery, no_cache
from fnmatch import fnmatch
from app.utils import validate_node_id

ZONE_MARKER = "DNS_ZONE"

logger = logging.getLogger("uvicorn")


def log(msg):
    logger.info(f"[{__name__}] {msg}")


regex_soa = re.compile(
    r"^\s*(?P<nameserver>\S+)\s+(?P<postmaster>\S+)\s+(?P<serial>\d+)\s+(?P<refresh>\S+)\s+(?P<retry>\S+)\s+(?P<expire>\S+)\s+(?P<ttl>\S+)\s*$"
)


def soa_to_string(soa):
    nameserver = soa["nameserver"]
    postmaster = soa["postmaster"]
    refresh = soa["refresh"]
    retry = soa["retry"]
    expire = soa["expire"]
    ttl = soa["ttl"]
    serial = int(time.time())
    return f"{nameserver} {postmaster} {serial} {refresh} {retry} {expire} {ttl}"


def rrset_match(name, type):
    def do_match(rrset):
        return rrset["name"] == name and rrset["type"] == type

    return do_match


def find_record(rrsets, name, type):
    try:
        return next(
            filter(
                rrset_match(name, type),
                rrsets,
            )
        )
    except StopIteration:
        return None


def string_to_soa(str):
    groups = regex_soa.match(str)
    return {
        "nameserver": groups["nameserver"],
        "postmaster": groups["postmaster"],
        "expire": int(groups["expire"]),
        "refresh": int(groups["refresh"]),
        "retry": int(groups["retry"]),
        "ttl": int(groups["ttl"]),
        "serial": int(groups["serial"]),
    }


def get_soa(zone):
    for rule in zone["rrsets"]:
        if rule["type"] == "SOA":
            return string_to_soa(rule["records"][0]["content"])
    return None


class PowerdnsHTTPApi:
    def __init__(self, root, session):
        self.root = root
        self.session = session

    @classmethod
    def create(cls, root, session):
        cls._instance = cls(root, session)
        return cls._instance

    @classmethod
    def get_instance(cls):
        return cls._instance

    async def post(self, path, data):
        log(f"API POST {path}")
        full_path = f"{self.root.rstrip('/')}/{path.lstrip('/')}"
        await self.session.post(full_path, json=data)

    async def patch(self, path, data):
        log(f"API PATCH {path}")
        full_path = f"{self.root.rstrip('/')}/{path.lstrip('/')}"
        r = await self.session.patch(full_path, json=data)
        if r.status != 204:
            error = await r.json()
            raise Exception(error["error"])
        return r

    async def delete(self, path):
        log(f"API DELETE {path}")
        full_path = f"{self.root.rstrip('/')}/{path.lstrip('/')}"
        return await self.session.delete(full_path)

    @cacheMethodForQuery
    async def get(self, path):
        log(f"API GET {path}")

        full_path = f"{self.root.rstrip('/')}/{path.lstrip('/')}"

        async with self.session.get(full_path) as response:
            return await response.json()

    async def get_zone(self, zone_id):
        try:
            return await self.get(f"/api/v1/servers/localhost/zones/{zone_id}")
        except Exception as e:
            print("ERROR", e)
            return None

    async def get_zones(self):
        zones = await self.get("/api/v1/servers/localhost/zones")

        return [z for z in zones if z["name"] != "."]

    async def get_soa(self, zone_id):
        info = await self.get_zone(zone_id)
        soa = get_soa(info)
        return soa

    async def get_rules_for_zone(self, zone_id):
        info = await self.get_zone(zone_id)
        return [{**z, "zone": info["name"]} for z in info["rrsets"]]

    async def get_rules(self):
        rules = []
        for zone in await self.get_zones():
            rules += await self.get_rules_for_zone(zone["id"])

        return rules

    async def get_rule(self, zone, name, type):
        rules = await self.get_rules_for_zone(zone)
        return find_record(rules, name, type)

    async def update_soa(self, zone_name, soa):
        zone_info = await self.get_zone(zone_name)
        rule = find_record(zone_info["rrsets"], zone_name, "SOA")
        if rule is None:
            raise Exception(f"Rule {zone} with type SOA is not found on {zone}.")

        content = soa_to_string(soa)
        rule["records"] = [{"content": content, "disabled": False}]
        rule["changetype"] = "REPLACE"
        rule["ttl"] = soa["ttl"]
        url = f"/api/v1/servers/localhost/zones/{zone_info['name']}"
        return await self.patch(url, {"rrsets": [rule]})

    # ZONES

    async def create_zone(self, name, soa):
        zone_info = await self.get_zone(name)
        if zone_info is not None:
            raise Exception("A zone with this name already exists.")

        content = soa_to_string(soa)
        rule = {
            "name": name,
            "type": "SOA",
            "records": [{"content": content, "disabled": False}],
            "ttl": soa["ttl"],
        }
        data = {
            "name": name,
            "nameservers": [soa["nameserver"]],
            "kind": "native",
            "rrsets": [rule],
            "soa_edit": "INCEPTION-EPOCH",
            "soa_edit_api": "INCEPTION-EPOCH",
        }
        r = await self.post("/api/v1/servers/localhost/zones", data)
        with no_cache():
            return await self.get_zone(name)

    async def update_zone(self, nodeId, soa):
        zone_name = validate_node_id(nodeId, "DNS_ZONE")[0]
        zone_info = await self.get_zone(zone_name)
        if zone_info is None:
            raise Exception("This zone doesn't exists.")
        await self.update_soa(zone_name, soa)
        return await self.get_zone(zone_name)

    async def delete_zone(self, nodeId):
        zone_name = validate_node_id(nodeId, "DNS_ZONE")[0]
        r = await self.delete(f"/api/v1/servers/localhost/zones/{zone_name}")
        return 200 <= r.status < 300

    # Rules

    async def rule_replace(self, zone, name, type, ttl, records):
        for record in records:
            record["disabled"] = not record["enabled"]
        rrset = {
            "name": name,
            "type": type,
            "changetype": "REPLACE",
            "ttl": ttl,
            "records": records,
        }

        await self.patch(f"/api/v1/servers/localhost/zones/{zone}", {"rrsets": [rrset]})
        return await self.get_rule(zone, name, type)

    async def enable_rule(self, nodeId, enabled):
        zone, name, type = validate_node_id(nodeId, "DNS_RULE")
        rule = await self.get_rule(zone, name, type)
        if rule is None:
            raise Exception("Rule not found")

        for record in rule["records"]:
            record["enabled"] = enabled
        return await self.rule_replace(zone, name, type, rule["ttl"], rule["records"])

    async def create_rule(self, zone_name, name, type, ttl, records):
        zone = await self.get_zone(zone_name)
        name = name
        if zone is None:
            raise Exception("Invalid zone")
        if find_record(zone["rrsets"], name, type):
            raise Exception(
                f"A rule with name={name} and type={type} already exist on {zone_name}"
            )
        return await self.rule_replace(zone["id"], name, type, ttl, records)

    async def update_rule(self, nodeId, ttl, records):
        zone, name, type = validate_node_id(nodeId, "DNS_RULE")
        return await self.rule_replace(zone, name, type, ttl, records)

    async def delete_rule(self, nodeId):
        zone, name, type = validate_node_id(nodeId, "DNS_RULE")
        rrset = {"name": name, "type": type, "changetype": "DELETE"}
        r = await self.patch(
            f"/api/v1/servers/localhost/zones/{zone}", {"rrsets": [rrset]}
        )
        return 200 <= r.status < 300


class PowerdnsRedisApi:
    def __init__(self, client, root):
        self.client = client
        self.root = root

    async def get_logs(self, domain="*", type="*", offset=0, count=20):
        c = self.client
        logs = []

        skipped = 0
        pos = 0
        while len(logs) < count:
            keys = await c.lrange("dns/logs", pos, pos + 10)
            if not keys:
                break
            for key in keys:
                log = await c.hgetall(key)
                # If log is empty that mean we reached expired logs
                if not log:
                    return logs

                if fnmatch(log["domain"], domain) and fnmatch(log["type"], type):
                    if skipped < offset:
                        skipped += 1
                    else:
                        logs.append(log)
                        if len(logs) == count:
                            return logs
            pos += len(keys)
        return logs
