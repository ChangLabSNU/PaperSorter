# PaperSorter Examples

This directory contains example configuration and automation scripts for PaperSorter.

## Files

### config.yml
Example configuration file for PaperSorter. Copy this to your working directory and customize with your API keys and database credentials.

### Cron Wrapper Scripts

These scripts provide automated execution with log rotation:

- **cron-update.sh** - Runs the update task to fetch new articles
- **cron-broadcast.sh** - Runs the broadcast task to send Slack notifications (with time-based filtering)
- **cron-combined.sh** - Runs both update and broadcast in sequence

To use these scripts:
1. Copy to your preferred location
2. Edit the configuration variables at the top of each script
3. Make executable: `chmod +x *.sh`
4. Add to crontab (see crontab.example)

### crontab.example
Example crontab entries showing different scheduling strategies for running PaperSorter tasks.

## Usage

1. **Initial Setup**
   ```bash
   # Copy and customize configuration
   cp examples/config.yml ./config.yml
   # Edit config.yml with your API keys and settings
   ```

2. **Manual Execution**
   ```bash
   # Run tasks manually
   papersorter update --config ./config.yml
   papersorter broadcast --config ./config.yml
   ```

3. **Automated Execution**
   ```bash
   # Copy and customize cron scripts
   cp examples/cron-combined.sh ~/bin/papersorter-cron.sh
   chmod +x ~/bin/papersorter-cron.sh
   # Edit the script with your paths

   # Add to crontab
   crontab -e
   # Add: 0 */3 * * * /home/username/bin/papersorter-cron.sh
   ```

## Notes

- The cron scripts include automatic log rotation to prevent logs from growing too large
- Broadcast scripts include time-based filtering to only send notifications during working hours
- Adjust the schedules and time windows according to your preferences and timezone