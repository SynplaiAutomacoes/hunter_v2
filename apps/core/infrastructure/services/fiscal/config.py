from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WebmaniaConfig:
    base_url: str = ""
    b2b_base_url: str = ""
    ambient: int = 2
    api_key: str = ""
    consumer_key: str = ""
    consumer_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    b2b_consumer_key: str = ""
    b2b_consumer_secret: str = ""
    b2b_access_token: str = ""
    b2b_access_token_secret: str = ""
    webhook_token: str = ""
    tax_class_base_url: str = ""
    nfe_consulta_endpoint: str = ""
    nfse_consulta_endpoint: str = ""
