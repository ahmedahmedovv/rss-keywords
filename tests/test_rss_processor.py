import pytest
from rss_keywords.a import (
    clean_text,
    detect_language,
    normalize_date,
    extract_keywords
)

def test_clean_text():
    text = "<p>Hello World!</p>"
    assert clean_text(text) == "hello world"

def test_detect_language():
    text = "Hello world"
    assert detect_language(text) == "en"
    
    text = "Dzień dobry"
    assert detect_language(text) == "pl"

def test_normalize_date():
    # Test various date formats
    assert normalize_date("2024-01-01") == "2024-01-01"
    assert normalize_date("01/01/2024") == "2024-01-01"
    assert normalize_date("Jan 1, 2024") == "2024-01-01"

def test_extract_keywords():
    text = "Python is a great programming language for data science"
    keywords = extract_keywords(text)
    assert isinstance(keywords, list)
    assert len(keywords) > 0
    assert "python" in [k.lower() for k in keywords] 