#!/usr/bin/env python3
"""
Run script for the YouTube Downloader application.

This script starts the application without needing to install it.
"""
import os
import sys
import platform
import logging
from typing import List


def main(args: List[str] = None) -> int:
    """
    Start the YouTube Downloader application.

    Args:
        args: Command line arguments

    Returns:
        int: Exit code
    """
    if args is None:
        args = sys.argv
        
    # Add src directory to Python path so imports work correctly
    project_root = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(project_root, 'src')
    sys.path.insert(0, src_dir)
    
    # Create logs directory
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Initialize logger early
    from ytdownload.utils.logger import setup_logger
    logger = setup_logger(log_level=logging.INFO)
    logger.info("Application starting")
    
    # Fix SSL certificate issues on macOS
    if platform.system() == 'Darwin':  # Only on macOS
        logger.info("Checking SSL certificates...")
        from ytdownload.utils.ssl_fix import fix_macos_ssl_certificates, disable_ssl_verification
        
        # Try to fix certificates properly first
        if not fix_macos_ssl_certificates():
            logger.warning("Could not install SSL certificates. Disabling SSL verification.")
            print("Warning: Could not install SSL certificates.")
            print("Temporarily disabling SSL verification for development purposes.")
            disable_ssl_verification()
            print("Note: This is less secure but will allow the app to function.")
    
    # Now this import will work
    logger.info("Initializing main application")
    from ytdownload.__main__ import main as app_main
    return app_main(args)


if __name__ == "__main__":
    sys.exit(main()) 