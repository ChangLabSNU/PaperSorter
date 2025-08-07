#!/bin/bash
# Example cron wrapper script for PaperSorter broadcast task
# Copy and customize this script for your environment

# Set your PaperSorter command
# For system-wide installation:
PAPERSORTER_CMD="papersorter"
# For virtual environment:
# PAPERSORTER_CMD="/path/to/venv/bin/papersorter"
# For conda environment:
# PAPERSORTER_CMD="conda run -n myenv papersorter"

# Configuration
PAPERSORTER_DIR="/path/to/papersorter"
LOGFILE="background-updates.log"
CONFIG_FILE="./config.yml"

# Change to PaperSorter directory
cd "$PAPERSORTER_DIR" || exit 1

# Function to rotate logs when they get too large
rotate_logs() {
    # Check if log file exists and is larger than 50MB
    if [ -f "$LOGFILE" ] && [ $(stat -c%s "$LOGFILE") -gt 52428800 ]; then
        echo "$(date): Rotating log file (size: $(stat -c%s "$LOGFILE") bytes)" >> "$LOGFILE"

        # Remove oldest compressed log if we have 5 or more
        if [ $(ls -1 ${LOGFILE}.*.gz 2>/dev/null | wc -l) -ge 5 ]; then
            oldest_log=$(ls -1t ${LOGFILE}.*.gz | tail -1)
            rm -f "$oldest_log"
        fi

        # Rotate and compress current log
        timestamp=$(date +%Y%m%d_%H%M%S)
        mv "$LOGFILE" "${LOGFILE}.${timestamp}"
        gzip "${LOGFILE}.${timestamp}"

        # Create new log file
        touch "$LOGFILE"
        echo "$(date): Log rotated. Previous log compressed as ${LOGFILE}.${timestamp}.gz" >> "$LOGFILE"
    fi
}

$PAPERSORTER_CMD broadcast \
    --config "$CONFIG_FILE" \
    --log-file "$LOGFILE" \
    --quiet

# Rotate logs if needed
rotate_logs