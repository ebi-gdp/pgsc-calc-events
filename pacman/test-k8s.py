#!/usr/bin/env python

from os import path
from time import sleep
import yaml
from kubernetes import client, config

from os import path
from time import sleep

import yaml

from kubernetes import client, config

def build_arguments():
    """ Build a complicated container argument string in a clearer way """

    # nextflow requires JSON params in a file, so redirect the environment variable
    json_args = " ".join(["/bin/echo", "${JSON}", ">", "/tmp/params.json", ";", ""])

    # useful for checking params from kubectl logs
    debug_args = " ".join(["cat", "/tmp/params.json", ";", ""])

    # run the pipeline!
    nxf_args = " ".join(["nextflow", "run", "pgscatalog/pgsc_calc", "-name", "${ID}",
                         "-r", "dev", "-latest", "-profile", "k8s,test",
                         "-params-file", "/tmp/params.json", "-with-weblog",
                         "http://pgscalc-log-webhook-eventsource-svc:4567"])

    dummy_nxf = "nextflow run hello"
    # stick arguments together, container executes /bin/sh -c ...
    return ['-c', json_args + debug_args + dummy_nxf] # TODO: nxf_args

def create_job_object(params, JOB_NAME):

    # create environment variables from kafka message
    params = {'JSON': '{}', 'ID': 'uniqueid'}
    env_vars = [client.V1EnvVar(k, v) for k, v in params.items()]

    # Configureate Pod template container
    container = client.V1Container(
        name="nxf-controller",
        image="docker.io/nextflow/nextflow:21.10.6",
        args = build_arguments(),
        env = env_vars,
        command=["/bin/sh"])
    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": "pi"}),
        spec=client.V1PodSpec(restart_policy="Never", containers=[container]))
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
    print("job created!")
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

    print("job started!")

    job_completed = False
    while not job_completed:
        api_response = api_instance.read_namespaced_job_status(
            name=JOB_NAME,
            namespace="test")
        if api_response.status.succeeded is not None or \
                api_response.status.failed is not None:
            job_completed = True
        sleep(1)

    print("job completed!")

def delete_job(api_instance, JOB_NAME):
    api_response = api_instance.delete_namespaced_job(
        name=JOB_NAME,
        namespace="test",
        body=client.V1DeleteOptions(
            propagation_policy='Foreground',
            grace_period_seconds=5))
    print("job deleted! (cleanup)")


def main():
    # Configs can be set in Configuration class directly or using helper
    # utility. If no argument provided, the config will be loaded from
    # default location.
    config.load_kube_config()
    batch_v1 = client.BatchV1Api()

    # TODO: autogenerate based on kafka consumer?
    JOB_NAME = "nxf"

    # Create a job object with client-python API. The job we
    # created is same as the `pi-job.yaml` in the /examples folder.
    job = create_job_object(params = None, JOB_NAME = JOB_NAME)

    create_job(batch_v1, job)

    delete_job(batch_v1, JOB_NAME)


if __name__ == '__main__':
    main()
