#!/usr/bin/env python3
#
# Copyright (c) 2024-2025 Seoul National University
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

"""Model management commands for PaperSorter."""

import os
import pickle
import argparse
from ..config import get_config
from ..db import DatabaseManager
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from tabulate import tabulate

from ..log import log, initialize_logging
from ..cli.base import BaseCommand, registry
from ..__version__ import __version__


class ModelsCommand(BaseCommand):
    """Manage trained models."""

    name = 'models'
    help = 'Manage trained models'

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add models-specific arguments."""
        subparsers = parser.add_subparsers(dest='subcommand', help='Model management commands')
        subparsers.required = True

        # List subcommand
        list_parser = subparsers.add_parser('list', help='List all models')
        list_parser.add_argument('--active-only', action='store_true',
                                help='Show only active models')
        list_parser.add_argument('--inactive-only', action='store_true',
                                help='Show only inactive models')
        list_parser.add_argument('--with-channels', action='store_true',
                                help='Show associated channels')
        list_parser.add_argument('--format', choices=['table', 'json'], default='table',
                                help='Output format')

        # Show subcommand
        show_parser = subparsers.add_parser('show', help='Show detailed model information')
        show_parser.add_argument('model_id', type=int, help='Model ID')

        # Modify subcommand
        modify_parser = subparsers.add_parser('modify', help='Modify model metadata')
        modify_parser.add_argument('model_id', type=int, help='Model ID')
        modify_parser.add_argument('--name', help='New model name')
        modify_parser.add_argument('--score-name', help='New score display name')
        modify_parser.add_argument('--notes', help='New model notes')

        # Activate subcommand
        activate_parser = subparsers.add_parser('activate', help='Activate a model')
        activate_parser.add_argument('model_id', type=int, help='Model ID')

        # Deactivate subcommand
        deactivate_parser = subparsers.add_parser('deactivate', help='Deactivate a model')
        deactivate_parser.add_argument('model_id', type=int, help='Model ID')
        deactivate_parser.add_argument('--force', action='store_true',
                                      help='Force deactivation even if used by channels')

        # Delete subcommand
        delete_parser = subparsers.add_parser('delete', help='Delete a model')
        delete_parser.add_argument('model_id', type=int, help='Model ID')
        delete_parser.add_argument('--force', action='store_true',
                                  help='Force deletion without confirmation')
        delete_parser.add_argument('--keep-file', action='store_true',
                                  help='Keep the model file, only remove from database')

        # Export subcommand
        export_parser = subparsers.add_parser('export', help='Export model to pickle file with metadata')
        export_parser.add_argument('model_id', type=int, help='Model ID')
        export_parser.add_argument('-o', '--output', required=True,
                                  help='Output pickle file path')
        export_parser.add_argument('--include-predictions', action='store_true',
                                  help='Include prediction statistics')

        # Import subcommand
        import_parser = subparsers.add_parser('import', help='Import model from pickle dump file')
        import_parser.add_argument('input_file', help='Input pickle dump file path')
        import_parser.add_argument('--name', help='Override model name')
        import_parser.add_argument('--notes', help='Override model notes')
        import_parser.add_argument('--activate', action='store_true',
                                  help='Activate model after import')

        # Validate subcommand
        validate_parser = subparsers.add_parser('validate', help='Validate model files')
        validate_parser.add_argument('model_id', type=int, nargs='?',
                                    help='Model ID (if omitted, validates all models)')
        validate_parser.add_argument('--fix-orphans', action='store_true',
                                    help='Remove orphaned model files')

    def handle(self, args: argparse.Namespace, context) -> int:
        """Execute the models command."""
        initialize_logging('models', args.log_file, args.quiet)

        self.config = get_config(args.config).raw

        self.db_config = self.config['db']
        self.model_dir = self.config.get('models', {}).get('path', './models')

        # Ensure model directory exists
        Path(self.model_dir).mkdir(parents=True, exist_ok=True)

        self.db_manager = DatabaseManager.from_config(
            self.db_config,
            application_name="papersorter-cli-models",
        )

        try:
            # Dispatch to appropriate subcommand handler
            subcommand = args.subcommand
            handler = getattr(self, f'handle_{subcommand}')
            return handler(args)
        finally:
            self.db_manager.close()

    def handle_list(self, args: argparse.Namespace) -> int:
        """List all models."""
        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            # Build query
            query = """
                SELECT
                    m.id,
                    m.name,
                    m.score_name,
                    m.notes,
                    m.created,
                    m.is_active,
                    COUNT(DISTINCT c.id) as channel_count,
                    COUNT(DISTINCT pp.feed_id) as prediction_count
                FROM models m
                LEFT JOIN channels c ON c.model_id = m.id
                LEFT JOIN predicted_preferences pp ON pp.model_id = m.id
            """

            conditions = []
            if args.active_only:
                conditions.append("m.is_active = TRUE")
            elif args.inactive_only:
                conditions.append("m.is_active = FALSE")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " GROUP BY m.id, m.name, m.notes, m.created, m.is_active"
            query += " ORDER BY m.id"

            cursor.execute(query)
            models = cursor.fetchall()

            # Check file existence
            for model in models:
                model_file = os.path.join(self.model_dir, f"model-{model['id']}.pkl")
                model['file_exists'] = os.path.exists(model_file)

            # Get associated channels if requested
            if args.with_channels:
                for model in models:
                    cursor.execute(
                        """
                        SELECT id, name, is_active
                        FROM channels
                        WHERE model_id = %s
                        ORDER BY id
                        """,
                        (model['id'],),
                    )
                    model['channels'] = cursor.fetchall()

            cursor.close()

        # Format output
        if args.format == 'json':
            # Convert datetime objects to strings
            for model in models:
                model['created'] = model['created'].isoformat() if model['created'] else None
            print(json.dumps(models, indent=2))
        else:
            self._print_models_table(models, args.with_channels)

        return 0

    def handle_show(self, args: argparse.Namespace) -> int:
        """Show detailed model information."""
        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute(
                """
                SELECT id, name, score_name, notes, created, is_active
                FROM models
                WHERE id = %s
                """,
                (args.model_id,),
            )
            model = cursor.fetchone()

            if not model:
                log.error(f"Model {args.model_id} not found")
                cursor.close()
                return 1

            model_file = os.path.join(self.model_dir, f"model-{args.model_id}.pkl")
            file_exists = os.path.exists(model_file)

            cursor.execute(
                """
                SELECT id, name, is_active, score_threshold
                FROM channels
                WHERE model_id = %s
                ORDER BY id
                """,
                (args.model_id,),
            )
            channels = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_predictions,
                    AVG(score) as avg_score,
                    MIN(score) as min_score,
                    MAX(score) as max_score,
                    STDDEV(score) as stddev_score
                FROM predicted_preferences
                WHERE model_id = %s
                """,
                (args.model_id,),
            )
            stats = cursor.fetchone()
            cursor.close()

        # Print basic information
        basic_info = [
            ["Model ID", model['id']],
            ["Name", model['name'] or 'N/A'],
            ["Score Name", model.get('score_name', 'Score')],
            ["Notes", model['notes'] or 'N/A'],
            ["Created", model['created']],
            ["Status", 'Active' if model['is_active'] else 'Inactive'],
            ["File", model_file],
            ["File exists", 'Yes' if file_exists else 'No']
        ]

        if file_exists:
            file_size = os.path.getsize(model_file) / (1024 * 1024)
            basic_info.append(["File size", f"{file_size:.2f} MB"])

        print("\n" + tabulate(basic_info, tablefmt='plain'))

        # Load and show model metadata if available
        if file_exists:
            try:
                with open(model_file, 'rb') as f:
                    model_data = pickle.load(f)
                if 'metadata' in model_data:
                    print("\n=== Model Metadata ===")
                    metadata_items = [[key, value] for key, value in model_data['metadata'].items()]
                    print(tabulate(metadata_items, tablefmt='plain'))
            except Exception as e:
                print(f"\nWarning: Could not load model file: {e}")

        # Print prediction statistics
        print("\n=== Prediction Statistics ===")
        if stats['total_predictions'] > 0:
            stats_table = [
                ["Total predictions", stats['total_predictions']],
                ["Average score", f"{stats['avg_score']:.3f}"],
                ["Score range", f"{stats['min_score']:.3f} - {stats['max_score']:.3f}"],
                ["Standard deviation", f"{stats['stddev_score']:.3f}"]
            ]
            print(tabulate(stats_table, tablefmt='plain'))
        else:
            print("No predictions found")

        # Print associated channels
        if channels:
            print(f"\n=== Associated Channels ({len(channels)}) ===")
            channel_rows = []
            for channel in channels:
                status = "Active" if channel['is_active'] else "Inactive"
                threshold = f"{channel['score_threshold']:.2f}" if channel['score_threshold'] else 'N/A'
                channel_rows.append([channel['id'], channel['name'], status, threshold])
            print(tabulate(channel_rows, headers=['ID', 'Name', 'Status', 'Threshold'], tablefmt='simple'))
        else:
            print("\n=== Associated Channels ===")
            print("No associated channels")

        return 0

    def handle_modify(self, args: argparse.Namespace) -> int:
        """Modify model metadata."""
        if not args.name and not getattr(args, 'score_name', None) and not args.notes:
            log.error("Nothing to modify. Specify --name, --score-name, or --notes")
            return 1

        with self.db_manager.session() as session:
            cursor = session.cursor()

            cursor.execute("SELECT id FROM models WHERE id = %s", (args.model_id,))
            if not cursor.fetchone():
                log.error(f"Model {args.model_id} not found")
                cursor.close()
                return 1

            updates = []
            values = []
            if args.name is not None:
                updates.append("name = %s")
                values.append(args.name)
            if getattr(args, 'score_name', None) is not None:
                updates.append("score_name = %s")
                values.append(args.score_name)
            if args.notes is not None:
                updates.append("notes = %s")
                values.append(args.notes)

            values.append(args.model_id)

            cursor.execute(
                f"UPDATE models SET {', '.join(updates)} WHERE id = %s",
                values,
            )
            cursor.close()

        log.info(f"Model {args.model_id} updated successfully")
        return 0

    def handle_activate(self, args: argparse.Namespace) -> int:
        """Activate a model."""
        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute("SELECT id, is_active FROM models WHERE id = %s", (args.model_id,))
            model = cursor.fetchone()

            if not model:
                log.error(f"Model {args.model_id} not found")
                cursor.close()
                return 1

            if model['is_active']:
                log.warning(f"Model {args.model_id} is already active")
                cursor.close()
                return 0

            model_file = os.path.join(self.model_dir, f"model-{args.model_id}.pkl")
            if not os.path.exists(model_file):
                log.error(f"Model file not found: {model_file}")
                cursor.close()
                return 1

            try:
                with open(model_file, 'rb') as f:
                    pickle.load(f)
            except Exception as e:
                log.error(f"Failed to load model file: {e}")
                cursor.close()
                return 1

            cursor.execute("UPDATE models SET is_active = TRUE WHERE id = %s", (args.model_id,))
            cursor.close()

        log.info(f"Model {args.model_id} activated successfully")
        return 0

    def handle_deactivate(self, args: argparse.Namespace) -> int:
        """Deactivate a model."""
        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute("SELECT id, is_active FROM models WHERE id = %s", (args.model_id,))
            model = cursor.fetchone()

            if not model:
                log.error(f"Model {args.model_id} not found")
                cursor.close()
                return 1

            if not model['is_active']:
                log.warning(f"Model {args.model_id} is already inactive")
                cursor.close()
                return 0

            cursor.execute(
                """
                SELECT id, name FROM channels
                WHERE model_id = %s AND is_active = TRUE
                """,
                (args.model_id,),
            )
            active_channels = cursor.fetchall()

            if active_channels and not args.force:
                log.error(f"Model {args.model_id} is used by {len(active_channels)} active channel(s):")
                for channel in active_channels:
                    log.error(f"  - {channel['name']} (ID: {channel['id']})")
                log.error("Use --force to deactivate anyway")
                cursor.close()
                return 1

            cursor.execute("UPDATE models SET is_active = FALSE WHERE id = %s", (args.model_id,))
            cursor.close()

        log.info(f"Model {args.model_id} deactivated successfully")
        if active_channels:
            log.warning(f"Warning: {len(active_channels)} channel(s) still reference this model")
        return 0

    def handle_delete(self, args: argparse.Namespace) -> int:
        """Delete a model."""
        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute("SELECT id, name FROM models WHERE id = %s", (args.model_id,))
            model = cursor.fetchone()

            if not model:
                log.error(f"Model {args.model_id} not found")
                cursor.close()
                return 1

            cursor.execute("SELECT COUNT(*) as count FROM channels WHERE model_id = %s", (args.model_id,))
            channel_count = cursor.fetchone()['count']

            if channel_count > 0:
                log.error(f"Model {args.model_id} is used by {channel_count} channel(s)")
                log.error("Cannot delete model while it is referenced by channels")
                cursor.close()
                return 1

            if not args.force:
                model_name = model['name'] or f"Model {args.model_id}"
                response = input(f"Are you sure you want to delete '{model_name}'? [y/N] ")
                if response.lower() != 'y':
                    log.info("Deletion cancelled")
                    cursor.close()
                    return 0

            cursor.execute("DELETE FROM models WHERE id = %s", (args.model_id,))
            cursor.close()

        if not args.keep_file:
            model_file = os.path.join(self.model_dir, f"model-{args.model_id}.pkl")
            if os.path.exists(model_file):
                try:
                    os.remove(model_file)
                    log.info(f"Deleted model file: {model_file}")
                except Exception as e:
                    log.warning(f"Could not delete model file: {e}")
        log.info(f"Model {args.model_id} deleted successfully")
        return 0

    def handle_export(self, args: argparse.Namespace) -> int:
        """Export model to portable ZIP format."""
        import json
        import xgboost as xgb
        import zipfile
        import tempfile

        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            cursor.execute(
                """
                SELECT id, name, notes, created, is_active
                FROM models
                WHERE id = %s
                """,
                (args.model_id,),
            )
            model_info = cursor.fetchone()

            if not model_info:
                log.error(f"Model {args.model_id} not found")
                cursor.close()
                return 1

            model_file = os.path.join(self.model_dir, f"model-{args.model_id}.pkl")
            if not os.path.exists(model_file):
                log.error(f"Model file not found: {model_file}")
                cursor.close()
                return 1

            try:
                with open(model_file, 'rb') as f:
                    model_data = pickle.load(f)
            except Exception as e:
                log.error(f"Failed to load model file: {e}")
                cursor.close()
                return 1

            metadata = {
                'original_id': model_info['id'],
                'name': model_info['name'],
                'notes': model_info['notes'],
                'created': model_info['created'].isoformat() if model_info['created'] else None,
                'export_date': datetime.now().isoformat(),
                'export_version': '2.0',
                'papersorter_version': __version__,
            }

            if 'metadata' in model_data:
                metadata.update(model_data['metadata'])

            if args.include_predictions:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_predictions,
                        AVG(score) as avg_score,
                        MIN(score) as min_score,
                        MAX(score) as max_score,
                        STDDEV(score) as stddev_score
                    FROM predicted_preferences
                    WHERE model_id = %s
                    """,
                    (args.model_id,),
                )
                stats = cursor.fetchone()
                metadata['prediction_stats'] = dict(stats)

            cursor.close()

        # Create portable ZIP export
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Save XGBoost model in JSON format
                xgb_model = model_data.get('model')
                if xgb_model:
                    model_json_path = os.path.join(tmpdir, 'model.json')
                    xgb_model.save_model(model_json_path)

                # Save scaler parameters as JSON
                scaler = model_data.get('scaler')
                scaler_params = {}
                if scaler:
                    # Extract scaler parameters for portable serialization
                    scaler_params = {
                        'type': 'StandardScaler',
                        'mean': scaler.mean_.tolist() if hasattr(scaler, 'mean_') else None,
                        'scale': scaler.scale_.tolist() if hasattr(scaler, 'scale_') else None,
                        'var': scaler.var_.tolist() if hasattr(scaler, 'var_') else None,
                        'n_features_in': scaler.n_features_in_ if hasattr(scaler, 'n_features_in_') else None,
                        'n_samples_seen': int(scaler.n_samples_seen_) if hasattr(scaler, 'n_samples_seen_') else None,
                        'with_mean': scaler.with_mean if hasattr(scaler, 'with_mean') else True,
                        'with_std': scaler.with_std if hasattr(scaler, 'with_std') else True,
                    }

                scaler_json_path = os.path.join(tmpdir, 'scaler.json')
                with open(scaler_json_path, 'w') as f:
                    json.dump(scaler_params, f, indent=2)

                # Save metadata
                metadata_json_path = os.path.join(tmpdir, 'metadata.json')
                with open(metadata_json_path, 'w') as f:
                    json.dump(metadata, f, indent=2)

                # Create ZIP archive
                with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as zf:
                    if xgb_model:
                        zf.write(model_json_path, 'model.json')
                    zf.write(scaler_json_path, 'scaler.json')
                    zf.write(metadata_json_path, 'metadata.json')

                log.info(f"Model exported successfully to: {args.output} (ZIP format)")

            return 0
        except Exception as e:
            log.error(f"Failed to export model: {e}")
            return 1

    def handle_import(self, args: argparse.Namespace) -> int:
        """Import model from portable ZIP format."""
        import json
        import xgboost as xgb
        import zipfile
        import tempfile
        from sklearn.preprocessing import StandardScaler
        import numpy as np

        if not os.path.exists(args.input_file):
            log.error(f"Input file not found: {args.input_file}")
            return 1

        if not zipfile.is_zipfile(args.input_file):
            log.error(f"Input file is not a valid ZIP file: {args.input_file}")
            return 1

        try:
            log.info("Importing from ZIP format")

            with tempfile.TemporaryDirectory() as tmpdir:
                with zipfile.ZipFile(args.input_file, 'r') as zf:
                    zf.extractall(tmpdir)

                metadata_path = os.path.join(tmpdir, 'metadata.json')
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                else:
                    metadata = {}

                model = None
                model_path = os.path.join(tmpdir, 'model.json')
                if os.path.exists(model_path):
                    model = xgb.Booster()
                    model.load_model(model_path)
                    log.info("Loaded XGBoost model from JSON format")
                else:
                    log.error("Model file not found in ZIP archive")
                    return 1

                scaler = None
                scaler_path = os.path.join(tmpdir, 'scaler.json')
                if os.path.exists(scaler_path):
                    with open(scaler_path, 'r') as f:
                        scaler_params = json.load(f)

                    if scaler_params.get('type') == 'StandardScaler':
                        scaler = StandardScaler(
                            with_mean=scaler_params.get('with_mean', True),
                            with_std=scaler_params.get('with_std', True),
                        )
                        if scaler_params.get('mean') is not None:
                            scaler.mean_ = np.array(scaler_params['mean'])
                        if scaler_params.get('scale') is not None:
                            scaler.scale_ = np.array(scaler_params['scale'])
                        if scaler_params.get('var') is not None:
                            scaler.var_ = np.array(scaler_params['var'])
                        if scaler_params.get('n_features_in') is not None:
                            scaler.n_features_in_ = scaler_params['n_features_in']
                        if scaler_params.get('n_samples_seen') is not None:
                            scaler.n_samples_seen_ = scaler_params['n_samples_seen']
                        log.info("Reconstructed StandardScaler from parameters")

                import_data = {
                    'model': model,
                    'scaler': scaler,
                    'metadata': metadata,
                }
        except Exception as e:
            log.error(f"Failed to load model file: {e}")
            return 1

        model_name = args.name or metadata.get('name', 'Imported Model')
        model_notes = args.notes or metadata.get('notes') or ''

        import_info = f"\nImported from {args.input_file} on {datetime.now().isoformat()}"
        if metadata.get('original_id'):
            import_info += f" (Original ID: {metadata['original_id']})"
        if metadata.get('export_version'):
            import_info += f" (Export version: {metadata['export_version']})"
        model_notes = (model_notes + import_info).strip()

        with self.db_manager.session() as session:
            cursor = session.cursor()
            cursor.execute(
                """
                INSERT INTO models (name, score_name, notes, created, is_active)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
                RETURNING id
                """,
                (model_name, 'Score', model_notes, args.activate),
            )
            new_model_id = cursor.fetchone()[0]
            cursor.close()

        model_file = os.path.join(self.model_dir, f"model-{new_model_id}.pkl")
        try:
            import_data['metadata'] = metadata
            import_data['metadata']['imported_as_id'] = new_model_id
            import_data['metadata']['import_date'] = datetime.now().isoformat()

            with open(model_file, 'wb') as f:
                pickle.dump(import_data, f)
        except Exception as e:
            log.error(f"Failed to save model file: {e}")
            with self.db_manager.session() as session:
                cleanup_cursor = session.cursor()
                cleanup_cursor.execute("DELETE FROM models WHERE id = %s", (new_model_id,))
                cleanup_cursor.close()
            return 1

        log.info(f"Model imported successfully with ID: {new_model_id}")
        if args.activate:
            log.info("Model activated")
        return 0

    def handle_validate(self, args: argparse.Namespace) -> int:
        """Validate model files."""
        with self.db_manager.session() as session:
            cursor = session.cursor(dict_cursor=True)

            if args.model_id:
                cursor.execute("SELECT id, name, is_active FROM models WHERE id = %s", (args.model_id,))
                models = cursor.fetchall()
                if not models:
                    log.error(f"Model {args.model_id} not found")
                    cursor.close()
                    return 1
            else:
                cursor.execute("SELECT id, name, is_active FROM models ORDER BY id")
                models = cursor.fetchall()

            cursor.close()

        # Check each model
        issues = []
        orphaned_files = []

        # Check registered models
        for model in models:
            model_file = os.path.join(self.model_dir, f"model-{model['id']}.pkl")
            model_name = model['name'] or f"Model {model['id']}"

            if not os.path.exists(model_file):
                issues.append(f"{model_name} (ID: {model['id']}): File missing")
                if model['is_active']:
                    issues[-1] += " [CRITICAL: Active model]"
            else:
                # Try to load the model
                try:
                    with open(model_file, 'rb') as f:
                        model_data = pickle.load(f)
                    if 'model' not in model_data:
                        issues.append(f"{model_name} (ID: {model['id']}): Invalid model format")
                    else:
                        log.info(f"{model_name} (ID: {model['id']}): Valid")
                except Exception as e:
                    issues.append(f"{model_name} (ID: {model['id']}): Cannot load - {e}")

        # Check for orphaned files
        if not args.model_id:
            model_files = Path(self.model_dir).glob("model-*.pkl")
            registered_ids = {m['id'] for m in models}

            for model_file in model_files:
                try:
                    file_id = int(model_file.stem.split('-')[1])
                    if file_id not in registered_ids:
                        orphaned_files.append(model_file)
                except (IndexError, ValueError):
                    pass  # Ignore files that don't match the pattern

        # Report results
        if issues:
            log.warning("Validation issues found:")
            for issue in issues:
                log.warning(f"  - {issue}")
        else:
            log.info("All models validated successfully")

        if orphaned_files:
            log.warning(f"Found {len(orphaned_files)} orphaned model file(s):")
            for file in orphaned_files:
                log.warning(f"  - {file}")

            if args.fix_orphans:
                for file in orphaned_files:
                    try:
                        os.remove(file)
                        log.info(f"Removed: {file}")
                    except Exception as e:
                        log.error(f"Failed to remove {file}: {e}")

        return 1 if issues else 0

    def _print_models_table(self, models: List[Dict], with_channels: bool = False) -> None:
        """Print models in a formatted table."""
        if not models:
            print("No models found")
            return

        # Prepare table data
        headers = ['ID', 'Name', 'Score Name', 'Status', 'File', 'Channels', 'Predictions', 'Created']
        if with_channels:
            headers.append('Associated Channels')

        rows = []
        for model in models:
            status = 'Active' if model['is_active'] else 'Inactive'
            file_status = 'OK' if model['file_exists'] else 'Missing'
            created = model['created'].strftime('%Y-%m-%d') if model['created'] else 'N/A'

            row = [
                model['id'],
                model['name'] or 'Unnamed',
                model.get('score_name', 'Score'),
                status,
                file_status,
                model['channel_count'],
                model['prediction_count'],
                created
            ]

            if with_channels and 'channels' in model:
                channel_names = [f"{c['name']}" for c in model['channels']]
                row.append(', '.join(channel_names) if channel_names else 'None')

            rows.append(row)

        # Print table using tabulate
        print("\n" + tabulate(rows, headers=headers, tablefmt='grid'))
        print(f"\nTotal: {len(models)} model(s)\n")


# Register the command
registry.register(ModelsCommand)
