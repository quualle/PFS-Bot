# utils.py
import logging

def debug_print(category, message):
    """Helper for consistent debug printing"""
    logging.debug(f"[{category}] {message}")
    print(f"[{category}] {message}")