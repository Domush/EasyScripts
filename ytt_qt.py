from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QFileDialog,
    QCheckBox,
    QTextEdit,
    QProgressBar,
    QFrame,
    QScrollArea,
    QGroupBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QShortcut, QKeySequence, QIcon
import sys
import os
import json
import threading
import queue
from datetime import datetime

from AiTranscriptProcessor import (
    AiTranscriptProcessor,
    ProcessingStatus,
    ConfigurationError,
    ProviderError,
    ProcessingError,
)


class TranscriptProcessingThread(QThread):
    progress_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal()

    def __init__(self, processor, provider_key, selected_paths, is_directory, include_subdirs):
        super().__init__()
        self.processor = processor
        # Set up progress callback
        self.processor.progress_callback = self.handle_progress
        self.provider_key = provider_key
        self.selected_paths = selected_paths
        self.is_directory = is_directory
        self.include_subdirs = include_subdirs
        self.cancelled = False

    def handle_progress(self, message: str, status: ProcessingStatus, data: dict = None):
        """Handle progress updates from the processor"""
        # Map processor status to GUI levels
        gui_level = {
            ProcessingStatus.ERROR_CONFIG: "error",
            ProcessingStatus.ERROR_PROVIDER: "error",
            ProcessingStatus.ERROR_REQUEST: "error",
            ProcessingStatus.ERROR_TIMEOUT: "error",
            ProcessingStatus.PROCESSING_START: "info",
            ProcessingStatus.PROCESSING_FILE: "info",
            ProcessingStatus.REQUEST_START: "info",
            ProcessingStatus.REQUEST_RETRY: "warning",
            ProcessingStatus.FILE_COMPLETE: "success",
            ProcessingStatus.FILE_SKIPPED: "warning",
        }.get(status, "info")

        self.progress_signal.emit(message, gui_level)

    def run(self):
        try:
            self.processor.set_provider(self.provider_key)
            file_count = 0
            file_success_count = 0

            if self.is_directory:
                directory = self.selected_paths[0]

                if self.include_subdirs:
                    self.progress_signal.emit(
                        f"\nProcessing directory: {directory.split(os.sep)[-1]} and all subdirectories",
                        "info",
                    )
                    for root, _, files in os.walk(directory):
                        for file in files:
                            if self.cancelled:
                                raise InterruptedError("Processing cancelled by user")
                            if file.endswith(".json") and not file.startswith("."):
                                file_count += 1
                                try:
                                    result = self.processor.process_file(os.path.join(root, file))
                                    if result:
                                        file_success_count += 1
                                except ProcessingError as e:
                                    self.progress_signal.emit(str(e), "error")
                else:
                    self.progress_signal.emit(f"\nProcessing directory: {directory.split(os.sep)[-1]}", "info")
                    for filename in os.listdir(directory):
                        if self.cancelled:
                            raise InterruptedError("Processing cancelled by user")
                        if filename.endswith(".json") and not filename.startswith("."):
                            file_count += 1
                            try:
                                result = self.processor.process_file(os.path.join(directory, filename))
                                if result:
                                    file_success_count += 1
                            except ProcessingError as e:
                                self.progress_signal.emit(str(e), "error")
            else:
                for file in self.selected_paths:
                    if self.cancelled:
                        raise InterruptedError("Processing cancelled by user")
                    file_count += 1
                    try:
                        result = self.processor.process_file(file)
                        if result:
                            file_success_count += 1
                    except ProcessingError as e:
                        self.progress_signal.emit(str(e), "error")

            level = "success" if file_success_count > 0 else "info"
            self.progress_signal.emit(
                f"\nProcessing complete. {file_success_count} of {file_count} files processed",
                level,
            )

        except InterruptedError as e:
            self.progress_signal.emit(f"Interrupted error: \n{str(e)}", "error")
        except ProviderError as e:
            self.progress_signal.emit(f"Provider error: {str(e)}", "error")
        except ConfigurationError as e:
            self.progress_signal.emit(f"Configuration error: {str(e)}", "error")
        except Exception as e:
            self.progress_signal.emit(f"Error during processing: {e}", "error")
        finally:
            self.finished_signal.emit()


class PromptEditorDialog(QWidget):
    def __init__(self, parent, prompt_type, current_prompt, save_callback):
        super().__init__(parent, Qt.WindowType.Dialog)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.prompt_type = prompt_type
        self.save_callback = save_callback

        self.setWindowTitle(f"Edit {prompt_type.title()} Prompt")
        self.setup_ui(current_prompt)

        # Set size and position
        self.resize(800, 600)
        parent_center = parent.geometry().center()
        self.move(parent_center.x() - 400, parent_center.y() - 300)

    def setup_ui(self, current_prompt):
        layout = QVBoxLayout(self)

        # Text editor
        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        if current_prompt:
            self.editor.setText(current_prompt)
        layout.addWidget(self.editor)

        # Add hotkeys
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(self.save)
        cancel_shortcut = QShortcut(QKeySequence("Escape"), self)
        cancel_shortcut.activated.connect(self.close)

        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save Changes (Ctrl+S)")
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton("Cancel (Esc)")
        cancel_btn.clicked.connect(self.close)

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        layout.addLayout(button_layout)

    def save(self):
        new_prompt = self.editor.toPlainText().strip()
        self.save_callback(self.prompt_type, new_prompt)
        self.close()


class TranscriptProcessorGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        # Initialize variables
        self.selected_paths = []
        self.is_directory = False
        self.include_subdirs_state = False  # Store checkbox state
        self.processing_thread = None
        self.providers = {}
        self.provider_name_to_key = {}
        self.current_path = os.getcwd()
        self.processing_queue = queue.Queue()  # Initialize processing queue

        # Style configuration
        self.configure_styles()

        # Setup UI
        self.padding_style = "font-size: 14px; padding: 10px 20px;"
        self.setup_ui()

        # Initialize processor
        self.processor = AiTranscriptProcessor(progress_callback=self.log_message)

        self.load_providers()

        # Window settings
        self.setWindowTitle("YouTube Transcript Processor")
        screen_height = QApplication.primaryScreen().size().height()
        self.resize(1024, int(screen_height * 2 / 3))
        self.setMinimumSize(800, 600)

        # Progress timer
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.setInterval(100)

    def configure_styles(self):
        self.log_colors = {
            "default": "#505050",
            "info": "#2E86C1",
            "warning": "#E67E22",
            "error": "#E74C3C",
            "success": "#27AE60",
        }

    def log_message(self, message, level="default", data=None):
        color = self.log_colors.get(level, self.log_colors["default"])
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message.strip()}\n"

        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

        char_format = QTextCharFormat()
        char_format.setForeground(QColor(color))
        cursor.insertText(formatted_message, char_format)

        self.log_text.ensureCursorVisible()

    def setup_ui(self):
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Set window icon
        self.setWindowIcon(QIcon("icon.jpg"))

        # Title
        title_label = QLabel("YouTube Transcript Processor")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333; margin-bottom: 20px;")
        main_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # AI Provider section
        provider_group = QGroupBox("AI Provider")
        provider_layout = QHBoxLayout()

        self.provider_combo = QComboBox()
        self.provider_combo.setStyleSheet(self.padding_style)
        self.set_default_btn = QPushButton("Set as Default")
        self.set_default_btn.clicked.connect(self.set_default_provider)

        provider_layout.addWidget(self.provider_combo)
        provider_layout.addWidget(self.set_default_btn)
        provider_group.setLayout(provider_layout)
        main_layout.addWidget(provider_group)

        # Process buttons
        process_layout = QHBoxLayout()
        self.process_file_btn = QPushButton("Select File(s)")
        self.process_file_btn.clicked.connect(self.select_files)
        self.process_dir_btn = QPushButton("Select Directory")
        self.process_dir_btn.clicked.connect(self.select_directory)

        process_layout.addWidget(self.process_file_btn)
        process_layout.addWidget(self.process_dir_btn)

        # Edit prompt buttons
        edit_layout = QHBoxLayout()
        self.edit_system_btn = QPushButton("Edit System Prompt")
        self.edit_system_btn.clicked.connect(lambda: self.edit_prompt("system"))
        self.edit_user_btn = QPushButton("Edit User Prompt")
        self.edit_user_btn.clicked.connect(lambda: self.edit_prompt("user"))

        edit_layout.addStretch()
        edit_layout.addWidget(self.edit_system_btn)
        edit_layout.addWidget(self.edit_user_btn)

        process_layout.addLayout(edit_layout)
        main_layout.addLayout(process_layout)

        # Update button styles
        self.process_file_btn.setStyleSheet(self.padding_style)
        self.process_dir_btn.setStyleSheet(self.padding_style)
        self.set_default_btn.setStyleSheet(self.padding_style)
        self.edit_system_btn.setStyleSheet(self.padding_style)
        self.edit_user_btn.setStyleSheet(self.padding_style)

        # Selection display
        self.selection_group = None

        # Progress section
        progress_label = QLabel("Progress")
        progress_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        main_layout.addWidget(progress_label)

        self.progress_status = QLabel("Ready")
        main_layout.addWidget(self.progress_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Log section
        log_label = QLabel("Status Log")
        log_label.setFont(QFont("Segue UI", 10, QFont.Weight.Bold))
        main_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        main_layout.addWidget(self.log_text)

    def load_providers(self):
        try:
            with open(".yttApiKeys.json", "r") as f:
                api_keys = json.load(f)
                self.providers = {key: value for key, value in api_keys["ai-providers"].items() if key != "default"}
                self.provider_name_to_key = {value["name"]: key for key, value in self.providers.items()}
                provider_names = list(self.provider_name_to_key.keys())
                default_provider = api_keys["ai-providers"].get("default", {}).get("name")

                self.provider_combo.addItems(provider_names)
                if default_provider:
                    self.provider_combo.setCurrentText(default_provider)

        except Exception as e:
            self.log_message(f"Error loading providers: {e}", "error")

    def set_default_provider(self):
        selected_name = self.provider_combo.currentText()
        if selected_name:
            try:
                selected_key = self.provider_name_to_key.get(selected_name)
                if not selected_key:
                    self.log_message(f"Provider {selected_name} not found", "error")
                    return

                with open(".yttApiKeys.json", "r+") as f:
                    api_keys = json.load(f)
                    api_keys["ai-providers"]["default"] = api_keys["ai-providers"][selected_key]
                    f.seek(0)
                    json.dump(api_keys, f, indent=4)
                    f.truncate()
                self.log_message(f"Set {selected_name} as default provider", "success")
            except Exception as e:
                self.log_message(f"Error setting default: {e}", "error")

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select JSON file(s) to process",
            self.current_path,
            "JSON files (*.json);;All files (*.*)",
        )
        if files:
            self.selected_paths = files
            self.is_directory = False
            self.update_selection_display()

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory to Process", self.current_path)
        if directory:
            self.selected_paths = [directory]
            self.is_directory = True
            self.update_selection_display()

    def update_selection_display(self):
        if self.selection_group is not None:
            if hasattr(self, "include_subdirs"):
                self.include_subdirs_state = self.include_subdirs.isChecked()
            self.selection_group.deleteLater()
            self.selection_group = None

        if not self.selected_paths:
            return

        self.selection_group = QGroupBox("Selection")
        layout = QVBoxLayout()

        # Selection text display
        selection_text = QTextEdit()
        selection_text.setReadOnly(True)

        if self.is_directory:
            directory = self.selected_paths[0]
            selection_text.setText(f"Directory: {directory}")

            self.include_subdirs = QCheckBox("Include Subdirectories")
            self.include_subdirs.setChecked(self.include_subdirs_state)
            layout.addWidget(selection_text)
            layout.addWidget(self.include_subdirs)
        else:
            text = "\n".join(f"• {os.path.basename(path)}" for path in self.selected_paths)
            selection_text.setText(text)
            layout.addWidget(selection_text)

        # Begin button
        begin_layout = QHBoxLayout()
        self.begin_btn = QPushButton("Begin Processing")
        self.begin_btn.setStyleSheet(self.padding_style)
        self.begin_btn.clicked.connect(self.begin_processing)
        self.update_begin_button_state()

        begin_layout.addStretch()
        begin_layout.addWidget(self.begin_btn)
        layout.addLayout(begin_layout)

        self.selection_group.setLayout(layout)

        # Add to main layout after process buttons
        self.centralWidget().layout().insertWidget(3, self.selection_group)

    def begin_processing(self):
        if hasattr(self, "processing_thread") and self.processing_thread is not None:
            # Cancel mode
            self.processing_thread.cancelled = True
            self.log_message(
                "Cancelling... Please wait for current operation to complete.",
                "warning",
            )
            self.begin_btn.setEnabled(False)
            return

        if not self.selected_paths:
            return

        if not self.provider_combo.currentText():
            self.log_message("Please select an AI provider first", "warning")
            return

        provider_name = self.provider_combo.currentText()
        provider_key = self.provider_name_to_key.get(provider_name)

        include_subdirs = self.include_subdirs.isChecked() if hasattr(self, "include_subdirs") else False

        # Start processing thread
        self.processing_thread = TranscriptProcessingThread(
            self.processor,
            provider_key,
            self.selected_paths,
            self.is_directory,
            include_subdirs,
        )
        self.processing_thread.progress_signal.connect(self.log_message)
        self.processing_thread.finished_signal.connect(self.stop_processing)
        self.processing_thread.start()

        # Start progress updates
        self.start_processing()
        self.progress_timer.start()

    def start_processing(self):
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.process_file_btn.setEnabled(False)
        self.process_dir_btn.setEnabled(False)
        self.begin_btn.setText("Cancel Processing")
        self.begin_btn.clicked.disconnect()
        self.begin_btn.clicked.connect(self.begin_processing)

        if hasattr(self, "include_subdirs"):
            self.include_subdirs.setEnabled(False)
        self.progress_status.setText("Processing... Please wait")

    def stop_processing(self):
        self.progress_bar.setRange(0, 100)  # Reset to determinate mode
        self.progress_bar.setValue(0)
        self.process_file_btn.setEnabled(True)
        self.process_dir_btn.setEnabled(True)
        self.begin_btn.setText("Begin Processing")
        self.begin_btn.clicked.disconnect()
        self.begin_btn.clicked.connect(self.begin_processing)

        if hasattr(self, "include_subdirs"):
            self.include_subdirs.setEnabled(True)
        self.progress_status.setText("Ready")
        self.processing_thread = None
        self.progress_timer.stop()

    def update_begin_button_state(self):
        prompts_valid = self.processor.system_prompt and self.processor.user_prompt
        if hasattr(self, "begin_btn"):
            self.begin_btn.setEnabled(bool(prompts_valid))

    def update_progress(self):
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
            self.progress_bar.setValue(self.progress_bar.value() + 5)

            # Schedule next update
            self.progress_timer.start(100)

        except Exception as e:
            self.log_message(f"Error updating progress: {e}", "error")
            self.stop_processing()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranscriptProcessorGUI()
    window.show()
    sys.exit(app.exec())
