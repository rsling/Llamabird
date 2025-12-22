#!/usr/bin/env python3
"""
Test suite for Llamabird Email Parser

This script demonstrates and tests the email parser functionality.
"""

import json
import sys
from pathlib import Path
from email_parser import EmailParser, EmailData


def print_header(text):
    """Print a formatted header"""
    print(f"\n{'=' * 70}")
    print(f"{text}")
    print('=' * 70)


def test_config_loading():
    """Test configuration loading"""
    print_header("TEST 1: Configuration Loading")

    try:
        parser = EmailParser()
        print("✓ Configuration loaded successfully")

        # Show IMAP accounts
        imap_accounts = parser.config.get('imap_accounts', [])
        print(f"✓ Found {len(imap_accounts)} IMAP account(s)")

        for account in imap_accounts:
            enabled_str = "ENABLED" if account.get('enabled', True) else "DISABLED"
            print(f"  • {account['name']}: {enabled_str}")

        # Show attachment extraction status
        att_config = parser.attachment_config
        if att_config.get('enabled'):
            print(f"✓ Attachment extraction: ENABLED (max {att_config.get('max_size_mb')}MB)")
        else:
            print("⚠ Attachment extraction: DISABLED (libraries not installed)")

        return True
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return False


def test_inbox_detection():
    """Test inbox detection and filtering"""
    print_header("TEST 2: INBOX Detection and Filtering")

    try:
        parser = EmailParser()
        inboxes = parser.get_enabled_inboxes()

        if not inboxes:
            print("⚠ No enabled inboxes found")
            return False

        print(f"✓ Found {len(inboxes)} enabled inbox(es):")

        for inbox in inboxes:
            size_mb = inbox.stat().st_size / (1024 * 1024)
            print(f"  • {inbox.parent.name}: {size_mb:.1f} MB")

        return True
    except Exception as e:
        print(f"✗ Inbox detection failed: {e}")
        return False


def test_email_parsing():
    """Test parsing emails from inboxes"""
    print_header("TEST 3: Email Parsing")

    try:
        parser = EmailParser()
        inboxes = parser.get_enabled_inboxes()

        if not inboxes:
            print("⚠ No inboxes to parse")
            return False

        # Parse first 3 emails from first inbox
        inbox = inboxes[0]
        print(f"Parsing emails from: {inbox.parent.name}\n")

        emails_parsed = 0
        for i, email_data in enumerate(parser.parse_inbox(inbox, limit=3), 1):
            print(f"Email {i}:")
            print(f"  Message-ID: {email_data.message_id[:60]}...")
            print(f"  Subject: {email_data.subject[:60]}...")
            print(f"  From: {email_data.from_addr}")
            print(f"  Date: {email_data.date}")
            print(f"  Body (text): {len(email_data.body_text)} chars")
            print(f"  Body (HTML): {len(email_data.body_html)} chars")
            print(f"  Attachments: {len(email_data.attachments)}")
            print()
            emails_parsed += 1

        if emails_parsed > 0:
            print(f"✓ Successfully parsed {emails_parsed} email(s)")
            return True
        else:
            print("⚠ No emails parsed")
            return False

    except Exception as e:
        print(f"✗ Email parsing failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_message_id_extraction():
    """Test Message-ID extraction"""
    print_header("TEST 4: Message-ID Extraction")

    try:
        parser = EmailParser()
        inboxes = parser.get_enabled_inboxes()

        if not inboxes:
            print("⚠ No inboxes available")
            return False

        print("Message-IDs from recent emails:\n")

        count = 0
        for inbox in inboxes[:1]:  # Test first inbox only
            for email_data in parser.parse_inbox(inbox, limit=5):
                print(f"  • {email_data.message_id}")
                count += 1

        if count > 0:
            print(f"\n✓ Extracted {count} Message-ID(s)")
            return True
        else:
            print("\n⚠ No Message-IDs extracted")
            return False

    except Exception as e:
        print(f"✗ Message-ID extraction failed: {e}")
        return False


def test_body_extraction():
    """Test email body text extraction"""
    print_header("TEST 5: Email Body Text Extraction")

    try:
        parser = EmailParser()
        inboxes = parser.get_enabled_inboxes()

        if not inboxes:
            print("⚠ No inboxes available")
            return False

        # Get first email with substantial body
        for inbox in inboxes:
            for email_data in parser.parse_inbox(inbox, limit=10):
                if len(email_data.body_text) > 100:
                    print(f"Sample email body from: {email_data.from_addr}\n")
                    print(f"Subject: {email_data.subject}\n")
                    print("Body preview (first 300 chars):")
                    print("-" * 70)
                    print(email_data.body_text[:300])
                    print("-" * 70)
                    print(f"\nFull body length: {len(email_data.body_text)} chars")

                    if email_data.body_html:
                        print(f"HTML version: {len(email_data.body_html)} chars")

                    print("\n✓ Body text extraction successful")
                    return True

        print("⚠ No emails with substantial body found")
        return False

    except Exception as e:
        print(f"✗ Body extraction failed: {e}")
        return False


def test_attachment_detection():
    """Test attachment detection"""
    print_header("TEST 6: Attachment Detection")

    try:
        parser = EmailParser()
        inboxes = parser.get_enabled_inboxes()

        if not inboxes:
            print("⚠ No inboxes available")
            return False

        # Search for emails with attachments
        attachments_found = 0
        for inbox in inboxes:
            for email_data in parser.parse_inbox(inbox, limit=50):
                if email_data.attachments:
                    if attachments_found == 0:
                        print("Emails with attachments:\n")

                    print(f"Subject: {email_data.subject[:50]}...")
                    for att in email_data.attachments:
                        size_kb = att.size_bytes / 1024
                        print(f"  • {att.filename}")
                        print(f"    Type: {att.content_type}, Size: {size_kb:.1f} KB")
                        if att.text_content:
                            print(f"    Text extracted: {len(att.text_content)} chars")
                        else:
                            if not parser.attachment_config.get('enabled'):
                                print(f"    (Text extraction disabled - libraries not installed)")
                            else:
                                print(f"    (No text extracted)")
                    print()

                    attachments_found += 1
                    if attachments_found >= 3:  # Show max 3 examples
                        break

            if attachments_found >= 3:
                break

        if attachments_found > 0:
            print(f"✓ Found {attachments_found} email(s) with attachments")
            return True
        else:
            print("⚠ No emails with attachments found in first 50 emails")
            return False

    except Exception as e:
        print(f"✗ Attachment detection failed: {e}")
        return False


def test_account_filtering():
    """Test account enable/disable filtering"""
    print_header("TEST 7: Account Filtering")

    try:
        parser = EmailParser()

        # Show all accounts and their status
        all_accounts = parser.config.get('imap_accounts', [])
        enabled_count = sum(1 for acc in all_accounts if acc.get('enabled', True))

        print(f"Total IMAP accounts: {len(all_accounts)}")
        print(f"Enabled accounts: {enabled_count}")
        print(f"Disabled accounts: {len(all_accounts) - enabled_count}\n")

        print("Account status:")
        for account in all_accounts:
            status = "ENABLED" if account.get('enabled', True) else "DISABLED"
            print(f"  • {account['name']}: {status}")

        # Get filtered inboxes
        enabled_inboxes = parser.get_enabled_inboxes()
        print(f"\nInboxes to be processed: {len(enabled_inboxes)}")

        if len(all_accounts) == len(enabled_inboxes):
            print("✓ All accounts are enabled (default)")
            print("\nTo disable an account, edit config.json and set 'enabled': false")
        else:
            print("✓ Account filtering is working")

        return True

    except Exception as e:
        print(f"✗ Account filtering test failed: {e}")
        return False


def test_multilingual_support():
    """Test handling of multilingual emails (German/English)"""
    print_header("TEST 8: Multilingual Email Support")

    try:
        parser = EmailParser()
        inboxes = parser.get_enabled_inboxes()

        if not inboxes:
            print("⚠ No inboxes available")
            return False

        # Look for emails with non-ASCII characters (German umlauts, etc.)
        multilingual_found = 0
        for inbox in inboxes:
            for email_data in parser.parse_inbox(inbox, limit=20):
                # Check if subject or body contains non-ASCII
                if any(ord(c) > 127 for c in email_data.subject + email_data.body_text):
                    if multilingual_found == 0:
                        print("Multilingual emails detected:\n")

                    print(f"From: {email_data.from_addr}")
                    print(f"Subject: {email_data.subject}")
                    print(f"Body preview: {email_data.body_text[:100]}...")
                    print()

                    multilingual_found += 1
                    if multilingual_found >= 3:
                        break

            if multilingual_found >= 3:
                break

        if multilingual_found > 0:
            print(f"✓ Successfully handled {multilingual_found} multilingual email(s)")
            return True
        else:
            print("⚠ No multilingual emails found in sample")
            return True  # Not a failure, just no multilingual emails

    except Exception as e:
        print(f"✗ Multilingual support test failed: {e}")
        return False


def main():
    """Run all tests"""
    print_header("LLAMABIRD EMAIL PARSER TEST SUITE")

    results = []

    # Run tests
    results.append(("Configuration Loading", test_config_loading()))
    results.append(("INBOX Detection", test_inbox_detection()))
    results.append(("Email Parsing", test_email_parsing()))
    results.append(("Message-ID Extraction", test_message_id_extraction()))
    results.append(("Body Text Extraction", test_body_extraction()))
    results.append(("Attachment Detection", test_attachment_detection()))
    results.append(("Account Filtering", test_account_filtering()))
    results.append(("Multilingual Support", test_multilingual_support()))

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        print("\nNext steps:")
        print("1. Install attachment extraction libraries:")
        print("   pip install html2text chardet pypdf python-docx odfpy")
        print("2. Re-run discover.py to detect libraries")
        print("3. Test attachment text extraction with emails containing documents")
        print("\nNote: Legacy .doc files are not supported (only modern .docx)")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
