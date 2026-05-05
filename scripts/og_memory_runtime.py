#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def _load_sourced_env(root: Path) -> dict[str, str]:
    parent_env = root.parent / "source_ogmem_env.sh"
    if not parent_env.is_file():
        return {}
    cmd = (
        f"source {shlex_quote(str(parent_env))} >/dev/null 2>&1; "
        "python3 - <<'PY'\n"
        "import json, os\n"
        "keys = [\n"
        "  'EMBEDDING_PROVIDER', 'OGMEM_EMBEDDING_MODEL', 'OGMEM_EMBEDDING_BASE_URL',\n"
        "  'OGMEM_EMBEDDING_API_KEY', 'OGMEM_START_LOCAL_EMBED_SERVER', 'VECTOR_DB_TYPE',\n"
        "  'OGMEM_CODE_TOGGLE', 'OGMEM_CODE_SEARCH_CANDIDATE_MAX_FILES',\n"
        "  'OGMEM_CODE_SEARCH_EMBED_MAX_FILES', 'OGMEM_BOOTSTRAP_MAX_FILES',\n"
        "  'OGMEM_BOOTSTRAP_FULL_INDEX_CAP_FILES', 'OPENAI_API_KEY', 'OPENAI_BASE_URL'\n"
        "]\n"
        "print(json.dumps({k: os.environ[k] for k in keys if k in os.environ}))\n"
        "PY"
    )
    result = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout or "{}")


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _extract_port(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port is not None:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _wait_http(url: str, timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


def _port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) != 0


def _find_agfs_bin(root: Path) -> str:
    explicit = os.environ.get("AGFS_BIN")
    if explicit and shutil.which(explicit):
        return explicit
    local = root / "agfs" / "build" / "agfs-server"
    if local.is_file():
        return str(local)
    found = shutil.which("agfs-server")
    if found:
        return found
    raise FileNotFoundError("Could not find agfs-server; set AGFS_BIN or build agfs")


class OGMemoryRuntime:
    def __init__(self, root: Path, output_dir: Path) -> None:
        self.root = root
        self.output_dir = output_dir
        self.logs_dir = output_dir
        self.agfs_data_dir = output_dir / "agfs-data"
        self.agfs_config = output_dir / "agfs-config.yaml"
        self.agfs_log = output_dir / "agfs-server.log"
        self.server_log = output_dir / "og-memory-server.log"
        self.mcp_json = output_dir / "mcp-og-memory.json"
        self.processes: list[subprocess.Popen[str]] = []
        self.env = self._build_env()

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(_load_sourced_env(self.root))
        env.setdefault("PYTHONPATH", str(self.root))
        if str(self.root) not in env["PYTHONPATH"].split(os.pathsep):
            env["PYTHONPATH"] = f"{self.root}{os.pathsep}{env['PYTHONPATH']}"
        env.setdefault("NO_PROXY", "127.0.0.1,localhost")
        env.setdefault("no_proxy", "127.0.0.1,localhost")
        env.setdefault("OGMEM_HTTP_PORT", "8090")
        env.setdefault("OG_MEMORY_URL", f"http://127.0.0.1:{env['OGMEM_HTTP_PORT']}")
        env.setdefault("OG_MEMORY_ACCOUNT_ID", "acct-demo")
        env.setdefault("OG_MEMORY_USER_ID", "u-claude")
        env.setdefault("OG_MEMORY_AGENT_ID", "claude-code")
        env.setdefault("AGFS_BASE_URL", "http://127.0.0.1:1833")
        env.setdefault("VECTOR_DB_TYPE", env.get("VECTOR_DB_TYPE", "memory"))
        env.setdefault("OGMEM_CODE_TOGGLE", env.get("OGMEM_CODE_TOGGLE", "1"))
        env.setdefault("EMBEDDING_PROVIDER", env.get("EMBEDDING_PROVIDER", "openai"))
        env.setdefault("OGMEM_EMBEDDING_MODEL", env.get("OGMEM_EMBEDDING_MODEL", "text-embedding-3-large"))
        env.setdefault("OGMEM_EMBEDDING_BASE_URL", env.get("OGMEM_EMBEDDING_BASE_URL", "https://api.openai-proxy.org"))
        env.setdefault("OGMEM_START_LOCAL_EMBED_SERVER", env.get("OGMEM_START_LOCAL_EMBED_SERVER", "0"))
        env.setdefault("OGMEM_CODE_SEARCH_CANDIDATE_MAX_FILES", env.get("OGMEM_CODE_SEARCH_CANDIDATE_MAX_FILES", "40"))
        env.setdefault("OGMEM_CODE_SEARCH_EMBED_MAX_FILES", env.get("OGMEM_CODE_SEARCH_EMBED_MAX_FILES", "20"))
        env.setdefault("OGMEM_BOOTSTRAP_MAX_FILES", env.get("OGMEM_BOOTSTRAP_MAX_FILES", "40"))
        env.setdefault("OGMEM_BOOTSTRAP_FULL_INDEX_CAP_FILES", env.get("OGMEM_BOOTSTRAP_FULL_INDEX_CAP_FILES", "40"))
        env.setdefault("CLAUDE_CODE_DEBUG_LOG_LEVEL", env.get("CLAUDE_CODE_DEBUG_LOG_LEVEL", "debug"))
        model = env.get("OGMEM_EMBEDDING_MODEL", "").lower()
        if env.get("OGMEM_FORCE_EMBED_DIM_ALIGN", "1") == "1":
            if "text-embedding-3-large" in model:
                env["OPENGAUSS_DIMENSION"] = "3072"
            elif "text-embedding-3-small" in model or "text-embedding-ada-002" in model:
                env["OPENGAUSS_DIMENSION"] = "1536"
            else:
                env["OPENGAUSS_DIMENSION"] = env.get("OPENGAUSS_DIMENSION", "384")
        return env

    def _write_configs(self) -> None:
        self.agfs_data_dir.mkdir(parents=True, exist_ok=True)
        self.agfs_config.write_text(
            "\n".join(
                [
                    "server:",
                    '  address: ":1833"',
                    "  log_level: info",
                    "plugins:",
                    "  serverinfofs:",
                    "    enabled: true",
                    "    path: /serverinfo",
                    '    config:',
                    '      version: "1.0.0"',
                    "  localfs:",
                    "    enabled: true",
                    "    path: /local",
                    "    config:",
                    f'      local_dir: "{self.agfs_data_dir}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        py_bin = shutil.which("python3") or "python3"
        cfg = {
            "mcpServers": {
                "og-memory": {
                    "command": py_bin,
                    "args": ["-m", "og_memory_mcp"],
                    "env": {
                        "PYTHONPATH": self.env["PYTHONPATH"],
                        "OG_MEMORY_URL": self.env["OG_MEMORY_URL"],
                        "OG_MEMORY_ACCOUNT_ID": self.env["OG_MEMORY_ACCOUNT_ID"],
                        "OG_MEMORY_USER_ID": self.env["OG_MEMORY_USER_ID"],
                        "OG_MEMORY_AGENT_ID": self.env["OG_MEMORY_AGENT_ID"],
                    },
                }
            }
        }
        self.mcp_json.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    def start(self) -> None:
        agfs_port = _extract_port(self.env["AGFS_BASE_URL"])
        og_port = _extract_port(self.env["OG_MEMORY_URL"])
        if not _port_is_free("127.0.0.1", agfs_port):
            raise RuntimeError(f"AGFS port {agfs_port} is already in use")
        if not _port_is_free("127.0.0.1", og_port):
            raise RuntimeError(f"oG-memory port {og_port} is already in use")

        self._write_configs()
        agfs_bin = _find_agfs_bin(self.root)
        agfs_proc = subprocess.Popen(
            [agfs_bin, "-c", str(self.agfs_config)],
            cwd=str(self.root),
            stdout=self.agfs_log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            text=True,
            env=self.env,
        )
        self.processes.append(agfs_proc)
        server_proc = subprocess.Popen(
            [shutil.which("python3") or "python3", str(self.root / "server" / "app.py")],
            cwd=str(self.root),
            stdout=self.server_log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            text=True,
            env=self.env,
        )
        self.processes.append(server_proc)

        _wait_http(f"{self.env['AGFS_BASE_URL']}/api/v1/health")
        _wait_http(f"{self.env['OG_MEMORY_URL']}/api/v1/health")

    def stop(self) -> None:
        for proc in reversed(self.processes):
            if proc.poll() is None:
                proc.terminate()
        deadline = time.time() + 10
        for proc in reversed(self.processes):
            while proc.poll() is None and time.time() < deadline:
                time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()

