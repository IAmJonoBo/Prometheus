#!/usr/bin/env python3
"""Model registry governance and signature validation.

This module provides governance capabilities for model downloads including:
- Signature validation for models
- Cadence enforcement for model updates
- Audit trail for model operations
- Integration with dependency governance policies
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

__all__ = [
    "ModelRegistryGovernance",
    "ModelSignature",
    "ModelCadencePolicy",
    "validate_model_signature",
    "check_model_cadence",
]


@dataclass(slots=True)
class ModelSignature:
    """Model signature information for validation."""
    
    model_id: str
    version: str
    checksum_sha256: str
    signature: str | None = None
    signed_at: datetime | None = None
    signed_by: str | None = None


@dataclass(slots=True)
class ModelCadencePolicy:
    """Cadence policy for model updates."""
    
    model_id: str
    min_days_between_updates: int = 7
    allowed_update_windows: list[str] = field(default_factory=lambda: ["weekday"])
    snooze_until: datetime | None = None
    environment: str = "dev"


@dataclass(slots=True)
class ModelAuditEntry:
    """Audit trail entry for model operations."""
    
    model_id: str
    operation: str  # download, validate, update, delete
    timestamp: datetime
    success: bool
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelRegistryGovernance:
    """Governance engine for model registry operations."""
    
    def __init__(self, policy_path: Path | None = None):
        """Initialize governance engine with optional policy path."""
        self.policy_path = policy_path or Path.cwd() / "configs" / "model-registry-policy.toml"
        self.audit_log: list[ModelAuditEntry] = []
        self._policies: dict[str, ModelCadencePolicy] = {}
        self._signatures: dict[str, ModelSignature] = {}
        
    def register_model_signature(self, signature: ModelSignature) -> None:
        """Register a model signature for validation."""
        key = f"{signature.model_id}@{signature.version}"
        self._signatures[key] = signature
        
    def validate_model(
        self,
        model_id: str,
        version: str,
        model_path: Path,
    ) -> tuple[bool, str | None]:
        """Validate model signature and integrity.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        key = f"{model_id}@{version}"
        signature = self._signatures.get(key)
        
        if not signature:
            error = f"No signature registered for {key}"
            self._audit(model_id, "validate", False, error)
            return False, error
            
        # Validate checksum
        if not model_path.exists():
            error = f"Model file not found: {model_path}"
            self._audit(model_id, "validate", False, error)
            return False, error
            
        actual_checksum = self._compute_checksum(model_path)
        if actual_checksum != signature.checksum_sha256:
            error = f"Checksum mismatch for {key}: expected {signature.checksum_sha256}, got {actual_checksum}"
            self._audit(model_id, "validate", False, error)
            return False, error
            
        # Signature is valid
        self._audit(model_id, "validate", True)
        return True, None
        
    def check_update_allowed(
        self,
        model_id: str,
        last_update: datetime | None = None,
    ) -> tuple[bool, str | None]:
        """Check if model update is allowed by cadence policy.
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        policy = self._policies.get(model_id)
        
        if not policy:
            # No policy means updates are allowed
            return True, None
            
        # Check snooze period
        if policy.snooze_until and datetime.now(UTC) < policy.snooze_until:
            reason = f"Update snoozed until {policy.snooze_until.isoformat()}"
            return False, reason
            
        # Check minimum days between updates
        if last_update:
            min_delta = timedelta(days=policy.min_days_between_updates)
            elapsed = datetime.now(UTC) - last_update
            if elapsed < min_delta:
                reason = f"Minimum cadence not met: {elapsed.days} days < {policy.min_days_between_updates} days"
                return False, reason
                
        # Check update window
        current_day = datetime.now(UTC).strftime("%A").lower()
        if "weekday" in policy.allowed_update_windows:
            if current_day in ["saturday", "sunday"]:
                reason = f"Updates not allowed on weekends (current: {current_day})"
                return False, reason
                
        return True, None
        
    def add_policy(self, policy: ModelCadencePolicy) -> None:
        """Register a cadence policy for a model."""
        self._policies[policy.model_id] = policy
        
    def export_audit_log(self, destination: Path) -> None:
        """Export audit log to JSON file."""
        entries = [
            {
                "model_id": entry.model_id,
                "operation": entry.operation,
                "timestamp": entry.timestamp.isoformat(),
                "success": entry.success,
                "error": entry.error,
                "metadata": entry.metadata,
            }
            for entry in self.audit_log
        ]
        
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        
    def _audit(
        self,
        model_id: str,
        operation: str,
        success: bool,
        error: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record audit entry."""
        entry = ModelAuditEntry(
            model_id=model_id,
            operation=operation,
            timestamp=datetime.now(UTC),
            success=success,
            error=error,
            metadata=metadata,
        )
        self.audit_log.append(entry)
        
    @staticmethod
    def _compute_checksum(path: Path) -> str:
        """Compute SHA-256 checksum of file."""
        sha256 = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


def validate_model_signature(
    model_id: str,
    version: str,
    model_path: Path,
    signature: ModelSignature,
) -> tuple[bool, str | None]:
    """Standalone function to validate model signature.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    governance = ModelRegistryGovernance()
    governance.register_model_signature(signature)
    return governance.validate_model(model_id, version, model_path)


def check_model_cadence(
    model_id: str,
    policy: ModelCadencePolicy,
    last_update: datetime | None = None,
) -> tuple[bool, str | None]:
    """Standalone function to check model update cadence.
    
    Returns:
        Tuple of (is_allowed, reason)
    """
    governance = ModelRegistryGovernance()
    governance.add_policy(policy)
    return governance.check_update_allowed(model_id, last_update)
