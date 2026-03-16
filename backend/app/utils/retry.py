"""
Mecanismo de retry para chamadas de API
Usado para tratar a lógica de retry de chamadas a APIs externas como LLM
"""

import time
import random
import functools
from typing import Callable, Any, Optional, Type, Tuple
from ..utils.logger import get_logger

logger = get_logger('mirofish.retry')


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Decorador de retry com backoff exponencial

    Args:
        max_retries: Número máximo de tentativas
        initial_delay: Atraso inicial (segundos)
        max_delay: Atraso máximo (segundos)
        backoff_factor: Fator de backoff
        jitter: Se deve adicionar variação aleatória
        exceptions: Tipos de exceção que devem ser retentados
        on_retry: Função de callback ao retentar (exception, retry_count)

    Usage:
        @retry_with_backoff(max_retries=3)
        def call_llm_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Função {func.__name__} ainda falhou após {max_retries} tentativas: {str(e)}")
                        raise
                    
                    # Calcular atraso
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"Função {func.__name__} falhou na tentativa {attempt + 1}: {str(e)}, "
                        f"retentando em {current_delay:.1f}s..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    time.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_with_backoff_async(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Versão assíncrona do decorador de retry
    """
    import asyncio
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            delay = initial_delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(f"Função assíncrona {func.__name__} ainda falhou após {max_retries} tentativas: {str(e)}")
                        raise
                    
                    current_delay = min(delay, max_delay)
                    if jitter:
                        current_delay = current_delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"Função assíncrona {func.__name__} falhou na tentativa {attempt + 1}: {str(e)}, "
                        f"retentando em {current_delay:.1f}s..."
                    )
                    
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    await asyncio.sleep(current_delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        return wrapper
    return decorator


class RetryableAPIClient:
    """
    Encapsulamento de cliente de API com retry
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_factor: float = 2.0
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    def call_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        **kwargs
    ) -> Any:
        """
        Executar chamada de função e retentar em caso de falha

        Args:
            func: Função a ser chamada
            *args: Argumentos da função
            exceptions: Tipos de exceção que devem ser retentados
            **kwargs: Argumentos nomeados da função

        Returns:
            Valor de retorno da função
        """
        last_exception = None
        delay = self.initial_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)
                
            except exceptions as e:
                last_exception = e
                
                if attempt == self.max_retries:
                    logger.error(f"Chamada de API ainda falhou após {self.max_retries} tentativas: {str(e)}")
                    raise
                
                current_delay = min(delay, self.max_delay)
                current_delay = current_delay * (0.5 + random.random())
                
                logger.warning(
                    f"Chamada de API falhou na tentativa {attempt + 1}: {str(e)}, "
                    f"retentando em {current_delay:.1f}s..."
                )
                
                time.sleep(current_delay)
                delay *= self.backoff_factor
        
        raise last_exception
    
    def call_batch_with_retry(
        self,
        items: list,
        process_func: Callable,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        continue_on_failure: bool = True
    ) -> Tuple[list, list]:
        """
        Chamada em lote com retry individual para cada item que falhar

        Args:
            items: Lista de itens a serem processados
            process_func: Função de processamento, recebe um único item como argumento
            exceptions: Tipos de exceção que devem ser retentados
            continue_on_failure: Se deve continuar processando outros itens após falha de um item

        Returns:
            (lista de resultados bem-sucedidos, lista de itens com falha)
        """
        results = []
        failures = []
        
        for idx, item in enumerate(items):
            try:
                result = self.call_with_retry(
                    process_func,
                    item,
                    exceptions=exceptions
                )
                results.append(result)
                
            except Exception as e:
                logger.error(f"Falha ao processar item {idx + 1}: {str(e)}")
                failures.append({
                    "index": idx,
                    "item": item,
                    "error": str(e)
                })
                
                if not continue_on_failure:
                    raise
        
        return results, failures

