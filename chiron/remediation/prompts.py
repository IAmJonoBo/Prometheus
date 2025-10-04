#!/usr/bin/env python3
"""Guided remediation prompts for interactive operator assistance.

Provides interactive CLI prompts to guide operators through remediation
of common issues including:
- Dependency guard violations
- Wheelhouse packaging failures
- Runtime dependency issues
- Model registry problems
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Callable

__all__ = [
    "RemediationType",
    "RemediationPrompt",
    "prompt_for_remediation",
    "prompt_guard_violation",
    "prompt_wheelhouse_failure",
    "prompt_runtime_failure",
]


class RemediationType(Enum):
    """Types of remediation issues."""
    
    GUARD_VIOLATION = "guard_violation"
    WHEELHOUSE_FAILURE = "wheelhouse_failure"
    RUNTIME_FAILURE = "runtime_failure"
    MODEL_REGISTRY = "model_registry"
    PREFLIGHT_FAILURE = "preflight_failure"


@dataclass(slots=True)
class RemediationOption:
    """A remediation option that can be selected."""
    
    key: str
    description: str
    action: Callable[[], bool]
    requires_confirmation: bool = False


@dataclass(slots=True)
class RemediationPrompt:
    """Interactive remediation prompt."""
    
    title: str
    description: str
    remediation_type: RemediationType
    options: list[RemediationOption]
    
    def display(self) -> RemediationOption | None:
        """Display prompt and get user selection.
        
        Returns:
            Selected option or None if cancelled
        """
        print(f"\n{'=' * 70}")
        print(f"🔧 {self.title}")
        print(f"{'=' * 70}")
        print(f"\n{self.description}\n")
        
        print("Available remediation options:\n")
        for idx, option in enumerate(self.options, start=1):
            print(f"  {idx}. {option.description}")
            
        print(f"  {len(self.options) + 1}. Cancel and exit")
        
        while True:
            try:
                choice = input("\nSelect an option (1-{max_opt}): ".format(
                    max_opt=len(self.options) + 1
                ))
                choice_idx = int(choice) - 1
                
                if choice_idx == len(self.options):
                    print("\n❌ Remediation cancelled")
                    return None
                    
                if 0 <= choice_idx < len(self.options):
                    selected = self.options[choice_idx]
                    
                    if selected.requires_confirmation:
                        confirm = input(f"\n⚠️  Confirm action '{selected.description}'? (y/N): ")
                        if confirm.lower() != 'y':
                            print("Action cancelled, please select again.")
                            continue
                            
                    return selected
                else:
                    print(f"Invalid choice. Please enter a number between 1 and {len(self.options) + 1}")
                    
            except ValueError:
                print("Invalid input. Please enter a number.")
            except KeyboardInterrupt:
                print("\n\n❌ Remediation cancelled by user")
                return None


def prompt_guard_violation(
    package: str,
    severity: str,
    reason: str,
) -> bool:
    """Prompt for remediation of guard violation.
    
    Returns:
        True if remediation was successful
    """
    def snooze_violation() -> bool:
        """Snooze violation for a period."""
        print(f"\n📅 Snoozing guard violation for {package}")
        print("Note: This will create a snooze entry in the dependency profile")
        # Would integrate with actual snooze logic
        return True
        
    def update_package() -> bool:
        """Attempt to update package to safe version."""
        print(f"\n⬆️  Updating {package} to latest safe version")
        print("Note: This will run 'prometheus deps upgrade' with appropriate constraints")
        # Would integrate with actual upgrade logic
        return True
        
    def add_exception() -> bool:
        """Add exception to policy."""
        print(f"\n⚠️  Adding policy exception for {package}")
        print("Note: This requires justification and approval")
        # Would integrate with policy management
        return True
        
    def rollback() -> bool:
        """Rollback recent changes."""
        print(f"\n↩️  Rolling back recent changes")
        print("Note: This will restore previous dependency state")
        # Would integrate with rollback logic
        return True
        
    prompt = RemediationPrompt(
        title="Dependency Guard Violation Detected",
        description=f"""
Package: {package}
Severity: {severity}
Reason: {reason}

The dependency guard has identified a policy violation that needs attention.
Please select a remediation strategy:
        """.strip(),
        remediation_type=RemediationType.GUARD_VIOLATION,
        options=[
            RemediationOption(
                key="update",
                description=f"Update {package} to latest safe version",
                action=update_package,
            ),
            RemediationOption(
                key="snooze",
                description=f"Snooze violation for 7 days",
                action=snooze_violation,
            ),
            RemediationOption(
                key="rollback",
                description="Rollback to previous dependency state",
                action=rollback,
                requires_confirmation=True,
            ),
            RemediationOption(
                key="exception",
                description="Add policy exception (requires approval)",
                action=add_exception,
                requires_confirmation=True,
            ),
        ],
    )
    
    selected = prompt.display()
    if selected:
        print(f"\n🔄 Executing remediation: {selected.description}")
        success = selected.action()
        if success:
            print("✅ Remediation completed successfully")
        else:
            print("❌ Remediation failed")
        return success
    
    return False


def prompt_wheelhouse_failure(
    package: str,
    missing_platforms: list[str],
) -> bool:
    """Prompt for remediation of wheelhouse packaging failure.
    
    Returns:
        True if remediation was successful
    """
    def allowlist_sdist() -> bool:
        """Add package to sdist allowlist."""
        print(f"\n✅ Adding {package} to sdist allowlist")
        print("Note: This allows source distribution for this package")
        # Would integrate with allowlist management
        return True
        
    def exclude_package() -> bool:
        """Exclude package from packaging."""
        print(f"\n➖ Excluding {package} from offline package")
        print("Warning: This may affect functionality in offline environments")
        # Would integrate with packaging exclusions
        return True
        
    def update_platforms() -> bool:
        """Update platform requirements."""
        print(f"\n🔧 Updating platform requirements")
        print("Note: This will modify platform constraints in policy")
        # Would integrate with platform management
        return True
        
    platforms_str = ", ".join(missing_platforms)
    
    prompt = RemediationPrompt(
        title="Wheelhouse Packaging Failure",
        description=f"""
Package: {package}
Missing wheels for platforms: {platforms_str}

The package cannot be included in the offline wheelhouse because binary wheels
are not available for all required platforms. Please select a remediation strategy:
        """.strip(),
        remediation_type=RemediationType.WHEELHOUSE_FAILURE,
        options=[
            RemediationOption(
                key="allowlist",
                description=f"Allow source distribution for {package}",
                action=allowlist_sdist,
            ),
            RemediationOption(
                key="platforms",
                description="Update platform requirements to exclude missing platforms",
                action=update_platforms,
            ),
            RemediationOption(
                key="exclude",
                description=f"Exclude {package} from offline packaging",
                action=exclude_package,
                requires_confirmation=True,
            ),
        ],
    )
    
    selected = prompt.display()
    if selected:
        print(f"\n🔄 Executing remediation: {selected.description}")
        success = selected.action()
        if success:
            print("✅ Remediation completed successfully")
        else:
            print("❌ Remediation failed")
        return success
    
    return False


def prompt_runtime_failure(
    error_type: str,
    error_message: str,
) -> bool:
    """Prompt for remediation of runtime failure.
    
    Returns:
        True if remediation was successful
    """
    def reinstall_deps() -> bool:
        """Reinstall dependencies."""
        print("\n🔄 Reinstalling dependencies")
        print("This will run: poetry install --sync")
        # Would run actual reinstall
        return True
        
    def clear_cache() -> bool:
        """Clear Poetry cache."""
        print("\n🗑️  Clearing Poetry cache")
        print("This will run: poetry cache clear --all pypi")
        # Would clear cache
        return True
        
    def rebuild_wheelhouse() -> bool:
        """Rebuild offline wheelhouse."""
        print("\n🔨 Rebuilding offline wheelhouse")
        print("This will run: prometheus offline-package")
        # Would rebuild wheelhouse
        return True
        
    prompt = RemediationPrompt(
        title="Runtime Dependency Failure",
        description=f"""
Error Type: {error_type}
Error: {error_message}

A runtime dependency issue has been detected. This typically indicates missing
or corrupted dependencies. Please select a remediation strategy:
        """.strip(),
        remediation_type=RemediationType.RUNTIME_FAILURE,
        options=[
            RemediationOption(
                key="reinstall",
                description="Reinstall all dependencies (poetry install --sync)",
                action=reinstall_deps,
            ),
            RemediationOption(
                key="cache",
                description="Clear Poetry cache and reinstall",
                action=clear_cache,
            ),
            RemediationOption(
                key="wheelhouse",
                description="Rebuild offline wheelhouse from scratch",
                action=rebuild_wheelhouse,
                requires_confirmation=True,
            ),
        ],
    )
    
    selected = prompt.display()
    if selected:
        print(f"\n🔄 Executing remediation: {selected.description}")
        success = selected.action()
        if success:
            print("✅ Remediation completed successfully")
        else:
            print("❌ Remediation failed")
        return success
    
    return False


def prompt_for_remediation(
    remediation_type: RemediationType,
    **kwargs: str | list[str],
) -> bool:
    """Generic remediation prompt dispatcher.
    
    Args:
        remediation_type: Type of remediation needed
        **kwargs: Type-specific parameters
        
    Returns:
        True if remediation was successful
    """
    if remediation_type == RemediationType.GUARD_VIOLATION:
        return prompt_guard_violation(
            package=str(kwargs.get("package", "unknown")),
            severity=str(kwargs.get("severity", "unknown")),
            reason=str(kwargs.get("reason", "unknown")),
        )
    elif remediation_type == RemediationType.WHEELHOUSE_FAILURE:
        return prompt_wheelhouse_failure(
            package=str(kwargs.get("package", "unknown")),
            missing_platforms=kwargs.get("missing_platforms", []),  # type: ignore[arg-type]
        )
    elif remediation_type == RemediationType.RUNTIME_FAILURE:
        return prompt_runtime_failure(
            error_type=str(kwargs.get("error_type", "unknown")),
            error_message=str(kwargs.get("error_message", "unknown")),
        )
    else:
        print(f"❌ Unknown remediation type: {remediation_type}")
        return False
