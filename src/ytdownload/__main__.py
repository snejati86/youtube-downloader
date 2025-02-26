#!/usr/bin/env python3
"""
Entry point for the YouTube Downloader application.

This module initializes and launches the main application window.
"""
import sys
from typing import List

from PyQt6.QtWidgets import QApplication

from ytdownload.gui.main_window import MainWindow


def main(args: List[str] = None) -> int:
    """
    Initialize and run the application.

    Args:
        args: Command line arguments.

    Returns:
        int: Exit code of the application.
    """
    if args is None:
        args = sys.argv

    app = QApplication(args)
    app.setApplicationName("YouTube Downloader")
    app.setOrganizationName("YTDownload")
    app.setOrganizationDomain("ytdownload.app")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main()) 