"""
Gerenciamento de configuração
Carrega configurações de forma unificada a partir do arquivo .env no diretório raiz do projeto
"""

import os
from dotenv import load_dotenv

# Carregar arquivo .env do diretório raiz do projeto
# Caminho: MiroFish/.env (relativo a backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # Se não houver .env no diretório raiz, tentar carregar variáveis de ambiente (para ambiente de produção)
    load_dotenv(override=True)


class Config:
    """Classe de configuração Flask"""

    # Configuração Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    # Configuração JSON - desabilitar escape ASCII, permitir exibição direta de caracteres (em vez do formato \uXXXX)
    JSON_AS_ASCII = False
    
    # Configuração LLM (formato OpenAI unificado)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Configuração Zep
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # Configuração de upload de arquivos
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # Configuração de processamento de texto
    DEFAULT_CHUNK_SIZE = 500  # Tamanho padrão do bloco
    DEFAULT_CHUNK_OVERLAP = 50  # Tamanho padrão da sobreposição
    
    # Configuração de simulação OASIS
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # Configuração de ações disponíveis na plataforma OASIS
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Configuração do Report Agent
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls):
        """Validar configurações necessárias"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY não configurada")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY não configurada")
        return errors

