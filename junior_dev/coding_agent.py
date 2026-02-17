import subprocess
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass

DEFAULT_AGENT_TIMEOUT_SECONDS = 7200
POLL_INTERVAL_SECONDS = 0.1
GIT_STATUS_TIMEOUT_SECONDS = 5
THREAD_JOIN_TIMEOUT_SECONDS = 2


@dataclass
class AgentResult:
    success: bool
    output: str
    error: str
    execution_time: float
    exit_code: int
    changes_made: bool


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _pipeline_env(agents_dir: Path, backend: str) -> Dict[str, str]:
    env = dict(os.environ)
    env["AGENT_BACKEND"] = backend
    env["AGENTS_DIR"] = str(agents_dir)
    env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")
    return env


def _read_stream(pipe, lines: List[str], file=sys.stdout):
    for line in iter(pipe.readline, ""):
        print(line, end="", flush=True, file=file)
        lines.append(line)
    pipe.close()


class CodingAgent:
    def __init__(
        self,
        agent_type: str = "pipeline",
        timeout: int = DEFAULT_AGENT_TIMEOUT_SECONDS,
        working_dir: Optional[str] = None,
        agent_args: Optional[List[str]] = None,
        agents_dir: Optional[str] = None,
        pipeline_backend: Optional[str] = None,
    ):
        if agent_type != "pipeline":
            raise ValueError(f"Only 'pipeline' agent type is supported. Got: {agent_type}")

        self.agent_type = agent_type
        self.timeout = timeout
        self.working_dir = Path(working_dir) if working_dir else None
        self.agent_args = agent_args or []
        self.agents_dir = Path(agents_dir) if agents_dir else None
        self.pipeline_backend = pipeline_backend

    def execute(self, prompt: str) -> AgentResult:
        start = time.time()
        try:
            success, output, error, exit_code, changes = self._run_pipeline(prompt)
        except Exception as e:
            success, output, error, exit_code, changes = False, "", str(e), -1, False

        return AgentResult(
            success=success,
            output=output,
            error=error,
            execution_time=time.time() - start,
            exit_code=exit_code,
            changes_made=changes,
        )

    def check_agent_available(self) -> bool:
        return self._pipeline_script() is not None

    def _agents_dir(self) -> Path:
        if self.agents_dir is None:
            return _project_root() / ".agents"
        return self.agents_dir if self.agents_dir.is_absolute() else _project_root() / self.agents_dir

    def _pipeline_script(self) -> Optional[Path]:
        script = self._agents_dir() / "run_pipeline.sh"
        if script.is_file() and os.access(script, os.X_OK):
            return script
        return None

    def _backend(self) -> str:
        if self.pipeline_backend:
            return self.pipeline_backend
        for i, arg in enumerate(self.agent_args):
            if arg == "--backend" and i + 1 < len(self.agent_args):
                return self.agent_args[i + 1]
            if arg.startswith("--backend="):
                return arg.split("=", 1)[1]
        return os.getenv("AGENT_BACKEND", "cursor")

    def _run_pipeline(self, prompt: str) -> Tuple[bool, str, str, int, bool]:
        if not self.working_dir:
            return False, "", "pipeline agent requires working_dir", -1, False

        script = self._pipeline_script()
        if not script:
            return False, "", f"Pipeline script not found or not executable: {self._agents_dir() / 'run_pipeline.sh'}", -1, False

        env = _pipeline_env(self._agents_dir(), self._backend())
        cmd = ["bash", str(script), prompt]

        try:
            exit_code, output, err = self._run_cmd(cmd, str(self.working_dir), env)
            success = exit_code == 0
            changes = self._git_has_changes() if success else False
            return success, output, err, exit_code, changes
        except Exception as e:
            return False, "", str(e), -1, False

    def _run_cmd(self, cmd: List[str], cwd: str, env: Dict[str, str]) -> Tuple[int, str, str]:
        process = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        out_lines: List[str] = []
        err_lines: List[str] = []
        t_out = threading.Thread(target=_read_stream, args=(process.stdout, out_lines), daemon=True)
        t_err = threading.Thread(target=_read_stream, args=(process.stderr, err_lines), kwargs={"file": sys.stderr}, daemon=True)
        t_out.start()
        t_err.start()

        start = time.time()
        while process.poll() is None:
            if time.time() - start > self.timeout:
                process.kill()
                t_out.join(timeout=1)
                t_err.join(timeout=1)
                return -1, "".join(out_lines), f"Pipeline execution timed out after {self.timeout}s"
            time.sleep(POLL_INTERVAL_SECONDS)

        t_out.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
        t_err.join(timeout=THREAD_JOIN_TIMEOUT_SECONDS)
        return process.returncode or 0, "".join(out_lines), "".join(err_lines)

    def _git_has_changes(self) -> bool:
        if not self.working_dir:
            return False
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.working_dir), capture_output=True, text=True,
                timeout=GIT_STATUS_TIMEOUT_SECONDS,
            )
            return bool(r.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
