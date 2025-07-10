#!/bin/bash
# Automation Scripts for Claude Memory System OSS
# Production-ready automation for deduplication and optimization

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config.json"
VENV_DIR="${SCRIPT_DIR}/venv"
LOGS_DIR="${SCRIPT_DIR}/logs"

# Create necessary directories
mkdir -p "$LOGS_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if virtual environment exists and activate it
setup_environment() {
    if [ ! -d "$VENV_DIR" ]; then
        log "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    
    log "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    
    # Install/upgrade dependencies
    if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
        log "Installing dependencies..."
        pip install -q -r "${SCRIPT_DIR}/requirements.txt"
    fi
}

# Check configuration file
check_config() {
    if [ ! -f "$CONFIG_FILE" ]; then
        if [ -f "${SCRIPT_DIR}/config.example.json" ]; then
            warning "Config file not found. Copying from example..."
            cp "${SCRIPT_DIR}/config.example.json" "$CONFIG_FILE"
            warning "Please edit $CONFIG_FILE with your database credentials"
            exit 1
        else
            error "Configuration file $CONFIG_FILE not found"
            exit 1
        fi
    fi
}

# Run deduplication process
run_deduplication() {
    local dry_run_flag=""
    local strategy="${1:-keep_latest}"
    
    if [ "$2" = "--dry-run" ]; then
        dry_run_flag="--dry-run"
        log "Running deduplication analysis (dry run)..."
    else
        log "Running deduplication with strategy: $strategy"
    fi
    
    python3 "${SCRIPT_DIR}/deduplication_engine.py" \
        --config "$CONFIG_FILE" \
        --analyze \
        --resolve "$strategy" \
        $dry_run_flag \
        --output "${LOGS_DIR}/deduplication_$(date +%Y%m%d_%H%M%S).json" \
        2>&1 | tee "${LOGS_DIR}/deduplication.log"
    
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        success "Deduplication completed successfully"
    else
        error "Deduplication failed"
        return 1
    fi
}

# Run checkpoint filtering
run_checkpoint_filter() {
    local dry_run_flag=""
    
    if [ "$1" = "--dry-run" ]; then
        dry_run_flag="--dry-run"
        log "Running checkpoint filtering analysis (dry run)..."
    else
        log "Running checkpoint filtering..."
    fi
    
    python3 "${SCRIPT_DIR}/checkpoint_filter.py" \
        --config "$CONFIG_FILE" \
        --analyze \
        --apply \
        $dry_run_flag \
        --output "${LOGS_DIR}/checkpoint_filter_$(date +%Y%m%d_%H%M%S).json" \
        2>&1 | tee "${LOGS_DIR}/checkpoint_filter.log"
    
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        success "Checkpoint filtering completed successfully"
    else
        error "Checkpoint filtering failed"
        return 1
    fi
}

# Run effectiveness monitoring
run_monitoring() {
    log "Running effectiveness monitoring..."
    
    python3 "${SCRIPT_DIR}/effectiveness_monitor.py" \
        --config "$CONFIG_FILE" \
        --report \
        --output "${LOGS_DIR}/effectiveness_$(date +%Y%m%d_%H%M%S).json" \
        2>&1 | tee "${LOGS_DIR}/monitoring.log"
    
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        success "Monitoring completed successfully"
    else
        error "Monitoring failed"
        return 1
    fi
}

# Full optimization cycle
run_full_optimization() {
    local dry_run_flag=""
    
    if [ "$1" = "--dry-run" ]; then
        dry_run_flag="--dry-run"
        log "Running full optimization cycle (dry run)..."
    else
        log "Running full optimization cycle..."
    fi
    
    log "Step 1/3: Checkpoint filtering"
    run_checkpoint_filter $dry_run_flag
    
    log "Step 2/3: Deduplication"
    run_deduplication "keep_latest" $dry_run_flag
    
    log "Step 3/3: Effectiveness monitoring"
    run_monitoring
    
    success "Full optimization cycle completed"
}

# Generate system report
generate_report() {
    local report_file="${LOGS_DIR}/system_report_$(date +%Y%m%d_%H%M%S).txt"
    
    log "Generating system report..."
    
    {
        echo "=== CLAUDE MEMORY SYSTEM - SYSTEM REPORT ==="
        echo "Generated: $(date)"
        echo "Script directory: $SCRIPT_DIR"
        echo ""
        
        echo "=== CONFIGURATION ==="
        if [ -f "$CONFIG_FILE" ]; then
            echo "Config file: $CONFIG_FILE"
            echo "Database host: $(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['database']['host'])" 2>/dev/null || echo "N/A")"
        else
            echo "Config file: NOT FOUND"
        fi
        echo ""
        
        echo "=== RECENT LOGS ==="
        echo "Log directory: $LOGS_DIR"
        if [ -d "$LOGS_DIR" ]; then
            echo "Recent log files:"
            ls -la "$LOGS_DIR"/*.log 2>/dev/null | tail -5 || echo "No log files found"
        fi
        echo ""
        
        echo "=== PYTHON ENVIRONMENT ==="
        echo "Python version: $(python3 --version)"
        echo "Virtual environment: $VENV_DIR"
        if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
            echo "Dependencies:"
            cat "${SCRIPT_DIR}/requirements.txt" | grep -v "^#" | grep -v "^$"
        fi
        echo ""
        
        echo "=== DISK USAGE ==="
        echo "Script directory size:"
        du -sh "$SCRIPT_DIR" 2>/dev/null || echo "N/A"
        echo ""
        
    } > "$report_file"
    
    success "System report generated: $report_file"
    cat "$report_file"
}

# Show usage information
show_usage() {
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  dedup [strategy]     Run deduplication (strategies: keep_latest, merge, flag_only)"
    echo "  filter              Run checkpoint filtering"
    echo "  monitor             Run effectiveness monitoring"
    echo "  optimize            Run full optimization cycle"
    echo "  report              Generate system report"
    echo "  setup               Setup environment and dependencies"
    echo ""
    echo "Options:"
    echo "  --dry-run          Simulation mode (no actual changes)"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 setup                    # Initial setup"
    echo "  $0 dedup --dry-run         # Test deduplication"
    echo "  $0 optimize                # Full optimization"
    echo "  $0 monitor                 # Monitor effectiveness"
}

# Main execution
main() {
    case "${1:-}" in
        "setup")
            log "Setting up Claude Memory System OSS..."
            setup_environment
            check_config
            success "Setup completed!"
            ;;
        "dedup")
            check_config
            setup_environment
            run_deduplication "${2:-keep_latest}" "$3"
            ;;
        "filter")
            check_config
            setup_environment
            run_checkpoint_filter "$2"
            ;;
        "monitor")
            check_config
            setup_environment
            run_monitoring
            ;;
        "optimize")
            check_config
            setup_environment
            run_full_optimization "$2"
            ;;
        "report")
            generate_report
            ;;
        "help"|"--help"|"-h")
            show_usage
            ;;
        "")
            log "Claude Memory System - Automation Scripts"
            show_usage
            ;;
        *)
            error "Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Execute main function with all arguments
main "$@"