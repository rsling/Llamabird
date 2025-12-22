#!/usr/bin/env python3
"""
Llamabird Ollama Summarizer Module

This module handles sending email content to Ollama for AI summarization.
Includes performance profiling and configurable prompts.
"""

import json
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass
from email_parser import EmailData


@dataclass
class SummaryResult:
    """Result of email summarization"""
    message_id: str
    summary: str
    duration_seconds: float
    model_name: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class OllamaSummarizer:
    """
    Handles email summarization using Ollama AI models.

    Features:
    - Configurable prompts
    - Performance profiling
    - Model loading strategy testing
    - German and English support
    """

    # Default prompt template
    DEFAULT_PROMPT_TEMPLATE = """You are an email summarization assistant. Summarize the following email concisely and clearly.

Focus on:
- The main message body (exclude quoted reply text unless specifically important)
- Key information from ALL attachments (if multiple attachments, summarize each one)
- Who sent the email to whom (use real names from the email, not email addresses)

Email details:
From: {from_name} ({from_addr})
To: {to_info}
Subject: {subject}
Date: {date}

Email body:
{body}

{attachments_section}

Provide a clear, concise summary in 2-4 sentences. IMPORTANT: If there are multiple attachments, mention all of them in your summary. Write your summary in {language}, regardless of the email's language."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize Ollama summarizer.

        Args:
            config_path: Path to config.json (default: auto-detect)
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"

        self.config = self._load_config(config_path)
        self.ollama_url = self.config.get('ollama_url', 'http://localhost:11434')
        self.model_name = self.config.get('ollama_model', 'qwen2.5')

        # Load prompt configuration
        self.prompt_config = self.config.get('summarizer_prompts', {})
        template = self.prompt_config.get('template')
        self.prompt_template = template if template is not None else self.DEFAULT_PROMPT_TEMPLATE

        # Load summary language (default: German)
        self.summary_language = self.config.get('summary_language', 'German')

        # Profiling data
        self.profile_data = {
            'model_loads': [],
            'summaries': []
        }

    def _load_config(self, config_path: Path) -> Dict:
        """Load configuration from JSON file"""
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                "Please run discover.py first to generate config.json"
            )

        with open(config_path, 'r') as f:
            return json.load(f)

    def check_model_loaded(self) -> bool:
        """
        Check if the model is currently loaded in Ollama.

        Returns:
            True if model is loaded, False otherwise

        Note: This check may not work on all Ollama versions.
        """
        try:
            # Try to use /api/ps endpoint (may not be available on all versions)
            req = urllib.request.Request(f'{self.ollama_url}/api/ps')
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                running_models = data.get('models', [])

                for model in running_models:
                    if model.get('name', '').startswith(self.model_name):
                        return True

                return False
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Endpoint not available on this Ollama version
                return None  # Unknown status
            return False
        except Exception:
            return False

    def preload_model(self) -> float:
        """
        Preload the model into memory by making a minimal request.

        Returns:
            Time taken to load model in seconds
        """
        start_time = time.time()

        try:
            payload = {
                "model": self.model_name,
                "prompt": "test",
                "stream": False,
                "options": {
                    "num_predict": 1  # Minimal generation
                }
            }

            req = urllib.request.Request(
                f'{self.ollama_url}/api/generate',
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                response.read()  # Consume response

            duration = time.time() - start_time
            self.profile_data['model_loads'].append(duration)

            return duration

        except Exception as e:
            print(f"Error preloading model: {e}", file=sys.stderr)
            return 0.0

    def summarize_email(self, email_data: EmailData) -> SummaryResult:
        """
        Generate a summary for an email using Ollama.

        Args:
            email_data: Parsed email data

        Returns:
            SummaryResult with summary and profiling info
        """
        start_time = time.time()

        # Build prompt from template
        prompt = self._build_prompt(email_data)

        # Call Ollama API
        try:
            summary_text, token_info = self._call_ollama(prompt)

            duration = time.time() - start_time

            result = SummaryResult(
                message_id=email_data.message_id,
                summary=summary_text,
                duration_seconds=duration,
                model_name=self.model_name,
                prompt_tokens=token_info.get('prompt_eval_count', 0),
                completion_tokens=token_info.get('eval_count', 0),
                total_tokens=token_info.get('prompt_eval_count', 0) + token_info.get('eval_count', 0)
            )

            # Record profiling data
            self.profile_data['summaries'].append({
                'duration': duration,
                'tokens': result.total_tokens,
                'message_id': email_data.message_id
            })

            return result

        except Exception as e:
            duration = time.time() - start_time
            print(f"Error summarizing email: {e}", file=sys.stderr)

            # Return error result
            return SummaryResult(
                message_id=email_data.message_id,
                summary=f"[Error: Could not generate summary - {str(e)}]",
                duration_seconds=duration,
                model_name=self.model_name
            )

    def _build_prompt(self, email_data: EmailData) -> str:
        """
        Build the prompt for summarization using the configured template.

        Args:
            email_data: Parsed email data

        Returns:
            Formatted prompt string
        """
        # Extract sender name from email address
        from_name = email_data.from_addr.split('@')[0] if email_data.from_addr else "Unknown"

        # Format date
        date_str = str(email_data.date) if email_data.date else "Unknown"

        # Handle recipients (simplified - we don't have To: header yet)
        to_info = "recipients"  # TODO: Extract from headers if needed

        # Get body text
        body = email_data.body_text or email_data.body_html or "[No body content]"

        # Trim very long bodies to avoid token limits
        max_body_length = self.prompt_config.get('max_body_length', 10000)
        if len(body) > max_body_length:
            body = body[:max_body_length] + "\n\n[... truncated ...]"

        # Build attachments section
        attachments_section = ""
        if email_data.attachments:
            attachments_section = "Attachments:\n"
            for att in email_data.attachments:
                attachments_section += f"- {att.filename}"
                if att.text_content:
                    # Include attachment text, but limit length
                    max_att_length = self.prompt_config.get('max_attachment_length', 2000)
                    att_text = att.text_content[:max_att_length]
                    if len(att.text_content) > max_att_length:
                        att_text += "\n[... truncated ...]"
                    attachments_section += f"\n  Content: {att_text}\n"
                else:
                    attachments_section += "\n"

        # Format the prompt
        prompt = self.prompt_template.format(
            from_name=from_name,
            from_addr=email_data.from_addr,
            to_info=to_info,
            subject=email_data.subject,
            date=date_str,
            body=body,
            attachments_section=attachments_section,
            language=self.summary_language
        )

        return prompt

    def _call_ollama(self, prompt: str) -> tuple[str, Dict]:
        """
        Call Ollama API with the given prompt.

        Args:
            prompt: The prompt to send

        Returns:
            Tuple of (summary_text, token_info)
        """
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": self.prompt_config.get('model_options', {})
        }

        req = urllib.request.Request(
            f'{self.ollama_url}/api/generate',
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode('utf-8'))

            summary_text = result.get('response', '').strip()

            # Extract token information
            token_info = {
                'prompt_eval_count': result.get('prompt_eval_count', 0),
                'eval_count': result.get('eval_count', 0),
                'total_duration': result.get('total_duration', 0),
                'load_duration': result.get('load_duration', 0),
                'prompt_eval_duration': result.get('prompt_eval_duration', 0),
                'eval_duration': result.get('eval_duration', 0)
            }

            return summary_text, token_info

    def get_profiling_summary(self) -> Dict:
        """
        Get summary of profiling data.

        Returns:
            Dictionary with profiling statistics
        """
        summary = {
            'model_loads': {
                'count': len(self.profile_data['model_loads']),
                'total_time': sum(self.profile_data['model_loads']),
                'avg_time': sum(self.profile_data['model_loads']) / len(self.profile_data['model_loads']) if self.profile_data['model_loads'] else 0
            },
            'summaries': {
                'count': len(self.profile_data['summaries']),
                'total_time': sum(s['duration'] for s in self.profile_data['summaries']),
                'avg_time': sum(s['duration'] for s in self.profile_data['summaries']) / len(self.profile_data['summaries']) if self.profile_data['summaries'] else 0,
                'total_tokens': sum(s['tokens'] for s in self.profile_data['summaries']),
                'avg_tokens': sum(s['tokens'] for s in self.profile_data['summaries']) / len(self.profile_data['summaries']) if self.profile_data['summaries'] else 0
            }
        }

        return summary


def main():
    """CLI interface for testing summarizer"""
    import argparse
    from email_parser import EmailParser

    parser = argparse.ArgumentParser(
        description='Llamabird Ollama Summarizer - Test email summarization'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=3,
        help='Number of emails to summarize (default: 3)'
    )
    parser.add_argument(
        '--profile',
        action='store_true',
        help='Show detailed profiling information'
    )
    parser.add_argument(
        '--preload',
        action='store_true',
        help='Preload model before summarizing'
    )

    args = parser.parse_args()

    try:
        # Initialize components
        print("Initializing Ollama Summarizer...")
        summarizer = OllamaSummarizer()
        email_parser = EmailParser()

        print(f"Using model: {summarizer.model_name}")
        print(f"Ollama URL: {summarizer.ollama_url}\n")

        # Check model status
        model_status = summarizer.check_model_loaded()
        if model_status is True:
            print("✓ Model is already loaded in memory\n")
        elif model_status is False:
            print("⚠ Model not currently loaded\n")
        else:
            print("⚠ Cannot determine model status (Ollama version may not support status check)\n")

        # Preload if requested
        if args.preload:
            print("Preloading model...")
            load_time = summarizer.preload_model()
            print(f"✓ Model loaded in {load_time:.2f} seconds\n")

        # Get emails to summarize
        inboxes = email_parser.get_enabled_inboxes()
        if not inboxes:
            print("No enabled inboxes found")
            return 1

        # Summarize emails
        print(f"{'=' * 70}")
        print(f"Summarizing {args.limit} email(s)...")
        print(f"{'=' * 70}\n")

        count = 0
        for inbox in inboxes:
            for email_data in email_parser.parse_inbox(inbox, limit=args.limit):
                count += 1

                print(f"Email {count}:")
                print(f"  From: {email_data.from_addr}")
                print(f"  Subject: {email_data.subject}")
                print(f"  Message-ID: {email_data.message_id[:50]}...")

                # Summarize
                print(f"  Summarizing...", end='', flush=True)
                result = summarizer.summarize_email(email_data)
                print(f" Done in {result.duration_seconds:.2f}s")

                # Show summary
                print(f"\n  Summary:")
                print(f"  {'-' * 66}")
                for line in result.summary.split('\n'):
                    print(f"  {line}")
                print(f"  {'-' * 66}")

                if args.profile:
                    print(f"  Tokens: {result.total_tokens} (prompt: {result.prompt_tokens}, completion: {result.completion_tokens})")

                print()

                if count >= args.limit:
                    break

            if count >= args.limit:
                break

        # Show profiling summary
        if args.profile:
            print(f"\n{'=' * 70}")
            print("PROFILING SUMMARY")
            print(f"{'=' * 70}")

            prof = summarizer.get_profiling_summary()

            if prof['model_loads']['count'] > 0:
                print(f"\nModel Loading:")
                print(f"  Count: {prof['model_loads']['count']}")
                print(f"  Average time: {prof['model_loads']['avg_time']:.2f}s")

            print(f"\nSummarization:")
            print(f"  Emails processed: {prof['summaries']['count']}")
            print(f"  Total time: {prof['summaries']['total_time']:.2f}s")
            print(f"  Average time per email: {prof['summaries']['avg_time']:.2f}s")
            print(f"  Average tokens per email: {prof['summaries']['avg_tokens']:.0f}")

            if prof['summaries']['count'] > 0:
                emails_per_minute = 60 / prof['summaries']['avg_time']
                print(f"  Estimated throughput: {emails_per_minute:.1f} emails/minute")

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
