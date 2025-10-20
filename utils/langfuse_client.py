import os
from dotenv import load_dotenv
from langfuse import get_client

load_dotenv()

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST=os.getenv("LANGFUSE_HOST", "http://localhost:3000")
  
def init_langfuse():
    """Inicializa o cliente Langfuse com as chaves do .env."""
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        print("⚠️  Aviso: LANGFUSE_PUBLIC_KEY e/ou LANGFUSE_SECRET_KEY não definidas.")
        print("   O tracing do Langfuse não estará disponível.")
        print("   Acesse http://localhost:3000 para criar um projeto e obter as chaves.")
        return None

    try:
        langfuse_client = get_client()
        
        # Tentativa de autenticação - não bloqueia se falhar
        try:
            if langfuse_client.auth_check():
                print("✅ Cliente Langfuse está autenticado e pronto!")
                return langfuse_client
            else:
                print("⚠️  Falha na autenticação do Langfuse. Verifique suas credenciais e host.")
                print("   A aplicação continuará funcionando sem tracing.")
                return None
        except Exception as auth_error:
            print(f"⚠️  Erro na autenticação do Langfuse: {auth_error}")
            print("   A aplicação continuará funcionando sem tracing.")
            print("   Acesse http://localhost:3000 para configurar o Langfuse e obter as chaves corretas.")
            return None
            
    except Exception as e:
        print(f"⚠️  Erro ao inicializar cliente Langfuse: {e}")
        print("   A aplicação continuará funcionando sem tracing.")
        return None
