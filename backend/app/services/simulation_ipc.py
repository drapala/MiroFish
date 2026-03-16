"""
Módulo de comunicação IPC de simulação
Usado para comunicação entre processos entre o backend Flask e scripts de simulação

Implementa um padrão simples de comando/resposta através do sistema de arquivos:
1. Flask escreve comandos no diretório commands/
2. O script de simulação faz polling do diretório de comandos, executa comandos e escreve respostas no diretório responses/
3. Flask faz polling do diretório de respostas para obter resultados
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_ipc')


class CommandType(str, Enum):
    """Tipo de comando"""
    INTERVIEW = "interview"           # Entrevista de um único Agent
    BATCH_INTERVIEW = "batch_interview"  # Entrevista em lote
    CLOSE_ENV = "close_env"           # Fechar ambiente


class CommandStatus(str, Enum):
    """Status do comando"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """Comando IPC"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """Resposta IPC"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    Cliente IPC de simulação (usado pelo lado Flask)

    Usado para enviar comandos ao processo de simulação e aguardar respostas
    """

    def __init__(self, simulation_dir: str):
        """
        Inicializar cliente IPC

        Args:
            simulation_dir: Diretório de dados de simulação
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Garantir que os diretórios existam
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        Enviar comando e aguardar resposta

        Args:
            command_type: Tipo de comando
            args: Argumentos do comando
            timeout: Tempo limite (segundos)
            poll_interval: Intervalo de polling (segundos)

        Returns:
            IPCResponse

        Raises:
            TimeoutError: Timeout aguardando resposta
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )
        
        # Escrever arquivo de comando
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Enviando comando IPC: {command_type.value}, command_id={command_id}")
        
        # Aguardar resposta
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)
                    
                    # Limpar arquivos de comando e resposta
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass
                    
                    logger.info(f"Resposta IPC recebida: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Falha ao analisar resposta: {e}")
            
            time.sleep(poll_interval)
        
        # Timeout
        logger.error(f"Timeout aguardando resposta IPC: command_id={command_id}")

        # Limpar arquivo de comando
        try:
            os.remove(command_file)
        except OSError:
            pass
        
        raise TimeoutError(f"Timeout aguardando resposta do comando ({timeout}s)")
    
    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> IPCResponse:
        """
        Enviar comando de entrevista de um único Agent

        Args:
            agent_id: Agent ID
            prompt: Pergunta da entrevista
            platform: Plataforma especificada (opcional)
                - "twitter": Entrevistar apenas na plataforma Twitter
                - "reddit": Entrevistar apenas na plataforma Reddit
                - None: Em simulação dupla, entrevistar em ambas as plataformas simultaneamente
            timeout: Tempo limite

        Returns:
            IPCResponse, campo result contém o resultado da entrevista
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        Enviar comando de entrevista em lote

        Args:
            interviews: Lista de entrevistas, cada elemento contém {"agent_id": int, "prompt": str, "platform": str(opcional)}
            platform: Plataforma padrão (opcional, será sobrescrita pelo platform de cada item de entrevista)
                - "twitter": Entrevistar por padrão apenas na plataforma Twitter
                - "reddit": Entrevistar por padrão apenas na plataforma Reddit
                - None: Em simulação dupla, cada Agent entrevistado em ambas as plataformas
            timeout: Tempo limite

        Returns:
            IPCResponse, campo result contém todos os resultados das entrevistas
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        Enviar comando de fechar ambiente

        Args:
            timeout: Tempo limite

        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )
    
    def check_env_alive(self) -> bool:
        """
        Verificar se o ambiente de simulação está ativo

        Determinado verificando o arquivo env_status.json
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return status.get("status") == "alive"
        except (json.JSONDecodeError, OSError):
            return False


class SimulationIPCServer:
    """
    Servidor IPC de simulação (usado pelo lado do script de simulação)

    Faz polling do diretório de comandos, executa comandos e retorna respostas
    """

    def __init__(self, simulation_dir: str):
        """
        Inicializar servidor IPC

        Args:
            simulation_dir: Diretório de dados de simulação
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Garantir que os diretórios existam
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)

        # Status do ambiente
        self._running = False
    
    def start(self):
        """Marcar servidor como em execução"""
        self._running = True
        self._update_env_status("alive")
    
    def stop(self):
        """Marcar servidor como parado"""
        self._running = False
        self._update_env_status("stopped")
    
    def _update_env_status(self, status: str):
        """Atualizar arquivo de status do ambiente"""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def poll_commands(self) -> Optional[IPCCommand]:
        """
        Fazer polling do diretório de comandos, retornando o primeiro comando pendente

        Returns:
            IPCCommand ou None
        """
        if not os.path.exists(self.commands_dir):
            return None
        
        # Obter arquivos de comando ordenados por tempo
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))
        
        command_files.sort(key=lambda x: x[1])
        
        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Falha ao ler arquivo de comando: {filepath}, {e}")
                continue
        
        return None
    
    def send_response(self, response: IPCResponse):
        """
        Enviar resposta

        Args:
            response: Resposta IPC
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Excluir arquivo de comando
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass
    
    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Enviar resposta de sucesso"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))
    
    def send_error(self, command_id: str, error: str):
        """Enviar resposta de erro"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
