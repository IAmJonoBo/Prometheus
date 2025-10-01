#!/usr/bin/env bash
#
# verify_artifacts.sh - Verify offline packaging artifacts are properly built
#
# This script validates that the CI-built artifacts contain all necessary
# components for offline installation, preventing issues like PR #90 where
# the wheelhouse had metadata but no actual wheel files.
#
# Usage:
#   scripts/verify_artifacts.sh [artifact-dir]
#
# Environment variables:
#   ARTIFACT_DIR    Directory containing extracted CI artifacts (default: dist)
#   VERBOSE         Set to "true" for detailed output (default: false)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARTIFACT_DIR="${1:-${ARTIFACT_DIR:-${REPO_ROOT}/dist}}"
VERBOSE="${VERBOSE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Track validation results
ERRORS=0
WARNINGS=0
CHECKS=0

log_info() {
	printf '%bℹ %b%s\n' "${BLUE}" "${NC}" "$1"
}

log_success() {
	printf '%b✓ %b%s\n' "${GREEN}" "${NC}" "$1"
	CHECKS=$((CHECKS + 1))
}

log_warning() {
	printf '%b⚠ %b%s\n' "${YELLOW}" "${NC}" "$1"
	WARNINGS=$((WARNINGS + 1))
	CHECKS=$((CHECKS + 1))
}

log_error() {
	printf '%b✗ %b%s\n' "${RED}" "${NC}" "$1"
	ERRORS=$((ERRORS + 1))
	CHECKS=$((CHECKS + 1))
}

verbose() {
	if [[ ${VERBOSE} == "true" ]]; then
		printf "  %s\n" "$1"
	fi
}

header() {
	printf '\n%b═══ %s ═══%b\n' "${BLUE}" "$1" "${NC}"
}

# Validate artifact directory exists
validate_artifact_dir() {
	header "Validating Artifact Directory"

	if [[ ! -d ${ARTIFACT_DIR} ]]; then
		log_error "Artifact directory not found: ${ARTIFACT_DIR}"
		return 1
	fi

	log_success "Artifact directory exists: ${ARTIFACT_DIR}"
	verbose "$(ls -lh "${ARTIFACT_DIR}")"
}

# Validate BUILD_INFO file
validate_build_info() {
	header "Validating Build Metadata"

	local build_info="${ARTIFACT_DIR}/BUILD_INFO"

	if [[ ! -f ${build_info} ]]; then
		log_warning "BUILD_INFO file not found"
		return 0
	fi

	log_success "BUILD_INFO file exists"
	verbose "$(cat "${build_info}")"

	# Check for required fields
	if grep -q "Build timestamp:" "${build_info}"; then
		log_success "Build timestamp present"
	else
		log_warning "Build timestamp missing from BUILD_INFO"
	fi

	if grep -q "Git SHA:" "${build_info}"; then
		log_success "Git SHA present"
	else
		log_warning "Git SHA missing from BUILD_INFO"
	fi
}

# Validate wheelhouse
validate_wheelhouse() {
	header "Validating Wheelhouse"

	local wheelhouse="${ARTIFACT_DIR}/wheelhouse"

	if [[ ! -d ${wheelhouse} ]]; then
		log_error "Wheelhouse directory not found: ${wheelhouse}"
		return 1
	fi

	log_success "Wheelhouse directory exists"

	# Check for manifest.json
	local manifest="${wheelhouse}/manifest.json"
	if [[ ! -f ${manifest} ]]; then
		log_warning "Wheelhouse manifest.json not found"
	else
		log_success "Wheelhouse manifest.json exists"

		# Parse manifest for wheel count
		if command -v jq >/dev/null 2>&1; then
			local wheel_count
			wheel_count=$(jq -r '.wheel_count // 0' "${manifest}")
			verbose "Manifest reports ${wheel_count} wheels"

			if [[ ${wheel_count} -eq 0 ]]; then
				log_error "Manifest reports 0 wheels"
			else
				log_success "Manifest reports ${wheel_count} wheels"
			fi
		fi
	fi

	# Check for requirements.txt
	local req_file="${wheelhouse}/requirements.txt"
	if [[ ! -f ${req_file} ]]; then
		log_error "requirements.txt not found in wheelhouse"
	else
		log_success "requirements.txt exists"
		local req_count
		req_count=$(wc -l <"${req_file}" | tr -d ' ')
		verbose "requirements.txt has ${req_count} lines"
	fi

	# Count actual wheel files - THIS IS THE KEY CHECK
	local wheel_files
	wheel_files=$(find "${wheelhouse}" -name "*.whl" -type f | wc -l | tr -d ' ')

	if [[ ${wheel_files} -eq 0 ]]; then
		log_error "No wheel files (.whl) found in wheelhouse! This is the PR #90 issue."
		log_error "Wheelhouse has metadata but no actual wheels - offline install will fail."
	else
		log_success "Found ${wheel_files} wheel files in wheelhouse"
		verbose "$(find "${wheelhouse}" -name "*.whl" -type f | head -5)"
		if [[ ${wheel_files} -gt 5 ]]; then
			verbose "... and $((wheel_files - 5)) more"
		fi
	fi

	# Check for pip-audit
	if find "${wheelhouse}" -name "pip_audit*.whl" -type f -print -quit | grep -q .; then
		log_success "pip-audit wheel found (enables offline security scanning)"
	else
		log_warning "pip-audit not found in wheelhouse (security scanning limited offline)"
	fi

	# Check wheelhouse size
	local wheelhouse_size
	wheelhouse_size=$(du -sh "${wheelhouse}" 2>/dev/null | cut -f1 || echo "unknown")
	log_info "Wheelhouse size: ${wheelhouse_size}"
}

# Validate Python wheel
validate_python_wheel() {
	header "Validating Python Package"

	local wheel_count
	wheel_count=$(find "${ARTIFACT_DIR}" -maxdepth 1 -name "*.whl" -type f | wc -l | tr -d ' ')

	if [[ ${wheel_count} -eq 0 ]]; then
		log_warning "No Python wheel (.whl) found in artifact root"
	else
		log_success "Found ${wheel_count} Python wheel(s) in artifact root"
		verbose "$(find "${ARTIFACT_DIR}" -maxdepth 1 -name "*.whl" -type f)"
	fi
}

# Test offline installation (if requested)
test_offline_install() {
	header "Testing Offline Installation"

	local wheelhouse="${ARTIFACT_DIR}/wheelhouse"
	local req_file="${wheelhouse}/requirements.txt"

	if [[ ! -f ${req_file} ]]; then
		log_warning "Skipping offline install test - requirements.txt not found"
		return 0
	fi

	# Create temporary venv
	local venv_dir="/tmp/test-offline-install-$$"

	log_info "Creating test virtualenv: ${venv_dir}"
	python -m venv "${venv_dir}" || {
		log_warning "Failed to create virtualenv - skipping install test"
		return 0
	}

	# shellcheck disable=SC1091
	source "${venv_dir}/bin/activate" || {
		log_warning "Failed to activate virtualenv - skipping install test"
		rm -rf "${venv_dir}"
		return 0
	}

	log_info "Attempting offline install..."
	if python -m pip install --no-index \
		--find-links "${wheelhouse}" \
		-r "${req_file}" >/dev/null 2>&1; then
		log_success "Offline installation successful"

		# Check if pip-audit is available
		if command -v pip-audit >/dev/null 2>&1; then
			log_success "pip-audit available after install"
		else
			log_warning "pip-audit not available after install"
		fi
	else
		log_error "Offline installation failed"
		log_error "Some dependencies may be missing from wheelhouse"
	fi

	deactivate
	rm -rf "${venv_dir}"
}

# Main validation flow
main() {
	printf '%b╔═══════════════════════════════════════════════════════════╗%b\n' "${BLUE}" "${NC}"
	printf '%b║  Prometheus Artifact Verification (PR #90 Prevention)    ║%b\n' "${BLUE}" "${NC}"
	printf '%b╚═══════════════════════════════════════════════════════════╝%b\n' "${BLUE}" "${NC}"

	log_info "Artifact directory: ${ARTIFACT_DIR}"
	log_info "Verbose mode: ${VERBOSE}"
	printf '\n'

	# Run validations
	validate_artifact_dir
	validate_build_info
	validate_wheelhouse
	validate_python_wheel

	# Optional: test offline install if --test flag provided
	if [[ ${1-} == "--test" ]] || [[ ${2-} == "--test" ]]; then
		test_offline_install
	fi

	# Summary
	header "Validation Summary"
	printf 'Checks run: %b%d%b\n' "${BLUE}" "${CHECKS}" "${NC}"
	printf 'Errors:     %b%d%b\n' "${RED}" "${ERRORS}" "${NC}"
	printf 'Warnings:   %b%d%b\n' "${YELLOW}" "${WARNINGS}" "${NC}"
	printf '\n'

	if [[ ${ERRORS} -gt 0 ]]; then
		printf '%b✗ Validation failed with %d error(s)%b\n' "${RED}" "${ERRORS}" "${NC}"
		printf '%bThese issues must be fixed before deploying to air-gapped environments.%b\n' "${YELLOW}" "${NC}"
		return 1
	elif [[ ${WARNINGS} -gt 0 ]]; then
		printf '%b⚠ Validation completed with %d warning(s)%b\n' "${YELLOW}" "${WARNINGS}" "${NC}"
		printf "Review warnings before deploying to production.\n"
		return 0
	else
		printf '%b✓ All validations passed!%b\n' "${GREEN}" "${NC}"
		printf "Artifacts are ready for offline deployment.\n"
		return 0
	fi
}

# Run if executed directly
if [[ ${BASH_SOURCE[0]} == "${0}" ]]; then
	main "$@"
fi
