# YouTube AI Transcript Processor
# Utility to download, analyze and enhance YouTube video transcripts into easy to read markdown using AI
#
# Copyright (c) 2025 Phillip Webber
# All Rights Reserved
#
# Non-commercial Use Only
#
# This software may only be used for non-commercial purposes. Commercial use is prohibited
# without express written permission from the copyright holder.
#
# Redistribution and use in source and binary forms, with or without modification,
# for non-commercial purposes only are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Standard library imports
from datetime import datetime
import json, re, os
import asyncio
from typing import Dict, Any, Optional, Callable
from enum import Enum

# Third-party imports
from openai import OpenAI


class ProcessingStatus(str, Enum):
    """Status codes for processor operations"""

    # Error states
    ERROR_CONFIG = "error_config"
    ERROR_PROVIDER = "error_provider"
    ERROR_REQUEST = "error_request"
    ERROR_TIMEOUT = "error_timeout"

    # Progress states
    PROCESSING_START = "processing_start"
    PROCESSING_FILE = "processing_file"
    REQUEST_START = "request_start"
    REQUEST_RETRY = "request_retry"

    # Success states
    FILE_COMPLETE = "file_complete"
    FILE_SKIPPED = "file_skipped"


class TranscriptProcessorError(Exception):
    """Base exception class for transcript processor errors"""

    pass


class ConfigurationError(TranscriptProcessorError):
    """Configuration related errors"""

    pass


class ProviderError(TranscriptProcessorError):
    """AI provider related errors"""

    pass


class ProcessingError(TranscriptProcessorError):
    """Processing related errors"""

    pass


class AiTranscriptProcessor:
    """Main processor class for handling AI transcript reformatting"""

    def __init__(
        self,
        progress_callback: Optional[Callable[[str, ProcessingStatus, Optional[Dict]], None]] = None,
        ai_provider: str = "default",
    ):
        self._provider = None
        self._client = None
        self._api_key_filename = ".yttApiKeys.json"
        self._prompts_filename = ".yttConfig.json"
        self.progress_callback = progress_callback
        try:
            self.set_provider(ai_provider)
        except ProviderError:
            # Silently fail if default provider is not found
            pass
        # Minimum lengths for each section (anything shorter will be skipped)
        self.min_title_length = 20
        self.min_summary_length = 100
        self.min_content_length = 500
        self.system_prompt = ""
        self.user_prompt = ""
        self.load_prompts()

    def notify(self, status: ProcessingStatus, message: str, data: Optional[Dict] = None) -> None:
        """Send status update via callback if configured"""
        if self.progress_callback:
            self.progress_callback(message, status, data)

    def load_prompts(self):
        """Load prompt configuration from file"""
        try:
            with open(self._prompts_filename, "r") as f:
                config = json.load(f)
                self.system_prompt = config.get("system_prompt", "").strip()
                self.user_prompt = config.get("user_prompt", "").strip()
        except (FileNotFoundError, json.JSONDecodeError):
            self.notify(
                ProcessingStatus.ERROR_CONFIG,
                "AI Prompts not configured. You must add prompts prior to processing any transcripts",
            )
            self.system_prompt = ""
            self.user_prompt = ""

    def save_prompt_config(self):
        """Save prompt configuration to file"""
        config = {
            "system_prompt": self.system_prompt.strip(),
            "user_prompt": self.user_prompt.strip(),
        }
        try:
            with open(self._prompts_filename, "w") as f:
                json.dump(config, f, indent=4)
                return True
        except IOError as e:
            self.notify(ProcessingStatus.ERROR_CONFIG, f"Error saving prompt configuration: {e}")
            return False
        except Exception as e:
            self.notify(ProcessingStatus.ERROR_CONFIG, f"Unexpected error saving prompt configuration: {e}")
            return False

    # Provider management methods
    @property
    def provider(self):
        return self._provider

    @provider.setter
    def provider(self, value):
        self._provider = value
        if value:
            self._set_client(value["api_key"], value["base_url"])

    # Sets the provider based on provider name
    def set_provider(self, provider_name):
        """Sets the provider based on provider name"""
        try:
            with open(self._api_key_filename, "r") as f:
                api_keys = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ConfigurationError(f"Failed to load API keys: {e}")

        provider = api_keys["ai-providers"].get(provider_name)
        if not provider:
            error_msg = f"Provider '{provider_name}' not found"
            self.notify(ProcessingStatus.ERROR_PROVIDER, error_msg)
            raise ProviderError(error_msg)

        self._set_client(provider["api_key"], provider["base_url"])
        self.provider = provider
        return provider

    def _set_client(self, api_key: str, base_url: str) -> None:
        if api_key and base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)

    # File processing and utility methods
    def _sanitize_filename(self, title: str) -> str:
        """Sanitize a string for use as a filename."""
        if not isinstance(title, str):
            return str(title)

        sanitized = title
        replacements = [
            (r"[^\u0000-\u007F\u0080-\uFFFF]", ""),  # Remove non-UTF8 chars
            (r"( *)_( *)", r"\1 \2"),  # Replace underscore with space
            (r"( *)[:]( *)", " - "),  # Replace colon with hyphen
            (r" +", " "),  # Fix multiple spaces
            (r"[^\w\- ]", ""),  # Remove invalid chars
        ]

        for pattern, replacement in replacements:
            sanitized = re.sub(pattern, replacement, sanitized)

        return sanitized.strip()

    # AI interaction methods
    def _combine_transcript(self, transcript: list) -> str:
        """Combine transcript segments into a single text"""
        return " ".join(segment["text"] for segment in transcript)

    async def reformat_transcript(self, input_json: Dict[Any, Any]) -> Dict[str, str]:
        """Reformat the transcript using AI"""

        full_text = self._combine_transcript(input_json["transcript"])
        metadata = json.dumps(input_json["metadata"])

        # Use stored prompts
        prompt = (
            self.user_prompt
            + """
Use this JSON schema:
Return: {'title': str, 'summary': str, 'content': str}

Here is the original metadata and transcript for reference:
"""
            + f"\n\nOriginal metadata:\n{metadata}\n\nTranscript:\n{full_text}"
        )

        MAX_RETRIES = 2
        TIMEOUT = 45  # seconds

        response = None
        for attempt in range(MAX_RETRIES):
            try:
                model = self.provider.get("model") or "o1"
                self.notify(
                    ProcessingStatus.REQUEST_START,
                    f"Sending request to AI... {f'(attempt {attempt + 1}/{MAX_RETRIES})' if attempt > 0 else ''}",
                )

                response = self._client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    stream=False,
                    timeout=TIMEOUT,
                )

            except TimeoutError:
                if attempt == MAX_RETRIES - 1:
                    error_msg = "Request timed out after all retries"
                    self.notify(ProcessingStatus.ERROR_TIMEOUT, error_msg)
                    raise ProcessingError(error_msg)
                self.notify(ProcessingStatus.REQUEST_RETRY, "Request timed out, retrying...")
                await asyncio.sleep(1)
            except Exception as e:
                error_msg = f"Request to AI failed: {e}"
                self.notify(ProcessingStatus.ERROR_REQUEST, error_msg)
                raise ProcessingError(error_msg)

            if not response:
                self.notify(ProcessingStatus.ERROR_REQUEST, "Error: No response received from AI")
                continue

            try:
                result = self._process_ai_response(response, input_json)
                return result
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    error_msg = f"Error processing AI response after all retries: {e}"
                    self.notify(ProcessingStatus.ERROR_REQUEST, error_msg)
                    raise ProcessingError(error_msg)
                self.notify(ProcessingStatus.REQUEST_RETRY, "Error processing AI response, retrying...")
                await asyncio.sleep(1)

    def _process_ai_response(self, response, input_json):
        """Process the AI response and save results"""
        if hasattr(response.choices, "model_extra") and getattr(response.choices.model_extra, "error", None):
            raise ValueError(response.choices.model_extra.error)

        reply = response.choices[0].message.content
        if not reply:
            raise ValueError("Empty response content")

        # Clean and parse JSON response
        reply = re.sub(r"^[^{]*", "", reply)
        reply = re.sub(r"[^}]*$", "", reply)
        json_response = json.loads(reply)

        # Validate response fields
        if not all(key in json_response for key in ["title", "summary", "content"]):
            raise ValueError("Missing required fields in AI response")

        title = json_response["title"]
        summary = json_response["summary"]
        content = json_response["content"]

        # Validate content lengths
        if not (
            len(title) > self.min_title_length
            and len(summary) > self.min_summary_length
            and len(content) > self.min_content_length
        ):
            raise ValueError("Content too short")

        # Save result
        channel_name = self._sanitize_filename(input_json["metadata"]["channel_name"])
        output_dir = os.path.join("processed", channel_name)
        os.makedirs(output_dir, exist_ok=True)

        filename = f"{self._sanitize_filename(title)}.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(json_response, f, ensure_ascii=False, indent=4)

        self.notify(ProcessingStatus.FILE_COMPLETE, f"File processed. Saved as: {filename}")

        return {
            "title": title,
            "summary": summary,
            "content": content,
            "filename": filename,
            "filepath": filepath,
        }

    # File and directory processing methods
    def process_file(self, file: str) -> Dict[str, str]:
        """Process a JSON file containing the transcript"""
        # Track processed files in a JSON file
        processed_files_path = ".yttProcessedFiles.json"
        try:
            with open(processed_files_path, "r") as f:
                processed_files = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            processed_files = {}

        # Get just the filename without path
        filename = os.path.basename(file)
        self.notify(ProcessingStatus.PROCESSING_FILE, f"Processing file: {filename.split(os.sep)[-1]}")

        # Check if file was previously processed by using just the filename
        if filename in processed_files:
            output_path = processed_files[filename]["output_path"]
            if os.path.exists(output_path):
                self.notify(ProcessingStatus.FILE_SKIPPED, "File already processed. Skipping.", {"file_path": file})
                return None
            else:
                self.notify(
                    ProcessingStatus.PROCESSING_START,
                    "File has previously been processed, but the output file is missing. Reprocessing...",
                )

        # Process the file
        with open(file, "r", encoding="utf-8") as f:
            input_json = json.load(f)

        result = asyncio.run(self.reformat_transcript(input_json))

        # Update processed files tracking using just the filename as key
        if result:
            processed_files[filename] = {
                "output_path": result["filepath"],
                "processed_date": str(datetime.now()),
            }
            with open(processed_files_path, "w") as f:
                json.dump(processed_files, f, indent=4)

        return result
