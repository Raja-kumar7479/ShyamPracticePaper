"""Multi-language code execution for the coding section."""
import os
import time
import shutil
import tempfile
import logging

from . import docker_runner
from config import Config

logger = logging.getLogger(__name__)

# The six required languages. Each entry defines the source filename, the
# compile step (None when interpreted), and the run command.
LANGUAGES = {
    "python":     {"file": "main.py",     "compile": None,
                   "run": "python3 main.py"},
    "javascript": {"file": "main.js",     "compile": None,
                   "run": "node main.js"},
    # JVM flags go on the command line, not JAVA_TOOL_OPTIONS: the env var
    # makes the JVM print a "Picked up ..." banner to stderr, which would be
    # shown to candidates as part of their error output.
    # MaxRAMPercentage keeps the heap inside the container's memory cap --
    # otherwise the JVM sizes it from host RAM and gets OOM-killed instead of
    # reporting a clean error.
    "java":       {"file": "Main.java",   "compile": "javac Main.java",
                   "run": "java -XX:MaxRAMPercentage=75 -XX:+UseSerialGC "
                          "-Xss64m -cp . Main"},
    "c":          {"file": "main.c",      "compile": "gcc main.c -o main -lm",
                   "run": "./main"},
    "cpp":        {"file": "main.cpp",    "compile": "g++ main.cpp -o main",
                   "run": "./main"},
    "csharp":     {"file": "Program.cs",  "compile": "mcs -out:main.exe Program.cs",
                   "run": "mono main.exe"},
}

# Per-stream display cap. Large outputs (tens of thousands of lines) still run
# fine -- only what is shown back is truncated, with an explicit marker.
OUTPUT_CAP = 20000

# Unlikely to appear in candidate output; used to frame per-testcase results so
# one container run can report many testcases.
_SEP = "@@CJ_CASE_SEP_9f3a@@"

# Compile and run share one container; these let the host distinguish a
# compilation failure from a runtime failure without a second round trip.
_COMPILE_FAIL = "@@CJ_COMPILE_FAIL_9f3a@@"
_COMPILE_LOG = "_cj_compile.log"


class CaseResult:
    def __init__(self, status="FAIL", output="", error="", execution_time=0.0):
        self.status = status
        self.output = output
        self.error = error
        self.execution_time = execution_time

    def as_dict(self, reveal=True):
        return {
            "status": self.status,
            "output": self.output if reveal else "",
            "error": self.error if reveal else "",
            "execution_time": self.execution_time,
        }


class RunResult:
    def __init__(self, compiled=True, error="", cases=None):
        self.compiled = compiled
        self.error = error
        self.cases = cases or []

    @property
    def passed(self):
        return sum(1 for c in self.cases if c.status == "PASS")

    @property
    def total(self):
        return len(self.cases)

    def verdict(self):
        if not self.compiled:
            return "CE"
        if not self.cases:
            return "IE"
        if any(c.status == "TLE" for c in self.cases):
            return "TLE"
        if any(c.status == "RE" for c in self.cases):
            return "RE"
        return "AC" if self.passed == self.total else "WA"


def _truncate(s):
    if s is None:
        return ""
    return (s[:OUTPUT_CAP] + "... [truncated]") if len(s) > OUTPUT_CAP else s


def _normalise(s):
    """Trailing whitespace per line and at the end is not significant."""
    if s is None:
        return ""
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


DEFAULT_FLOAT_TOLERANCE = 1e-6


def _float_match(actual, expected, tol):
    """Token-wise compare: numbers within `tol`, everything else exact.

    Lets a problem whose answer is 3.14159... accept 3.141593 while still
    catching a wrong integer or a stray word in the output.
    """
    at, et = actual.split(), expected.split()
    if len(at) != len(et):
        return False
    for x, y in zip(at, et):
        if x == y:
            continue
        try:
            xf, yf = float(x), float(y)
        except ValueError:
            return False
        if abs(xf - yf) > tol:
            return False
    return True


def _matches(actual, expected, mode="exact", tol=None):
    """Compare candidate output to the expected output for a testcase.

    exact     - trimmed exact match (the default)
    float     - numeric tokens compared within `tol`
    unordered - the multiset of output lines, order ignored
    """
    a = _normalise(actual)
    e = _normalise(expected)
    if mode == "unordered":
        return sorted(a.splitlines()) == sorted(e.splitlines())
    if mode == "float":
        return _float_match(a, e, tol if tol and tol > 0 else DEFAULT_FLOAT_TOLERANCE)
    return a == e


def _driver_script(run_cmd, n_cases, per_case_timeout):
    """
    Shell driver that runs every testcase inside ONE container.

    Container start costs ~0.5-1s, which dominates short submissions; batching
    turns N starts into 1. Each case is wrapped in `timeout` so a single
    infinite loop cannot consume the whole budget, and results are framed with
    a separator plus the exit code so the host can attribute them per case.
    """
    return f"""
for i in $(seq 1 {n_cases}); do
  start=$(date +%s%N)
  timeout {per_case_timeout} {run_cmd} < in_$i.txt > out_$i.txt 2> err_$i.txt
  code=$?
  end=$(date +%s%N)
  echo "{_SEP}$i|$code|$(( (end - start) / 1000000 ))"
done
"""


def execute(code: str, language: str, testcases: list,
            time_limit: int = None, memory_limit: str = None,
            compare_mode: str = "exact", float_tolerance: float = None) -> RunResult:
    """
    Compile (if needed) and run `code` against `testcases`.

    testcases: list of dicts with 'input_text' and 'expected_output'.
    compare_mode: how output is graded - 'exact', 'float', or 'unordered'.
    """
    if language not in LANGUAGES:
        return RunResult(compiled=False, error=f"Unsupported language: {language}")
    if not testcases:
        return RunResult(compiled=True, error="No testcases configured")

    spec = LANGUAGES[language]
    time_limit = time_limit or Config.RUN_TIMEOUT
    temp_dir = tempfile.mkdtemp(prefix="cj_")
    started = time.perf_counter()
    logger.info("exec start lang=%s cases=%d code=%dB",
                language, len(testcases), len(code.encode("utf-8")))

    try:
        with open(os.path.join(temp_dir, spec["file"]), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(code)

        for i, tc in enumerate(testcases, start=1):
            with open(os.path.join(temp_dir, f"in_{i}.txt"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(tc.get("input_text") or "")

        # Compile and run share ONE container: a second `docker run` costs
        # ~0.6s of pure startup, which dominated compiled-language timings.
        # The compiler writes a sentinel file so the host can tell a
        # compilation failure from a runtime one without a second round trip.
        script = ""
        if spec["compile"]:
            script += (
                f"{spec['compile']} 2> {_COMPILE_LOG}; "
                f"if [ $? -ne 0 ]; then echo {_COMPILE_FAIL}; exit 0; fi\n"
            )
        script += _driver_script(spec["run"], len(testcases), time_limit)

        # Whole-batch ceiling; per-case `timeout` already bounds each case.
        batch_timeout = (time_limit * len(testcases)
                         + (Config.COMPILE_TIMEOUT if spec["compile"] else 0)
                         + 10)
        rc, stdout, stderr, timed_out = docker_runner.run(
            temp_dir, script, timeout=batch_timeout,
            memory_limit=memory_limit, prefix="cjr",
        )

        if timed_out:
            cases = [CaseResult(status="TLE", error="Time Limit Exceeded")
                     for _ in testcases]
            return RunResult(compiled=True, cases=cases)

        if _COMPILE_FAIL in stdout:
            log = _read(temp_dir, _COMPILE_LOG)
            logger.info("exec compile-error lang=%s in %.2fs",
                        language, time.perf_counter() - started)
            return RunResult(compiled=False,
                             error=_truncate(log) or "Compilation failed")

        # Parse the framed status lines.
        meta = {}
        for line in stdout.splitlines():
            if line.startswith(_SEP):
                try:
                    idx, code_, ms = line[len(_SEP):].split("|")
                    meta[int(idx)] = (int(code_), int(ms) / 1000.0)
                except ValueError:
                    continue

        cases = []
        for i, tc in enumerate(testcases, start=1):
            exit_code, elapsed = meta.get(i, (None, 0.0))
            out = _read(temp_dir, f"out_{i}.txt")
            err = _read(temp_dir, f"err_{i}.txt")

            if exit_code is None:
                cases.append(CaseResult("RE", out, _truncate(err) or
                                        "No result produced", elapsed))
            elif exit_code == 124:
                # `timeout` uses 124 for the timed-out case.
                cases.append(CaseResult("TLE", out, "Time Limit Exceeded", elapsed))
            elif exit_code != 0:
                cases.append(CaseResult("RE", out,
                                        _truncate(err) or f"Exit code {exit_code}",
                                        elapsed))
            elif _matches(out, tc.get("expected_output"), compare_mode, float_tolerance):
                cases.append(CaseResult("PASS", _truncate(out), "", elapsed))
            else:
                cases.append(CaseResult("FAIL", _truncate(out), "", elapsed))

        result = RunResult(compiled=True, cases=cases)
        logger.info("exec done lang=%s verdict=%s passed=%d/%d in %.2fs",
                    language, result.verdict(), result.passed, result.total,
                    time.perf_counter() - started)
        return result

    except FileNotFoundError:
        # `docker` not on PATH -- an operational problem, not the candidate's.
        logger.error("Docker CLI not found; cannot execute submissions")
        return RunResult(
            compiled=True,
            error="The code execution service is unavailable. "
                  "Please notify the invigilator.")
    except Exception as e:
        logger.exception("Execution failed after %.2fs",
                         time.perf_counter() - started)
        return RunResult(
            compiled=True,
            error="The code execution service hit an internal error. "
                  "Your code was not graded — please try again.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _read(temp_dir, name):
    path = os.path.join(temp_dir, name)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def run_custom_input(code: str, language: str, stdin_data: str,
                     time_limit: int = None, memory_limit: str = None):
    """Single ad-hoc run for the 'Use Custom Input' box."""
    result = execute(code, language,
                     [{"input_text": stdin_data, "expected_output": None}],
                     time_limit, memory_limit)
    if not result.compiled:
        return {"compiled": False, "error": result.error, "output": ""}
    case = result.cases[0] if result.cases else CaseResult()
    return {
        "compiled": True,
        "output": case.output,
        "error": case.error,
        "execution_time": case.execution_time,
        "status": case.status,
    }
