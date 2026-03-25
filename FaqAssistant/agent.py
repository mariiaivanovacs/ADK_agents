from dotenv import load_dotenv

load_dotenv()

import os
import re
import uuid
import random
from typing import Optional, Dict, Any, List, Tuple

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from firebase_admin import firestore
from firebase_db import db


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PRODUCT_CATALOG = {
    "prod_001": "SmartBudget Pro",
    "prod_002": "SmartBudget Basic",
    "prod_003": "SmartBudget Family",
    "prod_004": "SmartBudget Business",
    "prod_005": "SmartBudget Student",
}

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "6"))
MAX_RELEVANT_PRODUCTS = int(os.getenv("MAX_RELEVANT_PRODUCTS", "3"))
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "500"))

# In-memory cache for product documents so we do not hit Firestore on every turn
_PRODUCT_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    text = text or ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _extract_user_text(llm_request: LlmRequest) -> str:
    """
    Safely extracts the latest user text from the request.
    Supports multiple parts, not only the first one.
    """
    if not llm_request.contents:
        return ""

    for content in reversed(llm_request.contents):
        if getattr(content, "role", None) == "user":
            parts = getattr(content, "parts", []) or []
            texts = []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    texts.append(part_text)
            return _truncate(" ".join(texts), 1000)

    return ""


def _get_client_id(state: dict) -> str:
    """
    Stable client_id for the lifetime of the session.
    If you have a real authenticated user id, replace this logic.
    """
    if "_client_id" not in state:
        state["_client_id"] = str(uuid.uuid4())
    return state["_client_id"]


def _load_product_cache() -> Dict[str, Dict[str, Any]]:
    """
    Load all product documents once per process.
    Falls back to the product name from PRODUCT_CATALOG if a document is missing.
    """
    global _PRODUCT_CACHE

    if _PRODUCT_CACHE is not None:
        return _PRODUCT_CACHE

    cache: Dict[str, Dict[str, Any]] = {}

    for product_id, fallback_name in PRODUCT_CATALOG.items():
        doc = db.collection("products").document(product_id).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["name"] = data.get("name", fallback_name)
            cache[product_id] = data
        else:
            cache[product_id] = {"name": fallback_name}

    _PRODUCT_CACHE = cache
    return cache


def _build_catalog_summary(products: Dict[str, Dict[str, Any]]) -> str:
    """
    Compact list of available products.
    This is much smaller than dumping every field from every product.
    """
    lines = []
    for product_id, data in products.items():
        name = data.get("name", product_id)
        lines.append(f"- [{product_id}] {name}")
    return "\n".join(lines) if lines else "No products found."


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _find_relevant_products(user_text: str, products: Dict[str, Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Lightweight keyword matcher.
    We score products by overlap between the user's message and product name / fields.
    """
    if not user_text:
        return []

    user_tokens = set(_tokenize(user_text))
    scored: List[Tuple[int, str, Dict[str, Any]]] = []

    for product_id, data in products.items():
        name = str(data.get("name", ""))
        searchable_text = " ".join(
            [
                product_id,
                name,
                str(data.get("description", "")),
                str(data.get("features", "")),
                str(data.get("plan", "")),
                str(data.get("tier", "")),
                str(data.get("category", "")),
            ]
        ).lower()

        score = 0

        # Strong signal: exact substring of product name
        if name and name.lower() in user_text.lower():
            score += 10

        # Token overlap
        product_tokens = set(_tokenize(searchable_text))
        overlap = len(user_tokens & product_tokens)
        score += overlap

        # Small bonus if product id is mentioned
        if product_id.lower() in user_text.lower():
            score += 5

        if score > 0:
            scored.append((score, product_id, data))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(pid, data) for _, pid, data in scored[:MAX_RELEVANT_PRODUCTS]]


def _format_product_details(product_id: str, data: Dict[str, Any]) -> str:
    """
    Keep details compact. Only include non-empty fields.
    """
    lines = [f"[{product_id}] {data.get('name', product_id)}"]
    for key, value in data.items():
        if key == "name":
            continue
        if value is None or value == "":
            continue
        lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def _fetch_history(client_id: str) -> str:
    docs = (
        db.collection("conversations")
        .document(client_id)
        .collection("messages")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(MAX_HISTORY_MESSAGES)
        .stream()
    )

    history = []
    for doc in docs:
        data = doc.to_dict() or {}
        role = data.get("role", "unknown")
        message = _truncate(str(data.get("message", "")), MAX_MESSAGE_CHARS)
        history.append({"role": role, "message": message})

    history.reverse()

    if not history:
        return "No previous conversation history."

    lines = ["Previous conversation:"]
    for entry in history:
        lines.append(f"{entry['role'].capitalize()}: {entry['message']}")
    return "\n".join(lines)


def _ensure_demo_purchases(client_id: str) -> None:
    """
    Creates a demo purchase record only if none exists.
    This is useful for test/case scenarios and can be disabled with DEMO_MODE=false.
    """
    if not DEMO_MODE:
        return

    ref = db.collection("purchases").document(client_id)
    doc = ref.get()

    if doc.exists:
        data = doc.to_dict() or {}
        if data.get("product_ids"):
            return

    product_ids = list(PRODUCT_CATALOG.keys())
    purchased = random.sample(product_ids, k=random.randint(0, min(2, len(product_ids))))

    ref.set({
        "product_ids": purchased,
    }, merge=True)


def _fetch_purchases(client_id: str) -> str:
    doc = db.collection("purchases").document(client_id).get()
    if not doc.exists:
        return "No purchase records found."

    data = doc.to_dict() or {}
    purchased_ids = data.get("product_ids", [])

    if not purchased_ids:
        return "No products purchased yet."

    products = _load_product_cache()
    names = []
    for pid in purchased_ids:
        name = products.get(pid, {}).get("name") or PRODUCT_CATALOG.get(pid, pid)
        names.append(name)

    return "Purchased: " + ", ".join(names)


def _store_turn(client_id: str, user_message: str, agent_message: str) -> None:
    messages_ref = db.collection("conversations").document(client_id).collection("messages")
    batch = db.batch()

    for role, text in [("user", user_message), ("agent", agent_message)]:
        batch.set(
            messages_ref.document(),
            {
                "role": role,
                "message": text,
                "timestamp": firestore.SERVER_TIMESTAMP,
            },
        )

    batch.commit()


def _build_context_block(client_id: str, user_text: str) -> str:
    """
    Build only the minimal context that the model needs for this turn.
    """
    products = _load_product_cache()

    history_text = _fetch_history(client_id)
    catalog_summary = _build_catalog_summary(products)
    relevant_products = _find_relevant_products(user_text, products)

    if relevant_products:
        relevant_text = "\n\n".join(
            _format_product_details(product_id, data) for product_id, data in relevant_products
        )
    else:
        relevant_text = "No specific product matched the current user message."

    purchases_text = _fetch_purchases(client_id)

    return (
        f"--- Conversation History ---\n{history_text}\n\n"
        f"--- Product Catalog Summary ---\n{catalog_summary}\n\n"
        f"--- Relevant Product Details ---\n{relevant_text}\n\n"
        f"--- Client Purchases ---\n{purchases_text}"
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_BASE_INSTRUCTION = """You are an AI customer support agent for SmartBudget products.

Rules:
- Be concise, accurate, and helpful.
- Use the provided context only.
- If a product is not in the catalog context, say it was not found.
- If asked whether the client purchased a product, check the purchase context.
- If user asks for opinion or decision - provide one.
- If users asks unrelevant questions - kindly reject.
- Prefer the most relevant product details rather than repeating the whole catalog.
"""


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def before_model_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> Optional[object]:
    """
    Build a compact system instruction before the LLM call.
    """
    state = callback_context.state
    client_id = _get_client_id(state)

    user_text = _extract_user_text(llm_request)
    state["_user_message"] = user_text

    # Demo scenario: create purchases once if missing
    _ensure_demo_purchases(client_id)

    context_block = _build_context_block(client_id, user_text)

    if llm_request.config is not None:
        llm_request.config.system_instruction = f"{_BASE_INSTRUCTION}\n\n{context_block}"

    return None


def after_model_callback(
    callback_context: CallbackContext,
    llm_response,
) -> None:
    """
    Store the completed turn after the model replies.
    """
    if getattr(llm_response, "partial", False):
        return None

    agent_message = ""
    content = getattr(llm_response, "content", None)
    if content:
        for part in getattr(content, "parts", []) or []:
            agent_message += getattr(part, "text", "") or ""

    client_id = callback_context.state.get("_client_id", "")
    user_message = callback_context.state.get("_user_message", "")

    if client_id and user_message and agent_message:
        _store_turn(client_id, user_message, agent_message)

    return None


# ---------------------------------------------------------------------------
# Root agent
# ---------------------------------------------------------------------------

root_agent = Agent(
    name="faq_agent",
    model="gemini-2.5-flash",
    instruction=_BASE_INSTRUCTION,
    before_model_callback=before_model_callback,
    after_model_callback=after_model_callback,
)