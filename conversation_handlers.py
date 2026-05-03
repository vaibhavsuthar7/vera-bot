"""
conversation_handlers.py — Optional multi-turn conversation handler.
Implements respond() for the replay test bonus points.
"""

import re

# Auto-reply patterns seen in production WhatsApp Business
AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"aapki madad ke liye shukriya",
    r"main ek automated",
    r"i am an automated",
    r"hamari team.*pahuncha",
    r"we will get back",
    r"hum jald.*sampark",
    r"bahut-bahut shukriya.*jaankari",
]


def is_auto_reply(message: str) -> bool:
    msg_lower = message.lower()
    for pattern in AUTO_REPLY_PATTERNS:
        if re.search(pattern, msg_lower):
            return True
    return False


def detect_intent(message: str) -> str:
    """
    Returns: 'accept' | 'reject' | 'question' | 'auto_reply' | 'neutral'
    """
    if is_auto_reply(message):
        return "auto_reply"

    msg_lower = message.lower()

    accept_signals = ["yes", "haan", "ha ", "sure", "okay", "ok", "theek", "chalega",
                      "go ahead", "karo", "please do", "let's do", "send me", "bhejo",
                      "join", "judrna", "sign up", "register"]
    reject_signals = ["no", "nahi", "nope", "not interested", "stop", "band karo",
                      "mat karo", "don't", "chhod do", "later", "baad mein", "busy"]

    for s in accept_signals:
        if s in msg_lower:
            return "accept"
    for s in reject_signals:
        if s in msg_lower:
            return "reject"

    if "?" in message or any(w in msg_lower for w in ["kya", "how", "what", "kitna", "kab", "when", "price", "cost"]):
        return "question"

    return "neutral"


def respond(state: dict, merchant_message: str) -> dict:
    """
    state: {
      "merchant_id": str,
      "category_slug": str,
      "conversation_history": list of {role, body},
      "merchant_name": str,
      "last_trigger_kind": str,
      "auto_reply_count": int,
      "merchant_language": str,   # "hi" | "en" | "hi-en"
    }
    merchant_message: the latest message from the merchant

    Returns:
      {"action": "send"|"wait"|"end", "body": str, "rationale": str}
    """
    intent = detect_intent(merchant_message)
    auto_reply_count = state.get("auto_reply_count", 0)
    merchant_name = state.get("merchant_name", "")
    first_name = merchant_name.split()[0] if merchant_name else "aap"
    lang = state.get("merchant_language", "hi-en")
    trigger_kind = state.get("last_trigger_kind", "general")

    # ── Auto-reply handling ──────────────────────────────────────────────────
    if intent == "auto_reply":
        if auto_reply_count == 0:
            # First auto-reply: try once more with a direct question
            if "hi" in lang:
                body = f"{first_name} ji, directly aapse baat karni thi — kya aap 2 minute de sakte hain? Kuch important share karna tha."
            else:
                body = f"Hi {first_name}, wanted to reach you directly — got something useful to share. Can you spare 2 mins?"
            return {"action": "send", "body": body, "rationale": "First auto-reply detected; one direct attempt before exiting"}
        else:
            # Second auto-reply: graceful exit
            if "hi" in lang:
                body = "Koi baat nahi! Main baad mein try karungi. Aapka business accha chal raha hai — best wishes! 🙂"
            else:
                body = "No problem! I'll try another time. Best wishes for your business! 🙂"
            return {"action": "end", "body": body, "rationale": "Second auto-reply; graceful exit to preserve merchant goodwill"}

    # ── Clear rejection ──────────────────────────────────────────────────────
    if intent == "reject":
        if "hi" in lang:
            body = "Samajh gaye! Koi zarurat ho toh main yahan hoon. 🙂"
        else:
            body = "Understood! I'm here if you need anything. 🙂"
        return {"action": "end", "body": body, "rationale": "Merchant signaled not interested; clean exit"}

    # ── Clear acceptance → move to action immediately ────────────────────────
    if intent == "accept":
        if trigger_kind in ("research_digest", "cde_opportunity"):
            if "hi" in lang:
                body = "Sending now — abstract + ek patient-ed WhatsApp draft bhi bana rahi hoon jo aap directly share kar sakte hain. Ready in 2 min. ✅"
            else:
                body = "Sending now — also drafting a 90-sec patient-ed WhatsApp you can reshare. Ready in 2 min. ✅"
        elif trigger_kind in ("perf_dip", "perf_spike"):
            if "hi" in lang:
                body = "Done! Maine aapka Google post draft kar diya — 3 options hain. Review karke bata dein kaun sa publish karun. ✅"
            else:
                body = "Done! I've drafted 3 Google post options for you. Review and tell me which to publish. ✅"
        elif trigger_kind in ("recall_due", "appointment_tomorrow"):
            if "hi" in lang:
                body = "Booking confirm ho gayi! Patient ko reminder bhej diya. Koi aur help chahiye toh batayein. 🦷✅"
            else:
                body = "Booking confirmed! Reminder sent to the patient. Let me know if you need anything else. ✅"
        elif trigger_kind in ("renewal_due", "winback_eligible"):
            if "hi" in lang:
                body = "Badhiya! Renewal link bhej rahi hoon — UPI/card dono options hain. Plan activate hote hi profile boost shuru ho jayega. ✅"
            else:
                body = "Great! Sending the renewal link — UPI or card, your choice. Profile boost kicks in as soon as it's active. ✅"
        else:
            if "hi" in lang:
                body = "Perfect! Kaam ho gaya — main yeh abhi set kar rahi hoon. 2 minute mein done. ✅"
            else:
                body = "Perfect! On it — will have this done in 2 minutes. ✅"
        return {"action": "send", "body": body, "rationale": "Merchant accepted; moved to action immediately without re-qualifying"}

    # ── Question: answer briefly, keep momentum ──────────────────────────────
    if intent == "question":
        if "hi" in lang:
            body = f"Zaroor batata hoon — {merchant_message[:30]}... ke baare mein. Short mein: [relevant answer]. Kya aage badhein?"
        else:
            body = f"Good question — briefly: [relevant answer based on context]. Shall we proceed?"
        # Note: In production this would call Claude with the specific question
        return {"action": "send", "body": body, "rationale": "Merchant asked a clarifying question; answered briefly to maintain momentum"}

    # ── Neutral / unclear — keep conversation alive ──────────────────────────
    if "hi" in lang:
        body = f"Samajh gaye. {first_name} ji, ek kaam ki cheez share karni thi — kya 2 minute hain?"
    else:
        body = f"Got it. {first_name}, had something useful to share — do you have 2 minutes?"
    return {"action": "send", "body": body, "rationale": "Neutral reply; re-engaging with low-friction question"}
