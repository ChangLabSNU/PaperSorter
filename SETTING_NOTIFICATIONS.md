# Setting Up Notifications in PaperSorter

PaperSorter supports sending notifications to Slack, Discord, and Email. The system automatically detects the notification type based on the URL and formats messages accordingly.

## Table of Contents
- [Quick Start](#quick-start)
- [Slack Setup](#slack-setup)
- [Discord Setup](#discord-setup)
- [Email Setup](#email-setup)
- [Channel Configuration](#channel-configuration)
- [Testing Webhooks](#testing-webhooks)
- [Notification Features](#notification-features)
- [Troubleshooting](#troubleshooting)

## Quick Start

1. **Choose notification type**: Slack, Discord, or Email
2. **Configure endpoint**:
   - **Slack/Discord**: Get a webhook URL (see platform-specific instructions below)
   - **Email**: Use `mailto:` format (e.g., `mailto:user@example.com`)
3. **Add the channel** to PaperSorter via the web interface:
   - Navigate to Settings → Channels
   - Click "Add Channel"
   - Enter the webhook URL or email address
   - Set score threshold (e.g., 0.7)
   - Configure broadcast hours (optional)
   - Save and test
4. **Run broadcast** to send notifications:
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

## Email Setup

### Quick Start for Email

1. **Add SMTP configuration** to `config.yml`:
   ```yaml
   # For Gmail (recommended)
   smtp:
     provider: gmail
     username: "your@gmail.com"
     password: "xxxx-xxxx-xxxx-xxxx"  # App password from Google

   email:
     from_address: "your@gmail.com"
     from_name: "PaperSorter"
   ```

2. **Test the configuration**:
   ```bash
   papersorter test smtp -r test@example.com
   ```

3. **Add email channel** in web interface:
   - Go to Settings → Channels
   - Add webhook URL: `mailto:recipient@example.com`
   - Set score threshold and save

4. **Run broadcast**:
   ```bash
   papersorter broadcast
   ```

### Configuring Email Notifications

Email notifications send newsletter-style digests containing multiple papers in a single email.

#### 1. SMTP Server Configuration

PaperSorter supports both authenticated and unauthenticated SMTP servers. Configure in your `config.yml`:

##### Provider-based Configuration (Recommended for Public Services)

For Gmail, Outlook, or Yahoo, use the simplified provider configuration:

```yaml
# Gmail configuration
smtp:
  provider: gmail
  username: "your-email@gmail.com"
  password: "your-app-password"  # Use app-specific password

email:
  from_address: "your-email@gmail.com"
  from_name: "PaperSorter Newsletter"
```

```yaml
# Outlook.com/Hotmail configuration (Personal accounts only)
smtp:
  provider: outlook
  username: "your-email@outlook.com"
  password: "your-app-password"  # Requires 2FA enabled

email:
  from_address: "your-email@outlook.com"
  from_name: "Research Digest"

# Note: This works for personal Outlook.com accounts.
# For Microsoft 365 business accounts, OAuth2 is required
# and app passwords will stop working after April 2026.
```

```yaml
# Yahoo Mail configuration
smtp:
  provider: yahoo
  username: "your-email@yahoo.com"
  password: "your-app-password"

email:
  from_address: "your-email@yahoo.com"
  from_name: "Paper Alerts"
```

##### Custom SMTP Configuration

For custom SMTP servers (university, corporate, or other providers):

```yaml
# Custom SMTP with authentication
smtp:
  provider: custom
  host: "mail.university.edu"
  port: 587
  encryption: tls  # Options: tls, ssl, none
  username: "researcher@university.edu"
  password: "your-password"

email:
  from_address: "researcher@university.edu"
  from_name: "Lab Paper Digest"
```

```yaml
# Custom SMTP without authentication (internal networks)
smtp:
  provider: custom
  host: "internal-smtp.local"
  port: 25
  encryption: none
  # No username/password needed for internal SMTP

email:
  from_address: "papersorter@internal.local"
  from_name: "PaperSorter"
```

##### Direct Configuration (Without Provider)

For direct SMTP configuration without using a provider:

```yaml
# Direct SMTP configuration
smtp:
  host: "smtp.example.com"
  port: 587
  encryption: tls  # Options: tls, ssl, none
  username: "user@example.com"  # Optional
  password: "password"           # Optional

email:
  from_address: "noreply@example.com"
  from_name: "PaperSorter"
```

#### 2. Important: App-Specific Passwords

**Gmail users**:
1. Enable 2-factor authentication in your Google account
2. Generate an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Use the 16-character app password (not your regular password)

**Outlook.com (Personal accounts)**:
1. Enable 2-factor authentication in your Microsoft account
2. Go to [account.microsoft.com/security](https://account.microsoft.com/security)
3. Navigate to "Advanced security options" → "App passwords"
4. Create a new app password
5. Use this app password (not your regular password) in the configuration

   Note: Microsoft is phasing out app passwords. This method works as of 2025 but may be deprecated in the future.

**Microsoft 365 (Business accounts)**:
- App passwords are being deprecated and will stop working after April 2026
- OAuth2 is now required for business accounts
- For automated systems, consider using Microsoft's alternatives:
  - Azure Communication Services
  - Microsoft Graph API
- Or use a different SMTP service for notifications

**Yahoo users**:
1. Enable 2-step verification in your Yahoo account
2. Generate an app password at [login.yahoo.com/myaccount/security](https://login.yahoo.com/myaccount/security)
3. Use the app password for SMTP authentication

#### 3. Testing SMTP Configuration

Before adding email channels, test your SMTP configuration:

```bash
# Test connection only
papersorter test smtp

# Test with verbose output (shows configuration details)
papersorter test smtp -v

# Send a test email
papersorter test smtp -r recipient@example.com

# Custom subject for test email
papersorter test smtp -r recipient@example.com -s "Test from PaperSorter"
```

The test command will:
- Verify SMTP connection
- Check authentication (if configured)
- Send a test email (if recipient provided)
- Provide troubleshooting tips for common issues

#### 4. Adding Email Channels

1. Navigate to Settings → Channels
2. Click "Add Channel"
3. Enter email in `mailto:` format:
   ```
   mailto:researcher@university.edu
   ```
4. Configure settings:
   - **Channel Name**: e.g., "Daily Digest"
   - **Score Threshold**: Papers above this score
   - **Broadcast Limit**: Max papers per email (default: 20)
   - **Broadcast Hours**: When to send emails

#### 5. Email Subject Configuration

Customize the email subject in `config.yml`:

```yaml
email:
  subject_template: "Research Papers Digest - {date:%B %d, %Y}"
```

The `{date}` placeholder supports Python datetime formatting.

### Email Notification Features

- **Newsletter format**: Multiple papers in one email
- **Responsive HTML design**: Works on desktop and mobile
- **Plain text fallback**: For email clients that don't support HTML
- **Paper cards** with:
  - Title with link to paper
  - Authors and source
  - Publication date
  - Relevance score with color coding
  - Abstract or summary
  - "More Like This" button (if base_url configured)
- **Channel name** in email header
- **Summary statistics**: Number of papers and sources

### Email Template Customization

Templates are located in `PaperSorter/templates/email/`:
- `newsletter.html`: HTML version
- `newsletter.txt`: Plain text version

You can customize these templates using Jinja2 syntax. Available variables:
- `papers`: List of paper objects
- `channel_name`: Name of the channel
- `date`: Current date
- `base_url`: Web interface URL (if configured)
- `source_count`: Number of unique sources

## Channel Configuration

1. **Access Settings**:
   ```
   http://localhost:5001/settings/channels
   ```

2. **Add New Channel**:
   - Click "Add Channel"
   - Fill in the form:
     - **Channel Name**: Descriptive name (e.g., "ML Papers", "Biology Research")
     - **Endpoint URL**: Your webhook URL (Slack/Discord) or email (mailto:address)
     - **Score Threshold**: Minimum score to send (0.0 to 1.0)
     - **Model ID**: Which trained model to use
     - **Broadcast Limit**: Max notifications per broadcast run
     - **Broadcast Hours**: Select hours when notifications are allowed (24/7 if all selected)

3. **Channel Settings Explained**:
   - **Score Threshold**: Only papers scoring above this value are sent
     - 0.9+ = Only highly relevant papers
     - 0.7-0.9 = Relevant papers
     - 0.5-0.7 = Potentially interesting
     - <0.5 = Include everything (not recommended)
   - **Broadcast Limit**: Prevents notification spam (default: 20)
   - **Model ID**: Use different models for different topics

   - **Broadcast Hours**: Time restrictions for sending notifications
     - Select individual hours when broadcasting is allowed
     - All selected = 24/7 broadcasting
     - Use preset buttons for common patterns:
       - Business (9-17): Working hours only
       - Every morning: 8am only
       - After meals: 8am, 12pm, 5pm

## Testing Webhooks

1. Go to Settings → Channels
2. Click "Test" button next to any channel
3. Check your Slack/Discord/Email for test message

## Notification Features

### Automatic Webhook Detection

PaperSorter automatically detects the notification type based on the URL:
- URLs containing `slack.com` → Slack formatting
- URLs containing `discord.com` or `discordapp.com` → Discord formatting
- URLs starting with `mailto:` → Email newsletter
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

#### Email Troubleshooting

Common email issues and solutions:

1. **Connection errors**:
   ```bash
   # Test SMTP connection
   papersorter test smtp -v
   ```
   - Check SMTP host and port settings
   - For provider config: Ensure provider name is correct (gmail, outlook, yahoo)
   - For custom config: Verify host and port are correct
   - Test connectivity: `telnet smtp.gmail.com 587`
   - Check firewall rules for outbound SMTP

2. **Authentication failures**:
   ```bash
   # Common error: "535 Authentication failed"
   ```
   - **Gmail**: Must use App Password (16 characters, no spaces)
     - Enable 2FA first at myaccount.google.com
     - Generate app password at myaccount.google.com/apppasswords
   - **Outlook.com (Personal)**: Requires app password with 2FA enabled
   - **Microsoft 365 (Business)**: OAuth2 required; app passwords deprecated
   - **Yahoo**: Requires app-specific password
   - **Custom servers**: Check if authentication is required
   - Verify username format (usually full email address)

3. **Provider-specific issues**:
   - **Gmail "Less secure app" error**:
     - Solution: Use app password instead
     - Do NOT enable "Less secure apps" (deprecated)
   - **Outlook "550 5.7.1" error**:
     - Ensure using smtp-mail.outlook.com (not smtp.live.com)
     - Use port 587 with TLS
   - **Yahoo connection timeout**:
     - Ensure 2-step verification is enabled
     - Use app password, not account password

4. **Encryption/TLS errors**:
   - Provider configs handle this automatically
   - For custom SMTP:
     - Port 587: Use `encryption: tls`
     - Port 465: Use `encryption: ssl`
     - Port 25: Use `encryption: none` (not recommended)
   - Certificate errors: Update system certificates

5. **Emails not received**:
   - Run test command first: `papersorter test smtp -r your@email.com`
   - Check spam/junk folder
   - Verify recipient address in channel config
   - Check sender reputation (SPF/DKIM records)
   - Test with different recipient domains

6. **Configuration examples**:
   ```yaml
   # Provider-based (recommended for public services)
   smtp:
     provider: gmail
     username: your@gmail.com
     password: app-password

   # Direct configuration
   smtp:
     host: smtp.gmail.com
     port: 587
     encryption: tls
     username: your@gmail.com
     password: app-password
   ```

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

Set up a cron job to run every hour:

```bash
# Run broadcast every hour (channels have individual hour restrictions)
0 * * * * /path/to/papersorter broadcast --config /path/to/config.yml
```

The broadcast task will automatically respect each channel's configured broadcast hours. Configure hours per channel in the web interface (Settings → Channels).

### Filtering by Date

Only broadcast recent papers:
```bash
# Clear old items from queue (default: 30 days)
papersorter broadcast --clear-old-days 7  # Only last week's papers
```

## Security Considerations

1. **Keep webhooks private**: Never commit webhook URLs to version control
2. **Rotate webhooks periodically**: Delete and recreate if compromised
3. **Limit webhook permissions**: Use dedicated channels for notifications
4. **Monitor usage**: Check for unexpected notification patterns