#!/usr/bin/env python3
"""
Artifact signing and verification using Sigstore cosign.

Provides keyless signing and verification for wheelhouse bundles
and other artifacts using OIDC-based Sigstore.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SigningResult:
    """Result of signing operation."""

    success: bool
    signature_path: Path | None = None
    certificate_path: Path | None = None
    error_message: str | None = None


class CosignSigner:
    """Sign artifacts using Sigstore cosign."""

    def __init__(self, keyless: bool = True):
        """
        Initialize cosign signer.

        Args:
            keyless: Use keyless signing with OIDC (default: True)
        """
        self.keyless = keyless

    def sign_blob(
        self,
        artifact_path: Path,
        signature_output: Path | None = None,
    ) -> SigningResult:
        """
        Sign a blob (file) using cosign.

        Args:
            artifact_path: Path to artifact to sign
            signature_output: Path for signature output (default: artifact_path.sig)

        Returns:
            SigningResult with success status and paths
        """
        cosign = shutil.which("cosign")
        if not cosign:
            logger.error(
                "cosign not found. " "Install from: https://github.com/sigstore/cosign"
            )
            return SigningResult(
                success=False, error_message="cosign not found in PATH"
            )

        if not artifact_path.exists():
            logger.error(f"Artifact not found: {artifact_path}")
            return SigningResult(
                success=False, error_message=f"Artifact not found: {artifact_path}"
            )

        if signature_output is None:
            signature_output = artifact_path.with_suffix(artifact_path.suffix + ".sig")

        cmd = [
            cosign,
            "sign-blob",
            "--yes",  # Non-interactive mode
            str(artifact_path),
        ]

        # Redirect signature to file
        try:
            logger.info(f"Signing artifact: {artifact_path}")

            with signature_output.open("w") as sig_file:
                result = subprocess.run(
                    cmd,
                    stdout=sig_file,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    env={"COSIGN_EXPERIMENTAL": "1"} if self.keyless else None,
                )

            if result.returncode != 0:
                logger.error(f"Signing failed: {result.stderr}")
                return SigningResult(success=False, error_message=result.stderr)

            logger.info(f"Signed artifact: {signature_output}")
            return SigningResult(
                success=True,
                signature_path=signature_output,
            )

        except Exception as e:
            logger.error(f"Error signing artifact: {e}")
            return SigningResult(success=False, error_message=str(e))

    def verify_blob(
        self,
        artifact_path: Path,
        signature_path: Path,
        certificate_path: Path | None = None,
        certificate_identity: str | None = None,
        certificate_oidc_issuer: str | None = None,
    ) -> bool:
        """
        Verify a signed blob using cosign.

        Args:
            artifact_path: Path to artifact to verify
            signature_path: Path to signature file
            certificate_path: Path to certificate (if available)
            certificate_identity: Expected certificate identity
            certificate_oidc_issuer: Expected OIDC issuer

        Returns:
            True if verification succeeds, False otherwise
        """
        cosign = shutil.which("cosign")
        if not cosign:
            logger.error("cosign not found")
            return False

        if not artifact_path.exists():
            logger.error(f"Artifact not found: {artifact_path}")
            return False

        if not signature_path.exists():
            logger.error(f"Signature not found: {signature_path}")
            return False

        cmd = [
            cosign,
            "verify-blob",
            "--signature",
            str(signature_path),
        ]

        if certificate_path:
            cmd.extend(["--certificate", str(certificate_path)])

        if certificate_identity:
            cmd.extend(["--certificate-identity", certificate_identity])

        if certificate_oidc_issuer:
            cmd.extend(["--certificate-oidc-issuer", certificate_oidc_issuer])

        cmd.append(str(artifact_path))

        try:
            logger.info(f"Verifying artifact: {artifact_path}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                env={"COSIGN_EXPERIMENTAL": "1"} if self.keyless else None,
            )

            if result.returncode != 0:
                logger.error(f"Verification failed: {result.stderr}")
                return False

            logger.info(f"Verification succeeded: {artifact_path}")
            return True

        except Exception as e:
            logger.error(f"Error verifying artifact: {e}")
            return False


def sign_wheelhouse_bundle(
    bundle_path: Path,
    output_dir: Path | None = None,
) -> SigningResult:
    """
    Sign a wheelhouse bundle using keyless cosign.

    Args:
        bundle_path: Path to wheelhouse bundle (tar.gz)
        output_dir: Directory for signature output (default: bundle parent dir)

    Returns:
        SigningResult with success status and paths
    """
    signer = CosignSigner(keyless=True)

    if output_dir:
        signature_path = output_dir / f"{bundle_path.name}.sig"
    else:
        signature_path = bundle_path.with_suffix(bundle_path.suffix + ".sig")

    return signer.sign_blob(bundle_path, signature_path)


def verify_wheelhouse_bundle(
    bundle_path: Path,
    signature_path: Path,
) -> bool:
    """
    Verify a signed wheelhouse bundle.

    Args:
        bundle_path: Path to wheelhouse bundle
        signature_path: Path to signature file

    Returns:
        True if verification succeeds, False otherwise
    """
    signer = CosignSigner(keyless=True)
    return signer.verify_blob(bundle_path, signature_path)
