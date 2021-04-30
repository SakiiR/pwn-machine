import json
import os
from ..utils import (
    registerQuery,
    registerMutation,
    createType,
    create_kv_resolver,
    createInterface,
    base64_encode,
    base64_decode,
)
from . import with_traefik_http, with_traefik_redis



def create_middleware(traefik_redis, name, type, settings):
    prefix = f"/http/middlewares/{name}/{type}"
    for k, v in settings_to_kv(input[key], prefix):
        traefik_redis.set(k, v)


def create_mutation_resolver(object_type, type_name):
    @registerMutation(f"create{object_type}")
    @with_traefik_redis
    async def resolve_create_mutation(*_, traefik_redis, input):
        middleware_name = input["name"]
        return await traefik_redis.create_middleware(
            middleware_name, type_name, input[type_name]
        )

    @registerMutation(f"update{object_type}")
    @with_traefik_redis
    async def resolve_update_mutation(*_, traefik_redis, nodeId, patch):
        return await traefik_redis.update_middleware(nodeId, type_name, patch)


def create_type_resolver(type):
    def resolver(*_):
        return type

    return resolver


middlewares = {
    "TraefikMiddlewareAddPrefix": "addPrefix",
    "TraefikMiddlewareBasicAuth": "basicAuth",
    "TraefikMiddlewareBuffering": "buffering",
    "TraefikMiddlewareChain": "chain",
    "TraefikMiddlewareCircuitBreaker": "circuitBreaker",
    "TraefikMiddlewareCompress": "compress",
    "TraefikMiddlewareContentType": "contentType",
    "TraefikMiddlewareDigestAuth": "digestAuth",
    "TraefikMiddlewareErrors": "errors",
    "TraefikMiddlewareForwardAuth": "forwardAuth",
    "TraefikMiddlewareHeaders": "headers",
    "TraefikMiddlewareIpWhiteList": "ipWhiteList",
    "TraefikMiddlewareInFlightReq": "inFlightReq",
    "TraefikMiddlewarePassTLSClientCert": "passTLSClientCert",
    "TraefikMiddlewareRateLimit": "rateLimit",
    "TraefikMiddlewareRedirectRegex": "redirectRegex",
    "TraefikMiddlewareRedirectScheme": "redirectScheme",
    "TraefikMiddlewareReplacePath": "replacePath",
    "TraefikMiddlewareReplacePathRegex": "replacePathRegex",
    "TraefikMiddlewareRetry": "retry",
    "TraefikMiddlewareStripPrefix": "stripPrefix",
    "TraefikMiddlewareStripPrefixRegex": "stripPrefixRegex",
}


for graphql_name, type_name in middlewares.items():
    MiddlewareType = createType(graphql_name)
    MiddlewareType.field("type")(create_type_resolver(type_name))
    create_mutation_resolver(graphql_name, type_name)

TraefikMiddlewareHeadersInfo = createType("TraefikMiddlewareHeadersInfo")

TraefikMiddlewareHeadersInfo.field("customRequestHeaders")(
    create_kv_resolver("customRequestHeaders")
)
TraefikMiddlewareHeadersInfo.field("customResponseHeaders")(
    create_kv_resolver("customResponseHeaders")
)
TraefikMiddlewareHeadersInfo.field("sslProxyHeaders")(
    create_kv_resolver("sslProxyHeaders")
)

TraefikMiddlewareRetryInfo = createType("TraefikMiddlewareRetryInfo")


@TraefikMiddlewareRetryInfo.field("initialInterval")
def resolve_initial_interval(info, *_):
    if "initialInterval" not in info:
        return None
    return info["initialInterval"] // 1_000_000_000


TraefikMiddlewareRateLimitInfo = createType("TraefikMiddlewareRateLimitInfo")


@TraefikMiddlewareRateLimitInfo.field("period")
def resolve_period(info, *_):
    if "period" not in info:
        return None
    return info["period"] // 1_000_000_000


TraefikMiddleware = createInterface("TraefikMiddleware")


@TraefikMiddleware.field("nodeId")
async def resolve_nodeid(middleware, *_):
    return base64_encode(["middleware", middleware["name"]], json=True)


@TraefikMiddleware.field("enabled")
async def enabled_resolver(middleware, *_):
    return middleware["status"] == "enabled"


@TraefikMiddleware.field("usedBy")
@with_traefik_http
async def resolver(middleware, *_, traefik_http):
    if "usedBy" not in middleware:
        return []
    return await traefik_http.get_routers_used_by(middleware["usedBy"], ("http",))


@TraefikMiddleware.type_resolver
def resolve_middleware_type(obj, *_):
    for graphql_name, type_name in middlewares.items():
        if type_name.lower() == obj["type"]:
            return graphql_name


@registerQuery("traefikMiddlewares")
@with_traefik_http
async def resolve_middlewares(*_, traefik_http):
    return await traefik_http.get_middlewares()


@registerMutation("traefikDeleteMiddleware")
@with_traefik_redis
async def resolve_delete(*_, traefik_redis, nodeId):
    return {"ok": traefik_redis.delete_middleware(nodeId)}