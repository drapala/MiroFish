<template>
  <div class="home-container">
    <!-- Barra de navega\u00e7\u00e3o superior -->
    <nav class=”navbar”>
      <div class=”nav-brand”>MIROFISH</div>
      <div class=”nav-links”>
        <a href=”https://github.com/666ghj/MiroFish” target=”_blank” class=”github-link”>
          Visite nosso Github <span class=”arrow”>↗</span>
        </a>
      </div>
    </nav>

    <div class=”main-content”>
      <!-- Parte superior: \u00c1rea Hero -->
      <section class=”hero-section”>
        <div class=”hero-left”>
          <div class=”tag-row”>
            <span class=”orange-tag”>Motor de Intelig\u00eancia Coletiva Simples e Universal</span>
            <span class=”version-text”>/ v0.1-pr\u00e9via</span>
          </div>

          <h1 class=”main-title”>
            Envie qualquer relat\u00f3rio<br>
            <span class=”gradient-text”>Simule o futuro agora</span>
          </h1>

          <div class=”hero-desc”>
            <p>
              Mesmo com apenas um trecho de texto, <span class=”highlight-bold”>MiroFish</span> pode gerar automaticamente um mundo paralelo com at\u00e9 <span class=”highlight-orange”>milh\u00f5es de Agents</span> baseado nas sementes reais contidas nele. Injete vari\u00e1veis com vis\u00e3o privilegiada e encontre o <span class=”highlight-code”>”melhor local”</span> em intera\u00e7\u00f5es coletivas complexas em ambientes din\u00e2micos
            </p>
            <p class=”slogan-text”>
              Deixe o futuro se ensaiar entre Agents, deixe as decis\u00f5es vencerem ap\u00f3s mil batalhas<span class=”blinking-cursor”>_</span>
            </p>
          </div>
           
          <div class="decoration-square"></div>
        </div>
        
        <div class="hero-right">
          <!-- Área do Logo -->
          <div class="logo-container">
            <img src="../assets/logo/MiroFish_logo_left.jpeg" alt="MiroFish Logo" class="hero-logo" />
          </div>
          
          <button class="scroll-down-btn" @click="scrollToBottom">
            ↓
          </button>
        </div>
      </section>

      <!-- Parte inferior: Layout de duas colunas -->
      <section class="dashboard-section">
        <!-- Coluna esquerda: Status e etapas -->
        <div class="left-panel">
          <div class="panel-header">
            <span class="status-dot">■</span> Status do Sistema
          </div>

          <h2 class="section-title">Pronto</h2>
          <p class="section-desc">
            Motor de predi\u00e7\u00e3o em espera. Envie m\u00faltiplos dados n\u00e3o estruturados para inicializar a sequ\u00eancia de simula\u00e7\u00e3o
          </p>

          <!-- Cart\u00f5es de m\u00e9tricas -->
          <div class="metrics-row">
            <div class="metric-card">
              <div class="metric-value">Baixo Custo</div>
              <div class="metric-label">Simula\u00e7\u00e3o padr\u00e3o m\u00e9dia 5$/vez</div>
            </div>
            <div class="metric-card">
              <div class="metric-value">Alta Disponibilidade</div>
              <div class="metric-label">At\u00e9 milh\u00f5es de Agents em simula\u00e7\u00e3o</div>
            </div>
          </div>

          <!-- Introdu\u00e7\u00e3o das etapas de simula\u00e7\u00e3o -->
          <div class="steps-container">
            <div class="steps-header">
               <span class="diamond-icon">◇</span> Sequ\u00eancia do Fluxo de Trabalho
            </div>
            <div class="workflow-list">
              <div class="workflow-item">
                <span class="step-num">01</span>
                <div class="step-info">
                  <div class="step-title">Constru\u00e7\u00e3o do Grafo</div>
                  <div class="step-desc">Extra\u00e7\u00e3o de sementes reais & Inje\u00e7\u00e3o de mem\u00f3ria individual e coletiva & Constru\u00e7\u00e3o GraphRAG</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">02</span>
                <div class="step-info">
                  <div class="step-title">Configura\u00e7\u00e3o do Ambiente</div>
                  <div class="step-desc">Extra\u00e7\u00e3o de rela\u00e7\u00f5es entre entidades & Gera\u00e7\u00e3o de personas & Inje\u00e7\u00e3o de par\u00e2metros de simula\u00e7\u00e3o</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">03</span>
                <div class="step-info">
                  <div class="step-title">Iniciar Simula\u00e7\u00e3o</div>
                  <div class="step-desc">Simula\u00e7\u00e3o paralela em duas plataformas & An\u00e1lise autom\u00e1tica de demandas de predi\u00e7\u00e3o & Atualiza\u00e7\u00e3o din\u00e2mica de mem\u00f3ria temporal</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">04</span>
                <div class="step-info">
                  <div class="step-title">Gera\u00e7\u00e3o de Relat\u00f3rio</div>
                  <div class="step-desc">ReportAgent possui um rico conjunto de ferramentas para intera\u00e7\u00e3o profunda com o ambiente p\u00f3s-simula\u00e7\u00e3o</div>
                </div>
              </div>
              <div class="workflow-item">
                <span class="step-num">05</span>
                <div class="step-info">
                  <div class="step-title">Intera\u00e7\u00e3o Profunda</div>
                  <div class="step-desc">Converse com qualquer indiv\u00edduo do mundo simulado & Converse com o ReportAgent</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Coluna direita: Console interativo -->
        <div class="right-panel">
          <div class="console-box">
            <!-- \u00c1rea de upload -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">01 / Sementes Reais</span>
                <span class="console-meta">Formatos suportados: PDF, MD, TXT</span>
              </div>
              
              <div 
                class="upload-zone"
                :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
                @dragover.prevent="handleDragOver"
                @dragleave.prevent="handleDragLeave"
                @drop.prevent="handleDrop"
                @click="triggerFileInput"
              >
                <input
                  ref="fileInput"
                  type="file"
                  multiple
                  accept=".pdf,.md,.txt"
                  @change="handleFileSelect"
                  style="display: none"
                  :disabled="loading"
                />
                
                <div v-if="files.length === 0" class="upload-placeholder">
                  <div class="upload-icon">↑</div>
                  <div class="upload-title">Arraste arquivos para enviar</div>
                  <div class="upload-hint">ou clique para navegar no sistema de arquivos</div>
                </div>
                
                <div v-else class="file-list">
                  <div v-for="(file, index) in files" :key="index" class="file-item">
                    <span class="file-icon">📄</span>
                    <span class="file-name">{{ file.name }}</span>
                    <button @click.stop="removeFile(index)" class="remove-btn">×</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Linha divis\u00f3ria -->
            <div class="console-divider">
              <span>Par\u00e2metros de Entrada</span>
            </div>

            <!-- \u00c1rea de entrada -->
            <div class="console-section">
              <div class="console-header">
                <span class="console-label">>_ 02 / Prompt de Simula\u00e7\u00e3o</span>
              </div>
              <div class="input-wrapper">
                <textarea
                  v-model="formData.simulationRequirement"
                  class="code-input"
                  placeholder="// Insira em linguagem natural a demanda de simula\u00e7\u00e3o ou predi\u00e7\u00e3o (ex: Se a universidade publicar um comunicado revogando a puni\u00e7\u00e3o, qual ser\u00e1 a tend\u00eancia da opini\u00e3o p\u00fablica?)"
                  rows="6"
                  :disabled="loading"
                ></textarea>
                <div class="model-badge">Motor: MiroFish-V1.0</div>
              </div>
            </div>

            <!-- Bot\u00e3o de iniciar -->
            <div class="console-section btn-section">
              <button
                class="start-engine-btn"
                @click="startSimulation"
                :disabled="!canSubmit || loading"
              >
                <span v-if="!loading">Iniciar Motor</span>
                <span v-else>Inicializando...</span>
                <span class="btn-arrow">→</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Banco de dados de projetos hist\u00f3ricos -->
      <HistoryDatabase />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import HistoryDatabase from '../components/HistoryDatabase.vue'

const router = useRouter()

// Dados do formul\u00e1rio
const formData = ref({
  simulationRequirement: ''
})

// Lista de arquivos
const files = ref([])

// Estado
const loading = ref(false)
const error = ref('')
const isDragOver = ref(false)

// Refer\u00eancia do input de arquivo
const fileInput = ref(null)

// Computed: pode enviar
const canSubmit = computed(() => {
  return formData.value.simulationRequirement.trim() !== '' && files.value.length > 0
})

// Acionar sele\u00e7\u00e3o de arquivo
const triggerFileInput = () => {
  if (!loading.value) {
    fileInput.value?.click()
  }
}

// Processar sele\u00e7\u00e3o de arquivo
const handleFileSelect = (event) => {
  const selectedFiles = Array.from(event.target.files)
  addFiles(selectedFiles)
}

// Processar arrastar e soltar
const handleDragOver = (e) => {
  if (!loading.value) {
    isDragOver.value = true
  }
}

const handleDragLeave = (e) => {
  isDragOver.value = false
}

const handleDrop = (e) => {
  isDragOver.value = false
  if (loading.value) return
  
  const droppedFiles = Array.from(e.dataTransfer.files)
  addFiles(droppedFiles)
}

// Adicionar arquivos
const addFiles = (newFiles) => {
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt'].includes(ext)
  })
  files.value.push(...validFiles)
}

// Remover arquivo
const removeFile = (index) => {
  files.value.splice(index, 1)
}

// Rolar para o final
const scrollToBottom = () => {
  window.scrollTo({
    top: document.body.scrollHeight,
    behavior: 'smooth'
  })
}

// Iniciar simula\u00e7\u00e3o - redireciona imediatamente, chamada API na p\u00e1gina Process
const startSimulation = () => {
  if (!canSubmit.value || loading.value) return
  
  // Armazenar dados pendentes de upload
  import('../store/pendingUpload.js').then(({ setPendingUpload }) => {
    setPendingUpload(files.value, formData.value.simulationRequirement)
    
    // Redirecionar imediatamente para a p\u00e1gina Process (usando identificador especial para novo projeto)
    router.push({
      name: 'Process',
      params: { projectId: 'new' }
    })
  })
}
</script>

<style scoped>
/* Variáveis globais e reset */
:root {
  --black: #000000;
  --white: #FFFFFF;
  --orange: #FF4500;
  --gray-light: #F5F5F5;
  --gray-text: #666666;
  --border: #E5E5E5;
  /* 
    Usar Space Grotesk como fonte principal de títulos, JetBrains Mono como fonte de código/rótulos
    Certifique-se de importar essas Google Fonts no index.html 
  */
  --font-mono: 'JetBrains Mono', monospace;
  --font-sans: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  --font-cn: 'Noto Sans SC', system-ui, sans-serif;
}

.home-container {
  min-height: 100vh;
  background: var(--white);
  font-family: var(--font-sans);
  color: var(--black);
}

/* Navegação superior */
.navbar {
  height: 60px;
  background: var(--black);
  color: var(--white);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
}

.nav-brand {
  font-family: var(--font-mono);
  font-weight: 800;
  letter-spacing: 1px;
  font-size: 1.2rem;
}

.nav-links {
  display: flex;
  align-items: center;
}

.github-link {
  color: var(--white);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: opacity 0.2s;
}

.github-link:hover {
  opacity: 0.8;
}

.arrow {
  font-family: sans-serif;
}

/* Área de conteúdo principal */
.main-content {
  max-width: 1400px;
  margin: 0 auto;
  padding: 60px 40px;
}

/* Área Hero */
.hero-section {
  display: flex;
  justify-content: space-between;
  margin-bottom: 80px;
  position: relative;
}

.hero-left {
  flex: 1;
  padding-right: 60px;
}

.tag-row {
  display: flex;
  align-items: center;
  gap: 15px;
  margin-bottom: 25px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

.orange-tag {
  background: var(--orange);
  color: var(--white);
  padding: 4px 10px;
  font-weight: 700;
  letter-spacing: 1px;
  font-size: 0.75rem;
}

.version-text {
  color: #999;
  font-weight: 500;
  letter-spacing: 0.5px;
}

.main-title {
  font-size: 4.5rem;
  line-height: 1.2;
  font-weight: 500;
  margin: 0 0 40px 0;
  letter-spacing: -2px;
  color: var(--black);
}

.gradient-text {
  background: linear-gradient(90deg, #000000 0%, #444444 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-block;
}

.hero-desc {
  font-size: 1.05rem;
  line-height: 1.8;
  color: var(--gray-text);
  max-width: 640px;
  margin-bottom: 50px;
  font-weight: 400;
  text-align: justify;
}

.hero-desc p {
  margin-bottom: 1.5rem;
}

.highlight-bold {
  color: var(--black);
  font-weight: 700;
}

.highlight-orange {
  color: var(--orange);
  font-weight: 700;
  font-family: var(--font-mono);
}

.highlight-code {
  background: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 0.9em;
  color: var(--black);
  font-weight: 600;
}

.slogan-text {
  font-size: 1.2rem;
  font-weight: 520;
  color: var(--black);
  letter-spacing: 1px;
  border-left: 3px solid var(--orange);
  padding-left: 15px;
  margin-top: 20px;
}

.blinking-cursor {
  color: var(--orange);
  animation: blink 1s step-end infinite;
  font-weight: 700;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.decoration-square {
  width: 16px;
  height: 16px;
  background: var(--orange);
}

.hero-right {
  flex: 0.8;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
}

.logo-container {
  width: 100%;
  display: flex;
  justify-content: flex-end;
  padding-right: 40px;
}

.hero-logo {
  max-width: 500px; /* Ajustar tamanho do logo */
  width: 100%;
}

.scroll-down-btn {
  width: 40px;
  height: 40px;
  border: 1px solid var(--border);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--orange);
  font-size: 1.2rem;
  transition: all 0.2s;
}

.scroll-down-btn:hover {
  border-color: var(--orange);
}

/* Layout de duas colunas Dashboard */
.dashboard-section {
  display: flex;
  gap: 60px;
  border-top: 1px solid var(--border);
  padding-top: 60px;
  align-items: flex-start;
}

.dashboard-section .left-panel,
.dashboard-section .right-panel {
  display: flex;
  flex-direction: column;
}

/* Painel esquerdo */
.left-panel {
  flex: 0.8;
}

.panel-header {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
}

.status-dot {
  color: var(--orange);
  font-size: 0.8rem;
}

.section-title {
  font-size: 2rem;
  font-weight: 520;
  margin: 0 0 15px 0;
}

.section-desc {
  color: var(--gray-text);
  margin-bottom: 25px;
  line-height: 1.6;
}

.metrics-row {
  display: flex;
  gap: 20px;
  margin-bottom: 15px;
}

.metric-card {
  border: 1px solid var(--border);
  padding: 20px 30px;
  min-width: 150px;
}

.metric-value {
  font-family: var(--font-mono);
  font-size: 1.8rem;
  font-weight: 520;
  margin-bottom: 5px;
}

.metric-label {
  font-size: 0.85rem;
  color: #999;
}

/* Introdução das etapas de simulação */
.steps-container {
  border: 1px solid var(--border);
  padding: 30px;
  position: relative;
}

.steps-header {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  color: #999;
  margin-bottom: 25px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.diamond-icon {
  font-size: 1.2rem;
  line-height: 1;
}

.workflow-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.workflow-item {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.step-num {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--black);
  opacity: 0.3;
}

.step-info {
  flex: 1;
}

.step-title {
  font-weight: 520;
  font-size: 1rem;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 0.85rem;
  color: var(--gray-text);
}

/* Console interativo direito */
.right-panel {
  flex: 1.2;
}

.console-box {
  border: 1px solid #CCC; /* Borda sólida externa */
  padding: 8px; /* Padding para efeito de borda dupla */
}

.console-section {
  padding: 20px;
}

.console-section.btn-section {
  padding-top: 0;
}

.console-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #666;
}

.upload-zone {
  border: 1px dashed #CCC;
  height: 200px;
  overflow-y: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s;
  background: #FAFAFA;
}

.upload-zone.has-files {
  align-items: flex-start;
}

.upload-zone:hover {
  background: #F0F0F0;
  border-color: #999;
}

.upload-placeholder {
  text-align: center;
}

.upload-icon {
  width: 40px;
  height: 40px;
  border: 1px solid #DDD;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 15px;
  color: #999;
}

.upload-title {
  font-weight: 500;
  font-size: 0.9rem;
  margin-bottom: 5px;
}

.upload-hint {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: #999;
}

.file-list {
  width: 100%;
  padding: 15px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-item {
  display: flex;
  align-items: center;
  background: var(--white);
  padding: 8px 12px;
  border: 1px solid #EEE;
  font-family: var(--font-mono);
  font-size: 0.85rem;
}

.file-name {
  flex: 1;
  margin: 0 10px;
}

.remove-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.2rem;
  color: #999;
}

.console-divider {
  display: flex;
  align-items: center;
  margin: 10px 0;
}

.console-divider::before,
.console-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #EEE;
}

.console-divider span {
  padding: 0 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #BBB;
  letter-spacing: 1px;
}

.input-wrapper {
  position: relative;
  border: 1px solid #DDD;
  background: #FAFAFA;
}

.code-input {
  width: 100%;
  border: none;
  background: transparent;
  padding: 20px;
  font-family: var(--font-mono);
  font-size: 0.9rem;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  min-height: 150px;
}

.model-badge {
  position: absolute;
  bottom: 10px;
  right: 15px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
  color: #AAA;
}

.start-engine-btn {
  width: 100%;
  background: var(--black);
  color: var(--white);
  border: none;
  padding: 20px;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 1.1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  transition: all 0.3s ease;
  letter-spacing: 1px;
  position: relative;
  overflow: hidden;
}

/* Estado clicável (não desabilitado) */
.start-engine-btn:not(:disabled) {
  background: var(--black);
  border: 1px solid var(--black);
  animation: pulse-border 2s infinite;
}

.start-engine-btn:hover:not(:disabled) {
  background: var(--orange);
  border-color: var(--orange);
  transform: translateY(-2px);
}

.start-engine-btn:active:not(:disabled) {
  transform: translateY(0);
}

.start-engine-btn:disabled {
  background: #E5E5E5;
  color: #999;
  cursor: not-allowed;
  transform: none;
  border: 1px solid #E5E5E5;
}

/* Animação guia: pulso sutil na borda */
@keyframes pulse-border {
  0% { box-shadow: 0 0 0 0 rgba(0, 0, 0, 0.2); }
  70% { box-shadow: 0 0 0 6px rgba(0, 0, 0, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 0, 0, 0); }
}

/* Adaptação responsiva */
@media (max-width: 1024px) {
  .dashboard-section {
    flex-direction: column;
  }
  
  .hero-section {
    flex-direction: column;
  }
  
  .hero-left {
    padding-right: 0;
    margin-bottom: 40px;
  }
  
  .hero-logo {
    max-width: 200px;
    margin-bottom: 20px;
  }
}
</style>
