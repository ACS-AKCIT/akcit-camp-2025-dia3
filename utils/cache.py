"""
Utilitários de cache e limitação de taxa usando Redis.

Este módulo fornece funções para obter uma conexão com Redis, armazenar e
recuperar valores de cache, e implementar um simples controle de taxa
(rate limiting) por usuário.  O Redis funciona como um banco de dados
em memória extremamente rápido; ele suporta operações atômicas como
incremento de contadores e possui tipos de dados variados (strings,
listas, conjuntos, etc.).  Aqui usamos strings para armazenar
resultados serializados e contadores para controle de taxa.

Exemplo de uso:

>>> from utils.cache import get_or_set_cache
>>> result = get_or_set_cache('metrics:PETR4:1y', lambda: calcula_metricas())

Isso tenta recuperar a chave no Redis; se não existir, chama
`calcula_metricas()` e armazena o valor com TTL definido.

Nota: Para usar este módulo, certifique‑se de que um servidor Redis
esteja acessível e que as variáveis REDIS_HOST e REDIS_PORT estejam
definidas no arquivo `.env`.
"""
import json
import os
import time
from typing import Any, Callable

try:
    import redis  # type: ignore
except Exception:
    redis = None  # type: ignore
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback: se python-dotenv não estiver disponível, as variáveis
    # de ambiente devem estar definidas externamente.
    pass


_in_memory_store = {}


class InMemoryRedis:
    def get(self, key: str):
        item = _in_memory_store.get(key)
        if not item:
            return None
        value, expiry = item
        if expiry is not None and time.time() > expiry:
            _in_memory_store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ex=None) -> None:
        expiry = time.time() + ex if ex else None
        _in_memory_store[key] = (value, expiry)

    def incr(self, key: str) -> int:
        current = self.get(key)
        try:
            num = int(current) if current is not None else 0
        except Exception:
            num = 0
        num += 1
        self.set(key, str(num))
        return num

    def expire(self, key: str, seconds: int) -> None:
        item = _in_memory_store.get(key)
        if not item:
            return
        value, _ = item
        _in_memory_store[key] = (value, time.time() + seconds)


_in_memory_singleton = InMemoryRedis()


def get_redis_connection():
    """Obtém uma conexão Redis ou fallback em memória se FAKE_CACHE=1 ou sem redis.

    Retorna:
        objeto compatível com Redis (get, set, incr, expire).
    """
    if os.getenv("FAKE_CACHE") == "1" or redis is None:
        return _in_memory_singleton
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    return redis.Redis(host=host, port=port, password=os.getenv("REDIS_PASSWORD"), decode_responses=True)


def get_or_set_cache(key: str, func: Callable[[], Any], ttl: int = 86400) -> Any:
    """Obtém um valor do cache ou calcula e armazena se ausente.

    Este padrão é conhecido como *cache aside*: primeiro tenta ler o valor
    do cache; se não existir, executa a função fornecida, armazena o
    resultado com um tempo de vida (TTL) e retorna o valor.

    Args:
        key (str): chave no Redis.
        func (Callable[[], Any]): função que gera o valor se a chave
            não existir.
        ttl (int, opcional): tempo em segundos para expiração.  Padrão 24h.

    Returns:
        Any: o valor obtido ou calculado.
    """
    r = get_redis_connection()
    value = r.get(key)
    if value is not None:
        try:
            # Tenta desserializar JSON; se falhar, retorna string
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    # Valor não encontrado; calcula e armazena
    result = func()
    try:
        serialized = json.dumps(result)
    except (TypeError, ValueError):
        # Se não serializável em JSON, armazena como string
        serialized = str(result)
    r.set(key, serialized, ex=ttl)
    return result


def check_rate_limit(user_id: str, limit: int = 5, window: int = 60) -> None:
    """Aplica limitação de taxa para chamadas do usuário.

    Incrementa um contador no Redis com chave composta por usuário e
    janela de tempo.  Se o contador exceder o limite, lança uma
    exceção.  A chave expira automaticamente ao final da janela para
    reiniciar a contagem.

    Args:
        user_id (str): identificador único do usuário (pode ser ID de
            sessão ou endereço IP).
        limit (int): número máximo de chamadas permitidas na janela.
        window (int): tamanho da janela em segundos (padrão 1 minuto).

    Raises:
        Exception: se o limite for excedido.
    """
    r = get_redis_connection()
    current_window = int(time.time() // window)
    key = f"rate:{user_id}:{current_window}"
    count = r.incr(key)
    if count == 1:
        # Define expiração apenas na primeira chamada da janela
        r.expire(key, window)
    if count > limit:
        raise Exception(
            "Você excedeu o número máximo de requisições permitidas. Tente novamente mais tarde."
        )