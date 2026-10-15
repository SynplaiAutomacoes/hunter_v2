from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

ENGINE_PATTERN = re.compile(r"(?<!\d)(\d[.,]\d)(?!\d)")

_WEIGHT_MARCA = 15.0
_WEIGHT_MODELO = 35.0
_WEIGHT_VERSAO = 10.0
_WEIGHT_ANO = 10.0
_WEIGHT_COMBUSTIVEL = 15.0
_WEIGHT_MOTORIZACAO = 15.0
_WD_SCORE_BONUS = 5.0


def _norm(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value).split())


def _tokens(value: object) -> list[str]:
    return _norm(value).split()


def _extract_displacement(value: object) -> str:
    match = ENGINE_PATTERN.search(str(value or ""))
    if not match:
        return ""
    return match.group(1).replace(",", ".")


def parse_fipe_valor(texto_valor: object) -> Decimal | None:
    """Converte 'R$ 131.646,00' em Decimal."""
    cleaned = re.sub(r"[^\d.,]", "", str(texto_valor or "").strip())
    if not cleaned:
        return None
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _fuel_compatible(wd_fuel: str, candidate_fuel: str) -> bool:
    wd_tokens = set(_tokens(wd_fuel))
    candidate_tokens = set(_tokens(candidate_fuel))
    if not wd_tokens or not candidate_tokens:
        return False
    if wd_tokens == candidate_tokens or wd_tokens & candidate_tokens:
        return True
    flex_family = {"flex", "gasolina", "etanol", "alcool"}
    return bool((wd_tokens | candidate_tokens) <= flex_family or ("flex" in (wd_tokens | candidate_tokens) and bool((wd_tokens | candidate_tokens) & {"gasolina", "etanol", "alcool", "flex"})))


def _score_candidate(
    *,
    candidate: dict[str, Any],
    brand: str,
    model: str,
    version: str,
    year_model: str,
    fuel: str,
    engine_displacement: str,
) -> float:
    candidate_tokens = _tokens(candidate.get("texto_modelo"))
    model_tokens = _tokens(model)

    if brand and _norm(candidate.get("texto_marca")) != _norm(brand):
        marca_points = 0.0
    else:
        marca_points = _WEIGHT_MARCA

    candidate_year = str(candidate.get("ano_modelo") or "").strip()
    if year_model and candidate_year and candidate_year != str(year_model).strip():
        ano_points = 0.0
    else:
        ano_points = _WEIGHT_ANO

    f1 = 0.0
    if model_tokens and candidate_tokens:
        intersection = set(model_tokens) & set(candidate_tokens)
        f1 = (2 * len(intersection) / (len(model_tokens) + len(candidate_tokens))) if intersection else 0.0
    modelo_points = round(f1 * _WEIGHT_MODELO, 2)

    if version:
        versao_points = _WEIGHT_VERSAO if _norm(version) in candidate_tokens else 0.0
    else:
        versao_points = _WEIGHT_VERSAO / 2

    candidate_fuel = str(candidate.get("combustivel") or "")
    if not fuel or not candidate_fuel:
        combustivel_points = _WEIGHT_COMBUSTIVEL / 2 if (fuel or candidate_fuel) else 0.0
        if not fuel and not candidate_fuel:
            combustivel_points = _WEIGHT_COMBUSTIVEL / 2
    elif _norm(fuel) == _norm(candidate_fuel):
        combustivel_points = _WEIGHT_COMBUSTIVEL
    elif _fuel_compatible(fuel, candidate_fuel):
        combustivel_points = 8.0
    else:
        combustivel_points = 0.0

    candidate_displacement = _extract_displacement(candidate.get("texto_modelo"))
    if not engine_displacement or not candidate_displacement:
        motorizacao_points = _WEIGHT_MOTORIZACAO / 2
    elif engine_displacement == candidate_displacement:
        motorizacao_points = _WEIGHT_MOTORIZACAO
    else:
        motorizacao_points = 0.0

    try:
        wd_score = float(candidate.get("score") or 0)
    except (TypeError, ValueError):
        wd_score = 0.0
    wd_bonus = round(max(0.0, min(wd_score, 100.0)) / 100 * _WD_SCORE_BONUS, 2)

    total = marca_points + modelo_points + versao_points + ano_points + combustivel_points + motorizacao_points + wd_bonus
    return round(min(total, 100.0), 2)


def _passes_eliminatory(*, candidate: dict[str, Any], brand: str, model: str, year_model: str) -> bool:
    if brand and _norm(candidate.get("texto_marca")) != _norm(brand):
        return False
    candidate_year = str(candidate.get("ano_modelo") or "").strip()
    if year_model and candidate_year and candidate_year != str(year_model).strip():
        return False
    model_tokens = _tokens(model)
    if model_tokens and _tokens(candidate.get("texto_modelo")):
        family = model_tokens[0]
        if family not in _tokens(candidate.get("texto_modelo")):
            return False
    return True


def select_fipe_item(
    *,
    candidates: list[dict[str, Any]],
    brand: str = "",
    model: str = "",
    version: str = "",
    year_model: str = "",
    fuel: str = "",
    engine_displacement: str = "",
) -> tuple[dict[str, Any] | None, float]:
    """Seleciona o melhor item FIPE (eliminação + score 0-100 + desempate pelo 1º).

    Retorna (item, score). Em caso de empate, a ordem original vence ([0]).
    Se a eliminação zerar a lista, repete só com score (best effort).
    """
    items = [candidate for candidate in candidates if isinstance(candidate, dict)]
    if not items:
        return None, 0.0

    eligible = [candidate for candidate in items if _passes_eliminatory(candidate=candidate, brand=brand, model=model, year_model=year_model)]
    pool = eligible or items

    scored = [
        (
            _score_candidate(
                candidate=candidate,
                brand=brand,
                model=model,
                version=version,
                year_model=year_model,
                fuel=fuel,
                engine_displacement=engine_displacement,
            ),
            candidate,
        )
        for candidate in pool
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_item = scored[0]
    return best_item, best_score
