from app.utils import registerQuery, registerMutation, createType
from . import docker_client, KeyValue, formatTime
from docker.errors import APIError, NotFound
from docker.types import IPAMConfig, IPAMPool

DockerNetwork = createType("DockerNetwork")


@registerQuery("dockerNetworks")
def resolve_networks(*_):
    return docker_client.networks.list(greedy=True)


def resolve_create_network(
    *,
    name,
    labels: list[KeyValue],
    ipv6,
    driver,
    internal,
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


@registerMutation("dockerCreateNetwork")
def resolve_form_create_network(*_, input):
    return resolve_create_network(**input)


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
def resolve_network_builtin(network, _):
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
def resolve_network_connections(network, _):
    return [
        {
            "ipv4Address": endpoint["IPv4Address"].rpartition("/")[0] or None,
            "ipv6Address": endpoint["IPv6Address"] or None,
            "container": docker_client.containers.get(id),
        }
        for id, endpoint in network.attrs["Containers"].items()
    ]


@registerMutation("dockerConnectContainerToNetwork")
def resolve_connect_container(*_, connection):
    network = docker_client.networks.get(connection["networkId"])
    container = docker_client.containers.get(connection["containerId"])
    try:
        network.connect(container)
    except APIError:
        return False
    return True


@registerMutation("dockerDisconnectContainerFromNetwork")
def resolve_connect_container(*_, connection):
    network = docker_client.networks.get(connection["networkId"])
    container = docker_client.containers.get(connection["containerId"])
    try:
        network.disconnect(container)
    except APIError:
        return False
    return True


@registerMutation("dockerRemoveNetwork")
def resolve_remove_network(*_, id):
    try:
        docker_client.api.remove_network(id)
    except (NotFound, APIError):
        return False
    return True


@registerMutation("dockerPruneNetworks")
def resolve_prune_networks(*_):
    try:
        docker_client.api.prune_networks()
    except APIError:
        return False
    return True
