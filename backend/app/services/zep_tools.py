"""
Serviço de ferramentas de busca Zep
Encapsula busca de grafo, leitura de nós, consulta de arestas e outras ferramentas para uso pelo Report Agent

Ferramentas de busca principais (otimizadas):
1. InsightForge (busca de insight profundo) - busca híbrida mais poderosa, gera subperguntas automaticamente e busca em múltiplas dimensões
2. PanoramaSearch (busca ampla) - obter visão geral, incluindo conteúdo expirado
3. QuickSearch (busca simples) - busca rápida
"""

import time
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from zep_cloud.client import Zep

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.zep_paging import fetch_all_nodes, fetch_all_edges

logger = get_logger('mirofish.zep_tools')


@dataclass
class SearchResult:
    """Resultado de busca"""
    facts: List[str]
    edges: List[Dict[str, Any]]
    nodes: List[Dict[str, Any]]
    query: str
    total_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "facts": self.facts,
            "edges": self.edges,
            "nodes": self.nodes,
            "query": self.query,
            "total_count": self.total_count
        }
    
    def to_text(self) -> str:
        """Converter para formato de texto, para compreensão do LLM"""
        text_parts = [f"Consulta de busca: {self.query}", f"Encontradas {self.total_count} informações relevantes"]
        
        if self.facts:
            text_parts.append("\n### Fatos relevantes:")
            for i, fact in enumerate(self.facts, 1):
                text_parts.append(f"{i}. {fact}")
        
        return "\n".join(text_parts)


@dataclass
class NodeInfo:
    """Informações do nó"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes
        }
    
    def to_text(self) -> str:
        """Converter para formato de texto"""
        entity_type = next((l for l in self.labels if l not in ["Entity", "Node"]), "tipo desconhecido")
        return f"Entidade: {self.name} (tipo: {entity_type})\nResumo: {self.summary}"


@dataclass
class EdgeInfo:
    """Informações da aresta"""
    uuid: str
    name: str
    fact: str
    source_node_uuid: str
    target_node_uuid: str
    source_node_name: Optional[str] = None
    target_node_name: Optional[str] = None
    # Informações temporais
    created_at: Optional[str] = None
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    expired_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "fact": self.fact,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "source_node_name": self.source_node_name,
            "target_node_name": self.target_node_name,
            "created_at": self.created_at,
            "valid_at": self.valid_at,
            "invalid_at": self.invalid_at,
            "expired_at": self.expired_at
        }
    
    def to_text(self, include_temporal: bool = False) -> str:
        """Converter para formato de texto"""
        source = self.source_node_name or self.source_node_uuid[:8]
        target = self.target_node_name or self.target_node_uuid[:8]
        base_text = f"Relação: {source} --[{self.name}]--> {target}\nFato: {self.fact}"
        
        if include_temporal:
            valid_at = self.valid_at or "desconhecido"
            invalid_at = self.invalid_at or "até o momento"
            base_text += f"\nValidade: {valid_at} - {invalid_at}"
            if self.expired_at:
                base_text += f" (expirado: {self.expired_at})"
        
        return base_text
    
    @property
    def is_expired(self) -> bool:
        """Se está expirado"""
        return self.expired_at is not None
    
    @property
    def is_invalid(self) -> bool:
        """Se está invalidado"""
        return self.invalid_at is not None


@dataclass
class InsightForgeResult:
    """
    Resultado de busca de insight profundo (InsightForge)
    Contém resultados de busca de múltiplas subperguntas e análise abrangente
    """
    query: str
    simulation_requirement: str
    sub_queries: List[str]
    
    # Resultados de busca por dimensão
    semantic_facts: List[str] = field(default_factory=list)  # Resultados de busca semântica
    entity_insights: List[Dict[str, Any]] = field(default_factory=list)  # Insights de entidades
    relationship_chains: List[str] = field(default_factory=list)  # Cadeias de relações
    
    # Informações estatísticas
    total_facts: int = 0
    total_entities: int = 0
    total_relationships: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "simulation_requirement": self.simulation_requirement,
            "sub_queries": self.sub_queries,
            "semantic_facts": self.semantic_facts,
            "entity_insights": self.entity_insights,
            "relationship_chains": self.relationship_chains,
            "total_facts": self.total_facts,
            "total_entities": self.total_entities,
            "total_relationships": self.total_relationships
        }
    
    def to_text(self) -> str:
        """Converter para formato de texto detalhado, para compreensão do LLM"""
        text_parts = [
            f"## Análise profunda de previsão futura",
            f"Questão de análise: {self.query}",
            f"Cenário de previsão: {self.simulation_requirement}",
            f"\n### Estatísticas de dados de previsão",
            f"- Fatos de previsão relevantes: {self.total_facts}",
            f"- Entidades envolvidas: {self.total_entities}",
            f"- Cadeias de relações: {self.total_relationships}"
        ]
        
        # Subperguntas
        if self.sub_queries:
            text_parts.append(f"\n### Subperguntas analisadas")
            for i, sq in enumerate(self.sub_queries, 1):
                text_parts.append(f"{i}. {sq}")
        
        # Resultados de busca semântica
        if self.semantic_facts:
            text_parts.append(f"\n### [Fatos-chave] (cite estes textos originais no relatório)")
            for i, fact in enumerate(self.semantic_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Insights de entidades
        if self.entity_insights:
            text_parts.append(f"\n### [Entidades principais]")
            for entity in self.entity_insights:
                text_parts.append(f"- **{entity.get('name', 'desconhecido')}** ({entity.get('type', 'entidade')})")
                if entity.get('summary'):
                    text_parts.append(f"  Resumo: \"{entity.get('summary')}\"")
                if entity.get('related_facts'):
                    text_parts.append(f"  Fatos relevantes: {len(entity.get('related_facts', []))}")
        
        # Cadeias de relações
        if self.relationship_chains:
            text_parts.append(f"\n### [Cadeias de relações]")
            for chain in self.relationship_chains:
                text_parts.append(f"- {chain}")
        
        return "\n".join(text_parts)


@dataclass
class PanoramaResult:
    """
    Resultado de busca ampla (Panorama)
    Contém todas as informações relevantes, incluindo conteúdo expirado
    """
    query: str
    
    # Todos os nós
    all_nodes: List[NodeInfo] = field(default_factory=list)
    # Todas as arestas (incluindo expiradas)
    all_edges: List[EdgeInfo] = field(default_factory=list)
    # Fatos atualmente válidos
    active_facts: List[str] = field(default_factory=list)
    # Fatos expirados/invalidados (registros históricos)
    historical_facts: List[str] = field(default_factory=list)
    
    # Estatísticas
    total_nodes: int = 0
    total_edges: int = 0
    active_count: int = 0
    historical_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "all_nodes": [n.to_dict() for n in self.all_nodes],
            "all_edges": [e.to_dict() for e in self.all_edges],
            "active_facts": self.active_facts,
            "historical_facts": self.historical_facts,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "active_count": self.active_count,
            "historical_count": self.historical_count
        }
    
    def to_text(self) -> str:
        """Converter para formato de texto (versão completa, sem truncar)"""
        text_parts = [
            f"## Resultado de busca ampla (visão panorâmica futura)",
            f"Consulta: {self.query}",
            f"\n### Informações estatísticas",
            f"- Total de nós: {self.total_nodes}",
            f"- Total de arestas: {self.total_edges}",
            f"- Fatos válidos atuais: {self.active_count}",
            f"- Fatos históricos/expirados: {self.historical_count}"
        ]
        
        # Fatos atualmente válidos（saída completa, sem truncar）
        if self.active_facts:
            text_parts.append(f"\n### [Fatos válidos atuais] (texto original dos resultados da simulação)")
            for i, fact in enumerate(self.active_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Fatos históricos/expirados (saída completa, sem truncar)
        if self.historical_facts:
            text_parts.append(f"\n### [Fatos históricos/expirados] (registro do processo de evolução)")
            for i, fact in enumerate(self.historical_facts, 1):
                text_parts.append(f"{i}. \"{fact}\"")
        
        # Entidades-chave (saída completa, sem truncar)
        if self.all_nodes:
            text_parts.append(f"\n### [Entidades envolvidas]")
            for node in self.all_nodes:
                entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "entidade")
                text_parts.append(f"- **{node.name}** ({entity_type})")
        
        return "\n".join(text_parts)


@dataclass
class AgentInterview:
    """Resultado de entrevista de um único Agent"""
    agent_name: str
    agent_role: str  # Tipo de papel (ex: estudante, professor, mídia, etc.)
    agent_bio: str  # Biografia
    question: str  # Pergunta da entrevista
    response: str  # Resposta da entrevista
    key_quotes: List[str] = field(default_factory=list)  # Citações-chave
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_role": self.agent_role,
            "agent_bio": self.agent_bio,
            "question": self.question,
            "response": self.response,
            "key_quotes": self.key_quotes
        }
    
    def to_text(self) -> str:
        text = f"**{self.agent_name}** ({self.agent_role})\n"
        # Exibir agent_bio completo, sem truncar
        text += f"_Biografia: {self.agent_bio}_\n\n"
        text += f"**Q:** {self.question}\n\n"
        text += f"**A:** {self.response}\n"
        if self.key_quotes:
            text += "\n**Citações-chave:**\n"
            for quote in self.key_quotes:
                # Limpar diversos tipos de aspas
                clean_quote = quote.replace('\u201c', '').replace('\u201d', '').replace('"', '')
                clean_quote = clean_quote.replace('\u300c', '').replace('\u300d', '')
                clean_quote = clean_quote.strip()
                # Remover pontuação do início
                while clean_quote and clean_quote[0] in '，,；;：:、。！？\n\r\t ':
                    clean_quote = clean_quote[1:]
                # Filtrar conteúdo lixo contendo números de perguntas (pergunta 1-9)
                skip = False
                for d in '123456789':
                    if f'\u95ee\u9898{d}' in clean_quote:
                        skip = True
                        break
                if skip:
                    continue
                # Truncar conteúdo muito longo (truncar por ponto final, não truncagem rígida)
                if len(clean_quote) > 150:
                    dot_pos = clean_quote.find('\u3002', 80)
                    if dot_pos > 0:
                        clean_quote = clean_quote[:dot_pos + 1]
                    else:
                        clean_quote = clean_quote[:147] + "..."
                if clean_quote and len(clean_quote) >= 10:
                    text += f'> "{clean_quote}"\n'
        return text


@dataclass
class InterviewResult:
    """
    Resultado de entrevista (Interview)
    Contém respostas de entrevista de múltiplos Agents de simulação
    """
    interview_topic: str  # Tema da entrevista
    interview_questions: List[str]  # Lista de perguntas da entrevista
    
    # Agents selecionados para entrevista
    selected_agents: List[Dict[str, Any]] = field(default_factory=list)
    # Respostas de entrevista de cada Agent
    interviews: List[AgentInterview] = field(default_factory=list)
    
    # Razão para seleção do Agent
    selection_reasoning: str = ""
    # Resumo integrado da entrevista
    summary: str = ""
    
    # Estatísticas
    total_agents: int = 0
    interviewed_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "interview_topic": self.interview_topic,
            "interview_questions": self.interview_questions,
            "selected_agents": self.selected_agents,
            "interviews": [i.to_dict() for i in self.interviews],
            "selection_reasoning": self.selection_reasoning,
            "summary": self.summary,
            "total_agents": self.total_agents,
            "interviewed_count": self.interviewed_count
        }
    
    def to_text(self) -> str:
        """Converter para formato de texto detalhado, para compreensão do LLM e citação no relatório"""
        text_parts = [
            "## Relatório de entrevista aprofundada",
            f"**Tema da entrevista:** {self.interview_topic}",
            f"**Entrevistados:** {self.interviewed_count} / {self.total_agents} Agents de simulação",
            "\n### Razão para seleção dos entrevistados",
            self.selection_reasoning or "(seleção automática)",
            "\n---",
            "\n### Transcrição da entrevista",
        ]

        if self.interviews:
            for i, interview in enumerate(self.interviews, 1):
                text_parts.append(f"\n#### Entrevista #{i}: {interview.agent_name}")
                text_parts.append(interview.to_text())
                text_parts.append("\n---")
        else:
            text_parts.append("(sem registro de entrevista)\n\n---")

        text_parts.append("\n### Resumo da entrevista e pontos de vista centrais")
        text_parts.append(self.summary or "(sem resumo)")

        return "\n".join(text_parts)


class ZepToolsService:
    """
    Serviço de ferramentas de busca Zep
    
    [Ferramentas de busca principais - otimizadas]
    1. insight_forge - busca de insight profundo (mais poderosa, gera subperguntas automaticamente, busca multidimensional)
    2. panorama_search - busca ampla (obter visão geral, incluindo conteúdo expirado)
    3. quick_search - busca simples (busca rápida)
    4. interview_agents - entrevista aprofundada (entrevistar Agents de simulação, obter perspectivas múltiplas)
    
    [Ferramentas básicas]
    - search_graph - busca semântica do grafo
    - get_all_nodes - obter todos os nós do grafo
    - get_all_edges - obter todas as arestas do grafo (com informações temporais)
    - get_node_detail - obter informações detalhadas do nó
    - get_node_edges - obter arestas relacionadas ao nó
    - get_entities_by_type - obter entidades por tipo
    - get_entity_summary - obter resumo de relações da entidade
    """
    
    # Configuração de retry
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0
    
    def __init__(self, api_key: Optional[str] = None, llm_client: Optional[LLMClient] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY não configurada")
        
        self.client = Zep(api_key=self.api_key)
        # Cliente LLM para InsightForge gerar subperguntas
        self._llm_client = llm_client
        logger.info("ZepToolsService inicialização concluída")
    
    @property
    def llm(self) -> LLMClient:
        """Inicialização tardia do cliente LLM"""
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client
    
    def _call_with_retry(self, func, operation_name: str, max_retries: int = None):
        """Chamada de API com mecanismo de retry"""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Zep {operation_name} falha na tentativa {attempt + 1}: {str(e)[:100]}, "
                        f"retentando em {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= 2
                else:
                    logger.error(f"Zep {operation_name} ainda falhou após {max_retries} tentativas: {str(e)}")
        
        raise last_exception
    
    def search_graph(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Busca semântica do grafo
        
        Usar busca híbrida (semântica+BM25) para buscar informações relevantes no grafo.
        Se a search API do Zep Cloud não estiver disponível, degradar para correspondência de palavras-chave local.
        
        Args:
            graph_id: ID do grafo (Standalone Graph)
            query: consulta de busca
            limit: quantidade de resultados retornados
            scope: escopo de busca, "edges" ou "nodes"
            
        Returns:
            SearchResult: resultado de busca
        """
        logger.info(f"Busca no grafo: graph_id={graph_id}, query={query[:50]}...")
        
        # Tentar usar Zep Cloud Search API
        try:
            search_results = self._call_with_retry(
                func=lambda: self.client.graph.search(
                    graph_id=graph_id,
                    query=query,
                    limit=limit,
                    scope=scope,
                    reranker="cross_encoder"
                ),
                operation_name=f"busca no grafo(graph={graph_id})"
            )
            
            facts = []
            edges = []
            nodes = []
            
            # Analisar resultados de busca de arestas
            if hasattr(search_results, 'edges') and search_results.edges:
                for edge in search_results.edges:
                    if hasattr(edge, 'fact') and edge.fact:
                        facts.append(edge.fact)
                    edges.append({
                        "uuid": getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', ''),
                        "name": getattr(edge, 'name', ''),
                        "fact": getattr(edge, 'fact', ''),
                        "source_node_uuid": getattr(edge, 'source_node_uuid', ''),
                        "target_node_uuid": getattr(edge, 'target_node_uuid', ''),
                    })
            
            # Analisar resultados de busca de nós
            if hasattr(search_results, 'nodes') and search_results.nodes:
                for node in search_results.nodes:
                    nodes.append({
                        "uuid": getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                        "name": getattr(node, 'name', ''),
                        "labels": getattr(node, 'labels', []),
                        "summary": getattr(node, 'summary', ''),
                    })
                    # Resumos de nós também contam como fatos
                    if hasattr(node, 'summary') and node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"Busca concluída: encontrados {len(facts)} fatos relevantes")
            
            return SearchResult(
                facts=facts,
                edges=edges,
                nodes=nodes,
                query=query,
                total_count=len(facts)
            )
            
        except Exception as e:
            logger.warning(f"Zep Search API falhou, degradando para busca local: {str(e)}")
            # Degradar: usar busca de correspondência de palavras-chave local
            return self._local_search(graph_id, query, limit, scope)
    
    def _local_search(
        self, 
        graph_id: str, 
        query: str, 
        limit: int = 10,
        scope: str = "edges"
    ) -> SearchResult:
        """
        Busca de correspondência de palavras-chave local (como plano de degradação da Zep Search API)
        
        Obter todas as arestas/nós, depois realizar correspondência de palavras-chave localmente
        
        Args:
            graph_id: ID do grafo
            query: consulta de busca
            limit: quantidade de resultados retornados
            scope: escopo de busca
            
        Returns:
            SearchResult: resultado de busca
        """
        logger.info(f"Usando busca local: query={query[:30]}...")
        
        facts = []
        edges_result = []
        nodes_result = []
        
        # Extrair palavras-chave da consulta (tokenização simples)
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def match_score(text: str) -> int:
            """Calcular pontuação de correspondência entre texto e consulta"""
            if not text:
                return 0
            text_lower = text.lower()
            # Correspondência exata da consulta
            if query_lower in text_lower:
                return 100
            # Correspondência de palavras-chave
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 10
            return score
        
        try:
            if scope in ["edges", "both"]:
                # Obter todas as arestas e fazer correspondência
                all_edges = self.get_all_edges(graph_id)
                scored_edges = []
                for edge in all_edges:
                    score = match_score(edge.fact) + match_score(edge.name)
                    if score > 0:
                        scored_edges.append((score, edge))
                
                # Ordenar por pontuação
                scored_edges.sort(key=lambda x: x[0], reverse=True)
                
                for score, edge in scored_edges[:limit]:
                    if edge.fact:
                        facts.append(edge.fact)
                    edges_result.append({
                        "uuid": edge.uuid,
                        "name": edge.name,
                        "fact": edge.fact,
                        "source_node_uuid": edge.source_node_uuid,
                        "target_node_uuid": edge.target_node_uuid,
                    })
            
            if scope in ["nodes", "both"]:
                # Obter todos os nós e fazer correspondência
                all_nodes = self.get_all_nodes(graph_id)
                scored_nodes = []
                for node in all_nodes:
                    score = match_score(node.name) + match_score(node.summary)
                    if score > 0:
                        scored_nodes.append((score, node))
                
                scored_nodes.sort(key=lambda x: x[0], reverse=True)
                
                for score, node in scored_nodes[:limit]:
                    nodes_result.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "labels": node.labels,
                        "summary": node.summary,
                    })
                    if node.summary:
                        facts.append(f"[{node.name}]: {node.summary}")
            
            logger.info(f"Busca local concluída: encontrados {len(facts)} fatos relevantes")
            
        except Exception as e:
            logger.error(f"Falha na busca local: {str(e)}")
        
        return SearchResult(
            facts=facts,
            edges=edges_result,
            nodes=nodes_result,
            query=query,
            total_count=len(facts)
        )
    
    def get_all_nodes(self, graph_id: str) -> List[NodeInfo]:
        """
        Obter todos os nós do grafo (com paginação)

        Args:
            graph_id: ID do grafo

        Returns:
            Lista de nós
        """
        logger.info(f"Obtendo grafo {graph_id} todos os nós...")

        nodes = fetch_all_nodes(self.client, graph_id)

        result = []
        for node in nodes:
            node_uuid = getattr(node, 'uuid_', None) or getattr(node, 'uuid', None) or ""
            result.append(NodeInfo(
                uuid=str(node_uuid) if node_uuid else "",
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            ))

        logger.info(f"Obtidos {len(result)} nós")
        return result

    def get_all_edges(self, graph_id: str, include_temporal: bool = True) -> List[EdgeInfo]:
        """
        Obter todas as arestas do grafo (com paginação, incluindo informações temporais)

        Args:
            graph_id: ID do grafo
            include_temporal: Se deve incluir informações temporais (padrão True)

        Returns:
            Lista de arestas (incluindo created_at, valid_at, invalid_at, expired_at)
        """
        logger.info(f"Obtendo grafo {graph_id} todas as arestas...")

        edges = fetch_all_edges(self.client, graph_id)

        result = []
        for edge in edges:
            edge_uuid = getattr(edge, 'uuid_', None) or getattr(edge, 'uuid', None) or ""
            edge_info = EdgeInfo(
                uuid=str(edge_uuid) if edge_uuid else "",
                name=edge.name or "",
                fact=edge.fact or "",
                source_node_uuid=edge.source_node_uuid or "",
                target_node_uuid=edge.target_node_uuid or ""
            )

            # Adicionar informações temporais
            if include_temporal:
                edge_info.created_at = getattr(edge, 'created_at', None)
                edge_info.valid_at = getattr(edge, 'valid_at', None)
                edge_info.invalid_at = getattr(edge, 'invalid_at', None)
                edge_info.expired_at = getattr(edge, 'expired_at', None)

            result.append(edge_info)

        logger.info(f"Obtidos {len(result)} arestas")
        return result
    
    def get_node_detail(self, node_uuid: str) -> Optional[NodeInfo]:
        """
        Obter informações detalhadas de um único nó
        
        Args:
            node_uuid: UUID do nó
            
        Returns:
            Informações do nó ou None
        """
        logger.info(f"Obtendo detalhes do nó: {node_uuid[:8]}...")
        
        try:
            node = self._call_with_retry(
                func=lambda: self.client.graph.node.get(uuid_=node_uuid),
                operation_name=f"obter detalhes do nó(uuid={node_uuid[:8]}...)"
            )
            
            if not node:
                return None
            
            return NodeInfo(
                uuid=getattr(node, 'uuid_', None) or getattr(node, 'uuid', ''),
                name=node.name or "",
                labels=node.labels or [],
                summary=node.summary or "",
                attributes=node.attributes or {}
            )
        except Exception as e:
            logger.error(f"Falha ao obter detalhes do nó: {str(e)}")
            return None
    
    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[EdgeInfo]:
        """
        Obter todas as arestas relacionadas ao nó
        
        Obtendo todas as arestas do grafo e filtrando as relacionadas ao nó especificado
        
        Args:
            graph_id: ID do grafo
            node_uuid: UUID do nó
            
        Returns:
            Lista de arestas
        """
        logger.info(f"Obtendo nó {node_uuid[:8]}... arestas relacionadas")
        
        try:
            # Obter todas as arestas do grafo e filtrar
            all_edges = self.get_all_edges(graph_id)
            
            result = []
            for edge in all_edges:
                # Verificar se a aresta está relacionada ao nó especificado (como fonte ou destino)
                if edge.source_node_uuid == node_uuid or edge.target_node_uuid == node_uuid:
                    result.append(edge)
            
            logger.info(f"Encontrados {len(result)} arestas relacionadas ao nó")
            return result
            
        except Exception as e:
            logger.warning(f"Falha ao obter arestas do nó: {str(e)}")
            return []
    
    def get_entities_by_type(
        self, 
        graph_id: str, 
        entity_type: str
    ) -> List[NodeInfo]:
        """
        Obter entidades por tipo
        
        Args:
            graph_id: ID do grafo
            entity_type: tipo de entidade (ex: Student, PublicFigure etc.)
            
        Returns:
            Lista de entidades que correspondem ao tipo
        """
        logger.info(f"Obtendo entidades do tipo {entity_type}...")
        
        all_nodes = self.get_all_nodes(graph_id)
        
        filtered = []
        for node in all_nodes:
            # Verificar se labels contém o tipo especificado
            if entity_type in node.labels:
                filtered.append(node)
        
        logger.info(f"Encontrados {len(filtered)} {entity_type} entidades do tipo")
        return filtered
    
    def get_entity_summary(
        self, 
        graph_id: str, 
        entity_name: str
    ) -> Dict[str, Any]:
        """
        Obter resumo de relações da entidade especificada
        
        Buscar todas as informações relacionadas à entidade e gerar resumo
        
        Args:
            graph_id: ID do grafo
            entity_name: Nome da entidade
            
        Returns:
            Informações do resumo da entidade
        """
        logger.info(f"Obtendo entidade {entity_name} resumo de relações...")
        
        # Primeiro buscar informações relacionadas à entidade
        search_result = self.search_graph(
            graph_id=graph_id,
            query=entity_name,
            limit=20
        )
        
        # Tentar encontrar a entidade em todos os nós
        all_nodes = self.get_all_nodes(graph_id)
        entity_node = None
        for node in all_nodes:
            if node.name.lower() == entity_name.lower():
                entity_node = node
                break
        
        related_edges = []
        if entity_node:
            # Passar o parâmetro graph_id
            related_edges = self.get_node_edges(graph_id, entity_node.uuid)
        
        return {
            "entity_name": entity_name,
            "entity_info": entity_node.to_dict() if entity_node else None,
            "related_facts": search_result.facts,
            "related_edges": [e.to_dict() for e in related_edges],
            "total_relations": len(related_edges)
        }
    
    def get_graph_statistics(self, graph_id: str) -> Dict[str, Any]:
        """
        Obter informações estatísticas do grafo
        
        Args:
            graph_id: ID do grafo
            
        Returns:
            Informações estatísticas
        """
        logger.info(f"Obtendo informações estatísticas do grafo {graph_id}...")
        
        nodes = self.get_all_nodes(graph_id)
        edges = self.get_all_edges(graph_id)
        
        # Distribuição de tipos de entidade
        entity_types = {}
        for node in nodes:
            for label in node.labels:
                if label not in ["Entity", "Node"]:
                    entity_types[label] = entity_types.get(label, 0) + 1
        
        # Distribuição de tipos de relação
        relation_types = {}
        for edge in edges:
            relation_types[edge.name] = relation_types.get(edge.name, 0) + 1
        
        return {
            "graph_id": graph_id,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "entity_types": entity_types,
            "relation_types": relation_types
        }
    
    def get_simulation_context(
        self, 
        graph_id: str,
        simulation_requirement: str,
        limit: int = 30
    ) -> Dict[str, Any]:
        """
        Obter informações de contexto relacionadas à simulação
        
        Busca abrangente de todas as informações relacionadas aos requisitos de simulação
        
        Args:
            graph_id: ID do grafo
            simulation_requirement: Descrição dos requisitos de simulação
            limit: Limite de quantidade por categoria de informação
            
        Returns:
            Informações de contexto da simulação
        """
        logger.info(f"Obtendo contexto de simulação: {simulation_requirement[:50]}...")
        
        # Buscar informações relacionadas aos requisitos de simulação
        search_result = self.search_graph(
            graph_id=graph_id,
            query=simulation_requirement,
            limit=limit
        )
        
        # Obter estatísticas do grafo
        stats = self.get_graph_statistics(graph_id)
        
        # Obter todos os nós de entidade
        all_nodes = self.get_all_nodes(graph_id)
        
        # Filtrar entidades com tipo real (não apenas nós Entity puros)
        entities = []
        for node in all_nodes:
            custom_labels = [l for l in node.labels if l not in ["Entity", "Node"]]
            if custom_labels:
                entities.append({
                    "name": node.name,
                    "type": custom_labels[0],
                    "summary": node.summary
                })
        
        return {
            "simulation_requirement": simulation_requirement,
            "related_facts": search_result.facts,
            "graph_statistics": stats,
            "entities": entities[:limit],  # Limitar quantidade
            "total_entities": len(entities)
        }
    
    # ========== Ferramentas de busca principais (otimizadas) ==========
    
    def insight_forge(
        self,
        graph_id: str,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_sub_queries: int = 5
    ) -> InsightForgeResult:
        """
        [InsightForge - Busca de Insight Profundo]
        
        A função de busca híbrida mais poderosa, decompõe automaticamente a questão e busca em múltiplas dimensões:
        1. Usa LLM para decompor a questão em múltiplas subperguntas
        2. Realiza busca semântica para cada subpergunta
        3. Extrai entidades relevantes e obtém suas informações detalhadas
        4. Rastreia cadeias de relações
        5. Integra todos os resultados, gerando insights profundos
        
        Args:
            graph_id: ID do grafo
            query: pergunta do usuário
            simulation_requirement: Descrição dos requisitos de simulação
            report_context: contexto do relatório (opcional, para geração mais precisa de subperguntas)
            max_sub_queries: quantidade máxima de subperguntas
            
        Returns:
            InsightForgeResult: resultado da busca de insight profundo
        """
        logger.info(f"InsightForge busca de insight profundo: {query[:50]}...")
        
        result = InsightForgeResult(
            query=query,
            simulation_requirement=simulation_requirement,
            sub_queries=[]
        )
        
        # Step 1: Usar LLM para gerar subperguntas
        sub_queries = self._generate_sub_queries(
            query=query,
            simulation_requirement=simulation_requirement,
            report_context=report_context,
            max_queries=max_sub_queries
        )
        result.sub_queries = sub_queries
        logger.info(f"Geradas {len(sub_queries)} subperguntas")
        
        # Step 2: Realizar busca semântica para cada subpergunta
        all_facts = []
        all_edges = []
        seen_facts = set()
        
        for sub_query in sub_queries:
            search_result = self.search_graph(
                graph_id=graph_id,
                query=sub_query,
                limit=15,
                scope="edges"
            )
            
            for fact in search_result.facts:
                if fact not in seen_facts:
                    all_facts.append(fact)
                    seen_facts.add(fact)
            
            all_edges.extend(search_result.edges)
        
        # Também buscar a questão original
        main_search = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=20,
            scope="edges"
        )
        for fact in main_search.facts:
            if fact not in seen_facts:
                all_facts.append(fact)
                seen_facts.add(fact)
        
        result.semantic_facts = all_facts
        result.total_facts = len(all_facts)
        
        # Step 3: Extrair UUIDs de entidades relevantes das arestas, obter apenas informações dessas entidades (não obter todos os nós)
        entity_uuids = set()
        for edge_data in all_edges:
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                if source_uuid:
                    entity_uuids.add(source_uuid)
                if target_uuid:
                    entity_uuids.add(target_uuid)
        
        # Obter detalhes de todas as entidades relevantes (sem limite de quantidade, saída completa)
        entity_insights = []
        node_map = {}  # Para construção posterior de cadeias de relações
        
        for uuid in list(entity_uuids):  # Processar todas as entidades, sem truncar
            if not uuid:
                continue
            try:
                # Obter informações de cada nó relacionado individualmente
                node = self.get_node_detail(uuid)
                if node:
                    node_map[uuid] = node
                    entity_type = next((l for l in node.labels if l not in ["Entity", "Node"]), "entidade")
                    
                    # Obter todos os fatos relacionados a esta entidade (sem truncar)
                    related_facts = [
                        f for f in all_facts 
                        if node.name.lower() in f.lower()
                    ]
                    
                    entity_insights.append({
                        "uuid": node.uuid,
                        "name": node.name,
                        "type": entity_type,
                        "summary": node.summary,
                        "related_facts": related_facts  # Saída completa, sem truncar
                    })
            except Exception as e:
                logger.debug(f"Obtendo nó {uuid} falhou: {e}")
                continue
        
        result.entity_insights = entity_insights
        result.total_entities = len(entity_insights)
        
        # Step 4: Construir todas as cadeias de relações (sem limite de quantidade)
        relationship_chains = []
        for edge_data in all_edges:  # Processar todas as arestas, sem truncar
            if isinstance(edge_data, dict):
                source_uuid = edge_data.get('source_node_uuid', '')
                target_uuid = edge_data.get('target_node_uuid', '')
                relation_name = edge_data.get('name', '')
                
                source_name = node_map.get(source_uuid, NodeInfo('', '', [], '', {})).name or source_uuid[:8]
                target_name = node_map.get(target_uuid, NodeInfo('', '', [], '', {})).name or target_uuid[:8]
                
                chain = f"{source_name} --[{relation_name}]--> {target_name}"
                if chain not in relationship_chains:
                    relationship_chains.append(chain)
        
        result.relationship_chains = relationship_chains
        result.total_relationships = len(relationship_chains)
        
        logger.info(f"InsightForge concluído: {result.total_facts} fatos, {result.total_entities} entidades, {result.total_relationships} relações")
        return result
    
    def _generate_sub_queries(
        self,
        query: str,
        simulation_requirement: str,
        report_context: str = "",
        max_queries: int = 5
    ) -> List[str]:
        """
        Usar LLM para gerar subperguntas
        
        Decompor uma questão complexa em múltiplas subperguntas que podem ser buscadas independentemente
        """
        system_prompt = """Você é um especialista profissional em análise de questões. Sua tarefa é decompor uma questão complexa em múltiplas subperguntas que podem ser observadas independentemente no mundo simulado.

Requisitos:
1. Cada subpergunta deve ser específica o suficiente para encontrar comportamentos ou eventos de Agent relacionados no mundo simulado
2. As subperguntas devem cobrir diferentes dimensões da questão original (como: quem, o quê, por quê, como, quando, onde)
3. As subperguntas devem ser relevantes ao cenário de simulação
4. Retornar em formato JSON: {"sub_queries": ["subpergunta1", "subpergunta2", ...]}"""

        user_prompt = f"""Contexto dos requisitos de simulação:
{simulation_requirement}

{f"Contexto do relatório:{report_context[:500]}" if report_context else ""}

Por favor, decomponha a seguinte questão em {max_queries} subperguntas:
{query}

Retorne a lista de subperguntas em formato JSON."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            sub_queries = response.get("sub_queries", [])
            # Garantir que é uma lista de strings
            return [str(sq) for sq in sub_queries[:max_queries]]
            
        except Exception as e:
            logger.warning(f"Falha ao gerar subperguntas: {str(e)}, usando subperguntas padrão")
            # Degradação: retornar variantes baseadas na questão original
            return [
                query,
                f"{query} principais participantes",
                f"{query} causas e impactos",
                f"{query} processo de desenvolvimento"
            ][:max_queries]
    
    def panorama_search(
        self,
        graph_id: str,
        query: str,
        include_expired: bool = True,
        limit: int = 50
    ) -> PanoramaResult:
        """
        [PanoramaSearch - Busca Ampla]
        
        Obter visão panorâmica completa, incluindo todo o conteúdo relevante e informações históricas/expiradas:
        1. Obter todos os nós relevantes
        2. Obter todas as arestas (incluindo expiradas/invalidadas)
        3. Classificar e organizar informações atuais válidas e históricas
        
        Esta ferramenta é adequada para cenários que requerem compreender a visão geral de eventos e rastrear processos de evolução.
        
        Args:
            graph_id: ID do grafo
            query: consulta de busca (para ordenação por relevância)
            include_expired: Se deve incluir conteúdo expirado (padrão True)
            limit: limite de quantidade de resultados retornados
            
        Returns:
            PanoramaResult: resultado da busca ampla
        """
        logger.info(f"PanoramaSearch busca ampla: {query[:50]}...")
        
        result = PanoramaResult(query=query)
        
        # Obter todos os nós
        all_nodes = self.get_all_nodes(graph_id)
        node_map = {n.uuid: n for n in all_nodes}
        result.all_nodes = all_nodes
        result.total_nodes = len(all_nodes)
        
        # Obter todas as arestas (com informações temporais)
        all_edges = self.get_all_edges(graph_id, include_temporal=True)
        result.all_edges = all_edges
        result.total_edges = len(all_edges)
        
        # Classificar fatos
        active_facts = []
        historical_facts = []
        
        for edge in all_edges:
            if not edge.fact:
                continue
            
            # Adicionar nomes de entidades aos fatos
            source_name = node_map.get(edge.source_node_uuid, NodeInfo('', '', [], '', {})).name or edge.source_node_uuid[:8]
            target_name = node_map.get(edge.target_node_uuid, NodeInfo('', '', [], '', {})).name or edge.target_node_uuid[:8]
            
            # Verificar se expirou/foi invalidado
            is_historical = edge.is_expired or edge.is_invalid
            
            if is_historical:
                # Fatos históricos/expirados, adicionar marcação temporal
                valid_at = edge.valid_at or "desconhecido"
                invalid_at = edge.invalid_at or edge.expired_at or "desconhecido"
                fact_with_time = f"[{valid_at} - {invalid_at}] {edge.fact}"
                historical_facts.append(fact_with_time)
            else:
                # Fatos atualmente válidos
                active_facts.append(edge.fact)
        
        # Ordenação por relevância baseada na consulta
        query_lower = query.lower()
        keywords = [w.strip() for w in query_lower.replace(',', ' ').replace('，', ' ').split() if len(w.strip()) > 1]
        
        def relevance_score(fact: str) -> int:
            fact_lower = fact.lower()
            score = 0
            if query_lower in fact_lower:
                score += 100
            for kw in keywords:
                if kw in fact_lower:
                    score += 10
            return score
        
        # Ordenar e limitar quantidade
        active_facts.sort(key=relevance_score, reverse=True)
        historical_facts.sort(key=relevance_score, reverse=True)
        
        result.active_facts = active_facts[:limit]
        result.historical_facts = historical_facts[:limit] if include_expired else []
        result.active_count = len(active_facts)
        result.historical_count = len(historical_facts)
        
        logger.info(f"PanoramaSearch concluído: {result.active_count} válidos, {result.historical_count} históricos")
        return result
    
    def quick_search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10
    ) -> SearchResult:
        """
        [QuickSearch - Busca Simples]
        
        Ferramenta de busca rápida e leve:
        1. Chamar diretamente a busca semântica do Zep
        2. Retornar os resultados mais relevantes
        3. Adequada para necessidades de busca simples e diretas
        
        Args:
            graph_id: ID do grafo
            query: consulta de busca
            limit: quantidade de resultados retornados
            
        Returns:
            SearchResult: resultado de busca
        """
        logger.info(f"QuickSearch busca simples: {query[:50]}...")
        
        # Chamar diretamente o método search_graph existente
        result = self.search_graph(
            graph_id=graph_id,
            query=query,
            limit=limit,
            scope="edges"
        )
        
        logger.info(f"QuickSearch concluído: {result.total_count} resultados")
        return result
    
    def interview_agents(
        self,
        simulation_id: str,
        interview_requirement: str,
        simulation_requirement: str = "",
        max_agents: int = 5,
        custom_questions: List[str] = None
    ) -> InterviewResult:
        """
        [InterviewAgents - Entrevista Aprofundada]
        
        Chamar a API real de entrevista OASIS, entrevistar Agents em execução na simulação:
        1. Ler automaticamente o arquivo de perfis, conhecer todos os Agents de simulação
        2. Usar LLM para analisar requisitos de entrevista, selecionar inteligentemente os Agents mais relevantes
        3. Usar LLM para gerar perguntas de entrevista
        4. Chamar a interface /api/simulation/interview/batch para entrevista real (entrevista simultânea em duas plataformas)
        5. Integrar todos os resultados de entrevista, gerar relatório de entrevista
        
        [IMPORTANTE] Esta funcionalidade requer que o ambiente de simulação esteja em execução (ambiente OASIS não fechado)
        
        [Cenários de uso]
        - Necessidade de entender perspectivas de eventos de diferentes papéis
        - Necessidade de coletar opiniões e pontos de vista de múltiplas partes
        - Necessidade de obter respostas reais dos Agents de simulação (não simulação LLM)
        
        Args:
            simulation_id: ID da simulação (para localizar arquivo de perfis e chamar API de entrevista)
            interview_requirement: descrição dos requisitos de entrevista (não estruturada, ex: "entender a visão dos estudantes sobre o evento")
            simulation_requirement: contexto dos requisitos de simulação (opcional)
            max_agents: quantidade máxima de Agents a entrevistar
            custom_questions: perguntas de entrevista personalizadas (opcional, se não fornecidas serão geradas automaticamente)
            
        Returns:
            InterviewResult: resultado da entrevista
        """
        from .simulation_runner import SimulationRunner
        
        logger.info(f"InterviewAgents entrevista aprofundada (API real): {interview_requirement[:50]}...")
        
        result = InterviewResult(
            interview_topic=interview_requirement,
            interview_questions=custom_questions or []
        )
        
        # Step 1: Ler arquivo de perfis
        profiles = self._load_agent_profiles(simulation_id)
        
        if not profiles:
            logger.warning(f"Perfis de Agent não encontrados para simulação {simulation_id}")
            result.summary = "Arquivo de perfis de Agents para entrevista não encontrado"
            return result
        
        result.total_agents = len(profiles)
        logger.info(f"Carregados {len(profiles)} perfis de Agent")
        
        # Step 2: Usar LLM para selecionar Agents a entrevistar (retornar lista de agent_id)
        selected_agents, selected_indices, selection_reasoning = self._select_agents_for_interview(
            profiles=profiles,
            interview_requirement=interview_requirement,
            simulation_requirement=simulation_requirement,
            max_agents=max_agents
        )
        
        result.selected_agents = selected_agents
        result.selection_reasoning = selection_reasoning
        logger.info(f"Selecionados {len(selected_agents)} Agents para entrevista: {selected_indices}")
        
        # Step 3: Gerar perguntas de entrevista (se não fornecidas)
        if not result.interview_questions:
            result.interview_questions = self._generate_interview_questions(
                interview_requirement=interview_requirement,
                simulation_requirement=simulation_requirement,
                selected_agents=selected_agents
            )
            logger.info(f"Geradas {len(result.interview_questions)} perguntas de entrevista")
        
        # Combinar perguntas em um único prompt de entrevista
        combined_prompt = "\n".join([f"{i+1}. {q}" for i, q in enumerate(result.interview_questions)])
        
        # Adicionar prefixo otimizado, restringir formato de resposta do Agent
        INTERVIEW_PROMPT_PREFIX = (
            "Você está sendo entrevistado. Por favor, combine seu perfil, todas as memórias e ações passadas, "
            "e responda diretamente às seguintes perguntas em texto puro.\n"
            "Requisitos de resposta:\n"
            "1. Responda diretamente em linguagem natural, não chame nenhuma ferramenta\n"
            "2. Não retorne formato JSON ou formato de chamada de ferramenta\n"
            "3. Não use títulos Markdown (como #, ##, ###)\n"
            "4. Responda uma a uma por número de pergunta, cada resposta começando com "Pergunta X:" (X é o número da pergunta)\n"
            "5. Separe as respostas de cada pergunta com uma linha em branco\n"
            "6. As respostas devem ter conteúdo substancial, pelo menos 2-3 frases por pergunta\n\n"
        )
        optimized_prompt = f"{INTERVIEW_PROMPT_PREFIX}{combined_prompt}"
        
        # Step 4: Chamar API de entrevista real (sem especificar plataforma, padrão entrevista simultânea em duas plataformas)
        try:
            # Construir lista de entrevistas em lote (sem especificar plataforma, entrevista em duas plataformas)
            interviews_request = []
            for agent_idx in selected_indices:
                interviews_request.append({
                    "agent_id": agent_idx,
                    "prompt": optimized_prompt  # Usar prompt otimizado
                    # Sem especificar plataforma, API entrevistará em ambas as plataformas twitter e reddit
                })
            
            logger.info(f"Chamando API de entrevista em lote (duas plataformas): {len(interviews_request)} Agents")
            
            # Chamar método de entrevista em lote do SimulationRunner (sem passar plataforma, entrevista em duas plataformas)
            api_result = SimulationRunner.interview_agents_batch(
                simulation_id=simulation_id,
                interviews=interviews_request,
                platform=None,  # Sem especificar plataforma, entrevista em duas plataformas
                timeout=180.0   # Duas plataformas precisam de timeout mais longo
            )
            
            logger.info(f"API de entrevista retornou: {api_result.get('interviews_count', 0)} resultados, success={api_result.get('success')}")
            
            # Verificar se a chamada de API foi bem-sucedida
            if not api_result.get("success", False):
                error_msg = api_result.get("error", "erro desconhecido")
                logger.warning(f"API de entrevista retornou falha: {error_msg}")
                result.summary = f"Falha na chamada da API de entrevista: {error_msg}. Por favor, verifique o estado do ambiente de simulação OASIS."
                return result
            
            # Step 5: Analisar resultados retornados pela API, construir objetos AgentInterview
            # Formato de retorno do modo duas plataformas: {"twitter_0": {...}, "reddit_0": {...}, "twitter_1": {...}, ...}
            api_data = api_result.get("result", {})
            results_dict = api_data.get("results", {}) if isinstance(api_data, dict) else {}
            
            for i, agent_idx in enumerate(selected_indices):
                agent = selected_agents[i]
                agent_name = agent.get("realname", agent.get("username", f"Agent_{agent_idx}"))
                agent_role = agent.get("profession", "desconhecido")
                agent_bio = agent.get("bio", "")
                
                # Obter resultados de entrevista deste Agent nas duas plataformas
                twitter_result = results_dict.get(f"twitter_{agent_idx}", {})
                reddit_result = results_dict.get(f"reddit_{agent_idx}", {})
                
                twitter_response = twitter_result.get("response", "")
                reddit_response = reddit_result.get("response", "")

                # Limpar possível envólucro JSON de chamada de ferramenta
                twitter_response = self._clean_tool_call_response(twitter_response)
                reddit_response = self._clean_tool_call_response(reddit_response)

                # Sempre exibir marcação de duas plataformas
                twitter_text = twitter_response if twitter_response else "(nenhuma resposta obtida nesta plataforma)"
                reddit_text = reddit_response if reddit_response else "(nenhuma resposta obtida nesta plataforma)"
                response_text = f"[Resposta da plataforma Twitter]\n{twitter_text}\n\n[Resposta da plataforma Reddit]\n{reddit_text}"

                # Extrair citações-chave (das respostas de ambas as plataformas)
                import re
                combined_responses = f"{twitter_response} {reddit_response}"

                # Limpar texto de resposta: remover marcações, numeração, Markdown e outras interferências
                clean_text = re.sub(r'#{1,6}\s+', '', combined_responses)
                clean_text = re.sub(r'\{[^}]*tool_name[^}]*\}', '', clean_text)
                clean_text = re.sub(r'[*_`|>~\-]{2,}', '', clean_text)
                clean_text = re.sub(r'Pergunta\d+[：:]\s*', '', clean_text)
                clean_text = re.sub(r'【[^】]+】', '', clean_text)

                # Estratégia 1 (principal): Extrair frases completas com conteúdo substantivo
                sentences = re.split(r'[。！？]', clean_text)
                meaningful = [
                    s.strip() for s in sentences
                    if 20 <= len(s.strip()) <= 150
                    and not re.match(r'^[\s\W，,；;：:、]+', s.strip())
                    and not s.strip().startswith(('{', 'Pergunta'))
                ]
                meaningful.sort(key=len, reverse=True)
                key_quotes = [s + "。" for s in meaningful[:3]]

                # Estratégia 2 (complementar): Texto longo dentro de aspas chinesas pareadas
                if not key_quotes:
                    paired = re.findall(r'\u201c([^\u201c\u201d]{15,100})\u201d', clean_text)
                    paired += re.findall(r'\u300c([^\u300c\u300d]{15,100})\u300d', clean_text)
                    key_quotes = [q for q in paired if not re.match(r'^[，,；;：:、]', q)][:3]
                
                interview = AgentInterview(
                    agent_name=agent_name,
                    agent_role=agent_role,
                    agent_bio=agent_bio[:1000],  # Expandir limite de comprimento do bio
                    question=combined_prompt,
                    response=response_text,
                    key_quotes=key_quotes[:5]
                )
                result.interviews.append(interview)
            
            result.interviewed_count = len(result.interviews)
            
        except ValueError as e:
            # Ambiente de simulação não está em execução
            logger.warning(f"Falha na chamada da API de entrevista (ambiente não está em execução?): {e}")
            result.summary = f"Falha na entrevista: {str(e)}. O ambiente de simulação pode estar fechado, verifique se o ambiente OASIS está em execução."
            return result
        except Exception as e:
            logger.error(f"Exceção na chamada da API de entrevista: {e}")
            import traceback
            logger.error(traceback.format_exc())
            result.summary = f"Erro durante o processo de entrevista: {str(e)}"
            return result
        
        # Step 6: Gerar resumo da entrevista
        if result.interviews:
            result.summary = self._generate_interview_summary(
                interviews=result.interviews,
                interview_requirement=interview_requirement
            )
        
        logger.info(f"InterviewAgents concluído: entrevistados {result.interviewed_count} Agents (duas plataformas)")
        return result
    
    @staticmethod
    def _clean_tool_call_response(response: str) -> str:
        """Limpar envólucro de chamada de ferramenta JSON na resposta do Agent, extrair conteúdo real"""
        if not response or not response.strip().startswith('{'):
            return response
        text = response.strip()
        if 'tool_name' not in text[:80]:
            return response
        import re as _re
        try:
            data = json.loads(text)
            if isinstance(data, dict) and 'arguments' in data:
                for key in ('content', 'text', 'body', 'message', 'reply'):
                    if key in data['arguments']:
                        return str(data['arguments'][key])
        except (json.JSONDecodeError, KeyError, TypeError):
            match = _re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
            if match:
                return match.group(1).replace('\\n', '\n').replace('\\"', '"')
        return response

    def _load_agent_profiles(self, simulation_id: str) -> List[Dict[str, Any]]:
        """Carregar arquivo de perfis de Agent da simulação"""
        import os
        import csv
        
        # Construir caminho do arquivo de perfis
        sim_dir = os.path.join(
            os.path.dirname(__file__), 
            f'../../uploads/simulations/{simulation_id}'
        )
        
        profiles = []
        
        # Tentar ler primeiro o formato JSON do Reddit
        reddit_profile_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_profile_path):
            try:
                with open(reddit_profile_path, 'r', encoding='utf-8') as f:
                    profiles = json.load(f)
                logger.info(f"Carregados {len(profiles)} perfis do reddit_profiles.json")
                return profiles
            except Exception as e:
                logger.warning(f"Falha ao ler reddit_profiles.json: {e}")
        
        # Tentar ler formato CSV do Twitter
        twitter_profile_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_profile_path):
            try:
                with open(twitter_profile_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Converter formato CSV para formato unificado
                        profiles.append({
                            "realname": row.get("name", ""),
                            "username": row.get("username", ""),
                            "bio": row.get("description", ""),
                            "persona": row.get("user_char", ""),
                            "profession": "desconhecido"
                        })
                logger.info(f"Carregados {len(profiles)} perfis do reddit_profiles.json")
                return profiles
            except Exception as e:
                logger.warning(f"Falha ao ler twitter_profiles.csv: {e}")
        
        return profiles
    
    def _select_agents_for_interview(
        self,
        profiles: List[Dict[str, Any]],
        interview_requirement: str,
        simulation_requirement: str,
        max_agents: int
    ) -> tuple:
        """
        Usar LLM para selecionar Agents a entrevistar
        
        Returns:
            tuple: (selected_agents, selected_indices, reasoning)
                - selected_agents: lista de informações completas dos Agents selecionados
                - selected_indices: lista de índices dos Agents selecionados (para chamada de API)
                - reasoning: razão da seleção
        """
        
        # Construir lista de resumo de Agents
        agent_summaries = []
        for i, profile in enumerate(profiles):
            summary = {
                "index": i,
                "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                "profession": profile.get("profession", "desconhecido"),
                "bio": profile.get("bio", "")[:200],
                "interested_topics": profile.get("interested_topics", [])
            }
            agent_summaries.append(summary)
        
        system_prompt = """Você é um especialista profissional em planejamento de entrevistas. Sua tarefa é selecionar, a partir da lista de Agents de simulação, os objetos mais adequados para entrevista com base nos requisitos.

Critérios de seleção:
1. A identidade/profissão do Agent é relevante ao tema da entrevista
2. O Agent pode ter pontos de vista únicos ou valiosos
3. Selecionar perspectivas diversificadas (como: apoiadores, opositores, neutros, profissionais etc.)
4. Priorizar papéis diretamente relacionados ao evento

Retornar em formato JSON:
{
    "selected_indices": [lista de índices dos Agents selecionados],
    "reasoning": "explicação da razão da seleção"
}"""

        user_prompt = f"""Requisitos de entrevista:
{interview_requirement}

Contexto da simulação:
{simulation_requirement if simulation_requirement else "Não fornecido"}

Lista de Agents disponíveis (total de {len(agent_summaries)}):
{json.dumps(agent_summaries, ensure_ascii=False, indent=2)}

Por favor, selecione no máximo {max_agents} Agents mais adequados para entrevista e explique a razão da seleção."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            selected_indices = response.get("selected_indices", [])[:max_agents]
            reasoning = response.get("reasoning", "Seleção automática baseada em relevância")
            
            # Obter informações completas dos Agents selecionados
            selected_agents = []
            valid_indices = []
            for idx in selected_indices:
                if 0 <= idx < len(profiles):
                    selected_agents.append(profiles[idx])
                    valid_indices.append(idx)
            
            return selected_agents, valid_indices, reasoning
            
        except Exception as e:
            logger.warning(f"Falha na seleção de Agent por LLM, usando seleção padrão: {e}")
            # Degradação: selecionar os primeiros N
            selected = profiles[:max_agents]
            indices = list(range(min(max_agents, len(profiles))))
            return selected, indices, "Usando estratégia de seleção padrão"
    
    def _generate_interview_questions(
        self,
        interview_requirement: str,
        simulation_requirement: str,
        selected_agents: List[Dict[str, Any]]
    ) -> List[str]:
        """Usar LLM para gerar perguntas de entrevista"""
        
        agent_roles = [a.get("profession", "desconhecido") for a in selected_agents]
        
        system_prompt = """Você é um jornalista/entrevistador profissional. Com base nos requisitos de entrevista, gere 3-5 perguntas de entrevista aprofundadas.

PerguntaRequisitos:
1. Perguntas abertas, encorajando respostas detalhadas
2. Diferentes papéis podem ter respostas diferentes
3. Abranger múltiplas dimensões como fatos, opiniões e sentimentos
4. Linguagem natural, como uma entrevista real
5. Cada pergunta com no máximo 50 caracteres, concisa e clara
6. Perguntar diretamente, sem incluir descrição de contexto ou prefixo

Retornar em formato JSON:{"questions": ["Pergunta1", "Pergunta2", ...]}"""

        user_prompt = f"""Requisitos de entrevista:{interview_requirement}

Contexto da simulação:{simulation_requirement if simulation_requirement else "Não fornecido"}

Papéis dos entrevistados: {', '.join(agent_roles)}

Por favor, gere 3-5 perguntas de entrevista."""

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5
            )
            
            return response.get("questions", [f"Sobre {interview_requirement}, qual é a sua opinião?"])
            
        except Exception as e:
            logger.warning(f"Falha ao gerar perguntas de entrevista: {e}")
            return [
                f"Sobre {interview_requirement}, qual é o seu ponto de vista?",
                "Que impacto isso tem sobre você ou o grupo que você representa?",
                "Como você acha que este problema deveria ser resolvido ou melhorado?"
            ]
    
    def _generate_interview_summary(
        self,
        interviews: List[AgentInterview],
        interview_requirement: str
    ) -> str:
        """Gerar resumo da entrevista"""
        
        if not interviews:
            return "Nenhuma entrevista concluída"
        
        # Coletar todo o conteúdo das entrevistas
        interview_texts = []
        for interview in interviews:
            interview_texts.append(f"【{interview.agent_name}（{interview.agent_role}）】\n{interview.response[:500]}")
        
        system_prompt = """Você é um editor de notícias profissional. Com base nas respostas de múltiplos entrevistados, gere um resumo da entrevista.

Requisitos do resumo:
1. Sintetizar os principais pontos de vista de todas as partes
2. Apontar consensos e divergências nos pontos de vista
3. Destacar citações valiosas
4. Objetivo e neutro, sem favorecer nenhuma parte
5. Limitar a 1000 caracteres

Restrições de formato (devem ser seguidas):
- Usar parágrafos de texto puro, separar diferentes seções com linhas em branco
- Não usar títulos Markdown (como #, ##, ###)
- Não usar linhas de separação (como ---, ***)
- Ao citar palavras originais dos entrevistados, usar aspas
- Pode usar **negrito** para marcar palavras-chave, mas não usar outra sintaxe Markdown"""

        user_prompt = f"""Tema da entrevista: {interview_requirement}

Conteúdo da entrevista:
{"".join(interview_texts)}

Por favor, gere o resumo da entrevista."""

        try:
            summary = self.llm.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return summary
            
        except Exception as e:
            logger.warning(f"Falha ao gerar resumo da entrevista: {e}")
            # Degradação: concatenação simples
            return f"Foram entrevistados {len(interviews)} entrevistados, incluindo: " + "、".join([i.agent_name for i in interviews])
