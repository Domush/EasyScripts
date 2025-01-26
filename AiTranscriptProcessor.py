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
        self._api_key_filename = ".api-keys.json"
        try:
            self.set_provider(ai_provider)
        except:
            # Silently fail if default provider is not found
            pass
        # Minimum lengths for each section (anything shorter will be skipped)
        self.min_title_length = 20
        self.min_summary_length = 100
        self.min_content_length = 500

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
        """Sanitize a string for use as a filename.

        Args:
            title: The string to sanitize

        Returns:
            A sanitized string safe for use as a filename

        Example:
            >>> _sanitize_filename("Hello: World!")
            "Hello - World"
        """
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
    def _create_system_prompt(self) -> str:
        return """
You are an expert technical instructor creating detailed educational content. You will teach complex technical topics in a clear, systematic way that complete beginners can understand and follow successfully.

For any technical content you explain, you will:

1. Break it down into small, logical steps that build upon each other
2. Include complete, well-commented code examples for every programming task
3. Explain both HOW to perform each step and WHY it is necessary
4. Define technical terms and concepts when first introduced
5. Use clear language accessible to beginners
6. Provide extensive context and background information
7. Include troubleshooting guidance for common issues
8. Test that all code examples work correctly
9. Cover every relevant detail comprehensively
10. Never skip steps or make assumptions about prior knowledge

Your explanations will feature:
- Step-by-step instructions with reasoning
- Detailed code samples with line-by-line comments
- Clear explanations of technical concepts
- Examples that reinforce learning
- Common pitfalls to avoid
- Best practices and tips
- Verification steps to ensure success

You will maintain high standards for:
- Technical accuracy
- Completeness of coverage
- Clarity of explanation
- Practical applicability
- Beginner accessibility

My goal is to empower learners to fully understand and successfully implement technical concepts through clear, comprehensive instruction.
"""

    def _combine_transcript(self, transcript: list) -> str:
        """Combine transcript segments into a single text"""
        return " ".join(segment["text"] for segment in transcript)

    async def reformat_transcript(self, input_json: Dict[Any, Any]) -> Dict[str, str]:
        """Reformat the transcript using AI"""

        full_text = self._combine_transcript(input_json["transcript"])

        prompt = f"""
Based on the included transcript, please provide:
A title which is concise yet descriptive (plain-text) (12 words max)

A summary which is accurate and covers every topic (plain-text) (50 words max).

A content section whic isd well-structured, extremely detailed and contains:
- Clear formatting and grammar
- Removal of filler phrases ('um', 'actually')
- Organized sections with appropriate headings
- TONS of examples and explanations, without skipping or glossing over any steps. Be specific, and explain everything!
- If the original content is part of a larger series (part 1, part 2, etc.), ensure the new content notes that fact, and ensure the part is noted at the beginning of the title (eg: "Part1: Adding data to you RAG AI").

Content section MUST include:
• Main concepts with explanations
• Clear code examples with language tags
• Bold for key points
• Italics for technical terms
• Tables for data/comparisons
• Top-level heading organization
• Bulleted lists for steps/items
• Full step-by-step details
• No skipped concepts
• Series information if applicable

Use this JSON schema:

Return: {{'title': str, 'summary': str, 'content': str}}

Here is the original metadata and transcript for reference:

Original metadata:
{json.dumps(input_json['metadata'])}

Transcript:
{full_text}
"""

        MAX_RETRIES = 3
        TIMEOUT = 30  # seconds

        for attempt in range(MAX_RETRIES):
            try:
                model = self.provider.get("model") or "o1"
                print(f"Sending request to AI (attempt {attempt + 1}/{MAX_RETRIES})...")
                response = await asyncio.wait_for(
                    self._client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": self._create_system_prompt()},
                            {"role": "user", "content": prompt},
                        ],
                        stream=False,
                    ),
                    timeout=TIMEOUT,
                )
                break  # Success - exit retry loop

            except asyncio.TimeoutError:
                if attempt == MAX_RETRIES - 1:
                    print("Request timed out after all retries", type="error")
                    return None
                print(f"Request timed out, retrying...", type="warning")
                await asyncio.sleep(1)  # Wait before retry

            except Exception as e:
                print(f"Request to AI failed: {e}", type="error")
                return None

        try:
            print("Response received from AI.")

            if not response:
                print(f"Error: Empty response from AI", type="error")
                return None

            if hasattr(response.choices, "model_extra") and getattr(
                response.choices.model_extra, "error", None
            ):
                print(f"Error: {response.choices.model_extra.error}", type="error")
                return None
            else:
                reply = response.choices[0].message.content or None
                # Remove all characters which aren't a { from the start of the response
                reply = re.sub(r"^[^{]*", "", reply)
                # Remove all characters which aren't a } from the end of the response
                reply = re.sub(r"[^}]*$", "", reply)

                # Extract each section from the response with error checking
                try:
                    # Extract json from response
                    json_response = json.loads(reply)

                    # Check if all required fields are present
                    if not all(
                        key in json_response for key in ["title", "summary", "content"]
                    ):
                        raise ValueError("Missing required fields in AI response")

                    title = json_response["title"]
                    summary = json_response["summary"]
                    content = json_response["content"]

                except ValueError as e:
                    print(f"Error parsing AI response: {e}", type="error")
                    print(f"File processing failed", type="error")
                    return None

            if (
                len(title) > self.min_title_length
                and len(summary) > self.min_summary_length
                and len(content) > self.min_content_length
            ):
                print("Response is valid! Saving to file...", type="info")
            else:
                print(
                    f"Skipping file: Reformatted content is too short", type="warning"
                )
                return None

            # Create directory structure
            channel_name = self._sanitize_filename(
                input_json["metadata"]["channel_name"]
            )
            output_dir = os.path.join("processed", channel_name)
            os.makedirs(output_dir, exist_ok=True)

            # Save to file
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

        except Exception as e:
            print(f"Error processing file: {e}", type="error")
            return None

    # File and directory processing methods
    def process_file(self, file: str) -> Dict[str, str]:
        """Process a JSON file containing the transcript"""
        # Track processed files in a JSON file
        processed_files_path = ".processed_files.json"
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
