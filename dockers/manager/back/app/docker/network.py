from ..utils import registerQuery, createType
from . import docker_client, KeyValue
from datetime import datetime

DockerNetwork = createType("DockerNetwork")


@registerQuery("dockerNetworks")
async def resolve_networks(*_):
    return docker_client.networks.list(greedy=True)


@DockerNetwork.field("labels")
async def resolve_network_labels(network, _):
    return [KeyValue(k,v) for k,v in network.attrs["Labels"].items()]


@DockerNetwork.field("created")
async def resolve_network_created(network, _):
    return str(datetime.fromisoformat(network.attrs["Created"].partition(".")[0]))


@DockerNetwork.field("ipv6")
async def resolve_network_ipv6(network, _):
    return network.attrs["EnableIPv6"]


@DockerNetwork.field("driver")
async def resolve_network_driver(network, _):
    return network.attrs["Driver"]


@DockerNetwork.field("internal")
async def resolve_network_internal(network, _):
    return network.attrs["Internal"]


@DockerNetwork.field("subnet")
async def resolve_network_subnet(network, _):
    return (network.attrs["IPAM"]["Config"] or [{}])[0].get("Subnet")


@DockerNetwork.field("gateway")
async def resolve_network_gateway(network, _):
    return (network.attrs["IPAM"]["Config"] or [{}])[0].get("Gateway")
