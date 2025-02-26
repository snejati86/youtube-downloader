"""
Logging utilities for the YouTube Downloader application.

This module provides logging configuration and utilities.
"""
import os
import sys
import logging
from datetime import datetime
from typing import Optional

# Global logger instance
logger: Optional[logging.Logger] = None


def setup_logger(log_level: int = logging.INFO) -> logging.Logger:
    """
    Set up the application logger.
    
    Args:
        log_level: Logging level (default: INFO)
        
    Returns:
        logging.Logger: Configured logger
    """
    global logger
    
    if logger is not None:
        return logger
    
    # Create logs directory
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    # Configure logger
    logger = logging.getLogger('ytdownload')
    logger.setLevel(log_level)
    
    # Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create file handler
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'ytdownload_{timestamp}.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Create formatter and add to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger


def get_logger() -> logging.Logger:
    """
    Get the application logger. Sets up a new logger if none exists.
    
    Returns:
        logging.Logger: Application logger
    """
    global logger
    
    if logger is None:
        logger = setup_logger()
        
    return logger 