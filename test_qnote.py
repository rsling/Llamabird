#!/usr/bin/env python3
"""
Test script for QNote Writer

This script demonstrates how to use the QNote writer module
and creates test QNotes to verify Thunderbird can display them.
"""

import json
import sys
from pathlib import Path
from qnote_writer import QNoteWriter, load_config


def print_header(text):
    """Print a formatted header"""
    print(f"\n{'=' * 70}")
    print(f"{text}")
    print('=' * 70)


def test_filename_conversion():
    """Test Message-ID to filename conversion"""
    print_header("TEST 1: Message-ID to Filename Conversion")

    test_cases = [
        ("<test@example.com>", "test%40example.com.qnote"),
        ("test@example.com", "test%40example.com.qnote"),
        ("<abc123@uni-jena.de>", "abc123%40uni-jena.de.qnote"),
        ("<df36f688a89741e6a498712a9dc7a787@uni-jena.de>",
         "df36f688a89741e6a498712a9dc7a787%40uni-jena.de.qnote"),
    ]

    all_passed = True
    for message_id, expected in test_cases:
        result = QNoteWriter.message_id_to_filename(message_id)
        passed = result == expected

        status = "✓" if passed else "✗"
        print(f"{status} {message_id:50} -> {result}")

        if not passed:
            print(f"  Expected: {expected}")
            all_passed = False

    return all_passed


def test_qnote_creation(writer: QNoteWriter):
    """Test creating QNote files"""
    print_header("TEST 2: Creating QNote Files")

    test_notes = [
        {
            "message_id": "<test-llamabird-1@example.com>",
            "summary": "📧 Test Email Summary\n\nThis is a test AI-generated summary for Llamabird.\n\n• Point 1: Testing QNote creation\n• Point 2: Verifying JSON format\n• Point 3: Checking Thunderbird display"
        },
        {
            "message_id": "<test-llamabird-2@example.com>",
            "summary": "Quick meeting reminder - The team meeting scheduled for tomorrow at 10 AM has been moved to 2 PM. Please update your calendar."
        },
    ]

    created_files = []

    for note in test_notes:
        try:
            filepath = writer.write_qnote(
                note['message_id'],
                note['summary'],
                overwrite=True  # Allow overwriting test notes
            )

            print(f"✓ Created: {filepath.name}")
            print(f"  Message-ID: {note['message_id']}")
            print(f"  Summary preview: {note['summary'][:60]}...")

            created_files.append(filepath)

        except Exception as e:
            print(f"✗ Failed to create QNote for {note['message_id']}: {e}")
            return False, []

    return True, created_files


def test_qnote_reading(writer: QNoteWriter, message_ids):
    """Test reading QNote files"""
    print_header("TEST 3: Reading QNote Files")

    all_passed = True
    for message_id in message_ids:
        data = writer.read_qnote(message_id)

        if data:
            print(f"✓ Read QNote for {message_id}")
            print(f"  Text length: {len(data.get('text', ''))} characters")
            print(f"  Timestamp: {data.get('ts')}")
            print(f"  Dimensions: {data.get('width')}x{data.get('height')}")
        else:
            print(f"✗ Failed to read QNote for {message_id}")
            all_passed = False

    return all_passed


def display_qnote_contents(created_files):
    """Display the contents of created QNote files"""
    print_header("QNote File Contents")

    for filepath in created_files:
        print(f"\nFile: {filepath.name}")
        print("-" * 70)

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(json.dumps(data, indent=2, ensure_ascii=False))


def test_with_real_message(writer: QNoteWriter):
    """Test with a real Message-ID from the user's mailbox"""
    print_header("TEST 4: Testing with Real Email (Optional)")

    # Check if there's an existing QNote we can examine
    existing_qnotes = writer.list_qnotes()

    if existing_qnotes:
        print(f"Found {len(existing_qnotes)} existing QNote(s):")

        for filename, filepath in existing_qnotes[:3]:  # Show first 3
            print(f"\n  • {filename}")

            # Try to read it
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Show preview
            text_preview = data.get('text', '')[:100]
            print(f"    Preview: {text_preview}...")

        return True
    else:
        print("No existing QNotes found.")
        print("This is normal if you haven't created any notes in Thunderbird yet.")
        return True


def main():
    """Run all tests"""
    print_header("LLAMABIRD QNOTE WRITER TEST SUITE")

    try:
        # Load configuration
        print("\nLoading configuration...")
        config = load_config()
        qnote_dir = Path(config['qnote_path'])
        print(f"✓ QNote directory: {qnote_dir}")

        # Initialize writer
        writer = QNoteWriter(qnote_dir)

        # Run tests
        results = []

        # Test 1: Filename conversion
        results.append(("Filename Conversion", test_filename_conversion()))

        # Test 2: Create QNotes
        success, created_files = test_qnote_creation(writer)
        results.append(("QNote Creation", success))

        if success:
            # Test 3: Read QNotes
            test_message_ids = [
                "<test-llamabird-1@example.com>",
                "<test-llamabird-2@example.com>",
            ]
            results.append(("QNote Reading", test_qnote_reading(writer, test_message_ids)))

            # Display contents
            display_qnote_contents(created_files)

        # Test 4: Real messages
        results.append(("Real Message Test", test_with_real_message(writer)))

        # Summary
        print_header("TEST SUMMARY")

        all_passed = True
        for test_name, passed in results:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"{status}: {test_name}")
            if not passed:
                all_passed = False

        if all_passed:
            print("\n🎉 All tests passed!")
            print("\nNext steps:")
            print("1. Open Thunderbird/Betterbird")
            print("2. Check if test notes appear for test emails")
            print("   (Note: You may need to create dummy emails with matching Message-IDs,")
            print("    or the notes may not be visible without corresponding emails)")
            return 0
        else:
            print("\n⚠ Some tests failed. Please review the errors above.")
            return 1

    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        print("Please run discover.py first to generate config.json")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
