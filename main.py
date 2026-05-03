"""
Vera Bot — magicpin AI Challenge submission
FastAPI server exposing all 5 required endpoints.
Uses Google Gemini API (free tier).
"""

import os
import time
import uuid
import json
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Vera Bot", version="1.0.0")
start_time = time.time()

# ─── In-memory state ─────────────────────────────────────────────────────────

contexts: dict = {
    "category": {},
    "merchant": {},
    "customer": {},
    "trigger": {},
}

conversations: dict = {}
suppression_keys: set = set()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

TEAM_NAME = os.environ.get("TEAM_NAME", "Vera-AI")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "team@example.com")
TEAM_MEMBERS = [m.strip() for m in os.environ.get("TEAM_MEMBERS", "Dev").split(",")]


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ContextPush(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict
    delivered_at: Optional[str] = None

class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = []

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: Optional[str] = None
    turn_number: Optional[int] = None


# ─── Gemini API caller ────────────────────────────────────────────────────────

async def call_gemini(system_prompt: str, user_content: str) -> str:
    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n---\n\n{user_content}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 800,
        }
    }
    async with httpx.AsyncClient(timeout=28.0) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def parse_json_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except:
                continue
    return json.loads(raw.strip())


# ─── Message composer ─────────────────────────────────────────────────────────

async def compose_message(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
    conversation_history: Optional[list] = None,
    reply_to: Optional[str] = None,
) -> dict:

    is_reply = reply_to is not None
    scope = trigger.get("scope", "merchant")
    trigger_kind = trigger.get("kind", "unknown")

    merchant_name = merchant.get("identity", {}).get("name", "Merchant")
    owner_name = merchant.get("identity", {}).get("owner_first_name", "")
    city = merchant.get("identity", {}).get("city", "")
    languages = merchant.get("identity", {}).get("languages", ["en"])
    category_slug = merchant.get("category_slug", category.get("slug", "unknown"))
    performance = merchant.get("performance", {})
    signals = merchant.get("signals", [])
    active_offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    peer_stats = category.get("peer_stats", {})
    voice = category.get("voice", {})
    digest = category.get("digest", [])
    offer_catalog = category.get("offer_catalog", [])
    subscription = merchant.get("subscription", {})
    conv_hist = merchant.get("conversation_history", [])
    cust_agg = merchant.get("customer_aggregate", {})
    review_themes = merchant.get("review_themes", [])

    lang_instruction = "Hindi-English code-mix (natural Hinglish)" if "hi" in languages else "English"

    auto_reply_detected = False
    if reply_to and conversation_history:
        last_msgs = [m["body"] for m in conversation_history[-3:] if m.get("role") == "merchant"]
        if len(set(last_msgs)) == 1 and len(last_msgs) >= 2:
            auto_reply_detected = True

    if is_reply:
        system_prompt = f"""You are Vera, magicpin's AI merchant assistant on WhatsApp.
Continue this conversation with a merchant. Compose the next reply.

STRICT RULES:
- Language: {lang_instruction}
- Tone: {voice.get('tone', 'peer_collegial')} — collegial, NOT salesy
- Taboo words (NEVER use): {', '.join(voice.get('vocab_taboo', []))}
- Max 3 sentences
- Single CTA at end only
- If merchant said YES/interested: move to ACTION immediately, no more qualifying
- If merchant said STOP/not interested: exit in one polite sentence
- If auto_reply: try once more differently, then exit
- No preamble like "I hope you're well"
- AUTO_REPLY_DETECTED: {auto_reply_detected}

Return ONLY this JSON (no markdown, no explanation):
{{"action": "send", "body": "message text", "cta": "binary_yes_stop or open_ended or none", "rationale": "one line"}}
OR
{{"action": "end", "body": "exit message", "rationale": "one line"}}"""

        user_content = f"""Merchant: {merchant_name} ({city}), category: {category_slug}
Conversation so far: {json.dumps(conversation_history or [], ensure_ascii=False)}
Merchant just replied: "{reply_to}"
Auto-reply detected: {auto_reply_detected}

Return JSON only."""

    else:
        trigger_payload = trigger.get("payload", {})
        top_item_id = trigger_payload.get("top_item_id", "")
        digest_item = next((d for d in digest if d.get("id") == top_item_id), None)

        customer_section = ""
        if customer:
            cname = customer.get("identity", {}).get("name", "Customer")
            clang = customer.get("identity", {}).get("language_pref", "en")
            cstate = customer.get("state", "active")
            crel = customer.get("relationship", {})
            cprefs = customer.get("preferences", {})
            customer_section = f"""
CUSTOMER (send on behalf of merchant TO this customer):
- Name: {cname}, language: {clang}, state: {cstate}
- Last visit: {crel.get('last_visit')}, services: {crel.get('services_received', [])}
- Preferred slots: {cprefs.get('preferred_slots', 'any')}
- Available slots: {trigger_payload.get('available_slots', [])}"""

        system_prompt = f"""You are Vera, magicpin's AI merchant assistant on WhatsApp.
Compose ONE proactive outbound WhatsApp message for this merchant based on the trigger.

STRICT RULES:
1. Language: {lang_instruction}
2. Tone: {voice.get('tone', 'peer_collegial')} — peer/collegial, NOT promotional
3. Taboo words (NEVER use): {', '.join(voice.get('vocab_taboo', []))}
4. MUST use 1-2 concrete facts: numbers, dates, peer stats, source citations
5. Use service+price format: "Haircut @ ₹99" NOT "10% off"
6. Single CTA at the END only
7. Binary YES/STOP for action triggers; open question for info triggers
8. NO preamble ("Hope you're well"), NO re-introduction
9. Max 4 sentences for WhatsApp readability
10. Use compulsion levers: social proof / loss aversion / curiosity / effort externalization

Return ONLY this JSON (no markdown, no explanation):
{{"body": "WhatsApp message text", "cta": "binary_yes_stop or open_ended or none", "send_as": "vera or merchant_on_behalf", "suppression_key": "short_dedup_key", "rationale": "one sentence"}}"""

        user_content = f"""TRIGGER: kind={trigger_kind}, scope={scope}, urgency={trigger.get('urgency', 1)}
TRIGGER PAYLOAD: {json.dumps(trigger_payload, ensure_ascii=False)}
DIGEST ITEM: {json.dumps(digest_item, ensure_ascii=False) if digest_item else "N/A"}

MERCHANT: {merchant_name} (owner: {owner_name}), {city}, category={category_slug}
- Subscription: {subscription.get('status')}, {subscription.get('days_remaining')} days, plan={subscription.get('plan')}
- Performance 30d: views={performance.get('views')}, calls={performance.get('calls')}, CTR={performance.get('ctr')} (peer avg CTR={peer_stats.get('avg_ctr')})
- Active offers: {[o['title'] for o in active_offers]}
- Signals: {signals}
- Customer aggregate: {cust_agg}
- Review themes: {review_themes}
- Last Vera conversation: {json.dumps(conv_hist[-2:] if conv_hist else [], ensure_ascii=False)}

CATEGORY ({category_slug}):
- Offer catalog: {[o['title'] for o in offer_catalog[:5]]}
- Peer stats: avg_rating={peer_stats.get('avg_rating')}, avg_ctr={peer_stats.get('avg_ctr')}, avg_reviews={peer_stats.get('avg_review_count')}
- Digest (latest 3): {json.dumps([{{'title': d['title'], 'source': d.get('source',''), 'summary': d.get('summary','')[:120]}} for d in digest[:3]], ensure_ascii=False)}
{customer_section}

Return JSON only."""

    raw = await call_gemini(system_prompt, user_content)
    return parse_json_response(raw)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - start_time),
        "contexts_loaded": {k: len(v) for k, v in contexts.items()}
    }

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": TEAM_NAME,
        "team_members": TEAM_MEMBERS,
        "model": "gemini-1.5-flash",
        "approach": "Gemini-powered composer with trigger-kind dispatch, auto-reply detection, voice/language matching per category",
        "contact_email": CONTACT_EMAIL,
        "version": "1.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

@app.post("/v1/context")
async def receive_context(push: ContextPush):
    scope = push.scope
    if scope not in contexts:
        return JSONResponse(status_code=400, content={"accepted": False, "reason": "invalid_scope"})

    cid = push.context_id
    current = contexts[scope].get(cid, {})
    current_version = current.get("version", 0)

    if push.version < current_version:
        return JSONResponse(status_code=409, content={"accepted": False, "reason": "stale_version", "current_version": current_version})

    if push.version == current_version and current:
        return {"accepted": True, "ack_id": f"ack_{cid}_v{push.version}_noop", "stored_at": datetime.now(timezone.utc).isoformat()}

    contexts[scope][cid] = {"payload": push.payload, "version": push.version}
    return {"accepted": True, "ack_id": f"ack_{cid}_v{push.version}", "stored_at": datetime.now(timezone.utc).isoformat()}

@app.post("/v1/tick")
async def tick(req: TickRequest):
    if not GEMINI_API_KEY:
        return {"actions": []}

    actions = []
    for trigger_id in req.available_triggers:
        trigger_data = contexts["trigger"].get(trigger_id, {})
        if not trigger_data:
            continue

        trigger = trigger_data["payload"]
        supp_key = trigger.get("suppression_key", trigger_id)
        if supp_key in suppression_keys:
            continue

        merchant_id = trigger.get("merchant_id")
        if not merchant_id:
            continue

        merchant_data = contexts["merchant"].get(merchant_id, {})
        if not merchant_data:
            continue
        merchant = merchant_data["payload"]

        category_slug = merchant.get("category_slug", "")
        category = contexts["category"].get(category_slug, {}).get("payload", {})

        customer = None
        customer_id = trigger.get("customer_id")
        if customer_id:
            cust_data = contexts["customer"].get(customer_id, {})
            if cust_data:
                customer = cust_data["payload"]

        try:
            result = await compose_message(category, merchant, trigger, customer)
        except Exception as e:
            continue

        conv_id = f"conv_{uuid.uuid4().hex[:8]}"
        suppression_keys.add(supp_key)
        conversations[conv_id] = [{"role": "vera", "body": result.get("body", ""), "ts": req.now}]

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": result.get("send_as", "vera"),
            "trigger_id": trigger_id,
            "template_name": f"vera_{trigger.get('kind', 'general')}_v1",
            "template_params": [],
            "body": result.get("body", ""),
            "cta": result.get("cta", "open_ended"),
            "suppression_key": supp_key,
            "rationale": result.get("rationale", ""),
        })

        if len(actions) >= 3:
            break

    return {"actions": actions}

@app.post("/v1/reply")
async def reply(req: ReplyRequest):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="API key not configured")

    conv_id = req.conversation_id
    if conv_id not in conversations:
        conversations[conv_id] = []

    conversations[conv_id].append({
        "role": req.from_role,
        "body": req.message,
        "ts": req.received_at or datetime.now(timezone.utc).isoformat()
    })

    merchant_data = contexts["merchant"].get(req.merchant_id, {})
    merchant = merchant_data.get("payload", {}) if merchant_data else {}
    category_slug = merchant.get("category_slug", "")
    category = contexts["category"].get(category_slug, {}).get("payload", {})

    customer = None
    if req.customer_id:
        cust_data = contexts["customer"].get(req.customer_id, {})
        if cust_data:
            customer = cust_data["payload"]

    trigger = {"scope": "merchant", "kind": "reply", "payload": {}}

    try:
        result = await compose_message(
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
            conversation_history=conversations[conv_id],
            reply_to=req.message,
        )
    except Exception as e:
        return {"action": "end", "rationale": f"Error: {str(e)}"}

    action = result.get("action", "send")
    if action == "send":
        body = result.get("body", "")
        conversations[conv_id].append({"role": "vera", "body": body, "ts": datetime.now(timezone.utc).isoformat()})
        return {"action": "send", "body": body, "cta": result.get("cta", "open_ended"), "rationale": result.get("rationale", "")}
    elif action == "wait":
        return {"action": "wait", "wait_seconds": 1800, "rationale": result.get("rationale", "backing off")}
    else:
        return {"action": "end", "rationale": result.get("rationale", "conversation ended")}
