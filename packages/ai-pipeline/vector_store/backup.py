import os
import sys
import subprocess
import argparse
import tempfile

# Configuration template for milvus-backup tool mapping to the Docker network
CONFIG_TEMPLATE = """
milvus:
  address: "milvus-standalone:19530"
minio:
  address: "milvus-minio:9000"
  ssl: false
  accessKeyID: "minioadmin"
  secretAccessKey: "minioadmin"
  useSSL: false
  bucketName: "a-bucket"
  rootPath: "files"
etcd:
  endpoints:
    - "milvus-etcd:2379"
"""


def run_wsl_command(command: str) -> subprocess.CompletedProcess:
    """Runs a shell command inside the WSL Ubuntu environment."""
    wsl_cmd = ["wsl", "-d", "Ubuntu", "-u", "root", "sh", "-c", command]
    print(f"Executing WSL: {command}")
    return subprocess.run(wsl_cmd, capture_output=True, text=True)


def execute_backup_action(action: str, backup_name: str, backup_dir: str):
    """Executes a create or restore action using the milvus-backup docker image.
    
    Args:
        action: "create" or "restore"
        backup_name: Name identifier for the backup
        backup_dir: Local path on host where backups should be stored
    """
    os.makedirs(backup_dir, exist_ok=True)
    
    # Convert windows host backup path to WSL path
    # Example: C:\Users\... -> /mnt/c/Users/...
    abs_backup_dir = os.path.abspath(backup_dir)
    wsl_backup_dir = abs_backup_dir.replace("\\", "/").replace(":", "")
    if wsl_backup_dir[0].isupper() or (len(wsl_backup_dir) > 1 and wsl_backup_dir[1] == "/"):
        # drive letter conversion (e.g. C/Users -> /mnt/c/Users)
        drive = wsl_backup_dir[0].lower()
        wsl_backup_dir = f"/mnt/{drive}{wsl_backup_dir[1:]}"
    
    print(f"Host backup directory: {abs_backup_dir}")
    print(f"WSL backup directory: {wsl_backup_dir}")

    # Create temporary config file in host and copy it/create it in WSL
    # We will write the config directly into a temporary file in WSL /tmp/milvus_backup_config.yaml
    config_write_cmd = f"cat << 'EOF' > /tmp/milvus_backup_config.yaml\n{CONFIG_TEMPLATE}\nEOF"
    res = run_wsl_command(config_write_cmd)
    if res.returncode != 0:
        print(f"Error creating config in WSL: {res.stderr}")
        return False

    # Build the milvus-backup command
    # We mount the WSL backup directory to /backup and the config to /config.yaml
    docker_network = "visionquery_default"
    
    backup_command = (
        f"docker run --rm "
        f"--network {docker_network} "
        f"-v {wsl_backup_dir}:/backup "
        f"-v /tmp/milvus_backup_config.yaml:/config.yaml "
        f"milvusdb/milvus-backup:v0.3.0 "
        f"milvus-backup {action} "
        f"--config /config.yaml "
        f"--name {backup_name}"
    )

    print(f"Running Milvus backup tool action '{action}' for backup: '{backup_name}'...")
    res = run_wsl_command(backup_command)
    
    print("----- STDOUT -----")
    print(res.stdout)
    if res.stderr:
        print("----- STDERR -----")
        print(res.stderr)
        
    if res.returncode == 0:
        print(f"[SUCCESS] Milvus backup '{action}' completed successfully.")
        return True
    else:
        print(f"[FAIL] Milvus backup '{action}' failed with exit code: {res.returncode}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Milvus Backup and Restore Wrapper Utility")
    parser.add_argument("action", choices=["create", "restore"], help="Backup action to perform")
    parser.add_argument("--name", required=True, help="Backup name")
    parser.add_argument("--dir", default="./backups/milvus", help="Directory to store backups")
    args = parser.parse_args()

    success = execute_backup_action(args.action, args.name, args.dir)
    if success:
        sys.exit(0)
    else:
        sys.exit(1)
