from datetime import datetime
import json
from pyexpat import model
import re
import os
from typing import Dict, Any
import asyncio
from openai import OpenAI
from prettyPrint import *


class AiTranscriptProcessor:
    def __init__(self, ai_provider="default"):
        self._provider = None
        self._client = None
        self._api_key_filename = ".api-keys.json"
        self.set_provider(ai_provider)
        # Minimum lengths for each section (anything shorter will be skipped)
        self.min_title_length = 20
        self.min_summary_length = 100
        self.min_content_length = 500

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
            eprint(f"Provider '{provider_name}' not found")

        self._set_client(provider["api_key"], provider["base_url"])
        self.provider = provider
        return provider

    def _set_client(self, api_key: str, base_url: str) -> None:
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def _sanitize_filename(self, title: str) -> str:
        """Sanitize the title for use as a filename"""
        # Replace underscores with spaces, keep consistent spacing
        sanitized = re.sub(r"( *)_( *)", r"\1 \2", title)
        # Replace colons with hyphens
        sanitized = re.sub(r"( *)[:]( *)", r" - ", title)
        # matches anything NOT word chars, hyphen or space
        sanitized = re.sub(r"[^\w\- ]", "", title)
        return sanitized

    def _create_system_prompt(self) -> str:
        return """
You are an expert technical trainer and have been tasked with improving upon poorly written training material.
You will be teaching students who know almost nothing about the topic, so you must hold their hand through every step.
Every single step should have code examples, detailed explanations, and highlight both how and why each step is done.

Create a extremely comprehensive instructional guide following these requirements:

Bullet point lists are not enough! EVERY SINGLE STEP must be HIGHLY DETAILED, as to avoid the student making a mistake or getting confused.

Do not assume the student knows anything about the topic. Provide detailed explanations for every step.

Format markdown to include:
- Bold text for important facts
- Italic text for technical terms/code
- Step-by-step instructions, assuming the reader knows nothing about any of the topics covered
- Tables where applicable

Focus on:
- Detailed explanations of each step
- Technical accuracy
- Exhaustive coverage of the original content, without skipping any topics or steps covered in the original material. The new material should be at least as detailed as the original.

Maintain these specifications:
- No Patreon references
- Clear, detailed code examples whenever coding or commandline executions must be performed. Including code comments explaining any lines of code which may bring up questions from the reader.
- If any section seems unclear, provide additional examples or explanation; more is better!
- Be sure to explain why each step is being take. Don't just list the steps, explain the reasoning behind each one.

Format the content without mentioning markdown syntax directly.

It's important to follow the above requirements to ensure the content is accurate and helpful to the intended audience. Users will get very upset if the content is not detailed enough or if it skips over important steps.
"""

    def _combine_transcript(self, transcript: list) -> str:
        """Combine transcript segments into a single text"""
        return " ".join(segment["text"] for segment in transcript)

    async def reformat_transcript(self, input_json: Dict[Any, Any]) -> Dict[str, str]:
        """Reformat the transcript using AI"""

        full_text = self._combine_transcript(input_json["transcript"])

        prompt = f"""Based on the included transcript, please provide:
A concise yet descriptive plain-text title (15 words max).
An accurate plain-text summary which covers every topic (50 words max).
Well-structured, extremely detailed markdown-formatted content with:
- Clear formatting and grammar
- Removal of filler phrases ('um', 'actually')
- Organized sections with appropriate headings
- TONS of examples and explanations, without skipping or glossing over any steps. Be specific, and explain everything!
- If the original content is part of a larger series (part 1, part 2, etc.), ensure the new content notes that fact, and ensure the part is noted at the beginning of the title (eg: "Part1: Adding data to you RAG AI").

Format the response with three distinct sections:
Title: [Title here]
Summary: [Summary here]
Content: [Content here]

Here is the original metadata and transcript for reference:

Original metadata:
{json.dumps(input_json['metadata'])}

Transcript:
{full_text}
"""

        try:
            model = self.provider.get("model") or "o1"
            print("Sending request to AI...")
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": self._create_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )

        except Exception as e:
            eprint(f"Request to AI failed: {e}")
            return None

        try:
            print("Response received from AI.")

            if not response:
                eprint(f"Error: Empty response from AI")
                return None

            if hasattr(response.choices, "model_extra") and getattr(
                response.choices.model_extra, "error", None
            ):
                eprint(f"Error: {response.choices.model_extra.error}")
                return None
            else:
                content = response.choices[0].message.content or None

                # Extract each section from the response with error checking
                try:
                    title_parts = re.split(
                        r"Title:", content, flags=re.IGNORECASE, maxsplit=1
                    )
                    if len(title_parts) < 2:
                        raise ValueError("Title section not found")

                    summary_parts = re.split(
                        r"Summary:", title_parts[1], flags=re.IGNORECASE, maxsplit=1
                    )
                    if len(summary_parts) < 2:
                        raise ValueError("Summary section not found")

                    content_parts = re.split(
                        r"Content:", summary_parts[1], flags=re.IGNORECASE, maxsplit=1
                    )
                    if len(content_parts) < 2:
                        raise ValueError("Content section not found")

                    title = summary_parts[0].strip("\n \t")
                    summary = content_parts[0].strip("\n \t")
                    content = content_parts[1].strip("\n \t")

                except ValueError as e:
                    eprint(f"Error parsing AI response: {e}")
                    eprint(f"File processing failed")
                    return None

                json_response = {"title": title, "summary": summary, "content": content}

            if (
                len(json_response["title"]) > self.min_title_length
                and len(json_response["summary"]) > self.min_summary_length
                and len(json_response["content"]) > self.min_content_length
            ):
                print("Response is valid! Saving to file...")
            else:
                wprint(f"Skipping file: Reformatted content is too short")
                return None

            # Create directory structure
            channel_name = self._sanitize_filename(
                input_json["metadata"]["channel_name"]
            )
            output_dir = os.path.join("processed", channel_name)
            os.makedirs(output_dir, exist_ok=True)

            # Save to file
            filename = f"{self._sanitize_filename(json_response['title'])}.json"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(json_response, f, ensure_ascii=False, indent=4)

            iprint(f"File processed successfully")
            return {
                "title": json_response["title"],
                "summary": json_response["summary"],
                "content": json_response["content"],
                "filename": filename,
                "filepath": filepath,
            }

        except Exception as e:
            eprint(f"Error processing file: {e}")
            return None

    def process_file(self, input_file_path: str) -> Dict[str, str]:
        """Process a JSON file containing the transcript"""
        # Track processed files in a JSON file
        processed_files_path = ".processed_files.json"
        try:
            with open(processed_files_path, "r") as f:
                processed_files = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            processed_files = {}

        input_filename = input_file_path.split(os.sep)[-1]
        iprint(f"Processing file: {input_filename}")

        # Check if file was previously processed
        if input_filename in processed_files:
            output_path = processed_files[input_filename]["output_path"]
            if os.path.exists(output_path):
                wprint(f"File already processed. Output at: {output_path}")
                return None
            else:
                wprint(f"Previous output missing. Reprocessing file.")

        # Process the file
        with open(input_file_path, "r", encoding="utf-8") as f:
            input_json = json.load(f)

        result = asyncio.run(self.reformat_transcript(input_json))

        # Update processed files tracking
        if result:
            processed_files[input_filename] = {
                "output_path": result["filepath"],
                "processed_date": str(datetime.datetime.now()),
            }
            with open(processed_files_path, "w") as f:
                json.dump(processed_files, f, indent=4)

        return result

    def process_directory(self, input_dir: str) -> None:
        """Process all JSON files in a directory"""
        wprint(f"\nProcessing directory: {input_dir.split(os.sep)[-1]}")
        for filename in os.listdir(input_dir):
            if filename.endswith(".json"):
                input_file_path = os.path.join(input_dir, filename)
                self.process_file(input_file_path)

    def select_ai_provider(self):
        """Display menu for AI provider selection and handle default settings"""
        while True:
            try:
                with open(self._api_key_filename, "r") as f:
                    api_keys = json.load(f)

                providers = [
                    key for key in api_keys["ai-providers"].keys() if key != "default"
                ]

                iprint("\nAvailable AI Providers:")
                for i, provider in enumerate(providers, 1):
                    print(f"{i}. {api_keys["ai-providers"][provider]["name"]}")
                wprint(f"{len(providers) + 1}. Go back")

                choice = input("\nSelect provider number: ")
                if not choice.isdigit():
                    wprint("Please enter a valid number")
                    continue

                choice = int(choice) - 1
                if choice == len(providers):
                    return

                if 0 <= choice < len(providers):
                    selected_provider = providers[choice]
                    set_default = input("\nSet as default? [Y/n]: ").lower()

                    if set_default in ["", "y", "yes"]:
                        api_keys["ai-providers"]["default"] = api_keys["ai-providers"][
                            selected_provider
                        ]
                        with open(self._api_key_filename, "w") as f:
                            json.dump(api_keys, f, indent=4)
                        iprint(f"{selected_provider} set as default provider")
                    return

                wprint("Invalid selection")
            except Exception as e:
                eprint(f"Error processing API keys: {e}")
                return

    def display_main_menu(self):
        """Display main menu and handle user selection"""
        while True:
            iprint("\nMain Menu")
            print(
                f"1. Select AI Provider {f"(Current: {self.provider["name"]})" if self.provider else ""}"
            )
            print("2. Reformat Transcripts")
            eprint("0. Exit")

            choice = int(input("\nEnter your choice: "))

            if choice == 1:
                self.select_ai_provider()
            elif choice == 2:
                if not self.provider:
                    wprint("Please select an AI provider first")
                    self.select_ai_provider()
                self.display_reformat_menu()
            elif choice == 0:
                exit()
            else:
                wprint("Invalid choice. Please try again.")

    def display_reformat_menu(self):
        """Display reformat menu and process user selection"""
        while True:
            iprint("\nYouTube Transcript Reformatter")
            wprint("1. Back")
            print("2. Process single JSON file")
            print("3. Process directory of JSON files")
            eprint("0. Exit")

            choice = int(input("\nEnter your choice: "))

            if choice == 1:
                break
            elif choice == 2:
                current_dir = os.getcwd()
                while True:
                    # List all files and directories in current path
                    items = [".."] + sorted([f for f in os.listdir(current_dir)])

                    # Filter for only JSON files and directories
                    filtered_items = ["Back"] + [
                        item
                        for item in items[1:]
                        if item.endswith(".json")
                        and not item.startswith(".")  # Ignore files starting with "."
                        and not item.startswith("config")  # Ignore config.json
                        or os.path.isdir(os.path.join(current_dir, item))
                        and not item.startswith(".")  # Ignore hidden directories
                        and not item.startswith("__")  # Ignore virtual environments
                    ]

                    if not filtered_items[1:]:  # If no items other than "Back"
                        eprint(
                            f"\nNo JSON files or directories found in '{current_dir.split(os.sep)[-1]}'"
                        )
                        if current_dir == os.getcwd():  # If in starting directory
                            break
                        current_dir = os.path.dirname(current_dir)  # Go up one level
                        continue

                    iprint(
                        f"\nCurrent directory: {current_dir.split(os.getcwd())[1].replace('\\','/') or '/'}"
                    )
                    print("\nAvailable items:")
                    for i, item in enumerate(filtered_items):
                        item_path = os.path.join(
                            current_dir, item if item != "Back" else ".."
                        )
                        if item == "Back":
                            wprint(f"{i+1}. {item}")
                        elif os.path.isdir(item_path):
                            print(f"{i+1}. 📁 {item}")
                        else:
                            print(f"{i+1}. 📄 {item}")

                    eprint("0. Exit")
                    try:
                        choice = int(input("\nSelect number: ")) - 1
                        if choice == -1:
                            exit()

                        if not (0 <= choice < len(filtered_items)):
                            eprint("Invalid selection")
                            continue

                        selected = filtered_items[choice]

                        if selected == "Back":
                            if current_dir == os.getcwd():  # If in starting directory
                                break
                            current_dir = os.path.dirname(current_dir)
                            continue

                        item_path = os.path.join(current_dir, selected)
                        if os.path.isdir(item_path):
                            current_dir = item_path
                        else:  # JSON file
                            self.process_file(item_path)

                    except ValueError:
                        wprint("Please enter a valid number")

            elif choice == 3:
                # List directories in current path if 'transcripts' doesn't exist
                search_path = "transcripts" if os.path.exists("transcripts") else "."

                dirs = [
                    d
                    for d in os.listdir(search_path)
                    if os.path.isdir(os.path.join(search_path, d))
                ]
                if not dirs:
                    eprint("No directories found")
                    continue

                iprint("\nAvailable directories:")
                for i, dir_name in enumerate(dirs, 1):
                    print(f"{i}. {dir_name}")

                try:
                    dir_index = int(input("\nSelect directory number: ")) - 1
                    if 0 <= dir_index < len(dirs):
                        selected_dir = os.path.join(search_path, dirs[dir_index])
                        search_subdirs = input(
                            "\nSearch subdirectories? [Y/n]: "
                        ).lower()
                        if search_subdirs in ["", "y", "yes"]:
                            for root, _, files in os.walk(selected_dir):
                                for file in files:
                                    if file.endswith(".json"):
                                        self.process_file(os.path.join(root, file))
                        else:
                            self.process_directory(selected_dir)
                    else:
                        eprint("Invalid selection")
                except ValueError:
                    wprint("Please enter a valid number")

            elif choice == 0:
                exit()
            else:
                wprint("Invalid choice. Please try again.")


# Main program (if run directly)
if __name__ == "__main__":
    reformatter = AiTranscriptProcessor()
    reformatter.display_main_menu()
