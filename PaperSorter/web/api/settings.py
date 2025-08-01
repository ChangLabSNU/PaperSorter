#!/usr/bin/env python3
#
# Copyright (c) 2024 Hyeshik Chang
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

"""Settings API endpoints."""

import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify, render_template, current_app
from ..auth.decorators import admin_required

settings_bp = Blueprint('settings', __name__)


# Settings pages
@settings_bp.route('/settings')
@admin_required
def settings():
    """Settings main page."""
    return render_template('settings.html')


@settings_bp.route('/settings/channels')
@admin_required
def settings_channels():
    """Channels settings page."""
    return render_template('settings_channels.html')


@settings_bp.route('/settings/users')
@admin_required
def settings_users():
    """Users settings page."""
    return render_template('settings_users.html')


@settings_bp.route('/settings/models')
@admin_required
def settings_models():
    """Models settings page."""
    return render_template('settings_models.html')


@settings_bp.route('/settings/events')
@admin_required
def settings_events():
    """Event logs viewer page."""
    return render_template('settings_events.html')


# Channels API endpoints
@settings_bp.route('/api/settings/channels')
@admin_required
def api_get_channels():
    """Get all channels."""
    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, name, endpoint_url, score_threshold, model_id, is_active
        FROM channels
        ORDER BY id
    """)

    channels = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'channels': channels})


@settings_bp.route('/api/settings/channels', methods=['POST'])
@admin_required
def api_create_channel():
    """Create a new channel."""
    data = request.get_json()

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO channels (name, endpoint_url, score_threshold, model_id, is_active)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (data['name'], data['endpoint_url'],
              data.get('score_threshold', 0.7), data.get('model_id', 1),
              data.get('is_active', True)))

        channel_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'id': channel_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings/channels/<int:channel_id>', methods=['PUT'])
@admin_required
def api_update_channel(channel_id):
    """Update a channel."""
    data = request.get_json()

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE channels
            SET name = %s, endpoint_url = %s, score_threshold = %s, model_id = %s, is_active = %s
            WHERE id = %s
        """, (data['name'], data['endpoint_url'],
              data.get('score_threshold', 0.7), data.get('model_id', 1),
              data.get('is_active', True), channel_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings/channels/<int:channel_id>', methods=['DELETE'])
@admin_required
def api_delete_channel(channel_id):
    """Delete a channel."""
    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM channels WHERE id = %s", (channel_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# Users API endpoints
@settings_bp.route('/api/settings/users')
@admin_required
def api_get_users():
    """Get all users."""
    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, username, created, lastlogin, timezone
        FROM users
        ORDER BY id
    """)

    users = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'users': users})


@settings_bp.route('/api/settings/users', methods=['POST'])
@admin_required
def api_create_user():
    """Create a new user."""
    data = request.get_json()

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (username, password, created, timezone)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            RETURNING id
        """, (data['username'], data.get('password', 'default'),
              data.get('timezone', 'Asia/Seoul')))

        user_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'id': user_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings/users/<int:user_id>', methods=['PUT'])
@admin_required
def api_update_user(user_id):
    """Update a user."""
    data = request.get_json()

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        # Update query parts
        update_parts = ['username = %s']
        update_values = [data['username']]

        if 'timezone' in data:
            update_parts.append('timezone = %s')
            update_values.append(data['timezone'])

        # Add user_id at the end
        update_values.append(user_id)

        cursor.execute(f"""
            UPDATE users
            SET {', '.join(update_parts)}
            WHERE id = %s
        """, update_values)

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    """Delete a user."""
    if user_id == 1:
        return jsonify({'success': False, 'error': 'Cannot delete default user'}), 400

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# Models API endpoints
@settings_bp.route('/api/settings/models')
@admin_required
def api_get_models():
    """Get all models."""
    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cursor.execute("""
        SELECT id, name, user_id, created, is_active
        FROM models
        ORDER BY id
    """)

    models = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({'models': models})


@settings_bp.route('/api/settings/models', methods=['POST'])
@admin_required
def api_create_model():
    """Create a new model."""
    data = request.get_json()

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO models (name, user_id, created, is_active)
            VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            RETURNING id
        """, (data['name'], data.get('user_id', 1),
              data.get('is_active', True)))

        model_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'id': model_id})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings/models/<int:model_id>', methods=['PUT'])
@admin_required
def api_update_model(model_id):
    """Update a model."""
    data = request.get_json()

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        # Update query parts
        update_parts = ['name = %s']
        update_values = [data['name']]

        if 'is_active' in data:
            update_parts.append('is_active = %s')
            update_values.append(data['is_active'])

        # Add model_id at the end
        update_values.append(model_id)

        cursor.execute(f"""
            UPDATE models
            SET {', '.join(update_parts)}
            WHERE id = %s
        """, update_values)

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/settings/models/<int:model_id>', methods=['DELETE'])
@admin_required
def api_delete_model(model_id):
    """Delete a model."""
    if model_id == 1:
        return jsonify({'success': False, 'error': 'Cannot delete default model'}), 400

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM models WHERE id = %s", (model_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# Event logs API endpoints
@settings_bp.route('/api/settings/events')
@admin_required
def api_get_events():
    """Get event logs with pagination."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    offset = (page - 1) * per_page

    conn = current_app.config['get_db_connection']()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM events")
        total = cursor.fetchone()['total']

        # Get events with feed and user information
        cursor.execute("""
            SELECT e.*, f.title as feed_title, u.username
            FROM events e
            LEFT JOIN feeds f ON e.feed_id = f.id
            LEFT JOIN users u ON e.user_id = u.id
            ORDER BY e.occurred DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        events = cursor.fetchall()

        cursor.close()
        conn.close()

        # Convert datetime to ISO format for JSON
        for event in events:
            if event['occurred']:
                event['occurred'] = event['occurred'].isoformat()

        return jsonify({
            'events': events,
            'total': total,
            'page': page,
            'per_page': per_page,
            'has_more': offset + per_page < total
        })
    except Exception as e:
        cursor.close()
        conn.close()
        return jsonify({'error': str(e)}), 500