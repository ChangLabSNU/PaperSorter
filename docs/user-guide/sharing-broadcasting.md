# Sharing and Broadcasting Papers

PaperSorter's sharing and broadcasting system manages paper notifications to external channels like Slack, Discord, or email newsletters. The "Share" function queues papers for notification delivery, while the broadcast system processes this queue and sends the actual notifications.

## Overview

The system works in two stages:

1. **Sharing**: Queue papers for notification delivery (adds to broadcast queue)
2. **Broadcasting**: Process the queue and send notifications to configured channels

This separation allows you to:
- Review papers before notifications are sent
- Batch notifications to avoid channel spam
- Send to multiple channels with different thresholds
- Prevent duplicate notifications
- Schedule notifications for appropriate times

## Sharing Papers

### How to Share

Papers can be shared in multiple ways:

1. **From the paper list**: Click the 📤 Share button on any paper
2. **From search results**: Share interesting papers directly from search
3. **From similar articles**: Share when browsing related papers
4. **From PDF search**: Share papers discovered through Paper Connect

### Share Status Indicators

- **📤 Share button (not highlighted)**: Paper is not shared
- **📤 Share button (highlighted blue)**: Paper is in the broadcast queue
- **📡 Broadcasted**: Paper has already been sent to channels

### What Happens When You Share

When you share a paper:
1. It's added to the broadcast queue for notification delivery
2. A shared badge (📤) appears on the paper's score
3. The paper becomes eligible for sending to notification channels
4. The paper will be included in the next broadcast run (if above threshold)

## Broadcasting System

### How Broadcasting Works

The broadcast system processes shared papers:

1. **Queue Processing**: Runs periodically (typically hourly)
2. **Channel Selection**: Each channel has its own settings
3. **Score Filtering**: Only papers above threshold are sent
4. **Duplicate Prevention**: Papers are only broadcast once per channel

### Channel Configuration

Each notification channel can have:

- **Score threshold**: Minimum score for broadcasting (e.g., 0.7)
- **Model selection**: Which ML model to use for scoring
- **Broadcast hours**: Time window for sending (e.g., 9 AM - 5 PM)
- **Active status**: Enable/disable without deleting

### Broadcast Command

```bash
# Process broadcast queue for all channels
papersorter broadcast

# Limit broadcasts per channel
papersorter broadcast --limit 10

# Clear old broadcast history
papersorter broadcast --clear-old-days 30
```

## Channel-Aware Features

### Multiple Channels

You can have different channels for:
- Different research groups
- Different topics or keywords
- Different urgency levels
- Different time zones

### Channel Selection

In the web interface:
1. Use the channel selector dropdown
2. View shows shared/broadcast status for selected channel
3. Each channel maintains its own queue

### Primary Channel

Your primary channel is used by default for:
- Share actions when no channel is selected
- PDF search and similar articles views
- Quick sharing from any interface

## Best Practices

### For Sharing

1. **Be selective**: Share papers that are truly interesting
2. **Consider audience**: Think about who will receive notifications
3. **Review before broadcast**: Check the queue periodically
4. **Use consistently**: Develop a sharing rhythm

### For Broadcasting

1. **Set appropriate thresholds**: Start high (0.8+) and adjust
2. **Configure broadcast hours**: Respect team working hours
3. **Monitor channel activity**: Ensure notifications are valuable
4. **Regular schedule**: Run broadcast task hourly via cron

### For Teams

1. **Separate channels by topic**: Create focused notification streams
2. **Assign channel owners**: Have someone responsible for each channel
3. **Document channel purpose**: Make clear what each channel is for
4. **Review channel performance**: Adjust thresholds based on feedback

## Queue Management

### Viewing the Queue

In the web interface:
- Shared papers show the 📤 badge
- Filter view to show only shared papers
- See queue size in channel settings

### Removing from Queue

To unshare a paper:
1. Click the Share button again to toggle
2. The paper is removed from broadcast queue
3. Won't be sent in next broadcast run

### Queue Persistence

- Shared status persists until broadcast
- Survives system restarts
- Can accumulate if broadcast doesn't run
- Old items auto-cleared after configurable period

## Troubleshooting

### Papers Not Broadcasting

Check if:
- Paper score is above channel threshold
- Channel is active
- Broadcast task is running
- Current time is within broadcast hours
- Paper wasn't already broadcast

### Duplicate Broadcasts

The system prevents duplicates by:
- Tracking broadcast history per channel
- Checking before each broadcast
- Marking papers as broadcasted

### Missing Share Button

Share button is disabled when:
- Paper is already broadcasted (shows 📡)
- You don't have permission to share
- System is in read-only mode

## Integration with ML Models

### Score-Based Sharing

The system uses ML predictions to:
- Filter papers for broadcasting
- Rank papers in notification order
- Provide score badges for context

### Model Selection

Different channels can use different models:
- General model for broad topics
- Specialized models for specific research areas
- User-specific models for personalized channels

### Continuous Improvement

As you label more papers:
- Model predictions improve
- Sharing becomes more accurate
- Fewer false positives in broadcasts
- Better alignment with team interests

## API and Automation

### Share via API

```python
# Share a paper programmatically
POST /api/feeds/{feed_id}/share
{
    "action": "share",
    "channel_id": 1  # Optional, uses primary if not specified
}
```

### Broadcast Automation

Set up cron jobs for regular broadcasting:

```cron
# Run broadcast every hour during work hours
0 9-17 * * * /path/to/papersorter broadcast
```

### Webhook Integration

Channels support webhooks for:
- Slack workspaces
- Discord servers
- Custom endpoints
- Email notifications

## Summary

The sharing and broadcasting system provides:
- **Control**: Choose what gets shared
- **Flexibility**: Multiple channels with different settings
- **Intelligence**: ML-powered filtering
- **Reliability**: No duplicate notifications
- **Integration**: Works with existing notification systems

Use sharing to build a curated queue of interesting papers, and let the broadcast system handle distribution according to your configured rules.