import logging
from typing import Dict, Any, Optional
from app.config import settings
# from app.services.model_registry import ModelRegistry # Annahme: ModelRegistry existiert

logger = logging.getLogger(__name__)

# Dummy ModelRegistry für das Beispiel
class ModelRegistry:
    def get_model_info(self, provider_id: str) -> Optional[Dict[str, Any]]:
        if provider_id == settings.LLM_DEFAULT:
            return {"model_id": settings.GPT_OSS_MODEL_ID, "api_base": settings.GPT_OSS_API_BASE, "api_key": settings.GPT_OSS_API_KEY}
        elif provider_id == settings.LLM_HEAVY:
            return {"model_id": settings.DEEPSEEK_MODEL_ID, "api_base": settings.DEEPSEEK_API_BASE, "api_key": settings.DEEPSEEK_API_KEY}
        elif provider_id == settings.OPENROUTER_MODEL_ID:
            return {"model_id": settings.OPENROUTER_MODEL_ID, "api_base": settings.OPENROUTER_API_BASE, "api_key": settings.OPENROUTER_API_KEY}
        return None

class LLMRouter:
    def __init__(self, model_registry: ModelRegistry):
        self.model_registry = model_registry
        self.policy_rules = [
            {
                "when": lambda task, messages: task in ['arch', 'longform', 'security_review'] or self._is_long_text(messages),
                "use": settings.LLM_HEAVY,
                "max_tokens": 3500,
                "timeout_ms": settings.DEEPSEEK_TIMEOUT_MS,
                "provider_base": settings.DEEPSEEK_API_BASE,
                "api_key": settings.DEEPSEEK_API_KEY,
                "model_id": settings.DEEPSEEK_MODEL_ID,
                "fallback": settings.LLM_DEFAULT # Fallback to default if heavy fails
            },
            {
                "when": lambda task, messages: task in ['chat', 'small_fix', 'summarize'],
                "use": settings.LLM_DEFAULT,
                "max_tokens": 1200,
                "timeout_ms": settings.GPT_OSS_TIMEOUT_MS,
                "provider_base": settings.GPT_OSS_API_BASE,
                "api_key": settings.GPT_OSS_API_KEY,
                "model_id": settings.GPT_OSS_MODEL_ID,
                "fallback": settings.OPENROUTER_MODEL_ID # Fallback to OpenRouter if default fails
            },
            {
                "when": lambda task, messages: "latency_critical" in task, # Annahme: task kann auch Tags enthalten
                "use": settings.OPENROUTER_MODEL_ID,
                "max_tokens": 900,
                "timeout_ms": settings.OPENROUTER_TIMEOUT_MS,
                "provider_base": settings.OPENROUTER_API_BASE,
                "api_key": settings.OPENROUTER_API_KEY,
                "model_id": settings.OPENROUTER_MODEL_ID,
                "fallback": settings.LLM_DEFAULT
            }
            # Weitere Regeln hier hinzufügen, z.B. für ZukiJourney oder Ollama
        ]

    def _is_long_text(self, messages: list[Dict[str, Any]]) -> bool:
        # Einfache Heuristik: Zähle die Gesamtzeichen in den Nachrichten
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars > 1000 # Beispiel: Als "Langtext" gilt alles über 1000 Zeichen

    async def route_llm_request(self, task: str, messages: list[Dict[str, Any]], user_options: Dict[str, Any]) -> Dict[str, Any]:
        chosen_rule = None
        for rule in self.policy_rules:
            if rule["when"](task, messages):
                chosen_rule = rule
                break

        if not chosen_rule:
            # Fallback to default if no specific rule matches
            logger.warning(f"No specific LLM routing rule matched for task '{task}'. Falling back to default.")
            chosen_rule = {
                "use": settings.LLM_DEFAULT,
                "max_tokens": 1200,
                "timeout_ms": settings.GPT_OSS_TIMEOUT_MS,
                "provider_base": settings.GPT_OSS_API_BASE,
                "api_key": settings.GPT_OSS_API_KEY,
                "model_id": settings.GPT_OSS_MODEL_ID,
                "fallback": None
            }

        # Merge user options with chosen rule defaults
        final_options = {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": chosen_rule.get("max_tokens"),
            "timeout_ms": chosen_rule.get("timeout_ms"),
            **user_options
        }

        provider_id = chosen_rule["use"]
        model_info = self.model_registry.get_model_info(provider_id) # Annahme: ModelRegistry kann Infos liefern

        if not model_info:
            logger.error(f"Model info not found for provider_id: {provider_id}. Falling back to default.")
            provider_id = settings.LLM_DEFAULT
            model_info = self.model_registry.get_model_info(provider_id)
            if not model_info:
                raise ValueError(f"Default LLM '{settings.LLM_DEFAULT}' not found in registry.")

        return {
            "provider_id": provider_id,
            "model_id": chosen_rule.get("model_id") or model_info.get("model_id"), # Use rule's specific model_id if present
            "api_base": chosen_rule.get("provider_base") or model_info.get("api_base"),
            "api_key": chosen_rule.get("api_key") or model_info.get("api_key"),
            "options": final_options,
            "fallback_provider_id": chosen_rule.get("fallback")
        }
