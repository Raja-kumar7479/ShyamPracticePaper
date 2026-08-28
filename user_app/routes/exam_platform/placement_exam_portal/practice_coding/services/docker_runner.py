"""Docker sandbox primitives shared by the code and SQL executors."""
import os
import uuid
import logging
import subprocess

from config import Config

logger = logging.getLogger(__name__)

SANDBOX_DIR = "/sandbox"


def host_mount_path(path: str) -> str:
    """
    Convert a Windows path to the form Docker Desktop accepts for bind mounts
    (C:\\Users\\x -> /c/Users/x). Unchanged on POSIX hosts.
    """
    if os.name != "nt":
        return path
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return "/" + drive.rstrip(":").lower() + rest.replace("\\", "/")


def new_container_name(prefix="judge") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def build_argv(temp_dir: str, shell_cmd: str, name: str,
               memory_limit: str = None) -> list:
    """
    Build the `docker run` argv for untrusted code.

    Locked down: no network, hard memory cap with swap pinned to the same value
    (without --memory-swap a process can swap past the limit), and a PID cap to
    blunt fork bombs.
    """
    mem = memory_limit or Config.MEMORY_LIMIT
    argv = [
        "docker", "run", "--rm", "-i",
        "--name", name,
        "--memory", mem,
        "--memory-swap", mem,
        "--pids-limit", "128",
        "-v", f"{host_mount_path(temp_dir)}:{SANDBOX_DIR}",
        "-w", SANDBOX_DIR,
    ]
    if Config.DOCKER_NETWORK_DISABLED:
        argv += ["--network", "none"]
    if Config.DOCKER_READONLY_ROOTFS:
        # Compilers need scratch space; the bind mount stays writable so build
        # artifacts can still be produced.
        argv += ["--read-only", "--tmpfs", "/tmp:rw,size=64m"]
    if Config.CPU_QUOTA and Config.CPU_QUOTA > 0:
        argv += ["--cpus", str(Config.CPU_QUOTA)]

    argv += [Config.JUDGE_IMAGE, "sh", "-c", shell_cmd]
    return argv


def kill_container(name: str) -> None:
    """
    Force-remove a container, ignoring failures.

    Required on timeout: killing the `docker run` client does not stop the
    container it started, so --rm never fires and the code keeps running.
    """
    try:
        subprocess.run(["docker", "rm", "-f", name],
                       capture_output=True, timeout=10)
    except Exception:
        logger.warning("Failed to remove container %s", name, exc_info=True)


def run(temp_dir: str, shell_cmd: str, stdin_data: str = "",
        timeout: int = 10, memory_limit: str = None, prefix="judge"):
    """
    Execute shell_cmd in a sandbox container.

    Returns (returncode, stdout, stderr, timed_out).
    """
    name = new_container_name(prefix)
    argv = build_argv(temp_dir, shell_cmd, name, memory_limit)
    try:
        proc = subprocess.run(
            argv,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout + Config.DOCKER_STARTUP_GRACE,
        )
        return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired:
        kill_container(name)
        return -1, "", "", True


def warmup():
    """
    Pull the image into the daemon's cache and prime its layers.

    The very first `docker run` after a boot pays a one-off cost (image
    lookup, layer mount) that can be several seconds; doing it at startup
    means the first candidate submission is as fast as the rest.
    """
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", Config.JUDGE_IMAGE],
            capture_output=True, timeout=20,
        )
        if proc.returncode != 0:
            logger.warning(
                "Judge image '%s' is missing. Build it with: "
                "docker build -f coding_platform/Dockerfile.judge -t %s .",
                Config.JUDGE_IMAGE, Config.JUDGE_IMAGE)
            return False

        name = new_container_name("cjwarm")
        subprocess.run(
            ["docker", "run", "--rm", "--name", name, "--network", "none",
             Config.JUDGE_IMAGE, "true"],
            capture_output=True, timeout=60,
        )
        logger.info("Sandbox image '%s' warmed", Config.JUDGE_IMAGE)
        return True
    except Exception as e:
        logger.warning("Sandbox warmup skipped: %s", e)
        return False
