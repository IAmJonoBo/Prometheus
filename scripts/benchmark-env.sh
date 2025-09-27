#!/usr/bin/env bash
# Benchmark essentials to help Prometheus auto-tune runtime defaults.
# The script prints a lightweight report with CPU, memory, GPU, and disk stats.
#
# Usage: ./scripts/benchmark-env.sh
#
# The script is safe to run repeatedly and does not require sudo.

set -euo pipefail

indent() {
	sed 's/^/  /'
}

log_section() {
	echo "[benchmark] $1"
}

collect_cpu() {
	log_section "CPU"
	if command -v sysctl >/dev/null 2>&1; then
		sysctl -n machdep.cpu.brand_string 2>/dev/null | indent
		sysctl -n hw.physicalcpu hw.logicalcpu 2>/dev/null | paste - - |
			awk '{printf "  physical_cores: %s\n  logical_cores: %s\n", $1, $2}'
	elif command -v lscpu >/dev/null 2>&1; then
		lscpu | grep -E 'Model name|Socket|Thread|Core' | indent
	else
		echo "  (lscpu/sysctl not available)"
		uname -p | indent
	fi
}

collect_mem() {
	log_section "Memory"
	if command -v sysctl >/dev/null 2>&1; then
		sysctl -n hw.memsize 2>/dev/null |
			awk '{printf "  total_bytes: %s\n", $1}'
	elif command -v free >/dev/null 2>&1; then
		free -h | awk 'NR==2 {printf "  total: %s\n  used: %s\n  free: %s\n", $2, $3, $4}'
	else
		echo "  (free/sysctl not available)"
	fi
}

collect_gpu() {
	log_section "GPU"
	if command -v nvidia-smi >/dev/null 2>&1; then
		nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | indent
	elif command -v system_profiler >/dev/null 2>&1; then
		system_profiler SPDisplaysDataType 2>/dev/null |
			awk '/Chipset Model|VRAM/ {print}' | indent
	else
		echo "  (no NVIDIA GPU detected or tooling unavailable)"
	fi
}

collect_disk() {
	log_section "Disk"
	df -h . | awk 'NR==1 {next} {printf "  mount: %s\n  size: %s\n  used: %s\n  avail: %s\n", $6, $2, $3, $4}'
}

main() {
	collect_cpu
	collect_mem
	collect_gpu
	collect_disk
}

main "$@"
