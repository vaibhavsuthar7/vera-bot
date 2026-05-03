"""
Generate submission.jsonl — 30 composed messages using Gemini API (free).
Run: python generate_submission.py
Requires: GEMINI_API_KEY env variable
"""

import os, json, httpx, asyncio

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

with open("dataset/categories/dentists.json") as f: cat_dentists = json.load(f)
with open("dataset/categories/salons.json") as f: cat_salons = json.load(f)
with open("dataset/categories/restaurants.json") as f: cat_restaurants = json.load(f)
with open("dataset/categories/gyms.json") as f: cat_gyms = json.load(f)
with open("dataset/categories/pharmacies.json") as f: cat_pharmacies = json.load(f)
with open("dataset/merchants_seed.json") as f: merchants_raw = json.load(f)["merchants"]
with open("dataset/triggers_seed.json") as f: triggers_raw = json.load(f)["triggers"]
with open("dataset/customers_seed.json") as f: customers_raw = json.load(f)["customers"]

categories = {"dentists": cat_dentists, "salons": cat_salons, "restaurants": cat_restaurants, "gyms": cat_gyms, "pharmacies": cat_pharmacies}
merchants = {m["merchant_id"]: m for m in merchants_raw}
triggers = {t["id"]: t for t in triggers_raw}
customers = {c["customer_id"]: c for c in customers_raw}

TEST_PAIRS = [
    ("T01", "trg_001_research_digest_dentists", None),
    ("T02", "trg_002_compliance_dci_radiograph", None),
    ("T03", "trg_003_recall_due_priya", "c_001_priya_for_m001"),
    ("T04", "trg_004_perf_dip_bharat", None),
    ("T05", "trg_005_renewal_due_bharat", None),
    ("T06", "trg_006_festival_diwali", None),
    ("T07", "trg_007_bridal_followup_kavya", "c_005_kavya_for_m003"),
    ("T08", "trg_008_curious_ask_studio11", None),
    ("T09", "trg_009_winback_glamour", None),
    ("T10", "trg_010_ipl_match_delhi", None),
    ("T11", "trg_011_review_theme_late_delivery", None),
    ("T12", "trg_012_milestone_mylari", None),
    ("T13", "trg_013_corporate_thali_planning", None),
    ("T14", "trg_014_seasonal_acquisition_dip_powerhouse", None),
    ("T15", "trg_015_winback_rashmi", None),
    ("T16", "trg_016_kids_yoga_program_drafting", None),
    ("T17", "trg_017_kids_yoga_trial_followup_karthik", None),
    ("T18", "trg_018_supply_atorvastatin_recall", None),
    ("T19", "trg_019_chronic_refill_grandfather", None),
    ("T20", "trg_020_summer_demand_shift", None),
    ("T21", "trg_021_unverified_gbp_sunrise", None),
    ("T22", "trg_022_cde_webinar_dentists", None),
    ("T23", "trg_023_competitor_opened_dentist", None),
    ("T24", "trg_024_perf_spike_zen", None),
    ("T25", "trg_025_dormancy_glamour", None),
    ("T26", "trg_001_research_digest_dentists", "c_002_rohit_for_m001"),
    ("T27", "trg_006_festival_diwali", "c_004_sneha_for_m003"),
    ("T28", "trg_010_ipl_match_delhi", "c_006_amit_for_m005"),
    ("T29", "trg_004_perf_dip_bharat", None),
    ("T30", "trg_022_cde_webinar_dentists", None),
]

async def compose_one(test_id, trigger_id, customer_id):
    trigger = triggers.get(trigger_id)
    if not trigger:
        return {"test_id": test_id, "error": f"trigger not found: {trigger_id}"}

    merchant_id = trigger.get("merchant_id")
    merchant = merchants.get(merchant_id)
    if not merchant:
        return {"test_id": test_id, "error": f"merchant not found: {merchant_id}"}

    category_slug = merchant.get("category_slug", "")
    category = categories.get(category_slug, {})
    customer = customers.get(customer_id) if customer_id else None

    performance = merchant.get("performance", {})
    peer_stats = category.get("peer_stats", {})
    voice = category.get("voice", {})
    digest = category.get("digest", [])
    offer_catalog = category.get("offer_catalog", [])
    signals = merchant.get("signals", [])
    active_offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    cust_agg = merchant.get("customer_aggregate", {})
    review_themes = merchant.get("review_themes", [])
    subscription = merchant.get("subscription", {})
    conv_hist = merchant.get("conversation_history", [])
    languages = merchant.get("identity", {}).get("languages", ["en"])
    lang_instruction = "Hindi-English code-mix (natural Hinglish)" if "hi" in languages else "English"
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
        customer_section = f"\nCUSTOMER (send on behalf of merchant TO customer): Name={cname}, lang={clang}, state={cstate}, last_visit={crel.get('last_visit')}, slots={trigger_payload.get('available_slots', [])}"

    prompt = f"""You are Vera, magicpin's AI merchant assistant on WhatsApp.
Compose ONE proactive WhatsApp message for this trigger + merchant.

RULES:
1. Language: {lang_instruction}
2. Tone: {voice.get('tone', 'peer_collegial')} — peer/collegial NOT promotional
3. NEVER use: {', '.join(voice.get('vocab_taboo', []))}
4. Use 1-2 concrete facts: numbers, dates, peer stats, sources
5. Service+price: "Haircut @ ₹99" not "10% off"
6. Single CTA at END only (binary YES/STOP for action; open question for info)
7. No preamble, no re-introduction
8. Max 4 sentences

TRIGGER: kind={trigger.get('kind')}, scope={trigger.get('scope')}, urgency={trigger.get('urgency')}
PAYLOAD: {json.dumps(trigger_payload, ensure_ascii=False)}
DIGEST_ITEM: {json.dumps(digest_item, ensure_ascii=False) if digest_item else "N/A"}

MERCHANT: {merchant.get('identity',{}).get('name')} ({merchant.get('identity',{}).get('city')}), {category_slug}
- Subscription: {subscription.get('status')}, {subscription.get('days_remaining')}d remaining
- Performance: views={performance.get('views')}, calls={performance.get('calls')}, CTR={performance.get('ctr')} (peer={peer_stats.get('avg_ctr')})
- Active offers: {[o['title'] for o in active_offers]}
- Signals: {signals}
- Customer aggregate: {cust_agg}
- Review themes: {review_themes}
- Offer catalog: {[o['title'] for o in offer_catalog[:4]]}
- Digest: {json.dumps([{{'title': d['title'], 'source': d.get('source',''), 'summary': d.get('summary','')[:100]}} for d in digest[:3]], ensure_ascii=False)}
{customer_section}

Return ONLY JSON — no markdown, no explanation:
{{"body": "message", "cta": "binary_yes_stop|open_ended|none", "send_as": "vera|merchant_on_behalf", "suppression_key": "short_key", "rationale": "one sentence"}}"""

    url = f"{GEMINI_URL}?key={GEMINI_API_KEY}"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 600}}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()

    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                result = json.loads(part)
                result["test_id"] = test_id
                return result
            except: continue
    result = json.loads(raw)
    result["test_id"] = test_id
    return result

async def main():
    if not GEMINI_API_KEY:
        print("ERROR: Set GEMINI_API_KEY environment variable!")
        print("Get free key at: aistudio.google.com")
        return

    print(f"Generating 30 submissions using Gemini 1.5 Flash (free)...\n")
    results = []

    for i, (test_id, trigger_id, customer_id) in enumerate(TEST_PAIRS):
        print(f"  [{i+1:02d}/30] {test_id}: {trigger_id[:35]}...", end=" ", flush=True)
        try:
            result = await compose_one(test_id, trigger_id, customer_id)
            results.append(result)
            print(f"✓  cta={result.get('cta','?')}")
        except Exception as e:
            print(f"✗  {e}")
            results.append({"test_id": test_id, "error": str(e)})
        await asyncio.sleep(1)  # Gemini free tier rate limit

    with open("submission.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = len([r for r in results if "body" in r])
    print(f"\n✅ Done! {success}/30 successful → submission.jsonl")

if __name__ == "__main__":
    asyncio.run(main())
