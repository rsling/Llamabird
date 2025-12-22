#!/usr/bin/env python3
"""
Llamabird Environment Discovery Script

This script discovers and validates the environment needed for Llamabird:
- Thunderbird/Betterbird profile location
- Mail storage format and location
- QNote storage directory
- Ollama installation and available models
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional, Dict, List
import urllib.request
import urllib.error


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print a section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * 70}{Colors.END}")


def print_success(text: str):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_warning(text: str):
    """Print a warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_error(text: str):
    """Print an error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_info(label: str, value: str):
    """Print an info line"""
    print(f"  {Colors.BOLD}{label}:{Colors.END} {value}")


def find_thunderbird_profiles() -> List[Path]:
    """
    Search for Thunderbird/Betterbird profile directories.
    Returns list of possible profile base directories.
    """
    home = Path.home()
    possible_locations = [
        home / ".thunderbird",
        home / ".var/app/org.mozilla.Thunderbird/.thunderbird",
        home / ".var/app/eu.betterbird.Betterbird/.thunderbird",
    ]

    found = []
    for location in possible_locations:
        if location.exists():
            found.append(location)

    return found


def find_profile_folder(base_path: Path) -> Optional[Path]:
    """
    Find the actual profile folder by parsing profiles.ini.
    Prioritizes [Install*] sections (used by Flatpak) over Default=1 profiles.
    """
    if not base_path.exists():
        return None

    # Look for profiles.ini to find the default profile
    profiles_ini = base_path / "profiles.ini"
    if not profiles_ini.exists():
        # Fallback: look for directories ending with .default or .default-release
        for item in base_path.iterdir():
            if item.is_dir() and ('.default' in item.name):
                return item
        return None

    # Parse profiles.ini
    with open(profiles_ini, 'r') as f:
        lines = f.readlines()

    current_section = None
    sections = {}

    for line in lines:
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            sections[current_section] = {}
        elif '=' in line and current_section:
            key, value = line.split('=', 1)
            sections[current_section][key.strip()] = value.strip()

    # Priority 1: Check [Install*] sections (Flatpak and modern installations)
    for section_name, section_data in sections.items():
        if section_name.startswith('Install'):
            if 'Default' in section_data:
                profile_path = base_path / section_data['Default']
                if profile_path.exists():
                    return profile_path

    # Priority 2: Look for Default=1 profile
    for section_name, section_data in sections.items():
        if section_name.startswith('Profile'):
            if section_data.get('Default') == '1' and 'Path' in section_data:
                profile_path = base_path / section_data['Path']
                if profile_path.exists():
                    return profile_path

    # Priority 3: Any profile with a Path
    for section_name, section_data in sections.items():
        if section_name.startswith('Profile') and 'Path' in section_data:
            profile_path = base_path / section_data['Path']
            if profile_path.exists():
                return profile_path

    # Fallback: look for directories ending with .default or .default-release
    for item in base_path.iterdir():
        if item.is_dir() and ('.default' in item.name):
            return item

    return None


def find_qnote_directory(profile_path: Path) -> Optional[Path]:
    """
    Find the QNote storage directory within the profile
    """
    qnote_path = profile_path / "QNote"
    if qnote_path.exists() and qnote_path.is_dir():
        return qnote_path
    return None


def find_mail_storage(profile_path: Path) -> Dict[str, any]:
    """
    Find mail storage location and determine format (mbox or Maildir)
    """
    result = {
        'found': False,
        'path': None,
        'format': None,
        'accounts': []
    }

    # Mail is typically stored in Mail subdirectory
    mail_path = profile_path / "Mail"
    if not mail_path.exists():
        return result

    result['found'] = True
    result['path'] = mail_path

    # Look for mail account directories
    for item in mail_path.iterdir():
        if item.is_dir():
            # Check if it contains mbox files or Maildir structure
            has_mbox = any(f.is_file() and not f.suffix for f in item.iterdir() if not f.name.startswith('.'))
            has_maildir = (item / "cur").exists() or (item / "new").exists()

            if has_mbox or has_maildir:
                result['accounts'].append({
                    'name': item.name,
                    'path': item,
                    'format': 'Maildir' if has_maildir else 'mbox'
                })

    if result['accounts']:
        # Set overall format (assuming first account's format)
        result['format'] = result['accounts'][0]['format']

    return result


def find_imap_accounts(profile_path: Path) -> List[Dict]:
    """
    Find all IMAP accounts with INBOX files
    """
    imap_path = profile_path / "ImapMail"
    accounts = []

    if not imap_path.exists():
        return accounts

    for account_dir in imap_path.iterdir():
        # Skip .msf files and other non-directory items
        if not account_dir.is_dir() or account_dir.name.endswith('.msf'):
            continue

        inbox_file = account_dir / "INBOX"
        if inbox_file.exists() and inbox_file.is_file():
            accounts.append({
                "name": account_dir.name,
                "path": str(account_dir),
                "inbox_path": str(inbox_file),
                "enabled": True  # Default: all enabled
            })

    return accounts


def check_attachment_libraries() -> Dict:
    """
    Check which text extraction libraries are available
    """
    libraries = {}
    missing_libs = []

    # Core libraries (recommended)
    try:
        import html2text
        libraries['html2text'] = 'html2text'
    except ImportError:
        libraries['html2text'] = None
        missing_libs.append('html2text')

    try:
        import chardet
        libraries['chardet'] = 'chardet'
    except ImportError:
        libraries['chardet'] = None
        missing_libs.append('chardet')

    # Attachment extraction libraries (optional)
    try:
        import pypdf
        libraries['pdf'] = 'pypdf'
    except ImportError:
        libraries['pdf'] = None
        missing_libs.append('pypdf')

    try:
        import docx
        libraries['docx'] = 'python-docx'
    except ImportError:
        libraries['docx'] = None
        missing_libs.append('python-docx')

    try:
        import odf
        libraries['odt'] = 'odfpy'
    except ImportError:
        libraries['odt'] = None
        missing_libs.append('odfpy')

    # Note: textract is deprecated and not included
    # Legacy .doc files are not supported, only modern .docx files

    # At least one attachment library should be available
    enabled = any(libraries[k] is not None for k in ['pdf', 'docx', 'odt'])

    return {
        "enabled": enabled,
        "max_size_mb": 10,  # Maximum attachment size for text extraction
        "libraries": libraries,
        "missing": missing_libs
    }


def check_ollama_connection() -> bool:
    """
    Check if Ollama is running and accessible
    """
    try:
        req = urllib.request.Request('http://localhost:11434/api/tags')
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def get_ollama_models() -> List[str]:
    """
    Get list of installed Ollama models
    """
    try:
        req = urllib.request.Request('http://localhost:11434/api/tags')
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            models = [model['name'] for model in data.get('models', [])]
            return models
    except Exception as e:
        return []


def test_ollama_model(model_name: str) -> Optional[str]:
    """
    Test if a specific model is available in Ollama.

    Args:
        model_name: Model name or prefix to search for

    Returns:
        Full model name if found, None if not found
    """
    models = get_ollama_models()
    # Model names might have tags like :latest, so check partial matches
    for model in models:
        if model.startswith(model_name) or model == model_name:
            return model  # Return full model name
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Llamabird Environment Discovery - Find and validate all required components'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='qwen2.5',
        help='Ollama model to use for summarization (default: qwen2.5)'
    )

    args = parser.parse_args()

    print_header("LLAMABIRD ENVIRONMENT DISCOVERY")
    print(f"\nScanning your system for required components...\n")

    # Track overall status
    all_good = True
    config = {}

    # 1. Find Thunderbird/Betterbird
    print_header("1. Thunderbird/Betterbird Profile")

    profile_bases = find_thunderbird_profiles()
    if not profile_bases:
        print_error("No Thunderbird or Betterbird installation found")
        print_info("Searched", "~/.thunderbird, ~/.var/app/*/thunderbird")
        all_good = False
    else:
        for base in profile_bases:
            print_success(f"Found profile base: {base}")

            profile = find_profile_folder(base)
            if profile:
                print_success(f"Found active profile: {profile}")
                config['profile_path'] = str(profile)

                # Store for later checks
                active_profile = profile
                break
        else:
            print_warning("Profile base found but could not locate active profile folder")
            all_good = False

    # 2. Find QNote directory
    print_header("2. QNote Storage Directory")

    if 'profile_path' in config:
        qnote_dir = find_qnote_directory(Path(config['profile_path']))
        if qnote_dir:
            print_success(f"QNote directory found: {qnote_dir}")
            print_info("QNote files", f"{len(list(qnote_dir.glob('*.qnote')))} existing notes")
            config['qnote_path'] = str(qnote_dir)
        else:
            print_warning("QNote directory not found")
            print_info("Expected location", f"{config['profile_path']}/QNote")
            print_info("Note", "QNote directory will be created when first note is saved")
            # Not critical - QNote dir will be created
    else:
        print_error("Cannot check QNote directory (profile not found)")
        all_good = False

    # 3. Find mail storage
    print_header("3. Mail Storage Location")

    if 'profile_path' in config:
        mail_info = find_mail_storage(Path(config['profile_path']))
        if mail_info['found']:
            print_success(f"Mail directory found: {mail_info['path']}")
            print_info("Format", mail_info['format'] or "Unknown")
            print_info("Accounts found", str(len(mail_info['accounts'])))

            for account in mail_info['accounts']:
                print(f"    • {account['name']} ({account['format']})")

            config['mail_path'] = str(mail_info['path'])
            config['mail_format'] = mail_info['format']
            config['mail_accounts'] = [
                {'name': acc['name'], 'path': str(acc['path']), 'format': acc['format']}
                for acc in mail_info['accounts']
            ]
        else:
            print_error("Mail storage not found")
            all_good = False
    else:
        print_error("Cannot check mail storage (profile not found)")
        all_good = False

    # 4. Find IMAP accounts
    print_header("4. IMAP Email Accounts")

    if 'profile_path' in config:
        imap_accounts = find_imap_accounts(Path(config['profile_path']))
        if imap_accounts:
            print_success(f"Found {len(imap_accounts)} IMAP account(s) with INBOX")

            for account in imap_accounts:
                inbox_path = Path(account['inbox_path'])
                size_mb = inbox_path.stat().st_size / (1024 * 1024)
                print(f"    • {account['name']}: {size_mb:.1f} MB")

            config['imap_mail_path'] = str(Path(config['profile_path']) / "ImapMail")
            config['imap_accounts'] = imap_accounts
        else:
            print_warning("No IMAP accounts found")
            print_info("Note", "Only IMAP INBOX folders will be summarized")
            config['imap_accounts'] = []
    else:
        print_error("Cannot check IMAP accounts (profile not found)")
        all_good = False

    # 5. Check attachment extraction libraries
    print_header("5. Attachment Text Extraction Libraries")

    attachment_info = check_attachment_libraries()
    config['attachment_extraction'] = attachment_info

    # Show available libraries
    available = [name for name, lib in attachment_info['libraries'].items() if lib is not None]
    if available:
        print_success(f"Found {len(available)} library/libraries")
        for lib_type, lib_name in attachment_info['libraries'].items():
            if lib_name:
                print(f"    • {lib_type}: {lib_name}")

    # Show missing libraries
    if attachment_info['missing']:
        print()
        print_warning(f"{len(attachment_info['missing'])} library/libraries missing")
        for lib in attachment_info['missing']:
            print(f"    • {lib}")

        print()
        print_info("Install missing libraries",
                   "pip install " + " ".join(attachment_info['missing']))

    # Overall status
    if attachment_info['enabled']:
        print()
        print_success("Attachment text extraction is ENABLED")
        print_info("Max size", f"{attachment_info['max_size_mb']} MB")
    else:
        print()
        print_warning("Attachment text extraction is DISABLED (no libraries available)")
        print_info("Note", "Email summaries will not include attachment content")

    # 6. Check Ollama
    print_header("6. Ollama AI Service")

    if check_ollama_connection():
        print_success("Ollama is running and accessible")

        models = get_ollama_models()
        print_info("Installed models", f"{len(models)} found")

        for model in models:
            print(f"    • {model}")

        # Check requested model
        print(f"\n  Checking requested model: {Colors.BOLD}{args.model}{Colors.END}")

        full_model_name = test_ollama_model(args.model)
        if full_model_name:
            print_success(f"Model '{full_model_name}' is available")
            config['ollama_model'] = full_model_name  # Save full model name with tag
        else:
            print_error(f"Model '{args.model}' is NOT installed")
            print_info("Install with", f"ollama pull {args.model}")
            all_good = False

        config['ollama_url'] = 'http://localhost:11434'
    else:
        print_error("Ollama is not running or not accessible")
        print_info("Expected", "http://localhost:11434")
        print_info("Start with", "ollama serve")
        all_good = False

    # Summary
    print_header("DISCOVERY SUMMARY")

    if all_good:
        print_success("All components found and validated!")

        # Add summarizer prompts configuration if not present
        if 'summarizer_prompts' not in config:
            config['summarizer_prompts'] = {
                "template": None,  # null = use default
                "max_body_length": 10000,
                "max_attachment_length": 2000,
                "model_options": {},
                "instructions": {
                    "include_quoted_text": False,
                    "include_recipients": True,
                    "include_attachments": True,
                    "use_real_names": True
                }
            }

        # Add sender filtering configuration if not present
        if 'sender_filtering' not in config:
            config['sender_filtering'] = {
                "whitelist": [],  # e.g., ["*@uni-jena.de", "anna@web.de"]
                "blacklist": []   # e.g., ["spam@example.com", "*@spam-domain.com"]
            }

        # Add summary language configuration if not present
        if 'summary_language' not in config:
            config['summary_language'] = "German"  # Default to German

        print(f"\n{Colors.BOLD}Configuration for Llamabird:{Colors.END}\n")
        print(json.dumps(config, indent=2))

        # Save configuration
        config_file = Path(__file__).parent / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, indent=2, fp=f)

        print(f"\n{Colors.GREEN}Configuration saved to: {config_file}{Colors.END}")
        return 0
    else:
        print_error("Some components are missing or not configured correctly")
        print_warning("Please resolve the issues above before proceeding")
        return 1


if __name__ == '__main__':
    sys.exit(main())
