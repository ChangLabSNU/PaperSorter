# PaperSorter

PaperSorter is an academic paper recommendation system that utilizes
machine learning techniques to match users' interests. The system
retrieves article alerts from RSS feeds and processes the title,
author, journal name, and abstract of each article using
[Upstage's Solar LLM](https://www.upstage.ai/solar-llm) to generate
embedding vectors. These vectors serve as input for a regression
model that predicts the user's level of interest in each paper.
PaperSorter sends notifications about high-scoring articles to a
designated Slack channel, enabling timely discussion of relevant
publications among colleagues. The prediction model can be trained
incrementally with additional labels for new articles provided by
user.

<img src="https://github.com/ChangLabSNU/PaperSorter/assets/1702891/5ef2df1f-610b-4272-b496-ecf2a480dda2" width="660px">

## Installing

To install PaperSorter, use pip:

```
pip install papersorter
```

## Preparing

### TheOldReader

PaperSorter uses [TheOldReader](https://theoldreader.com) as its
feed source. After signing up for TheOldReader, you will receive
API access using your email and password. Before running PaperSorter,
make sure to set the `TOR_EMAIL` and `TOR_PASSWORD` environment
variables with your TheOldReader email and password, respectively.
This will allow PaperSorter to authenticate and retrieve the necessary
data from your feeds.

### Upstage Solar LLM

Solar LLM's embedding API converts article titles and contents into
numerical vectors. Sign up on the [Upstage console](https://console.upstage.ai/)
and create an API key as per the
[documentation](https://developers.upstage.ai/docs/getting-started/quick-start#get-an-api-key).
Store the key securely and set the `UPSTAGE_API_KEY` environment
variable before running PaperSorter.

### Slack Incoming WebHook

To send notifications to a Slack channel, create an incoming webhook
address as described in the [Slack documentation](https://api.slack.com/messaging/webhooks).
Store the address securely and set the `PAPERSORTER_WEBHOOK_URL` environment
variable before running PaperSorter.


## Initialization and Training

To train a predictor for your article interests, ensure your
TheOldReader account contains at least 1000 articles, including at
least 100 positively labeled articles marked with stars. Ideally,
aim for around 5000 articles with 500 starred items for optimal
performance.

After populating your TheOldReader account, initialize the feed and
embedding databases using:

```
papersorter update --prediction-model ""
```

Next, train your first model with:

```
papersorter train
```

If the ROCAUC performance metric meets your expectations, you're
ready to send notifications about new interesting articles. To avoid
a massive influx of notifications from the newly initialized database,
run:

```
sqlite3 feeds.db "UPDATE feeds SET broadcasted=0"
```

Now, test sending notifications with:

```
papersorter broadcast
```

You will receive formatted notifications in your Slack channel.

## Running as a Cron Job

Here is an example of a shell script that runs PaperSorter's `update`
and `broadcast` jobs in the background. This script sends notifications
about new interesting articles between 7 am and 9 pm, while only
performing updates during the night.

```
#!/bin/bash
PAPERSORTER_CMD=/path/to/papersorter
PAPERSORTER_DATADIR=/path/to/data
LOGFILE=background-updates.log
CURRENT_HOUR=$(date +%H)

cd $PAPERSORTER_DATADIR
$PAPERSORTER_CMD update -q --log-file $LOGFILE

if [ "$CURRENT_HOUR" -ge 7 ] && [ "$CURRENT_HOUR" -le 21 ]; then
    $PAPERSORTER_CMD broadcast -q --log-file $LOGFILE
fi
```

Here is an example line for the crontab. It runs the update script on
every hour at ten minutes past the hour.

```
10 * * * * /bin/bash /path/to/run-update.sh
```

## Feedback and Updating the Model

To improve the model, provide more labels for the articles. First,
extract the list of articles with the following command:

```
papersorter train -o model-temporary.pkl -f feedback.xlsx
```

This generates an Excel file, `feedback.xlsx`, containing titles,
authors, prediction scores, and other details. Review each row and
fill in the `label` column with `1` (interesting) or `0` (not interesting).
Leave it blank if unsure. Once you've labeled some articles, update
the feed database with:

```
papersorter feedback -i feedback.xlsx
```

Retrain the predictor with the updated labels using:

```
papersorter train
```

The new predictor is stored as `model.pkl`, and your next feeds will
be assessed with the updated model.

## Author

Hyeshik Chang <hyeshik@snu.ac.kr>