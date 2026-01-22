import subprocess
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class AgentResult:
    success: bool
    output: str
    error: str
    execution_time: float
    exit_code: int
    changes_made: bool


class CodingAgent:
    def __init__(
        self,
        agent_type: str = "aider",
        timeout: int = 300,
        working_dir: Optional[str] = None,
        agent_args: Optional[list[str]] = None,
    ):
        self.agent_type = agent_type
        self.timeout = timeout
        self.working_dir = Path(working_dir) if working_dir else None
        self.agent_args = agent_args or []
        
        self.supported_agents = {
            "aider": self._run_aider,
            "claude-code": self._run_claude_code,
            "cursor": self._run_cursor,
            "mock": self._run_mock,
        }
        
        if agent_type not in self.supported_agents:
            raise ValueError(f"Unsupported agent type: {agent_type}. Choose from: {list(self.supported_agents.keys())}")
    
    def execute(self, prompt: str, files: Optional[list] = None) -> AgentResult:
        start_time = time.time()
        
        try:
            result_func = self.supported_agents[self.agent_type]
            success, output, error, exit_code, changes = result_func(prompt, files)
            
            execution_time = time.time() - start_time
            
            return AgentResult(
                success=success,
                output=output,
                error=error,
                execution_time=execution_time,
                exit_code=exit_code,
                changes_made=changes
            )
        except Exception as e:
            execution_time = time.time() - start_time
            return AgentResult(
                success=False,
                output="",
                error=str(e),
                execution_time=execution_time,
                exit_code=-1,
                changes_made=False
            )
    
    def _run_aider(self, prompt: str, files: Optional[list] = None) -> Tuple[bool, str, str, int, bool]:
        cmd = ["aider", "--no-gitignore", *self.agent_args, "--message", prompt]
        
        if files:
            cmd.extend(files)
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self.working_dir) if self.working_dir else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            stdout_lines = []
            stderr_lines = []
            
            def read_stdout():
                for line in process.stdout:
                    print(line, end='', flush=True)
                    stdout_lines.append(line)
            
            def read_stderr():
                for line in process.stderr:
                    print(line, end='', flush=True, file=sys.stderr)
                    stderr_lines.append(line)
            
            stdout_thread = threading.Thread(target=read_stdout, daemon=True)
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stdout_thread.start()
            stderr_thread.start()
            
            start_time = time.time()
            while process.poll() is None:
                if time.time() - start_time > self.timeout:
                    process.kill()
                    stdout_thread.join(timeout=1)
                    stderr_thread.join(timeout=1)
                    return False, "", f"Agent execution timed out after {self.timeout}s", -1, False
                time.sleep(0.1)
            
            returncode = process.poll()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            
            output = ''.join(stdout_lines)
            error = ''.join(stderr_lines)
            success = returncode == 0
            changes = "No changes" not in output and returncode == 0
            
            return success, output, error, returncode, changes
        except FileNotFoundError:
            return False, "", "aider not found. Install with: pip install aider-chat", -1, False
    
    def _run_claude_code(self, prompt: str, files: Optional[list] = None) -> Tuple[bool, str, str, int, bool]:
        cmd = ["claude-code", *self.agent_args, "--prompt", prompt]
        
        if files:
            cmd.extend(["--files"] + files)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.working_dir) if self.working_dir else None,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False
            )
            
            return result.returncode == 0, result.stdout, result.stderr, result.returncode, result.returncode == 0
        except subprocess.TimeoutExpired:
            return False, "", f"Agent execution timed out after {self.timeout}s", -1, False
        except FileNotFoundError:
            return False, "", "claude-code not found in PATH", -1, False
    
    def _run_cursor(self, prompt: str, files: Optional[list] = None) -> Tuple[bool, str, str, int, bool]:
        return False, "", "Cursor agent integration not yet implemented", -1, False
    
    def _run_mock(self, prompt: str, files: Optional[list] = None) -> Tuple[bool, str, str, int, bool]:
        if not self.working_dir:
            return False, "", "mock agent requires working_dir", -1, False

        marker = self.working_dir / ".junior_dev_mock_change.txt"
        marker.write_text(
            "milestone2 mock agent change\n"
            f"timestamp: {time.time()}\n"
            f"prompt: {prompt}\n"
        )

        return True, f"Mock agent wrote {marker.name}", "", 0, True
    
    def check_agent_available(self) -> bool:
        if self.agent_type == "mock":
            return True
        
        agent_binary = None
        if self.agent_type == "aider":
            agent_binary = shutil.which("aider")
        elif self.agent_type == "claude-code":
            agent_binary = shutil.which("claude-code")
        
        if not agent_binary:
            return False
        
        try:
            result = subprocess.run(
                [agent_binary, "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

