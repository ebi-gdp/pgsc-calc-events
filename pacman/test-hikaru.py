from ruamel.yaml import YAML
from hikaru.model.rel_1_18 import *
from kubernetes import config, client


def load_job_instance():
    yaml = YAML()
    with open("manifests/pgsc-job.yaml", "r") as f:
        doc = yaml.load(f)
        return Job.from_yaml(doc)


def make_cm_vol(client, json_dict):
    """ Create a volume from a dynamic ConfigMap, unique to each pipeline run ID

    The JSON dict should contain two keys. Values are enquoted JSON strings """

    assert all([x in json_dict for x in ['input.json', 'params.json']]), "Invalid dict keys"

    cm = ConfigMap(data = json_dict,
                   metadata = ObjectMeta(labels = {'app': 'nextflow',
                                                   'instance': 'pipeline-1',
                                                   'cm_type': 'vol' },
                                         generateName = 'nxf-vol-config-'),
                   immutable = True)

    cm.set_client(client)
    result: Response = cm.createNamespacedConfigMap(namespace = 'test')

    return Volume(name = 'config',
                  configMap = ConfigMapVolumeSource(name = result.obj.metadata.name))


def provision_job_instance(job, params):
    """ Provision a job instance with parameters from Kafka """

    # TODO: update job metadata -------------------------------------

    params = {'input.json': '{}', 'params.json': '{}'}
    # provision a new config map volume from the message
    cm_vol = make_cm_vol(api_client, d)

    # update the job instance to reflect the new config map name
    # second volume is the config map
    volumes = job.spec.template.spec.volumes
    volumes[1] = cm_vol

    return job.create(namespace = 'test')

config.load_kube_config(config_file = '/home/benjamin/Documents/openstack/config')
api_client = client.ApiClient()
j = load_job_instance()
job_result: Response = provision_job_instance(j, None)

# todo: add type hints
# todo: cleanup and delete configmaps
