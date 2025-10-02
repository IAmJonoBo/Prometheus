#!/usr/bin/env bash
# Local development optimization script for LFS and wheelhouse setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
OPTIMIZE_LFS="${OPTIMIZE_LFS:-true}"
BUILD_WHEELHOUSE="${BUILD_WHEELHOUSE:-true}"
EXTRAS="${EXTRAS:-pii}"
PARALLEL_JOBS="${PARALLEL_JOBS:-$(nproc 2>/dev/null || echo 4)}"
VERBOSE="${VERBOSE:-false}"

log() {
	if [[ ${VERBOSE} == "true" ]]; then
		echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
	fi
}

info() {
	echo "[INFO] $*"
}

warn() {
	echo "[WARNING] $*"
}

error() {
	echo "[ERROR] $*" >&2
}

# Check prerequisites
check_prerequisites() {
	info "Checking prerequisites..."

	local missing_tools=()

	if ! command -v git >/dev/null 2>&1; then
		missing_tools+=("git")
	fi

	if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
		missing_tools+=("python3")
	fi

	if ! command -v poetry >/dev/null 2>&1; then
		missing_tools+=("poetry")
	fi

	if [[ ${OPTIMIZE_LFS} == "true" ]] && ! command -v git-lfs >/dev/null 2>&1; then
		missing_tools+=("git-lfs")
	fi

	if [[ ${#missing_tools[@]} -gt 0 ]]; then
		error "Missing required tools: ${missing_tools[*]}"
		echo "Please install the missing tools and try again."
		exit 1
	fi

	info "All prerequisites satisfied"
}

# Optimize Git LFS configuration for local development
optimize_lfs() {
	if [[ ${OPTIMIZE_LFS} != "true" ]]; then
		info "LFS optimization skipped"
		return 0
	fi

	info "Optimizing Git LFS configuration for local development..."

	# Configure LFS for better performance
	git config lfs.batch true
	git config lfs.transfertimeout 300
	git config lfs.activitytimeout 300
	git config lfs.dialtimeout 30
	git config lfs.concurrenttransfers "${PARALLEL_JOBS}"
	git config lfs.fetchrecentalways false

	# Set up local LFS cache optimization
	git config lfs.locksverify false        # Skip lock verification for local dev
	git config lfs.skipdownloaderrors false # Fail fast on download errors

	# Install LFS hooks if not present
	if ! git lfs install --local --skip-smudge; then
		warn "LFS hook installation failed, continuing anyway"
	fi

	# Verify LFS setup
	if [[ -f .gitattributes ]]; then
		log "Verifying LFS patterns in .gitattributes"
		lfs_files=$(git lfs track | wc -l || echo "0")
		info "LFS tracking ${lfs_files} file patterns"
	fi

	# Check for unhydrated files and offer to fetch them
	missing=$(git lfs ls-files 2>/dev/null | awk '$1 ~ /^-$/ {print $3}' | wc -l || echo "0")
	if [[ ${missing} -gt 0 ]]; then
		warn "${missing} LFS files are not hydrated locally"
		echo "To hydrate LFS files for offline development, run:"
		echo "  git lfs fetch --all && git lfs checkout"
	fi

	info "LFS optimization completed"
}

# Build local wheelhouse for offline development
build_local_wheelhouse() {
	if [[ ${BUILD_WHEELHOUSE} != "true" ]]; then
		info "Wheelhouse build skipped"
		return 0
	fi

	info "Building local wheelhouse for offline development..."

	local wheelhouse_dir="${REPO_ROOT}/vendor/wheelhouse"
	local build_script="${REPO_ROOT}/scripts/build-wheelhouse.sh"

	if [[ ! -f ${build_script} ]]; then
		error "Wheelhouse build script not found: ${build_script}"
		return 1
	fi

	# Set environment variables for local build
	export EXTRAS="${EXTRAS}"
	export INCLUDE_DEV="true"
	export CREATE_ARCHIVE="false"
	export PARALLEL_DOWNLOADS="${PARALLEL_JOBS}"
	export PREFER_BINARY="true"
	export VERBOSE="${VERBOSE}"

	# Run the build script
	log "Running wheelhouse build script with extras: ${EXTRAS}"
	if "${build_script}" "${wheelhouse_dir}"; then
		wheel_count=$(find "${wheelhouse_dir}" -name "*.whl" 2>/dev/null | wc -l || echo "0")
		wheelhouse_size=$(du -sh "${wheelhouse_dir}" 2>/dev/null | cut -f1 || echo "unknown")
		info "Wheelhouse built successfully: ${wheel_count} wheels (${wheelhouse_size})"

		# Create a convenience symlink for easy access
		if [[ ! -e "${REPO_ROOT}/wheelhouse" ]]; then
			ln -sf "vendor/wheelhouse" "${REPO_ROOT}/wheelhouse"
			info "Created convenience symlink: ./wheelhouse -> vendor/wheelhouse"
		fi
	else
		error "Wheelhouse build failed"
		return 1
	fi
}

cleanup_metadata() {
	local cleanup_script="${REPO_ROOT}/scripts/cleanup-macos-cruft.sh"
	if [[ ! -x ${cleanup_script} ]]; then
		return 0
	fi

	info "Pruning macOS metadata artefacts..."
	if cleanup_output="$(${cleanup_script} --include-git --include-poetry-env "${REPO_ROOT}" 2>&1)"; then
		if [[ -n ${cleanup_output} ]]; then
			printf '%s\n' "${cleanup_output}" | sed 's/^/[CLEANUP] /'
		fi
	else
		warn "Metadata cleanup reported issues"
	fi
}

# Set up development environment optimizations
setup_dev_environment() {
	info "Setting up development environment optimizations..."

	# Create .envrc for direnv users
	local envrc_file="${REPO_ROOT}/.envrc"
	if command -v direnv >/dev/null 2>&1 && [[ ! -f ${envrc_file} ]]; then
		cat >"${envrc_file}" <<EOF
# Optimized environment for Prometheus development
export POETRY_CACHE_DIR="\${PWD}/.cache/pypoetry"
export PIP_CACHE_DIR="\${PWD}/.cache/pip"
export PYTHONUSERBASE="\${PWD}/.cache/python-user"

# LFS optimization
export GIT_LFS_PROGRESS=1
export GIT_LFS_SKIP_SMUDGE=0

# Parallel processing
export PARALLEL_JOBS="${PARALLEL_JOBS}"
export MAKEFLAGS="-j${PARALLEL_JOBS}"

# Use local wheelhouse for offline installs
if [[ -d "\${PWD}/vendor/wheelhouse" ]]; then
    export PIP_FIND_LINKS="\${PWD}/vendor/wheelhouse"
    export PIP_NO_INDEX=1
fi
EOF
		info "Created .envrc for direnv users"
		echo "Run 'direnv allow' to activate the environment"
	fi

	# Set up pre-commit hook (uses repository-managed hooks under .githooks)
	local pre_commit_hook="${REPO_ROOT}/.git/hooks/pre-commit"
	local tracked_pre_commit="${REPO_ROOT}/.githooks/pre-commit"
	if [[ -f ${tracked_pre_commit} ]]; then
		mkdir -p "$(dirname "${pre_commit_hook}")"
		cp "${tracked_pre_commit}" "${pre_commit_hook}"
		chmod +x "${pre_commit_hook}"
		info "Installed pre-commit hook for YAML formatting, Ruff linting, and LFS guardrails"
	else
		warn "Tracked pre-commit hook not found; skipping hook installation"
	fi

	# Create helpful aliases
	local git_config_file="${REPO_ROOT}/.git/config"
	if [[ -f ${git_config_file} ]]; then
		# Add some helpful git aliases for LFS workflows
		git config alias.lfs-status 'lfs ls-files'
		git config alias.lfs-check "!git lfs ls-files | awk '\$1 ~ /^-$/ {print \$3}'"
		git config alias.lfs-fetch-all 'lfs fetch --all'
		git config alias.wheelhouse '!f() { scripts/build-wheelhouse.sh "$@"; }; f'

		info "Added helpful git aliases (lfs-status, lfs-check, lfs-fetch-all, wheelhouse)"
	fi
}

# Create development documentation
create_dev_docs() {
	info "Creating development documentation..."

	local readme_dev="${REPO_ROOT}/README-dev-setup.md"
	cat >"${readme_dev}" <<EOF
# Development Setup for Prometheus

This document describes the optimized development setup for the Prometheus repository,
including LFS and wheelhouse configuration for air-gapped development.

## Quick Start

Run the development optimization script:
\`\`\`bash
./scripts/setup-dev-optimized.sh
\`\`\`

## LFS Optimization

The repository uses Git LFS for large binary files. The optimization script configures:

- Batch transfers for better performance
- Appropriate timeouts for large files
- Concurrent transfers (${PARALLEL_JOBS} parallel)
- Local caching optimization

### Useful LFS Commands

\`\`\`bash
# Check LFS status
git lfs-status

# Check for unhydrated files
git lfs-check

# Fetch all LFS objects
git lfs-fetch-all

# Verify LFS setup
scripts/ci/verify-lfs.sh
\`\`\`

## Pre-commit Guardrails

The setup script installs a \`.git/hooks/pre-commit\` hook that removes
macOS metadata files (for example, \`.DS_Store\`, \`.AppleDouble\`, \`Icon?\`)
before each commit and restages the cleanup. The hook also surfaces
warnings for staged files larger than 10 MB so you can move them into
Git LFS.

## Wheelhouse for Offline Development

The wheelhouse contains pre-downloaded Python packages for offline development:

\`\`\`bash
# Build wheelhouse with default extras
git wheelhouse

# Build with specific extras
EXTRAS="pii,rag,llm" git wheelhouse

# Install from wheelhouse
pip install --no-index --find-links wheelhouse -r vendor/wheelhouse/requirements.txt
\`\`\`

## Environment Variables

Key environment variables for development:

- \`EXTRAS\`: Comma-separated list of Poetry extras to include (default: pii)
- \`PARALLEL_JOBS\`: Number of parallel jobs for builds (default: CPU count)
- \`OPTIMIZE_LFS\`: Enable LFS optimization (default: true)
- \`BUILD_WHEELHOUSE\`: Build wheelhouse during setup (default: true)

## Air-Gapped Development

For development without internet access:

1. Run the setup script with network access first
2. Ensure all LFS files are hydrated: \`git lfs fetch --all && git lfs checkout\`
3. Build a complete wheelhouse: \`INCLUDE_DEV=true EXTRAS="all-extras" ./scripts/build-wheelhouse.sh\`
4. Archive the vendor directory for transfer: \`tar -czf prometheus-vendor.tar.gz vendor/\`

## Troubleshooting

### LFS Issues

- **Unhydrated files**: Run \`git lfs fetch --all && git lfs checkout\`
- **Slow LFS operations**: Check network connection and LFS server status
- **Missing LFS objects**: Ensure they exist on the remote with \`git lfs ls-files --all\`

### Wheelhouse Issues

- **Missing wheels**: Rebuild with \`./scripts/build-wheelhouse.sh\`
- **Platform mismatch**: Check that wheels match your platform architecture
- **Dependency conflicts**: Update Poetry lock file and rebuild

Generated by setup-dev-optimized.sh on $(date)
EOF

	info "Created development documentation: README-dev-setup.md"
}

# Main execution
main() {
	info "Starting Prometheus development environment optimization..."
	info "Repository root: ${REPO_ROOT}"
	info "Parallel jobs: ${PARALLEL_JOBS}"

	cd "${REPO_ROOT}"

	check_prerequisites
	cleanup_metadata
	optimize_lfs
	build_local_wheelhouse
	setup_dev_environment
	create_dev_docs

	echo ""
	info "✅ Development environment optimization completed!"
	echo ""
	echo "Next steps:"
	echo "1. If using direnv: run 'direnv allow' to activate environment"
	echo "2. Install dependencies: poetry install --with dev"
	echo "3. Verify setup: poetry run python scripts/offline_package.py --dry-run"
	echo ""
	echo "For air-gapped development, see: README-dev-setup.md"
}

# Handle command line arguments
while [[ $# -gt 0 ]]; do
	case $1 in
	--no-lfs)
		OPTIMIZE_LFS="false"
		shift
		;;
	--no-wheelhouse)
		BUILD_WHEELHOUSE="false"
		shift
		;;
	--extras)
		EXTRAS="$2"
		shift 2
		;;
	--parallel-jobs)
		PARALLEL_JOBS="$2"
		shift 2
		;;
	--verbose)
		VERBOSE="true"
		shift
		;;
	--help)
		echo "Usage: $0 [options]"
		echo ""
		echo "Options:"
		echo "  --no-lfs              Skip LFS optimization"
		echo "  --no-wheelhouse       Skip wheelhouse build"
		echo "  --extras EXTRAS       Poetry extras to include (default: pii)"
		echo "  --parallel-jobs N     Number of parallel jobs (default: CPU count)"
		echo "  --verbose             Enable verbose logging"
		echo "  --help                Show this help message"
		exit 0
		;;
	*)
		error "Unknown option: $1"
		echo "Use --help for usage information"
		exit 1
		;;
	esac
done

main "$@"
