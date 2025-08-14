# Setting Up Notifications in PaperSorter

PaperSorter supports sending notifications to both Slack and Discord channels using webhooks. The system automatically detects the webhook type based on the URL and formats messages accordingly.

## Table of Contents
- [Quick Start](#quick-start)
- [Slack Setup](#slack-setup)
- [Discord Setup](#discord-setup)
- [Channel Configuration](#channel-configuration)
- [Testing Webhooks](#testing-webhooks)
- [Notification Features](#notification-features)
- [Troubleshooting](#troubleshooting)

## Quick Start

1. **Get a webhook URL** from either Slack or Discord (see platform-specific instructions below)
2. **Add the webhook** to PaperSorter via the web interface:
   - Navigate to Settings → Channels
   - Click "Add Channel"
   - Enter the webhook URL (auto-detects Slack vs Discord)
   - Set score threshold (e.g., 0.7)
   - Save and test
3. **Run broadcast** to send notifications:
   ```bash
   papersorter broadcast
   ```

## Slack Setup

### Creating a Slack Webhook

#### Method 1: Using Slack App (Recommended)

1. **Go to Slack API**: Visit [api.slack.com/apps](https://api.slack.com/apps)
2. **Create New App**: Click "Create New App" → "From scratch"
3. **Name your app**: e.g., "PaperSorter Notifications"
4. **Select workspace**: Choose your Slack workspace
5. **Enable Incoming Webhooks**:
   - Go to "Incoming Webhooks" in the left sidebar
   - Toggle "Activate Incoming Webhooks" to ON
6. **Add New Webhook**:
   - Click "Add New Webhook to Workspace"
   - Select the channel where notifications should be posted
   - Click "Allow"
7. **Copy the webhook URL**: It will look like:
   ```
   https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
   ```

#### Method 2: Using Incoming Webhooks App

1. **In Slack**: Go to your workspace → Apps → Browse Apps
2. **Search**: Find "Incoming WebHooks"
3. **Add to Slack**: Click "Add to Slack"
4. **Choose channel**: Select where to post messages
5. **Copy webhook URL**: Save the provided URL

### Slack Notification Features

When PaperSorter sends to Slack, you get:
- **Rich formatting** with Block Kit
- **Interactive buttons**:
  - Read - Opens the article
  - More Like This - Finds similar papers
  - Interested - Mark as relevant
  - Not Interested - Mark as irrelevant
- **Metadata display**:
  - QBio Score with heart emoji
  - Source with inbox emoji
  - Authors with pen emoji
- **Clickable links** for article sources

### Enabling Slack Interactivity (Optional)

To make the feedback buttons work directly in Slack:

1. **Configure your Slack App**:
   - Go to "Interactivity & Shortcuts"
   - Toggle ON "Interactivity"
2. **Set Request URL**:
   ```
   https://your-domain.com/slack-interactivity
   ```
   (Must be HTTPS)
3. **Save changes**

## Discord Setup

### Creating a Discord Webhook

1. **Open Discord**: Go to your Discord server
2. **Server Settings**: Right-click server name → Server Settings
3. **Integrations**: Click "Integrations" in the left sidebar
4. **Webhooks**: Click "Webhooks" → "New Webhook"
5. **Configure webhook**:
   - **Name**: e.g., "PaperSorter"
   - **Channel**: Select target channel
   - **Avatar** (optional): Upload PaperSorter logo
6. **Copy Webhook URL**: Click "Copy Webhook URL"
   - It will look like:
   ```
   https://discord.com/api/webhooks/1234567890/XXXXXXXXXXXXXXXXXXXX
   ```
7. **Save**: Click "Save Changes"

### Discord Notification Features

When PaperSorter sends to Discord, you get:
- **Rich embeds** with color coding:
  - 🟢 Green (score ≥ 70%)
  - 🟡 Yellow (score 40-70%)
  - 🔴 Red (score < 40%)
- **Visual indicators** for scores
- **Markdown links** for actions:
  - 📖 Read Article
  - 🔍 More Like This
  - 👍 Interested
  - 👎 Not Interested
- **Timestamp** and footer information
- **Author field** with paper authors
- **Metadata fields** showing score, source, and model

## Channel Configuration

1. **Access Settings**:
   ```
   http://localhost:5001/settings/channels
   ```

2. **Add New Channel**:
   - Click "Add Channel"
   - Fill in the form:
     - **Channel Name**: Descriptive name (e.g., "ML Papers", "Biology Research")
     - **Endpoint URL**: Your webhook URL (Slack or Discord)
     - **Score Threshold**: Minimum score to send (0.0 to 1.0)
     - **Model ID**: Which trained model to use
     - **Broadcast Limit**: Max notifications per broadcast run

3. **Channel Settings Explained**:
   - **Score Threshold**: Only papers scoring above this value are sent
     - 0.9+ = Only highly relevant papers
     - 0.7-0.9 = Relevant papers
     - 0.5-0.7 = Potentially interesting
     - <0.5 = Include everything (not recommended)
   - **Broadcast Limit**: Prevents notification spam (default: 20)
   - **Model ID**: Use different models for different topics

## Testing Webhooks

### Method 1: Web Interface Test Button

1. Go to Settings → Channels
2. Click "Test" button next to any channel
3. Check your Slack/Discord for test message

### Method 2: Command Line Test Script

```bash
# Test a Discord webhook
python test_discord_webhook.py "https://discord.com/api/webhooks/YOUR_WEBHOOK"

# Test a Slack webhook
python test_discord_webhook.py "https://hooks.slack.com/services/YOUR_WEBHOOK"
```

### Method 3: Manual API Test

```bash
# Test via API endpoint
curl -X POST http://localhost:5001/api/settings/channels/1/test \
     -H "Content-Type: application/json"
```

## Notification Features

### Automatic Webhook Detection

PaperSorter automatically detects the webhook type based on hostname:
- URLs ending with `slack.com` → Slack formatting
- URLs ending with `discord.com` or `discordapp.com` → Discord formatting
- Unknown URLs → Default to Slack formatting

### Message Content

All notifications include:
- **Paper title** and abstract/summary
- **Authors** and publication source
- **Prediction score** (0-100%)
- **Direct link** to the paper
- **Action links** for feedback and discovery

### Feedback System

The feedback buttons/links allow users to:
1. **Mark papers as interesting**: Improves model training
2. **Mark as not interesting**: Helps filter future papers
3. **Find similar papers**: Discovers related research

Feedback is stored in the database and can be used to retrain models:
```bash
papersorter train  # Incorporates feedback into model
```

## Troubleshooting

### Common Issues

#### Webhook Not Working

1. **Check URL format**:
   - Slack: Must start with `https://hooks.slack.com/`
   - Discord: Must start with `https://discord.com/api/webhooks/`

2. **Test connectivity**:
   ```bash
   curl -X POST -H "Content-Type: application/json" \
        -d '{"content":"Test"}' \
        YOUR_WEBHOOK_URL
   ```

3. **Check logs**:
   ```bash
   papersorter broadcast --log-file broadcast.log
   tail -f broadcast.log
   ```

#### No Notifications Sent

1. **Verify channel is active**:
   ```sql
   SELECT * FROM channels WHERE is_active = true;
   ```

2. **Check score threshold**:
   - Lower threshold if too high
   - Check predicted scores:
   ```sql
   SELECT pp.score, f.title 
   FROM predicted_preferences pp 
   JOIN feeds f ON pp.feed_id = f.id 
   ORDER BY pp.score DESC LIMIT 10;
   ```

3. **Check broadcast queue**:
   ```sql
   SELECT COUNT(*) FROM broadcasts 
   WHERE broadcasted_time IS NULL;
   ```

#### Discord Rate Limits

Discord webhooks have rate limits:
- **30 requests per minute** per webhook
- PaperSorter will show "rate limit" errors if exceeded
- Solution: Reduce `broadcast_limit` in channel settings

#### Slack Rate Limits

Slack is more generous but still has limits:
- **1 message per second** sustained
- Burst capability for short periods

### Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Invalid webhook URL" | Malformed URL | Check URL format and copy again |
| "404 Not Found" | Webhook deleted | Create new webhook |
| "401 Unauthorized" | Invalid token | Regenerate webhook URL |
| "429 Too Many Requests" | Rate limited | Wait and reduce broadcast_limit |
| "400 Bad Request" | Invalid message format | Check logs for details |

### Debugging

Enable debug logging:
```bash
# Verbose broadcast with log file
papersorter broadcast --log-file debug.log

# Check notification provider detection
python -c "
from PaperSorter.notification import create_notification_provider
url = 'YOUR_WEBHOOK_URL'
provider = create_notification_provider(url)
print(f'Detected provider: {provider.__class__.__name__}')
"
```

## Best Practices

1. **Separate channels by topic**: Use different webhooks for different research areas
2. **Adjust thresholds gradually**: Start high (0.8+) and lower if needed
3. **Regular model retraining**: Incorporate feedback weekly/monthly
4. **Monitor notification volume**: Avoid overwhelming channels
5. **Test webhooks after creation**: Use the test button to verify setup
6. **Use meaningful channel names**: Helps identify purpose in the UI
7. **Set appropriate broadcast limits**: 10-20 notifications per run is usually good

## Advanced Configuration

### Multiple Models per Channel

You can use different trained models for different channels:

```python
# Train specialized models
papersorter train -o model_ml.pkl      # For ML papers
papersorter train -o model_bio.pkl     # For biology papers

# Assign to channels via web UI or database
UPDATE channels SET model_id = 2 WHERE name = 'ML Papers';
UPDATE channels SET model_id = 3 WHERE name = 'Bio Research';
```

### Scheduled Broadcasts

Set up cron jobs for regular notifications:

```bash
# Morning digest at 9 AM
0 9 * * * /path/to/papersorter broadcast --config /path/to/config.yml

# Afternoon update at 3 PM
0 15 * * * /path/to/papersorter broadcast --config /path/to/config.yml

# Evening summary at 8 PM (weekdays only)
0 20 * * 1-5 /path/to/papersorter broadcast --config /path/to/config.yml
```

### Filtering by Date

Only broadcast recent papers:
```bash
# Clear old items from queue (default: 30 days)
papersorter broadcast --clear-old-days 7  # Only last week's papers
```

## Security Considerations

1. **Keep webhooks private**: Never commit webhook URLs to version control
2. **Use environment variables** for sensitive data if needed:
   ```bash
   export SLACK_WEBHOOK="https://hooks.slack.com/..."
   ```
3. **Rotate webhooks periodically**: Delete and recreate if compromised
4. **Limit webhook permissions**: Use dedicated channels for notifications
5. **Monitor usage**: Check for unexpected notification patterns

## Support

For issues or questions:
- Check the [main README](README.md)
- Review logs in the broadcast task
- Open an issue on [GitHub](https://github.com/ChangLabSNU/PaperSorter)