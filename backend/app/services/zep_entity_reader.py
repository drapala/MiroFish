"""
Serviço de leitura e filtragem de entidades Zep
Ler nós do grafo Zep e filtrar os que correspondem aos tipos de entidade predefinidos
"""

import time
from typing import Dict, Any, List, Optional, Set, Callable, TypeVar
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_entity_reader')

# Para tipo de retorno genérico
T = TypeVar('T')


@dataclass
class EntityNode:
    """Estrutura de dados do nó de entidade"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Informações de arestas relacionadas
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Informações de outros nós relacionados
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }
    
    def get_entity_type(self) -> Optional[str]:
        """Obter tipo de entidade (excluindo label padrão Entity)"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Conjunto de entidades filtradas"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Serviço de leitura e filtragem de entidades Zep

    Funcionalidades principais:
    1. Ler todos os nós do grafo Zep
    2. Filtrar nós que correspondem aos tipos de entidade predefinidos (nós cujos Labels não são apenas Entity)
    3. Obter arestas relacionadas e informações de nós associados para cada entidade
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY não configurada")
        
        self.client = Zep(api_key=self.api_key)
    
    def _call_with_retry(
        self, 
        func: Callable[[], T], 
        operation_name: str,
        max_retries: int = 3,
        initial_delay: float = 2.0
    ) -> T:
        """
        Chamada de API Zep com mecanismo de retry

        Args:
            func: Função a ser executada (lambda ou callable sem parâmetros)
            operation_name: Nome da operação, usado para logs
            max_retries: Número máximo de tentativas (padrão 3, ou seja, no máximo 3 tentativas)
            initial_delay: Atraso inicial em segundos

        Returns:
            Resultado da chamada de API
        """
        last_exception = None
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} falhou na tentativa {attempt + 1}: {str(e)[:100]}, "
                        f"retentando em {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= 2  # Backoff exponencial
                else:
                    logger.error(f"Zep {operation_name} ainda falhou após {max_retries} tentativas: {str(e)}")
        
        raise last_exception
    
    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Obter todos os nós do grafo (com paginação)

        Args:
            graph_id: ID do grafo

        Returns:
            Lista de nós
        """
        logger.info(f"Obtendo todos os nós do grafo {graph_id}...")

        nodes = fetch_all_nodes(self.client, graph_id)

        nodes_data = []
        for node in nodes:
            nodes_data.append({
                "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                "name": node.name or "",
                "labels": node.labels or [],
                "summary": node.summary or "",
                "attributes": node.attributes or {},
            })

        logger.info(f"Total de {len(nodes_data)} nós obtidos")
        return nodes_data

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        Obter todas as arestas do grafo (com paginação)

        Args:
            graph_id: ID do grafo

        Returns:
            Lista de arestas
        """
        logger.info(f"Obtendo todas as arestas do grafo {graph_id}...")

        edges = fetch_all_edges(self.client, graph_id)

        edges_data = []
        for edge in edges:
            edges_data.append({
                "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                "name": edge.name or "",
                "fact": edge.fact or "",
                "source_node_uuid": edge.source_node_uuid,
                "target_node_uuid": edge.target_node_uuid,
                "attributes": edge.attributes or {},
            })

        logger.info(f"Total de {len(edges_data)} arestas obtidas")
        return edges_data
    
    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        Obter todas as arestas relacionadas ao nó especificado (com mecanismo de retry)

        Args:
            node_uuid: UUID do nó

        Returns:
            Lista de arestas
        """
        try:
            # Chamar Zep API com mecanismo de retry
            edges = self._call_with_retry(
                func=lambda: self.client.graph.node.get_entity_edges(node_uuid=node_uuid),
                operation_name=f"obter arestas do nó(node={node_uuid[:8]}...)"
            )
            
            edges_data = []
            for edge in edges:
                edges_data.append({
                    "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "attributes": edge.attributes or {},
                })
            
            return edges_data
        except Exception as e:
            logger.warning(f"Falha ao obter arestas do nó {node_uuid}: {str(e)}")
            return []
    
    def filter_defined_entities(
        self, 
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        Filtrar nós que correspondem aos tipos de entidade predefinidos

        Lógica de filtragem:
        - Se os Labels do nó contêm apenas "Entity", significa que esta entidade não corresponde aos nossos tipos predefinidos, pular
        - Se os Labels do nó contêm labels além de "Entity" e "Node", significa que corresponde ao tipo predefinido, manter

        Args:
            graph_id: ID do grafo
            defined_entity_types: Lista de tipos de entidade predefinidos (opcional, se fornecido mantém apenas esses tipos)
            enrich_with_edges: Se deve obter informações de arestas relacionadas para cada entidade

        Returns:
            FilteredEntities: Conjunto de entidades filtradas
        """
        logger.info(f"Iniciando filtragem de entidades do grafo {graph_id}...")
        
        # Obter todos os nós
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        
        # Obter todas as arestas (para busca de associações posterior)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        
        # Construir mapeamento de UUID de nó para dados do nó
        node_map = {n["uuid"]: n for n in all_nodes}
        
        # Filtrar entidades que atendem aos critérios
        filtered_entities = []
        entity_types_found = set()
        
        for node in all_nodes:
            labels = node.get("labels", [])
            
            # Lógica de filtragem: Labels devem conter labels além de "Entity" e "Node"
            custom_labels = [l for l in labels if l not in ["Entity", "Node"]]
            
            if not custom_labels:
                # Apenas labels padrão, pular
                continue
            
            # Se tipos predefinidos foram especificados, verificar se há correspondência
            if defined_entity_types:
                matching_labels = [l for l in custom_labels if l in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]
            
            entity_types_found.add(entity_type)
            
            # Criar objeto de nó de entidade
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node["summary"],
                attributes=node["attributes"],
            )
            
            # Obter arestas e nós relacionados
            if enrich_with_edges:
                related_edges = []
                related_node_uuids = set()
                
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])
                
                entity.related_edges = related_edges
                
                # Obter informações básicas dos nós associados
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        })
                
                entity.related_nodes = related_nodes
            
            filtered_entities.append(entity)
        
        logger.info(f"Filtragem concluída: total de nós {total_count}, que atendem aos critérios {len(filtered_entities)}, "
                   f"tipos de entidade: {entity_types_found}")
        
        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )
    
    def get_entity_with_context(
        self, 
        graph_id: str, 
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        Obter uma única entidade e seu contexto completo (arestas e nós associados, com mecanismo de retry)

        Args:
            graph_id: ID do grafo
            entity_uuid: UUID da entidade

        Returns:
            EntityNode ou None
        """
        try:
            # Obter nó com mecanismo de retry
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=entity_uuid),
                operation_name=f"obter detalhes do nó(uuid={entity_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            # Obter arestas do nó
            edges = self.get_node_edges(entity_uuid)
            
            # Obter todos os nós para busca de associações
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {n["uuid"]: n for n in all_nodes}
            
            # Processar arestas e nós relacionados
            related_edges = []
            related_node_uuids = set()
            
            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge["fact"],
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])
            
            # Obter informações dos nós associados
            related_nodes = []
            for related_uuid in related_node_uuids:
                if related_uuid in node_map:
                    related_node = node_map[related_uuid]
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node["labels"],
                        "summary": related_node.get("summary", ""),
                    })
            
            return EntityNode(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {},
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
            
        except Exception as e:
            logger.error(f"Falha ao obter entidade {entity_uuid}: {str(e)}")
            return None
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        Obter todas as entidades de um tipo especificado

        Args:
            graph_id: ID do grafo
            entity_type: Tipo de entidade (ex: "Student", "PublicFigure" etc.)
            enrich_with_edges: Se deve obter informações de arestas relacionadas

        Returns:
            Lista de entidades
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities


