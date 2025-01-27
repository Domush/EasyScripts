### If this application helps you, please consider [Sponsoring me via GitHub Sponsors](https://github.com/sponsors/Domush)
*(Similar to Patreon, but for open-source devs like me who don't place their creations behind a paywall)*

![image](https://github.com/user-attachments/assets/69aea2ff-664a-420f-9608-c0b01b7c4b3c)

---

# YouTube Transcript Downloader (YTD)
### and
# YouTube AI Transcripts (YTT)

### Two amazing utilities, one package.

---

## YouTube Transcript Downloader (YTD)

### Usage
Run the script:
```bash
python YoutubeTranscriptDownloader.py
```

## Overview
The YouTube Transcript Downloader is a Python application for downloading transcripts from YouTube videos and channels. It uses the YouTube Data API and YouTube Transcript API to fetch video metadata and subtitles. The application can save transcripts to files, process video lists, and identify duplicate transcripts.

## Features
| **Feature** | Description |
|---------|-------------|
| **Fetch Single Video Transcript** | Download and save transcripts for individual videos |
| **Process Video Lists** | Extract transcripts from a list of video URLs or IDs in text or CSV files |
| **Channel Video Metadata** | Fetch video metadata from a YouTube channel and save it as a CSV file |
| **Duplicate Detection** | Identify duplicate transcripts in a directory |
| **Customizable Configuration** | Modify log settings, transcript filename length, and regex patterns via `.ytdConfig.json` |

## Requirements
- 🚨 **YouTube API key** 🚨
- Python 3.7+
- Dependencies:
  - See requirements.txt

Install dependencies with:
```bash
pip install -r requirements.txt
```

## Setup
- Clone the repository or download the files.
- Install dependencies (see above).
- Edit the `.yttApiKeys-example.json` file and rename it to `.yttApiKeys.json`:
  - Example entry:
   ```json
   {
        "youtube": {
            "base_url": "https://www.googleapis.com/youtube/v3",
            "api_key": "your api key here"
        }
   }
   ```
- (Optional) Configure `.ytdConfig.json` to customize settings.

## Configuration
The `config.json` file allows you to customize the application.
- `"TRANSCRIPT_FILENAME_LENGTH"`: truncates filenames to max x characters, incl spaces.
- `"REGEX_PATTERNS"`
    - `"sanitize_filename"`: Removes non-standard UTF-8 characters and removes double spaces in title.
    - `"iso_duration"`: Gets the total length from the video.
    - `"youtube_video_id"`: Validates the video ID (the part after 'watch' in youtube video urls)
        - make sure they don't have any other tags such as `?t=xxx`


- **Output Directory**: Transcripts and metadata are saved in the `transcripts` directory.

## Logging
Logs are saved to the specified logging directory as `./logs/ytd-[date].log`.

Logging can be disabled by setting `"ENABLE_LOGGING": false`.

## Known Issues
- Transcripts disabled by the channel owner cannot be downloaded.

## License
YouTube Transcript Downloader (YTD) is fully open-source and available under the [GNU General Public License (GPL)](https://www.gnu.org/licenses/gpl-3.0.txt).

---

# YouTube AI Transcripts (YTT) Usage

---

## Overview
YouTube AI Transcripts is a GUI-based Python application for processing YouTube transcript into well-styled and organized markdown for easy viewing or importing into a vector DB for AI RAG (retrieval augmented generation) usage. It's designed to use the transcript files exported by the included YouTube Transcript Downloader, but you can provide your own files as long as you follow the same json structure as YTD.

## Features
| **Feature** | Description |
|-------------|-------------|
| **Process Transcripts** | Convert any transcript into structured markdown, optimized for technical how-to and coding content. Perfect for converting YouTube channels into websites or updating local RAG agents |
| **Duplicate Detection** | Automatically prevents processing the same transcript multiple times unless processed file is deleted |
| **Customizable Processing** | Highly flexible prompt system allows customizing output format - from technical documentation to creative content like rap lyrics or poems. Edit prompts via GUI or `.yttConfig.json` |

## Requirements
- 🚨 **AI service API key ([Google Gemini](https://aistudio.google.com/apikey) is free, or host your own using [LM Studio](https://lmstudio.ai))** 🚨
- Python 3.7+
- Dependencies:
    - See requirements.txt

Install dependencies with:
```bash
pip install -r requirements.txt
```

## Setup
- Clone the repository or download the files.
- Install dependencies (see above).
- Edit the `.yttApiKeys-example.json` file and rename it to `.yttApiKeys.json`:
  - Example entry:
   ```json
   {
        "google": {
            "name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "model": "gemini-2.0-flash-exp",
            "api_key": "your api key here"
        },
   }
   ```
- (Optional) Use the GUI to adjust the AI prompts to meet your needs (saved in `.yttConfig.json`).

- **Output Directory**: AI processed transcript are saved in the `processed` directory.

## Usage
Run the script:
```bash
python ytt.py
```

## Known Issues
- Smaller AI models (the ones you host yourself) are not very good at formatting content for automated parsing. It's recommended to use a commercial AI service, but the app will automatically retry a few times in the hopes a locally hosted model with figure it out eventually.

## License
YouTube AI Transcripts (YTT) is free for non-commercial use in its current form.

**For commercial use contact me for licensing**: yttsales@webbsense.com

*Copyright 2025 Phillip Webber. All Rights Reserved*

---

# Example AI processed YouTube transcript (using locally hosted Claude 8B Sonnet)

---
---

# Game Development Tips for Beginners in 2024

### Summary

This video provides five key game development tips for beginners in 2024, emphasizing system creation over full games, avoiding marketplace assets initially, focusing on gameplay before art, keeping projects short, and not starting with multiplayer.

This content is based on a video providing advice for aspiring game developers. This is Part 1 of a series covering game development topics.

## Tip 1: Build Systems, Not Full Games

Instead of starting with a complete game, focus on creating individual systems. This approach offers several advantages:

*   **Reduced Pressure:** Working on systems like character locomotion or inventory management reduces the emotional investment compared to a full game project. It makes it easier to change direction or abandon a system without feeling like you're giving up on a major project.
*   **Skill Development:** System-focused projects allow you to concentrate on specific skills and mechanics, such as player movement, UI, or inventory management, and master them.
*   **Reusability:** Well-designed systems can be easily reused in other projects, saving time and effort later on. For example, a character movement system or inventory system can be ported into a new game, rather than having to start from scratch each time. This approach will ensure you develop a solid foundation of knowledge and skill to build future games.

**Example:**

Instead of creating a complete third-person action game as your first project, start by building the following as separate projects:

*   A project focused solely on third-person locomotion.
*   A project focusing on creating an inventory system.
*   A project focusing on creating a menu system.

By breaking down your project in this way you can focus on learning specific skills, and avoid the burnout that can come with overly ambitious projects. This will also ensure you avoid the pitfalls of overly coupled code bases.

## Tip 2: Avoid Marketplace Assets (Initially)

It might seem counterintuitive, but when starting out, avoid using pre-made assets and plugins from marketplaces. Here’s why:

*   **Learning Curve:** Using pre-built systems will prevent you from learning how to implement the mechanics yourself. While it’s helpful to deconstruct and learn from plugins after you have some experience, using them directly from the outset will limit your understanding and skill growth.
*   **Scope Creep:** Marketplace assets often have many more features than you need, leading to feature bloat. This can complicate your project and distract from core gameplay elements.
*   **Maintainability:** Plugins often have complex codebases that can be difficult to understand and modify, making it hard to maintain or customize these systems. When you use a pre-built system, you do not develop the skills required to understand the code, and when issues arise you may not be able to fix them effectively, resulting in wasted time.

**Recommendation:**

Use marketplace assets to learn how systems work, but avoid integrating them directly into your first project. This way you can understand how they function and how to create your own solutions, rather than relying on pre-made assets. Always try to build systems yourself first.

## Tip 3: Don't Focus on Art (Initially)

Unless your game is heavily art-focused, don't prioritize art in your early projects. Here's why:

*   **Time Waste:** Focusing on art early will waste valuable time on assets you will likely replace later. It's better to focus on gameplay and mechanics first, to ensure they are fun, before adding visual elements.
*   **Integration Issues:** Integrating assets can be time-consuming, and many will be replaced as your game evolves. It is more time-efficient to ensure your mechanics are solid first and then worry about the art later.
*   **Premature Satisfaction:** Focusing on art can be a distraction that may mask flaws in gameplay mechanics. If a game looks great, it might make you feel like it is fun, and prevent you from properly evaluating the core mechanics.

**Best Practice:**

Use basic placeholder assets like mannequins and gray boxes. Focus on making the gameplay fun. Once you've achieved that, then focus on the visual presentation. If the game is fun in its simplest form, the art will only enhance the experience.

## Tip 4: Keep Project Time Short and Move On

Avoid getting stuck on a single system for too long. Here's why:

*   **Avoid Perfectionism:** Being overly perfectionistic can lead to burnout. It's better to work on multiple systems and iterate on them, rather than spend too much time on perfecting a single aspect of the game.
*   **Cross-System Learning:** Working on different systems will allow you to transfer learning across multiple areas. A design pattern or problem-solving method you use in one system can apply to another, helping you build your skill set faster.
*   **Observer Pattern Example:** If you learn the *Observer pattern* (also known as *event dispatchers* or *delegates*), in one system, such as an interaction system, you can use it to improve a different system, such as your enemy AI. You won’t discover these connections and improvements unless you work across different systems.

| System         | Purpose                                                                      | Learning Opportunities                                                                   |
| -------------- | ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Enemy System   | Controlling AI behavior, attacks, damage, health.                         | Core game mechanics, state management                                                        |
| Interaction    | Allowing the player to interact with game world objects.                       | The *observer pattern*, code decoupling                                                      |
| Inventory      | Holding/Managing items.                                                                | Data structures, UI                                                                      |
| Menu System    | Displaying/Managing game options.                                                           | UI design, player feedback                                                               |
| Locomotion     | Implementing player movement.                                           | Core game mechanics, player input                                                        |

**Implementation:**

Work on a system for a couple of weeks, then move on to a new system. After a while, return to the old system to iterate on your previous work and make it better. This will lead to a library of well-developed systems that you can use in your future games.

## Tip 5: Don't Start with Multiplayer

Avoid starting with a multiplayer game. Here's why:

*   **Complexity:** Multiplayer games are significantly more complex to develop than single-player games. Implementing features like replication, prediction, and correction can be challenging and time-consuming.
*   **Time Sink:** Replicating features for multiplayer can double the workload, making it a time-sink, and a potentially frustrating task.
*   **Design Issues:** Multiplayer introduces a host of design issues around sessions, login, and matchmaking, all of which require significant effort and resources to implement correctly.

**Note:**

While you can experiment with multiplayer mechanics to understand how they work, avoid making a full multiplayer game as your first major project. It's better to gain experience with single-player games first before taking on the added complexity of multiplayer. Start with the easier aspects of game development before tackling the more complex tasks. This will help you build experience and confidence.

**Summary:**

By following these five tips, aspiring game developers can avoid many common pitfalls and build a solid foundation for future success. Focus on systems, avoid marketplace assets, focus on gameplay, work on multiple systems, and avoid complex multiplayer games. These principles will ensure you gain the most valuable skills and experience possible during your learning journey.
