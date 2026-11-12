"""Claude reads the signals and writes the brief: what changed, why it probably happened, what to do.

Two backends, same prompt and same JSON schema:
- ANTHROPIC_API_KEY set -> Anthropic Messages API (production, runs on a server or in n8n).
- otherwise -> the local Claude Code CLI in headless mode (`claude -p`), isolated: no tools,
  no MCP servers, no project settings. Handy for a laptop demo on a Claude subscription.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

SCHEMA = {
    "type": "object",
    "required": ["status", "headline", "alerts", "opportunities", "client_note"],
    "properties": {
        "status": {"type": "string", "enum": ["green", "amber", "red"]},
        "headline": {"type": "string", "description": "One sentence, max 25 words, the single most important thing this period."},
        "alerts": {"type": "array", "maxItems": 5, "items": {
            "type": "object", "required": ["severity", "source", "title", "evidence", "likely_cause", "next_action", "owner"],
            "properties": {
                "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                "source": {"type": "string", "enum": ["search_console", "ga4", "merchant_center", "cross_source"]},
                "title": {"type": "string"},
                "evidence": {"type": "string", "description": "Exact numbers from the signals, nothing else."},
                "likely_cause": {"type": "string", "description": "Hypothesis. Say 'unclear' if the data does not support one."},
                "next_action": {"type": "string", "description": "One concrete step someone can do in the next 7 days."},
                "owner": {"type": "string", "enum": ["account_manager", "seo", "feed_specialist", "developer", "client"]}}}},
        "opportunities": {"type": "array", "maxItems": 4, "items": {
            "type": "object", "required": ["title", "evidence", "next_action"],
            "properties": {"title": {"type": "string"}, "evidence": {"type": "string"}, "next_action": {"type": "string"}}}},
        "client_note": {"type": "string", "description": "3-4 plain sentences the account manager can paste to the client. No jargon, no internal tool names."},
    },
}

SYSTEM = """You are the analyst on an agency's client account team. Every week you get a JSON summary of one client's
Google Search Console, GA4 and Merchant Center data (current period vs the previous period of the same length,
see window_days) plus alerts that fixed rules already raised.

Write the brief for the account manager.
Rules:
- Use only numbers that appear in the input. Do not estimate revenue or anything that is not in the data.
- Rank by business impact: a suspended Merchant account or a broken tracking setup beats a 12% dip in impressions.
- Look across sources: e.g. Search Console clicks flat but GA4 organic sessions down suggests tracking or consent, not SEO.
- Small numbers are noise. Do not raise an alert on a change from 4 to 2.
- Search queries may be in Ukrainian or Russian. Quote them as they are and add a short English gloss in brackets.
- A source with an "error" field was not available. Mention it once as a setup gap, do not guess its numbers.
- Plain, direct English. No filler, no hype, no em dashes.
Return JSON only, matching the schema."""


def analyze(signals: dict, model: str = "") -> dict:
    payload = json.dumps(signals, ensure_ascii=False, separators=(",", ":"))
    prompt = f"Signals for this week:\n{payload}"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _api(prompt, model or "claude-sonnet-5-5")
    return _cli(prompt, model or "sonnet")


def _api(prompt: str, model: str) -> dict:
    import anthropic  # optional dependency

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model, max_tokens=4000, system=SYSTEM,
        tools=[{"name": "brief", "description": "Return the weekly brief", "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "brief"},
        messages=[{"role": "user", "content": prompt}])
    block = next(b for b in msg.content if b.type == "tool_use")
    out = dict(block.input)
    out["_meta"] = {"backend": "api", "model": model,
                    "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    return out


def _cli(prompt: str, model: str) -> dict:
    exe = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
    cmd = [exe, "-p", "--model", model, "--output-format", "json",
           "--json-schema", json.dumps(SCHEMA),
           "--system-prompt", SYSTEM,
           "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
           "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence"]
    run = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=600,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if run.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {run.stderr[:500] or run.stdout[:500]}")
    env = json.loads(run.stdout)
    out = env.get("structured_output")
    if out is None:  # older CLI: JSON comes back as text
        text = (env.get("result") or "").strip().removeprefix("```json").removesuffix("```")
        out = json.loads(text)
    usage = env.get("usage") or {}
    out["_meta"] = {"backend": "claude-code-cli", "model": model, "cost_usd": env.get("total_cost_usd"),
                    "duration_ms": env.get("duration_ms"),
                    "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}
    return out
