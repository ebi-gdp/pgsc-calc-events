#!/usr/bin/env python

from os import path
from time import sleep
import yaml
from kubernetes import client, config
from os import path
from time import sleep
import logging
from kubernetes import client, config
from kafka import KafkaConsumer
import json

def create_arguments_list():
    """ Build a complicated container argument string """

    # nextflow parameters must be in a JSON file
    param_args = " ".join(["/bin/echo", "${JSON}", ">", "/tmp/params.json", ";", ""])

    # pipeline input must be in a JSON file
    input_args = " ".join(["/bin/echo", "${INPUT}", ">", "/tmp/input.json", ";", ""])

    # useful for debugging logs
    debug_args = " ".join(["cat", "/tmp/params.json", "/tmp/input.json", ";", ""])

    # run the pipeline!
    nxf_args = " ".join(["nextflow", "run", "pgscatalog/pgsc_calc", "-name", "${ID}",
                         "-r", "dev", "-latest", "-profile", "k8s,test",
                         "-params-file", "/tmp/params.json", "-with-weblog",
                         "http://pgscalc-log-webhook-eventsource-svc:4567",
                         "--input", "/tmp/input.json"])

    # useful for running a dummy nextflow pipeline
    dummy_nxf = "nextflow run hello"

    # stick arguments together, container executes /bin/sh -c ...
    return ['-c', param_args + input_args + debug_args + dummy_nxf] # TODO: nxf_args


def create_resource_requirements_object():
    """ Create a resource requirements object for the nextflow driver container.

    https://www.nextflow.io/blog/2021/5_tips_for_hpc_users.html
    'An average pipeline may require 2 CPUs and 2 GB of resources allocation.'
    """

    limits = {'cpu': 2, 'memory': '4G'}
    requests = {'cpu': 2, 'memory': '2G'}
    return client.V1ResourceRequirements(limits, requests)


def create_volumes_list():
    """ Create a list of named volumes """
    ssd_pvc = client.V1PersistentVolumeClaimVolumeSource(claim_name = 'ssdnfsclaim')
    return[client.V1Volume(name = 'vol-1', persistent_volume_claim = ssd_pvc)]


def create_volume_mounts_list():
    """ Create a list of volume mounts.

    The pipeline needs fast SSD storage for intermediate work directories.

    TODO: use a sub path to isolate pipeline instances
    """
    return [client.V1VolumeMount(name = 'vol-1', mount_path = '/workspace')]

def create_environment_vars_object(params):
    """ Combine static environment variables with parameters from Kafka """

    # TODO read from config map?
    nxf_static = {'NXF_OPTS': '-Xms500M -Xmx3500M',
                  'NXF_EXECUTOR': 'k8s',
                  'NXF_ANSI_LOG': 'false',
                  'NXF_HOME': '/workpace/nxf_home'}

    return [client.V1EnvVar(k, v) for k, v in {**params, **nxf_static}.items()]

def create_job_object(params, JOB_NAME):

    # create environment variables from kafka message
    params = {'JSON': '{}', 'ID': 'uniqueid'}

    # Configureate Pod template container
    container = client.V1Container(
        name="nxf-controller",
        image="docker.io/nextflow/nextflow:21.10.6",
        args = create_arguments_list(),
        env = create_environment_vars_object(params),
        command=["/bin/sh"],
        volume_mounts = create_volume_mounts_list(),
        resources = create_resource_requirements_object())
        # TODO: working_dir = ???)

    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": "pi"}),
        spec=client.V1PodSpec(restart_policy="Never",
                              containers=[container],
                              volumes=create_volumes_list()))

    # Create the specification of deployment
    spec = client.V1JobSpec(
        template=template,
        backoff_limit=4)
    # Instantiate the job object
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=JOB_NAME),
        spec=spec)

    return job


def create_job(api_instance, job):
    api_response = api_instance.create_namespaced_job(
        body=job,
        namespace="test")
    logging.info("job created")
    get_job_status(api_instance, job.metadata.name)


def get_job_status(api_instance, JOB_NAME):
    job_started = False

    while not job_started:
        api_response = api_instance.read_namespaced_job_status(
            name=JOB_NAME,
            namespace="test")
        if api_response.status.start_time is not None:
            job_started = True
        sleep(1)

    logging.info("job started")

    job_completed = False
    while not job_completed:
        api_response = api_instance.read_namespaced_job_status(
            name=JOB_NAME,
            namespace="test")
        if api_response.status.succeeded is not None or \
                api_response.status.failed is not None:
            job_completed = True
        sleep(1)

    logging.info("job completed")

def delete_job(api_instance, JOB_NAME):
    api_response = api_instance.delete_namespaced_job(
        name=JOB_NAME,
        namespace="test",
        body=client.V1DeleteOptions(
            propagation_policy='Foreground',
            grace_period_seconds=5))
    logging.info("job deleted (cleanup)")


def parse_json(m):
    try:
        return json.loads(m.decode('ascii'))
    except json.decoder.JSONDecodeError:
        return json.loads('{}')

def main():
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    config.load_kube_config()
    batch_v1 = client.BatchV1Api()

    logging.basicConfig(level=logging.INFO,
                    format='(%(threadName)-9s) %(message)s',)
    logging.getLogger("kafka").setLevel(logging.WARNING) # kafka is verbose

    launch_consumer = KafkaConsumer('my-topic',
                                group_id='my-group',
                                bootstrap_servers=['localhost:9092'],
                                value_deserializer=lambda m: parse_json(m))

    for message in launch_consumer:
            # do proper validation with json schema, just skip weird messages
            try:
                JOB_NAME = message.value['id']
                target_genomes = message.value['target_genomes']
                params = message.value['nxf_params_file']
                workdir = message.value['nxf_work']
            except KeyError:
                logging.info('Invalid message received, skipping')
                continue

            logging.info('Valid message received')
            params = None
            job = create_job_object(params, JOB_NAME)
            create_job(batch_v1, job)
            delete_job(batch_v1, JOB_NAME)



if __name__ == '__main__':
    main()
