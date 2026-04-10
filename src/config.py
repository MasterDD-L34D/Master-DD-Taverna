import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODULES_DIR = BASE_DIR / "modules"
DATA_DIR = BASE_DIR / "data"


class Settings:
    """Configurazione base caricata da variabili d'ambiente."""

    def __init__(self) -> None:
        self.api_key: str | None = os.getenv("API_KEY")
        self.allow_anonymous: bool = os.getenv("ALLOW_ANONYMOUS", "false").lower() in (
            "1",
            "true",
            "yes",
            "y",
        )
        self.allow_module_dump: bool = os.getenv(
            "ALLOW_MODULE_DUMP", "false"
        ).lower() in (
            "1",
            "true",
            "yes",
            "y",
        )  # se False, il testo dei moduli viene troncato
        self.module_dump_whitelist: set[str] = {
            name.strip()
            for name in os.getenv("MODULE_DUMP_WHITELIST", "").split(",")
            if name.strip()
        }
        self.auth_backoff_threshold: int = int(
            os.getenv("AUTH_BACKOFF_THRESHOLD", "5")
        )  # tentativi invalidi prima del backoff
        self.auth_backoff_seconds: int = int(
            os.getenv("AUTH_BACKOFF_SECONDS", "60")
        )  # finestra di backoff in secondi
        self.auth_backoff_state_ttl_seconds: int = int(
            os.getenv("AUTH_BACKOFF_STATE_TTL_SECONDS", "3600")
        )  # TTL per lo stato backoff in memoria
        self.auth_backoff_max_clients: int = int(
            os.getenv("AUTH_BACKOFF_MAX_CLIENTS", "10000")
        )  # numero massimo di client tracciati in memoria
        self.metrics_api_key: str | None = os.getenv("METRICS_API_KEY")
        self.metrics_ip_allowlist: list[str] = [
            ip.strip()
            for ip in os.getenv("METRICS_IP_ALLOWLIST", "").split(",")
            if ip.strip()
        ]
        self.trust_proxy_headers: bool = os.getenv(
            "TRUST_PROXY_HEADERS", "false"
        ).lower() in ("1", "true", "yes", "y")
        self.trusted_proxy_ips: list[str] = [
            ip.strip()
            for ip in os.getenv("TRUSTED_PROXY_IPS", "").split(",")
            if ip.strip()
        ]


settings = Settings()


ACCESS_POLICY_MATRIX = {
    "API_KEY": {
        "default": None,
        "scope": "Tutti gli endpoint applicativi protetti da require_api_key.",
        "effect": "Se ALLOW_ANONYMOUS=false, x-api-key deve combaciare con API_KEY.",
    },
    "ALLOW_ANONYMOUS": {
        "default": "false",
        "scope": "Autenticazione endpoint applicativi (escluso /metrics).",
        "effect": "Se true, bypassa API_KEY e resetta il tracker backoff per client.",
    },
    "ALLOW_MODULE_DUMP": {
        "default": "false",
        "scope": "GET/POST /modules/{name}",
        "effect": (
            "false: blocca dump non testuali e tronca i moduli testuali con header "
            "di contenuto parziale; true: abilita dump completo salvo moduli protetti "
            "non in whitelist."
        ),
    },
    "AUTH_BACKOFF_STATE_TTL_SECONDS": {
        "default": "3600",
        "scope": "Tracker in memoria dei tentativi falliti auth",
        "effect": (
            "Rimuove entry inattive oltre il TTL durante la lettura/scrittura "
            "del tracker, limitando crescita e retention dati in RAM."
        ),
    },
    "AUTH_BACKOFF_MAX_CLIENTS": {
        "default": "10000",
        "scope": "Tracker in memoria dei tentativi falliti auth",
        "effect": (
            "Impone un limite massimo di client tracciati; al superamento "
            "viene applicata eviction oldest-first basata su last_seen."
        ),
    },
    "METRICS_API_KEY": {
        "default": None,
        "scope": "GET /metrics",
        "effect": (
            "Se valorizzata, autorizza /metrics con x-api-key; anche API_KEY resta "
            "accettata come fallback."
        ),
    },
    "METRICS_IP_ALLOWLIST": {
        "default": "",
        "scope": "GET /metrics",
        "effect": (
            "CSV di IP consentiti su client host; include x-forwarded-for solo "
            "se TRUST_PROXY_HEADERS=true e proxy sorgente fidato."
        ),
    },
    "TRUST_PROXY_HEADERS": {
        "default": "false",
        "scope": "Risoluzione client IP e policy x-forwarded-for",
        "effect": (
            "Se true, accetta x-forwarded-for solo da proxy in TRUSTED_PROXY_IPS; "
            "se false usa sempre request.client.host."
        ),
    },
    "TRUSTED_PROXY_IPS": {
        "default": "",
        "scope": "Risoluzione client IP e policy x-forwarded-for",
        "effect": (
            "CSV di IP proxy fidati autorizzati a fornire x-forwarded-for; "
            "valori non validi o assenti vengono ignorati."
        ),
    },
}
