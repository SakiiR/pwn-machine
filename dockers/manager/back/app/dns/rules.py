from functools import wraps
import time
from ..utils import registerQuery, registerMutation, createType, dnsname, create_node_id


def with_dns_http(f):
    @wraps(f)
    def wrapper(obj, info, *args, **kwargs):
        dns_http = info.context["request"].state.dns_http
        return f(obj, info, *args, **kwargs, dns_http=dns_http)

    return wrapper


DnsRule = createType("DnsRule")


@registerQuery("dnsRules")
@with_dns_http
async def get_dns_rules(*_, dns_http):
    return await dns_http.get_rules()


@DnsRule.field("nodeId")
def resolve_nodeid(rule, *_):
    return create_node_id("DNS_RULE", rule["zone"], rule["name"], rule["type"])


DnsRecord = createType("DnsRecord")


@DnsRecord.field("enabled")
def resolve_enabled(record, *_):
    return not record["disabled"]


@registerMutation("createDnsRule")
@with_dns_http
async def create_dns_rule_mutation(*_, dns_http, input):
    zone = input["zone"]
    name = input["name"]
    type = input["type"]
    ttl = input["ttl"]
    records = input["records"]
    return await dns_http.create_rule(zone, name, type, ttl, records)


@registerMutation("deleteDnsRule")
@with_dns_http
async def delete_dns_rule_mutation(*_, dns_http, nodeId):
    return await dns_http.delete_rule(nodeId)