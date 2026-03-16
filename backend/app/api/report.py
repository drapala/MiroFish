"""
Rotas de API de relatório
Fornece interfaces para geração, obtenção e conversa de relatórios de simulação
"""

import os
import traceback
import threading
from flask import request, jsonify, send_file

from . import report_bp
from ..config import Config
from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
from ..services.simulation_manager import SimulationManager
from ..models.project import ProjectManager
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger('mirofish.api.report')


# ============== Interface de geração de relatório ==============

@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    Gerar relatório de análise de simulação (tarefa assíncrona)

    Esta é uma operação demorada, a interface retorna imediatamente o task_id,
    use GET /api/report/generate/status para consultar o progresso

    Requisição (JSON):
        {
            "simulation_id": "sim_xxxx",    // Obrigatório, ID da simulação
            "force_regenerate": false        // Opcional, forçar regeneração
        }

    Retorno:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "task_id": "task_xxxx",
                "status": "generating",
                "message": "Tarefa de geração de relatório iniciada"
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça o simulation_id"
            }), 400

        force_regenerate = data.get('force_regenerate', False)

        # Obter informações da simulação
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulação não encontrada: {simulation_id}"
            }), 404

        # Verificar se já existe relatório
        if not force_regenerate:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "message": "Relatório já existe",
                        "already_generated": True
                    }
                })

        # Obter informações do projeto
        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Projeto não encontrado: {state.project_id}"
            }), 404

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "ID do grafo ausente, certifique-se de que o grafo foi construído"
            }), 400

        simulation_requirement = project.simulation_requirement
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Descrição do requisito de simulação ausente"
            }), 400

        # Gerar report_id antecipadamente para retornar ao frontend imediatamente
        import uuid
        report_id = f"report_{uuid.uuid4().hex[:12]}"

        # Criar tarefa assíncrona
        task_manager = TaskManager()
        task_id = task_manager.create_task(
            task_type="report_generate",
            metadata={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "report_id": report_id
            }
        )

        # Definir tarefa em segundo plano
        def run_generate():
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=0,
                    message="Inicializando Report Agent..."
                )

                # Criar Report Agent
                agent = ReportAgent(
                    graph_id=graph_id,
                    simulation_id=simulation_id,
                    simulation_requirement=simulation_requirement
                )

                # Callback de progresso
                def progress_callback(stage, progress, message):
                    task_manager.update_task(
                        task_id,
                        progress=progress,
                        message=f"[{stage}] {message}"
                    )

                # Gerar relatório (passando report_id pré-gerado)
                report = agent.generate_report(
                    progress_callback=progress_callback,
                    report_id=report_id
                )

                # Salvar relatório
                ReportManager.save_report(report)

                if report.status == ReportStatus.COMPLETED:
                    task_manager.complete_task(
                        task_id,
                        result={
                            "report_id": report.report_id,
                            "simulation_id": simulation_id,
                            "status": "completed"
                        }
                    )
                else:
                    task_manager.fail_task(task_id, report.error or "Falha na geração do relatório")

            except Exception as e:
                logger.error(f"Falha na geração do relatório: {str(e)}")
                task_manager.fail_task(task_id, str(e))

        # Iniciar thread em segundo plano
        thread = threading.Thread(target=run_generate, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "report_id": report_id,
                "task_id": task_id,
                "status": "generating",
                "message": "Tarefa de geração de relatório iniciada, consulte o progresso em /api/report/generate/status",
                "already_generated": False
            }
        })

    except Exception as e:
        logger.error(f"Falha ao iniciar tarefa de geração de relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/generate/status', methods=['POST'])
def get_generate_status():
    """
    Consultar progresso da tarefa de geração de relatório

    Requisição (JSON):
        {
            "task_id": "task_xxxx",         // Opcional, task_id retornado por generate
            "simulation_id": "sim_xxxx"     // Opcional, ID da simulação
        }

    Retorno:
        {
            "success": true,
            "data": {
                "task_id": "task_xxxx",
                "status": "processing|completed|failed",
                "progress": 45,
                "message": "..."
            }
        }
    """
    try:
        data = request.get_json() or {}

        task_id = data.get('task_id')
        simulation_id = data.get('simulation_id')

        # Se simulation_id foi fornecido, verificar primeiro se já existe relatório concluído
        if simulation_id:
            existing_report = ReportManager.get_report_by_simulation(simulation_id)
            if existing_report and existing_report.status == ReportStatus.COMPLETED:
                return jsonify({
                    "success": True,
                    "data": {
                        "simulation_id": simulation_id,
                        "report_id": existing_report.report_id,
                        "status": "completed",
                        "progress": 100,
                        "message": "Relatório já gerado",
                        "already_completed": True
                    }
                })

        if not task_id:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça task_id ou simulation_id"
            }), 400

        task_manager = TaskManager()
        task = task_manager.get_task(task_id)

        if not task:
            return jsonify({
                "success": False,
                "error": f"Tarefa não encontrada: {task_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": task.to_dict()
        })

    except Exception as e:
        logger.error(f"Falha ao consultar estado da tarefa: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============== Interface de obtenção de relatório ==============

@report_bp.route('/<report_id>', methods=['GET'])
def get_report(report_id: str):
    """
    Obter detalhes do relatório

    Retorno:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "simulation_id": "sim_xxxx",
                "status": "completed",
                "outline": {...},
                "markdown_content": "...",
                "created_at": "...",
                "completed_at": "..."
            }
        }
    """
    try:
        report = ReportManager.get_report(report_id)

        if not report:
            return jsonify({
                "success": False,
                "error": f"Relatório não encontrado: {report_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": report.to_dict()
        })

    except Exception as e:
        logger.error(f"Falha ao obter relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/by-simulation/<simulation_id>', methods=['GET'])
def get_report_by_simulation(simulation_id: str):
    """
    Obter relatório por ID da simulação

    Retorno:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                ...
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)

        if not report:
            return jsonify({
                "success": False,
                "error": f"Esta simulação ainda não possui relatório: {simulation_id}",
                "has_report": False
            }), 404

        return jsonify({
            "success": True,
            "data": report.to_dict(),
            "has_report": True
        })

    except Exception as e:
        logger.error(f"Falha ao obter relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/list', methods=['GET'])
def list_reports():
    """
    Listar todos os relatórios

    Parâmetros de Query:
        simulation_id: Filtrar por ID da simulação (opcional)
        limit: Limite de quantidade retornada (padrão 50)

    Retorno:
        {
            "success": true,
            "data": [...],
            "count": 10
        }
    """
    try:
        simulation_id = request.args.get('simulation_id')
        limit = request.args.get('limit', 50, type=int)

        reports = ReportManager.list_reports(
            simulation_id=simulation_id,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": [r.to_dict() for r in reports],
            "count": len(reports)
        })

    except Exception as e:
        logger.error(f"Falha ao listar relatórios: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/download', methods=['GET'])
def download_report(report_id: str):
    """
    Baixar relatório (formato Markdown)

    Retorna arquivo Markdown
    """
    try:
        report = ReportManager.get_report(report_id)

        if not report:
            return jsonify({
                "success": False,
                "error": f"Relatório não encontrado: {report_id}"
            }), 404

        md_path = ReportManager._get_report_markdown_path(report_id)

        if not os.path.exists(md_path):
            # Se o arquivo MD não existir, gerar um arquivo temporário
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write(report.markdown_content)
                temp_path = f.name

            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"{report_id}.md"
            )

        return send_file(
            md_path,
            as_attachment=True,
            download_name=f"{report_id}.md"
        )

    except Exception as e:
        logger.error(f"Falha ao baixar relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>', methods=['DELETE'])
def delete_report(report_id: str):
    """Excluir relatório"""
    try:
        success = ReportManager.delete_report(report_id)

        if not success:
            return jsonify({
                "success": False,
                "error": f"Relatório não encontrado: {report_id}"
            }), 404

        return jsonify({
            "success": True,
            "message": f"Relatório excluído: {report_id}"
        })

    except Exception as e:
        logger.error(f"Falha ao excluir relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de conversa com Report Agent ==============

@report_bp.route('/chat', methods=['POST'])
def chat_with_report_agent():
    """
    Conversar com o Report Agent

    O Report Agent pode chamar autonomamente ferramentas de busca para responder perguntas

    Requisição (JSON):
        {
            "simulation_id": "sim_xxxx",        // Obrigatório, ID da simulação
            "message": "Explique a tendência da opinião pública",    // Obrigatório, mensagem do usuário
            "chat_history": [                   // Opcional, histórico de conversa
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."}
            ]
        }

    Retorno:
        {
            "success": true,
            "data": {
                "response": "Resposta do Agent...",
                "tool_calls": [lista de ferramentas chamadas],
                "sources": [fontes de informação]
            }
        }
    """
    try:
        data = request.get_json() or {}

        simulation_id = data.get('simulation_id')
        message = data.get('message')
        chat_history = data.get('chat_history', [])

        if not simulation_id:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça o simulation_id"
            }), 400

        if not message:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça a message"
            }), 400

        # Obter informações de simulação e projeto
        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)

        if not state:
            return jsonify({
                "success": False,
                "error": f"Simulação não encontrada: {simulation_id}"
            }), 404

        project = ProjectManager.get_project(state.project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Projeto não encontrado: {state.project_id}"
            }), 404

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            return jsonify({
                "success": False,
                "error": "ID do grafo ausente"
            }), 400

        simulation_requirement = project.simulation_requirement or ""

        # Criar Agent e conversar
        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement
        )

        result = agent.chat(message=message, chat_history=chat_history)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"Falha na conversa: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de progresso e seções do relatório ==============

@report_bp.route('/<report_id>/progress', methods=['GET'])
def get_report_progress(report_id: str):
    """
    Obter progresso de geração do relatório (em tempo real)

    Retorno:
        {
            "success": true,
            "data": {
                "status": "generating",
                "progress": 45,
                "message": "Gerando seção: Descobertas principais",
                "current_section": "Descobertas principais",
                "completed_sections": ["Resumo executivo", "Contexto da simulação"],
                "updated_at": "2025-12-09T..."
            }
        }
    """
    try:
        progress = ReportManager.get_progress(report_id)

        if not progress:
            return jsonify({
                "success": False,
                "error": f"Relatório não encontrado ou informação de progresso indisponível: {report_id}"
            }), 404

        return jsonify({
            "success": True,
            "data": progress
        })

    except Exception as e:
        logger.error(f"Falha ao obter progresso do relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/sections', methods=['GET'])
def get_report_sections(report_id: str):
    """
    Obter lista de seções já geradas (saída por seção)

    O frontend pode fazer polling nesta interface para obter conteúdo das seções geradas,
    sem precisar esperar o relatório inteiro ser concluído

    Retorno:
        {
            "success": true,
            "data": {
                "report_id": "report_xxxx",
                "sections": [
                    {
                        "filename": "section_01.md",
                        "section_index": 1,
                        "content": "## Resumo executivo\\n\\n..."
                    },
                    ...
                ],
                "total_sections": 3,
                "is_complete": false
            }
        }
    """
    try:
        sections = ReportManager.get_generated_sections(report_id)

        # Obter estado do relatório
        report = ReportManager.get_report(report_id)
        is_complete = report is not None and report.status == ReportStatus.COMPLETED

        return jsonify({
            "success": True,
            "data": {
                "report_id": report_id,
                "sections": sections,
                "total_sections": len(sections),
                "is_complete": is_complete
            }
        })

    except Exception as e:
        logger.error(f"Falha ao obter lista de seções: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/section/<int:section_index>', methods=['GET'])
def get_single_section(report_id: str, section_index: int):
    """
    Obter conteúdo de uma única seção

    Retorno:
        {
            "success": true,
            "data": {
                "filename": "section_01.md",
                "content": "## Resumo executivo\\n\\n..."
            }
        }
    """
    try:
        section_path = ReportManager._get_section_path(report_id, section_index)

        if not os.path.exists(section_path):
            return jsonify({
                "success": False,
                "error": f"Seção não encontrada: section_{section_index:02d}.md"
            }), 404

        with open(section_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return jsonify({
            "success": True,
            "data": {
                "filename": f"section_{section_index:02d}.md",
                "section_index": section_index,
                "content": content
            }
        })

    except Exception as e:
        logger.error(f"Falha ao obter conteúdo da seção: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de verificação de estado do relatório ==============

@report_bp.route('/check/<simulation_id>', methods=['GET'])
def check_report_status(simulation_id: str):
    """
    Verificar se a simulação possui relatório e seu estado

    Usado pelo frontend para determinar se a funcionalidade de Interview está desbloqueada

    Retorno:
        {
            "success": true,
            "data": {
                "simulation_id": "sim_xxxx",
                "has_report": true,
                "report_status": "completed",
                "report_id": "report_xxxx",
                "interview_unlocked": true
            }
        }
    """
    try:
        report = ReportManager.get_report_by_simulation(simulation_id)

        has_report = report is not None
        report_status = report.status.value if report else None
        report_id = report.report_id if report else None

        # Interview só é desbloqueado após o relatório ser concluído
        interview_unlocked = has_report and report.status == ReportStatus.COMPLETED

        return jsonify({
            "success": True,
            "data": {
                "simulation_id": simulation_id,
                "has_report": has_report,
                "report_status": report_status,
                "report_id": report_id,
                "interview_unlocked": interview_unlocked
            }
        })

    except Exception as e:
        logger.error(f"Falha ao verificar estado do relatório: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de log do Agent ==============

@report_bp.route('/<report_id>/agent-log', methods=['GET'])
def get_agent_log(report_id: str):
    """
    Obter log detalhado de execução do Report Agent

    Obtém em tempo real cada passo de ação durante a geração do relatório, incluindo:
    - Início do relatório, início/conclusão do planejamento
    - Início de cada seção, chamadas de ferramentas, respostas do LLM, conclusão
    - Conclusão ou falha do relatório

    Parâmetros de Query:
        from_line: A partir de qual linha começar a leitura (opcional, padrão 0, para obtenção incremental)

    Retorno:
        {
            "success": true,
            "data": {
                "logs": [
                    {
                        "timestamp": "2025-12-13T...",
                        "elapsed_seconds": 12.5,
                        "report_id": "report_xxxx",
                        "action": "tool_call",
                        "stage": "generating",
                        "section_title": "Resumo executivo",
                        "section_index": 1,
                        "details": {
                            "tool_name": "insight_forge",
                            "parameters": {...},
                            ...
                        }
                    },
                    ...
                ],
                "total_lines": 25,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)

        log_data = ReportManager.get_agent_log(report_id, from_line=from_line)

        return jsonify({
            "success": True,
            "data": log_data
        })

    except Exception as e:
        logger.error(f"Falha ao obter log do Agent: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/agent-log/stream', methods=['GET'])
def stream_agent_log(report_id: str):
    """
    Obter log completo do Agent (obtenção única de tudo)

    Retorno:
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 25
            }
        }
    """
    try:
        logs = ReportManager.get_agent_log_stream(report_id)

        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })

    except Exception as e:
        logger.error(f"Falha ao obter log do Agent: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de log do console ==============

@report_bp.route('/<report_id>/console-log', methods=['GET'])
def get_console_log(report_id: str):
    """
    Obter log de saída do console do Report Agent

    Obtém em tempo real a saída do console durante a geração do relatório (INFO, WARNING etc.),
    diferente da interface agent-log que retorna logs JSON estruturados,
    este é um log em formato de texto puro estilo console.

    Parâmetros de Query:
        from_line: A partir de qual linha começar a leitura (opcional, padrão 0, para obtenção incremental)

    Retorno:
        {
            "success": true,
            "data": {
                "logs": [
                    "[19:46:14] INFO: Busca concluída: encontrados 15 fatos relevantes",
                    "[19:46:14] INFO: Busca no grafo: graph_id=xxx, query=...",
                    ...
                ],
                "total_lines": 100,
                "from_line": 0,
                "has_more": false
            }
        }
    """
    try:
        from_line = request.args.get('from_line', 0, type=int)

        log_data = ReportManager.get_console_log(report_id, from_line=from_line)

        return jsonify({
            "success": True,
            "data": log_data
        })

    except Exception as e:
        logger.error(f"Falha ao obter log do console: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/<report_id>/console-log/stream', methods=['GET'])
def stream_console_log(report_id: str):
    """
    Obter log completo do console (obtenção única de tudo)

    Retorno:
        {
            "success": true,
            "data": {
                "logs": [...],
                "count": 100
            }
        }
    """
    try:
        logs = ReportManager.get_console_log_stream(report_id)

        return jsonify({
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        })

    except Exception as e:
        logger.error(f"Falha ao obter log do console: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de ferramentas (para depuração) ==============

@report_bp.route('/tools/search', methods=['POST'])
def search_graph_tool():
    """
    Interface de ferramenta de busca no grafo (para depuração)

    Requisição (JSON):
        {
            "graph_id": "mirofish_xxxx",
            "query": "consulta de busca",
            "limit": 10
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get('graph_id')
        query = data.get('query')
        limit = data.get('limit', 10)

        if not graph_id or not query:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça graph_id e query"
            }), 400

        from ..services.zep_tools import ZepToolsService

        tools = ZepToolsService()
        result = tools.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit
        )

        return jsonify({
            "success": True,
            "data": result.to_dict()
        })

    except Exception as e:
        logger.error(f"Falha na busca no grafo: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@report_bp.route('/tools/statistics', methods=['POST'])
def get_graph_statistics_tool():
    """
    Interface de ferramenta de estatísticas do grafo (para depuração)

    Requisição (JSON):
        {
            "graph_id": "mirofish_xxxx"
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get('graph_id')

        if not graph_id:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça o graph_id"
            }), 400

        from ..services.zep_tools import ZepToolsService

        tools = ZepToolsService()
        result = tools.get_graph_statistics(graph_id)

        return jsonify({
            "success": True,
            "data": result
        })

    except Exception as e:
        logger.error(f"Falha ao obter estatísticas do grafo: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
