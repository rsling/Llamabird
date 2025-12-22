#!/usr/bin/env python3
"""
Llamabird QNote Writer Module

This module handles creating QNote files that Thunderbird/Betterbird
displays in the sidebar. QNote files are JSON files named after the
email's Message-ID.
"""

import json
import time
import argparse
import sys
from pathlib import Path
from urllib.parse import quote
from typing import Optional, Dict


class QNoteWriter:
    """
    Handles creation and management of QNote files for email summaries.
    """

    # Default window dimensions for QNote
    DEFAULT_WIDTH = 320
    DEFAULT_HEIGHT = 200
    DEFAULT_LEFT = 660
    DEFAULT_TOP = 395

    def __init__(self, qnote_directory: Path):
        """
        Initialize QNote writer with the QNote storage directory.

        Args:
            qnote_directory: Path to the QNote storage directory
        """
        self.qnote_directory = Path(qnote_directory)

        # Create directory if it doesn't exist
        if not self.qnote_directory.exists():
            self.qnote_directory.mkdir(parents=True, exist_ok=True)
            print(f"Created QNote directory: {self.qnote_directory}")

    @staticmethod
    def message_id_to_filename(message_id: str) -> str:
        """
        Convert an email Message-ID to a QNote filename.

        The Message-ID is URL-encoded and .qnote extension is added.
        Angle brackets (< >) are stripped if present.

        Args:
            message_id: Email Message-ID (with or without < >)

        Returns:
            QNote filename (e.g., "abc123%40example.com.qnote")

        Examples:
            >>> QNoteWriter.message_id_to_filename("<test@example.com>")
            'test%40example.com.qnote'
            >>> QNoteWriter.message_id_to_filename("test@example.com")
            'test%40example.com.qnote'
        """
        # Strip angle brackets if present
        clean_id = message_id.strip()
        if clean_id.startswith('<') and clean_id.endswith('>'):
            clean_id = clean_id[1:-1]

        # URL-encode and add extension
        filename = quote(clean_id, safe='') + '.qnote'
        return filename

    @staticmethod
    def create_qnote_data(
        text: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        left: Optional[int] = None,
        top: Optional[int] = None,
        timestamp: Optional[int] = None
    ) -> Dict:
        """
        Create the QNote JSON data structure.

        Args:
            text: The note content (AI summary in our case)
            width: Window width in pixels (default: 320)
            height: Window height in pixels (default: 200)
            left: Window left position (default: 660)
            top: Window top position (default: 395)
            timestamp: Unix timestamp in milliseconds (default: current time)

        Returns:
            Dictionary with QNote structure
        """
        return {
            "text": text,
            "width": width or QNoteWriter.DEFAULT_WIDTH,
            "height": height or QNoteWriter.DEFAULT_HEIGHT,
            "left": left or QNoteWriter.DEFAULT_LEFT,
            "top": top or QNoteWriter.DEFAULT_TOP,
            "ts": timestamp or int(time.time() * 1000)
        }

    def write_qnote(
        self,
        message_id: str,
        summary_text: str,
        overwrite: bool = False
    ) -> Path:
        """
        Write a QNote file for an email.

        Args:
            message_id: Email Message-ID
            summary_text: Summary text to write
            overwrite: If True, overwrite existing QNote (default: False)

        Returns:
            Path to the created QNote file

        Raises:
            FileExistsError: If QNote exists and overwrite=False
            IOError: If writing fails
        """
        filename = self.message_id_to_filename(message_id)
        filepath = self.qnote_directory / filename

        # Check if file exists
        if filepath.exists() and not overwrite:
            raise FileExistsError(
                f"QNote already exists for this message: {filepath}\n"
                f"Use overwrite=True to replace it."
            )

        # Create QNote data
        qnote_data = self.create_qnote_data(summary_text)

        # Write to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(qnote_data, f, indent=2, ensure_ascii=False)

            return filepath
        except Exception as e:
            raise IOError(f"Failed to write QNote file: {e}")

    def read_qnote(self, message_id: str) -> Optional[Dict]:
        """
        Read an existing QNote file.

        Args:
            message_id: Email Message-ID

        Returns:
            QNote data dictionary or None if not found
        """
        filename = self.message_id_to_filename(message_id)
        filepath = self.qnote_directory / filename

        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to read QNote {filepath}: {e}")
            return None

    def qnote_exists(self, message_id: str) -> bool:
        """
        Check if a QNote exists for a given Message-ID.

        Args:
            message_id: Email Message-ID

        Returns:
            True if QNote exists, False otherwise
        """
        filename = self.message_id_to_filename(message_id)
        filepath = self.qnote_directory / filename
        return filepath.exists()

    def delete_qnote(self, message_id: str) -> bool:
        """
        Delete a QNote file.

        Args:
            message_id: Email Message-ID

        Returns:
            True if deleted, False if didn't exist
        """
        filename = self.message_id_to_filename(message_id)
        filepath = self.qnote_directory / filename

        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def list_qnotes(self) -> list:
        """
        List all QNote files in the directory.

        Returns:
            List of tuples (filename, filepath)
        """
        qnotes = []
        for filepath in self.qnote_directory.glob('*.qnote'):
            qnotes.append((filepath.name, filepath))
        return sorted(qnotes)


def load_config() -> Dict:
    """
    Load configuration from config.json.

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config.json doesn't exist
    """
    config_path = Path(__file__).parent / 'config.json'

    if not config_path.exists():
        raise FileNotFoundError(
            "config.json not found. Please run discover.py first."
        )

    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    """CLI interface for testing QNote writer."""
    parser = argparse.ArgumentParser(
        description='Llamabird QNote Writer - Create and manage QNote files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Write a QNote for a message
  %(prog)s write "<abc123@example.com>" "This is a test summary"

  # Read an existing QNote
  %(prog)s read "<abc123@example.com>"

  # List all QNotes
  %(prog)s list

  # Delete a QNote
  %(prog)s delete "<abc123@example.com>"
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Write command
    write_parser = subparsers.add_parser('write', help='Write a new QNote')
    write_parser.add_argument('message_id', help='Email Message-ID')
    write_parser.add_argument('text', help='Summary text to write')
    write_parser.add_argument('--overwrite', action='store_true',
                              help='Overwrite if QNote already exists')

    # Read command
    read_parser = subparsers.add_parser('read', help='Read a QNote')
    read_parser.add_argument('message_id', help='Email Message-ID')

    # Check command
    check_parser = subparsers.add_parser('check', help='Check if QNote exists')
    check_parser.add_argument('message_id', help='Email Message-ID')

    # List command
    list_parser = subparsers.add_parser('list', help='List all QNotes')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete a QNote')
    delete_parser.add_argument('message_id', help='Email Message-ID')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        # Load configuration
        config = load_config()
        qnote_dir = Path(config['qnote_path'])

        # Initialize writer
        writer = QNoteWriter(qnote_dir)

        # Execute command
        if args.command == 'write':
            filepath = writer.write_qnote(
                args.message_id,
                args.text,
                overwrite=args.overwrite
            )
            print(f"✓ QNote written successfully:")
            print(f"  File: {filepath}")
            print(f"  Message-ID: {args.message_id}")
            print(f"  Text length: {len(args.text)} characters")

        elif args.command == 'read':
            data = writer.read_qnote(args.message_id)
            if data:
                print(f"QNote for {args.message_id}:")
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                print(f"No QNote found for {args.message_id}")
                return 1

        elif args.command == 'check':
            exists = writer.qnote_exists(args.message_id)
            if exists:
                print(f"✓ QNote exists for {args.message_id}")
                filename = writer.message_id_to_filename(args.message_id)
                print(f"  Filename: {filename}")
            else:
                print(f"✗ No QNote found for {args.message_id}")
                return 1

        elif args.command == 'list':
            qnotes = writer.list_qnotes()
            if qnotes:
                print(f"Found {len(qnotes)} QNote(s):")
                for filename, filepath in qnotes:
                    print(f"  • {filename}")
            else:
                print("No QNotes found")

        elif args.command == 'delete':
            if writer.delete_qnote(args.message_id):
                print(f"✓ QNote deleted for {args.message_id}")
            else:
                print(f"✗ No QNote found for {args.message_id}")
                return 1

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except FileExistsError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
