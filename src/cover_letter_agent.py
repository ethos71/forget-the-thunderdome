#!/usr/bin/env python3
"""
AutoGen-powered cover letter generator.
Uses a 2-agent conversation: Researcher + Writer.

Uses AutoGen when an LLM provider is available. Local-first: a reachable local
Ollama server (http://localhost:11434) is preferred, even when a paid key
(OPENAI_API_KEY / ANTHROPIC_API_KEY) is set. The paid key is used only when
Ollama is down, or when FTT_FORCE_PAID=1.
Falls back to template-based generation on ANY failure
(no provider at all, import error, network timeout, etc.).

Usage:
  from cover_letter_agent import generate_cover_letter
  letter = generate_cover_letter("Stripe", "Principal Engineer", job_description="...")
"""

import os
import sys
from typing import Optional

import ai_config
from profile_loader import load_profile


def _build_profile_text(profile: dict) -> str:
    """Render the candidate profile (from profile.yaml) as prompt text."""
    identity = profile.get("identity", {})
    search = profile.get("search", {})
    narrative = profile.get("narrative", {})

    strengths = "\n".join(f"- {s}" for s in narrative.get("key_strengths", []))
    history_lines = []
    for jobrec in narrative.get("work_history", []):
        history_lines.append(
            f"- {jobrec.get('title', '')} at {jobrec.get('company', '')} ({jobrec.get('years', '')})"
        )
        for h in jobrec.get("highlights", []):
            history_lines.append(f"    • {h}")
    history = "\n".join(history_lines)

    target_roles = ", ".join(search.get("target_roles", []))
    contact = " | ".join(
        x for x in [identity.get("phone", ""), identity.get("email", ""),
                    identity.get("github", "")] if x
    )

    return f"""
Name: {identity.get('name', '')}
Location: {identity.get('location', '')}

Pitch: {(narrative.get('elevator_pitch') or '').strip()}

Key Accomplishments:
{strengths}

Work History:
{history}

Technical: {narrative.get('tech_summary', '')}

Target roles: {target_roles}
Contact: {contact}
"""

_RESEARCHER_PROMPT = """You are a company research specialist. Given a company name and job role,
search for recent information about:
1. Company mission, product, and recent news (1–2 sentences)
2. The engineering culture and technical stack
3. Why this role matters to the company's goals
4. One specific thing that would excite a senior engineer about this opportunity

Keep your research concise — 150 words max. Be factual, not generic."""

_WRITER_PROMPT = """You are an expert cover letter writer for engineers.
Write a compelling, authentic cover letter for the candidate described below.

Rules:
- Maximum 4 short paragraphs
- Opening: genuine excitement about THIS specific company (use the research)
- Body: 2–3 specific accomplishments that directly match the role requirements
- Closing: confident, not desperate — he's a strong candidate
- NO corporate buzzwords, NO filler phrases like "I believe I would be a great fit"
- Tone: confident peer, not supplicant
- End with contact info block

Do not hallucinate company facts. Only use what the researcher provided.
Do not invent accomplishments — only use what the candidate profile states."""


def generate_cover_letter(
    company: str,
    role: str,
    job_description: Optional[str] = None,
) -> str:
    """
    Generate a tailored cover letter using AutoGen.
    Returns the letter as a string.
    Falls back to template on any failure.
    """
    if not ai_config.is_available():
        return _template_fallback(company, role, job_description)

    try:
        return _autogen_generate(company, role, job_description)
    except Exception as e:
        print(f"  ⚠️  AutoGen cover letter failed ({e}), using template.", file=sys.stderr)
        return _template_fallback(company, role, job_description)


def _autogen_generate(company: str, role: str, job_description: Optional[str]) -> str:
    """Internal: runs the AutoGen 2-agent conversation."""
    try:
        import autogen
    except ImportError:
        raise ImportError("pyautogen not installed")

    config_list = ai_config.get_openai_config()
    if not config_list:
        raise ValueError("No LLM config available")

    llm_config = {
        "config_list": config_list,
        "timeout": 60,
        "temperature": 0.4,
    }

    # ── Agents ────────────────────────────────────────────────────────────

    profile = load_profile()
    profile_text = _build_profile_text(profile)
    candidate_name = profile.get("identity", {}).get("name", "the candidate")

    researcher = autogen.AssistantAgent(
        name="Researcher",
        system_message=_RESEARCHER_PROMPT,
        llm_config=llm_config,
    )

    writer = autogen.AssistantAgent(
        name="Writer",
        system_message=_WRITER_PROMPT + f"\n\nCandidate profile:\n{profile_text}",
        llm_config=llm_config,
    )

    user_proxy = autogen.UserProxyAgent(
        name="Coordinator",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=4,
        is_termination_msg=lambda msg: "FINAL_LETTER:" in msg.get("content", ""),
        code_execution_config=False,
    )

    jd_section = f"\n\nJob description:\n{job_description[:1000]}" if job_description else ""

    # Step 1: Research
    research_result = {"content": ""}

    def capture_research(recipient, messages, sender, config):
        for msg in reversed(messages):
            if msg.get("name") == "Researcher":
                research_result["content"] = msg.get("content", "")
                break
        return False, None

    researcher.register_reply(
        trigger=autogen.UserProxyAgent,
        reply_func=capture_research,
        position=0,
    )

    user_proxy.initiate_chat(
        researcher,
        message=(
            f"Research {company} for a {role} application. "
            f"Focus on recent engineering culture, product mission, and why this role matters.{jd_section}"
        ),
        max_turns=2,
        silent=True,
    )

    research = research_result["content"] or f"{company} is a leading technology company."

    # Step 2: Write letter
    letter_result = {"content": ""}

    def capture_letter(recipient, messages, sender, config):
        for msg in reversed(messages):
            if msg.get("name") == "Writer":
                letter_result["content"] = msg.get("content", "")
                break
        return False, None

    writer.register_reply(
        trigger=autogen.UserProxyAgent,
        reply_func=capture_letter,
        position=0,
    )

    user_proxy.initiate_chat(
        writer,
        message=(
            f"Write a cover letter for {candidate_name} applying to {company} as {role}.\n\n"
            f"Company research:\n{research}{jd_section}\n\n"
            "End your response with FINAL_LETTER: on its own line, then the complete letter."
        ),
        max_turns=3,
        silent=True,
    )

    raw = letter_result["content"]
    if "FINAL_LETTER:" in raw:
        return raw.split("FINAL_LETTER:", 1)[1].strip()
    if raw:
        return raw.strip()

    raise ValueError("Writer produced no output")


def _template_fallback(
    company: str, role: str, job_description: Optional[str] = None
) -> str:
    """Template-based cover letter (always available, profile-driven)."""
    profile = load_profile()
    identity = profile.get("identity", {})
    narrative = profile.get("narrative", {})

    pitch = (narrative.get("elevator_pitch") or "").strip()
    strengths = narrative.get("key_strengths", [])
    tech_summary = narrative.get("tech_summary", "")

    key_req = "building scalable systems"
    if job_description:
        jd_lower = job_description.lower()
        req_map = {
            "ai": "deploying AI at scale",
            "ml": "machine learning systems",
            "data": "data infrastructure",
            "fraud": "fraud detection",
            "compliance": "regulatory compliance",
            "architect": "system architecture",
            "fintech": "fintech solutions",
            "lead": "team leadership",
        }
        for kw, val in req_map.items():
            if kw in jd_lower:
                key_req = val
                break

    strength_bullets = "\n".join(f"• {s}" for s in strengths[:4]) or "• [Add key_strengths to profile.yaml]"
    contact_lines = "\n".join(
        x for x in [identity.get("name", ""), identity.get("phone", ""),
                    identity.get("email", ""), identity.get("github", "")] if x
    )

    return f"""Dear Hiring Manager,

{pitch} I'm excited about {company}'s {role} position.

Your role emphasizes {key_req}. My recent work directly demonstrates this:

{strength_bullets}

Technical depth: {tech_summary}

What excites me about {company}: You're solving problems that matter at scale, and this role lines up directly with the work I do best.

I'm ready to bring proven execution and ownership to your challenges.

Best regards,
{contact_lines}
"""
