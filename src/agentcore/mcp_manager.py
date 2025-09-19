"""Utilities to deploy Model Context Protocol (MCP) adapters."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .config import MCPRepositoryConfig


@dataclass
class MCPRepositoryInstaller:
    """Clones and prepares MCP servers for use inside AgentCore."""

    repositories: Iterable[MCPRepositoryConfig]
    install_dir: Path

    def install(self) -> List[Path]:
        installed_paths: List[Path] = []
        self.install_dir.mkdir(parents=True, exist_ok=True)
        for repo in self.repositories:
            repo_dir = self.install_dir / repo.name
            if repo_dir.exists():
                continue
            subprocess.check_call(["git", "clone", repo.git_url, str(repo_dir)])
            subprocess.check_call(["git", "checkout", repo.revision], cwd=repo_dir)
            if repo.startup_command:
                subprocess.check_call(repo.startup_command, cwd=repo_dir)
            installed_paths.append(repo_dir)
        return installed_paths


@dataclass
class MCPBootstrapper:
    """Registers MCP servers with Strands agent runtime."""

    installer: MCPRepositoryInstaller

    def bootstrap(self) -> List[dict]:
        repositories = self.installer.install()
        descriptors: List[dict] = []
        for repo_dir in repositories:
            manifest_path = repo_dir / "mcp-manifest.json"
            if not manifest_path.exists():
                raise FileNotFoundError(f"MCP manifest missing in {repo_dir}")
            descriptors.append(
                {
                    "name": repo_dir.name,
                    "manifest_path": str(manifest_path),
                }
            )
        return descriptors
