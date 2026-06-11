#!/usr/bin/env python3
"""
Form Parser Orchestrator
Discovers, parses, and suggests answers for job application forms
Usage: form_parser.py <job_url> [--output json|markdown]
"""

import json
import sys
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from form_extractor import extract_form, FormField
from answer_suggester import AnswerSuggester

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class FormParserOrchestrator:
    """Main orchestrator for parsing forms and generating answers"""
    
    def __init__(self, url: str):
        self.url = url
        self.suggester = AnswerSuggester()
        self.parsed_form = None
    
    def parse(self):
        """Parse the form"""
        logger.info(f"Parsing form from {self.url}...")
        
        try:
            self.parsed_form = extract_form(self.url)
            logger.info(f"✓ Successfully parsed form ({self.parsed_form.form_system.value})")
            
            # Add suggestions
            self._add_suggestions()
            
            return self.parsed_form
        except Exception as e:
            logger.error(f"Failed to parse form: {e}")
            raise
    
    def _add_suggestions(self):
        """Add answer suggestions to all fields"""
        
        if not self.parsed_form.fields:
            return
        
        # Extract company name from URL if possible
        company = self._extract_company_name()
        
        for field in self.parsed_form.fields:
            # Get suggestion
            suggestion = self.suggester.suggest_answer(
                field.name, field.label, field.field_type.value, company
            )
            
            field.suggested_answer = suggestion.suggested_answer
            
            # For dropdowns, try to pick a value
            if field.field_type.value == 'select' and field.options:
                suggested_value = self.suggester.suggest_dropdown_value(field.label, field.options)
                if suggested_value:
                    field.suggested_answer = suggested_value
    
    def _extract_company_name(self) -> Optional[str]:
        """Extract company name from URL"""
        from urllib.parse import urlparse
        
        parsed = urlparse(self.url)
        domain = parsed.netloc
        
        # Extract company name from domain
        if 'workday' in domain:
            parts = domain.split('.')
            if parts[0] != 'myworkdayjobs':
                return parts[0].capitalize()
        
        if 'lever' in domain:
            parts = domain.split('.')
            if parts[0] != 'jobs':
                return parts[0].capitalize()
        
        return None
    
    def to_markdown(self) -> str:
        """Generate human-readable markdown form template"""
        
        if not self.parsed_form:
            return "Form not parsed yet"
        
        md = []
        
        # Header
        md.append(f"# Job Application Form")
        md.append(f"**Source**: {self.parsed_form.form_system.value.upper()}")
        md.append(f"**URL**: {self.parsed_form.url}")
        md.append(f"**Parsed**: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
        md.append("")
        
        # Title and description
        if self.parsed_form.form_title:
            md.append(f"## {self.parsed_form.form_title}")
            md.append("")
        
        if self.parsed_form.form_description:
            md.append(f"> {self.parsed_form.form_description}")
            md.append("")
        
        # Fields
        md.append(f"## Form Fields ({len(self.parsed_form.fields)} total)")
        md.append("")
        
        # Group by category
        by_category = {}
        for field in self.parsed_form.fields:
            cat = field.field_category or 'other'
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(field)
        
        for category in ['standard', 'custom', 'preference', 'other']:
            if category not in by_category:
                continue
            
            fields = by_category[category]
            
            md.append(f"### {category.title()} Fields ({len(fields)})")
            md.append("")
            
            for field in fields:
                md.append(f"#### {field.label}")
                md.append(f"- **Field Name**: `{field.name}`")
                md.append(f"- **Type**: {field.field_type.value}")
                md.append(f"- **Required**: {'Yes' if field.required else 'No'}")
                
                if field.placeholder:
                    md.append(f"- **Placeholder**: {field.placeholder}")
                
                if field.options:
                    md.append(f"- **Options**: {', '.join(field.options[:5])}")
                    if len(field.options) > 5:
                        md.append(f"  (+ {len(field.options) - 5} more)")
                
                md.append("")
                md.append(f"**Suggested Answer**:")
                md.append(f"```")
                md.append(field.suggested_answer or "[No suggestion available]")
                md.append(f"```")
                md.append("")
        
        # Instructions
        md.append("## How to Fill This Form")
        md.append("")
        md.append("1. **Standard Fields** (auto-populated): Copy-paste directly into form")
        md.append("2. **Custom Questions** (marked with suggested text): Review & customize for company")
        md.append("3. **Dropdowns/Preferences**: Select from options matching your profile")
        md.append("")
        md.append("> **⏱️ Time estimate**: 5-10 minutes to complete & submit")
        md.append("")
        
        return "\n".join(md)
    
    def to_json(self) -> str:
        """Generate JSON output"""
        if not self.parsed_form:
            return "{}"
        
        return json.dumps(self.parsed_form.to_dict(), indent=2)


def main():
    if len(sys.argv) < 2:
        print("Usage: form_parser.py <job_url> [--output json|markdown]")
        print("")
        print("Examples:")
        print("  form_parser.py https://example.workdayjobs.com/job/123")
        print("  form_parser.py https://example.workdayjobs.com/job/123 --output markdown > form.md")
        sys.exit(1)
    
    url = sys.argv[1]
    output_format = 'markdown'  # default
    
    for arg in sys.argv[2:]:
        if arg.startswith('--output'):
            output_format = arg.split('=')[1] if '=' in arg else 'markdown'
    
    try:
        orchestrator = FormParserOrchestrator(url)
        parsed = orchestrator.parse()
        
        if output_format == 'json':
            print(orchestrator.to_json())
        else:
            print(orchestrator.to_markdown())
        
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
