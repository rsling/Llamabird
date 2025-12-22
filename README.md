<p align="center">
  <img src="icon.png" width="400" alt="Llamabird Logo" />
</p>

# Llamabird

AI-powered email summarizer for Thunderbird/Betterbird using local Ollama models.

## Quick Start

### 1. Environment Discovery

Run the discovery script to verify your environment:

```bash
cd llamabird
python3 discover.py
```

To use a specific Ollama model:

```bash
python3 discover.py --model mistral-nemo:12b
```

The script will:
- Find your Thunderbird/Betterbird profile
- Locate mail storage and QNote directories
- Check Ollama connectivity
- Verify the specified model is installed
- Generate a `config.json` with all discovered paths

### 2. Install Ollama Model (if needed)

If the discovery script reports your model is not installed:

```bash
ollama pull qwen2.5
# or
ollama pull mistral-nemo:12b
```

### 3. Test QNote Writer

Run the test suite to verify QNote creation:

```bash
python3 test_qnote.py
```

Use the CLI to manually create/read QNotes:

```bash
# Write a QNote
python3 qnote_writer.py write "<message-id@example.com>" "Summary text here"

# List all QNotes
python3 qnote_writer.py list

# Read a QNote
python3 qnote_writer.py read "<message-id@example.com>"

# Check if QNote exists
python3 qnote_writer.py check "<message-id@example.com>"

# Delete a QNote
python3 qnote_writer.py delete "<message-id@example.com>"
```

### 4. Install Email Parsing Libraries (Optional but Recommended)

Install libraries for full attachment text extraction support:

```bash
# Install Python dependencies
pip install html2text chardet pypdf python-docx odfpy

# Re-run discovery to detect new libraries
python3 discover.py
```

Core libraries (html2text, chardet) are highly recommended for proper email parsing. Attachment libraries (pypdf, python-docx, odfpy) are optional but enable text extraction from email attachments.

**Note**: Legacy .doc file format is not supported (textract is deprecated). Only modern .docx files can be processed via python-docx.

### 5. Test Email Parser

Run the comprehensive test suite:

```bash
python3 test_email_parser.py
```

Parse emails from your inboxes:

```bash
# Parse first 5 emails from all enabled inboxes
python3 email_parser.py --limit 5

# Parse from specific inbox
python3 email_parser.py --inbox /path/to/INBOX --limit 10

# Show attachment details
python3 email_parser.py --limit 5 --show-attachments
```

### 6. Test Ollama Summarizer

Test AI-powered email summarization with performance profiling:

```bash
# Summarize first 3 emails (basic test)
python3 ollama_summarizer.py --limit 3

# Summarize with detailed profiling
python3 ollama_summarizer.py --limit 5 --profile

# Preload model before summarizing (recommended for batch processing)
python3 ollama_summarizer.py --limit 5 --profile --preload
```

**Performance Results** (qwen2.5:7b on typical hardware):

Without preload:
- First email: ~4.8s (includes model loading)
- Subsequent emails: ~2.8s
- Throughput: ~15.8 emails/minute

With preload:
- Model load time: ~9.6s (one-time cost)
- All emails: ~2.2s average (41% faster)
- Throughput: ~26.7 emails/minute (69% improvement)

**Recommended Strategy**: For background operation, preload the model at startup for optimal throughput.

### 7. Run Llamabird (Manual Mode)

The main integration script combines email parsing, AI summarization, and QNote creation:

```bash
# Process all emails from all enabled accounts (creates QNote files)
python3 llamabird.py

# Process only first 10 emails
python3 llamabird.py --limit 10

# Display summaries to stdout instead of creating QNote files (with paging)
python3 llamabird.py --limit 5 --no-qnote

# Preload model for better performance (recommended for batch processing)
python3 llamabird.py --limit 20 --preload --profile

# Process only a specific account
python3 llamabird.py --limit 10 --account uni-jena

# Combine options
python3 llamabird.py --limit 50 --preload --profile --account your-server
```

**Command-line Options:**
- `--limit N`: Process only first N emails (default: all)
- `--no-qnote`: Display summaries to stdout with paging instead of creating QNote files
- `--preload`: Preload AI model before processing (improves throughput by ~69%)
- `--profile`: Show detailed performance profiling
- `--account NAME`: Only process emails from accounts matching NAME

**Default Behavior (QNote Mode):**
- Processes all emails from all enabled accounts
- Automatically skips emails that already have QNote files
- Creates QNote files that appear in Thunderbird/Betterbird
- Shows progress and statistics

**Stdout Mode (--no-qnote):**
- Displays formatted summaries with more-style paging
- Shows: From (real name), Subject, Date, and AI-generated summary
- Press 'q' to quit the pager, space for next page
- Useful for reviewing summaries before committing to QNote files

### 8. Set Up Automatic Summarization (Daemon)

Run Llamabird as a background service that automatically summarizes new emails as they arrive.

#### Installation

Run the installation script to set up the daemon:

```bash
cd llamabird
./install_daemon.sh
```

This will:
- Install the `watchdog` dependency for file monitoring
- Update your configuration with daemon settings
- Create a systemd user service
- Enable automatic startup at login

#### Daemon Usage

**Start the daemon:**
```bash
systemctl --user start llamabird
```

**Check daemon status:**
```bash
systemctl --user status llamabird
```

**View live logs:**
```bash
journalctl --user -u llamabird -f
```

**Stop the daemon:**
```bash
systemctl --user stop llamabird
```

**Disable autostart:**
```bash
systemctl --user disable llamabird
```

#### How It Works

**Auto Mode (Default):**
1. Monitors all enabled INBOX files for modifications
2. When an email arrives, starts a 30-second debounce timer
3. If more emails arrive within 30s, the timer resets
4. When the timer expires, processes all new emails in batch
5. AI model stays loaded in memory for fast processing (~2-3s per email)

**Behavior:**
- New emails get summaries within ~30 seconds of arrival
- Multiple emails arriving together are batched efficiently
- Only processes emails that don't already have QNotes
- Respects sender whitelist/blacklist and deleted email filtering
- Automatically restarts if it crashes (systemd)
- Starts automatically at login

#### Configuration

The daemon settings are in `config.json`:

```json
{
  "daemon": {
    "mode": "auto",
    "debounce_seconds": 30,
    "interval_minutes": 5,
    "preload_model": true,
    "max_emails_per_run": 50,
    "log_file": "llamabird_daemon.log",
    "log_level": "INFO"
  }
}
```

**Settings:**
- `mode`: "auto" (file watching) or "interval" (periodic)
- `debounce_seconds`: Wait time after last email before processing (auto mode)
- `interval_minutes`: Process every N minutes (interval mode)
- `preload_model`: Load AI model on startup for better performance
- `max_emails_per_run`: Safety limit per processing cycle
- `log_file`: Log file location
- `log_level`: DEBUG, INFO, WARNING, or ERROR

**Interval Mode:**
To use periodic processing instead of file watching, change mode to "interval":

```json
{
  "daemon": {
    "mode": "interval",
    "interval_minutes": 5
  }
}
```

Then restart the daemon: `systemctl --user restart llamabird`

### 9. Configure Summary Language

Llamabird can generate summaries in any language, regardless of the email's language. The default is German.

Edit `config.json` to change the summary language:

```json
{
  "summary_language": "German"
}
```

**Supported Languages:**
- Use natural language names: "German", "English", "Spanish", "French", "Italian", etc.
- The AI will generate summaries in the specified language regardless of the email's language
- Example: German emails will be summarized in English if `"summary_language": "English"`

**Example:**
```json
{
  "summary_language": "English"
}
```
This will generate all summaries in English, even for German emails.

### 10. Customize Summarization Prompts (Optional)

The summarizer uses a default prompt that:
- Summarizes the main email body (excludes quoted reply text)
- Includes key information from attachments
- Uses real names instead of email addresses
- Writes summaries in the configured language (see above)

To customize the prompt, edit `config.json`:

```json
{
  "summarizer_prompts": {
    "template": "Your custom prompt template here with placeholders: {from_name}, {from_addr}, {to_info}, {subject}, {date}, {body}, {attachments_section}",
    "max_body_length": 10000,
    "max_attachment_length": 2000,
    "model_options": {
      "temperature": 0.7,
      "num_predict": 200
    },
    "instructions": {
      "include_quoted_text": false,
      "include_recipients": true,
      "include_attachments": true,
      "use_real_names": true
    }
  }
}
```

Set `"template": null` to use the default prompt.

### 11. Configure Sender Filtering (Optional)

Llamabird automatically skips emails marked as deleted in Thunderbird. You can also filter emails by sender address using whitelist and blacklist patterns.

Edit `config.json` to add sender filters:

```json
{
  "sender_filtering": {
    "whitelist": ["*@uni-jena.de", "anna@web.de"],
    "blacklist": ["*@spam-domain.com", "no-reply@marketing.com"]
  }
}
```

**Filtering Logic:**
- **Whitelist**: Emails from addresses matching whitelist patterns are **always processed**, even if they match blacklist patterns
- **Blacklist**: Emails from addresses matching blacklist patterns are **skipped**, unless they also match whitelist patterns
- **Default**: If an email matches neither whitelist nor blacklist, it is processed normally
- **Deleted emails**: Always skipped, regardless of whitelist/blacklist

**Wildcard Patterns:**
- `*@uni-jena.de` - Matches any address at uni-jena.de domain
- `anna@web.de` - Exact match only
- `spam*` - Matches addresses starting with "spam"
- `*spam*` - Matches addresses containing "spam"

**Example Use Cases:**
```json
{
  "sender_filtering": {
    "whitelist": ["*@uni-jena.de"],
    "blacklist": ["*@uber.com"]
  }
}
```
This configuration will:
- Always process emails from uni-jena.de addresses
- Skip all Uber emails
- Process all other emails normally

**Whitelist Override:**
```json
{
  "sender_filtering": {
    "whitelist": ["no-reply@uber.com"],
    "blacklist": ["*@uber.com"]
  }
}
```
This configuration will:
- Process emails from no-reply@uber.com (whitelist overrides blacklist)
- Skip all other @uber.com addresses
- Process all other emails normally

### 12. Configure Account Filtering (Optional)

To exclude specific email accounts from summarization, edit `config.json`:

```json
{
  "imap_accounts": [
    {
      "name": "imap.example.com",
      "path": "...",
      "inbox_path": "...",
      "enabled": true   // Set to false to disable this account
    }
  ]
}
```

## Project Status

**Current Step:** Step 6 - File Monitor & Automation ✓

### Development Roadmap

- [x] Step 1: Foundation & Environment Discovery
- [x] Step 2: QNote Writer Module
- [x] Step 3: Email Parser Module
- [x] Step 4: Ollama Summarizer Module
- [x] Step 5: Integration - Manual Mode
- [x] Step 6: File Monitor & Automation
- [ ] Step 7: Production Hardening

## Requirements

- Python 3.8+
- Thunderbird or Betterbird with QNote extension
- Ollama running locally
- At least one Ollama model installed

## Configuration

After running `discover.py`, a `config.json` file will be created with:
- Profile path
- QNote storage location
- Mail storage paths (Mail and ImapMail)
- IMAP account detection with enable/disable flags
- Attachment extraction library status
- Ollama model selection
- Summarization prompt configuration

### Key Configuration Fields

- **imap_accounts**: List of detected IMAP accounts with INBOX paths
  - Set `enabled: false` to exclude an account from summarization
  - By default, all accounts are enabled
  - Only INBOX folders are processed (Archive, Trash, etc. are ignored)
  - Smart mailboxes (unified folders) are automatically excluded

- **attachment_extraction**: Settings for attachment text extraction
  - `enabled`: Whether any extraction libraries are available
  - `max_size_mb`: Maximum file size for text extraction (default: 10 MB)
  - `libraries`: Status of each library (pypdf, python-docx, odfpy, html2text, chardet)
  - `missing`: List of missing libraries to install
  - **Note**: Legacy .doc files are not supported (only modern .docx)

- **summarizer_prompts**: AI summarization configuration
  - `template`: Custom prompt template (null = use default)
  - `max_body_length`: Maximum email body length to send to AI (default: 10000 chars)
  - `max_attachment_length`: Maximum attachment text length (default: 2000 chars)
  - `model_options`: Ollama model parameters (temperature, num_predict, etc.)
  - `instructions`: Summarization preferences
    - `include_quoted_text`: Include quoted reply text in summary (default: false)
    - `include_recipients`: Mention recipients in summary (default: true)
    - `include_attachments`: Include attachment content in summary (default: true)
    - `use_real_names`: Use real names instead of email addresses (default: true)

- **sender_filtering**: Sender whitelist/blacklist configuration
  - `whitelist`: List of sender patterns to always process (overrides blacklist)
  - `blacklist`: List of sender patterns to skip
  - Supports wildcards: `*@domain.com`, `user@*`, `*spam*`
  - Empty lists = no filtering (process all non-deleted emails)
  - **Note**: Deleted emails are always skipped automatically

- **summary_language**: Language for AI-generated summaries
  - Natural language name (e.g., "German", "English", "Spanish")
  - Default: "German"
  - Summaries will be written in this language regardless of the email's language

- **daemon**: Automatic summarization daemon settings
  - `mode`: "auto" (file watching) or "interval" (periodic) - Default: "auto"
  - `debounce_seconds`: Wait time after last email before processing - Default: 30
  - `interval_minutes`: Minutes between checks in interval mode - Default: 5
  - `preload_model`: Preload AI model on startup - Default: true
  - `max_emails_per_run`: Maximum emails to process per cycle - Default: 50
  - `log_file`: Daemon log file location - Default: "llamabird_daemon.log"
  - `log_level`: Logging verbosity (DEBUG, INFO, WARNING, ERROR) - Default: "INFO"

This configuration will be used by subsequent Llamabird components.
