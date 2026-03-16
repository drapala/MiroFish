"""
Serviço de construção de grafos
Interface 2: Construção de Standalone Graph usando Zep API
"""

import os
import uuid
import time
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from zep_cloud.client import Zep
from zep_cloud import EpisodeData, EntityEdgeSourceTarget

from ..config import Config
from ..models.task import TaskManager, TaskStatus
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges
from .text_processor import TextProcessor


@dataclass
class GraphInfo:
    """Informações do grafo"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    Serviço de construção de grafos
    Responsável por chamar a API Zep para construir grafos de conhecimento
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY não configurada")
        
        self.client = Zep(api_key=self.api_key)
        self.task_manager = TaskManager()
    
    def build_graph_async(
        self,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "MiroFish Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        batch_size: int = 3
    ) -> str:
        """
        Construir grafo de forma assíncrona

        Args:
            text: Texto de entrada
            ontology: Definição de ontologia (saída da interface 1)
            graph_name: Nome do grafo
            chunk_size: Tamanho do bloco de texto
            chunk_overlap: Tamanho da sobreposição do bloco
            batch_size: Quantidade de blocos por lote

        Returns:
            ID da tarefa
        """
        # Criar tarefa
        task_id = self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            }
        )
        
        # Executar construção em thread de background
        thread = threading.Thread(
            target=self._build_graph_worker,
            args=(task_id, text, ontology, graph_name, chunk_size, chunk_overlap, batch_size)
        )
        thread.daemon = True
        thread.start()
        
        return task_id
    
    def _build_graph_worker(
        self,
        task_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int
    ):
        """Thread de trabalho para construção de grafos"""
        try:
            self.task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=5,
                message="Iniciando construção do grafo..."
            )
            
            # 1. Criar grafo
            graph_id = self.create_graph(graph_name)
            self.task_manager.update_task(
                task_id,
                progress=10,
                message=f"Grafo criado: {graph_id}"
            )
            
            # 2. Configurar ontologia
            self.set_ontology(graph_id, ontology)
            self.task_manager.update_task(
                task_id,
                progress=15,
                message="Ontologia configurada"
            )
            
            # 3. Dividir texto em blocos
            chunks = TextProcessor.split_text(text, chunk_size, chunk_overlap)
            total_chunks = len(chunks)
            self.task_manager.update_task(
                task_id,
                progress=20,
                message=f"Texto dividido em {total_chunks} blocos"
            )
            
            # 4. Enviar dados em lotes
            episode_uuids = self.add_text_batches(
                graph_id, chunks, batch_size,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=20 + int(prog * 0.4),  # 20-60%
                    message=msg
                )
            )
            
            # 5. Aguardar conclusão do processamento Zep
            self.task_manager.update_task(
                task_id,
                progress=60,
                message="Aguardando Zep processar dados..."
            )
            
            self._wait_for_episodes(
                episode_uuids,
                lambda msg, prog: self.task_manager.update_task(
                    task_id,
                    progress=60 + int(prog * 0.3),  # 60-90%
                    message=msg
                )
            )
            
            # 6. Obter informações do grafo
            self.task_manager.update_task(
                task_id,
                progress=90,
                message="Obtendo informações do grafo..."
            )
            
            graph_info = self._get_graph_info(graph_id)
            
            # Concluído
            self.task_manager.complete_task(task_id, {
                "graph_id": graph_id,
                "graph_info": graph_info.to_dict(),
                "chunks_processed": total_chunks,
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            self.task_manager.fail_task(task_id, error_msg)
    
    def create_graph(self, name: str) -> str:
        """Criar grafo Zep (método público)"""
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        
        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description="MiroFish Social Simulation Graph"
        )
        
        return graph_id
    
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """Configurar ontologia do grafo (método público)"""
        import warnings
        from typing import Optional
        from pydantic import Field
        from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel
        
        # Suprimir avisos do Pydantic v2 sobre Field(default=None)
        # Este é o uso exigido pelo Zep SDK, o aviso vem da criação dinâmica de classes e pode ser ignorado com segurança
        warnings.filterwarnings('ignore', category=UserWarning, module='pydantic')
        
        # Nomes reservados do Zep, não podem ser usados como nomes de atributos
        RESERVED_NAMES = {'uuid', 'name', 'group_id', 'name_embedding', 'summary', 'created_at'}
        
        def safe_attr_name(attr_name: str) -> str:
            """Converter nomes reservados em nomes seguros"""
            if attr_name.lower() in RESERVED_NAMES:
                return f"entity_{attr_name}"
            return attr_name
        
        # Criar tipos de entidade dinamicamente
        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            
            # Criar dicionário de atributos e anotações de tipo (necessário para Pydantic v2)
            attrs = {"__doc__": description}
            annotations = {}
            
            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # Usar nome seguro
                attr_desc = attr_def.get("description", attr_name)
                # Zep API requer description do Field, isto é obrigatório
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]  # Anotação de tipo
            
            attrs["__annotations__"] = annotations
            
            # Criar classe dinamicamente
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class
        
        # Criar tipos de aresta dinamicamente
        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")
            
            # Criar dicionário de atributos e anotações de tipo
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])  # Usar nome seguro
                attr_desc = attr_def.get("description", attr_name)
                # Zep API requer description do Field, isto é obrigatório
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]  # Atributos de aresta usam tipo str
            
            attrs["__annotations__"] = annotations
            
            # Criar classe dinamicamente
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description
            
            # Construir source_targets
            source_targets = []
            for st in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=st.get("source", "Entity"),
                        target=st.get("target", "Entity")
                    )
                )
            
            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)
        
        # Chamar Zep API para configurar ontologia
        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )
    
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """Adicionar texto ao grafo em lotes, retornando lista de uuid de todos os episodes"""
        episode_uuids = []
        total_chunks = len(chunks)
        
        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size
            
            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    f"Enviando lote {batch_num}/{total_batches} ({len(batch_chunks)} blocos)...",
                    progress
                )
            
            # Construir dados de episode
            episodes = [
                EpisodeData(data=chunk, type="text")
                for chunk in batch_chunks
            ]
            
            # Enviar para Zep
            try:
                batch_result = self.client.graph.add_batch(
                    graph_id=graph_id,
                    episodes=episodes
                )
                
                # Coletar uuid dos episodes retornados
                if batch_result and isinstance(batch_result, list):
                    for ep in batch_result:
                        ep_uuid = getattr(ep, 'uuid_', None) or getattr(ep, 'uuid', None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)
                
                # Evitar requisições muito rápidas
                time.sleep(1)
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Falha ao enviar lote {batch_num}: {str(e)}", 0)
                raise
        
        return episode_uuids
    
    def _wait_for_episodes(
        self,
        episode_uuids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600
    ):
        """Aguardar conclusão do processamento de todos os episodes (consultando o status processed de cada episode)"""
        if not episode_uuids:
            if progress_callback:
                progress_callback("Sem necessidade de aguardar (nenhum episode)", 1.0)
            return
        
        start_time = time.time()
        pending_episodes = set(episode_uuids)
        completed_count = 0
        total_episodes = len(episode_uuids)
        
        if progress_callback:
            progress_callback(f"Iniciando aguardo do processamento de {total_episodes} blocos de texto...", 0)
        
        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        f"Timeout parcial de blocos de texto, concluídos {completed_count}/{total_episodes}",
                        completed_count / total_episodes
                    )
                break
            
            # Verificar status de processamento de cada episode
            for ep_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=ep_uuid)
                    is_processed = getattr(episode, 'processed', False)
                    
                    if is_processed:
                        pending_episodes.remove(ep_uuid)
                        completed_count += 1
                        
                except Exception as e:
                    # Ignorar erros de consulta individual, continuar
                    pass
            
            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    f"Zep processando... {completed_count}/{total_episodes} concluídos, {len(pending_episodes)} pendentes ({elapsed}s)",
                    completed_count / total_episodes if total_episodes > 0 else 0
                )
            
            if pending_episodes:
                time.sleep(3)  # Verificar a cada 3 segundos
        
        if progress_callback:
            progress_callback(f"Processamento concluído: {completed_count}/{total_episodes}", 1.0)
    
    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """Obter informações do grafo"""
        # Obter nós (paginado)
        nodes = fetch_all_nodes(self.client, graph_id)

        # Obter arestas (paginado)
        edges = fetch_all_edges(self.client, graph_id)

        # Contabilizar tipos de entidade
        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types)
        )
    
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Obter dados completos do grafo (incluindo informações detalhadas)

        Args:
            graph_id: ID do grafo

        Returns:
            Dicionário contendo nodes e edges, incluindo informações de tempo, atributos e outros dados detalhados
        """
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        # Criar mapeamento de nós para obter nomes dos nós
        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""
        
        nodes_data = []
        for node in nodes:
            # Obter data de criação
            created_at = getattr(node, 'created_at', None)
            if created_at:
                created_at = str(created_at)
            
            nodes_data.append({
                "uuid": node.uuid_,
                "name": node.name,
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
                "created_at": created_at,
            })
        
        edges_data = []
        for edge in edges:
            # Obter informações de tempo
            created_at = getattr(edge, 'created_at', None)
            valid_at = getattr(edge, 'valid_at', None)
            invalid_at = getattr(edge, 'invalid_at', None)
            expired_at = getattr(edge, 'expired_at', None)
            
            # Obter episodes
            episodes = getattr(edge, 'episodes', None) or getattr(edge, 'episode_ids', None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(e) for e in episodes]
            
            # Obter fact_type
            fact_type = getattr(edge, 'fact_type', None) or edge.name or ""
            
            edges_data.append({
                "uuid": edge.uuid_,
                "name": edge.name or "",
                "fact": edge.fact or "",
                "fact_type": fact_type,
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "source_node_name": node_map.get(edge.source_node_uuid, ""),
                "target_node_name": node_map.get(edge.target_node_uuid, ""),
                "attributes": edge.attributes or {},
                "created_at": str(created_at) if created_at else None,
                "valid_at": str(valid_at) if valid_at else None,
                "invalid_at": str(invalid_at) if invalid_at else None,
                "expired_at": str(expired_at) if expired_at else None,
                "episodes": episodes or [],
            })
        
        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }
    
    def delete_graph(self, graph_id: str):
        """Excluir grafo"""
        self.client.graph.delete(graph_id=graph_id)

