#!/usr/bin/env python3
"""
Form Extractor
Detects form system (Workday, Lever, Greenhouse, etc) and extracts all form fields
"""

import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class FormSystem(str, Enum):
    """Supported job application form systems"""
    WORKDAY = "workday"
    LEVER = "lever"
    GREENHOUSE = "greenhouse"
    LINKEDIN = "linkedin"
    LINKEDIN_EXTERNAL = "linkedin_external"
    ASHBY = "ashby"
    BAMBOO = "bamboo"
    JOBVITE = "jobvite"
    APPLY = "apply"  # Custom HTML
    UNKNOWN = "unknown"


class FieldType(str, Enum):
    """Field types"""
    TEXT = "text"
    EMAIL = "email"
    PHONE = "phone"
    NUMBER = "number"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    FILE = "file"
    DATE = "date"
    HIDDEN = "hidden"
    UNKNOWN = "unknown"


@dataclass
class FormField:
    """Represents a form field"""
    name: str
    label: str
    field_type: FieldType
    required: bool = False
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None
    html_selector: Optional[str] = None
    suggested_answer: Optional[str] = None
    field_category: Optional[str] = None  # e.g., "standard", "custom", "preference"
    
    def to_dict(self):
        """Convert to dictionary"""
        d = asdict(self)
        d['field_type'] = self.field_type.value
        return d


@dataclass
class ParsedForm:
    """Complete parsed form"""
    url: str
    form_system: FormSystem
    form_title: Optional[str] = None
    form_description: Optional[str] = None
    fields: Optional[List[FormField]] = None
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'url': self.url,
            'form_system': self.form_system.value,
            'form_title': self.form_title,
            'form_description': self.form_description,
            'field_count': len(self.fields) if self.fields else 0,
            'fields': [f.to_dict() for f in self.fields] if self.fields else []
        }


class FormDetector:
    """Detects form system from URL and HTML"""
    
    FORM_SIGNATURES = {
        FormSystem.WORKDAY: {
            'url_patterns': [r'\.myworkdayjobs\.com', r'workdayjobs\.com'],
            'css_selectors': ['[data-testid*="form"]', '[class*="wd-"]', 'form[id*="wd"]'],
            'text_patterns': ['workday', 'careers powered by workday']
        },
        FormSystem.LEVER: {
            'url_patterns': [r'lever\.co', r'jobs\.lever\.co'],
            'css_selectors': ['[data-qa="form"]', '.template-form', '[class*="lever"]'],
            'text_patterns': ['lever']
        },
        FormSystem.GREENHOUSE: {
            'url_patterns': [r'greenhouse\.io', r'boards\.greenhouse\.io'],
            'css_selectors': ['[data-testid="form"]', '.form-container', 'form.template-form'],
            'text_patterns': ['greenhouse']
        },
        FormSystem.LINKEDIN: {
            'url_patterns': [r'linkedin\.com/jobs'],
            'css_selectors': ['[data-form-id]', '.jobs-search__results-list'],
            'text_patterns': ['linkedin']
        },
        FormSystem.ASHBY: {
            'url_patterns': [r'ashbyhq\.com', r'jobs\.ashbyhq\.com'],
            'css_selectors': ['[data-component-name="JobApplicationForm"]'],
            'text_patterns': ['ashby']
        },
        FormSystem.BAMBOO: {
            'url_patterns': [r'bamboohr\.com'],
            'css_selectors': ['[class*="bamboo"]', 'form[class*="application"]'],
            'text_patterns': ['bamboo']
        },
    }
    
    def __init__(self, html: str, url: str):
        self.html = html
        self.url = url
        self.soup = BeautifulSoup(html, 'html.parser')
    
    def detect(self) -> FormSystem:
        """Detect form system"""
        
        # Check URL patterns first
        for system, sigs in self.FORM_SIGNATURES.items():
            for pattern in sigs['url_patterns']:
                if re.search(pattern, self.url, re.IGNORECASE):
                    logger.info(f"Detected {system.value} by URL pattern")
                    return system
        
        # Check CSS selectors
        for system, sigs in self.FORM_SIGNATURES.items():
            for selector in sigs['css_selectors']:
                if self.soup.select(selector):
                    logger.info(f"Detected {system.value} by CSS selector")
                    return system
        
        # Check text patterns
        html_text = self.soup.get_text().lower()
        for system, sigs in self.FORM_SIGNATURES.items():
            for pattern in sigs['text_patterns']:
                if pattern in html_text:
                    logger.info(f"Detected {system.value} by text pattern")
                    return system
        
        logger.warning("Could not detect form system, defaulting to UNKNOWN")
        return FormSystem.UNKNOWN


class FormExtractor:
    """Extracts form fields from HTML"""
    
    def __init__(self, html: str, url: str):
        self.html = html
        self.url = url
        self.soup = BeautifulSoup(html, 'html.parser')
        self.detector = FormDetector(html, url)
        self.form_system = self.detector.detect()
    
    def extract(self) -> ParsedForm:
        """Extract form fields"""
        logger.info(f"Extracting form from {self.url}")
        logger.info(f"Detected system: {self.form_system.value}")
        
        # Find main form
        form = self.soup.find('form')
        if not form:
            logger.warning("No form element found")
            form = self.soup.find('div', class_=re.compile(r'form|application', re.I))
        
        fields = []
        if form:
            fields = self._extract_fields(form)
        else:
            # Fallback: extract all inputs/textareas
            fields = self._extract_all_inputs()
        
        logger.info(f"Extracted {len(fields)} fields")
        
        return ParsedForm(
            url=self.url,
            form_system=self.form_system,
            form_title=self._extract_title(),
            form_description=self._extract_description(),
            fields=fields
        )
    
    def _extract_fields(self, form) -> List[FormField]:
        """Extract fields from form element"""
        fields = []
        
        # Extract input fields
        for input_elem in form.find_all(['input', 'textarea', 'select']):
            field = self._parse_field_element(input_elem)
            if field:
                fields.append(field)
        
        return fields
    
    def _extract_all_inputs(self) -> List[FormField]:
        """Fallback: extract all form inputs from page"""
        fields = []
        
        for input_elem in self.soup.find_all(['input', 'textarea', 'select']):
            field = self._parse_field_element(input_elem)
            if field:
                fields.append(field)
        
        return fields
    
    def _parse_field_element(self, elem) -> Optional[FormField]:
        """Parse a single form field"""
        
        name = elem.get('name', '').strip()
        if not name:
            return None
        
        # Find label
        label = self._find_label(elem, name)
        
        # Determine field type
        field_type = self._get_field_type(elem)
        
        # Extract attributes
        placeholder = elem.get('placeholder', '')
        required = 'required' in elem.attrs or 'aria-required' in elem.attrs
        
        # Extract options for select
        options = None
        if field_type == FieldType.SELECT:
            options = [opt.get_text(strip=True) for opt in elem.find_all('option')]
        
        # Determine category
        category = self._categorize_field(name, label)
        
        return FormField(
            name=name,
            label=label,
            field_type=field_type,
            required=required,
            placeholder=placeholder,
            options=options,
            field_category=category
        )
    
    def _find_label(self, elem, name: str) -> str:
        """Find label for field"""
        
        # Check for associated label
        elem_id = elem.get('id', '')
        if elem_id:
            label_elem = self.soup.find('label', {'for': elem_id})
            if label_elem:
                return label_elem.get_text(strip=True)
        
        # Check for parent label
        parent_label = elem.find_parent('label')
        if parent_label:
            return parent_label.get_text(strip=True)
        
        # Use name as fallback
        return name.replace('_', ' ').title()
    
    def _get_field_type(self, elem) -> FieldType:
        """Determine field type"""
        
        if elem.name == 'textarea':
            return FieldType.TEXTAREA
        
        if elem.name == 'select':
            return FieldType.SELECT
        
        input_type = elem.get('type', 'text').lower()
        type_map = {
            'email': FieldType.EMAIL,
            'phone': FieldType.PHONE,
            'tel': FieldType.PHONE,
            'number': FieldType.NUMBER,
            'checkbox': FieldType.CHECKBOX,
            'radio': FieldType.RADIO,
            'file': FieldType.FILE,
            'date': FieldType.DATE,
            'hidden': FieldType.HIDDEN,
        }
        
        return type_map.get(input_type, FieldType.TEXT)
    
    def _categorize_field(self, name: str, label: str) -> str:
        """Categorize field as standard/custom/preference"""
        
        standard_fields = {
            'first_name', 'firstName', 'firstname',
            'last_name', 'lastName', 'lastname',
            'email', 'phone', 'location', 'resume',
            'cv', 'cover_letter', 'portfolio'
        }
        
        if name.lower() in standard_fields:
            return 'standard'
        
        if any(w in label.lower() for w in ['tell us', 'why', 'interest', 'experience', 'question', 'custom']):
            return 'custom'
        
        return 'preference'
    
    def _extract_title(self) -> Optional[str]:
        """Extract form title"""
        
        # Check for h1
        h1 = self.soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        # Check for page title
        title = self.soup.find('title')
        if title:
            return title.get_text(strip=True)
        
        return None
    
    def _extract_description(self) -> Optional[str]:
        """Extract form description"""
        
        # Check for first paragraph
        p = self.soup.find('p', class_=re.compile(r'description|intro|intro-text', re.I))
        if p:
            return p.get_text(strip=True)
        
        return None


def extract_form(url: str) -> ParsedForm:
    """Main function to extract form from URL"""
    
    logger.info(f"Fetching {url}...")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        raise
    
    extractor = FormExtractor(response.text, url)
    return extractor.extract()


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: form_extractor.py <job_url>")
        print("Example: form_extractor.py https://example.com/jobs/123")
        sys.exit(1)
    
    url = sys.argv[1]
    
    try:
        form = extract_form(url)
        print(json.dumps(form.to_dict(), indent=2))
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
