"""
Orquestrador do sistema de análise financeira.

Este módulo centraliza o fluxo de trabalho para atender às
solicitações do usuário.  Ele coordena as diferentes etapas:

* Limitação de taxa por usuário via Redis
* Ingestão de dados: envia mensagens para o worker de ingestão
* Cálculo de métricas: envia mensagens para o worker de métricas
* Geração de insights via LLM com suporte a RAG
* Geração da recomendação final

O orquestrador gerencia o cache: se dados ou métricas já
estiverem disponíveis em Redis, evita reenviar tarefas.  Ele também
realiza polling simples para aguardar a conclusão das etapas
assíncronas, com um timeout configurável.

Além disso, registra a interação (pergunta do usuário e resposta do
sistema) no banco vetorial para que o mecanismo RAG possa recuperar
contexto relevante nas próximas interações.

Uso típico::

    from agents.orchestrator import analyze
    resposta = analyze("PETR4", "1y", "Analise a empresa PETR4", user_id="alice")
    print(resposta)

Para aplicações reais, você pode integrar esta função com um
framework web (FastAPI, Flask, etc.) ou CLI para receber as
solicitações do usuário.
"""
import logging

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    load_dotenv = None  # type: ignore

from utils.cache import check_rate_limit
from crew.crew import create_finance_crew, create_multi_ticker_crew
from utils.langfuse_client import init_langfuse
from openinference.instrumentation.crewai import CrewAIInstrumentor
from openinference.instrumentation.litellm import LiteLLMInstrumentor

# Carrega variáveis do .env se a biblioteca estiver disponível
if load_dotenv:
    load_dotenv()

# Inicializa Langfuse para tracing e observabilidade
langfuse_client = init_langfuse()

# Somente instrumenta se o Langfuse estiver disponível
if langfuse_client:
    CrewAIInstrumentor().instrument(skip_dep_check=True)
    LiteLLMInstrumentor().instrument()


def analyze(ticker: str, periodo: str, user_question: str, user_id: str = "anon", llm_provider: str = "gemini") -> str:
    """Executa a análise completa para uma ação e período usando CrewAI.

    Este método orquestra todo o fluxo através da CrewAI: aplica rate limiting
    e delega todo o trabalho (busca de dados, cálculo de métricas, geração de
    insights e recomendação) para os agentes da Crew.

    Args:
        ticker (str): código do ativo (ex.: PETR4).
        periodo (str): intervalo (ex.: 1y, 6mo, 1mo etc.).
        user_question (str): pergunta original do usuário (para fins de
            armazenamento em memória vetorial).
        user_id (str): identificador único do usuário para
            rate limiting.
        llm_provider (str): "gemini" (padrão) ou "openai" para escolher o LLM.

    Returns:
        str: resposta combinando insights e recomendação gerados pela Crew.

    Raises:
        Exception: se exceder o limite de taxa ou se a Crew falhar.
    """
    # Verifica limite de requisições
    check_rate_limit(user_id)

    logging.info(f"Processando solicitação para {ticker} no período {periodo}")
    print(f"Processando solicitação para {ticker} no período {periodo}")

    # Cria e executa a Crew - AGENTES FAZEM TODO O TRABALHO
    try:
        crew = create_finance_crew(ticker, periodo, llm_provider)
        
        if langfuse_client:
            with langfuse_client.start_as_current_span(name="finance-crew-trace"):
                result = crew.kickoff()
        else:
            result = crew.kickoff()
        
        # O resultado pode ser string ou objeto CrewOutput
        if hasattr(result, 'raw'):
            resposta = str(result.raw)
        else:
            resposta = str(result)
            
    except Exception as e:
        logging.error(f"Erro ao executar Crew: {e}")
        raise Exception(f"Falha na análise via CrewAI: {e}")
    
    if langfuse_client:
        langfuse_client.flush()

    return resposta


def analyze_multi_tickers(tickers: list[str], periodo: str, user_question: str, 
                          user_id: str = "anon", llm_provider: str = "gemini") -> str:
    """Executa análise comparativa para múltiplos tickers usando CrewAI.

    Este método orquestra a análise de múltiplos tickers, compara os dividend yields
    e gera um PDF com o ranking de recomendações.

    Args:
        tickers (list[str]): lista de códigos de ativos (ex.: ["PETR4", "VALE3", "ITUB4", "BBDC4"]).
        periodo (str): intervalo (ex.: 1y, 6mo, 1mo etc.).
        user_question (str): pergunta original do usuário (para fins de
            armazenamento em memória vetorial).
        user_id (str): identificador único do usuário para
            rate limiting.
        llm_provider (str): "gemini" (padrão) ou "openai" para escolher o LLM.

    Returns:
        str: resposta com o ranking e caminho do PDF gerado.

    Raises:
        Exception: se exceder o limite de taxa ou se a Crew falhar.
    """
    # Verifica limite de requisições
    check_rate_limit(user_id)

    tickers_str = ", ".join(tickers)
    logging.info(f"Processando análise comparativa para {tickers_str} no período {periodo}")
    print(f"Processando análise comparativa para {tickers_str} no período {periodo}")

    # Cria e executa a Crew - AGENTES FAZEM TODO O TRABALHO
    try:
        crew = create_multi_ticker_crew(tickers, periodo, llm_provider)
        
        if langfuse_client:
            with langfuse_client.start_as_current_span(name="multi-ticker-crew-trace"):
                result = crew.kickoff()
        else:
            result = crew.kickoff()
        
        # O resultado pode ser string ou objeto CrewOutput
        if hasattr(result, 'raw'):
            resposta = str(result.raw)
        else:
            resposta = str(result)
            
    except Exception as e:
        logging.error(f"Erro ao executar Crew multi-ticker: {e}")
        raise Exception(f"Falha na análise comparativa via CrewAI: {e}")
    
    if langfuse_client:
        langfuse_client.flush()

    return resposta