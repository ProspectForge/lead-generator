# Outreach Generation Design

LLM-powered personalized outreach message generation for leads.

## Requirements

- Generate 4 message types per lead: cold email, LinkedIn connection request, LinkedIn follow-up, follow-up email
- Two generation modes: template-guided (uses existing templates as style guide) and free-form (original copy from lead data + system prompt)
- Support both OpenAI and Anthropic as LLM providers
- Cache generated messages to flat files in `data/outreach/` so they won't regenerate
- View generated messages in the interactive CLI from the lead detail view
- Regenerate with either simple re-roll or custom user instructions (e.g. "make it shorter")
- Single lead at a time (from CLI when browsing leads)
- Support multiple templates stored in `templates/*.md`

## Architecture

### New Modules

**`src/llm_client.py`** — Unified LLM abstraction

- `LLMClient` class with `generate(system_prompt: str, user_prompt: str) -> str`
- Supports OpenAI (`openai` SDK) and Anthropic (`anthropic` SDK)
- Provider selected via `settings.outreach.llm_provider`
- Uses existing `OPENAI_API_KEY` or new `ANTHROPIC_API_KEY` from `.env`

**`src/outreach_generator.py`** — Message generation logic

- Takes lead data (DataFrame row) + template path (or None for free-form)
- Generates all 4 message types in a single LLM call
- Parses response into individual messages
- Reads/writes cached files from `data/outreach/`
- Supports regeneration with optional user instructions
- Key functions:
  - `generate_outreach(lead_row, template_path=None, contact_index=1) -> dict[str, str]`
  - `load_cached_outreach(brand_name) -> dict[str, str] | None`
  - `regenerate_outreach(lead_row, message_type=None, instructions=None) -> dict[str, str]`

**`src/config.py`** — Add `OutreachSettings` dataclass

```python
@dataclass
class OutreachSettings:
    llm_provider: str = "openai"       # "openai" or "anthropic"
    llm_model: str = "gpt-4o"          # model name
    default_template: str = ""         # default template filename
```

Also add `anthropic_api_key` to `Settings` and `ANTHROPIC_API_KEY` to `.env.example`.

## Template System

Templates are markdown files in `templates/` matching the existing format:

```markdown
# Outreach Templates -- Campaign Name

Campaign description.

**Positioning:** ...
**Tone:** ...
**CTA:** ...

## CSV Field Mapping
| Placeholder | CSV Field |
...

## Cold Email
(template content with {placeholders})

## LinkedIn Connection Request
...

## LinkedIn Follow-Up
...

## Follow-Up Email
...
```

- Templates auto-discovered from `templates/*.md`
- In template-guided mode: template + lead data sent to LLM for deep personalization
- In free-form mode: generic system prompt with company positioning, LLM writes original copy
- User picks mode + template in CLI before generating

## File Storage & Caching

Flat files in `data/outreach/`:

```
data/outreach/
  brand-name-slug_cold_email.md
  brand-name-slug_linkedin_request.md
  brand-name-slug_linkedin_followup.md
  brand-name-slug_follow_up_email.md
```

Each file has a metadata header:

```markdown
---
brand: Brand Name
template: outreach-rasai-inventory-automation
contact: John Smith
generated_at: 2026-02-17T14:30:00
model: gpt-4o
instructions: null
---

Message content here...
```

Caching behavior:
- Before generating, check if files exist for this brand
- If they exist, load and display (no API call)
- User explicitly chooses "Regenerate" to overwrite
- Regeneration overwrites the file (no version history)

## CLI Integration

Integration point: `_display_lead_details` navigation choices in `__main__.py`.

Add a "Generate Outreach" option to the lead detail view navigation.

### User Flow

```
Lead Detail View
  +-- "Generate Outreach"
       +-- Check if outreach files already exist for this brand
       |   +-- YES: Show existing messages, offer "View / Regenerate"
       |   +-- NO: Continue to generation
       +-- Select mode: "Template-guided" or "Free-form"
       |   +-- If template-guided: pick template from templates/*.md
       +-- Select contact (if multiple contacts on the lead)
       +-- Generate all 4 messages (with progress spinner)
       +-- Display messages in Rich panels
       +-- Options:
            +-- "Regenerate all" (simple re-roll)
            +-- "Regenerate with instructions" (user types guidance)
            +-- "Regenerate specific message" (pick which one)
            +-- "Back to lead"
```

Messages displayed using Rich `Panel` components with message type as title.

## LLM Prompting Strategy

### Template-Guided Mode

**System prompt:**

> You are an expert B2B outreach copywriter. You write personalized sales messages that feel like they were written by someone who genuinely researched the recipient's business. You follow the provided template's structure, tone, and positioning but deeply personalize using the lead's specific data. Keep messages concise and natural -- never use filler or generic phrases.

**User prompt:**

> Here is the template to follow as a style guide:
> {template_content}
>
> Here is the lead data:
> - Brand: {brand_name}
> - Website: {website}
> - Locations: {location_count} across {cities}
> - Contact: {contact_name}, {contact_title}
> - E-commerce platform: {ecommerce_platform}
> - Marketplaces: {marketplaces}
> - Industry: {industry}
> - Employee count: {employee_count}
>
> Generate personalized versions of all 4 message types. Output each under a markdown heading: ## Cold Email, ## LinkedIn Connection Request, ## LinkedIn Follow-Up, ## Follow-Up Email.

### Free-Form Mode

Same structure but without template content. More creative system prompt describing company positioning.

### Regeneration with Instructions

Append user instructions to the prompt:

> Previous generation: {existing_message}
> User feedback: "{user_instructions}"
> Regenerate this message incorporating the feedback.

### Efficiency

Single API call generates all 4 messages to minimize cost and latency.

## Dependencies

Add to `requirements.txt`:
- `anthropic>=0.40.0` (for Anthropic provider support)

The `openai` SDK is already a dependency.

## Approach Decision

**Chosen: Approach A (Embedded in Lead Detail View)** -- generate outreach from within the existing lead browsing flow. Natural workflow, minimal new navigation, easy to extend later.
