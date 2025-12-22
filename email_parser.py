#!/usr/bin/env python3
"""
Llamabird Email Parser Module

This module handles parsing emails from Thunderbird/Betterbird mbox files.
Extracts Message-IDs, email content, and text from attachments for AI summarization.
"""

import json
import mailbox
import hashlib
import sys
import io
import fnmatch
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Iterator, Tuple, Dict
from email.utils import parseaddr, parsedate_to_datetime
from email.header import decode_header as email_decode_header
from datetime import datetime


@dataclass
class AttachmentData:
    """Data structure for email attachments"""
    filename: str
    content_type: str
    size_bytes: int
    text_content: Optional[str] = None  # None if extraction failed or disabled


@dataclass
class EmailData:
    """Data structure for parsed email"""
    message_id: str
    subject: str
    from_addr: str
    date: Optional[datetime]
    body_text: str
    body_html: str
    attachments: List[AttachmentData]


class EmailParser:
    """
    Parser for Thunderbird/Betterbird mbox email files.

    Handles extraction of email metadata, body content, and attachment text.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize email parser with configuration.

        Args:
            config_path: Path to config.json (default: auto-detect)
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        self.config = self._load_config(config_path)
        self.attachment_config = self.config.get('attachment_extraction', {})

    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                "Please run discover.py first to generate config.json"
            )

        with open(config_path, 'r') as f:
            return json.load(f)

    def get_enabled_inboxes(self) -> List[Path]:
        """
        Get list of enabled INBOX paths to process.

        Returns:
            List of Path objects for enabled INBOX files
        """
        inboxes = []

        for account in self.config.get('imap_accounts', []):
            if account.get('enabled', True):  # Default to enabled if not specified
                inbox_path = Path(account['inbox_path'])
                if inbox_path.exists():
                    inboxes.append(inbox_path)

        return inboxes

    def _is_email_deleted(self, message) -> bool:
        """
        Check if an email is marked as deleted.

        Thunderbird stores flags in X-Mozilla-Status and X-Mozilla-Status2 headers.
        The deleted flag is 0x0008 in X-Mozilla-Status.

        Args:
            message: email.message.Message object

        Returns:
            True if email is deleted, False otherwise
        """
        # Check X-Mozilla-Status header
        mozilla_status = message.get('X-Mozilla-Status', '0000')
        try:
            status_int = int(mozilla_status, 16)
            # 0x0008 is the Deleted flag
            if status_int & 0x0008:
                return True
        except ValueError:
            pass

        return False

    def _matches_pattern(self, email_address: str, pattern: str) -> bool:
        """
        Check if an email address matches a wildcard pattern.

        Supports simple wildcard patterns like:
        - *@uni-jena.de (matches any address at uni-jena.de)
        - anna@web.de (exact match)
        - spam* (matches addresses starting with spam)

        Args:
            email_address: Email address to check
            pattern: Wildcard pattern

        Returns:
            True if address matches pattern, False otherwise
        """
        return fnmatch.fnmatch(email_address.lower(), pattern.lower())

    def _should_skip_sender(self, from_addr: str) -> bool:
        """
        Check if an email should be skipped based on sender whitelist/blacklist.

        Logic:
        - If whitelist exists and email matches: DON'T skip (always process)
        - If blacklist exists and email matches: skip (unless also whitelisted)
        - If neither matches: DON'T skip (default behavior)

        Args:
            from_addr: Sender email address

        Returns:
            True if email should be skipped, False otherwise
        """
        sender_config = self.config.get('sender_filtering', {})
        whitelist = sender_config.get('whitelist', [])
        blacklist = sender_config.get('blacklist', [])

        # Check whitelist first (highest priority)
        for pattern in whitelist:
            if self._matches_pattern(from_addr, pattern):
                return False  # Whitelisted, always process

        # Check blacklist
        for pattern in blacklist:
            if self._matches_pattern(from_addr, pattern):
                return True  # Blacklisted, skip

        # Default: don't skip
        return False

    def parse_inbox(self, inbox_path: Path, limit: Optional[int] = None) -> Iterator[EmailData]:
        """
        Parse mbox inbox and yield EmailData objects.

        Args:
            inbox_path: Path to INBOX mbox file
            limit: Optional limit on number of emails to parse

        Yields:
            EmailData objects for each successfully parsed email
        """
        try:
            mbox = mailbox.mbox(str(inbox_path))
        except Exception as e:
            print(f"Error opening mbox file {inbox_path}: {e}", file=sys.stderr)
            return

        count = 0
        for key, message in mbox.items():
            if limit and count >= limit:
                break

            try:
                # Skip deleted emails
                if self._is_email_deleted(message):
                    continue

                # Check sender filtering before full parsing
                from_addr = parseaddr(message.get('From', ''))[1]
                if self._should_skip_sender(from_addr):
                    continue

                email_data = self._parse_message(message)
                if email_data:
                    yield email_data
                    count += 1
            except Exception as e:
                # Log error, continue with next message
                print(f"Error parsing message {key}: {e}", file=sys.stderr)
                continue

    def _parse_message(self, message) -> Optional[EmailData]:
        """
        Extract all data from a single email message.

        Args:
            message: email.message.Message object

        Returns:
            EmailData object or None if parsing fails
        """
        # Extract Message-ID
        message_id = message.get('Message-ID', '').strip()
        if not message_id:
            # Generate fallback Message-ID using hash of headers
            message_id = self._generate_fallback_message_id(message)

        # Extract headers
        subject = self._decode_header(message.get('Subject', ''))
        from_addr = parseaddr(message.get('From', ''))[1]

        # Parse date
        try:
            date = parsedate_to_datetime(message.get('Date', ''))
        except Exception:
            date = None

        # Extract body
        body_text, body_html = self._extract_body(message)

        # Extract attachments
        attachments = self._extract_attachments(message)

        return EmailData(
            message_id=message_id,
            subject=subject,
            from_addr=from_addr,
            date=date,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments
        )

    def _generate_fallback_message_id(self, message) -> str:
        """Generate a fallback Message-ID by hashing message headers"""
        # Use Subject, From, Date to create unique ID
        components = [
            message.get('Subject', ''),
            message.get('From', ''),
            message.get('Date', ''),
            message.get('To', '')
        ]
        hash_input = '|'.join(components).encode('utf-8')
        hash_value = hashlib.md5(hash_input).hexdigest()
        return f"<{hash_value}@llamabird.generated>"

    def _decode_header(self, header_value: str) -> str:
        """Decode email header (handles encoding)"""
        if not header_value:
            return ''

        decoded_parts = []
        for part, encoding in email_decode_header(header_value):
            if isinstance(part, bytes):
                if encoding:
                    try:
                        decoded_parts.append(part.decode(encoding, errors='replace'))
                    except:
                        decoded_parts.append(part.decode('utf-8', errors='replace'))
                else:
                    decoded_parts.append(part.decode('utf-8', errors='replace'))
            else:
                decoded_parts.append(part)

        return ''.join(decoded_parts)

    def _extract_body(self, message) -> Tuple[str, str]:
        """
        Extract plain text and HTML body from email.

        Returns:
            Tuple of (plain_text, html_text)
        """
        text_parts = []
        html_parts = []

        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                content_disposition = part.get_content_disposition()

                # Skip attachments
                if content_disposition == 'attachment':
                    continue

                if content_type == 'text/plain':
                    text_parts.append(self._decode_content(part))
                elif content_type == 'text/html':
                    html_parts.append(self._decode_content(part))
        else:
            content_type = message.get_content_type()
            content = self._decode_content(message)
            if content_type == 'text/plain':
                text_parts.append(content)
            elif content_type == 'text/html':
                html_parts.append(content)

        # Join parts
        text = '\n\n'.join(text_parts)
        html = '\n\n'.join(html_parts)

        # Convert HTML to text if no plain text available
        if not text and html:
            text = self._html_to_text(html)

        return text, html

    def _decode_content(self, part) -> str:
        """
        Decode email content with proper encoding detection.

        Args:
            part: email message part

        Returns:
            Decoded text content
        """
        payload = part.get_payload(decode=True)
        if not payload:
            return ''

        # Try declared encoding first
        charset = part.get_content_charset()
        if charset:
            try:
                return payload.decode(charset, errors='replace')
            except:
                pass

        # Fallback to chardet if available
        if self.attachment_config.get('libraries', {}).get('chardet'):
            try:
                import chardet
                detected = chardet.detect(payload)
                encoding = detected.get('encoding', 'utf-8')
                if encoding:
                    return payload.decode(encoding, errors='replace')
            except:
                pass

        # Final fallback to UTF-8
        return payload.decode('utf-8', errors='replace')

    def _html_to_text(self, html: str) -> str:
        """
        Convert HTML to plain text.

        Args:
            html: HTML content

        Returns:
            Plain text version
        """
        if not html:
            return ''

        # Use html2text if available
        if self.attachment_config.get('libraries', {}).get('html2text'):
            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0  # Don't wrap lines
                return h.handle(html)
            except Exception as e:
                print(f"html2text conversion failed: {e}", file=sys.stderr)

        # Fallback: simple HTML stripping
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_attachments(self, message) -> List[AttachmentData]:
        """
        Extract and process attachments from email.

        Args:
            message: email message object

        Returns:
            List of AttachmentData objects
        """
        attachments = []

        if not message.is_multipart():
            return attachments

        for part in message.walk():
            content_disposition = part.get_content_disposition()

            if content_disposition == 'attachment':
                filename = part.get_filename()
                if not filename:
                    filename = 'unnamed_attachment'

                # Decode filename if needed
                filename = self._decode_header(filename)

                content_type = part.get_content_type()
                content = part.get_payload(decode=True)

                if not content:
                    continue

                size_bytes = len(content)

                # Try to extract text if enabled
                text_content = None
                if self.attachment_config.get('enabled', False):
                    text_content = self._extract_text_from_attachment(
                        content, content_type, filename, size_bytes
                    )

                attachments.append(AttachmentData(
                    filename=filename,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    text_content=text_content
                ))

        return attachments

    def _extract_text_from_attachment(
        self, content: bytes, content_type: str, filename: str, size_bytes: int
    ) -> Optional[str]:
        """
        Extract text from attachment based on file type.

        Args:
            content: Attachment content bytes
            content_type: MIME content type
            filename: Attachment filename
            size_bytes: Size in bytes

        Returns:
            Extracted text or None if extraction failed/skipped
        """
        # Check size limit
        max_size_mb = self.attachment_config.get('max_size_mb', 10)
        size_mb = size_bytes / (1024 * 1024)
        if size_mb > max_size_mb:
            print(f"Skipping {filename}: {size_mb:.1f}MB exceeds {max_size_mb}MB limit", file=sys.stderr)
            return None

        try:
            # Determine file type and extract
            if 'pdf' in content_type.lower() or filename.lower().endswith('.pdf'):
                return self._extract_pdf(content)
            elif filename.lower().endswith('.docx'):
                return self._extract_docx(content)
            elif filename.lower().endswith('.doc'):
                return self._extract_doc_legacy(content, filename)
            elif 'opendocument' in content_type.lower() or filename.lower().endswith('.odt'):
                return self._extract_odt(content)
        except Exception as e:
            print(f"Failed to extract text from {filename}: {e}", file=sys.stderr)

        return None

    def _extract_pdf(self, content: bytes) -> Optional[str]:
        """Extract text from PDF file"""
        if not self.attachment_config.get('libraries', {}).get('pdf'):
            return None

        try:
            import pypdf
            from io import BytesIO

            pdf_file = BytesIO(content)
            pdf_reader = pypdf.PdfReader(pdf_file)

            text_parts = []
            for page in pdf_reader.pages:
                text_parts.append(page.extract_text())

            return '\n\n'.join(text_parts)
        except Exception as e:
            print(f"PDF extraction failed: {e}", file=sys.stderr)
            return None

    def _extract_docx(self, content: bytes) -> Optional[str]:
        """Extract text from modern Word (.docx) file"""
        if not self.attachment_config.get('libraries', {}).get('docx'):
            return None

        try:
            import docx
            from io import BytesIO

            doc_file = BytesIO(content)
            doc = docx.Document(doc_file)

            text_parts = []
            for paragraph in doc.paragraphs:
                text_parts.append(paragraph.text)

            return '\n\n'.join(text_parts)
        except Exception as e:
            print(f"DOCX extraction failed: {e}", file=sys.stderr)
            return None

    def _extract_doc_legacy(self, content: bytes, filename: str) -> Optional[str]:
        """
        Legacy Word (.doc) file extraction.

        Note: textract is deprecated and not supported. Only modern .docx files
        can be processed. Legacy .doc files are skipped.
        """
        print(f"Skipping {filename}: Legacy .doc format not supported (use .docx instead)", file=sys.stderr)
        return None

    def _extract_odt(self, content: bytes) -> Optional[str]:
        """Extract text from OpenDocument (.odt) file"""
        if not self.attachment_config.get('libraries', {}).get('odt'):
            return None

        try:
            from odf import text as odf_text, teletype
            from odf.opendocument import load as odf_load
            from io import BytesIO

            odt_file = BytesIO(content)
            doc = odf_load(odt_file)

            # Extract all text elements
            text_parts = []
            for paragraph in doc.getElementsByType(odf_text.P):
                text_parts.append(teletype.extractText(paragraph))

            return '\n\n'.join(text_parts)
        except Exception as e:
            print(f"ODT extraction failed: {e}", file=sys.stderr)
            return None


def main():
    """CLI interface for testing email parser"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Llamabird Email Parser - Parse and extract email content'
    )
    parser.add_argument(
        '--inbox',
        type=str,
        help='Path to specific INBOX file (default: all enabled inboxes)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=5,
        help='Number of emails to parse (default: 5)'
    )
    parser.add_argument(
        '--show-attachments',
        action='store_true',
        help='Show attachment details'
    )

    args = parser.parse_args()

    try:
        # Initialize parser
        email_parser = EmailParser()

        # Get inboxes to process
        if args.inbox:
            inboxes = [Path(args.inbox)]
        else:
            inboxes = email_parser.get_enabled_inboxes()

        if not inboxes:
            print("No enabled inboxes found")
            return 1

        # Process each inbox
        for inbox_path in inboxes:
            print(f"\n{'=' * 70}")
            print(f"Parsing: {inbox_path.parent.name}/INBOX")
            print(f"{'=' * 70}\n")

            for i, email_data in enumerate(email_parser.parse_inbox(inbox_path, limit=args.limit), 1):
                print(f"Email {i}:")
                print(f"  Message-ID: {email_data.message_id}")
                print(f"  From: {email_data.from_addr}")
                print(f"  Subject: {email_data.subject}")
                print(f"  Date: {email_data.date}")
                print(f"  Body length: {len(email_data.body_text)} chars")

                if args.show_attachments and email_data.attachments:
                    print(f"  Attachments: {len(email_data.attachments)}")
                    for att in email_data.attachments:
                        print(f"    • {att.filename} ({att.size_bytes} bytes)")
                        if att.text_content:
                            print(f"      Text extracted: {len(att.text_content)} chars")

                print()

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
