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
    QGroupBox,
    QListWidget,
    QListWidgetItem,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QTextCursor, QColor, QTextCharFormat, QShortcut, QKeySequence
import qtawesome as qta
import sys
import os
import json
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
    progress_signal = pyqtSignal(dict)  # Emitting a dictionary
    finished_signal = pyqtSignal()

    def __init__(self, processor, provider_key, file_paths):
        super().__init__()
        self.processor = processor
        self.processor.progress_callback = self.handle_progress
        self.provider_key = provider_key
        self.file_paths = file_paths
        self.cancelled = False

    def handle_progress(self, message: str, status: ProcessingStatus, data: dict = None):
        if data is None:
            data = {}
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
        file_path = data.get("file_path", "")
        signal_data = {
            "message": message,
            "level": gui_level,
            "file_path": file_path,
            "processed_count": 0,
            "total_count": 0,
        }
        self.progress_signal.emit(signal_data)

    def run(self):
        try:
            self.processor.set_provider(self.provider_key)
            file_count = len(self.file_paths)
            file_success_count = 0

            for file_path in self.file_paths:
                if self.cancelled:
                    raise InterruptedError("Processing cancelled by user")
                try:
                    result = self.processor.process_file(file_path)
                    if result:
                        file_success_count += 1
                        signal_data = {
                            "message": "File processed successfully",
                            "level": "success",
                            "file_path": file_path,
                            "processed_count": file_success_count,
                            "total_count": file_count,
                        }
                        self.progress_signal.emit(signal_data)
                    else:
                        signal_data = {
                            "message": "File processing failed",
                            "level": "error",
                            "file_path": file_path,
                            "processed_count": file_success_count,
                            "total_count": file_count,
                        }
                        self.progress_signal.emit(signal_data)
                except ProcessingError as e:
                    signal_data = {
                        "message": str(e),
                        "level": "error",
                        "file_path": file_path,
                        "processed_count": 0,
                        "total_count": 0,
                    }
                    self.progress_signal.emit(signal_data)

            level = "success" if file_success_count > 0 else "info"
            signal_data = {
                "message": f"\nProcessing complete. {file_success_count} of {file_count} files processed",
                "level": level,
                "file_path": "",
                "processed_count": file_success_count,
                "total_count": file_count,
            }
            self.progress_signal.emit(signal_data)
        except InterruptedError as e:
            signal_data = {
                "message": str(e),
                "level": "error",
                "file_path": "",
                "processed_count": 0,
                "total_count": 0,
            }
            self.progress_signal.emit(signal_data)
        except ProviderError as e:
            signal_data = {
                "message": f"Provider error: {str(e)}",
                "level": "error",
                "file_path": "",
                "processed_count": 0,
                "total_count": 0,
            }
            self.progress_signal.emit(signal_data)
        except ConfigurationError as e:
            signal_data = {
                "message": f"Configuration error: {str(e)}",
                "level": "error",
                "file_path": "",
                "processed_count": 0,
                "total_count": 0,
            }
            self.progress_signal.emit(signal_data)
        except Exception as e:
            signal_data = {
                "message": f"Error during processing: {e}",
                "level": "error",
                "file_path": "",
                "processed_count": 0,
                "total_count": 0,
            }
            self.progress_signal.emit(signal_data)
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

        self.resize(800, 600)
        parent_center = parent.geometry().center()
        self.move(parent_center.x() - 400, parent_center.y() - 300)

    def setup_ui(self, current_prompt):
        layout = QVBoxLayout(self)

        self.editor = QTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        if current_prompt:
            self.editor.setText(current_prompt)
        layout.addWidget(self.editor)

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
        self.selected_paths = []
        self.is_directory = False
        self.include_subdirs_state = False
        self.processing_thread = None
        self.providers = {}
        self.provider_name_to_key = {}
        self.current_path = os.getcwd()
        self.processing_queue = queue.Queue()

        self.configure_styles()
        self.padding_style = "font-size: 14px; padding: 10px 20px;"
        self.setup_ui()
        self.processor = AiTranscriptProcessor(progress_callback=self.log_message)
        self.load_providers()

        self.setWindowTitle("YouTube Transcript Processor")
        screen_height = QApplication.primaryScreen().size().height()
        self.resize(1024, int(screen_height * 2 / 3))
        self.setMinimumSize(800, 600)

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

    def log_message(self, message, level="default", file_path=None):
        color = self.log_colors.get(level, self.log_colors["default"])
        timestamp = datetime.now().strftime("%H:%M:%S")
        text = f"[{timestamp}] {message.strip()}"
        self.append_to_log(text, color)

    def append_to_log(self, message, color):
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

        char_format = QTextCharFormat()
        char_format.setForeground(QColor(color))
        cursor.insertText(message + "\n", char_format)
        self.log_text.ensureCursorVisible()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)

        title_label = QLabel("YouTube Transcript Processor")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333; margin-bottom: 20px;")
        main_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #5A5A5A;
                border-radius: 10px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #27AE60;
                border-radius: 10px;
            }
        """
        )
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignCenter)

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

        # Buttons layout
        process_layout = QHBoxLayout()
        self.process_file_btn = QPushButton("Select File(s)")
        self.process_file_btn.clicked.connect(self.select_files)
        self.process_dir_btn = QPushButton("Select Directory")
        self.process_dir_btn.clicked.connect(self.select_directory)
        process_layout.addWidget(self.process_file_btn)
        process_layout.addWidget(self.process_dir_btn)
        self.include_subdirs = QCheckBox("Include Subdirectories")
        self.include_subdirs.setChecked(False)
        process_layout.addWidget(self.include_subdirs)

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

        self.process_file_btn.setStyleSheet(self.padding_style)
        self.process_dir_btn.setStyleSheet(self.padding_style)
        self.set_default_btn.setStyleSheet(self.padding_style)
        self.edit_system_btn.setStyleSheet(self.padding_style)
        self.edit_user_btn.setStyleSheet(self.padding_style)

        # File list
        file_list_label = QLabel("Files to Process")
        file_list_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        main_layout.addWidget(file_list_label)
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("font-size: 16px; padding: 10px;")
        main_layout.addWidget(self.file_list)

        # Begin button
        begin_layout = QHBoxLayout()
        self.begin_btn = QPushButton("Begin Processing")
        self.begin_btn.setStyleSheet(self.padding_style)
        self.begin_btn.clicked.connect(self.begin_processing)
        begin_layout.addStretch()
        begin_layout.addWidget(self.begin_btn)
        main_layout.addLayout(begin_layout)

        # Log
        log_label = QLabel("Status Log")
        log_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        log_label.setStyleSheet("margin-top: 0px;")
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
            self.is_directory = False
            self.file_list.clear()
            self.selected_paths = []
            for f in files:
                self.selected_paths.append(os.path.normpath(f))
                item = QListWidgetItem(os.path.basename(f))
                self.file_list.addItem(item)

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Directory to Process", self.current_path)
        if directory:
            self.is_directory = True
            self.file_list.clear()
            directory = os.path.normpath(directory)
            # Gather all .json files from this directory (and subdirectories if checked).
            files_to_add = []
            if self.include_subdirs.isChecked():
                for root, _, files in os.walk(directory):
                    for file in files:
                        if file.endswith(".json") and not file.startswith("."):
                            files_to_add.append(os.path.normpath(os.path.join(root, file)))
            else:
                for file in os.listdir(directory):
                    if file.endswith(".json") and not file.startswith("."):
                        files_to_add.append(os.path.normpath(os.path.join(directory, file)))

            # Display them in the GUI
            for file_path in files_to_add:
                item = QListWidgetItem(os.path.basename(file_path))
                self.file_list.addItem(item)
            # Here, we store these file paths directly, so the QThread can process them
            self.selected_paths = files_to_add

    def begin_processing(self):
        # If a processing thread is already running, treat this as a cancel.
        if self.processing_thread is not None and self.processing_thread.isRunning():
            self.processing_thread.cancelled = True
            self.log_message("Cancelling... Please wait.", "warning")
            self.begin_btn.setEnabled(False)
            return

        # Make sure we have file paths selected.
        if not self.selected_paths:
            self.log_message("No files selected.", "warning")
            return

        # Make sure an AI provider is selected
        provider_name = self.provider_combo.currentText()
        if not provider_name:
            self.log_message("Please select an AI provider first", "warning")
            return

        provider_key = self.provider_name_to_key.get(provider_name)

        # Start background thread
        self.processing_thread = TranscriptProcessingThread(self.processor, provider_key, self.selected_paths)
        self.processing_thread.progress_signal.connect(self.update_file_status)
        self.processing_thread.finished_signal.connect(self.stop_processing)
        self.processing_thread.start()

        self.start_processing()

    def update_file_status(self, signal_data):
        message = signal_data.get("message", "")
        level = signal_data.get("level", "default")
        file_path = signal_data.get("file_path", "")
        processed_count = signal_data.get("processed_count", 0)
        total_count = signal_data.get("total_count", 0)

        if total_count > 0:
            self.progress_bar.setValue(int((processed_count / total_count) * 100))
        self.log_message(message, level, file_path)

        base_name = os.path.basename(file_path)
        for index in range(self.file_list.count()):
            item = self.file_list.item(index)
            if item.text() == base_name:
                if level == "success":
                    item.setIcon(qta.icon("fa.check", color="green"))
                elif level == "error":
                    item.setIcon(qta.icon("fa.times", color="red"))
                elif level == "warning":
                    item.setIcon(qta.icon("fa.square", color="gray"))
                elif level == "error":
                    item.setIcon(qta.icon("fa.times", color="red"))
                elif level == "info":
                    item.setIcon(qta.icon("fa.spinner", color="blue"))
                break

    def start_processing(self):
        self.status_label.setText("Processing... Please wait")
        self.process_file_btn.setEnabled(False)
        self.process_dir_btn.setEnabled(False)
        self.begin_btn.setText("Cancel Processing")
        self.begin_btn.clicked.disconnect()
        self.begin_btn.clicked.connect(self.begin_processing)
        self.progress_bar.setVisible(False)
        self.progress_bar.setVisible(True)
        self.progress_timer.start()

    def stop_processing(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.process_file_btn.setEnabled(True)
        self.process_dir_btn.setEnabled(True)
        self.begin_btn.setText("Begin Processing")
        self.begin_btn.clicked.disconnect()
        self.begin_btn.clicked.connect(self.begin_processing)
        self.status_label.setText("Ready")
        self.processing_thread = None
        self.progress_timer.stop()
        self.begin_btn.setEnabled(True)

    def update_progress(self):
        # Animate progress bar in indeterminate mode
        value = self.progress_bar.value()
        value = (value + 5) % 100
        self.progress_bar.setValue(value)

    def edit_prompt(self, prompt_type):
        current_prompt = getattr(self.processor, f"{prompt_type}_prompt", "")
        dialog = PromptEditorDialog(self, prompt_type, current_prompt, self.save_prompt)
        dialog.show()

    def save_prompt(self, prompt_type, new_prompt):
        if prompt_type == "system":
            self.processor.system_prompt = new_prompt
        elif prompt_type == "user":
            self.processor.user_prompt = new_prompt

        self.log_message(f"Updated {prompt_type} prompt.", "success")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TranscriptProcessorGUI()
    window.show()
    sys.exit(app.exec())
