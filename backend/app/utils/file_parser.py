"""
Ferramenta de análise de arquivos
Suporta extração de texto de arquivos PDF, Markdown e TXT
"""

import os
from pathlib import Path
from typing import List, Optional


def _read_text_with_fallback(file_path: str) -> str:
    """
    Ler arquivo de texto, detectando codificação automaticamente quando UTF-8 falhar.

    Estratégia de fallback em múltiplos níveis:
    1. Primeiro tentar decodificação UTF-8
    2. Usar charset_normalizer para detectar codificação
    3. Fallback para chardet para detectar codificação
    4. Por último usar UTF-8 + errors='replace' como garantia

    Args:
        file_path: Caminho do arquivo

    Returns:
        Conteúdo de texto decodificado
    """
    data = Path(file_path).read_bytes()
    
    # Primeiro tentar UTF-8
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    
    # Tentar usar charset_normalizer para detectar codificação
    encoding = None
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best and best.encoding:
            encoding = best.encoding
    except Exception:
        pass
    
    # Fallback para chardet
    if not encoding:
        try:
            import chardet
            result = chardet.detect(data)
            encoding = result.get('encoding') if result else None
        except Exception:
            pass
    
    # Garantia final: usar UTF-8 + replace
    if not encoding:
        encoding = 'utf-8'
    
    return data.decode(encoding, errors='replace')


class FileParser:
    """Analisador de arquivos"""
    
    SUPPORTED_EXTENSIONS = {'.pdf', '.md', '.markdown', '.txt'}
    
    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """
        Extrair texto de um arquivo

        Args:
            file_path: Caminho do arquivo

        Returns:
            Conteúdo de texto extraído
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")
        
        suffix = path.suffix.lower()
        
        if suffix not in cls.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Formato de arquivo não suportado: {suffix}")
        
        if suffix == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif suffix in {'.md', '.markdown'}:
            return cls._extract_from_md(file_path)
        elif suffix == '.txt':
            return cls._extract_from_txt(file_path)
        
        raise ValueError(f"Formato de arquivo não processável: {suffix}")
    
    @staticmethod
    def _extract_from_pdf(file_path: str) -> str:
        """Extrair texto de PDF"""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("É necessário instalar PyMuPDF: pip install PyMuPDF")
        
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    @staticmethod
    def _extract_from_md(file_path: str) -> str:
        """Extrair texto de Markdown, com detecção automática de codificação"""
        return _read_text_with_fallback(file_path)
    
    @staticmethod
    def _extract_from_txt(file_path: str) -> str:
        """Extrair texto de TXT, com detecção automática de codificação"""
        return _read_text_with_fallback(file_path)
    
    @classmethod
    def extract_from_multiple(cls, file_paths: List[str]) -> str:
        """
        Extrair texto de múltiplos arquivos e combinar

        Args:
            file_paths: Lista de caminhos de arquivos

        Returns:
            Texto combinado
        """
        all_texts = []
        
        for i, file_path in enumerate(file_paths, 1):
            try:
                text = cls.extract_text(file_path)
                filename = Path(file_path).name
                all_texts.append(f"=== Documento {i}: {filename} ===\n{text}")
            except Exception as e:
                all_texts.append(f"=== Documento {i}: {file_path} (falha na extração: {str(e)}) ===")
        
        return "\n\n".join(all_texts)


def split_text_into_chunks(
    text: str, 
    chunk_size: int = 500, 
    overlap: int = 50
) -> List[str]:
    """
    Dividir texto em blocos menores

    Args:
        text: Texto original
        chunk_size: Número de caracteres por bloco
        overlap: Número de caracteres de sobreposição

    Returns:
        Lista de blocos de texto
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # Tentar dividir nos limites de sentenças
        if end < len(text):
            # Encontrar o delimitador de sentença mais próximo
            for sep in ['。', '！', '？', '.\n', '!\n', '?\n', '\n\n', '. ', '! ', '? ']:
                last_sep = text[start:end].rfind(sep)
                if last_sep != -1 and last_sep > chunk_size * 0.3:
                    end = start + last_sep + len(sep)
                    break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        # O próximo bloco começa na posição de sobreposição
        start = end - overlap if end < len(text) else len(text)
    
    return chunks

