#!/usr/bin/env python3
"""
Answer Suggester
Maps form fields to suggested answers based on the user's profile.yaml
(identity, narrative, and answers sections — see profile.yaml.example).
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

# Make src/profile_loader importable from this MCP server directory
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from profile_loader import load_profile

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class AnswerSuggestion:
    """Suggested answer for a field"""
    field_name: str
    field_label: str
    field_type: str
    suggested_answer: str
    sources: List[str]  # e.g., ['resume', 'cover-letter', 'interview-prep']
    confidence: float  # 0-1
    notes: Optional[str] = None


class AnswerSuggester:
    """Suggests answers based on profile.yaml data"""

    def __init__(self, profile: Optional[dict] = None):
        profile = profile or load_profile()
        identity = profile.get('identity', {})
        answers = profile.get('answers', {})

        # Standard fields, all sourced from profile.yaml
        self.FIELD_PATTERNS = {
            'first_name': identity.get('first_name', ''),
            'first-name': identity.get('first_name', ''),
            'firstName': identity.get('first_name', ''),
            'last_name': identity.get('last_name', ''),
            'last-name': identity.get('last_name', ''),
            'lastName': identity.get('last_name', ''),
            'full_name': identity.get('name', ''),
            'email': identity.get('email', ''),
            'phone': identity.get('phone', ''),
            'location': identity.get('location', ''),
            'city': identity.get('city', ''),
            'state': identity.get('state', ''),
            'zip': identity.get('zip', ''),
            'country': identity.get('country', ''),
            'linkedin': identity.get('linkedin', ''),
            'github': identity.get('github', ''),

            # Experience / role level
            'years_experience': str(answers.get('years_experience', '')),
            'experience_level': str(answers.get('years_experience', '')),

            # Work status
            'work_authorization': answers.get('work_authorization', ''),
            'availability': answers.get('availability', ''),
            'notice_period': answers.get('notice_period', ''),
            'employment_type': answers.get('employment_type', ''),
            'visa_sponsorship': answers.get('visa_sponsorship', ''),
        }

        # Free-text screening questions, sourced from the profile's answers section
        self.CUSTOM_QUESTION_PATTERNS = {
            'tell_us_about': {
                'patterns': [r'tell us about', r'describe yourself', r'about yourself', r'background'],
                'answer': answers.get('about_you', ''),
            },
            'why_interested': {
                'patterns': [r'why.*interested', r'why.*position', r'why.*role', r'why this company'],
                'answer': answers.get('why_interested', ''),
            },
            'project_proud': {
                'patterns': [r'project.*proud', r'recent.*achievement', r'accomplishment'],
                'answer': answers.get('proudest_project', ''),
            },
            'why_leave': {
                'patterns': [r'why did you leave', r'why are you leaving'],
                'answer': answers.get('why_leaving', ''),
            },
        }
    
    def suggest_answer(self, field_name: str, field_label: str, field_type: str,
                      company: Optional[str] = None) -> AnswerSuggestion:
        """Suggest answer for a field"""
        
        # Try pattern matching
        field_key = field_name.lower().replace(' ', '_').replace('-', '_')
        
        if field_key in self.FIELD_PATTERNS and self.FIELD_PATTERNS[field_key]:
            return AnswerSuggestion(
                field_name=field_name,
                field_label=field_label,
                field_type=field_type,
                suggested_answer=self.FIELD_PATTERNS[field_key],
                sources=['profile'],
                confidence=0.99
            )
        
        # Try custom questions
        field_label_lower = field_label.lower()
        for pattern_type, pattern_data in self.CUSTOM_QUESTION_PATTERNS.items():
            for pattern in pattern_data['patterns']:
                if pattern in field_label_lower:
                    return AnswerSuggestion(
                        field_name=field_name,
                        field_label=field_label,
                        field_type=field_type,
                        suggested_answer=pattern_data['answer'],
                        sources=['interview-prep', 'cover-letter'],
                        confidence=0.80,
                        notes=f"Customize for {company or 'target company'}"
                    )
        
        # Default: generic answer
        return AnswerSuggestion(
            field_name=field_name,
            field_label=field_label,
            field_type=field_type,
            suggested_answer='[Please provide answer]',
            sources=[],
            confidence=0.0,
            notes='No automatic suggestion available'
        )
    
    def suggest_dropdown_value(self, field_label: str, options: List[str]) -> Optional[str]:
        """Suggest dropdown value from available options"""
        
        # Match against experience level
        if any(x in field_label.lower() for x in ['level', 'seniority', 'experience']):
            for opt in options:
                if any(x in opt.lower() for x in ['principal', 'lead', 'staff', 'senior']):
                    return opt
        
        # Match against years
        if 'years' in field_label.lower():
            for opt in options:
                if any(x in opt.lower() for x in ['20+', '15+', '10+', '25', '20', '15']):
                    return opt
        
        # Default to first non-empty option
        return options[0] if options else None


def main():
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: answer_suggester.py <field_name> <field_label> [company]")
        print("Example: answer_suggester.py first_name 'First Name' Databricks")
        sys.exit(1)
    
    field_name = sys.argv[1]
    field_label = sys.argv[2]
    company = sys.argv[3] if len(sys.argv) > 3 else None
    field_type = 'text'  # default
    
    suggester = AnswerSuggester()
    suggestion = suggester.suggest_answer(field_name, field_label, field_type, company)
    
    print(json.dumps({
        'field_name': suggestion.field_name,
        'field_label': suggestion.field_label,
        'suggested_answer': suggestion.suggested_answer,
        'sources': suggestion.sources,
        'confidence': suggestion.confidence,
        'notes': suggestion.notes
    }, indent=2))


if __name__ == '__main__':
    main()
