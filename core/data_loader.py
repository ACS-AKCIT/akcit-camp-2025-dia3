"""
Agente de ingestão de dados (DataLoader).

Este módulo contém funções relacionadas à obtenção de dados da API
brapi.dev. No fluxo simplificado, a ingestão é síncrona: buscamos o
JSON da brapi e podemos armazenar no Redis sob a chave
`rawdata:ticker:periodo` para reaproveitamento.

Para testes locais, chame `fetch_brapi_data` diretamente.
"""
import os
from typing import Any, Dict

import requests
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

from utils.cache import get_redis_connection

if load_dotenv:
    load_dotenv()


def build_brapi_url(ticker: str, periodo: str) -> str:
    """Monta a URL para a API brapi.dev com parâmetros de interesse.

    Usamos os parâmetros `range` e `fundamental=true` e
    `dividends=true` para obter dados de preço, dados fundamentais e
    dividendos, respectivamente.  Ajuste conforme as necessidades do
    projeto (ex.: adicionar módulos via parâmetro `modules`).
    """
    base_url = f"https://brapi.dev/api/quote/{ticker}"
    params = {
        "range": periodo,
        "fundamental": "true",
        "dividends": "true",
    }
    token = os.getenv("BRAPI_TOKEN")
    if token:
        params["token"] = token
    # Concatena parâmetros na URL
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base_url}?{query}"


def build_brapi_history_url(ticker: str, periodo: str) -> str:
    """Monta a URL do endpoint de histórico diário da brapi.dev.

    Ex.: https://brapi.dev/api/quote/PETR4?range=1y
    """
    base_url = f"https://brapi.dev/api/quote/{ticker}"
    params = {
        "range": periodo,
    }
    token = os.getenv("BRAPI_TOKEN")
    if token:
        params["token"] = token
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base_url}?{query}"


def fetch_brapi_data(ticker: str, periodo: str) -> Dict[str, Any]:
    """Faz uma requisição HTTP à brapi.dev e retorna o JSON.

    Esta função é utilizada pelo worker de ingestão.  Se preferir
    realizar testes locais sem filas, você pode chamá‑la diretamente.

    Args:
        ticker (str): código do ativo (ex.: 'PETR4').
        periodo (str): intervalo (ex.: '1mo', '1y').

    Returns:
        dict: resposta JSON da brapi
    """
    # Modo fake para bootcamp/testes offline
    if os.getenv("FAKE_DATA") == "1":
        return {
            "results": [
                {
                    "historicalDataPrice": [
                        {"close": 10.0},
                        {"close": 10.2},
                        {"close": 10.1},
                        {"close": 10.5},
                    ]
                }
            ]
        }
    url = build_brapi_url(ticker, periodo)
    # Headers para evitar erro 417 (Expectation Failed)
    headers = {
        'User-Agent': 'FinanceAdvisor/1.0',
        'Accept': 'application/json',
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    # Se a resposta não contém série histórica, tenta o endpoint /history e injeta em results[0]
    try:
        result0 = data.get("results", [])[0]
    except Exception:
        result0 = None
    has_history = False
    if isinstance(result0, dict):
        series = result0.get("historicalDataPrice") or result0.get("historicalData") or result0.get("prices")
        has_history = isinstance(series, list) and len(series) > 0
    if not has_history:
        hurl = build_brapi_history_url(ticker, periodo)
        hresp = requests.get(hurl, headers=headers)
        hresp.raise_for_status()
        hjson = hresp.json() or {}
        prices = hjson.get("prices") or hjson.get("historicalDataPrice") or []
        if isinstance(result0, dict):
            result0["prices"] = prices
        elif isinstance(data.get("results"), list) and data["results"]:
            data["results"][0] = {"prices": prices}
        else:
            data = {"results": [{"prices": prices}]}
    return data


def enqueue_ingestion(ticker: str, periodo: str) -> None:
    """Mantido por compatibilidade: não faz nada no fluxo síncrono."""
    return None


def get_rawdata_from_cache(ticker: str, periodo: str):
    """Recupera dados brutos do Redis se estiverem em cache.

    Args:
        ticker (str): código do ativo.
        periodo (str): intervalo.

    Returns:
        dict ou None: JSON se presente no cache ou None caso contrário.
    """
    r = get_redis_connection()
    key = f"rawdata:{ticker}:{periodo}"
    data = r.get(key)
    if data:
        import json
        return json.loads(data)
    return None