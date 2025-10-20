"""
Finance Advisor - Dividend Analyst
Análise multi-ticker de dividendos com geração de PDF
"""
from .core.orchestrator import analyze_multi_tickers


def main():
    """Executa análises comparativas de dividendos para diferentes carteiras."""
    
    # Configuração
    periodo = "1y"
    llm_provider = "openai"  # ou "gemini"
    
    # Combinações de análise
    carteiras = [
        {
            "nome": "Blue Chips",
            "tickers": ["PETR4", "VALE3", "ITUB4", "BBDC4"]
        },
        {
            "nome": "Utilities + Energia",
            "tickers": ["ELET3", "ENBR3", "TAEE11", "CPLE6"]
        },
        {
            "nome": "Top Dividendos",
            "tickers": ["PETR4", "VALE3", "BBAS3"]
        }
    ]
    
    # Executa análises
    for carteira in carteiras:
        print(f"\n{'='*80}")
        print(f"📊 ANÁLISE: {carteira['nome']}")
        print(f"{'='*80}\n")
        
        try:
            pdf_path = analyze_multi_tickers(
                tickers=carteira["tickers"],
                periodo=periodo,
                user_question=f"Análise de dividendos - {carteira['nome']}",
                user_id="batch_analysis",
                llm_provider=llm_provider
            )
            print(f"\n✅ Análise concluída!")
            print(f"📄 PDF: {pdf_path}\n")
            
        except Exception as e:
            print(f"\n❌ Erro na análise de {carteira['nome']}: {e}\n")


if __name__ == "__main__":
    main()