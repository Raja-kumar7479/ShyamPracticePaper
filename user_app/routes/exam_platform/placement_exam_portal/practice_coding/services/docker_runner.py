import os
import time
import uuid
import logging
import tempfile
import threading
import subprocess

from config import Config

logger = logging.getLogger(__name__)

SANDBOX_DIR = "/sandbox"
STDOUT_LIMIT = max(65536, int(getattr(Config, 'JUDGE_STDOUT_LIMIT_BYTES', 4 * 1024 * 1024)))
FILE_LIMIT = max(1, int(getattr(Config, 'JUDGE_FILE_LIMIT_MB', 32))) * 1024 * 1024
OUTPUT_LIMIT_EXIT = 153

_status_lock = threading.Lock()
_status = {'at': 0.0, 'value': None}


def host_mount_path(path: str) -> str:
    if os.name != "nt":
        return path
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return "/" + drive.rstrip(":").lower() + rest.replace("\\", "/")


def new_container_name(prefix="judge") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _run_as():
    if not getattr(Config, 'DOCKER_RUN_AS_NONROOT', True) or os.name == "nt":
        return None
    uid = os.getuid() if hasattr(os, 'getuid') else 0
    gid = os.getgid() if hasattr(os, 'getgid') else 0
    if uid == 0:
        return 65534, 65534, True
    return uid, gid, False


def prepare_dir(temp_dir: str) -> None:
    who = _run_as()
    if not who or not who[2]:
        return
    try:
        os.chmod(temp_dir, 0o777)
        for name in os.listdir(temp_dir):
            os.chmod(os.path.join(temp_dir, name), 0o666)
    except OSError:
        logger.warning("Could not open up the sandbox directory %s", temp_dir, exc_info=True)


def build_argv(temp_dir: str, shell_cmd: str, name: str,
               memory_limit: str = None) -> list:
    mem = memory_limit or Config.MEMORY_LIMIT
    argv = [
        "docker", "run", "--rm", "-i",
        "--name", name,
        "--memory", mem,
        "--memory-swap", mem,
        "--pids-limit", "128",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--ulimit", f"fsize={FILE_LIMIT}:{FILE_LIMIT}",
        "--ulimit", "nofile=1024:1024",
        "-e", "HOME=/tmp",
        "-v", f"{host_mount_path(temp_dir)}:{SANDBOX_DIR}",
        "-w", SANDBOX_DIR,
    ]
    who = _run_as()
    if who:
        argv += ["--user", f"{who[0]}:{who[1]}"]
    if Config.DOCKER_NETWORK_DISABLED:
        argv += ["--network", "none"]
    if Config.DOCKER_READONLY_ROOTFS:
        argv += ["--read-only", "--tmpfs", "/tmp:rw,exec,size=128m,mode=1777"]
    if Config.CPU_QUOTA and Config.CPU_QUOTA > 0:
        argv += ["--cpus", str(Config.CPU_QUOTA)]

    argv += [Config.JUDGE_IMAGE, "sh", "-c", shell_cmd]
    return argv


def kill_container(name: str) -> None:
    try:
        subprocess.run(["docker", "rm", "-f", name],
                       capture_output=True, timeout=10)
    except Exception:
        logger.warning("Failed to remove container %s", name, exc_info=True)


def _read_capped(path, limit):
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def run(temp_dir: str, shell_cmd: str, stdin_data: str = "",
        timeout: int = 10, memory_limit: str = None, prefix="judge"):
    name = new_container_name(prefix)
    prepare_dir(temp_dir)
    argv = build_argv(temp_dir, shell_cmd, name, memory_limit)
    capture_dir = tempfile.mkdtemp(prefix="cjio_")
    out_path = os.path.join(capture_dir, "stdout")
    err_path = os.path.join(capture_dir, "stderr")
    in_path = os.path.join(capture_dir, "stdin")
    deadline = time.monotonic() + timeout + Config.DOCKER_STARTUP_GRACE
    try:
        with open(in_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(stdin_data or "")
        with open(in_path, "rb") as fin, open(out_path, "wb") as fout, open(err_path, "wb") as ferr:
            proc = subprocess.Popen(argv, stdin=fin, stdout=fout, stderr=ferr)
            overflow = False
            while proc.poll() is None:
                if time.monotonic() >= deadline:
                    kill_container(name)
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        proc.kill()
                    return -1, "", "", True
                try:
                    if os.path.getsize(out_path) > STDOUT_LIMIT or os.path.getsize(err_path) > STDOUT_LIMIT:
                        overflow = True
                        kill_container(name)
                        try:
                            proc.wait(timeout=10)
                        except Exception:
                            proc.kill()
                        break
                except OSError:
                    pass
                time.sleep(0.03)
        stdout = _read_capped(out_path, STDOUT_LIMIT)
        stderr = _read_capped(err_path, STDOUT_LIMIT)
        if overflow:
            logger.warning("Sandbox %s killed: output over %d bytes", name, STDOUT_LIMIT)
            return OUTPUT_LIMIT_EXIT, stdout, "Output limit exceeded", False
        return proc.returncode, stdout, stderr, False
    finally:
        for path in (in_path, out_path, err_path):
            try:
                os.remove(path)
            except OSError:
                pass
        try:
            os.rmdir(capture_dir)
        except OSError:
            pass


def docker_status(max_age=15.0):
    now = time.monotonic()
    with _status_lock:
        if _status['value'] is not None and now - _status['at'] < max_age:
            return _status['value']
    value = {'docker': False, 'image': False}
    try:
        proc = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", Config.JUDGE_IMAGE],
                              capture_output=True, timeout=5)
        if proc.returncode == 0:
            value = {'docker': True, 'image': True}
        else:
            ping = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                  capture_output=True, timeout=5)
            value = {'docker': ping.returncode == 0, 'image': False}
    except Exception:
        value = {'docker': False, 'image': False}
    with _status_lock:
        _status['value'] = value
        _status['at'] = time.monotonic()
    return value


def warmup():
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", Config.JUDGE_IMAGE],
            capture_output=True, timeout=20,
        )
        if proc.returncode != 0:
            logger.warning(
                "Judge image '%s' is missing. Build it with: "
                "docker build -f docker/Dockerfile.judge -t %s docker",
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
