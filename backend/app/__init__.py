"""
MiroFish Backend - Fábrica de aplicação Flask
"""

import os
import warnings

# Suprimir avisos do resource_tracker do multiprocessing (originados de bibliotecas de terceiros como transformers)
# Precisa ser configurado antes de todas as outras importações
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

from flask import Flask, request
from flask_cors import CORS

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class=Config):
    """Função fábrica da aplicação Flask"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Configurar codificação JSON: garantir exibição direta de caracteres (em vez do formato \uXXXX)
    # Flask >= 2.3 usa app.json.ensure_ascii, versões anteriores usam configuração JSON_AS_ASCII
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False
    
    # Configurar logs
    logger = setup_logger('mirofish')
    
    # Imprimir informações de inicialização apenas no subprocesso do reloader (evitar impressão dupla no modo debug)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process
    
    if should_log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend iniciando...")
        logger.info("=" * 50)
    
    # Habilitar CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Registrar função de limpeza de processos de simulação (garantir encerramento de todos os processos de simulação ao desligar o servidor)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Função de limpeza de processos de simulação registrada")
    
    # Middleware de log de requisições
    @app.before_request
    def log_request():
        logger = get_logger('mirofish.request')
        logger.debug(f"Requisição: {request.method} {request.path}")
        if request.content_type and 'json' in request.content_type:
            logger.debug(f"Corpo da requisição: {request.get_json(silent=True)}")
    
    @app.after_request
    def log_response(response):
        logger = get_logger('mirofish.request')
        logger.debug(f"Resposta: {response.status_code}")
        return response
    
    # Registrar blueprints
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    
    # Verificação de saúde
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'MiroFish Backend'}
    
    if should_log_startup:
        logger.info("MiroFish Backend inicialização concluída")
    
    return app

