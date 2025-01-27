# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-27

### Changed
- Major overhaul of the GUI, switched from Tkinter to PyQt6
- Improved GUI responsiveness and layout organization
- Enhanced TranscriptProcessorGUI with better progress tracking and status updates
- Restructured layout to include AI provider and prompts sections
- Streamlined progress reporting and file processing notifications
- Dynamic window sizing based on screen height
- Made the file listing section the main focus now that the status log isn't as vital

### Added
- Window icon and consistent styling
- Added multi-threading support
  - You can now edit AI prompts while it processes and it'll use the new prompts on the next file
- Directory rescan functionality for file list updates
  - Checking 'Include subdirectories' now triggers an automatic re-scan
- File list display with auto-scrolling
- Enhanced status indicators during processing
  - Files now have status icons. No more digging through the status log
- Keyboard shortcuts for saving and canceling in Prompt Editor

### Enhanced
- Progress tracking and UI responsiveness
- Processing status updates system
- Notification system for skipped files
- Error handling and status enum implementation

## [0.3.0] - 2024-01-26

### Added
- New PromptEditor dialog for improved prompt management
- Configuration management with .ytdConfig.json and .yttApiKeys.json
- Markdown preview functionality
- Tooltips and keyboard shortcuts for processing buttons

### Changed
- Refactored prompt editing and handling system
- Enhanced prompt loading and saving mechanisms
- Improved GUI with better font sizes and padding
- Streamlined save/cancel functionality

### Fixed
- AI response handling and retry logic
- Error handling and response validation
- Button configurations in GUI

## [0.2.0] - 2024-01-25

### Added
- Graphical User Interface (GUI)
- AI transcript processing capabilities
- Logging system to prevent duplicate processing
- Enhanced prompt system for better AI output

### Changed
- Refactored project structure
- Converted Downloader to a class-based system
- Improved filename sanitization

## [0.1.0] - 2024-01-24

### Added
- Playlist support
- Initial AI transcript reformatter
- Basic configuration system

### Changed
- Updated project requirements
- Restructured project files
- Enhanced config settings

## [0.0.1] - 2024-01-23
- Initial fork from original repository
