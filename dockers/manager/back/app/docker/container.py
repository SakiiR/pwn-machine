import re
import shlex
from typing import NamedTuple

from app.utils import createType, registerMutation, registerQuery

from docker.errors import APIError, NotFound
from docker.types import Mount

from . import KeyValue, docker_client, formatTime, kv_to_dict
from .image import resolve_image_name

DockerContainer = createType("DockerContainer")
DockerContainerMount = createType("DockerContainerMount")
DockerContainerConnection = createType("DockerContainerConnection")


class ContainerMount(NamedTuple):
    type: str
    source: str = None
    target: str = None
    readonly: bool = False
    volume: str = None
    name: str = None


@registerQuery("dockerContainers")
def resolve_containers(*_, onlyRunning):
    return docker_client.containers.list(all=not onlyRunning)


def graphql_to_docker_mounts(mounts):
    results = []
    for mount in mounts:
        target = mount["target"]
        type = mount["type"].lower()
        if type == "volume":
            source = mount["name"]
        else:
            source = mount["source"]
        results.append(Mount(target, source, type, mount["readonly"]))
    return results


def graphql_to_docker_ports(ports):
    results = {}
    for port in ports:
        containerPort = port["containerPort"]
        protocol = port["protocol"]
        targets = []
        for target in port["targets"]:
            host_ip, host_port = target.rsplit(":", 1)
            targets.append({"HostIp": host_ip, "HostPort": host_port})
        results[f"{containerPort}/{protocol}"] = targets
    return results


def resolve_create_container(
    *,
    name=None,
    image,
    labels: list[KeyValue],
    command=None,
    user,
    capAdd,
    capDrop,
    environment: list[KeyValue],
    privileged,
    readonly,
    mounts: list[ContainerMount],
    ports: list,
    restartPolicy,
    start=False,
    rm=False,
):

    labels = kv_to_dict(labels)
    mounts = graphql_to_docker_mounts(mounts)
    ports = graphql_to_docker_ports(ports)
    if start:
        f = docker_client.containers.run
    else:
        f = docker_client.containers.create
    return f(
        image,
        detach=True,
        name=name or None,
        labels=labels,
        command=command,
        user=user,
        environment=dict(environment),
        privileged=privileged,
        read_only=readonly,
        mounts=mounts,  #
        ports=ports,
    )


@registerMutation("createDockerContainer")
def resolve_form_create_container(*_, input):
    return resolve_create_container(**input)


@registerQuery("dockerContainerByName")
@registerQuery("dockerContainerById")
def resolve_container_by_name(*_, name=None, id=None):
    try:
        return docker_client.containers.get(name or id)
    except:
        return None


@DockerContainer.field("labels")
def resolve_container_labels(container, _):
    return [KeyValue(*label) for label in container.labels.items()]


@DockerContainer.field("created")
def resolve_container_created(container, _):
    return formatTime(container.attrs["Created"])


@DockerContainer.field("capAdd")
def resolve_container_capAdd(container, _):
    host_config = container.attrs["HostConfig"]
    if host_config["CapAdd"]:
        for cap_add in host_config["CapAdd"]:
            yield cap_add


@DockerContainer.field("capDrop")
def resolve_container_capDrop(container, _):
    host_config = container.attrs["HostConfig"]
    if host_config["CapDrop"]:
        for cap_drop in host_config["CapDrop"]:
            yield cap_drop


@DockerContainer.field("command")
def resolve_container_command(container, _):
    return shlex.join([container.attrs["Path"], *container.attrs["Args"]])


@DockerContainer.field("environment")
def resolve_container_environment(container, _):
    return [
        KeyValue(*var.partition("=")[::2]) for var in container.attrs["Config"]["Env"]
    ]


@DockerContainer.field("privileged")
def resolve_container_privileged(container, _):
    return container.attrs["HostConfig"]["Privileged"]


@DockerContainer.field("ps")
def resolve_container_ps(container, _):
    titles = [
        "user",
        "pid",
        "cpu",
        "mem",
        "vsz",
        "rss",
        "tty",
        "stat",
        "start",
        "time",
        "command",
    ]
    try:
        top = container.top(ps_args="-aux")
    except:
        return
    processes = []
    for ps in top["Processes"]:
        process = {}
        for title, value in zip(titles, ps):
            process[title] = value
        yield process


@DockerContainerConnection.field("ipAddress")
def resolve_connection_ip_address(connection, *_):
    return connection.get("IPAddress", None) or None


@DockerContainer.field("mounts")
def resolve_container_mounts(container, _):
    for mount in container.attrs["Mounts"]:
        yield ContainerMount(
            type=mount["Type"],
            source=mount.get("Source"),
            target=mount.get("Destination"),
            readonly=not mount["RW"],
            volume=mount.get("Name"),
            name=mount.get("Name"),
        )


@DockerContainerMount.field("volume")
def resolve_container_mount_volume(mount: ContainerMount, _):
    if mount.type == "VOLUME":
        return docker_client.volumes.get(mount.volume)
    return None


@DockerContainer.field("connections")
def resolve_container_connections(container, _):
    for name, endpoint in container.attrs["NetworkSettings"]["Networks"].items():
        yield {
            "aliases": endpoint["Aliases"] or [],
            "ipAddress": endpoint["IPAddress"] or None,
            "network": docker_client.networks.get(name),
        }


@DockerContainer.field("ports")
def resolve_container_ports(container, _):
    for port_proto, binds in container.ports.items():
        port, _, protocol = port_proto.rpartition("/")
        if binds is None:
            yield {"containerPort": port, "protocol": protocol, "targets": None}
            continue
        targets = []
        for bind in binds:
            host_ip = bind["HostIp"]
            host_port = bind["HostPort"]
            if ":" in host_ip:
                targets.append(f"[{host_ip}]:{host_port}")
            else:
                targets.append(f"{host_ip}:{host_port}")

        yield {"containerPort": port, "protocol": protocol, "targets": targets}


@DockerContainer.field("status")
def resolve_container_status(container, _):
    return container.status.upper()


@DockerContainer.field("restartPolicy")
def resilve_restart_policy(container, _):
    policy = container.attrs["HostConfig"]["RestartPolicy"]
    name = policy["Name"] or "no"
    maximumRetryCount = None
    if name == "on-failure":
        maximumRetryCount = policy["MaximumRetryCount"]
    return {"name": name, "maximumRetryCount": maximumRetryCount}


@registerMutation("startDockerContainer")
def resolve_start_container(*_, id):
    docker_client.api.start(id)
    return True


@registerMutation("restartDockerContainer")
def resolve_restart_container(*_, id):
    docker_client.api.restart(id)
    return True


@registerMutation("pauseDockerContainer")
def resolve_pause_container(*_, id):
    docker_client.api.pause(id)
    return True


@registerMutation("unpauseDockerContainer")
def resolve_unpause_container(*_, id):
    docker_client.api.unpause(id)
    return True


@registerMutation("stopDockerContainer")
def resolve_stop_container(*_, id):
    docker_client.api.stop(id)
    return True


@registerMutation("killDockerContainer")
def resolve_kill_container(*_, id):
    docker_client.api.kill(id)
    return True


@registerMutation("renameDockerContainer")
def resolve_rename_container(*_, id, name):
    docker_client.api.rename(id, name=name)
    return True


@registerMutation("deleteDockerContainer")
def resolve_remove_container(*_, id, force, pruneVolumes):
    docker_client.api.remove_container(id, v=pruneVolumes, force=force)
    return True


@registerMutation("pruneDockerContainers")
def resolve_prune_containers(*_):
    pruned = docker_client.containers.prune()
    return {
        "deleted": pruned["ContainersDeleted"] or [],
        "spaceReclaimed": 0,
    }
