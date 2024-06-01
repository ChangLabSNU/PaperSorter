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