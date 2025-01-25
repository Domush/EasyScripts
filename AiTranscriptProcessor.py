# Standard library imports
from datetime import datetime
import json, re, os, sys
from typing import Dict, Any, Optional
import asyncio
import threading
import queue
from concurrent.futures import ThreadPoolExecutor

# Third-party imports
from openai import OpenAI
from prettyPrint import *
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ttkthemes import ThemedTk


# Custom stdout redirector for GUI logging
class GuiLogRedirector:
    def __init__(self, widget, level="info"):
        self.widget = widget
        self.level = level

    def write(self, message):
        if message.strip():  # Only process non-empty messages
            self.widget.log_message(message.strip(), self.level)

    def flush(self):
        pass


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
            eprint(f"Provider '{provider_name}' not found")
            return None

        self._set_client(provider["api_key"], provider["base_url"])
        self.provider = provider
        return provider

    def _set_client(self, api_key: str, base_url: str) -> None:
        if api_key and base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)

    # File processing and utility methods
    def _sanitize_filename(self, title: str) -> str:
        """Sanitize the title for use as a filename"""
        # Replace underscores with spaces, keep consistent spacing
        sanitized = re.sub(r"( *)_( *)", r"\1 \2", title)
        # Replace colons with hyphens
        sanitized = re.sub(r"( *)[:]( *)", r" - ", title)
        # matches anything NOT word chars, hyphen or space
        sanitized = re.sub(r"[^\w\- ]", "", title)
        return sanitized

    # AI interaction methods
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

Format the content section without mentioning markdown syntax directly.

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

It's vital that you begin each section with the above headings, followed by their respective content. This will help ensure the content is well-organized and easy to read.
Only use markdown formatting in the "Content:" section. Do not include markdown in the title or summary or on the section names themselves.

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

    # File and directory processing methods
    def process_file(self, input_file_path: str) -> Dict[str, str]:
        """Process a JSON file containing the transcript"""
        # Track processed files in a JSON file
        processed_files_path = ".processed_files.json"
        try:
            with open(processed_files_path, "r") as f:
                processed_files = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            processed_files = {}

        # Get just the filename without path
        input_filename = os.path.basename(input_file_path)
        iprint(f"Processing file: {input_filename}")

        # Check if file was previously processed by using just the filename
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

        # Update processed files tracking using just the filename as key
        if result:
            processed_files[input_filename] = {
                "output_path": result["filepath"],
                "processed_date": str(datetime.now()),
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


class TranscriptProcessorGUI(tk.Frame):
    """GUI interface for the transcript processor"""

    def __init__(self, master=None):
        # Basic initialization
        super().__init__(master)
        self.master = master
        self.current_path = os.getcwd()

        # Core components initialization
        self.processor = AiTranscriptProcessor()
        self.selected_paths = []
        self.is_directory = False
        self.selection_frame = None
        self.include_subdirs_var = tk.BooleanVar(value=False)

        # Processing thread components
        self.processing_queue = queue.Queue()
        self.processing_thread = None

        # Window setup and positioning
        self.master.minsize(800, 600)
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        window_width = max(768, min(screen_width - 100, 1200))
        window_height = max(600, screen_height // 2)
        self.master.geometry(f"{window_width}x{window_height}")

        # GUI initialization
        self.setup_gui()

        # Center window
        self.master.update_idletasks()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.master.geometry(f"+{x}+{y}")

        # Window close handler
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Output redirection setup
        self.setup_output_redirection()

    def setup_output_redirection(self):
        """Configure stdout/stderr redirection to GUI"""
        # Create redirectors
        self.stdout = GuiLogRedirector(self, "info")
        self.stderr = GuiLogRedirector(self, "error")

        # Redirect standard outputs
        sys.stdout = self.stdout
        sys.stderr = self.stderr

        # Override prettyPrint functions
        global iprint, wprint, eprint

        def iprint(message):
            self.log_message(str(message), "info")

        def wprint(message):
            self.log_message(str(message), "warning")

        def eprint(message):
            self.log_message(str(message), "error")

    # GUI setup and update methods
    def setup_gui(self):
        """Initialize all GUI components"""
        # Configure main window
        self.master.title("Transcript Processor")

        # Create main frame
        self.main_frame = ttk.Frame(self.master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Provider selection
        self.provider_frame = ttk.LabelFrame(
            self.main_frame, text="AI Provider", padding="5"
        )
        self.provider_frame.pack(fill=tk.X, pady=5)

        self.provider_var = tk.StringVar()
        self.provider_combo = ttk.Combobox(
            self.provider_frame,
            textvariable=self.provider_var,
            state="readonly",  # This makes it non-editable
        )
        self.provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Prevent text selection when changing values
        def on_select(event):
            self.provider_combo.selection_clear()

        self.provider_combo.bind("<<ComboboxSelected>>", on_select)

        self.set_default_btn = ttk.Button(
            self.provider_frame,
            text="Set as Default",
            command=self.set_default_provider,
        )
        self.set_default_btn.pack(side=tk.LEFT, padx=5)

        # Process buttons
        self.process_frame = ttk.Frame(self.main_frame)
        self.process_frame.pack(fill=tk.X, pady=5)

        self.process_file_btn = ttk.Button(
            self.process_frame,
            text="Select File(s)",
            command=self.select_files,
        )
        self.process_file_btn.pack(side=tk.LEFT, padx=5)

        self.process_dir_btn = ttk.Button(
            self.process_frame,
            text="Select Directory",
            command=self.select_directory,
        )
        self.process_dir_btn.pack(side=tk.LEFT, padx=5)

        # Progress indication
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = ttk.Label(self.main_frame, textvariable=self.progress_var)
        self.progress_label.pack(fill=tk.X, pady=5)

        self.progress_bar = ttk.Progressbar(self.main_frame, mode="indeterminate")
        self.progress_bar.pack(fill=tk.X, pady=5)

        # Status log
        self.log_frame = ttk.LabelFrame(self.main_frame, text="Status Log", padding="5")
        self.log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = tk.Text(self.log_frame, height=10, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Initialize provider list
        self.load_providers()

    def load_providers(self):
        try:
            with open(".api-keys.json", "r") as f:
                api_keys = json.load(f)
                self.providers = {
                    key: value
                    for key, value in api_keys["ai-providers"].items()
                    if key != "default"
                }
                # Create mapping of display names to provider keys
                self.provider_name_to_key = {
                    value["name"]: key for key, value in self.providers.items()
                }
                provider_names = list(self.provider_name_to_key.keys())
                default_provider = (
                    api_keys["ai-providers"].get("default", {}).get("name")
                )
                self.provider_combo["values"] = provider_names
                if default_provider:
                    self.provider_combo.set(default_provider)
                else:
                    self.provider_combo.set("")
        except Exception as e:
            self.log_message(f"Error loading providers: {e}", "error")

    def set_default_provider(self):
        selected_name = self.provider_var.get()
        if selected_name:
            try:
                # Find the provider key by matching the name
                selected_key = next(
                    (
                        key
                        for key, value in self.providers.items()
                        if value["name"] == selected_name
                    ),
                    None,
                )
                if not selected_key:
                    self.log_message(f"Provider {selected_name} not found", "error")
                    return

                with open(".api-keys.json", "r+") as f:
                    api_keys = json.load(f)
                    api_keys["ai-providers"]["default"] = api_keys["ai-providers"][
                        selected_key
                    ]
                    f.seek(0)
                    json.dump(api_keys, f, indent=4)
                    f.truncate()
                self.log_message(f"Set {selected_name} as default provider", "success")
            except Exception as e:
                self.log_message(f"Error setting default: {e}", "error")

    def select_files(self):
        """Handle file selection"""
        files = filedialog.askopenfilenames(
            initialdir=self.current_path,
            title="Select JSON file(s) to process",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if files:
            self.selected_paths = files
            self.is_directory = False
            self.update_selection_display()

    def select_directory(self):
        """Handle directory selection"""
        directory = filedialog.askdirectory(
            initialdir=self.current_path,
            title="Select Directory to Process",
        )
        if directory:
            self.selected_paths = [directory]
            self.is_directory = True
            self.update_selection_display()

    def update_selection_display(self):
        """Update the selection display area with current selection"""
        if self.selection_frame is not None:
            self.selection_frame.destroy()

        if not self.selected_paths:
            self.selection_frame = None
            return

        # Create new selection frame
        self.selection_frame = ttk.LabelFrame(
            self.main_frame, text="Selection", padding="5"
        )
        self.selection_frame.pack(fill=tk.X, pady=5, after=self.process_frame)

        # Calculate required height based on content
        if self.is_directory:
            num_lines = 1  # Directory path
        else:
            num_lines = len(self.selected_paths)  # One line per file

        # Set minimum height of 1 line and maximum of 10 lines
        display_height = min(max(1, num_lines), 10)

        # Create frame for selection text with scrollbar
        selection_text_frame = ttk.Frame(self.selection_frame)
        selection_text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Get current ttk style colors and font metrics
        style = ttk.Style()
        fg_color = style.lookup("TLabel", "foreground") or "black"
        bg_color = style.lookup("TFrame", "background") or "white"
        font = style.lookup("TLabel", "font")

        # Create temporary label to measure line height
        temp_label = ttk.Label(
            self.master, text="Ay"
        )  # Text with both ascenders and descenders
        line_height = temp_label.winfo_reqheight()
        temp_label.destroy()

        # Add selection text widget with scrollbar
        selection_text = tk.Text(
            selection_text_frame,
            height=display_height,  # Dynamic height
            wrap=tk.NONE,
            state="normal",
            font=font,
            foreground=fg_color,
            background=bg_color,
            relief="flat",
            borderwidth=0,
            takefocus=0,  # Prevent focus
            cursor="arrow",  # Use normal cursor instead of text cursor
        )
        selection_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Only show scrollbar if content exceeds display height
        selection_scrollbar = ttk.Scrollbar(
            selection_text_frame, orient=tk.VERTICAL, command=selection_text.yview
        )
        if num_lines > 10:  # Show scrollbar only if needed
            selection_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        selection_text.configure(yscrollcommand=selection_scrollbar.set)

        # Add begin button first (always show it)
        self.begin_btn = ttk.Button(
            self.selection_frame, text="Begin Processing", command=self.begin_processing
        )
        self.begin_btn.pack(side=tk.RIGHT, padx=5)

        # Add content
        if self.is_directory:
            directory = self.selected_paths[0]
            selection_text.insert(tk.END, f"Directory: {directory}")
            self.include_subdirs_cb = ttk.Checkbutton(
                self.selection_frame,
                text="Include Subdirectories",
                variable=self.include_subdirs_var,
            )
            self.include_subdirs_cb.pack(side=tk.LEFT, padx=5)
        else:
            for path in self.selected_paths:
                filename = os.path.basename(path)
                selection_text.insert(tk.END, f"• {filename}\n")

        # Make text widget read-only and disable interaction
        selection_text.configure(state="disabled")
        selection_text.bind("<Key>", lambda e: "break")  # Prevent all key input
        selection_text.bind("<Button-1>", lambda e: "break")  # Prevent clicks

    # File processing methods
    def begin_processing(self):
        """Initialize file processing in a separate thread"""
        if not self.selected_paths:
            return

        if not self.provider_var.get():
            self.log_message("Please select an AI provider first", "warning")
            return

        # Start processing in separate thread
        self.processing_thread = threading.Thread(target=self._process_files)
        self.processing_thread.daemon = True
        self.processing_thread.start()

        # Start progress updates
        self.start_processing()
        self.update_progress()

    def _process_files(self):
        """Background thread for file processing"""
        try:
            # Get provider key from selected name
            provider_name = self.provider_var.get()
            provider_key = self.provider_name_to_key.get(provider_name)
            if not provider_key:
                raise ValueError(f"Provider key not found for '{provider_name}'")

            self.processor.set_provider(provider_key)

            if self.is_directory:
                directory = self.selected_paths[0]
                file_count = 0

                def process_file(filepath):
                    result = self.processor.process_file(filepath)
                    if result:
                        self.processing_queue.put(
                            ("success", f"Processed: {result['filename']}")
                        )
                        return 1
                    return 0

                if self.include_subdirs_var.get():
                    # Process directory and subdirectories
                    for root, _, files in os.walk(directory):
                        for file in files:
                            if file.endswith(".json"):
                                file_count += process_file(os.path.join(root, file))
                else:
                    # Process only the selected directory
                    for filename in os.listdir(directory):
                        if filename.endswith(".json"):
                            file_count += process_file(
                                os.path.join(directory, filename)
                            )

                self.processing_queue.put(
                    ("info", f"Completed processing {file_count} files")
                )
            else:
                # Process selected files
                for file in self.selected_paths:
                    result = self.processor.process_file(file)
                    if result:
                        self.processing_queue.put(
                            ("success", f"Processed: {result['filename']}")
                        )

        except Exception as e:
            self.processing_queue.put(("error", f"Error during processing: {e}"))
        finally:
            self.processing_queue.put(("done", None))  # Signal processing is complete

    # Progress tracking methods
    def update_progress(self):
        """Update progress bar and process messages from queue"""
        try:
            while True:
                # Check for messages without blocking
                try:
                    level, message = self.processing_queue.get_nowait()
                    if level == "done":
                        self.stop_processing()
                        return
                    self.log_message(message, level)
                except queue.Empty:
                    break

            # Update progress bar animation
            self.progress_bar.step(5)

            # Schedule next update
            self.after(100, self.update_progress)

        except Exception as e:
            self.log_message(f"Error updating progress: {e}", "error")
            self.stop_processing()

    def start_processing(self):
        """Prepare UI for processing state"""
        self.progress_bar.start()
        self.process_file_btn["state"] = "disabled"
        self.process_dir_btn["state"] = "disabled"
        self.begin_btn["state"] = "disabled"
        if hasattr(self, "include_subdirs_cb"):
            self.include_subdirs_cb["state"] = "disabled"
        self.progress_var.set("Processing... Please wait")

    def stop_processing(self):
        """Reset UI after processing completes"""
        self.progress_bar.stop()
        self.process_file_btn["state"] = "normal"
        self.process_dir_btn["state"] = "normal"
        self.begin_btn["state"] = "normal"
        if hasattr(self, "include_subdirs_cb"):
            self.include_subdirs_cb["state"] = "normal"
        self.progress_var.set("Ready")

    # Utility methods
    def log_message(self, message: str, level: str = "info"):
        """Add a colored message to the log"""
        colors = {
            "info": "black",
            "warning": "orange",
            "error": "red",
            "success": "green",
        }
        self.log_text.insert(tk.END, f"{message}\n", level)
        self.log_text.tag_config(level, foreground=colors.get(level, "black"))
        self.log_text.see(tk.END)

    def on_closing(self):
        """Handle window closing event"""
        # Restore original stdout/stderr
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        self.master.quit()


# Application entry point
if __name__ == "__main__":
    root = ThemedTk(theme="arc")
    app = TranscriptProcessorGUI(master=root)
    app.mainloop()
