#!/usr/bin/env python3
"""
Simple test for FeedDatabase.get_unscored_items() method
"""

from PaperSorter.feed_database import FeedDatabase

def test_get_unscored_items():
    # Initialize database connection
    db = FeedDatabase('qbio/config.yml')
    
    # Check active models first
    db.cursor.execute('SELECT id, name FROM models WHERE is_active = TRUE ORDER BY id')
    active_models = db.cursor.fetchall()
    
    print(f"Active models: {len(active_models)}")
    for model in active_models:
        print(f"  - Model {model['id']}: {model.get('name', 'unnamed')}")
    print()
    
    # Call get_unscored_items
    unscored_items = db.get_unscored_items()
    
    # Print results
    print(f"Found {len(unscored_items)} unscored items (missing scores for at least one active model)")
    
    # Show first 10 items if any exist
    if unscored_items:
        print("\nFirst 10 unscored items:")
        for i, item_id in enumerate(unscored_items[:10]):
            print(f"  {i+1}. {item_id}")
    
    # Close database connection
    db.db.close()

if __name__ == "__main__":
    test_get_unscored_items()