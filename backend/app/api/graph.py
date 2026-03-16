"""
Rotas de API relacionadas ao grafo
Utiliza mecanismo de contexto de projeto, com estado persistido no servidor
"""

import os
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# Obter logger
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """Verificar se a extensão do arquivo é permitida"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Interface de gerenciamento de projetos ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    Obter detalhes do projeto
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": f"Projeto não encontrado: {project_id}"
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    Listar todos os projetos
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)

    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    Excluir projeto
    """
    success = ProjectManager.delete_project(project_id)

    if not success:
        return jsonify({
            "success": False,
            "error": f"Projeto não encontrado ou falha ao excluir: {project_id}"
        }), 404

    return jsonify({
        "success": True,
        "message": f"Projeto excluído: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    Redefinir estado do projeto (para reconstruir o grafo)
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": f"Projeto não encontrado: {project_id}"
        }), 404

    # Redefinir para o estado de ontologia já gerada
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return jsonify({
        "success": True,
        "message": f"Projeto redefinido: {project_id}",
        "data": project.to_dict()
    })


# ============== Interface 1: Upload de arquivos e geração de ontologia ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    Interface 1: Upload de arquivos, análise e geração de definição de ontologia

    Método de requisição: multipart/form-data

    Parâmetros:
        files: Arquivos enviados (PDF/MD/TXT), podem ser múltiplos
        simulation_requirement: Descrição dos requisitos de simulação (obrigatório)
        project_name: Nome do projeto (opcional)
        additional_context: Informações adicionais (opcional)

    Retorno:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== Iniciando geração de definição de ontologia ===")

        # Obter parâmetros
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')

        logger.debug(f"Nome do projeto: {project_name}")
        logger.debug(f"Requisito de simulação: {simulation_requirement[:100]}...")

        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça a descrição do requisito de simulação (simulation_requirement)"
            }), 400

        # Obter arquivos enviados
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "Por favor, envie pelo menos um arquivo de documento"
            }), 400

        # Criar projeto
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"Projeto criado: {project.project_id}")

        # Salvar arquivos e extrair texto
        document_texts = []
        all_text = ""

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # Salvar arquivo no diretório do projeto
                file_info = ProjectManager.save_file_to_project(
                    project.project_id,
                    file,
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })

                # Extrair texto
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "Nenhum documento foi processado com sucesso, verifique o formato dos arquivos"
            }), 400

        # Salvar texto extraído
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Extração de texto concluída, total de {len(all_text)} caracteres")

        # Gerar ontologia
        logger.info("Chamando LLM para gerar definição de ontologia...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )

        # Salvar ontologia no projeto
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"Ontologia gerada: {entity_count} tipos de entidade, {edge_count} tipos de relação")

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== Geração de ontologia concluída === ID do projeto: {project.project_id}")

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface 2: Construção do grafo ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    Interface 2: Construir grafo com base no project_id

    Requisição (JSON):
        {
            "project_id": "proj_xxxx",  // Obrigatório, vindo da Interface 1
            "graph_name": "Nome do grafo",    // Opcional
            "chunk_size": 500,          // Opcional, padrão 500
            "chunk_overlap": 50         // Opcional, padrão 50
        }

    Retorno:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "Tarefa de construção do grafo iniciada"
            }
        }
    """
    try:
        logger.info("=== Iniciando construção do grafo ===")

        # Verificar configuração
        errors = []
        if not Config.ZEP_API_KEY:
            errors.append("ZEP_API_KEY não configurada")
        if errors:
            logger.error(f"Erro de configuração: {errors}")
            return jsonify({
                "success": False,
                "error": "Erro de configuração: " + "; ".join(errors)
            }), 500

        # Analisar requisição
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"Parâmetros da requisição: project_id={project_id}")

        if not project_id:
            return jsonify({
                "success": False,
                "error": "Por favor, forneça o project_id"
            }), 400

        # Obter projeto
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Projeto não encontrado: {project_id}"
            }), 404

        # Verificar estado do projeto
        force = data.get('force', False)  # Forçar reconstrução

        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "O projeto ainda não gerou a ontologia, por favor chame /ontology/generate primeiro"
            }), 400

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "O grafo está em construção, não reenvie. Para forçar reconstrução, adicione force: true",
                "task_id": project.graph_build_task_id
            }), 400

        # Se forçar reconstrução, redefinir estado
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        # Obter configuração
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

        # Atualizar configuração do projeto
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        # Obter texto extraído
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "Conteúdo de texto extraído não encontrado"
            }), 400

        # Obter ontologia
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "Definição de ontologia não encontrada"
            }), 400

        # Criar tarefa assíncrona
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"Construir grafo: {graph_name}")
        logger.info(f"Tarefa de construção do grafo criada: task_id={task_id}, project_id={project_id}")

        # Atualizar estado do projeto
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        # Iniciar tarefa em segundo plano
        def build_task():
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] Iniciando construção do grafo...")
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    message="Inicializando serviço de construção do grafo..."
                )

                # Criar serviço de construção do grafo
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)

                # Dividir em blocos
                task_manager.update_task(
                    task_id,
                    message="Dividindo texto em blocos...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text,
                    chunk_size=chunk_size,
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)

                # Criar grafo
                task_manager.update_task(
                    task_id,
                    message="Criando grafo Zep...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)

                # Atualizar graph_id do projeto
                project.graph_id = graph_id
                ProjectManager.save_project(project)

                # Configurar ontologia
                task_manager.update_task(
                    task_id,
                    message="Configurando definição de ontologia...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)

                # Adicionar texto (assinatura do progress_callback é (msg, progress_ratio))
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )

                task_manager.update_task(
                    task_id,
                    message=f"Iniciando adição de {total_chunks} blocos de texto...",
                    progress=15
                )

                episode_uuids = builder.add_text_batches(
                    graph_id,
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )

                # Aguardar processamento do Zep (consultar status processed de cada episode)
                task_manager.update_task(
                    task_id,
                    message="Aguardando processamento de dados pelo Zep...",
                    progress=55
                )

                def wait_progress_callback(msg, progress_ratio):
                    progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )

                builder._wait_for_episodes(episode_uuids, wait_progress_callback)

                # Obter dados do grafo
                task_manager.update_task(
                    task_id,
                    message="Obtendo dados do grafo...",
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)

                # Atualizar estado do projeto
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)

                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] Construção do grafo concluída: graph_id={graph_id}, nós={node_count}, arestas={edge_count}")

                # Concluído
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="Construção do grafo concluída",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )

            except Exception as e:
                # Atualizar estado do projeto para falha
                build_logger.error(f"[{task_id}] Falha na construção do grafo: {str(e)}")
                build_logger.debug(traceback.format_exc())

                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"Falha na construção: {str(e)}",
                    error=traceback.format_exc()
                )

        # Iniciar thread em segundo plano
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "Tarefa de construção do grafo iniciada, consulte o progresso em /task/{task_id}"
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface de consulta de tarefas ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    Consultar estado da tarefa
    """
    task = TaskManager().get_task(task_id)

    if not task:
        return jsonify({
            "success": False,
            "error": f"Tarefa não encontrada: {task_id}"
        }), 404

    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    Listar todas as tarefas
    """
    tasks = TaskManager().list_tasks()

    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== Interface de dados do grafo ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    Obter dados do grafo (nós e arestas)
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY não configurada"
            }), 500

        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data = builder.get_graph_data(graph_id)

        return jsonify({
            "success": True,
            "data": graph_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    Excluir grafo Zep
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY não configurada"
            }), 500

        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)

        return jsonify({
            "success": True,
            "message": f"Grafo excluído: {graph_id}"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
