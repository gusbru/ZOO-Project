def generate_manifest_header():
    return """
    apiVersion: v1
    kind: ConfigMap
    metadata:
        name: test-deploy-service-configmap
    data:
    """


def read_file(file):
    with open(file, "r") as f:
        return f.read()


def save_file(file, content):
    with open(file, "w") as f:
        f.write(content)


def generate_manifest(file):
    return f"{generate_manifest_header()}\n            {file}: |\n{read_file(file)}"


def generate_deploy_process_manifest(file):
    manifest = generate_manifest(file)
    save_file("DeployProcessConfigmap.yaml", manifest)
    print(f"Manifest generated from {file} and saved to manifest.yaml")


def main():
    generate_deploy_process_manifest(file="DeployProcess.py")


if __name__ == "__main__":
    main()
