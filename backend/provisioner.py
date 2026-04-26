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
    namespace = f"sunday-trainee-{username.lower()}"

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

    # Stable DNS name the attacker uses to reach the victim
    victim_dns = f"victim.{namespace}.svc.cluster.local"
    # The CTF platform backend — running locally, reachable via host.docker.internal in KIND
    ctf_url = "http://host.docker.internal:8000"

    # 2. Create Victim Deployment
    victim_deployment = _build_deployment(
        name="victim",
        namespace=namespace,
        image="sunday-victim:latest",
        capabilities=["NET_ADMIN", "NET_RAW"],
        env_vars={"CTF_URL": ctf_url},
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
            cluster_ip=None,  # headless: DNS resolves directly to pod IP
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
    # NET_ADMIN + NET_RAW are required for nmap -sS (raw SYN scan) and hping3
    attacker_deployment = _build_deployment(
        name="attacker",
        namespace=namespace,
        image="sunday-attacker:latest",
        capabilities=["NET_ADMIN", "NET_RAW"],
        env_vars={
            "VICTIM_HOST": victim_dns,  # e.g. victim.sunday-trainee-alice.svc.cluster.local
            "CTF_URL":     ctf_url,
        },
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
    namespace = f"sunday-trainee-{username.lower()}"
    v1 = client.CoreV1Api()
    try:
        v1.delete_namespace(namespace)
        print(f"[-] Namespace {namespace} deleted")
    except Exception as e:
        print(f"[!] Deprovision error: {e}")


def _build_deployment(name, namespace, image, capabilities=None, env_vars=None):
    """Helper to build a K8s Deployment object.

    Args:
        name:         Deployment/pod name (e.g. 'attacker', 'victim')
        namespace:    K8s namespace to deploy into
        image:        Docker image name (must be pre-loaded into the KIND cluster)
        capabilities: Optional list of Linux capabilities (e.g. ['NET_RAW', 'NET_ADMIN'])
        env_vars:     Optional dict of env vars to inject (e.g. {'VICTIM_HOST': '...'})
    """
    security_context = None
    if capabilities:
        security_context = client.V1SecurityContext(
            capabilities=client.V1Capabilities(add=capabilities)
        )

    env = [
        client.V1EnvVar(name=k, value=v)
        for k, v in env_vars.items()
    ] if env_vars else None

    container = client.V1Container(
        name=name,
        image=image,
        image_pull_policy="Never",
        security_context=security_context,
        env=env,
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