"""Definição da CrewAI para o fluxo Finance Advisor.

Converte os agentes manuais (`insight_generator`, `advisor`, etc.)
em Agents/Tasks CrewAI mantendo integrações existentes (cache, LLM).
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Any

# Fix para SQLite antigo - CrewAI depende do ChromaDB que precisa do SQLite 3.35+
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

try:
    from crewai import Agent, Task, Crew, LLM
except Exception:  # pragma: no cover - fallback em ambientes sem crewai
    Agent = object  # type: ignore
    Task = object  # type: ignore
    Crew = object  # type: ignore
    LLM = object  # type: ignore

from .tools import (
    fetch_brapi_data_tool, calc_dividend_metrics_tool, redis_get, get_metrics_from_cache,
    rank_tickers_by_dividend_yield, generate_dividend_pdf
)


def get_llm(provider: str = "gemini"):
    """Configura o LLM para usar Gemini ou OpenAI.
    
    Args:
        provider: "gemini" (padrão) ou "openai"
    """
    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY não configurada no .env")
        
        return LLM(
            model="gemini/gemini-2.5-flash",
            api_key=api_key,
            temperature=0.7,
        )
    
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY não configurada no .env")
        
        return LLM(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.7,
        )
    
    else:
        raise ValueError(f"Provider '{provider}' não suportado. Use 'gemini' ou 'openai'.")


def build_insight_prompt(metrics: Dict[str, float], ticker: str, context: list[str]) -> str:
    lines: list[str] = []
    lines.append(
        f"Você é um analista de dividendos especializado. Analise os dados de dividendos da empresa {ticker}."
    )
    if context:
        lines.append("Contexto relevante de conversas anteriores:\n" + "\n".join(context))
    
    # Formata as métricas de forma mais legível
    dividend_yield = metrics.get("dividend_yield", 0)
    preco_atual = metrics.get("preco_atual", 0)
    dividendos_12m = metrics.get("dividendos_12m", 0)
    qtd_pagamentos = int(metrics.get("quantidade_pagamentos", 0))
    
    lines.append("\n=== MÉTRICAS DE DIVIDENDOS ===")
    lines.append(f"• Dividend Yield (últimos 12 meses): {dividend_yield:.2f}%")
    lines.append(f"• Preço Atual: R$ {preco_atual:.2f}")
    lines.append(f"• Total de Dividendos (12 meses): R$ {dividendos_12m:.2f}")
    lines.append(f"• Quantidade de Pagamentos: {qtd_pagamentos}")
    lines.append("")
    lines.append("Com base nesses dados de dividendos, forneça insights sobre:")
    lines.append("1. A consistência dos pagamentos de dividendos")
    lines.append("2. A atratividade do dividend yield atual")
    lines.append("3. A regularidade e frequência dos pagamentos")
    lines.append("\nResponda em português de forma concisa e objetiva.")
    return "\n".join(lines)


def build_advisor_prompt(ticker: str, periodo: str, metrics: Dict[str, float], insights: str, context: list[str]) -> str:
    lines: list[str] = []
    lines.append(
        f"Você atua como um analista de dividendos sênior. Analise a empresa {ticker} no período {periodo}."
    )
    if context:
        lines.append("Contexto de conversas anteriores:\n" + "\n".join(context))
    
    lines.append("\n=== INSIGHTS DE DIVIDENDOS ===")
    lines.append(insights)
    
    # Formata as métricas
    dividend_yield = metrics.get("dividend_yield", 0)
    preco_atual = metrics.get("preco_atual", 0)
    dividendos_12m = metrics.get("dividendos_12m", 0)
    qtd_pagamentos = int(metrics.get("quantidade_pagamentos", 0))
    
    lines.append("\n=== MÉTRICAS DE DIVIDENDOS ===")
    lines.append(f"• Dividend Yield (últimos 12 meses): {dividend_yield:.2f}%")
    lines.append(f"• Preço Atual: R$ {preco_atual:.2f}")
    lines.append(f"• Total de Dividendos (12 meses): R$ {dividendos_12m:.2f}")
    lines.append(f"• Quantidade de Pagamentos: {qtd_pagamentos}")
    
    lines.append("\n=== CRITÉRIO DE RECOMENDAÇÃO ===")
    lines.append("Regra: Se o Dividend Yield for ACIMA DE 7% ao ano, RECOMENDE COMPRA.")
    lines.append("       Se for ABAIXO DE 7% ao ano, NÃO recomende compra.")
    lines.append("")
    
    # Indica claramente se está acima ou abaixo do threshold
    if dividend_yield > 7.0:
        lines.append(f"✓ O dividend yield de {dividend_yield:.2f}% está ACIMA de 7%. Recomende COMPRA.")
    else:
        lines.append(f"✗ O dividend yield de {dividend_yield:.2f}% está ABAIXO de 7%. NÃO recomende compra.")
    
    lines.append("")
    lines.append("Com base nesses dados, escreva uma recomendação clara (COMPRAR, MANTER ou VENDER) em português.")
    lines.append("Justifique sua decisão de forma concisa, focando no dividend yield e na qualidade dos pagamentos.")
    return "\n".join(lines)


def create_finance_crew(ticker: str, periodo: str, llm_provider: str = "gemini") -> Crew:
    """Cria a Crew com quatro agentes: Data, Métricas, Insight e Advisor.
    
    Args:
        ticker: Código da ação
        periodo: Período de análise
        llm_provider: "gemini" (padrão) ou "openai"
    """
    llm = get_llm(llm_provider)
    
    data_agent = Agent(
        role="Ingestor de Dados",
        goal=f"Buscar dados da brapi.dev para {ticker} período {periodo}",
        backstory="Profissional focado em coleta de dados robusta e resiliente.",
        tools=[fetch_brapi_data_tool, redis_get],
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )

    metrics_agent = Agent(
        role="Calculador de Métricas de Dividendos",
        goal="Calcular dividend yield e métricas relacionadas a dividendos a partir dos dados",
        backstory="Analista quantitativo especializado em análise de dividendos que calcula dividend yield dos últimos 12 meses.",
        tools=[calc_dividend_metrics_tool],
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )

    insight_agent = Agent(
        role="Analista de Dividendos",
        goal="Gerar insights sobre dividendos baseados em métricas",
        backstory=(
            "Especialista em análise de dividendos que avalia a consistência,"
            " regularidade e atratividade dos pagamentos de dividendos."
        ),
        tools=[get_metrics_from_cache],
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )

    advisor_agent = Agent(
        role="Consultor de Dividendos",
        goal="Recomendar compra se dividend yield > 7% ao ano",
        backstory=(
            "Consultor especializado em investimentos focados em dividendos."
            " Recomenda COMPRA quando dividend yield ultrapassa 7% ao ano,"
            " considerando também a consistência dos pagamentos."
        ),
        tools=[get_metrics_from_cache],
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )

    data_task = Task(
        description=f"Use a ferramenta fetch_brapi_data_tool passando ticker='{ticker}' e periodo='{periodo}' para buscar e salvar os dados no cache.",
        expected_output=f"Mensagem confirmando que os dados de {ticker} foram salvos no cache",
        agent=data_agent,
    )

    metrics_task = Task(
        description=(
            f"Use a ferramenta calc_dividend_metrics_tool passando ticker='{ticker}' e periodo='{periodo}' "
            f"para ler os dados do cache e calcular dividend yield e outras métricas. Retorne o JSON de métricas."
        ),
        expected_output="JSON string com métricas: dividend_yield, preco_atual, dividendos_12m, quantidade_pagamentos",
        agent=metrics_agent,
        context=[data_task],
    )

    insight_task = Task(
        description=(
            f"1. Use get_metrics_from_cache(ticker='{ticker}', periodo='{periodo}') para obter as métricas de dividendos. "
            f"2. Analise: dividend_yield, consistência dos pagamentos, regularidade. "
            f"3. Crie uma análise em português sobre a qualidade dos dividendos."
        ),
        expected_output="Texto em português analisando os dividendos da empresa",
        agent=insight_agent,
        context=[metrics_task],
    )

    advisor_task = Task(
        description=(
            f"1. Use get_metrics_from_cache(ticker='{ticker}', periodo='{periodo}') para obter as métricas. "
            f"2. REGRA CRÍTICA: Se dividend_yield > 7%, recomende COMPRA. Caso contrário, NÃO recomende compra. "
            f"3. Crie uma recomendação clara (COMPRAR/MANTER/VENDER) em português, "
            f"justificando com base no dividend yield e qualidade dos pagamentos."
        ),
        expected_output="Recomendação final em português (COMPRAR se DY > 7%)",
        agent=advisor_agent,
        context=[metrics_task, insight_task],
    )

    crew = Crew(
        agents=[data_agent, metrics_agent, insight_agent, advisor_agent],
        tasks=[data_task, metrics_task, insight_task, advisor_task],
        verbose=True,
    )
    return crew


def run_insights(ticker: str, periodo: str, metrics: Dict[str, float]) -> str:
    """Executa apenas a tarefa de insights usando as ferramentas com cache."""
    cache_key = f"insights:{ticker}:{periodo}"
    prompt = build_insight_prompt(metrics, ticker, [])
    insights = cache_get_or_compute.run(cache_key, compute_prompt=prompt)  # type: ignore[attr-defined]
    return str(insights)


def run_recommendation(ticker: str, periodo: str, metrics: Dict[str, float], insights: str) -> str:
    """Executa apenas a tarefa de recomendação usando as ferramentas com cache."""
    cache_key = f"recommendation:{ticker}:{periodo}"
    prompt = build_advisor_prompt(ticker, periodo, metrics, insights, [])
    texto = cache_get_or_compute.run(cache_key, compute_prompt=prompt)  # type: ignore[attr-defined]
    return str(texto)


def create_multi_ticker_crew(tickers: list[str], periodo: str, llm_provider: str = "gemini") -> Crew:
    """
    Cria uma Crew que analisa múltiplos tickers, compara e gera PDF.
    
    Fluxo:
    1. Para cada ticker: Data -> Métricas
    2. Comparador: Cria ranking por dividend yield
    3. Gerador de PDF: Cria relatório profissional
    
    Args:
        tickers: Lista de tickers a analisar (ex: ["PETR4", "VALE3", "ITUB4", "BBDC4"])
        periodo: Período de análise
        llm_provider: "gemini" (padrão) ou "openai"
    """
    llm = get_llm(llm_provider)
    
    all_agents = []
    all_tasks = []
    
    # Cria agentes de data e métricas para cada ticker
    for ticker in tickers:
        data_agent = Agent(
            role=f"Ingestor de Dados - {ticker}",
            goal=f"Buscar dados da brapi.dev para {ticker} período {periodo}",
            backstory=f"Especialista em coleta de dados de {ticker}.",
            tools=[fetch_brapi_data_tool],
            verbose=True,
            allow_delegation=False,
            llm=llm,
        )
        
        metrics_agent = Agent(
            role=f"Calculador de Métricas - {ticker}",
            goal=f"Calcular dividend yield para {ticker}",
            backstory=f"Analista quantitativo especializado em dividendos de {ticker}.",
            tools=[calc_dividend_metrics_tool],
            verbose=True,
            allow_delegation=False,
            llm=llm,
        )
        
        data_task = Task(
            description=f"Use fetch_brapi_data_tool com ticker='{ticker}' e periodo='{periodo}'",
            expected_output=f"Confirmação de que dados de {ticker} foram salvos",
            agent=data_agent,
        )
        
        metrics_task = Task(
            description=f"Use calc_dividend_metrics_tool com ticker='{ticker}' e periodo='{periodo}'",
            expected_output=f"JSON com métricas de dividendos de {ticker}",
            agent=metrics_agent,
            context=[data_task],
        )
        
        all_agents.extend([data_agent, metrics_agent])
        all_tasks.extend([data_task, metrics_task])
    
    # Agente Comparador
    comparator_agent = Agent(
        role="Comparador de Dividendos",
        goal="Comparar dividend yields e criar ranking de recomendações",
        backstory=(
            "Especialista em análise comparativa de ações que identifica as melhores "
            "oportunidades de investimento focado em dividendos."
        ),
        tools=[rank_tickers_by_dividend_yield],
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )
    
    tickers_str = ",".join(tickers)
    comparator_task = Task(
        description=(
            f"1. Use rank_tickers_by_dividend_yield com tickers_list='{tickers_str}' e periodo='{periodo}' "
            f"2. Analise o ranking retornado e identifique as melhores oportunidades "
            f"3. Retorne o JSON do ranking completo"
        ),
        expected_output="JSON com ranking ordenado por dividend yield",
        agent=comparator_agent,
        context=all_tasks,  # Depende de todas as tarefas de métricas
    )
    
    # Agente Gerador de PDF
    pdf_agent = Agent(
        role="Gerador de Relatórios",
        goal="Criar relatório PDF profissional com análise comparativa",
        backstory=(
            "Especialista em comunicação financeira que transforma análises técnicas "
            "em relatórios visuais claros e profissionais."
        ),
        tools=[generate_dividend_pdf],
        verbose=True,
        allow_delegation=False,
        llm=llm,
    )
    
    pdf_task = Task(
        description=(
            f"1. Receba o ranking JSON da tarefa anterior "
            f"2. Use generate_dividend_pdf passando o ranking como 'content' "
            f"3. Use o nome de arquivo 'ranking_dividendos_{periodo}.pdf' "
            f"4. Retorne a mensagem de sucesso com o caminho do arquivo"
        ),
        expected_output="Caminho do arquivo PDF gerado",
        agent=pdf_agent,
        context=[comparator_task],
    )
    
    all_agents.extend([comparator_agent, pdf_agent])
    all_tasks.extend([comparator_task, pdf_task])
    
    crew = Crew(
        agents=all_agents,
        tasks=all_tasks,
        verbose=True,
    )
    
    return crew


