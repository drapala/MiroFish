"""
Serviço Report Agent
Geração de relatórios de simulação no padrão ReACT usando LangChain + Zep

Funcionalidades:
1. Gerar relatórios com base nos requisitos de simulação e informações do grafo Zep
2. Primeiro planejar a estrutura do índice, depois gerar por seções
3. Cada seção utiliza o padrão ReACT de múltiplas rodadas de pensamento e reflexão
4. Suporte a diálogo com o usuário, chamando autonomamente ferramentas de busca durante o diálogo
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)

logger = get_logger('mirofish.report_agent')


class ReportLogger:
    """
    Registrador de log detalhado do Report Agent
    
    Gera arquivo agent_log.jsonl na pasta do relatório, registrando cada ação detalhada.
    Cada linha é um objeto JSON completo, contendo timestamp, tipo de ação, conteúdo detalhado etc.
    """
    
    def __init__(self, report_id: str):
        """
        Inicializar registrador de log
        
        Args:
            report_id: ID do relatório, usado para determinar o caminho do arquivo de log
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Garantir que o diretório do arquivo de log exista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Obter tempo decorrido desde o início (segundos)"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Registrar uma entrada de log
        
        Args:
            action: tipo de ação, como 'start', 'tool_call', 'llm_response', 'section_complete' etc.
            stage: estágio atual, como 'planning', 'generating', 'completed'
            details: Dicionário de conteúdo detalhado, sem truncar
            section_title: Título da seção atual (opcional)
            section_index: Índice da seção atual (opcional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Escrever em modo de adição no arquivo JSONL
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Registrar início da geração do relatório"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Tarefa de geração de relatório iniciada"
            }
        )
    
    def log_planning_start(self):
        """Registrar início do planejamento do esboço"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Iniciando planejamento do esboço do relatório"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Registrar informações de contexto obtidas durante o planejamento"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Obter informações de contexto da simulação",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Registrar conclusão do planejamento do esboço"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Planejamento do esboço concluído",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Registrar início da geração da seção"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Iniciando geração da seção: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Registrar processo de pensamento ReACT"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT rodada {iteration} de pensamento"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Registrar chamada de ferramenta"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Chamada de ferramenta: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Registrar resultado da chamada de ferramenta (conteúdo completo, sem truncar)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Resultado completo, sem truncar
                "result_length": len(result),
                "message": f"Ferramenta {tool_name} resultado retornado"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Registrar resposta LLM (conteúdo completo, sem truncar)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Resposta completa, sem truncar
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"Resposta LLM (chamada de ferramenta: {has_tool_calls}, resposta final: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Registrar conclusão da geração de conteúdo da seção (apenas registrar conteúdo, não representa conclusão da seção inteira)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Conteúdo completo, sem truncar
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Seção {section_title} geração de conteúdo concluída"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Registrar conclusão da geração da seção

        O frontend deve monitorar este log para determinar se uma seção foi realmente concluída e obter o conteúdo completo
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Seção {section_title} geração concluída"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Registrar conclusão da geração do relatório"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Geração do relatório concluída"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Registrar erro"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Erro ocorrido: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Registrador de log de console do Report Agent
    
    Escreve logs no estilo console (INFO, WARNING etc.) no arquivo console_log.txt na pasta do relatório.
    Estes logs diferem do agent_log.jsonl, sendo saída de console em formato de texto puro.
    """
    
    def __init__(self, report_id: str):
        """
        Inicializar registrador de log de console
        
        Args:
            report_id: ID do relatório, usado para determinar o caminho do arquivo de log
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Garantir que o diretório do arquivo de log exista"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Configurar handler de arquivo, escrever logs simultaneamente no arquivo"""
        import logging
        
        # Criar handler de arquivo
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Usar o mesmo formato conciso do console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Adicionar aos loggers relacionados ao report_agent
        loggers_to_attach = [
            'mirofish.report_agent',
            'mirofish.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Evitar adição duplicada
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Fechar handler de arquivo e remover do logger"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'mirofish.report_agent',
                'mirofish.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Garantir fechamento do handler de arquivo na destruição"""
        self.close()


class ReportStatus(str, Enum):
    """Status do relatório"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Seção do relatório"""
    title: str
    content: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content
        }

    def to_markdown(self, level: int = 2) -> str:
        """Converter para formato Markdown"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Esboço do relatório"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Converter para formato Markdown"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Relatório completo"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Constantes de template de Prompt
# ═══════════════════════════════════════════════════════════════

# -- Descrição das ferramentas --

TOOL_DESC_INSIGHT_FORGE = """\
[Busca de Insight Profundo - Ferramenta de busca poderosa]
Esta é nossa função de busca poderosa, projetada para análise profunda. Ela irá:
1. Decompor automaticamente sua questão em múltiplas subperguntas
2. Buscar informações no grafo de simulação em múltiplas dimensões
3. Integrar resultados de busca semântica, análise de entidades e rastreamento de cadeias de relações
4. Retornar o conteúdo de busca mais abrangente e profundo

[Cenários de uso]
- Necessidade de analisar profundamente um tópico
- Necessidade de entender múltiplos aspectos de um evento
- Necessidade de obter material rico para suportar seções do relatório

[Conteúdo retornado]
- Texto original de fatos relevantes (pode ser citado diretamente)
- Insights de entidades principais
- Análise de cadeias de relações"""

TOOL_DESC_PANORAMA_SEARCH = """\
[Busca Ampla - Obter visão panorâmica]
Esta ferramenta é usada para obter a visão completa dos resultados de simulação, especialmente adequada para entender processos de evolução de eventos. Ela irá:
1. Obter todos os nós e relações relevantes
2. Distinguir fatos atualmente válidos e fatos históricos/expirados
3. Ajudar a entender como a opinião pública evoluiu

[Cenários de uso]
- Necessidade de entender a linha completa de desenvolvimento do evento
- Necessidade de comparar mudanças na opinião pública em diferentes estágios
- Necessidade de obter informações abrangentes de entidades e relações

[Conteúdo retornado]
- Fatos válidos atuais (resultados mais recentes da simulação)
- Fatos históricos/expirados (registros de evolução)
- Todas as entidades envolvidas"""

TOOL_DESC_QUICK_SEARCH = """\
[Busca Simples - Busca rápida]
Ferramenta de busca rápida e leve, adequada para consultas de informação simples e diretas.

[Cenários de uso]
- Necessidade de encontrar rapidamente uma informação específica
- Necessidade de verificar um fato
- Busca simples de informações

[Conteúdo retornado]
- Lista de fatos mais relevantes para a consulta"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Entrevista Aprofundada - Entrevista real de Agents (duas plataformas)]
Chamar a API de entrevista do ambiente de simulação OASIS, realizar entrevistas reais com Agents de simulação em execução!
Isto não é simulação LLM, mas chamada à interface de entrevista real para obter respostas originais dos Agents de simulação.
Por padrão, entrevista simultaneamente nas duas plataformas Twitter e Reddit, obtendo perspectivas mais abrangentes.

Fluxo de funcionalidades:
1. Ler automaticamente arquivo de perfis, conhecer todos os Agents de simulação
2. Selecionar inteligentemente os Agents mais relevantes ao tema da entrevista (como estudantes, mídia, oficiais etc.)
3. Gerar automaticamente perguntas de entrevista
4. Chamar interface /api/simulation/interview/batch para entrevista real em duas plataformas
5. Integrar todos os resultados de entrevista, fornecendo análise multiperspectiva

[Cenários de uso]
- Necessidade de entender perspectivas de eventos de diferentes papéis (como os estudantes veem? como a mídia vê? o que dizem as autoridades?)
- Necessidade de coletar opiniões e posições de múltiplas partes
- Necessidade de obter respostas reais dos Agents de simulação (do ambiente de simulação OASIS)
- Desejo de tornar o relatório mais vívido, incluindo "transcrições de entrevistas"

[Conteúdo retornado]
- Informações de identidade dos Agents entrevistados
- Respostas de entrevista de cada Agent nas duas plataformas Twitter e Reddit
- Citações-chave (podem ser citadas diretamente)
- Resumo da entrevista e comparação de pontos de vista

[IMPORTANTE] O ambiente de simulação OASIS precisa estar em execução para usar esta funcionalidade!"""

# -- Prompt de planejamento de esboço --

PLAN_SYSTEM_PROMPT = """\
Você é um especialista na redação de "relatórios de previsão futura", com uma "visão de Deus" do mundo simulado — você pode observar o comportamento, discurso e interações de cada Agent na simulação.

[Conceito Central]
Construímos um mundo simulado e injetamos "requisitos de simulação" específicos como variáveis. Os resultados da evolução do mundo simulado são previsões do que pode acontecer no futuro. O que você está observando não são "dados experimentais", mas uma "pré-estreia do futuro".

[Sua Tarefa]
Redigir um "relatório de previsão futura", respondendo:
1. Sob as condições que definimos, o que aconteceu no futuro?
2. Como os diversos Agents (grupos de pessoas) reagiram e agiram?
3. Que tendências e riscos futuros dignos de atenção esta simulação revelou?

[Posicionamento do Relatório]
- Este é um relatório de previsão futura baseado em simulação, revelando "se for assim, como será o futuro"
- Foco nos resultados de previsão: direção dos eventos, reações coletivas, fenômenos emergentes, riscos potenciais
- O discurso e ações dos Agents no mundo simulado são previsões do comportamento futuro das pessoas
- NAO é uma análise da situação atual do mundo real
- NAO é um resumo genérico de opinião pública

[Limite de Número de Seções]
- Mínimo 2 seções, máximo 5 seções
- Não precisa de subseções, cada seção é redigida diretamente com conteúdo completo
- Conteúdo deve ser refinado, focado nas descobertas de previsão principais
- A estrutura das seções é projetada autonomamente por você com base nos resultados de previsão

Por favor, produza o esboço do relatório em formato JSON, conforme abaixo:
{
    "title": "Título do relatório",
    "summary": "Resumo do relatório (uma frase sintetizando a descoberta de previsão principal)",
    "sections": [
        {
            "title": "Título da seção",
            "description": "Descrição do conteúdo da seção"
        }
    ]
}

Atenção: o array sections deve ter no mínimo 2 e no máximo 5 elementos!"""

PLAN_USER_PROMPT_TEMPLATE = """\
[Configuração do Cenário de Previsão]
Variáveis injetadas no mundo simulado (requisitos de simulação): {simulation_requirement}

[Escala do Mundo Simulado]
- Quantidade de entidades participantes da simulação: {total_nodes}
- Quantidade de relações geradas entre entidades: {total_edges}
- Distribuição de tipos de entidade: {entity_types}
- Quantidade de Agents ativos: {total_entities}

[Amostra de Fatos Futuros Previstos pela Simulação]
{related_facts_json}

Por favor, examine esta pré-estreia do futuro com a "visão de Deus":
1. Sob as condições que definimos, que estado o futuro apresentou?
2. Como os diversos grupos de pessoas (Agents) reagiram e agiram?
3. Que tendências futuras dignos de atenção esta simulação revelou?

Com base nos resultados de previsão, projete a estrutura de seções mais adequada para o relatório.

[Lembrete] Número de seções do relatório: mínimo 2, máximo 5, conteúdo deve ser refinado e focado nas descobertas de previsão principais."""

# -- Prompt de geração de seção --

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
Você é um especialista na redação de "relatórios de previsão futura", atualmente redigindo uma seção do relatório.

Título do relatório: {report_title}
Resumo do relatório: {report_summary}
Cenário de previsão (requisitos de simulação): {simulation_requirement}

Seção atual a ser redigida: {section_title}

═══════════════════════════════════════════════════════════════
[Conceito Central]
═══════════════════════════════════════════════════════════════

O mundo simulado é uma pré-estreia do futuro. Injetamos condições específicas (requisitos de simulação) no mundo simulado,
e o comportamento e interações dos Agents na simulação são previsões do comportamento futuro das pessoas.

Sua tarefa é:
- Revelar o que aconteceu no futuro sob as condições definidas
- Prever como os diversos grupos de pessoas (Agents) reagiram e agiram
- Descobrir tendências futuras, riscos e oportunidades dignos de atenção

NAO escreva como uma análise da situação atual do mundo real
Foque em "como será o futuro" - os resultados da simulação são o futuro previsto

═══════════════════════════════════════════════════════════════
[Regras Mais Importantes - Devem Ser Seguidas]
═══════════════════════════════════════════════════════════════

1. [Deve chamar ferramentas para observar o mundo simulado]
   - Você está observando a pré-estreia do futuro com a "visão de Deus"
   - Todo conteúdo deve vir de eventos e discurso/ações dos Agents no mundo simulado
   - Proibido usar seu próprio conhecimento para escrever o conteúdo do relatório
   - Cada seção deve chamar ferramentas pelo menos 3 vezes (máximo 5) para observar o mundo simulado, que representa o futuro

2. [Deve citar o discurso/ações originais dos Agents]
   - O discurso e comportamento dos Agents são previsões do comportamento futuro das pessoas
   - Use formato de citação no relatório para exibir estas previsões, por exemplo:
     > "Certo grupo de pessoas expressaria: conteúdo original..."
   - Estas citações são evidências centrais da previsão de simulação

3. [Consistência linguística - Conteúdo citado deve ser traduzido para o idioma do relatório]
   - O conteúdo retornado pelas ferramentas pode conter expressões em inglês ou mistas
   - Se os requisitos de simulação e materiais originais estiverem em português, o relatório deve ser inteiramente redigido em português
   - Ao citar conteúdo em inglês ou misto retornado pelas ferramentas, deve traduzir para português fluente antes de escrever no relatório
   - Ao traduzir, manter o sentido original inalterado, garantindo expressão natural e fluente
   - Esta regra se aplica tanto ao texto principal quanto ao conteúdo em blocos de citação (formato >)

4. [Apresentar fielmente os resultados de previsão]
   - O conteúdo do relatório deve refletir os resultados de simulação que representam o futuro no mundo simulado
   - Não adicionar informações que não existem na simulação
   - Se houver informação insuficiente em algum aspecto, informar honestamente

═══════════════════════════════════════════════════════════════
[Normas de Formato - Extremamente Importante!]
═══════════════════════════════════════════════════════════════

[Uma seção = unidade mínima de conteúdo]
- Cada seção é a unidade mínima de divisão do relatório
- Proibido usar qualquer título Markdown dentro da seção (#, ##, ###, #### etc.)
- Proibido adicionar título principal da seção no início do conteúdo
- O título da seção é adicionado automaticamente pelo sistema, você só precisa redigir o conteúdo do texto
- Use **negrito**, separação de parágrafos, citações e listas para organizar o conteúdo, mas não use títulos

[Exemplo correto]
```
Esta seção analisou a dinâmica de propagação da opinião pública do evento. Através da análise aprofundada dos dados de simulação, descobrimos...

**Fase de detonação inicial**

O Weibo, como primeiro local da opinião pública, assumiu a função central de publicação inicial de informações:

> "O Weibo contribuiu com 68% do volume inicial de voz..."

**Fase de amplificação emocional**

A plataforma TikTok amplificou ainda mais o impacto do evento:

- Forte impacto visual
- Alto grau de ressonância emocional
```

[Exemplo incorreto]
```
## Resumo executivo          <-- Errado! Não adicione nenhum título
### Um, Fase inicial     <-- Errado! Não use ### para dividir subseções
#### 1.1 Análise detalhada   <-- Errado! Não use #### para subdividir

Esta seção analisou...
```

═══════════════════════════════════════════════════════════════
[Ferramentas de busca disponíveis] (chamar 3-5 vezes por seção)
═══════════════════════════════════════════════════════════════

{tools_description}

[Sugestões de uso de ferramentas - Por favor, misture diferentes ferramentas, não use apenas uma]
- insight_forge: análise de insight profundo, decompõe automaticamente questões e busca fatos e relações em múltiplas dimensões
- panorama_search: busca panorâmica ampla, entender visão geral do evento, linha do tempo e processo de evolução
- quick_search: verificar rapidamente um ponto de informação específico
- interview_agents: entrevistar Agents de simulação, obter perspectivas em primeira pessoa e reações reais de diferentes papéis

═══════════════════════════════════════════════════════════════
[Fluxo de Trabalho]
═══════════════════════════════════════════════════════════════

Em cada resposta você só pode fazer uma das duas coisas seguintes (não pode fazer ambas simultaneamente):

Opção A - Chamar ferramenta:
Produza seu pensamento, depois chame uma ferramenta no seguinte formato:
<tool_call>
{{"name": "nome_da_ferramenta", "parameters": {{"nome_do_parametro": "valor_do_parametro"}}}}
</tool_call>
O sistema executará a ferramenta e retornará os resultados para você. Você não precisa e não pode escrever os resultados de retorno da ferramenta você mesmo.

Opção B - Produzir conteúdo final:
Quando você obteve informação suficiente através das ferramentas, produza o conteúdo da seção começando com "Final Answer:".

Estritamente proibido:
- Proibido incluir chamada de ferramenta e Final Answer na mesma resposta
- Proibido fabricar resultados de retorno de ferramenta (Observation), todos os resultados de ferramentas são injetados pelo sistema
- Cada resposta pode chamar no máximo uma ferramenta

═══════════════════════════════════════════════════════════════
[Requisitos de Conteúdo da Seção]
═══════════════════════════════════════════════════════════════

1. O conteúdo deve ser baseado em dados de simulação obtidos pelas ferramentas
2. Citar abundantemente o texto original para demonstrar os efeitos da simulação
3. Usar formato Markdown (mas proibido usar títulos):
   - Usar **texto em negrito** para marcar pontos importantes (substituindo subtítulos)
   - Usar listas (- ou 1.2.3.) para organizar pontos-chave
   - Usar linhas em branco para separar diferentes parágrafos
   - Proibido usar qualquer sintaxe de título como #, ##, ###, ####
4. [Norma de formato de citação - Deve ser um parágrafo independente]
   A citação deve ser um parágrafo independente, com uma linha em branco antes e depois, não pode ser misturada no parágrafo:

   Formato correto:
   ```
   A resposta da escola foi considerada carente de conteúdo substantivo.

   > "O modo de resposta da escola parece rígido e lento no ambiente de mídia social em rápida mudança."

   Esta avaliação reflete a insatisfação generalizada do público.
   ```

   Formato incorreto:
   ```
   A resposta da escola foi considerada carente de conteúdo substantivo.> "O modo de resposta da escola..." Esta avaliação reflete...
   ```
5. Manter coerência lógica com outras seções
6. [Evitar repetição] Leia cuidadosamente o conteúdo das seções já concluídas abaixo, não repita a descrição das mesmas informações
7. [Reiterando] Não adicione nenhum título! Use **negrito** em vez de subtítulos"""

SECTION_USER_PROMPT_TEMPLATE = """\
Conteúdo das seções já concluídas (leia cuidadosamente, evite repetição):
{previous_content}

═══════════════════════════════════════════════════════════════
[Tarefa Atual] Redigir seção: {section_title}
═══════════════════════════════════════════════════════════════

[Lembrete Importante]
1. Leia cuidadosamente as seções já concluídas acima, evite repetir o mesmo conteúdo!
2. Antes de começar, deve chamar ferramentas para obter dados de simulação
3. Por favor, misture diferentes ferramentas, não use apenas uma
4. O conteúdo do relatório deve vir dos resultados de busca, não use seu próprio conhecimento

[Aviso de Formato - Deve Ser Seguido]
- Não escreva nenhum título (#, ##, ###, #### nenhum é permitido)
- Não escreva "{section_title}" como início
- O título da seção é adicionado automaticamente pelo sistema
- Escreva diretamente o texto, use **negrito** em vez de subtítulos

Por favor, comece:
1. Primeiro pense (Thought) em que informações esta seção precisa
2. Depois chame ferramentas (Action) para obter dados de simulação
3. Após coletar informações suficientes, produza Final Answer (texto puro, sem nenhum título)"""

# -- Templates de mensagem do ciclo ReACT --

REACT_OBSERVATION_TEMPLATE = """\
Observation (resultado da busca):

═══ Ferramenta {tool_name} retornou ===
{result}

═══════════════════════════════════════════════════════════════
Ferramentas chamadas {tool_calls_count}/{max_tool_calls} vezes (usadas: {used_tools_str}){unused_hint}
- Se a informação for suficiente: produza o conteúdo da seção começando com "Final Answer:" (deve citar os textos originais acima)
- Se precisar de mais informações: chame uma ferramenta para continuar buscando
═══════════════════════════════════════════════════════════════"""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Atenção] Você chamou apenas {tool_calls_count} ferramentas, são necessárias pelo menos {min_tool_calls} vezes."
    "Por favor, chame mais ferramentas para obter mais dados de simulação, depois produza Final Answer.{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Atualmente foram chamadas apenas {tool_calls_count}  ferramentas, são necessárias pelo menos  {min_tool_calls}  vezes."
    "Por favor, chame ferramentas para obter dados de simulação.{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "O número de chamadas de ferramenta atingiu o limite ({tool_calls_count}/{max_tool_calls}), não é possível chamar mais ferramentas."
    'Por favor, baseando-se nas informações já obtidas, produza imediatamente o conteúdo da seção começando com "Final Answer:".'
)

REACT_UNUSED_TOOLS_HINT = "\n💡 Você ainda não usou: {unused_list}, sugerimos experimentar diferentes ferramentas para obter informações de múltiplas perspectivas"

REACT_FORCE_FINAL_MSG = "O limite de chamadas de ferramenta foi atingido, por favor produza diretamente Final Answer: e gere o conteúdo da seção."

# -- Prompt de Chat --

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
Você é um assistente de previsão de simulação conciso e eficiente.

[Contexto]
Condições de previsão: {simulation_requirement}

[Relatório de Análise Já Gerado]
{report_content}

[Regras]
1. Priorize responder perguntas com base no conteúdo do relatório acima
2. Responda diretamente às perguntas, evitando discursos de pensamento prolixos
3. Somente quando o conteúdo do relatório for insuficiente para responder, chame ferramentas para buscar mais dados
4. As respostas devem ser concisas, claras e organizadas

[Ferramentas Disponíveis] (usar apenas quando necessário, chamar no máximo 1-2 vezes)
{tools_description}

[Formato de Chamada de Ferramenta]
<tool_call>
{{"name": "nome_da_ferramenta", "parameters": {{"nome_do_parametro": "valor_do_parametro"}}}}
</tool_call>

[Estilo de Resposta]
- Conciso e direto, sem longos discursos
- Usar formato > para citar conteúdo-chave
- Priorize dar a conclusão, depois explique a razão"""

CHAT_OBSERVATION_SUFFIX = "\n\nPor favor, responda à pergunta de forma concisa."


# ═══════════════════════════════════════════════════════════════
# Classe principal ReportAgent
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Agent de geração de relatórios de simulação

    Adota o padrão ReACT (Reasoning + Acting):
    1. Fase de planejamento: analisar requisitos de simulação, planejar estrutura do índice do relatório
    2. Fase de geração: gerar conteúdo seção por seção, cada seção pode chamar ferramentas múltiplas vezes para obter informações
    3. Fase de reflexão: verificar completude e precisão do conteúdo
    """
    
    # Número máximo de chamadas de ferramenta (por seções)
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Número máximo de rodadas de reflexão
    MAX_REFLECTION_ROUNDS = 3
    
    # Número máximo de chamadas de ferramenta no diálogo
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None
    ):
        """
        Inicializar Report Agent
        
        Args:
            graph_id: ID do grafo
            simulation_id: ID da simulação
            simulation_requirement: descrição dos requisitos de simulação
            llm_client: cliente LLM (opcional)
            zep_tools: serviço de ferramentas Zep (opcional)
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        
        # Definição de ferramentas
        self.tools = self._define_tools()
        
        # Registrador de log (inicializado em generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Registrador de log de console (inicializado em generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        
        logger.info(f"ReportAgent inicialização concluída: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Definir ferramentas disponíveis"""
        return {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "A questão ou tópico que você quer analisar profundamente",
                    "report_context": "Contexto da seção atual do relatório (opcional, ajuda a gerar subperguntas mais precisas)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Consulta de busca, usada para ordenação por relevância",
                    "include_expired": "Se deve incluir conteúdo expirado/histórico (padrão True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "String de consulta de busca",
                    "limit": "Quantidade de resultados retornados (opcional, padrão 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Tema da entrevista ou descrição dos requisitos (ex: 'entender a visão dos estudantes sobre o evento')",
                    "max_agents": "Quantidade máxima de Agents a entrevistar (opcional, padrão 5, máximo 10)"
                }
            }
        }
    
    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Executar chamada de ferramenta
        
        Args:
            tool_name: nome da ferramenta
            parameters: parâmetros da ferramenta
            report_context: Contexto do relatório (para InsightForge)
            
        Returns:
            Resultado da execução da ferramenta (formato texto)
        """
        logger.info(f"Executando ferramenta: {tool_name}, parâmetros: {parameters}")
        
        try:
            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Busca ampla - obter visão panorâmica
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Busca simples - busca rápida
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Entrevista aprofundada - chamar API real de entrevista OASIS para obter respostas dos Agents de simulação (duas plataformas)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Ferramentas antigas com compatibilidade retroativa (redirecionamento interno para novas ferramentas) ==========
            
            elif tool_name == "search_graph":
                # Redirecionar para quick_search
                logger.info("search_graph redirecionado para quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirecionar para insight_forge, pois é mais poderoso
                logger.info("get_simulation_context redirecionado para insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Ferramenta desconhecida: {tool_name}. Por favor, use uma das seguintes ferramentas: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"Falha na execução da ferramenta: {tool_name}, erro: {str(e)}")
            return f"Falha na execução da ferramenta: {str(e)}"
    
    # Conjunto de nomes de ferramentas válidos, para validação no parsing de fallback de JSON nu
    VALID_TOOL_NAMES = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Analisar chamadas de ferramenta da resposta LLM

        Formatos suportados (por prioridade)：
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. JSON nu (a resposta inteira ou uma única linha é um JSON de chamada de ferramenta)
        """
        tool_calls = []

        # Formato 1: estilo XML (formato padrão)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Formato 2: fallback - LLM produz JSON nu diretamente (sem tags <tool_call>)
        # Tentar apenas quando formato 1 não corresponder, evitando falsa correspondência de JSON no texto
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # A resposta pode conter texto de pensamento + JSON nu, tentar extrair o último objeto JSON
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validar se o JSON analisado é uma chamada de ferramenta válida"""
        # Suporta dois formatos de chave: {"name": ..., "parameters": ...} e {"tool": ..., "params": ...}
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self.VALID_TOOL_NAMES:
            # Unificar nomes de chave para name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Gerar texto de descrição de ferramentas"""
        desc_parts = ["Ferramentas disponíveis:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parâmetros: {params_desc}")
        return "\n".join(desc_parts)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Planejar esboço do relatório
        
        Usar LLM para analisar requisitos de simulação, planejar a estrutura do índice do relatório
        
        Args:
            progress_callback: função de callback de progresso
            
        Returns:
            ReportOutline: esboço do relatório
        """
        logger.info("Iniciando planejamento do esboço do relatório...")
        
        if progress_callback:
            progress_callback("planning", 0, "Analisando requisitos de simulação...")
        
        # Primeiro obter contexto de simulação
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Gerando esboço do relatório...")
        
        system_prompt = PLAN_SYSTEM_PROMPT
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            if progress_callback:
                progress_callback("planning", 80, "Analisando estrutura do esboço...")
            
            # Analisar esboço
            sections = []
            for section_data in response.get("sections", []):
                sections.append(ReportSection(
                    title=section_data.get("title", ""),
                    content=""
                ))
            
            outline = ReportOutline(
                title=response.get("title", "Relatório de Análise de Simulação"),
                summary=response.get("summary", ""),
                sections=sections
            )
            
            if progress_callback:
                progress_callback("planning", 100, "Planejamento do esboço concluído")
            
            logger.info(f"Planejamento do esboço concluído: {len(sections)} seções")
            return outline
            
        except Exception as e:
            logger.error(f"Falha no planejamento do esboço: {str(e)}")
            # Retornar esboço padrão (3 seções, como fallback)
            return ReportOutline(
                title="Relatório de Previsão Futura",
                summary="Análise de tendências futuras e riscos baseada em previsão de simulação",
                sections=[
                    ReportSection(title="Cenário de Previsão e Descobertas Principais"),
                    ReportSection(title="Análise de Previsão de Comportamento de Grupos"),
                    ReportSection(title="Perspectiva de Tendências e Alertas de Risco")
                ]
            )
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0
    ) -> str:
        """
        Gerar conteúdo de uma única seção usando padrão ReACT
        
        Ciclo ReACT:
        1. Thought (pensamento)- Analisar que informações são necessárias
        2. Action (ação)- Chamar ferramentas para obter informações
        3. Observation (observação)- Analisar resultados retornados pelas ferramentas
        4. Repetir até que a informação seja suficiente ou o número máximo seja atingido
        5. Final Answer (resposta final)- Gerar conteúdo da seção
        
        Args:
            section: seção a ser gerada
            outline: esboço completo
            previous_sections: Conteúdo das seções anteriores (para manter coerência)
            progress_callback: callback de progresso
            section_index: Índice da seção (para registro de log)
            
        Returns:
            Conteúdo da seção (formato Markdown)
        """
        logger.info(f"ReACT gerando seção: {section.title}")
        
        # Registrar log de início da seção
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            tools_description=self._get_tools_description(),
        )

        # Construir prompt do usuário - cada seção concluída com máximo de 4000 caracteres
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Cada seção com máximo de 4000 caracteres
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(Esta é a primeira seção)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Ciclo ReACT
        tool_calls_count = 0
        max_iterations = 5  # Número máximo de rodadas de iteração
        min_tool_calls = 3  # Número mínimo de chamadas de ferramenta
        conflict_retries = 0  # Número de conflitos consecutivos de chamada de ferramenta e Final Answer simultâneos
        used_tools = set()  # Registrar nomes de ferramentas já chamadas
        all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}

        # Contexto do relatório, para geração de subperguntas do InsightForge
        report_context = f"Título da seção: {section.title}\nRequisitos de simulação: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Busca profunda e redação em andamento ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Chamar LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Verificar se o retorno do LLM é None (exceção de API ou conteúdo vazio)
            if response is None:
                logger.warning(f"Seção {section.title} iteração {iteration + 1}: LLM retornou None")
                # Se ainda houver rodadas de iteração, adicionar mensagem e tentar novamente
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(resposta vazia)"})
                    messages.append({"role": "user", "content": "Por favor, continue gerando conteúdo."})
                    continue
                # Última iteração também retornou None, sair do loop para encerramento forçado
                break

            logger.debug(f"Resposta LLM: {response[:200]}...")

            # Analisar uma vez, reutilizar resultados
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # -- Tratamento de conflito: LLM produziu chamada de ferramenta e Final Answer simultaneamente --
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Seção {section.title} rodada {iteration+1}: "
                    f"LLM produziu chamada de ferramenta e Final Answer simultaneamente (conflito {conflict_retries})"
                )

                if conflict_retries <= 2:
                    # Primeiras duas vezes: descartar esta resposta, pedir ao LLM que responda novamente
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Erro de formato] Você incluiu chamada de ferramenta e Final Answer na mesma resposta, isso não é permitido.\n"
                            "Cada resposta só pode fazer uma das duas coisas a seguir:\n"
                            "- Chamar uma ferramenta (produzir um bloco <tool_call>, não escrever Final Answer)\n"
                            "- Produzir conteúdo final (começando com 'Final Answer:', não incluir <tool_call>)\n"
                            "Por favor, responda novamente, fazendo apenas uma dessas coisas."
                        ),
                    })
                    continue
                else:
                    # Terceira vez: tratamento degradado, truncar até a primeira chamada de ferramenta, executar forçadamente
                    logger.warning(
                        f"Seção {section.title}: {conflict_retries} conflitos consecutivos, "
                        "degradando para truncar e executar a primeira chamada de ferramenta"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Registrar log de resposta LLM
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # -- Caso 1: LLM produziu Final Answer --
            if has_final_answer:
                # Número insuficiente de chamadas de ferramenta, rejeitar e pedir para continuar chamando ferramentas
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(Estas ferramentas ainda não foram usadas, recomendamos experimentá-las: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                # Encerramento normal
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Seção {section.title} geração concluída(chamadas de ferramenta: {tool_calls_count} vezes)")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Caso 2: LLM tentou chamar ferramenta ──
            if has_tool_calls:
                # Cota de ferramentas esgotada -> informar claramente, pedir para produzir Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Executar apenas a primeira chamada de ferramenta
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM tentou chamar {len(tool_calls)} ferramentas, executando apenas a primeira: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Construir dica de ferramentas não utilizadas
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list="、".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # -- Caso 3: Nem chamada de ferramenta nem Final Answer --
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Número insuficiente de chamadas de ferramenta, recomendar ferramentas não utilizadas
                unused_tools = all_tools - used_tools
                unused_hint = f"(Estas ferramentas ainda não foram usadas, recomendamos experimentá-las: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Chamadas de ferramenta suficientes, LLM produziu conteúdo mas sem prefixo "Final Answer:"
            # Usar diretamente este conteúdo como resposta final, sem mais iterações vazias
            logger.info(f"Seção {section.title} prefixo 'Final Answer:' não detectado, adotando saída do LLM diretamente como conteúdo final (chamadas de ferramenta: {tool_calls_count} vezes)")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Número máximo de iterações atingido, gerar conteúdo forçadamente
        logger.warning(f"Seção {section.title} número máximo de iterações atingido, geração forçada")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Verificar se o retorno do LLM é None durante encerramento forçado
        if response is None:
            logger.error(f"Seção {section.title} LLM retornou None durante encerramento forçado, usando mensagem de erro padrão")
            final_answer = f"(Falha na geração desta seção: LLM retornou resposta vazia, por favor tente novamente mais tarde)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Registrar log de conclusão da geração de conteúdo da seção
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Gerar relatório completo (saída em tempo real por seção)
        
        Cada seção é salva imediatamente na pasta após a geração, sem precisar esperar a conclusão de todo o relatório.
        Estrutura de arquivos:
        reports/{report_id}/
            meta.json       - Metainformações do relatório
            outline.json    - Esboço do relatório
            progress.json   - Progresso da geração
            section_01.md   - Seção 1
            section_02.md   - Seção 2
            ...
            full_report.md  - Relatório completo
        
        Args:
            progress_callback: função de callback de progresso (stage, progress, message)
            report_id: ID do relatório(opcional, se não fornecido será gerado automaticamente)
            
        Returns:
            Report: relatório completo
        """
        import uuid
        
        # Se report_id não foi fornecido, gerar automaticamente
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Lista de títulos de seções concluídas (para rastreamento de progresso)
        completed_section_titles = []
        
        try:
            # Inicialização: criar pasta do relatório e salvar estado inicial
            ReportManager._ensure_report_folder(report_id)
            
            # Inicializar registrador de log(log estruturado agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Inicializar registrador de log de console（console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Inicializando relatório...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Fase 1: Planejar esboço
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Iniciando planejamento do esboço do relatório...",
                completed_sections=[]
            )
            
            # Registrar log de início do planejamento
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Iniciando planejamento do esboço do relatório...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Registrar log de conclusão do planejamento
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Salvar esboço no arquivo
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Planejamento do esboço concluído，{len(outline.sections)} seções",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Esboço salvo no arquivo: {report_id}/outline.json")
            
            # Fase 2: Gerar seção por seção (salvar por seção)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Salvar conteúdo para contexto
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Atualizar progresso
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Gerando seção: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Gerando seção: {section.title} ({section_num}/{total_sections})"
                    )
                
                # Gerar conteúdo principal da seção
                section_content = self._generate_section_react(
                    section=section,
                    outline=outline,
                    previous_sections=generated_sections,
                    progress_callback=lambda stage, prog, msg:
                        progress_callback(
                            stage, 
                            base_progress + int(prog * 0.7 / total_sections),
                            msg
                        ) if progress_callback else None,
                    section_index=section_num
                )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Salvar seção
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Registrar log de conclusão da seção
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Seção salva: {report_id}/section_{section_num:02d}.md")
                
                # Atualizar progresso
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Seção {section.title} concluída",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Fase 3: Montar relatório completo
            if progress_callback:
                progress_callback("generating", 95, "Montando relatório completo...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Montando relatório completo...",
                completed_sections=completed_section_titles
            )
            
            # Usar ReportManager para montar relatório completo
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calcular tempo total
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Registrar log de conclusão do relatório
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Salvar relatório final
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Geração do relatório concluída",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Geração do relatório concluída")
            
            logger.info(f"Geração do relatório concluída: {report_id}")
            
            # Fechar registrador de log de console
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Falha na geração do relatório: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Registrar log de erro
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Salvar estado de falha
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Falha na geração do relatório: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignorar erros de falha ao salvar
            
            # Fechar registrador de log de console
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Dialogar com Report Agent
        
        Durante o diálogo, o Agent pode chamar autonomamente ferramentas de busca para responder perguntas
        
        Args:
            message: mensagem do usuário
            chat_history: histórico do diálogo
            
        Returns:
            {
                "response": "resposta do Agent",
                "tool_calls": [lista de ferramentas chamadas],
                "sources": [fontes de informação]
            }
        """
        logger.info(f"Diálogo Report Agent: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Obter conteúdo do relatório já gerado
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limitar comprimento do relatório, evitar contexto muito longo
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [conteúdo do relatório truncado] ..."
        except Exception as e:
            logger.warning(f"Falha ao obter conteúdo do relatório: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(ainda sem relatório)",
            tools_description=self._get_tools_description(),
        )

        # Construir mensagens
        messages = [{"role": "system", "content": system_prompt}]
        
        # Adicionar histórico de diálogo
        for h in chat_history[-10:]:  # Limitar comprimento do histórico
            messages.append(h)
        
        # Adicionar mensagem do usuário
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # Ciclo ReACT(versão simplificada)
        tool_calls_made = []
        max_iterations = 2  # Reduzir número de rodadas de iteração
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Analisar chamadas de ferramenta
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # Sem chamada de ferramenta, retornar resposta diretamente
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Executar chamada de ferramenta(limitar quantidade)
            tool_results = []
            for call in tool_calls[:1]:  # Máximo 1 chamada de ferramenta por rodada
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limitar comprimento do resultado
                })
                tool_calls_made.append(call)
            
            # Adicionar resultados às mensagens
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']}resultado]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Iteração máxima atingida, obter resposta final
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Limpar resposta
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Gerenciador de relatórios
    
    Responsável pelo armazenamento persistente e busca de relatórios
    
    Estrutura de arquivos (saída por seção)：
    reports/
      {report_id}/
        meta.json          - Metainformações e status do relatório
        outline.json       - Esboço do relatório
        progress.json      - Progresso da geração
        section_01.md      - Seção 1
        section_02.md      - Seção 2
        ...
        full_report.md     - Relatório completo
    """
    
    # Diretório de armazenamento de relatórios
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Garantir que o diretório raiz de relatórios exista"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Obter caminho da pasta do relatório"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Garantir que a pasta do relatório exista e retornar o caminho"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Obter caminho do arquivo de metainformações do relatório"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Obter caminho do arquivo Markdown do relatório completo"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Obter caminho do arquivo de esboço"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Obter caminho do arquivo de progresso"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Obter caminho do arquivo Markdown da seção"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Obter caminho do arquivo de log do Agent"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Obter caminho do arquivo de log do console"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Obter conteúdo do log do console
        
        Este é o log de saída do console durante a geração do relatório (INFO, WARNING etc.)，
        diferente dos logs estruturados do agent_log.jsonl.
        
        Args:
            report_id: ID do relatório
            from_line: A partir de qual linha começar a leitura (para obtenção incremental, 0 significa do início)
            
        Returns:
            {
                "logs": [lista de linhas de log],
                "total_lines": total de linhas,
                "from_line": número da linha inicial,
                "has_more": se há mais logs
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Manter linha de log original, remover caractere de nova linha do final
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Leitura até o final concluída
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Obter log completo do console (obter tudo de uma vez)
        
        Args:
            report_id: ID do relatório
            
        Returns:
            Lista de linhas de log
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Obter conteúdo do log do Agent
        
        Args:
            report_id: ID do relatório
            from_line: A partir de qual linha começar a leitura (para obtenção incremental, 0 significa do início)
            
        Returns:
            {
                "logs": [lista de entradas de log],
                "total_lines": total de linhas,
                "from_line": número da linha inicial,
                "has_more": se há mais logs
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Pular linhas com falha no parsing
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Leitura até o final concluída
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Obter log completo do Agent (para obter tudo de uma vez)
        
        Args:
            report_id: ID do relatório
            
        Returns:
            Lista de entradas de log
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Salvar esboço do relatório
        
        Chamar imediatamente após a conclusão da fase de planejamento
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Esboço salvo: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Salvar seção individual

        Chamar imediatamente após a conclusão da geração de cada seção, implementando saída por seção

        Args:
            report_id: ID do relatório
            section_index: Índice da seção (a partir de 1)
            section: objeto da seção

        Returns:
            Caminho do arquivo salvo
        """
        cls._ensure_report_folder(report_id)

        # Construir conteúdo Markdown da seção - limpar possíveis títulos duplicados
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Salvar arquivo
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Seção salva: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Limpar conteúdo da seção
        
        1. Remover linhas de título Markdown duplicadas com o título da seção no início do conteúdo
        2. Converter todos os títulos de nível ### e inferior em texto em negrito
        
        Args:
            content: conteúdo original
            section_title: título da seção
            
        Returns:
            Conteúdo limpo
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Verificar se é uma linha de título Markdown
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Verificar se é um título duplicado com o título da seção (pular duplicatas nas primeiras 5 linhas)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Converter todos os níveis de título (#, ##, ###, #### etc.)em negrito
                # Como o título da seção é adicionado pelo sistema, o conteúdo não deve conter nenhum título
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Adicionar linha em branco
                continue
            
            # Se a linha anterior foi um título pulado e a linha atual é vazia, também pular
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remover linhas em branco do início
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Remover linhas de separação do início
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Também remover linhas em branco após a linha de separação
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Atualizar progresso da geração do relatório
        
        O frontend pode obter o progresso em tempo real lendo progress.json
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Obter progresso da geração do relatório"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Obter lista de seções já geradas
        
        Retornar informações de todos os arquivos de seção já salvos
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Analisar índice da seção a partir do nome do arquivo
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Montar relatório completo
        
        Montar relatório completo a partir dos arquivos de seção já salvos, com limpeza de títulos
        """
        folder = cls._get_report_folder(report_id)
        
        # Construir cabeçalho do relatório
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Ler todos os arquivos de seção em ordem
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Pós-processamento: limpar problemas de título do relatório inteiro
        md_content = cls._post_process_report(md_content, outline)
        
        # Salvar relatório completo
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Relatório completo montado: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Pós-processar conteúdo do relatório
        
        1. Remover títulos duplicados
        2. Manter título principal do relatório (#) e títulos de seção (##), remover títulos de outros níveis (###, #### etc.)
        3. Limpar linhas em branco e linhas de separação excedentes
        
        Args:
            content: conteúdo original do relatório
            outline: esboço do relatório
            
        Returns:
            Conteúdo processado
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Coletar todos os títulos de seção do esboço
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Verificar se é uma linha de título
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Verificar se é um título duplicado (título com mesmo conteúdo nas últimas 5 linhas)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Pular título duplicado e linhas em branco subsequentes
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Tratamento de hierarquia de títulos:
                # - # (level=1) manter apenas título principal do relatório
                # - ## (level=2) manter títulos de seção
                # - ### e inferior (level>=3) converter em texto em negrito
                
                if level == 1:
                    if title == outline.title:
                        # Manter título principal do relatório
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Título de seção usou # incorretamente, corrigir para ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Outros títulos de nível 1 converter em negrito
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Manter títulos de seção
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Títulos de nível 2 que não são de seção converter em negrito
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # Títulos de nível ### e inferior converter em texto em negrito
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Pular linha de separação logo após o título
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Manter apenas uma linha em branco após o título
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Limpar múltiplas linhas em branco consecutivas (manter no máximo 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Salvar metainformações e relatório completo"""
        cls._ensure_report_folder(report.report_id)
        
        # Salvar JSON de metainformações
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Salvar esboço
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Salvar relatório Markdown completo
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Relatório salvo: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Obter relatório"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Compatibilidade com formato antigo: verificar arquivo armazenado diretamente no diretório reports
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruir objeto Report
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', '')
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # Se markdown_content estiver vazio, tentar ler de full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Obter relatório pelo ID de simulação"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Novo formato: pasta
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Compatibilidade com formato antigo: arquivo JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """Listar relatórios"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # Novo formato: pasta
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Compatibilidade com formato antigo: arquivo JSON
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Ordenar por data de criação em ordem decrescente
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Excluir relatório (toda a pasta)"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # Novo formato: excluir toda a pasta
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Pasta do relatório excluída: {report_id}")
            return True
        
        # Compatibilidade com formato antigo: excluir arquivos individuais
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
