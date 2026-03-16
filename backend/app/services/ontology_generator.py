"""
Serviço de geração de ontologia
Interface 1: Analisar conteúdo textual, gerar definições de tipos de entidade e relacionamento adequados para simulação social
"""

import json
from typing import Dict, Any, List, Optional
from ..utils.llm_client import LLMClient


# Prompt de sistema para geração de ontologia
ONTOLOGY_SYSTEM_PROMPT = """Você é um especialista profissional em design de ontologia de grafos de conhecimento. Sua tarefa é analisar o conteúdo textual fornecido e os requisitos de simulação, projetando tipos de entidade e tipos de relacionamento adequados para **simulação de opinião pública em mídias sociais**.

**Importante: você deve produzir dados em formato JSON válido, sem nenhum outro conteúdo.**

## Contexto da tarefa principal

Estamos construindo um **sistema de simulação de opinião pública em mídias sociais**. Neste sistema:
- Cada entidade é uma "conta" ou "sujeito" que pode se expressar, interagir e propagar informações nas mídias sociais
- As entidades influenciam umas às outras, repostam, comentam e respondem
- Precisamos simular as reações de todas as partes em eventos de opinião pública e os caminhos de propagação de informações

Portanto, **as entidades devem ser sujeitos que existem no mundo real e que podem se expressar e interagir nas mídias sociais**:

**Pode ser**:
- Indivíduos específicos (figuras públicas, partes envolvidas, líderes de opinião, especialistas acadêmicos, pessoas comuns)
- Empresas (incluindo suas contas oficiais)
- Organizações (universidades, associações, ONGs, sindicatos, etc.)
- Departamentos governamentais, órgãos reguladores
- Instituições de mídia (jornais, emissoras de TV, mídias independentes, sites)
- As próprias plataformas de mídia social
- Representantes de grupos específicos (como associações de ex-alunos, fã-clubes, grupos de defesa de direitos, etc.)

**Não pode ser**:
- Conceitos abstratos (como "opinião pública", "emoção", "tendência")
- Temas/tópicos (como "integridade acadêmica", "reforma educacional")
- Pontos de vista/atitudes (como "apoiadores", "opositores")

## Formato de saída

Produza no formato JSON, contendo a seguinte estrutura:

```json
{
    "entity_types": [
        {
            "name": "Nome do tipo de entidade (inglês, PascalCase)",
            "description": "Descrição breve (inglês, máximo 100 caracteres)",
            "attributes": [
                {
                    "name": "Nome do atributo (inglês, snake_case)",
                    "type": "text",
                    "description": "Descrição do atributo"
                }
            ],
            "examples": ["Exemplo de entidade 1", "Exemplo de entidade 2"]
        }
    ],
    "edge_types": [
        {
            "name": "Nome do tipo de relacionamento (inglês, UPPER_SNAKE_CASE)",
            "description": "Descrição breve (inglês, máximo 100 caracteres)",
            "source_targets": [
                {"source": "Tipo de entidade de origem", "target": "Tipo de entidade de destino"}
            ],
            "attributes": []
        }
    ],
    "analysis_summary": "Breve análise explicativa do conteúdo textual (em português)"
}
```

## Guia de design (extremamente importante!)

### 1. Design de tipos de entidade - deve ser seguido rigorosamente

**Requisito de quantidade: devem ser exatamente 10 tipos de entidade**

**Requisito de estrutura hierárquica (deve conter tanto tipos específicos quanto tipos de fallback)**:

Seus 10 tipos de entidade devem conter os seguintes níveis:

A. **Tipos de fallback (obrigatórios, últimos 2 da lista)**:
   - `Person`: Tipo de fallback para qualquer pessoa física. Quando uma pessoa não se encaixa em outros tipos mais específicos, é classificada aqui.
   - `Organization`: Tipo de fallback para qualquer organização. Quando uma organização não se encaixa em outros tipos mais específicos, é classificada aqui.

B. **Tipos específicos (8, projetados com base no conteúdo textual)**:
   - Projetar tipos mais específicos para os papéis principais que aparecem no texto
   - Exemplo: se o texto envolve eventos acadêmicos, pode incluir `Student`, `Professor`, `University`
   - Exemplo: se o texto envolve eventos comerciais, pode incluir `Company`, `CEO`, `Employee`

**Por que são necessários tipos de fallback**:
- No texto aparecerão diversas pessoas, como "professor do ensino básico", "transeunte", "um internauta"
- Se não houver um tipo específico correspondente, devem ser classificados em `Person`
- Da mesma forma, pequenas organizações, grupos temporários, etc. devem ser classificados em `Organization`

**Princípios de design dos tipos específicos**:
- Identificar os tipos de papéis que aparecem com alta frequência ou são fundamentais no texto
- Cada tipo específico deve ter limites claros, evitando sobreposições
- A description deve explicar claramente a diferença entre este tipo e o tipo de fallback

### 2. Design de tipos de relacionamento

- Quantidade: 6-10
- Os relacionamentos devem refletir conexões reais nas interações de mídias sociais
- Garantir que os source_targets dos relacionamentos cubram os tipos de entidade definidos

### 3. Design de atributos

- 1-3 atributos-chave por tipo de entidade
- **Atenção**: nomes de atributos não podem usar `name`, `uuid`, `group_id`, `created_at`, `summary` (são palavras reservadas do sistema)
- Recomendado usar: `full_name`, `title`, `role`, `position`, `location`, `description`, etc.

## Referência de tipos de entidade

**Classe individual (específico)**:
- Student: Estudante
- Professor: Professor/Acadêmico
- Journalist: Jornalista
- Celebrity: Celebridade/Influenciador
- Executive: Executivo
- Official: Oficial do governo
- Lawyer: Advogado
- Doctor: Médico

**Classe individual (fallback)**:
- Person: Qualquer pessoa física (usado quando não se encaixa nos tipos específicos acima)

**Classe organizacional (específico)**:
- University: Universidade
- Company: Empresa
- GovernmentAgency: Órgão governamental
- MediaOutlet: Instituição de mídia
- Hospital: Hospital
- School: Escola
- NGO: Organização não governamental

**Classe organizacional (fallback)**:
- Organization: Qualquer organização (usado quando não se encaixa nos tipos específicos acima)

## Referência de tipos de relacionamento

- WORKS_FOR: Trabalha em
- STUDIES_AT: Estuda em
- AFFILIATED_WITH: Afiliado a
- REPRESENTS: Representa
- REGULATES: Regula
- REPORTS_ON: Reporta sobre
- COMMENTS_ON: Comenta sobre
- RESPONDS_TO: Responde a
- SUPPORTS: Apoia
- OPPOSES: Opõe-se a
- COLLABORATES_WITH: Colabora com
- COMPETES_WITH: Compete com
"""


class OntologyGenerator:
    """
    Gerador de ontologia
    Analisa conteúdo textual, gera definições de tipos de entidade e relacionamento
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client or LLMClient()
    
    def generate(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gerar definição de ontologia
        
        Args:
            document_texts: lista de textos de documentos
            simulation_requirement: descrição dos requisitos da simulação
            additional_context: contexto adicional
            
        Returns:
            definição de ontologia (entity_types, edge_types, etc.)
        """
        # Construir mensagem do usuário
        user_message = self._build_user_message(
            document_texts, 
            simulation_requirement,
            additional_context
        )
        
        messages = [
            {"role": "system", "content": ONTOLOGY_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
        
        # Chamar LLM
        result = self.llm_client.chat_json(
            messages=messages,
            temperature=0.3,
            max_tokens=4096
        )
        
        # Validar e pós-processar
        result = self._validate_and_process(result)
        
        return result
    
    # Comprimento máximo do texto enviado ao LLM (50 mil caracteres)
    MAX_TEXT_LENGTH_FOR_LLM = 50000
    
    def _build_user_message(
        self,
        document_texts: List[str],
        simulation_requirement: str,
        additional_context: Optional[str]
    ) -> str:
        """Construir mensagem do usuário"""
        
        # Combinar textos
        combined_text = "\n\n---\n\n".join(document_texts)
        original_length = len(combined_text)
        
        # Se o texto ultrapassar 50 mil caracteres, truncar (afeta apenas o conteúdo enviado ao LLM, não a construção do grafo)
        if len(combined_text) > self.MAX_TEXT_LENGTH_FOR_LLM:
            combined_text = combined_text[:self.MAX_TEXT_LENGTH_FOR_LLM]
            combined_text += f"\n\n...(texto original com {original_length} caracteres, truncado para os primeiros {self.MAX_TEXT_LENGTH_FOR_LLM} caracteres para análise de ontologia)..."
        
        message = f"""## Requisitos da simulação

{simulation_requirement}

## Conteúdo do documento

{combined_text}
"""
        
        if additional_context:
            message += f"""
## Observações adicionais

{additional_context}
"""
        
        message += """
Com base no conteúdo acima, projete tipos de entidade e tipos de relacionamento adequados para simulação de opinião pública social.

**Regras que devem ser seguidas**:
1. Deve produzir exatamente 10 tipos de entidade
2. Os últimos 2 devem ser tipos de fallback: Person (fallback individual) e Organization (fallback organizacional)
3. Os 8 primeiros são tipos específicos projetados com base no conteúdo textual
4. Todos os tipos de entidade devem ser sujeitos que podem se expressar no mundo real, não conceitos abstratos
5. Nomes de atributos não podem usar palavras reservadas como name, uuid, group_id; use full_name, org_name, etc.
"""
        
        return message
    
    def _validate_and_process(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Validar e pós-processar resultados"""
        
        # Garantir que campos necessários existam
        if "entity_types" not in result:
            result["entity_types"] = []
        if "edge_types" not in result:
            result["edge_types"] = []
        if "analysis_summary" not in result:
            result["analysis_summary"] = ""
        
        # Validar tipos de entidade
        for entity in result["entity_types"]:
            if "attributes" not in entity:
                entity["attributes"] = []
            if "examples" not in entity:
                entity["examples"] = []
            # Garantir que description não ultrapasse 100 caracteres
            if len(entity.get("description", "")) > 100:
                entity["description"] = entity["description"][:97] + "..."
        
        # Validar tipos de relacionamento
        for edge in result["edge_types"]:
            if "source_targets" not in edge:
                edge["source_targets"] = []
            if "attributes" not in edge:
                edge["attributes"] = []
            if len(edge.get("description", "")) > 100:
                edge["description"] = edge["description"][:97] + "..."
        
        # Limite da Zep API: máximo 10 tipos de entidade personalizados, máximo 10 tipos de aresta personalizados
        MAX_ENTITY_TYPES = 10
        MAX_EDGE_TYPES = 10
        
        # Definição dos tipos de fallback
        person_fallback = {
            "name": "Person",
            "description": "Any individual person not fitting other specific person types.",
            "attributes": [
                {"name": "full_name", "type": "text", "description": "Full name of the person"},
                {"name": "role", "type": "text", "description": "Role or occupation"}
            ],
            "examples": ["ordinary citizen", "anonymous netizen"]
        }
        
        organization_fallback = {
            "name": "Organization",
            "description": "Any organization not fitting other specific organization types.",
            "attributes": [
                {"name": "org_name", "type": "text", "description": "Name of the organization"},
                {"name": "org_type", "type": "text", "description": "Type of organization"}
            ],
            "examples": ["small business", "community group"]
        }
        
        # Verificar se já existem tipos de fallback
        entity_names = {e["name"] for e in result["entity_types"]}
        has_person = "Person" in entity_names
        has_organization = "Organization" in entity_names
        
        # Tipos de fallback a serem adicionados
        fallbacks_to_add = []
        if not has_person:
            fallbacks_to_add.append(person_fallback)
        if not has_organization:
            fallbacks_to_add.append(organization_fallback)
        
        if fallbacks_to_add:
            current_count = len(result["entity_types"])
            needed_slots = len(fallbacks_to_add)
            
            # Se adicionar ultrapassar 10, é necessário remover alguns tipos existentes
            if current_count + needed_slots > MAX_ENTITY_TYPES:
                # Calcular quantos precisam ser removidos
                to_remove = current_count + needed_slots - MAX_ENTITY_TYPES
                # Remover do final (preservar tipos específicos mais importantes no início)
                result["entity_types"] = result["entity_types"][:-to_remove]
            
            # Adicionar tipos de fallback
            result["entity_types"].extend(fallbacks_to_add)
        
        # Garantia final de não ultrapassar o limite (programação defensiva)
        if len(result["entity_types"]) > MAX_ENTITY_TYPES:
            result["entity_types"] = result["entity_types"][:MAX_ENTITY_TYPES]
        
        if len(result["edge_types"]) > MAX_EDGE_TYPES:
            result["edge_types"] = result["edge_types"][:MAX_EDGE_TYPES]
        
        return result
    
    def generate_python_code(self, ontology: Dict[str, Any]) -> str:
        """
        Converter definição de ontologia em código Python (similar a ontology.py)
        
        Args:
            ontology: definição de ontologia
            
        Returns:
            string de código Python
        """
        code_lines = [
            '"""',
            'Definições de tipos de entidade personalizados',
            'Gerado automaticamente pelo MiroFish, para simulação de opinião pública social',
            '"""',
            '',
            'from pydantic import Field',
            'from zep_cloud.external_clients.ontology import EntityModel, EntityText, EdgeModel',
            '',
            '',
            '# ============== Definições de tipos de entidade ==============',
            '',
        ]
        
        # Gerar tipos de entidade
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            desc = entity.get("description", f"A {name} entity.")
            
            code_lines.append(f'class {name}(EntityModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = entity.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        code_lines.append('# ============== Definições de tipos de relacionamento ==============')
        code_lines.append('')
        
        # Gerar tipos de relacionamento
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            # Converter para nome de classe PascalCase
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            desc = edge.get("description", f"A {name} relationship.")
            
            code_lines.append(f'class {class_name}(EdgeModel):')
            code_lines.append(f'    """{desc}"""')
            
            attrs = edge.get("attributes", [])
            if attrs:
                for attr in attrs:
                    attr_name = attr["name"]
                    attr_desc = attr.get("description", attr_name)
                    code_lines.append(f'    {attr_name}: EntityText = Field(')
                    code_lines.append(f'        description="{attr_desc}",')
                    code_lines.append(f'        default=None')
                    code_lines.append(f'    )')
            else:
                code_lines.append('    pass')
            
            code_lines.append('')
            code_lines.append('')
        
        # Gerar dicionário de tipos
        code_lines.append('# ============== Configuração de tipos ==============')
        code_lines.append('')
        code_lines.append('ENTITY_TYPES = {')
        for entity in ontology.get("entity_types", []):
            name = entity["name"]
            code_lines.append(f'    "{name}": {name},')
        code_lines.append('}')
        code_lines.append('')
        code_lines.append('EDGE_TYPES = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            class_name = ''.join(word.capitalize() for word in name.split('_'))
            code_lines.append(f'    "{name}": {class_name},')
        code_lines.append('}')
        code_lines.append('')
        
        # Gerar mapeamento de source_targets das arestas
        code_lines.append('EDGE_SOURCE_TARGETS = {')
        for edge in ontology.get("edge_types", []):
            name = edge["name"]
            source_targets = edge.get("source_targets", [])
            if source_targets:
                st_list = ', '.join([
                    f'{{"source": "{st.get("source", "Entity")}", "target": "{st.get("target", "Entity")}"}}'
                    for st in source_targets
                ])
                code_lines.append(f'    "{name}": [{st_list}],')
        code_lines.append('}')
        
        return '\n'.join(code_lines)

