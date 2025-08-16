==========
User Guide
==========

This comprehensive guide covers all aspects of using PaperSorter effectively, from basic configuration to advanced workflows.

Whether you're a researcher looking to streamline your paper discovery process or an administrator managing a team's research feeds, this guide provides the knowledge you need to get the most out of PaperSorter.

Overview
========

PaperSorter helps you:

- **Discover relevant papers** automatically from multiple sources
- **Train personalized models** that learn your research interests
- **Receive targeted notifications** through Slack, email, or other channels
- **Manage and label papers** through an intuitive web interface
- **Search and explore** related work using semantic similarity

.. toctree::
   :maxdepth: 2

   configuration
   feed-sources
   training-models
   notifications
   web-interface
   workflows

Quick Reference
===============

Common Tasks
------------

- **Add new feeds**: Use the web interface or directly edit the database
- **Train a model**: Label ~100 papers, then run ``papersorter train``
- **Check new papers**: Run ``papersorter update`` to fetch and score articles
- **Send notifications**: Use ``papersorter broadcast`` to deliver recommendations

Best Practices
--------------

- Start with broad feeds and narrow down based on model performance
- Label papers consistently to improve model accuracy
- Regularly retrain models as your research interests evolve
- Monitor notification channels to ensure appropriate content delivery

Related Sections
================

- :doc:`../getting-started/index` - Initial setup and installation
- :doc:`../cli-reference/index` - Complete command reference
- :doc:`../tutorials/index` - Step-by-step integration guides