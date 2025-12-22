#!/usr/bin/env python3
"""
Llamabird - AI Email Summarizer for Thunderbird/Betterbird

This is the main integration script that combines:
- Email parsing (email_parser.py)
- AI summarization (ollama_summarizer.py)
- QNote file creation (qnote_writer.py)

Supports two modes:
1. QNote mode (default): Create QNote files for Thunderbird
2. Stdout mode (--no-qnote): Display summaries with paging
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import pydoc

from email_parser import EmailParser, EmailData
from ollama_summarizer import OllamaSummarizer
from qnote_writer import QNoteWriter


class EmailSummarizer:
    """
    Main integration class for Llamabird.

    Coordinates email parsing, AI summarization, and QNote creation.
    """

    def __init__(self, no_qnote: bool = False, preload: bool = False, config_path: Optional[Path] = None):
        """
        Initialize the email summarizer.

        Args:
            no_qnote: If True, output to stdout instead of creating QNote files
            preload: If True, preload the AI model for better performance
            config_path: Path to config.json (default: auto-detect)
        """
        self.no_qnote = no_qnote

        # Load config to get QNote path
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        with open(config_path, 'r') as f:
            self.config = json.load(f)

        # Initialize components
        self.email_parser = EmailParser()
        self.ollama_summarizer = OllamaSummarizer()

        if not no_qnote:
            qnote_path = Path(self.config['qnote_path'])
            self.qnote_writer = QNoteWriter(qnote_path)

        # Preload model if requested
        if preload:
            print("Preloading AI model...")
            load_time = self.ollama_summarizer.preload_model()
            print(f"✓ Model loaded in {load_time:.2f} seconds\n")

    def extract_real_name(self, email_data: EmailData) -> str:
        """
        Extract real name from email address or use address if no name found.

        Args:
            email_data: Email data object

        Returns:
            Real name or email address
        """
        # For now, just use the part before @ as a simple name
        # In production, this could parse actual email headers for display names
        if email_data.from_addr:
            name_part = email_data.from_addr.split('@')[0]
            # Capitalize and clean up
            return name_part.replace('.', ' ').replace('_', ' ').title()
        return "Unknown Sender"

    def format_email_for_display(self, email_data: EmailData, summary: str) -> str:
        """
        Format email summary for stdout display.

        Args:
            email_data: Email data object
            summary: AI-generated summary

        Returns:
            Formatted string for display
        """
        # Extract real name
        from_name = self.extract_real_name(email_data)

        # Format date and time
        if email_data.date:
            date_str = email_data.date.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = "Unknown Date"

        # Build formatted output
        separator = "=" * 78
        output = []
        output.append(separator)
        output.append(f"From: {from_name} <{email_data.from_addr}>")
        output.append(f"Subject: {email_data.subject}")
        output.append(f"Date: {date_str}")
        output.append("")
        output.append("Summary:")
        output.append("-" * 78)
        output.append(summary)
        output.append(separator)
        output.append("")

        return "\n".join(output)

    def process_emails(
        self,
        limit: Optional[int] = None,
        account_filter: Optional[str] = None,
        profile: bool = False
    ) -> int:
        """
        Process emails from enabled inboxes.

        Args:
            limit: Maximum number of emails to process
            account_filter: Only process this account (None = all enabled)
            profile: Show profiling information

        Returns:
            Number of emails processed
        """
        # Get enabled inboxes
        inboxes = self.email_parser.get_enabled_inboxes()

        if not inboxes:
            print("No enabled inboxes found")
            return 0

        # Filter by account if specified
        if account_filter:
            inboxes = [
                inbox for inbox in inboxes
                if account_filter.lower() in inbox.parent.name.lower()
            ]
            if not inboxes:
                print(f"No inbox found matching: {account_filter}")
                return 0

        # Show processing mode
        if self.no_qnote:
            print(f"Mode: Display summaries to stdout (--no-qnote)\n")
        else:
            print(f"Mode: Create QNote files for Thunderbird\n")

        # Show accounts to process
        print(f"Processing {len(inboxes)} inbox(es):")
        for inbox in inboxes:
            size_mb = inbox.stat().st_size / (1024 * 1024)
            print(f"  • {inbox.parent.name}: {size_mb:.1f} MB")
        print()

        # Collect all outputs for stdout mode (to enable paging)
        stdout_outputs = []

        # Process emails
        processed_count = 0
        skipped_count = 0
        error_count = 0

        for inbox in inboxes:
            account_name = inbox.parent.name

            print(f"Processing account: {account_name}")
            print("-" * 70)

            for email_data in self.email_parser.parse_inbox(inbox, limit=limit):
                try:
                    # Check if we've reached the limit
                    if limit and processed_count >= limit:
                        break

                    # Check if QNote already exists (skip if so, unless in stdout mode)
                    if not self.no_qnote:
                        if self.qnote_writer.qnote_exists(email_data.message_id):
                            print(f"  ⊘ Skipped: {email_data.subject[:50]}... (QNote exists)")
                            skipped_count += 1
                            continue

                    # Generate summary
                    print(f"  → Summarizing: {email_data.subject[:50]}...", end='', flush=True)

                    result = self.ollama_summarizer.summarize_email(email_data)

                    print(f" Done in {result.duration_seconds:.2f}s")

                    if profile:
                        print(f"    Tokens: {result.total_tokens} (prompt: {result.prompt_tokens}, completion: {result.completion_tokens})")

                    # Output based on mode
                    if self.no_qnote:
                        # Collect for paging
                        formatted = self.format_email_for_display(email_data, result.summary)
                        stdout_outputs.append(formatted)
                    else:
                        # Create QNote file
                        qnote_path = self.qnote_writer.write_qnote(
                            email_data.message_id,
                            result.summary
                        )
                        print(f"    ✓ QNote created: {qnote_path.name}")

                    processed_count += 1

                except Exception as e:
                    print(f"  ✗ Error: {email_data.subject[:50]}... - {e}")
                    error_count += 1
                    continue

            # Check if we've reached the limit
            if limit and processed_count >= limit:
                break

            print()

        # Display summary
        print("=" * 70)
        print("PROCESSING COMPLETE")
        print("=" * 70)
        print(f"Emails processed: {processed_count}")
        if skipped_count > 0:
            print(f"Emails skipped (QNote exists): {skipped_count}")
        if error_count > 0:
            print(f"Errors: {error_count}")

        # Show profiling summary if requested
        if profile:
            print()
            prof = self.ollama_summarizer.get_profiling_summary()

            if prof['model_loads']['count'] > 0:
                print("Model Loading:")
                print(f"  Average time: {prof['model_loads']['avg_time']:.2f}s")

            print(f"Summarization:")
            print(f"  Total time: {prof['summaries']['total_time']:.2f}s")
            print(f"  Average time per email: {prof['summaries']['avg_time']:.2f}s")
            print(f"  Average tokens per email: {prof['summaries']['avg_tokens']:.0f}")

            if prof['summaries']['count'] > 0:
                emails_per_minute = 60 / prof['summaries']['avg_time']
                print(f"  Estimated throughput: {emails_per_minute:.1f} emails/minute")

        # Display outputs with paging (stdout mode only)
        if self.no_qnote and stdout_outputs:
            print()
            print("=" * 70)
            print("SUMMARIES (press 'q' to quit pager)")
            print("=" * 70)
            print()

            # Combine all outputs and use pager
            full_output = "\n".join(stdout_outputs)
            pydoc.pager(full_output)

        return processed_count


def main():
    """CLI interface for Llamabird integration"""
    parser = argparse.ArgumentParser(
        description='Llamabird - AI Email Summarizer for Thunderbird/Betterbird'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of emails to process (default: all)'
    )

    parser.add_argument(
        '--no-qnote',
        action='store_true',
        help='Display summaries to stdout instead of creating QNote files'
    )

    parser.add_argument(
        '--preload',
        action='store_true',
        help='Preload AI model before processing (recommended for batch processing)'
    )

    parser.add_argument(
        '--profile',
        action='store_true',
        help='Show detailed profiling information'
    )

    parser.add_argument(
        '--account',
        type=str,
        help='Only process emails from this account (partial name match)'
    )

    args = parser.parse_args()

    try:
        # Initialize summarizer
        print("=" * 70)
        print("LLAMABIRD - AI Email Summarizer")
        print("=" * 70)
        print()

        summarizer = EmailSummarizer(
            no_qnote=args.no_qnote,
            preload=args.preload
        )

        # Process emails
        count = summarizer.process_emails(
            limit=args.limit,
            account_filter=args.account,
            profile=args.profile
        )

        if count == 0:
            print("\nNo emails were processed.")
            return 1

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nPlease run discover.py first to generate config.json", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
