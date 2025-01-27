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
from typing import Dict, Any

# Third-party imports
from openai import OpenAI


class AiTranscriptProcessor:
    """Main processor class for handling AI transcript reformatting"""

    def __init__(self, ai_provider="default"):
        self._provider = None
        self._client = None
        self._api_key_filename = ".yttApiKeys.json"
        self._prompts_filename = ".yttConfig.json"
        try:
            self.set_provider(ai_provider)
        except:
            # Silently fail if default provider is not found
            pass
        # Minimum lengths for each section (anything shorter will be skipped)
        self.min_title_length = 20
        self.min_summary_length = 100
        self.min_content_length = 500
        self.system_prompt = ""
        self.user_prompt = ""
        self.load_prompts()

    def load_prompts(self):
        """Load prompt configuration from file"""
        try:
            with open(self._prompts_filename, "r") as f:
                config = json.load(f)
                self.system_prompt = config.get("system_prompt", "").strip()
                self.user_prompt = config.get("user_prompt", "").strip()
        except (FileNotFoundError, json.JSONDecodeError):
            print(
                "AI Prompts not configured. You must add prompts prior to processing any transcripts",
                type="error",
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
            print(f"Error saving prompt configuration: {e}", type="error")
        except Exception as e:
            print(f"Unexpected error saving prompt configuration: {e}", type="error")
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
        with open(self._api_key_filename, "r") as f:
            api_keys = json.load(f)

        provider = api_keys["ai-providers"].get(provider_name)
        if not provider:
            print(f"Provider '{provider_name}' not found", type="error")
            return None

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
                print(f"Sending request to AI... {f"(attempt {attempt + 1}/{MAX_RETRIES})" if attempt > 0 else ""}")

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
                    print("Request timed out after all retries", type="error")
                    return None
                print("Request timed out, retrying...", type="warning")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Request to AI failed: {e}", type="error")
                return None

            if not response:
                print("Error: No response received from AI", type="error")
                continue

            try:
                result = self._process_ai_response(response, input_json)
                return result
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    print(
                        f"Error processing AI response after all retries: {e}",
                        type="error",
                    )
                    return None
                print(
                    f"Error processing AI response, retrying...",
                    type="warning",
                )
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

        print(f"File processed. Saved as: {filename}", type="success")

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
        print(f"\nProcessing file: {filename.split(os.sep)[-1]}", type="info")

        # Check if file was previously processed by using just the filename
        if filename in processed_files:
            output_path = processed_files[filename]["output_path"]
            if os.path.exists(output_path):
                print(f"File already processed. Skipping.", type="warning")
                return None
            else:
                print(
                    f"File has previously been processed, but the output file is missing. Reprocessing...",
                    type="warning",
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
