# Standard library imports
import builtins
from datetime import datetime
import json, re, os, sys
from typing import Dict, Any, Optional
import asyncio
import threading
import queue
from concurrent.futures import ThreadPoolExecutor

# Third-party imports
from openai import OpenAI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ttkthemes import ThemedTk


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


class TranscriptProcessorGUI(tk.Frame):
    """GUI interface for the transcript processor"""

    def __init__(self, master=None):
        # Basic initialization
        super().__init__(master)
        self.master = master
        self.current_path = os.getcwd()

        # Save original print function
        self.original_print = builtins.print

        # Core components initialization
        self.processor = AiTranscriptProcessor()
        self.selected_paths = []
        self.is_directory = False
        self.selection_frame = None
        self.include_subdirs_var = tk.BooleanVar(value=False)

        # Processing thread components
        self.processing_queue = queue.Queue()
        self.processing_thread = None
        self.processing_cancelled = False

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

        # Setup output redirection
        self.setup_output_redirection()

        print("Transcript Processor ready", type="info")

    def setup_gui(self):
        """Initialize all GUI components"""
        # Configure main window
        self.master.title("Transcript Processor")

        # Configure button styles
        style = ttk.Style()
        style.configure("Begin.TButton", background="#e8ffe8")  # Pale green
        style.configure("Cancel.TButton", background="#ffe8e8")  # Pale red

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

        # Get current ttk style colors and font
        style = ttk.Style()
        fg_color = style.lookup("TLabel", "foreground") or "black"
        bg_color = style.lookup("TFrame", "background") or "white"
        font = style.lookup("TLabel", "font")

        # Create styled log text widget
        self.log_text = tk.Text(
            self.log_frame,
            height=10,
            wrap=tk.WORD,
            font=font,
            foreground=fg_color,
            background=bg_color,
            relief="flat",
            borderwidth=0,
            padx=5,
            pady=5,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure tags for different message types
        self.log_text.tag_configure("log", foreground=fg_color)
        self.log_text.tag_configure("info", foreground="#0066CC")  # Blue
        self.log_text.tag_configure("warning", foreground="#FF8800")  # Orange
        self.log_text.tag_configure("error", foreground="#FF4444")  # Red
        self.log_text.tag_configure("success", foreground="#44AA44")  # Green

        # Add scrollbar
        log_scrollbar = ttk.Scrollbar(
            self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        # Initialize provider list
        self.load_providers()

        # Add tooltip for process file button
        self._create_tooltip(
            self.process_file_btn, "Select one or more JSON files to process (Ctrl+O)"
        )

        # Add tooltip for process directory button
        self._create_tooltip(
            self.process_dir_btn,
            "Select a directory containing JSON files (Ctrl+D)\n\nIf 'Include Subdirectories' is checked, all subdirectories will be processed as well",
        )

        # Add keyboard shortcuts
        self.master.bind("<Control-o>", lambda e: self.select_files())
        self.master.bind("<Control-d>", lambda e: self.select_directory())

    def _create_tooltip(self, widget, text):
        """Create a tooltip for a given widget."""

        def enter(event):
            x, y, _, _ = widget.bbox("insert")
            x += widget.winfo_rootx() + 45
            y += widget.winfo_rooty() + 40

            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")

            label = ttk.Label(
                tip,
                text=text,
                justify=tk.LEFT,
                background="#ffffe0",
                relief=tk.SOLID,
                borderwidth=1,
                padding="5",
            )
            label.pack()
            widget.tooltip = tip

        def leave(event):
            if hasattr(widget, "tooltip"):
                widget.tooltip.destroy()
                del widget.tooltip

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

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
        begin_frame = tk.Frame(
            self.selection_frame, background="#e8ffe8"
        )  # Pale green background
        begin_frame.pack(side=tk.RIGHT, padx=5)

        self.begin_btn = ttk.Button(
            begin_frame,
            text="Begin Processing",
            command=self.begin_processing,
        )
        self.begin_btn.pack(
            expand=True, padx=1, pady=1
        )  # Small padding to show background color

        # Add tooltip for begin button
        self._create_tooltip(self.begin_btn, "Start processing selected files (Ctrl+B)")
        self.master.bind("<Control-b>", lambda e: self.begin_processing())

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

        # Reset cancellation flag
        self.processing_cancelled = False

        # Start processing in separate thread
        self.processing_thread = threading.Thread(target=self._process_files)
        self.processing_thread.daemon = True
        self.processing_thread.start()

        # Start progress updates
        self.start_processing()
        self.update_progress()

    def cancel_processing(self):
        """Cancel ongoing processing"""
        self.processing_cancelled = True
        self.log_message(
            "Cancelling... Please wait for current operation to complete.", "warning"
        )
        self.begin_btn["state"] = "disabled"  # Prevent multiple cancel clicks

    def _process_files(self):
        """Background thread for file processing"""
        try:
            # Get provider key from selected name
            provider_name = self.provider_var.get()
            provider_key = self.provider_name_to_key.get(provider_name)
            if not provider_key:
                raise ValueError(f"Provider key not found for '{provider_name}'")

            self.processor.set_provider(provider_key)

            file_count = 0
            file_success_count = 0

            if self.is_directory:
                directory = self.selected_paths[0]

                if self.include_subdirs_var.get():
                    # Process directory and subdirectories
                    print(
                        f"\nProcessing directory: {directory.split(os.sep)[-1]} and all subdirectories",
                        type="info",
                    )
                    for root, _, files in os.walk(directory):
                        for file in files:
                            if self.processing_cancelled:
                                raise InterruptedError("Processing cancelled by user")
                            if file.endswith(".json"):
                                file_count += 1
                                file_success_count += (
                                    1
                                    if self.processor.process_file(
                                        os.path.join(root, file)
                                    )
                                    else 0
                                )
                else:
                    # Process only the selected directory
                    print(
                        f"\nProcessing directory: {directory.split(os.sep)[-1]}",
                        type="info",
                    )
                    for filename in os.listdir(directory):
                        if self.processing_cancelled:
                            raise InterruptedError("Processing cancelled by user")
                        if filename.endswith(".json"):
                            file_count += 1
                            file_success_count += (
                                1
                                if self.processor.process_file(
                                    os.path.join(directory, filename)
                                )
                                else 0
                            )
            else:
                # Process selected files
                for file in self.selected_paths:
                    if self.processing_cancelled:
                        raise InterruptedError("Processing cancelled by user")
                    file_count += 1
                    file_success_count += 1 if self.processor.process_file(file) else 0
            self.processing_queue.put(
                (
                    "success" if file_success_count > 0 else "info",
                    f"\nProcessing complete. {file_success_count} of {file_count} files processed",
                )
            )

        except InterruptedError as e:
            self.processing_queue.put(("warning", f"\n{str(e)}"))
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
        self.begin_btn["text"] = "Cancel Processing"
        self.begin_btn["command"] = self.cancel_processing

        # Chance tooltip to cancel
        self._create_tooltip(self.begin_btn, "Cancel processing (Escape)")
        self.master.unbind("<Control-b>", lambda e: self.begin_processing())
        self.master.bind("<Escape>", lambda e: self.cancel_processing())

        self.begin_btn.master.configure(
            background="#ffe8e8"
        )  # Change frame to pale red
        if hasattr(self, "include_subdirs_cb"):
            self.include_subdirs_cb["state"] = "disabled"
        self.progress_var.set("Processing... Please wait")

    def stop_processing(self):
        """Reset UI after processing completes"""
        self.progress_bar.stop()
        self.process_file_btn["state"] = "normal"
        self.process_dir_btn["state"] = "normal"
        self.begin_btn["text"] = "Begin Processing"
        self.begin_btn["command"] = self.begin_processing

        # Re-Add tooltip for begin button
        self._create_tooltip(self.begin_btn, "Start processing selected files (Ctrl+B)")
        self.master.unbind("<Escape>", lambda e: self.cancel_processing())
        self.master.bind("<Control-b>", lambda e: self.begin_processing())

        self.begin_btn["state"] = "normal"
        self.begin_btn.master.configure(
            background="#e8ffe8"
        )  # Change frame back to pale green
        if hasattr(self, "include_subdirs_cb"):
            self.include_subdirs_cb["state"] = "normal"
        self.progress_var.set("Ready")

    # Utility methods
    def log_message(self, message: str, level: str = "log"):
        """Add a colored message to the log"""
        # Ensure text widget is editable
        self.log_text.configure(state="normal")

        # If message begins with a \n insert a newline first
        if message.startswith("\n"):
            self.log_text.insert(tk.END, "\n", "log")

        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] ", "log")
        self.log_text.insert(tk.END, f"{message.strip("\n ")}\n", level)

        # Make text widget read-only again
        self.log_text.configure(state="disabled")

        # Auto-scroll to the end
        self.log_text.see(tk.END)

        # Force GUI update
        self.update_idletasks()

    def setup_output_redirection(self):
        """Configure output redirection to GUI logging"""

        COLORS = {
            "info": "\033[94m",  # Light blue
            "warning": "\033[93m",  # Yellow
            "error": "\033[91m",  # Light red
            "success": "\033[92m",  # Green
        }
        END_COLOR = "\033[0m"

        def gui_print(*args, **kwargs):
            msg_type = kwargs.pop("type", None)
            text = " ".join(str(arg) for arg in args)

            # Print to terminal with color
            if msg_type in COLORS:
                colored_text = f"{COLORS[msg_type]}{text}{END_COLOR}"
                self.original_print(colored_text, **kwargs)
            else:
                self.original_print(text, **kwargs)

            # Log to GUI
            self.log_message(text, msg_type)

        builtins.print = gui_print

    def on_closing(self):
        """Handle window closing event"""
        try:
            # Restore original print function
            builtins.print = self.original_print
        except:
            pass
        self.master.destroy()


# Application entry point
if __name__ == "__main__":
    root = ThemedTk(theme="arc")
    app = TranscriptProcessorGUI(master=root)
    app.mainloop()
