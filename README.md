# YouTube Downloader

macOS-styled application to download content from YouTube channels.

## Features

- Search for YouTube channels and display their videos
- Select individual videos or all videos at once
- Download options: video, audio-only, or transcripts
- Concurrent downloads for maximum efficiency

## Installation

1. Clone this repository:
```bash
git clone https://github.com/snejati86/youtube-downloader.git
cd youtube-downloader
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Run the application:
```bash
python -m src.ytdownload
```

## Development

### Project Structure

```
ytdownload/
├── src/
│   └── ytdownload/
│       ├── api/          # YouTube API interactions
│       ├── gui/          # UI components
│       ├── services/     # Core functionality
│       └── utils/        # Helper functions
├── tests/                # Test modules
├── requirements.txt      # Dependencies
└── README.md
```

### Testing

Run tests with pytest:
```bash
pytest
```

## License

MIT

## Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - GUI framework

