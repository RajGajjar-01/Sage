import asyncio
import os
import signal
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.sandbox import Sandbox


@dataclass(frozen=True)
class ExecutionResult:
    output: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False


class ShellExecutor:
    """Runs bash commands inside the sandboxed workspace with a hard timeout."""

    def __init__(self, sandbox: Sandbox, timeout_seconds: int = 120) -> None:
        self._sandbox = sandbox
        self._timeout_seconds = timeout_seconds

    @property
    def working_directory(self) -> Path:
        return self._sandbox.root

    async def run(self, command: str) -> ExecutionResult:
        """Sandbox-check then execute `command` via bash, always inside the workspace root."""
        self._sandbox.check_command(command)

        started = time.perf_counter()
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as script:
            script.write(command)
            script_path = script.name

        try:
            process = await asyncio.create_subprocess_exec(
                "/bin/bash",
                script_path,
                cwd=self._sandbox.root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
                env=self._child_env(),
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(), timeout=self._timeout_seconds
                )
            except TimeoutError:
                self._kill_process_group(process)
                duration_ms = int((time.perf_counter() - started) * 1000)
                return ExecutionResult(
                    "Error: command timed out.", -1, duration_ms, timed_out=True
                )

            duration_ms = int((time.perf_counter() - started) * 1000)
            output = stdout.decode(errors="replace").rstrip()
            return ExecutionResult(output, process.returncode or 0, duration_ms)
        finally:
            Path(script_path).unlink(missing_ok=True)

    @staticmethod
    def _child_env() -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("HOME", "/root")
        env["LANG"] = "en_US.UTF-8"
        return env

    @staticmethod
    def _kill_process_group(process: asyncio.subprocess.Process) -> None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
