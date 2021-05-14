from ..utils import registerQuery, createType
from . import docker_client, KeyValue, formatTime

DockerVolume = createType("DockerVolume")


@registerQuery("dockerVolumes")
async def resolve_volumes(*_):
    return docker_client.volumes.list()


@DockerVolume.field("labels")
async def resolve_volume_labels(volume, _):
    return [KeyValue(*label) for label in (volume.attrs["Labels"] or {}).items()]


@DockerVolume.field("created")
async def resolve_volume_created(volume, _):
    return formatTime(volume.attrs["CreatedAt"])


@DockerVolume.field("mountpoint")
async def resolve_volume_mountpoint(volume, _):
    return volume.attrs["Mountpoint"]


@DockerVolume.field("usingContainers")
async def resolve_volume_using_containers(volume, _, onlyRunning=True):
    return docker_client.containers.list(
        all=not onlyRunning, filters={"volume": volume.attrs["Name"]}
    )
