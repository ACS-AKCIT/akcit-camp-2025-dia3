"""
Tools CrewAI que encapsulam integrações existentes (Redis cache e LLM).
Essas ferramentas serão chamadas por Agents/Tasks CrewAI.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.cache import get_or_set_cache, get_redis_connection
from utils.llm_client import generate_content

try:
    # Imports opcionais caso CrewAI não esteja instalado no ambiente do leitor
    from crewai.tools import tool
except Exception:  # pragma: no cover - fallback em ambientes sem crewai
    def tool(*dargs, **dkwargs):  # type: ignore
        # Suporta @tool e @tool("descricao")
        if dargs and callable(dargs[0]) and len(dargs) == 1 and not dkwargs:
            func = dargs[0]
            return _make_fake_tool(func)
        def decorator(func):
            return _make_fake_tool(func)
        return decorator

    def _make_fake_tool(func):  # type: ignore
        class FakeTool:
            def __init__(self, f):
                self._f = f
            def run(self, *args, **kwargs):
                return self._f(*args, **kwargs)
            def __call__(self, *args, **kwargs):
                return self._f(*args, **kwargs)
        return FakeTool(func)


@tool("Obtém valor do Redis ou calcula e armazena com TTL")
def cache_get_or_compute(key: str, compute_prompt: str = "") -> str:
    """
    Implementa o padrão cache-aside. Quando `compute_prompt` é fornecido,
    gera o conteúdo via LLM e o armazena; caso contrário retorna o valor bruto.
    """
    def _compute() -> Any:
        if not compute_prompt:
            return ""
        return generate_content(compute_prompt)

    result = get_or_set_cache(key, _compute)
    if isinstance(result, (dict, list)):
        import json as _json
        return _json.dumps(result)
    return str(result)


@tool("Lê string bruta de uma chave do Redis (sem JSON)")
def redis_get(key: str) -> str:
    """Retorna o valor cru (string) de uma chave no Redis sem desserializar JSON."""
    r = get_redis_connection()
    result = r.get(key)
    return result if result else ""


@tool("Busca dados da API brapi.dev e salva no cache")
def fetch_brapi_data_tool(ticker: str, periodo: str) -> str:
    """Busca dados brutos da brapi.dev e salva no Redis. Retorna mensagem de sucesso."""
    from core.data_loader import fetch_brapi_data
    import json
    
    data = fetch_brapi_data(ticker, periodo)
    
    # Salva no Redis
    r = get_redis_connection()
    cache_key = f"rawdata:{ticker}:{periodo}"
    r.set(cache_key, json.dumps(data, ensure_ascii=False), ex=86400)
    
    return f"Dados de {ticker} ({periodo}) salvos com sucesso no cache. Use a chave: {cache_key}"


@tool("Calcula métricas de dividendos lendo do cache")
def calc_dividend_metrics_tool(ticker: str, periodo: str) -> str:
    """Lê dados do cache e calcula dividend yield e outras métricas de dividendos."""
    from core.metrics_calculator import calc_metrics_from_raw
    import json
    
    # Lê do Redis
    r = get_redis_connection()
    cache_key = f"rawdata:{ticker}:{periodo}"
    cached_data = r.get(cache_key)
    
    if not cached_data:
        return json.dumps({"error": f"Dados não encontrados no cache para {ticker} {periodo}"})
    
    data = json.loads(cached_data)
    metrics = calc_metrics_from_raw(data)
    
    # Salva métricas no cache também
    metrics_key = f"metrics:{ticker}:{periodo}"
    r.set(metrics_key, json.dumps(metrics, ensure_ascii=False), ex=86400)
    
    return json.dumps(metrics, ensure_ascii=False)


@tool("Lê métricas de dividendos do cache")
def get_metrics_from_cache(ticker: str, periodo: str) -> str:
    """Recupera métricas de dividendos já calculadas do cache."""
    import json
    
    r = get_redis_connection()
    metrics_key = f"metrics:{ticker}:{periodo}"
    cached_metrics = r.get(metrics_key)
    
    if not cached_metrics:
        return json.dumps({"error": f"Métricas não encontradas no cache para {ticker} {periodo}"})
    
    return cached_metrics


@tool("Compara e rankeia tickers por dividend yield")
def rank_tickers_by_dividend_yield(tickers_list: str, periodo: str) -> str:
    """
    Compara múltiplos tickers e retorna um ranking ordenado por dividend yield.
    
    Args:
        tickers_list: String com tickers separados por vírgula (ex: "PETR4,VALE3,ITUB4,BBDC4")
        periodo: Período de análise
    
    Returns:
        JSON string com ranking ordenado por dividend yield (maior para menor)
    """
    import json
    
    tickers = [t.strip() for t in tickers_list.split(",")]
    r = get_redis_connection()
    
    ranking = []
    for ticker in tickers:
        metrics_key = f"metrics:{ticker}:{periodo}"
        cached_metrics = r.get(metrics_key)
        
        if cached_metrics:
            metrics = json.loads(cached_metrics)
            ranking.append({
                "ticker": ticker,
                "dividend_yield": metrics.get("dividend_yield", 0),
                "preco_atual": metrics.get("preco_atual", 0),
                "dividendos_12m": metrics.get("dividendos_12m", 0),
                "quantidade_pagamentos": int(metrics.get("quantidade_pagamentos", 0)),
                "recomendacao": "COMPRAR" if metrics.get("dividend_yield", 0) > 7.0 else "MANTER"
            })
    
    # Ordena por dividend yield (maior primeiro)
    ranking.sort(key=lambda x: x["dividend_yield"], reverse=True)
    
    return json.dumps(ranking, ensure_ascii=False, indent=2)


@tool("Gera PDF com análise de dividendos")
def generate_dividend_pdf(content: str, output_filename: str = "analise_dividendos.pdf") -> str:
    """
    Gera um PDF profissional com a análise de dividendos.
    
    Args:
        content: Conteúdo em texto para incluir no PDF
        output_filename: Nome do arquivo PDF a ser gerado
    
    Returns:
        Caminho completo do arquivo PDF gerado
    """
    import json
    import os
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    
    # Cria diretório de saída se não existir
    output_dir = os.path.join(os.getcwd(), "reports")
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, output_filename)
    
    # Cria o documento
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a5490'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1a5490'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=12
    )
    
    # Elementos do documento
    story = []
    
    # Título
    story.append(Paragraph("Análise de Dividendos", title_style))
    story.append(Paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 
                          styles['Normal']))
    story.append(Spacer(1, 0.5*cm))
    
    # Tenta parsear o conteúdo como JSON (ranking)
    try:
        ranking = json.loads(content)
        if isinstance(ranking, list) and ranking:
            # Cria tabela com o ranking
            story.append(Paragraph("Ranking de Ações por Dividend Yield", heading_style))
            story.append(Spacer(1, 0.3*cm))
            
            # Cabeçalho da tabela
            table_data = [[
                "Posição", "Ticker", "Dividend Yield", "Preço Atual", 
                "Dividendos 12M", "Pagamentos", "Recomendação"
            ]]
            
            # Dados da tabela
            for idx, item in enumerate(ranking, 1):
                table_data.append([
                    str(idx),
                    item.get("ticker", ""),
                    f"{item.get('dividend_yield', 0):.2f}%",
                    f"R$ {item.get('preco_atual', 0):.2f}",
                    f"R$ {item.get('dividendos_12m', 0):.2f}",
                    str(item.get('quantidade_pagamentos', 0)),
                    item.get('recomendacao', '')
                ])
            
            # Cria e estiliza a tabela
            t = Table(table_data, colWidths=[1.5*cm, 2*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2*cm, 2.5*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a5490')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ]))
            
            story.append(t)
            story.append(Spacer(1, 0.5*cm))
            
            # Destaque para a melhor opção
            best = ranking[0]
            story.append(Paragraph("🏆 Melhor Oportunidade", heading_style))
            best_text = f"""
            O ticker <b>{best.get('ticker', '')}</b> apresenta o melhor dividend yield 
            de <b>{best.get('dividend_yield', 0):.2f}%</b> ao ano, com preço atual de 
            R$ {best.get('preco_atual', 0):.2f} e {best.get('quantidade_pagamentos', 0)} 
            pagamentos nos últimos 12 meses, totalizando R$ {best.get('dividendos_12m', 0):.2f} 
            em dividendos.
            """
            story.append(Paragraph(best_text, normal_style))
            
    except json.JSONDecodeError:
        # Se não for JSON, trata como texto livre
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            if para.strip():
                story.append(Paragraph(para.strip(), normal_style))
                story.append(Spacer(1, 0.3*cm))
    
    # Rodapé
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        "<i>Relatório gerado automaticamente pelo Finance Advisor - Dividend Analyst</i>",
        styles['Normal']
    ))
    
    # Gera o PDF
    doc.build(story)
    
    return f"PDF gerado com sucesso: {output_path}"


