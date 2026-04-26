from kubernetes import client, config
import yaml
import os

def load_k8s_config():
    """
    Inside a K8s pod → use in-cluster config
    Outside (local dev) → use kubeconfig
    """
    try:
        config.load_incluster_config()
    except:
        config.load_kube_config()

def provision_trainee(username: str):
    """
    Creates a K8s namespace + victim + attacker for this trainee.
    Called automatically on registration.
    """
    load_k8s_config()
    namespace = f"trainee-{username.lower()}"

    v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()

    # 1. Create Namespace
    try:
        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)
        )
        v1.create_namespace(ns)
        print(f"[+] Namespace {namespace} created")
    except Exception as e:
        print(f"[!] Namespace may already exist: {e}")

    # 2. Create Victim Deployment
    victim_deployment = _build_deployment(
        name="victim",
        namespace=namespace,
        image="victim:latest",
        capabilities=["NET_ADMIN", "NET_RAW"]
    )
    try:
        apps_v1.create_namespaced_deployment(namespace, victim_deployment)
        print(f"[+] Victim deployment created in {namespace}")
    except Exception as e:
        print(f"[!] Victim deployment error: {e}")

    # 3. Create Victim Headless Service
    svc = client.V1Service(
        metadata=client.V1ObjectMeta(name="victim", namespace=namespace),
        spec=client.V1ServiceSpec(
            cluster_ip="None",
            selector={"app": "victim"},
            ports=[client.V1ServicePort(port=80)]
        )
    )
    try:
        v1.create_namespaced_service(namespace, svc)
        print(f"[+] Victim service created")
    except Exception as e:
        print(f"[!] Service error: {e}")

    # 4. Create Attacker Deployment
    attacker_deployment = _build_deployment(
        name="attacker",
        namespace=namespace,
        image="attacker:latest",
    )
    try:
        apps_v1.create_namespaced_deployment(namespace, attacker_deployment)
        print(f"[+] Attacker deployment created in {namespace}")
    except Exception as e:
        print(f"[!] Attacker deployment error: {e}")


def deprovision_trainee(username: str):
    """
    Deletes the entire namespace for this trainee.
    Deleting namespace deletes everything inside it automatically.
    """
    load_k8s_config()
    namespace = f"trainee-{username.lower()}"
    v1 = client.CoreV1Api()
    try:
        v1.delete_namespace(namespace)
        print(f"[-] Namespace {namespace} deleted")
    except Exception as e:
        print(f"[!] Deprovision error: {e}")


def _build_deployment(name, namespace, image, capabilities=None):
    """Helper to build a K8s Deployment object"""
    security_context = None
    if capabilities:
        security_context = client.V1SecurityContext(
            capabilities=client.V1Capabilities(add=capabilities)
        )

    container = client.V1Container(
        name=name,
        image=image,
        image_pull_policy="Never",
        security_context=security_context
    )

    return client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels={"app": name}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": name}),
                spec=client.V1PodSpec(containers=[container])
            )
        )
    )