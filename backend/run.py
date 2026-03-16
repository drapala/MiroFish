"""
MiroFish Backend - Ponto de entrada de inicialização
"""

import os
import sys

# Resolver problema de caracteres ilegíveis no console do Windows: configurar codificação UTF-8 antes de todas as importações
if sys.platform == 'win32':
    # Configurar variável de ambiente para garantir que Python use UTF-8
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    # Reconfigurar fluxos de saída padrão para UTF-8
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Adicionar diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config


def main():
    """Função principal"""
    # Validar configuração
    errors = Config.validate()
    if errors:
        print("Erro de configuração:")
        for err in errors:
            print(f"  - {err}")
        print("\nPor favor, verifique a configuração no arquivo .env")
        sys.exit(1)
    
    # Criar aplicação
    app = create_app()
    
    # Obter configuração de execução
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG
    
    # Iniciar serviço
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()

