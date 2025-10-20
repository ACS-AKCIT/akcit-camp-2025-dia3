"""
🏦 Finance Advisor - Dividend Analyst
Análise comparativa de dividendos com IA multi-agente
"""
import streamlit as st
import os
from pathlib import Path

# Import do orquestrador
from core.orchestrator import analyze_multi_tickers

# Configuração da página
st.set_page_config(
    page_title="Dividend Analyst",
    page_icon="💰",
    layout="wide"
)

# Título
st.title("💰 Dividend Analyst")
st.markdown("### Análise comparativa de dividendos com IA multi-agente")
st.divider()

# Lista de ações disponíveis (principais da B3)
ACOES_DISPONIVEIS = [
    "PETR4", "VALE3", "ITUB4", "BBDC4", "BBAS3",
    "ABEV3", "B3SA3", "RENT3", "ELET3", "ENBR3",
    "WEGE3", "SUZB3", "RAIL3", "JBSS3", "EMBR3",
    "CPLE6", "TAEE11", "CMIG4", "CSAN3", "VIVT3"
]

# Sidebar - Configurações
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Seleção de ações
    st.subheader("📊 Ações para Analisar")
    tickers_selecionados = st.multiselect(
        "Escolha de 2 a 6 ações:",
        options=sorted(ACOES_DISPONIVEIS),
        default=["PETR4", "VALE3", "ITUB4"],
        max_selections=6
    )
    
    # Período de análise
    st.subheader("📅 Período")
    periodo = st.selectbox(
        "Período de análise:",
        options=["1y", "6mo", "3mo", "2y"],
        index=0,
        format_func=lambda x: {
            "1y": "1 ano",
            "6mo": "6 meses",
            "3mo": "3 meses",
            "2y": "2 anos"
        }[x]
    )
    
    # Seleção do modelo
    st.subheader("🤖 Modelo de IA")
    llm_provider = st.radio(
        "Escolha o modelo:",
        options=["openai", "gemini"],
        index=0,
        format_func=lambda x: {
            "openai": "🟢 OpenAI (GPT-4o-mini)",
            "gemini": "🔵 Google Gemini Flash"
        }[x]
    )
    
    st.divider()
    
    # Info sobre APIs
    with st.expander("ℹ️ Informações"):
        st.caption("""
        **APIs necessárias:**
        - OpenAI: configure `OPENAI_API_KEY`
        - Gemini: configure `GEMINI_API_KEY`
        
        **O que o sistema faz:**
        1. Busca dados de dividendos
        2. Calcula dividend yield
        3. Compara e rankeia as ações
        4. Gera relatório PDF profissional
        """)

# Área principal
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🎯 Ações Selecionadas")
    if len(tickers_selecionados) >= 2:
        # Mostra as ações selecionadas
        cols = st.columns(min(len(tickers_selecionados), 4))
        for idx, ticker in enumerate(tickers_selecionados):
            with cols[idx % 4]:
                st.info(f"**{ticker}**")
    elif len(tickers_selecionados) == 1:
        st.warning("⚠️ Selecione pelo menos 2 ações para comparação")
    else:
        st.info("👈 Selecione as ações no menu lateral")

with col2:
    st.subheader("🚀 Executar")
    
    # Validação
    pode_executar = len(tickers_selecionados) >= 2
    
    if st.button(
        "▶️ Analisar Dividendos",
        type="primary",
        disabled=not pode_executar,
        use_container_width=True
    ):
        # Executa a análise
        with st.spinner(f"🔄 Analisando {len(tickers_selecionados)} ações..."):
            try:
                # Placeholder para progresso
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                progress_text.text("📊 Buscando dados das ações...")
                progress_bar.progress(20)
                
                # Executa análise
                resultado = analyze_multi_tickers(
                    tickers=tickers_selecionados,
                    periodo=periodo,
                    user_question=f"Análise comparativa de {', '.join(tickers_selecionados)}",
                    user_id="streamlit_user",
                    llm_provider=llm_provider
                )
                
                progress_bar.progress(100)
                progress_text.empty()
                progress_bar.empty()
                
                # Sucesso!
                st.success("✅ Análise concluída com sucesso!")
                
                # Extrai o caminho do PDF
                pdf_path = resultado.strip()
                
                # Mostra informações
                st.subheader("📄 Relatório Gerado")
                st.code(pdf_path, language=None)
                
                # Botão para baixar o PDF
                if os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as pdf_file:
                        pdf_bytes = pdf_file.read()
                        
                    st.download_button(
                        label="📥 Baixar Relatório PDF",
                        data=pdf_bytes,
                        file_name=f"analise_dividendos_{'_'.join(tickers_selecionados)}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
            except Exception as e:
                st.error(f"❌ Erro na análise: {str(e)}")
                with st.expander("🔍 Detalhes do erro"):
                    st.code(str(e))

# Rodapé
st.divider()
st.caption("💡 **Dica:** O dividend yield acima de 7% gera recomendação de COMPRA automaticamente.")
st.caption("🤖 Powered by CrewAI + OpenAI/Gemini + Brapi.dev")


