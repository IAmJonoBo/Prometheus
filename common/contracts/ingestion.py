"""Ingestion stage event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .base import BaseEvent


@dataclass(slots=True, kw_only=True)
class AttachmentManifest:
    """Metadata about attachments emitted from ingestion."""

    uri: str
    content_type: str
    byte_size: int
    checksum: str


@dataclass(slots=True, kw_only=True)
class IngestionNormalised(BaseEvent):
    """Event produced once raw inputs are normalised."""

    source_system: str
    canonical_uri: str
    provenance: Dict[str, str] = field(default_factory=dict)
    pii_redactions: List[str] = field(default_factory=list)
    attachments: List[AttachmentManifest] = field(default_factory=list)
