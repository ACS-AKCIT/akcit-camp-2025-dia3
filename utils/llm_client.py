"""
Cliente para chamada ao modelo de linguagem (LLM) Gemini.

Este módulo encapsula a configuração e a utilização do SDK
`google-generativeai` para acessar a API Gemini.  Especificamente, usamos
o modelo "gemini-2.5-flash" ou outro especificado via variável de
ambiente.  A chave de API deve ser definida na variável
`GEMINI_API_KEY` no `.env`.

Para mais detalhes sobre o SDK, consulte a documentação oficial da
Google.  O método `generate_content` abaixo envia um prompt de texto e
retorna a resposta do modelo como string.
"""
import os
from typing import List, Optional

try:
    from dotenv import load_dotenv
    # Carrega variáveis do .env se a biblioteca estiver disponível
    load_dotenv()
except ImportError:
    # Se python-dotenv não estiver instalado, ignoramos.  As variáveis
    # de ambiente devem estar configuradas por outros meios.
    load_dotenv = lambda *args, **kwargs: None  # type: ignore

# A importação do SDK do Google Gen AI pode falhar se a biblioteca não
# estiver instalada ou se não houver conectividade.  Certifique‑se de
# incluir `google-generativeai` em requirements.txt.
try:
    import google.generativeai as genai
except ImportError:
    genai = None

load_dotenv()


def _configure() -> None:
    """Configura a biblioteca genai com a chave do .env se ainda não foi feita."""
    # Modo fake para bootcamp/testes offline
    if os.getenv("FAKE_LLM") == "1":
        return
    if genai is None:
        raise ImportError(
            "O pacote google-generativeai não está instalado. Adicione-o ao requirements.txt."
        )
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "A chave GEMINI_API_KEY não foi definida. Crie um arquivo .env com sua chave."
        )
    # Configura a API key apenas uma vez.  O SDK mantém estado global.
    genai.configure(api_key=api_key)


def generate_content(prompt: str, model_name: Optional[str] = None) -> str:
    """Gera conteúdo de texto usando o modelo Gemini.

    Args:
        prompt (str): entrada de texto (pode incluir contexto recuperado via RAG).
        model_name (str, opcional): nome do modelo.  Se None, usa
            'gemini-2.5-flash'.

    Returns:
        str: texto gerado pelo modelo.

    Levanta:
        Exception: se ocorrer erro durante a chamada à API.
    """
    _configure()
    if os.getenv("FAKE_LLM") == "1":
        return f"[FAKE_LLM] Resposta gerada a partir do prompt:\n{prompt[:400]}..."
    model_name = model_name or "gemini-2.5-flash"
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return response.text
    except Exception as exc:
        raise RuntimeError(f"Erro ao chamar o modelo Gemini: {exc}") from exc


def chat_with_history(messages: List[dict], model_name: Optional[str] = None) -> str:
    """Envia uma lista de mensagens para o modelo Gemini em formato de chat.

    Args:
        messages (List[dict]): mensagens no formato
            [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}, ...]
        model_name (str, opcional): nome do modelo (padrão gemini-2.5-flash).
    Returns:
        str: a resposta gerada pelo modelo.

    Observação: esta função é fornecida como exemplo de chat
    multi-turn.  Use quando precisar fornecer histórico de conversa ao
    modelo.  O SDK do Gemini aceita esse formato.
    """
    _configure()
    if os.getenv("FAKE_LLM") == "1":
        return "[FAKE_LLM] Chat simulado com histórico (mensagens truncadas)."
    model_name = model_name or "gemini-2.5-flash"
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(messages)
        return response.text
    except Exception as exc:
        raise RuntimeError(f"Erro no chat com o modelo Gemini: {exc}") from exc