#!/usr/bin/env bash
# Enhanced LFS verification with performance optimizations for air-gapped environments
set -euo pipefail

# Configuration
LFS_TIMEOUT="${LFS_TIMEOUT:-300}"
LFS_RETRIES="${LFS_RETRIES:-3}"
LFS_BATCH_SIZE="${LFS_BATCH_SIZE:-100}"
VERBOSE="${VERBOSE:-false}"

log() {
    if [[ "${VERBOSE}" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
    fi
}

error() {
    echo "[ERROR] $*" >&2
}

warn() {
    echo "[WARNING] $*" >&2
}

# Check if git-lfs is installed
if ! command -v git-lfs >/dev/null 2>&1; then
	error "git-lfs not installed"
	exit 2
fi

# Configure LFS for better performance
log "Configuring LFS for optimal performance"
git config lfs.batch true
git config lfs.transfertimeout "${LFS_TIMEOUT}"
git config lfs.activitytimeout "${LFS_TIMEOUT}"
git config lfs.dialtimeout 30
git config lfs.concurrenttransfers 8
git config lfs.fetchrecentalways false

# Verify LFS installation
log "Verifying LFS installation"
git lfs version

# Check for unhydrated LFS pointers
log "Scanning for unhydrated LFS pointers"
missing=$(git lfs ls-files 2>/dev/null | awk '$1 ~ /^-$/ {print $3}' || true)

if [[ -n ${missing} ]]; then
	warn "Detected unhydrated LFS pointers:"
	echo "${missing}" | while IFS= read -r file; do
		echo "  - ${file}"
	done >&2
	
	echo "Attempting hydration with retry logic..." >&2
	
	# Attempt to fetch with retries
	retry_count=0
	while [[ ${retry_count} -lt ${LFS_RETRIES} ]]; do
		log "LFS fetch attempt $((retry_count + 1)) of ${LFS_RETRIES}"
		
		if timeout "${LFS_TIMEOUT}" git lfs fetch --all --verbose; then
			log "LFS fetch successful"
			break
		else
			retry_count=$((retry_count + 1))
			if [[ ${retry_count} -lt ${LFS_RETRIES} ]]; then
				warn "LFS fetch attempt ${retry_count} failed, retrying in 10 seconds..."
				sleep 10
			else
				error "All LFS fetch attempts failed"
			fi
		fi
	done
	
	# Attempt checkout with error handling
	log "Attempting LFS checkout"
	if ! git lfs checkout; then
		warn "LFS checkout encountered issues, attempting pull"
		if ! git lfs pull; then
			error "LFS pull also failed, some objects may remain unhydrated"
		fi
	fi
	
	# Verify hydration after attempts
	log "Verifying hydration status after fetch attempts"
	missing_after=$(git lfs ls-files 2>/dev/null | awk '$1 ~ /^-$/ {print $3}' || true)
	if [[ -n ${missing_after} ]]; then
		error "LFS hydration incomplete. Remaining unhydrated files:"
		echo "${missing_after}" | while IFS= read -r file; do
			echo "  - ${file}"
		done >&2
		
		# Check if we're in an air-gapped environment
		if ! curl -s --connect-timeout 5 https://github.com >/dev/null 2>&1; then
			warn "Detected air-gapped environment. Consider pre-downloading LFS objects."
			warn "Run 'git lfs fetch --all' in an environment with network access first."
		fi
		
		exit 3
	fi
fi

# Additional verification: check LFS storage usage
log "Checking LFS storage information"
if lfs_info=$(git lfs env 2>/dev/null); then
	echo "LFS Environment:" >&2
	echo "${lfs_info}" | grep -E "(Endpoint|LocalWorkingDir|LocalGitDir|LocalMediaDir)" >&2 || true
fi

# Check for LFS locks (which could interfere with air-gapped usage)
log "Checking for LFS locks"
if locks=$(git lfs locks 2>/dev/null); then
	if [[ -n ${locks} ]]; then
		warn "LFS locks detected (may interfere with air-gapped usage):"
		echo "${locks}" >&2
	fi
fi

# Verify specific patterns from .gitattributes
log "Verifying LFS patterns from .gitattributes"
if [[ -f .gitattributes ]]; then
	# Extract LFS patterns
	lfs_patterns=$(grep "filter=lfs" .gitattributes | awk '{print $1}' | head -10)
	if [[ -n ${lfs_patterns} ]]; then
		echo "Configured LFS patterns:" >&2
		echo "${lfs_patterns}" | while IFS= read -r pattern; do
			echo "  - ${pattern}"
			# Count files matching this pattern
			count=$(find . -path "./.git" -prune -o -path "${pattern}" -type f -print 2>/dev/null | wc -l || echo "0")
			echo "    (${count} files match)"
		done >&2
	fi
fi

# Performance metrics
if [[ -d .git/lfs ]]; then
	lfs_dir_size=$(du -sh .git/lfs 2>/dev/null | cut -f1 || echo "unknown")
	log "LFS cache size: ${lfs_dir_size}"
fi

echo "LFS verification passed." >&2
log "LFS verification completed successfully"
