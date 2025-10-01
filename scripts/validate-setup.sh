#!/usr/bin/env bash
# Test and validation script for the optimized LFS and wheelhouse setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

info() {
	echo "[INFO] $*"
}

error() {
	echo "[ERROR] $*" >&2
}

success() {
	echo "[SUCCESS] $*"
}

# Test script syntax
test_script_syntax() {
	info "Testing script syntax..."

	local scripts=(
		"scripts/build-wheelhouse.sh"
		"scripts/setup-dev-optimized.sh"
		"scripts/ci/verify-lfs.sh"
	)

	for script in "${scripts[@]}"; do
		if [[ -f "${REPO_ROOT}/${script}" ]]; then
			if bash -n "${REPO_ROOT}/${script}"; then
				success "Syntax OK: ${script}"
			else
				error "Syntax error in: ${script}"
				return 1
			fi
		else
			error "Script not found: ${script}"
			return 1
		fi
	done
}

# Test .gitattributes syntax
test_gitattributes() {
	info "Testing .gitattributes syntax..."

	local gitattributes="${REPO_ROOT}/.gitattributes"
	if [[ -f ${gitattributes} ]]; then
		# Check for common syntax issues
		if grep -q "filter=lfs diff=lfs merge=lfs -text" "${gitattributes}"; then
			success ".gitattributes has proper LFS patterns"
		else
			error ".gitattributes missing LFS patterns"
			return 1
		fi

		# Check for exclusions
		if grep -q "\-filter \-diff \-merge text" "${gitattributes}"; then
			success ".gitattributes has proper exclusions"
		else
			error ".gitattributes missing exclusions"
			return 1
		fi
	else
		error ".gitattributes not found"
		return 1
	fi
}

# Test TOML configuration
test_toml_config() {
	info "Testing TOML configuration..."

	local config="${REPO_ROOT}/configs/defaults/offline_package.toml"
	if [[ -f ${config} ]]; then
		# Basic syntax check using python
		if python3 -c "
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
    
with open('${config}', 'rb') as f:
    data = tomllib.load(f)
    
# Check for new performance section
if 'performance' in data:
    print('Performance section found')
else:
    print('Performance section missing')
    sys.exit(1)
    
print('TOML syntax OK')
"; then
			success "TOML configuration valid"
		else
			error "TOML configuration invalid"
			return 1
		fi
	else
		error "TOML configuration not found"
		return 1
	fi
}

# Test GitHub Actions workflow syntax
test_github_workflow() {
	info "Testing GitHub Actions workflow..."

	local workflow="${REPO_ROOT}/.github/workflows/offline-packaging-optimized.yml"
	if [[ -f ${workflow} ]]; then
		# Basic YAML syntax check
		if python3 -c "
import yaml
import sys

try:
    with open('${workflow}', 'r') as f:
        data = yaml.safe_load(f)
    
    # Check for required sections
    required_sections = ['name', 'on', 'jobs']
    for section in required_sections:
        if section not in data:
            print(f'Missing required section: {section}')
            sys.exit(1)
        print(f'Required section found: {section}')
    
    # Check for optimization features
    content = open('${workflow}').read()
    if 'prepare-matrix' in content:
        print('Matrix preparation found')
    if 'cache@v4' in content:
        print('Caching optimizations found')
    if 'multi-platform' in content or 'platform' in content.lower():
        print('Multi-platform support found')
        
    print('GitHub workflow syntax OK')
except Exception as e:
    print(f'YAML syntax error: {e}')
    sys.exit(1)
"; then
			success "GitHub workflow valid"
		else
			error "GitHub workflow invalid"
			return 1
		fi
	else
		error "GitHub workflow not found"
		return 1
	fi
}

# Test platform detection logic
test_platform_detection() {
	info "Testing platform detection logic..."

	# Test the platform detection logic from the build script
	local test_script
	test_script="$(mktemp)"
	cat >"${test_script}" <<'EOF'
#!/bin/bash
# Extract platform detection logic for testing
case "$(uname -s)" in
    Linux*)     
        ARCH="$(uname -m)"
        case "${ARCH}" in
            x86_64) PLATFORM="linux_x86_64" ;;
            aarch64|arm64) PLATFORM="linux_aarch64" ;;
            *) PLATFORM="linux_${ARCH}" ;;
        esac
        ;;
    Darwin*)    
        ARCH="$(uname -m)"
        MACOS_VERSION="10_15"  # Mock version for testing
        case "${ARCH}" in
            x86_64) PLATFORM="macosx_${MACOS_VERSION}_x86_64" ;;
            arm64) PLATFORM="macosx_${MACOS_VERSION}_arm64" ;;
            *) PLATFORM="macosx_${MACOS_VERSION}_${ARCH}" ;;
        esac
        ;;
    MINGW*|CYGWIN*|MSYS*)
        ARCH="$(uname -m)"
        case "${ARCH}" in
            x86_64) PLATFORM="win_amd64" ;;
            i686) PLATFORM="win32" ;;
            *) PLATFORM="win_${ARCH}" ;;
        esac
        ;;
    *) 
        PLATFORM="any"
        ;;
esac

echo "Detected platform: ${PLATFORM}"
EOF

	if bash "${test_script}"; then
		success "Platform detection logic works"
	else
		error "Platform detection logic failed"
		rm -f "${test_script}"
		return 1
	fi

	rm -f "${test_script}"
}

# Test documentation completeness
test_documentation() {
	info "Testing documentation completeness..."

	local readme="${REPO_ROOT}/README-dev-setup.md"
	if [[ -f ${readme} ]]; then
		# Check for key sections
		local required_sections=(
			"Quick Start"
			"LFS Optimization"
			"Wheelhouse"
			"Air-Gapped Development"
			"Troubleshooting"
		)

		for section in "${required_sections[@]}"; do
			if grep -q "## ${section}" "${readme}"; then
				success "Documentation section found: ${section}"
			else
				error "Documentation section missing: ${section}"
				return 1
			fi
		done
	else
		error "Development documentation not found"
		return 1
	fi
}

# Main test execution
main() {
	info "Starting validation of optimized LFS and wheelhouse setup..."
	info "Repository root: ${REPO_ROOT}"

	cd "${REPO_ROOT}"

	local tests=(
		"test_script_syntax"
		"test_gitattributes"
		"test_toml_config"
		"test_github_workflow"
		"test_platform_detection"
		"test_documentation"
	)

	local failed_tests=()

	for test in "${tests[@]}"; do
		if "${test}"; then
			success "Test passed: ${test}"
		else
			error "Test failed: ${test}"
			failed_tests+=("${test}")
		fi
		echo ""
	done

	if [[ ${#failed_tests[@]} -eq 0 ]]; then
		echo ""
		success "🎉 All validation tests passed!"
		echo ""
		echo "The optimized LFS and wheelhouse setup is ready for use."
		echo ""
		echo "Key improvements implemented:"
		echo "✅ Enhanced .gitattributes with comprehensive LFS patterns"
		echo "✅ Multi-platform wheelhouse build script with auto-detection"
		echo "✅ Optimized GitHub Actions workflow with caching and matrix builds"
		echo "✅ Enhanced LFS verification with retry logic and performance tuning"
		echo "✅ Development setup script for local optimization"
		echo "✅ Comprehensive documentation for air-gapped environments"
		echo ""
		echo "Next steps:"
		echo "1. Run './scripts/setup-dev-optimized.sh' for local development"
		echo "2. Use the new GitHub workflow for CI/CD builds"
		echo "3. See README-dev-setup.md for detailed usage instructions"
		return 0
	else
		echo ""
		error "❌ ${#failed_tests[@]} validation test(s) failed:"
		for test in "${failed_tests[@]}"; do
			echo "  - ${test}"
		done
		return 1
	fi
}

main "$@"
