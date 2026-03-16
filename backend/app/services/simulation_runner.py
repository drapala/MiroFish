"""
Executor de simulação OASIS
Executa simulação em segundo plano e registra as ações de cada Agent, com suporte a monitoramento de estado em tempo real
"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
import signal
import atexit
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from queue import Queue

from ..config import Config
from ..utils.logger import get_logger
from .zep_graph_memory_updater import ZepGraphMemoryManager
from .simulation_ipc import SimulationIPCClient, CommandType, IPCResponse

logger = get_logger('mirofish.simulation_runner')

# Marcar se a função de limpeza já foi registrada
_cleanup_registered = False

# Detecção de plataforma
IS_WINDOWS = sys.platform == 'win32'


class RunnerStatus(str, Enum):
    """Status do executor"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentAction:
    """Registro de ação do Agent"""
    round_num: int
    timestamp: str
    platform: str  # twitter / reddit
    agent_id: int
    agent_name: str
    action_type: str  # CREATE_POST, LIKE_POST, etc.
    action_args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None
    success: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "action_type": self.action_type,
            "action_args": self.action_args,
            "result": self.result,
            "success": self.success,
        }


@dataclass
class RoundSummary:
    """Resumo de cada rodada"""
    round_num: int
    start_time: str
    end_time: Optional[str] = None
    simulated_hour: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    active_agents: List[int] = field(default_factory=list)
    actions: List[AgentAction] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "simulated_hour": self.simulated_hour,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "active_agents": self.active_agents,
            "actions_count": len(self.actions),
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class SimulationRunState:
    """Estado de execução da simulação (tempo real)"""
    simulation_id: str
    runner_status: RunnerStatus = RunnerStatus.IDLE
    
    # Informações de progresso
    current_round: int = 0
    total_rounds: int = 0
    simulated_hours: int = 0
    total_simulation_hours: int = 0
    
    # Rodadas e tempo de simulação independentes por plataforma (para exibição paralela de dupla plataforma)
    twitter_current_round: int = 0
    reddit_current_round: int = 0
    twitter_simulated_hours: int = 0
    reddit_simulated_hours: int = 0
    
    # Status da plataforma
    twitter_running: bool = False
    reddit_running: bool = False
    twitter_actions_count: int = 0
    reddit_actions_count: int = 0
    
    # Status de conclusão da plataforma (detectando evento simulation_end no actions.jsonl)
    twitter_completed: bool = False
    reddit_completed: bool = False
    
    # Resumo por rodada
    rounds: List[RoundSummary] = field(default_factory=list)
    
    # Ações recentes (para exibição em tempo real no frontend)
    recent_actions: List[AgentAction] = field(default_factory=list)
    max_recent_actions: int = 50
    
    # Timestamps
    started_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    
    # Informações de erro
    error: Optional[str] = None
    
    # PID do processo (para parar)
    process_pid: Optional[int] = None
    
    def add_action(self, action: AgentAction):
        """Adicionar ação à lista de ações recentes"""
        self.recent_actions.insert(0, action)
        if len(self.recent_actions) > self.max_recent_actions:
            self.recent_actions = self.recent_actions[:self.max_recent_actions]
        
        if action.platform == "twitter":
            self.twitter_actions_count += 1
        else:
            self.reddit_actions_count += 1
        
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "runner_status": self.runner_status.value,
            "current_round": self.current_round,
            "total_rounds": self.total_rounds,
            "simulated_hours": self.simulated_hours,
            "total_simulation_hours": self.total_simulation_hours,
            "progress_percent": round(self.current_round / max(self.total_rounds, 1) * 100, 1),
            # Rodadas e tempo independentes por plataforma
            "twitter_current_round": self.twitter_current_round,
            "reddit_current_round": self.reddit_current_round,
            "twitter_simulated_hours": self.twitter_simulated_hours,
            "reddit_simulated_hours": self.reddit_simulated_hours,
            "twitter_running": self.twitter_running,
            "reddit_running": self.reddit_running,
            "twitter_completed": self.twitter_completed,
            "reddit_completed": self.reddit_completed,
            "twitter_actions_count": self.twitter_actions_count,
            "reddit_actions_count": self.reddit_actions_count,
            "total_actions_count": self.twitter_actions_count + self.reddit_actions_count,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "process_pid": self.process_pid,
        }
    
    def to_detail_dict(self) -> Dict[str, Any]:
        """Informações detalhadas incluindo ações recentes"""
        result = self.to_dict()
        result["recent_actions"] = [a.to_dict() for a in self.recent_actions]
        result["rounds_count"] = len(self.rounds)
        return result


class SimulationRunner:
    """
    Executor de simulação
    
    Responsável por:
    1. Executar simulação OASIS em processo de segundo plano
    2. Analisar logs de execução, registrar ações de cada Agent
    3. Fornecer interface de consulta de estado em tempo real
    4. Suportar operações de pausar/parar/retomar
    """
    
    # Diretório de armazenamento de estado de execução
    RUN_STATE_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../uploads/simulations'
    )
    
    # Diretório de scripts
    SCRIPTS_DIR = os.path.join(
        os.path.dirname(__file__),
        '../../scripts'
    )
    
    # Estado de execução em memória
    _run_states: Dict[str, SimulationRunState] = {}
    _processes: Dict[str, subprocess.Popen] = {}
    _action_queues: Dict[str, Queue] = {}
    _monitor_threads: Dict[str, threading.Thread] = {}
    _stdout_files: Dict[str, Any] = {}  # Armazenar handle de arquivo stdout
    _stderr_files: Dict[str, Any] = {}  # Armazenar handle de arquivo stderr
    
    # Configuração de atualização de memória do grafo
    _graph_memory_enabled: Dict[str, bool] = {}  # simulation_id -> enabled
    
    @classmethod
    def get_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Obter estado de execução"""
        if simulation_id in cls._run_states:
            return cls._run_states[simulation_id]
        
        # Tentar carregar do arquivo
        state = cls._load_run_state(simulation_id)
        if state:
            cls._run_states[simulation_id] = state
        return state
    
    @classmethod
    def _load_run_state(cls, simulation_id: str) -> Optional[SimulationRunState]:
        """Carregar estado de execução do arquivo"""
        state_file = os.path.join(cls.RUN_STATE_DIR, simulation_id, "run_state.json")
        if not os.path.exists(state_file):
            return None
        
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            state = SimulationRunState(
                simulation_id=simulation_id,
                runner_status=RunnerStatus(data.get("runner_status", "idle")),
                current_round=data.get("current_round", 0),
                total_rounds=data.get("total_rounds", 0),
                simulated_hours=data.get("simulated_hours", 0),
                total_simulation_hours=data.get("total_simulation_hours", 0),
                # Rodadas e tempo independentes por plataforma
                twitter_current_round=data.get("twitter_current_round", 0),
                reddit_current_round=data.get("reddit_current_round", 0),
                twitter_simulated_hours=data.get("twitter_simulated_hours", 0),
                reddit_simulated_hours=data.get("reddit_simulated_hours", 0),
                twitter_running=data.get("twitter_running", False),
                reddit_running=data.get("reddit_running", False),
                twitter_completed=data.get("twitter_completed", False),
                reddit_completed=data.get("reddit_completed", False),
                twitter_actions_count=data.get("twitter_actions_count", 0),
                reddit_actions_count=data.get("reddit_actions_count", 0),
                started_at=data.get("started_at"),
                updated_at=data.get("updated_at", datetime.now().isoformat()),
                completed_at=data.get("completed_at"),
                error=data.get("error"),
                process_pid=data.get("process_pid"),
            )
            
            # Carregar ações recentes
            actions_data = data.get("recent_actions", [])
            for a in actions_data:
                state.recent_actions.append(AgentAction(
                    round_num=a.get("round_num", 0),
                    timestamp=a.get("timestamp", ""),
                    platform=a.get("platform", ""),
                    agent_id=a.get("agent_id", 0),
                    agent_name=a.get("agent_name", ""),
                    action_type=a.get("action_type", ""),
                    action_args=a.get("action_args", {}),
                    result=a.get("result"),
                    success=a.get("success", True),
                ))
            
            return state
        except Exception as e:
            logger.error(f"Falha ao carregar estado de execução: {str(e)}")
            return None
    
    @classmethod
    def _save_run_state(cls, state: SimulationRunState):
        """Salvar estado de execução no arquivo"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        os.makedirs(sim_dir, exist_ok=True)
        state_file = os.path.join(sim_dir, "run_state.json")
        
        data = state.to_detail_dict()
        
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        cls._run_states[state.simulation_id] = state
    
    @classmethod
    def start_simulation(
        cls,
        simulation_id: str,
        platform: str = "parallel",  # twitter / reddit / parallel
        max_rounds: int = None,  # número máximo de rodadas (opcional, para truncar simulações longas)
        enable_graph_memory_update: bool = False,  # se deve atualizar atividades no grafo Zep
        graph_id: str = None  # ID do grafo Zep (obrigatório quando atualização do grafo está habilitada)
    ) -> SimulationRunState:
        """
        Iniciar simulação
        
        Args:
            simulation_id: ID da simulação
            platform: plataforma de execução (twitter/reddit/parallel)
            max_rounds: número máximo de rodadas (opcional, para truncar simulações longas)
            enable_graph_memory_update: se deve atualizar dinamicamente as atividades dos Agents no grafo Zep
            graph_id: ID do grafo Zep (obrigatório quando atualização do grafo está habilitada)
            
        Returns:
            SimulationRunState
        """
        # Verificar se já está em execução
        existing = cls.get_run_state(simulation_id)
        if existing and existing.runner_status in [RunnerStatus.RUNNING, RunnerStatus.STARTING]:
            raise ValueError(f"Simulação já está em execução: {simulation_id}")
        
        # Carregar configuração da simulação
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        config_path = os.path.join(sim_dir, "simulation_config.json")
        
        if not os.path.exists(config_path):
            raise ValueError(f"Configuração da simulação não existe, chame primeiro a interface /prepare")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Inicializar estado de execução
        time_config = config.get("time_config", {})
        total_hours = time_config.get("total_simulation_hours", 72)
        minutes_per_round = time_config.get("minutes_per_round", 30)
        total_rounds = int(total_hours * 60 / minutes_per_round)
        
        # Se o número máximo de rodadas foi especificado, truncar
        if max_rounds is not None and max_rounds > 0:
            original_rounds = total_rounds
            total_rounds = min(total_rounds, max_rounds)
            if total_rounds < original_rounds:
                logger.info(f"Rodadas truncadas: {original_rounds} -> {total_rounds} (max_rounds={max_rounds})")
        
        state = SimulationRunState(
            simulation_id=simulation_id,
            runner_status=RunnerStatus.STARTING,
            total_rounds=total_rounds,
            total_simulation_hours=total_hours,
            started_at=datetime.now().isoformat(),
        )
        
        cls._save_run_state(state)
        
        # Se a atualização de memória do grafo estiver habilitada, criar atualizador
        if enable_graph_memory_update:
            if not graph_id:
                raise ValueError("graph_id é obrigatório quando a atualização de memória do grafo está habilitada")
            
            try:
                ZepGraphMemoryManager.create_updater(simulation_id, graph_id)
                cls._graph_memory_enabled[simulation_id] = True
                logger.info(f"Atualização de memória do grafo habilitada: simulation_id={simulation_id}, graph_id={graph_id}")
            except Exception as e:
                logger.error(f"Falha ao criar atualizador de memória do grafo: {e}")
                cls._graph_memory_enabled[simulation_id] = False
        else:
            cls._graph_memory_enabled[simulation_id] = False
        
        # Determinar qual script executar (scripts localizados no diretório backend/scripts/)
        if platform == "twitter":
            script_name = "run_twitter_simulation.py"
            state.twitter_running = True
        elif platform == "reddit":
            script_name = "run_reddit_simulation.py"
            state.reddit_running = True
        else:
            script_name = "run_parallel_simulation.py"
            state.twitter_running = True
            state.reddit_running = True
        
        script_path = os.path.join(cls.SCRIPTS_DIR, script_name)
        
        if not os.path.exists(script_path):
            raise ValueError(f"Script não existe: {script_path}")
        
        # Criar fila de ações
        action_queue = Queue()
        cls._action_queues[simulation_id] = action_queue
        
        # Iniciar processo de simulação
        try:
            # Construir comando de execução, usando caminho completo
            # Nova estrutura de logs:
            #   twitter/actions.jsonl - Log de ações Twitter
            #   reddit/actions.jsonl  - Log de ações Reddit
            #   simulation.log        - Log do processo principal
            
            cmd = [
                sys.executable,  # Interpretador Python
                script_path,
                "--config", config_path,  # Usar caminho completo do arquivo de configuração
            ]
            
            # Se o número máximo de rodadas foi especificado, adicionar aos argumentos de linha de comando
            if max_rounds is not None and max_rounds > 0:
                cmd.extend(["--max-rounds", str(max_rounds)])
            
            # Criar arquivo de log principal, evitar bloqueio do processo por buffer cheio do pipe stdout/stderr
            main_log_path = os.path.join(sim_dir, "simulation.log")
            main_log_file = open(main_log_path, 'w', encoding='utf-8')
            
            # Configurar variáveis de ambiente do subprocesso, garantir codificação UTF-8 no Windows
            # Isso corrige o problema de bibliotecas de terceiros (como OASIS) não especificarem codificação ao ler arquivos
            env = os.environ.copy()
            env['PYTHONUTF8'] = '1'  # Suportado no Python 3.7+, faz todos os open() usarem UTF-8 por padrão
            env['PYTHONIOENCODING'] = 'utf-8'  # Garantir que stdout/stderr use UTF-8
            
            # Definir diretório de trabalho como diretório de simulação (banco de dados e outros arquivos serão gerados aqui)
            # Usar start_new_session=True para criar novo grupo de processos, garantindo que todos os subprocessos possam ser terminados via os.killpg
            process = subprocess.Popen(
                cmd,
                cwd=sim_dir,
                stdout=main_log_file,
                stderr=subprocess.STDOUT,  # stderr também escreve no mesmo arquivo
                text=True,
                encoding='utf-8',  # Especificar codificação explicitamente
                bufsize=1,
                env=env,  # Passar variáveis de ambiente com configuração UTF-8
                start_new_session=True,  # Criar novo grupo de processos, garantir que todos os processos relacionados possam ser terminados ao fechar o servidor
            )
            
            # Salvar handle de arquivo para fechamento posterior
            cls._stdout_files[simulation_id] = main_log_file
            cls._stderr_files[simulation_id] = None  # Não é mais necessário stderr separado
            
            state.process_pid = process.pid
            state.runner_status = RunnerStatus.RUNNING
            cls._processes[simulation_id] = process
            cls._save_run_state(state)
            
            # Iniciar thread de monitoramento
            monitor_thread = threading.Thread(
                target=cls._monitor_simulation,
                args=(simulation_id,),
                daemon=True
            )
            monitor_thread.start()
            cls._monitor_threads[simulation_id] = monitor_thread
            
            logger.info(f"Simulação iniciada com sucesso: {simulation_id}, pid={process.pid}, platform={platform}")
            
        except Exception as e:
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
            raise
        
        return state
    
    @classmethod
    def _monitor_simulation(cls, simulation_id: str):
        """Monitorar processo de simulação, analisar logs de ação"""
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        # Nova estrutura de logs: logs de ação por plataforma
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        process = cls._processes.get(simulation_id)
        state = cls.get_run_state(simulation_id)
        
        if not process or not state:
            return
        
        twitter_position = 0
        reddit_position = 0
        
        try:
            while process.poll() is None:  # Processo ainda em execução
                # Ler log de ações Twitter
                if os.path.exists(twitter_actions_log):
                    twitter_position = cls._read_action_log(
                        twitter_actions_log, twitter_position, state, "twitter"
                    )
                
                # Ler log de ações Reddit
                if os.path.exists(reddit_actions_log):
                    reddit_position = cls._read_action_log(
                        reddit_actions_log, reddit_position, state, "reddit"
                    )
                
                # Atualizar estado
                cls._save_run_state(state)
                time.sleep(2)
            
            # Após o processo terminar, ler os logs uma última vez
            if os.path.exists(twitter_actions_log):
                cls._read_action_log(twitter_actions_log, twitter_position, state, "twitter")
            if os.path.exists(reddit_actions_log):
                cls._read_action_log(reddit_actions_log, reddit_position, state, "reddit")
            
            # Processo encerrado
            exit_code = process.returncode
            
            if exit_code == 0:
                state.runner_status = RunnerStatus.COMPLETED
                state.completed_at = datetime.now().isoformat()
                logger.info(f"Simulação concluída: {simulation_id}")
            else:
                state.runner_status = RunnerStatus.FAILED
                # Ler informações de erro do arquivo de log principal
                main_log_path = os.path.join(sim_dir, "simulation.log")
                error_info = ""
                try:
                    if os.path.exists(main_log_path):
                        with open(main_log_path, 'r', encoding='utf-8') as f:
                            error_info = f.read()[-2000:]  # Pegar os últimos 2000 caracteres
                except Exception:
                    pass
                state.error = f"Código de saída do processo: {exit_code}, erro: {error_info}"
                logger.error(f"Simulação falhou: {simulation_id}, error={state.error}")
            
            state.twitter_running = False
            state.reddit_running = False
            cls._save_run_state(state)
            
        except Exception as e:
            logger.error(f"Exceção na thread de monitoramento: {simulation_id}, error={str(e)}")
            state.runner_status = RunnerStatus.FAILED
            state.error = str(e)
            cls._save_run_state(state)
        
        finally:
            # Parar atualizador de memória do grafo
            if cls._graph_memory_enabled.get(simulation_id, False):
                try:
                    ZepGraphMemoryManager.stop_updater(simulation_id)
                    logger.info(f"Atualização de memória do grafo parada: simulation_id={simulation_id}")
                except Exception as e:
                    logger.error(f"Falha ao parar atualizador de memória do grafo: {e}")
                cls._graph_memory_enabled.pop(simulation_id, None)
            
            # Limpar recursos do processo
            cls._processes.pop(simulation_id, None)
            cls._action_queues.pop(simulation_id, None)
            
            # Fechar handles de arquivo de log
            if simulation_id in cls._stdout_files:
                try:
                    cls._stdout_files[simulation_id].close()
                except Exception:
                    pass
                cls._stdout_files.pop(simulation_id, None)
            if simulation_id in cls._stderr_files and cls._stderr_files[simulation_id]:
                try:
                    cls._stderr_files[simulation_id].close()
                except Exception:
                    pass
                cls._stderr_files.pop(simulation_id, None)
    
    @classmethod
    def _read_action_log(
        cls, 
        log_path: str, 
        position: int, 
        state: SimulationRunState,
        platform: str
    ) -> int:
        """
        Ler arquivo de log de ações
        
        Args:
            log_path: caminho do arquivo de log
            position: posição da última leitura
            state: objeto de estado de execução
            platform: nome da plataforma (twitter/reddit)
            
        Returns:
            nova posição de leitura
        """
        # Verificar se a atualização de memória do grafo está habilitada
        graph_memory_enabled = cls._graph_memory_enabled.get(state.simulation_id, False)
        graph_updater = None
        if graph_memory_enabled:
            graph_updater = ZepGraphMemoryManager.get_updater(state.simulation_id)
        
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                f.seek(position)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            action_data = json.loads(line)
                            
                            # Processar entradas do tipo evento
                            if "event_type" in action_data:
                                event_type = action_data.get("event_type")
                                
                                # Detectar evento simulation_end, marcar plataforma como concluída
                                if event_type == "simulation_end":
                                    if platform == "twitter":
                                        state.twitter_completed = True
                                        state.twitter_running = False
                                        logger.info(f"Simulação Twitter concluída: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    elif platform == "reddit":
                                        state.reddit_completed = True
                                        state.reddit_running = False
                                        logger.info(f"Simulação Reddit concluída: {state.simulation_id}, total_rounds={action_data.get('total_rounds')}, total_actions={action_data.get('total_actions')}")
                                    
                                    # Verificar se todas as plataformas habilitadas foram concluídas
                                    # Se apenas uma plataforma foi executada, verificar apenas essa
                                    # Se duas plataformas foram executadas, ambas precisam estar concluídas
                                    all_completed = cls._check_all_platforms_completed(state)
                                    if all_completed:
                                        state.runner_status = RunnerStatus.COMPLETED
                                        state.completed_at = datetime.now().isoformat()
                                        logger.info(f"Simulação de todas as plataformas concluída: {state.simulation_id}")
                                
                                # Atualizar informações de rodada (do evento round_end)
                                elif event_type == "round_end":
                                    round_num = action_data.get("round", 0)
                                    simulated_hours = action_data.get("simulated_hours", 0)
                                    
                                    # Atualizar rodadas e tempo independentes por plataforma
                                    if platform == "twitter":
                                        if round_num > state.twitter_current_round:
                                            state.twitter_current_round = round_num
                                        state.twitter_simulated_hours = simulated_hours
                                    elif platform == "reddit":
                                        if round_num > state.reddit_current_round:
                                            state.reddit_current_round = round_num
                                        state.reddit_simulated_hours = simulated_hours
                                    
                                    # Rodada geral é o máximo entre as duas plataformas
                                    if round_num > state.current_round:
                                        state.current_round = round_num
                                    # Tempo geral é o máximo entre as duas plataformas
                                    state.simulated_hours = max(state.twitter_simulated_hours, state.reddit_simulated_hours)
                                
                                continue
                            
                            action = AgentAction(
                                round_num=action_data.get("round", 0),
                                timestamp=action_data.get("timestamp", datetime.now().isoformat()),
                                platform=platform,
                                agent_id=action_data.get("agent_id", 0),
                                agent_name=action_data.get("agent_name", ""),
                                action_type=action_data.get("action_type", ""),
                                action_args=action_data.get("action_args", {}),
                                result=action_data.get("result"),
                                success=action_data.get("success", True),
                            )
                            state.add_action(action)
                            
                            # Atualizar rodada
                            if action.round_num and action.round_num > state.current_round:
                                state.current_round = action.round_num
                            
                            # Se a atualização de memória do grafo estiver habilitada, enviar atividade ao Zep
                            if graph_updater:
                                graph_updater.add_activity_from_dict(action_data, platform)
                            
                        except json.JSONDecodeError:
                            pass
                return f.tell()
        except Exception as e:
            logger.warning(f"Falha ao ler log de ações: {log_path}, error={e}")
            return position
    
    @classmethod
    def _check_all_platforms_completed(cls, state: SimulationRunState) -> bool:
        """
        Verificar se todas as plataformas habilitadas concluíram a simulação
        
        Determinar se a plataforma está habilitada verificando se o arquivo actions.jsonl correspondente existe
        
        Returns:
            True se todas as plataformas habilitadas foram concluídas
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, state.simulation_id)
        twitter_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        reddit_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        
        # Verificar quais plataformas estão habilitadas (pela existência do arquivo)
        twitter_enabled = os.path.exists(twitter_log)
        reddit_enabled = os.path.exists(reddit_log)
        
        # Se a plataforma está habilitada mas não concluída, retornar False
        if twitter_enabled and not state.twitter_completed:
            return False
        if reddit_enabled and not state.reddit_completed:
            return False
        
        # Pelo menos uma plataforma está habilitada e concluída
        return twitter_enabled or reddit_enabled
    
    @classmethod
    def _terminate_process(cls, process: subprocess.Popen, simulation_id: str, timeout: int = 10):
        """
        Terminar processo e seus subprocessos de forma multiplataforma
        
        Args:
            process: processo a ser terminado
            simulation_id: ID da simulação (para logs)
            timeout: tempo limite de espera para o processo sair (segundos)
        """
        if IS_WINDOWS:
            # Windows: usar comando taskkill para terminar árvore de processos
            # /F = forçar término, /T = terminar árvore de processos (incluindo subprocessos)
            logger.info(f"Terminando árvore de processos (Windows): simulation={simulation_id}, pid={process.pid}")
            try:
                # Tentar término gracioso primeiro
                subprocess.run(
                    ['taskkill', '/PID', str(process.pid), '/T'],
                    capture_output=True,
                    timeout=5
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Forçar término
                    logger.warning(f"Processo não respondeu, forçando término: {simulation_id}")
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(process.pid), '/T'],
                        capture_output=True,
                        timeout=5
                    )
                    process.wait(timeout=5)
            except Exception as e:
                logger.warning(f"taskkill falhou, tentando terminate: {e}")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        else:
            # Unix: usar grupo de processos para terminar
            # Como start_new_session=True foi usado, o ID do grupo de processos é igual ao PID do processo principal
            pgid = os.getpgid(process.pid)
            logger.info(f"Terminando grupo de processos (Unix): simulation={simulation_id}, pgid={pgid}")
            
            # Enviar SIGTERM primeiro para todo o grupo de processos
            os.killpg(pgid, signal.SIGTERM)
            
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # Se não terminou após timeout, forçar envio de SIGKILL
                logger.warning(f"Grupo de processos não respondeu ao SIGTERM, forçando término: {simulation_id}")
                os.killpg(pgid, signal.SIGKILL)
                process.wait(timeout=5)
    
    @classmethod
    def stop_simulation(cls, simulation_id: str) -> SimulationRunState:
        """Parar simulação"""
        state = cls.get_run_state(simulation_id)
        if not state:
            raise ValueError(f"Simulação não existe: {simulation_id}")
        
        if state.runner_status not in [RunnerStatus.RUNNING, RunnerStatus.PAUSED]:
            raise ValueError(f"Simulação não está em execução: {simulation_id}, status={state.runner_status}")
        
        state.runner_status = RunnerStatus.STOPPING
        cls._save_run_state(state)
        
        # Terminar processo
        process = cls._processes.get(simulation_id)
        if process and process.poll() is None:
            try:
                cls._terminate_process(process, simulation_id)
            except ProcessLookupError:
                # Processo já não existe
                pass
            except Exception as e:
                logger.error(f"Falha ao terminar grupo de processos: {simulation_id}, error={e}")
                # Fallback para terminar processo diretamente
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    process.kill()
        
        state.runner_status = RunnerStatus.STOPPED
        state.twitter_running = False
        state.reddit_running = False
        state.completed_at = datetime.now().isoformat()
        cls._save_run_state(state)
        
        # Parar atualizador de memória do grafo
        if cls._graph_memory_enabled.get(simulation_id, False):
            try:
                ZepGraphMemoryManager.stop_updater(simulation_id)
                logger.info(f"Atualização de memória do grafo parada: simulation_id={simulation_id}")
            except Exception as e:
                logger.error(f"Falha ao parar atualizador de memória do grafo: {e}")
            cls._graph_memory_enabled.pop(simulation_id, None)
        
        logger.info(f"Simulação parada: {simulation_id}")
        return state
    
    @classmethod
    def _read_actions_from_file(
        cls,
        file_path: str,
        default_platform: Optional[str] = None,
        platform_filter: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Ler ações de um único arquivo de ações
        
        Args:
            file_path: caminho do arquivo de log de ações
            default_platform: plataforma padrão (usada quando o registro de ação não tem campo platform)
            platform_filter: filtro de plataforma
            agent_id: filtro de Agent ID
            round_num: filtro de rodada
        """
        if not os.path.exists(file_path):
            return []
        
        actions = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    
                    # Pular registros que não são ações (como eventos simulation_start, round_start, round_end, etc.)
                    if "event_type" in data:
                        continue
                    
                    # Pular registros sem agent_id (não são ações de Agent)
                    if "agent_id" not in data:
                        continue
                    
                    # Obter plataforma: priorizar platform do registro, caso contrário usar plataforma padrão
                    record_platform = data.get("platform") or default_platform or ""
                    
                    # Filtrar
                    if platform_filter and record_platform != platform_filter:
                        continue
                    if agent_id is not None and data.get("agent_id") != agent_id:
                        continue
                    if round_num is not None and data.get("round") != round_num:
                        continue
                    
                    actions.append(AgentAction(
                        round_num=data.get("round", 0),
                        timestamp=data.get("timestamp", ""),
                        platform=record_platform,
                        agent_id=data.get("agent_id", 0),
                        agent_name=data.get("agent_name", ""),
                        action_type=data.get("action_type", ""),
                        action_args=data.get("action_args", {}),
                        result=data.get("result"),
                        success=data.get("success", True),
                    ))
                    
                except json.JSONDecodeError:
                    continue
        
        return actions
    
    @classmethod
    def get_all_actions(
        cls,
        simulation_id: str,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Obter histórico completo de ações de todas as plataformas (sem limite de paginação)
        
        Args:
            simulation_id: ID da simulação
            platform: filtro de plataforma (twitter/reddit)
            agent_id: filtro de Agent
            round_num: filtro de rodada
            
        Returns:
            Lista completa de ações (ordenada por timestamp, mais recente primeiro)
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        actions = []
        
        # Ler arquivo de ações Twitter (definir platform como twitter automaticamente com base no caminho)
        twitter_actions_log = os.path.join(sim_dir, "twitter", "actions.jsonl")
        if not platform or platform == "twitter":
            actions.extend(cls._read_actions_from_file(
                twitter_actions_log,
                default_platform="twitter",  # Preencher campo platform automaticamente
                platform_filter=platform,
                agent_id=agent_id, 
                round_num=round_num
            ))
        
        # Ler arquivo de ações Reddit (definir platform como reddit automaticamente com base no caminho)
        reddit_actions_log = os.path.join(sim_dir, "reddit", "actions.jsonl")
        if not platform or platform == "reddit":
            actions.extend(cls._read_actions_from_file(
                reddit_actions_log,
                default_platform="reddit",  # Preencher campo platform automaticamente
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            ))
        
        # Se arquivos por plataforma não existem, tentar ler formato de arquivo único antigo
        if not actions:
            actions_log = os.path.join(sim_dir, "actions.jsonl")
            actions = cls._read_actions_from_file(
                actions_log,
                default_platform=None,  # Arquivo de formato antigo deve ter campo platform
                platform_filter=platform,
                agent_id=agent_id,
                round_num=round_num
            )
        
        # Ordenar por timestamp (mais recente primeiro)
        actions.sort(key=lambda x: x.timestamp, reverse=True)
        
        return actions
    
    @classmethod
    def get_actions(
        cls,
        simulation_id: str,
        limit: int = 100,
        offset: int = 0,
        platform: Optional[str] = None,
        agent_id: Optional[int] = None,
        round_num: Optional[int] = None
    ) -> List[AgentAction]:
        """
        Obter histórico de ações (com paginação)
        
        Args:
            simulation_id: ID da simulação
            limit: limite de quantidade retornada
            offset: deslocamento
            platform: filtro de plataforma
            agent_id: filtro de Agent
            round_num: filtro de rodada
            
        Returns:
            lista de ações
        """
        actions = cls.get_all_actions(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            round_num=round_num
        )
        
        # Paginação
        return actions[offset:offset + limit]
    
    @classmethod
    def get_timeline(
        cls,
        simulation_id: str,
        start_round: int = 0,
        end_round: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Obter timeline da simulação (resumido por rodada)
        
        Args:
            simulation_id: ID da simulação
            start_round: rodada inicial
            end_round: rodada final
            
        Returns:
            informações resumidas de cada rodada
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        # Agrupar por rodada
        rounds: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            round_num = action.round_num
            
            if round_num < start_round:
                continue
            if end_round is not None and round_num > end_round:
                continue
            
            if round_num not in rounds:
                rounds[round_num] = {
                    "round_num": round_num,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "active_agents": set(),
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            r = rounds[round_num]
            
            if action.platform == "twitter":
                r["twitter_actions"] += 1
            else:
                r["reddit_actions"] += 1
            
            r["active_agents"].add(action.agent_id)
            r["action_types"][action.action_type] = r["action_types"].get(action.action_type, 0) + 1
            r["last_action_time"] = action.timestamp
        
        # Converter para lista
        result = []
        for round_num in sorted(rounds.keys()):
            r = rounds[round_num]
            result.append({
                "round_num": round_num,
                "twitter_actions": r["twitter_actions"],
                "reddit_actions": r["reddit_actions"],
                "total_actions": r["twitter_actions"] + r["reddit_actions"],
                "active_agents_count": len(r["active_agents"]),
                "active_agents": list(r["active_agents"]),
                "action_types": r["action_types"],
                "first_action_time": r["first_action_time"],
                "last_action_time": r["last_action_time"],
            })
        
        return result
    
    @classmethod
    def get_agent_stats(cls, simulation_id: str) -> List[Dict[str, Any]]:
        """
        Obter estatísticas de cada Agent
        
        Returns:
            lista de estatísticas de Agent
        """
        actions = cls.get_actions(simulation_id, limit=10000)
        
        agent_stats: Dict[int, Dict[str, Any]] = {}
        
        for action in actions:
            agent_id = action.agent_id
            
            if agent_id not in agent_stats:
                agent_stats[agent_id] = {
                    "agent_id": agent_id,
                    "agent_name": action.agent_name,
                    "total_actions": 0,
                    "twitter_actions": 0,
                    "reddit_actions": 0,
                    "action_types": {},
                    "first_action_time": action.timestamp,
                    "last_action_time": action.timestamp,
                }
            
            stats = agent_stats[agent_id]
            stats["total_actions"] += 1
            
            if action.platform == "twitter":
                stats["twitter_actions"] += 1
            else:
                stats["reddit_actions"] += 1
            
            stats["action_types"][action.action_type] = stats["action_types"].get(action.action_type, 0) + 1
            stats["last_action_time"] = action.timestamp
        
        # Ordenar por total de ações
        result = sorted(agent_stats.values(), key=lambda x: x["total_actions"], reverse=True)
        
        return result
    
    @classmethod
    def cleanup_simulation_logs(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Limpar logs de execução da simulação (para forçar reinício da simulação)
        
        Irá deletar os seguintes arquivos:
        - run_state.json
        - twitter/actions.jsonl
        - reddit/actions.jsonl
        - simulation.log
        - stdout.log / stderr.log
        - twitter_simulation.db (banco de dados da simulação)
        - reddit_simulation.db (banco de dados da simulação)
        - env_status.json (status do ambiente)
        
        Nota: não deletará arquivos de configuração (simulation_config.json) nem arquivos de profile
        
        Args:
            simulation_id: ID da simulação
            
        Returns:
            informações do resultado da limpeza
        """
        import shutil
        
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        if not os.path.exists(sim_dir):
            return {"success": True, "message": "Diretório de simulação não existe, não é necessário limpar"}
        
        cleaned_files = []
        errors = []
        
        # Lista de arquivos a deletar (incluindo arquivos de banco de dados)
        files_to_delete = [
            "run_state.json",
            "simulation.log",
            "stdout.log",
            "stderr.log",
            "twitter_simulation.db",  # Banco de dados da plataforma Twitter
            "reddit_simulation.db",   # Banco de dados da plataforma Reddit
            "env_status.json",        # Arquivo de status do ambiente
        ]
        
        # Lista de diretórios a limpar (contêm logs de ação)
        dirs_to_clean = ["twitter", "reddit"]
        
        # Deletar arquivos
        for filename in files_to_delete:
            file_path = os.path.join(sim_dir, filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    cleaned_files.append(filename)
                except Exception as e:
                    errors.append(f"Falha ao deletar {filename}: {str(e)}")
        
        # Limpar logs de ação nos diretórios de plataforma
        for dir_name in dirs_to_clean:
            dir_path = os.path.join(sim_dir, dir_name)
            if os.path.exists(dir_path):
                actions_file = os.path.join(dir_path, "actions.jsonl")
                if os.path.exists(actions_file):
                    try:
                        os.remove(actions_file)
                        cleaned_files.append(f"{dir_name}/actions.jsonl")
                    except Exception as e:
                        errors.append(f"Falha ao deletar {dir_name}/actions.jsonl: {str(e)}")
        
        # Limpar estado de execução em memória
        if simulation_id in cls._run_states:
            del cls._run_states[simulation_id]
        
        logger.info(f"Limpeza de logs da simulação concluída: {simulation_id}, arquivos deletados: {cleaned_files}")
        
        return {
            "success": len(errors) == 0,
            "cleaned_files": cleaned_files,
            "errors": errors if errors else None
        }
    
    # Flag para prevenir limpeza duplicada
    _cleanup_done = False
    
    @classmethod
    def cleanup_all_simulations(cls):
        """
        Limpar todos os processos de simulação em execução
        
        Chamado ao fechar o servidor, garantir que todos os subprocessos sejam terminados
        """
        # Prevenir limpeza duplicada
        if cls._cleanup_done:
            return
        cls._cleanup_done = True
        
        # Verificar se há conteúdo para limpar (evitar que processos vazios imprimam logs inúteis)
        has_processes = bool(cls._processes)
        has_updaters = bool(cls._graph_memory_enabled)
        
        if not has_processes and not has_updaters:
            return  # Nada para limpar, retornar silenciosamente
        
        logger.info("Limpando todos os processos de simulação...")
        
        # Primeiro parar todos os atualizadores de memória do grafo (stop_all imprime logs internamente)
        try:
            ZepGraphMemoryManager.stop_all()
        except Exception as e:
            logger.error(f"Falha ao parar atualizador de memória do grafo: {e}")
        cls._graph_memory_enabled.clear()
        
        # Copiar dicionário para evitar modificação durante iteração
        processes = list(cls._processes.items())
        
        for simulation_id, process in processes:
            try:
                if process.poll() is None:  # Processo ainda em execução
                    logger.info(f"Terminando processo de simulação: {simulation_id}, pid={process.pid}")
                    
                    try:
                        # Usar método de término de processo multiplataforma
                        cls._terminate_process(process, simulation_id, timeout=5)
                    except (ProcessLookupError, OSError):
                        # Processo pode não existir mais, tentar terminar diretamente
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except Exception:
                            process.kill()
                    
                    # Atualizar run_state.json
                    state = cls.get_run_state(simulation_id)
                    if state:
                        state.runner_status = RunnerStatus.STOPPED
                        state.twitter_running = False
                        state.reddit_running = False
                        state.completed_at = datetime.now().isoformat()
                        state.error = "Servidor fechado, simulação terminada"
                        cls._save_run_state(state)
                    
                    # Atualizar state.json simultaneamente, definir status como stopped
                    try:
                        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
                        state_file = os.path.join(sim_dir, "state.json")
                        logger.info(f"Tentando atualizar state.json: {state_file}")
                        if os.path.exists(state_file):
                            with open(state_file, 'r', encoding='utf-8') as f:
                                state_data = json.load(f)
                            state_data['status'] = 'stopped'
                            state_data['updated_at'] = datetime.now().isoformat()
                            with open(state_file, 'w', encoding='utf-8') as f:
                                json.dump(state_data, f, indent=2, ensure_ascii=False)
                            logger.info(f"state.json atualizado para status stopped: {simulation_id}")
                        else:
                            logger.warning(f"state.json não existe: {state_file}")
                    except Exception as state_err:
                        logger.warning(f"Falha ao atualizar state.json: {simulation_id}, error={state_err}")
                        
            except Exception as e:
                logger.error(f"Falha ao limpar processo: {simulation_id}, error={e}")
        
        # Limpar handles de arquivo
        for simulation_id, file_handle in list(cls._stdout_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stdout_files.clear()
        
        for simulation_id, file_handle in list(cls._stderr_files.items()):
            try:
                if file_handle:
                    file_handle.close()
            except Exception:
                pass
        cls._stderr_files.clear()
        
        # Limpar estado em memória
        cls._processes.clear()
        cls._action_queues.clear()
        
        logger.info("Limpeza de processos de simulação concluída")
    
    @classmethod
    def register_cleanup(cls):
        """
        Registrar função de limpeza
        
        Chamado na inicialização da aplicação Flask, garantir que todos os processos de simulação sejam limpos ao fechar o servidor
        """
        global _cleanup_registered
        
        if _cleanup_registered:
            return
        
        # No modo debug do Flask, registrar limpeza apenas no subprocesso reloader (processo que realmente executa a aplicação)
        # WERKZEUG_RUN_MAIN=true indica que é o subprocesso reloader
        # Se não for modo debug, essa variável de ambiente não existe, e também precisa registrar
        is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
        is_debug_mode = os.environ.get('FLASK_DEBUG') == '1' or os.environ.get('WERKZEUG_RUN_MAIN') is not None
        
        # No modo debug, registrar apenas no subprocesso reloader; no modo não-debug, sempre registrar
        if is_debug_mode and not is_reloader_process:
            _cleanup_registered = True  # Marcar como registrado, prevenir que subprocessos tentem novamente
            return
        
        # Salvar handlers de sinal originais
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        # SIGHUP existe apenas em sistemas Unix (macOS/Linux), Windows não tem
        original_sighup = None
        has_sighup = hasattr(signal, 'SIGHUP')
        if has_sighup:
            original_sighup = signal.getsignal(signal.SIGHUP)
        
        def cleanup_handler(signum=None, frame=None):
            """Handler de sinal: primeiro limpar processos de simulação, depois chamar handler original"""
            # Imprimir log apenas quando há processos para limpar
            if cls._processes or cls._graph_memory_enabled:
                logger.info(f"Sinal {signum} recebido, iniciando limpeza...")
            cls.cleanup_all_simulations()
            
            # Chamar handler de sinal original, deixar Flask sair normalmente
            if signum == signal.SIGINT and callable(original_sigint):
                original_sigint(signum, frame)
            elif signum == signal.SIGTERM and callable(original_sigterm):
                original_sigterm(signum, frame)
            elif has_sighup and signum == signal.SIGHUP:
                # SIGHUP: enviado quando o terminal é fechado
                if callable(original_sighup):
                    original_sighup(signum, frame)
                else:
                    # Comportamento padrão: sair normalmente
                    sys.exit(0)
            else:
                # Se o handler original não for callable (como SIG_DFL), usar comportamento padrão
                raise KeyboardInterrupt
        
        # Registrar handler atexit (como fallback)
        atexit.register(cls.cleanup_all_simulations)
        
        # Registrar handlers de sinal (apenas na thread principal)
        try:
            # SIGTERM: sinal padrão do comando kill
            signal.signal(signal.SIGTERM, cleanup_handler)
            # SIGINT: Ctrl+C
            signal.signal(signal.SIGINT, cleanup_handler)
            # SIGHUP: terminal fechado (apenas sistemas Unix)
            if has_sighup:
                signal.signal(signal.SIGHUP, cleanup_handler)
        except ValueError:
            # Não está na thread principal, só pode usar atexit
            logger.warning("Não foi possível registrar handlers de sinal (não está na thread principal), usando apenas atexit")
        
        _cleanup_registered = True
    
    @classmethod
    def get_running_simulations(cls) -> List[str]:
        """
        Obter lista de IDs de todas as simulações em execução
        """
        running = []
        for sim_id, process in cls._processes.items():
            if process.poll() is None:
                running.append(sim_id)
        return running
    
    # ============== Funcionalidade de Interview ==============
    
    @classmethod
    def check_env_alive(cls, simulation_id: str) -> bool:
        """
        Verificar se o ambiente de simulação está ativo (pode receber comandos de Interview)

        Args:
            simulation_id: ID da simulação

        Returns:
            True indica ambiente ativo, False indica ambiente fechado
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            return False

        ipc_client = SimulationIPCClient(sim_dir)
        return ipc_client.check_env_alive()

    @classmethod
    def get_env_status_detail(cls, simulation_id: str) -> Dict[str, Any]:
        """
        Obter informações detalhadas de status do ambiente de simulação

        Args:
            simulation_id: ID da simulação

        Returns:
            dicionário de detalhes do status, contendo status, twitter_available, reddit_available, timestamp
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        status_file = os.path.join(sim_dir, "env_status.json")
        
        default_status = {
            "status": "stopped",
            "twitter_available": False,
            "reddit_available": False,
            "timestamp": None
        }
        
        if not os.path.exists(status_file):
            return default_status
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            return {
                "status": status.get("status", "stopped"),
                "twitter_available": status.get("twitter_available", False),
                "reddit_available": status.get("reddit_available", False),
                "timestamp": status.get("timestamp")
            }
        except (json.JSONDecodeError, OSError):
            return default_status

    @classmethod
    def interview_agent(
        cls,
        simulation_id: str,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """
        Entrevistar um único Agent

        Args:
            simulation_id: ID da simulação
            agent_id: ID do Agent
            prompt: pergunta da entrevista
            platform: plataforma especificada (opcional)
                - "twitter": entrevistar apenas na plataforma Twitter
                - "reddit": entrevistar apenas na plataforma Reddit
                - None: em simulação de dupla plataforma, entrevistar ambas simultaneamente, retornar resultado integrado
            timeout: tempo limite (segundos)

        Returns:
            dicionário de resultado da entrevista

        Raises:
            ValueError: simulação não existe ou ambiente não está em execução
            TimeoutError: timeout aguardando resposta
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulação não existe: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"Ambiente de simulação não está em execução ou foi fechado, não é possível executar Interview: {simulation_id}")

        logger.info(f"Enviando comando de Interview: simulation_id={simulation_id}, agent_id={agent_id}, platform={platform}")

        response = ipc_client.send_interview(
            agent_id=agent_id,
            prompt=prompt,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "agent_id": agent_id,
                "prompt": prompt,
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "agent_id": agent_id,
                "prompt": prompt,
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_agents_batch(
        cls,
        simulation_id: str,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> Dict[str, Any]:
        """
        Entrevistar múltiplos Agents em lote

        Args:
            simulation_id: ID da simulação
            interviews: lista de entrevistas, cada elemento contém {"agent_id": int, "prompt": str, "platform": str(opcional)}
            platform: plataforma padrão (opcional, será sobrescrita pelo platform de cada item de entrevista)
                - "twitter": por padrão entrevistar apenas na plataforma Twitter
                - "reddit": por padrão entrevistar apenas na plataforma Reddit
                - None: em simulação de dupla plataforma, cada Agent é entrevistado em ambas simultaneamente
            timeout: tempo limite (segundos)

        Returns:
            dicionário de resultado da entrevista em lote

        Raises:
            ValueError: simulação não existe ou ambiente não está em execução
            TimeoutError: timeout aguardando resposta
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulação não existe: {simulation_id}")

        ipc_client = SimulationIPCClient(sim_dir)

        if not ipc_client.check_env_alive():
            raise ValueError(f"Ambiente de simulação não está em execução ou foi fechado, não é possível executar Interview: {simulation_id}")

        logger.info(f"Enviando comando de Interview em lote: simulation_id={simulation_id}, count={len(interviews)}, platform={platform}")

        response = ipc_client.send_batch_interview(
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )

        if response.status.value == "completed":
            return {
                "success": True,
                "interviews_count": len(interviews),
                "result": response.result,
                "timestamp": response.timestamp
            }
        else:
            return {
                "success": False,
                "interviews_count": len(interviews),
                "error": response.error,
                "timestamp": response.timestamp
            }
    
    @classmethod
    def interview_all_agents(
        cls,
        simulation_id: str,
        prompt: str,
        platform: str = None,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        Entrevistar todos os Agents (entrevista global)

        Entrevistar todos os Agents da simulação com a mesma pergunta

        Args:
            simulation_id: ID da simulação
            prompt: pergunta da entrevista (mesma pergunta para todos os Agents)
            platform: plataforma especificada (opcional)
                - "twitter": entrevistar apenas na plataforma Twitter
                - "reddit": entrevistar apenas na plataforma Reddit
                - None: em simulação de dupla plataforma, cada Agent é entrevistado em ambas simultaneamente
            timeout: tempo limite (segundos)

        Returns:
            dicionário de resultado da entrevista global
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulação não existe: {simulation_id}")

        # Obter informações de todos os Agents do arquivo de configuração
        config_path = os.path.join(sim_dir, "simulation_config.json")
        if not os.path.exists(config_path):
            raise ValueError(f"Configuração da simulação não existe: {simulation_id}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        agent_configs = config.get("agent_configs", [])
        if not agent_configs:
            raise ValueError(f"Nenhum Agent na configuração da simulação: {simulation_id}")

        # Construir lista de entrevistas em lote
        interviews = []
        for agent_config in agent_configs:
            agent_id = agent_config.get("agent_id")
            if agent_id is not None:
                interviews.append({
                    "agent_id": agent_id,
                    "prompt": prompt
                })

        logger.info(f"Enviando comando de Interview global: simulation_id={simulation_id}, agent_count={len(interviews)}, platform={platform}")

        return cls.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=interviews,
            platform=platform,
            timeout=timeout
        )
    
    @classmethod
    def close_simulation_env(
        cls,
        simulation_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        Fechar ambiente de simulação (sem parar o processo de simulação)
        
        Enviar comando de fechamento de ambiente à simulação, permitindo saída graciosa do modo espera de comandos
        
        Args:
            simulation_id: ID da simulação
            timeout: tempo limite (segundos)
            
        Returns:
            dicionário de resultado da operação
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        if not os.path.exists(sim_dir):
            raise ValueError(f"Simulação não existe: {simulation_id}")
        
        ipc_client = SimulationIPCClient(sim_dir)
        
        if not ipc_client.check_env_alive():
            return {
                "success": True,
                "message": "Ambiente já está fechado"
            }
        
        logger.info(f"Enviando comando de fechamento de ambiente: simulation_id={simulation_id}")
        
        try:
            response = ipc_client.send_close_env(timeout=timeout)
            
            return {
                "success": response.status.value == "completed",
                "message": "Comando de fechamento de ambiente enviado",
                "result": response.result,
                "timestamp": response.timestamp
            }
        except TimeoutError:
            # Timeout pode ser porque o ambiente está sendo fechado
            return {
                "success": True,
                "message": "Comando de fechamento de ambiente enviado (timeout aguardando resposta, ambiente pode estar sendo fechado)"
            }
    
    @classmethod
    def _get_interview_history_from_db(
        cls,
        db_path: str,
        platform_name: str,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Obter histórico de Interview de um único banco de dados"""
        import sqlite3
        
        if not os.path.exists(db_path):
            return []
        
        results = []
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            if agent_id is not None:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview' AND user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))
            else:
                cursor.execute("""
                    SELECT user_id, info, created_at
                    FROM trace
                    WHERE action = 'interview'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            for user_id, info_json, created_at in cursor.fetchall():
                try:
                    info = json.loads(info_json) if info_json else {}
                except json.JSONDecodeError:
                    info = {"raw": info_json}
                
                results.append({
                    "agent_id": user_id,
                    "response": info.get("response", info),
                    "prompt": info.get("prompt", ""),
                    "timestamp": created_at,
                    "platform": platform_name
                })
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Falha ao ler histórico de Interview ({platform_name}): {e}")
        
        return results

    @classmethod
    def get_interview_history(
        cls,
        simulation_id: str,
        platform: str = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Obter registros de histórico de Interview (lidos do banco de dados)
        
        Args:
            simulation_id: ID da simulação
            platform: tipo de plataforma (reddit/twitter/None)
                - "reddit": obter apenas histórico da plataforma Reddit
                - "twitter": obter apenas histórico da plataforma Twitter
                - None: obter histórico de todas as plataformas
            agent_id: ID do Agent especificado (opcional, obter apenas histórico desse Agent)
            limit: limite de quantidade retornada por plataforma
            
        Returns:
            lista de registros de histórico de Interview
        """
        sim_dir = os.path.join(cls.RUN_STATE_DIR, simulation_id)
        
        results = []
        
        # Determinar plataformas a consultar
        if platform in ("reddit", "twitter"):
            platforms = [platform]
        else:
            # Quando platform não é especificado, consultar ambas plataformas
            platforms = ["twitter", "reddit"]
        
        for p in platforms:
            db_path = os.path.join(sim_dir, f"{p}_simulation.db")
            platform_results = cls._get_interview_history_from_db(
                db_path=db_path,
                platform_name=p,
                agent_id=agent_id,
                limit=limit
            )
            results.extend(platform_results)
        
        # Ordenar por tempo decrescente
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        # Se consultou múltiplas plataformas, limitar total
        if len(platforms) > 1 and len(results) > limit:
            results = results[:limit]
        
        return results

