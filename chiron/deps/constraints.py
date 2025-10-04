#!/usr/bin/env python3
"""
Hash-pinned constraints generation for reproducible builds.

Supports both uv and pip-tools for generating --require-hashes constraints.
This ensures deterministic, verifiable dependency installations.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ConstraintsConfig:
    """Configuration for constraints generation."""
    
    project_root: Path
    pyproject_path: Path
    output_path: Path
    tool: Literal["uv", "pip-tools"] = "uv"
    generate_hashes: bool = True
    include_extras: list[str] | None = None
    python_version: str | None = None


class ConstraintsGenerator:
    """Generate hash-pinned constraints for reproducible builds."""
    
    def __init__(self, config: ConstraintsConfig):
        self.config = config
        
    def generate(self) -> bool:
        """
        Generate hash-pinned constraints file.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Generating constraints using {self.config.tool}...")
        
        if self.config.tool == "uv":
            return self._generate_with_uv()
        elif self.config.tool == "pip-tools":
            return self._generate_with_pip_tools()
        else:
            logger.error(f"Unknown tool: {self.config.tool}")
            return False
    
    def _generate_with_uv(self) -> bool:
        """Generate constraints using uv."""
        uv_path = shutil.which("uv")
        if not uv_path:
            logger.error("uv not found in PATH. Install with: pip install uv")
            return False
        
        cmd = [
            uv_path,
            "pip",
            "compile",
            str(self.config.pyproject_path),
            "-o",
            str(self.config.output_path),
        ]
        
        if self.config.generate_hashes:
            cmd.append("--generate-hashes")
        
        if self.config.include_extras:
            for extra in self.config.include_extras:
                cmd.extend(["--extra", extra])
        
        if self.config.python_version:
            cmd.extend(["--python-version", self.config.python_version])
        
        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            
            if result.returncode != 0:
                logger.error(f"uv compile failed: {result.stderr}")
                return False
            
            logger.info(f"Generated constraints: {self.config.output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error running uv: {e}")
            return False
    
    def _generate_with_pip_tools(self) -> bool:
        """Generate constraints using pip-tools."""
        pip_compile = shutil.which("pip-compile")
        if not pip_compile:
            logger.error(
                "pip-compile not found. Install with: pip install pip-tools"
            )
            return False
        
        cmd = [
            pip_compile,
            str(self.config.pyproject_path),
            "--output-file",
            str(self.config.output_path),
        ]
        
        if self.config.generate_hashes:
            cmd.append("--generate-hashes")
        
        if self.config.include_extras:
            for extra in self.config.include_extras:
                cmd.extend(["--extra", extra])
        
        if self.config.python_version:
            cmd.extend(["--python-version", self.config.python_version])
        
        try:
            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=self.config.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            
            if result.returncode != 0:
                logger.error(f"pip-compile failed: {result.stderr}")
                return False
            
            logger.info(f"Generated constraints: {self.config.output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error running pip-compile: {e}")
            return False
    
    def verify_hashes(self) -> bool:
        """
        Verify that the generated constraints contain hashes.
        
        Returns:
            True if hashes are present, False otherwise
        """
        if not self.config.output_path.exists():
            logger.error(f"Constraints file not found: {self.config.output_path}")
            return False
        
        content = self.config.output_path.read_text()
        
        # Check for hash markers
        has_hashes = "--hash=sha256:" in content
        
        if not has_hashes:
            logger.warning(
                f"No hashes found in {self.config.output_path}. "
                "This may not be a hash-pinned constraints file."
            )
            return False
        
        logger.info(f"Verified hashes in {self.config.output_path}")
        return True


def generate_constraints(
    project_root: Path,
    pyproject_path: Path | None = None,
    output_path: Path | None = None,
    tool: Literal["uv", "pip-tools"] = "uv",
    include_extras: list[str] | None = None,
    python_version: str | None = None,
) -> bool:
    """
    Generate hash-pinned constraints for reproducible builds.
    
    Args:
        project_root: Root directory of the project
        pyproject_path: Path to pyproject.toml (defaults to project_root/pyproject.toml)
        output_path: Path for output constraints file (defaults to constraints.txt)
        tool: Tool to use ('uv' or 'pip-tools')
        include_extras: List of extras to include
        python_version: Target Python version
    
    Returns:
        True if successful, False otherwise
    """
    if pyproject_path is None:
        pyproject_path = project_root / "pyproject.toml"
    
    if output_path is None:
        output_path = project_root / "constraints.txt"
    
    config = ConstraintsConfig(
        project_root=project_root,
        pyproject_path=pyproject_path,
        output_path=output_path,
        tool=tool,
        generate_hashes=True,
        include_extras=include_extras,
        python_version=python_version,
    )
    
    generator = ConstraintsGenerator(config)
    if not generator.generate():
        return False
    
    return generator.verify_hashes()
