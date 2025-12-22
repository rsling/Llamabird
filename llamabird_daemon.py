#!/usr/bin/env python3
"""
Llamabird Daemon - Automatic Email Summarization Service

Monitors Thunderbird/Betterbird INBOX files and generates AI summaries automatically.
Runs as a systemd user service or standalone daemon.
"""

import sys
import json
import time
import signal
import logging
import threading
import argparse
from pathlib import Path
from datetime import datetime
from typing import Set, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

from email_parser import EmailParser
from ollama_summarizer import OllamaSummarizer
from qnote_writer import QNoteWriter


class InboxMonitor(FileSystemEventHandler):
    """
    Monitors INBOX files for modifications and schedules email processing.

    Implements debouncing to batch emails arriving close together.
    """

    def __init__(self, daemon, debounce_seconds: int = 30):
        """
        Initialize inbox monitor.

        Args:
            daemon: Reference to LlamabirdDaemon instance
            debounce_seconds: Seconds to wait after last change before processing
        """
        self.daemon = daemon
        self.debounce_seconds = debounce_seconds
        self.timer: Optional[threading.Timer] = None
        self.modified_inboxes: Set[Path] = set()
        self.lock = threading.Lock()

    def on_modified(self, event: FileModifiedEvent):
        """
        Handle file modification events.

        Args:
            event: File system event
        """
        # Only process INBOX file modifications
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.name == 'INBOX':
            with self.lock:
                self.modified_inboxes.add(file_path)
                self._reset_timer()
                logging.info(f"INBOX modified: {file_path.parent.name}")

    def _reset_timer(self):
        """Reset the debounce timer."""
        # Cancel existing timer
        if self.timer and self.timer.is_alive():
            self.timer.cancel()

        # Start new timer
        self.timer = threading.Timer(
            self.debounce_seconds,
            self._process_emails
        )
        self.timer.daemon = True
        self.timer.start()
        logging.debug(f"Debounce timer reset ({self.debounce_seconds}s)")

    def _process_emails(self):
        """Process all modified inboxes (called when debounce timer expires)."""
        with self.lock:
            inbox_count = len(self.modified_inboxes)
            if inbox_count == 0:
                return

            logging.info(f"Debounce timer expired - processing {inbox_count} inbox(es)")
            self.daemon.process_emails()
            self.modified_inboxes.clear()

    def stop(self):
        """Stop the monitor and cancel pending timers."""
        with self.lock:
            if self.timer and self.timer.is_alive():
                self.timer.cancel()
                logging.debug("Debounce timer cancelled")


class LlamabirdDaemon:
    """
    Main daemon class for Llamabird automatic email summarization.

    Supports two modes:
    - auto: File watching with debouncing (real-time)
    - interval: Periodic processing (cron-like)
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize Llamabird daemon.

        Args:
            config_path: Path to config.json (default: auto-detect)
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        # Load configuration
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.daemon_config = self.config.get('daemon', {})
        self.running = True
        self.observer: Optional[Observer] = None
        self.monitor: Optional[InboxMonitor] = None

        # Set up logging
        self._setup_logging()

        # Initialize components
        logging.info("Initializing Llamabird daemon...")
        self.email_parser = EmailParser()
        self.ollama_summarizer = OllamaSummarizer()

        qnote_path = Path(self.config['qnote_path'])
        self.qnote_writer = QNoteWriter(qnote_path)

        # Preload model if configured
        if self.daemon_config.get('preload_model', True):
            self._preload_model()

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._shutdown_signal)
        signal.signal(signal.SIGINT, self._shutdown_signal)

        logging.info("Daemon initialized successfully")

    def _setup_logging(self):
        """Configure logging based on daemon settings."""
        log_file = self.daemon_config.get('log_file', 'llamabird_daemon.log')
        log_level = self.daemon_config.get('log_level', 'INFO')

        # Convert string to logging level
        level = getattr(logging, log_level.upper(), logging.INFO)

        # Configure logging to both file and console
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def _preload_model(self):
        """Preload the Ollama model for better performance."""
        logging.info("Preloading Ollama model...")
        start_time = time.time()

        try:
            load_time = self.ollama_summarizer.preload_model()
            logging.info(f"Model preloaded in {load_time:.2f}s")
        except Exception as e:
            logging.error(f"Failed to preload model: {e}")
            logging.warning("Continuing anyway - model will load on first use")

    def _shutdown_signal(self, signum, frame):
        """Handle shutdown signals (SIGTERM, SIGINT)."""
        sig_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logging.info(f"Received {sig_name}, shutting down gracefully...")
        self.shutdown()

    def shutdown(self):
        """Gracefully shut down the daemon."""
        self.running = False

        # Stop file observer
        if self.observer:
            logging.info("Stopping file observer...")
            self.observer.stop()
            self.observer.join(timeout=5)

        # Stop monitor timers
        if self.monitor:
            self.monitor.stop()

        logging.info("Daemon shutdown complete")

    def run_auto_mode(self):
        """
        Run daemon in auto mode (file watching with debouncing).

        Monitors INBOX files for changes and processes emails automatically.
        """
        debounce_seconds = self.daemon_config.get('debounce_seconds', 30)

        logging.info(f"Starting daemon in AUTO mode (debounce: {debounce_seconds}s)")

        # Get all inbox paths to monitor
        inboxes = self.email_parser.get_enabled_inboxes()
        if not inboxes:
            logging.error("No enabled inboxes found - nothing to monitor")
            return 1

        logging.info(f"Monitoring {len(inboxes)} inbox(es):")
        for inbox in inboxes:
            logging.info(f"  • {inbox.parent.name}: {inbox}")

        # Set up file system observer
        self.observer = Observer()
        self.monitor = InboxMonitor(self, debounce_seconds)

        # Watch each inbox directory
        for inbox in inboxes:
            # Watch the parent directory (e.g., ImapMail/account.com/)
            watch_dir = inbox.parent
            self.observer.schedule(self.monitor, str(watch_dir), recursive=False)
            logging.debug(f"Watching directory: {watch_dir}")

        # Start observer
        self.observer.start()
        logging.info("File observer started - daemon is now running")

        # Main loop - just keep running until shutdown
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")

        return 0

    def run_interval_mode(self):
        """
        Run daemon in interval mode (periodic processing).

        Processes emails at regular intervals like a cron job.
        """
        interval_minutes = self.daemon_config.get('interval_minutes', 5)
        interval_seconds = interval_minutes * 60

        logging.info(f"Starting daemon in INTERVAL mode (every {interval_minutes} minutes)")

        # Main loop
        try:
            while self.running:
                logging.info("Interval timer triggered - processing emails")
                self.process_emails()

                # Sleep until next interval
                logging.debug(f"Sleeping for {interval_seconds}s")
                for _ in range(interval_seconds):
                    if not self.running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")

        return 0

    def process_emails(self):
        """
        Process all new emails from enabled inboxes.

        This is called either by the file monitor (auto mode) or
        by the interval timer (interval mode).
        """
        max_emails = self.daemon_config.get('max_emails_per_run', 50)

        logging.info(f"Processing emails (max: {max_emails})...")
        start_time = time.time()

        try:
            # Get enabled inboxes
            inboxes = self.email_parser.get_enabled_inboxes()
            if not inboxes:
                logging.warning("No enabled inboxes found")
                return

            processed_count = 0
            skipped_count = 0
            error_count = 0

            for inbox in inboxes:
                account_name = inbox.parent.name

                for email_data in self.email_parser.parse_inbox(inbox, limit=max_emails):
                    try:
                        # Check if we've reached the limit
                        if processed_count >= max_emails:
                            logging.info(f"Reached max emails limit ({max_emails})")
                            break

                        # Skip if QNote already exists
                        if self.qnote_writer.qnote_exists(email_data.message_id):
                            skipped_count += 1
                            continue

                        # Generate summary
                        logging.debug(f"Summarizing: {email_data.subject[:50]}...")
                        result = self.ollama_summarizer.summarize_email(email_data)

                        # Create QNote
                        qnote_path = self.qnote_writer.write_qnote(
                            email_data.message_id,
                            result.summary
                        )

                        logging.info(
                            f"✓ {account_name}: {email_data.subject[:40]}... "
                            f"({result.duration_seconds:.1f}s, {result.total_tokens} tokens)"
                        )

                        processed_count += 1

                    except Exception as e:
                        logging.error(f"Error processing email: {e}")
                        error_count += 1
                        continue

                # Check if we've reached the limit
                if processed_count >= max_emails:
                    break

            # Summary
            duration = time.time() - start_time
            logging.info(
                f"Processing complete: {processed_count} processed, "
                f"{skipped_count} skipped, {error_count} errors "
                f"({duration:.1f}s)"
            )

            # Show profiling if any emails were processed
            if processed_count > 0:
                prof = self.ollama_summarizer.get_profiling_summary()
                avg_time = prof['summaries']['avg_time']
                avg_tokens = prof['summaries']['avg_tokens']
                throughput = 60 / avg_time if avg_time > 0 else 0

                logging.info(
                    f"Performance: {avg_time:.1f}s/email, "
                    f"{avg_tokens:.0f} tokens/email, "
                    f"{throughput:.1f} emails/min"
                )

        except Exception as e:
            logging.error(f"Error in email processing: {e}", exc_info=True)

    def run(self, mode: Optional[str] = None):
        """
        Run the daemon in the specified mode.

        Args:
            mode: 'auto' or 'interval' (default: from config)

        Returns:
            Exit code (0 = success, 1 = error)
        """
        # Determine mode
        if mode is None:
            mode = self.daemon_config.get('mode', 'auto')

        logging.info(f"Llamabird Daemon starting (mode: {mode})")

        try:
            if mode == 'auto':
                return self.run_auto_mode()
            elif mode == 'interval':
                return self.run_interval_mode()
            else:
                logging.error(f"Unknown mode: {mode}")
                return 1

        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
            return 1


def main():
    """CLI interface for Llamabird daemon."""
    parser = argparse.ArgumentParser(
        description='Llamabird Daemon - Automatic Email Summarization Service'
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['auto', 'interval'],
        help='Run mode: auto (file watching) or interval (periodic)'
    )

    parser.add_argument(
        '--config',
        type=str,
        help='Path to config.json file'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Create daemon
    config_path = Path(args.config) if args.config else None
    daemon = LlamabirdDaemon(config_path)

    # Override log level if specified
    if args.log_level:
        logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Run daemon
    exit_code = daemon.run(mode=args.mode)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
