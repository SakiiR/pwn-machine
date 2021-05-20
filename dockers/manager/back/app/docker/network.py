from app.utils import registerQuery, registerMutation, createType
from . import docker_client, KeyValue, formatTime
from docker.errors import APIError, NotFound
from docker.types import IPAMConfig, IPAMPool

DockerNetwork = createType("DockerNetwork")
DockerNetworkConnection = createType("DockerNetworkConnection")


@registerQuery("dockerNetworks")
def resolve_networks(*_):
    return docker_client.networks.list(greedy=True)


@DockerNetwork.field("labels")
def resolve_network_labels(network, _):
    return [KeyValue(*label) for label in network.attrs["Labels"].items()]


@DockerNetwork.field("created")
def resolve_network_created(network, _):
    return formatTime(network.attrs["Created"])


@DockerNetwork.field("ipv6")
def resolve_network_ipv6(network, _):
    return network.attrs["EnableIPv6"]


@DockerNetwork.field("driver")
def resolve_network_driver(network, _):
    return network.attrs["Driver"]


@DockerNetwork.field("builtin")
def resolve_network_driver(network, _):
    return network.name in ["bridge", "host", "none"]


@DockerNetwork.field("internal")
def resolve_network_internal(network, _):
    return network.attrs["Internal"]


@DockerNetwork.field("ipams")
def resolve_network_ipams(network, _):
    return [
        {
            "subnet": ipam.get("Subnet"),
            "ipRange": ipam.get("IPRange"),
            "gateway": ipam.get("Gateway"),
        }
        for ipam in network.attrs["IPAM"]["Config"]
    ]


@DockerNetwork.field("connections")
def resolve_network_using_containers(network, _):
    return network.attrs["Containers"].values()


@DockerNetworkConnection.field("container")
def resolve_connection_container(connection, *_):
    return docker_client.containers.get(connection["Name"])


@DockerNetworkConnection.field("ipv4Address")
def resolve_connection_ip_address(connection, *_):
    return connection["IPv4Address"].split("/")[0] or None


@DockerNetworkConnection.field("ipv6Address")
def resolve_connection_ip_address(connection, *_):
    return connection["IPv6Address"] or None


@registerMutation("dockerCreateNetwork")
def resolve_create_network(
    *_,
    name,
    labels: list[KeyValue],
    ipv6=False,
    driver,
    internal=False,
    ipam: dict[str, str] = None,
):
    try:
        return docker_client.networks.create(
            name,
            check_duplicate=True,
            labels=dict(labels),
            enable_ipv6=ipv6,
            driver=driver,
            internal=internal,
            ipam=IPAMConfig(
                pool_configs=[
                    IPAMPool(
                        ipam.get("subnet"),
                        ipam.get("ipRange"),
                        ipam.get("gateway"),
                    )
                ]
            )
            if ipam is not None
            else None,
        )
    except APIError:
        return None


@registerMutation("dockerRemoveNetwork")
def resolve_remove_network(*_, id):
    try:
        (network := docker_client.networks.get(id)).remove()
    except (NotFound, APIError):
        return None
    return network


@registerMutation("dockerPruneNetworks")
def resolve_prune_networks(*_):
    try:
        networks = docker_client.networks.list()
        result = docker_client.networks.prune()
    except APIError:
        return None

    return [
        next(network for network in networks if network.name == name)
        for name in result["NetworksDeleted"] or []
    ]


@registerMutation("dockerConnectContainerToNetwork")
def resolve_connect_container(*_, input):
    network = docker_client.networks.get(input["networkId"])
    container = docker_client.containers.get(input["containerId"])
    try:
        network.connect(container)
    except APIError:
        return False
    return True


@registerMutation("dockerDisconnectContainerFromNetwork")
def resolve_connect_container(*_, input):
    network = docker_client.networks.get(input["networkId"])
    container = docker_client.containers.get(input["containerId"])
    try:
        network.disconnect(container)
    except APIError:
        return False
    return True
