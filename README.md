# Documentação de Implantação - Alfresco Upload Manager

## Visão Geral

O **Alfresco Upload Manager** é uma aplicação Python desenvolvida para realizar upload automatizado de arquivos e diretórios para o Alfresco ECM. O sistema oferece:

- Upload recursivo de estruturas de diretórios
- Sistema robusto de retry com reconexão automática
- Interface visual em tempo real com progresso detalhado
- Logs completos de todas as operações
- Detecção inteligente de arquivos/pastas já existentes
- Polling automático para operações com timeout

---

## Estrutura de Arquivos

```
projeto/
│
├── config/
│   └── config.json          # Arquivo de configuração
│
├── ico/
│   └── h2l.ico             # Ícone da aplicação
│
├── logs/                    # Diretório de logs (criado automaticamente)
│   └── upload_log_YYYYMMDD_HHMMSS.txt
│
├── release/                 # Diretório para executável compilado
│
└── main.py                  # Script principal
```

---

## Pré-requisitos de Desenvolvimento

### Software Necessário

1. **Python 3.11** ou superior
2. **PyInstaller** (para gerar executável)
3. **Acesso a API Rest Alfresco** configurado

---

## Instalação (Desenvolvimento)

As seções abaixo são apenas para **desenvolvimento** ou **recompilação** do sistema.

### Opção 1: Executar via Python

1. **Instale as dependências**:
```bash
pip install -r requirements.txt
```

2. **Configure o arquivo** (mesmas regras de produção acima) `config/config.json`

Edite o arquivo `release/dist/config/config.json` com as seguintes informações:

```json
{
  "ALFRESCO_URL": "http://<url_ou_ip>:<porta>/alfresco",
  "USERNAME": "admin",
  "PASSWORD": "admin",
  "SITE": "swsdp",
  "LOCAL_DIR": "C:\\Users\\usuario\\Documents\\pasta_upload"
}
```

#### Parâmetros de Configuração

| Parâmetro | Descrição | Exemplo                                |
|-----------|-----------|----------------------------------------|
| `ALFRESCO_URL` | URL base do servidor Alfresco | `http://<url_ou_ip>:<porta>/alfresco`  |
| `USERNAME` | Usuário com permissões de escrita | `admin`                                |
| `PASSWORD` | Senha do usuário | `admin`                                |
| `SITE` | Nome do site no Alfresco | `swsdp`                                |
| `LOCAL_DIR` | Caminho completo do diretório local para upload | `C:\\Users\\usuario\\Documents\\pasta` |

> **Atenção**: Use barras duplas (`\\`) nos caminhos do Windows ou barras simples (`/`)


3. **Execute o script**:
```bash
python main.py
```

### Opção 2: Gerar Executável

1. **Instale o PyInstaller**:
```bash
pip install pyinstaller
```

2. **Gere o executável**:
```bash
pyinstaller --clean --noconfirm --onefile --console --icon="ico/ico.ico" --name H2LAlfrescoUploader --distpath release/dist --workpath release/build --specpath release main.py
```

**Parâmetros do comando**:
- `--clean`: Remove cache de builds anteriores
- `--noconfirm`: Não pede confirmação para sobrescrever
- `--onefile`: Gera um único executável
- `--console`: Mantém janela de console visível
- `--icon`: Define o ícone da aplicação
- `--name`: Nome do executável gerado
- `--distpath`: Pasta de destino do executável
- `--workpath`: Pasta temporária de build
- `--specpath`: Pasta do arquivo .spec

3. **Localize o executável**:
   - Será criado em `release/dist/H2LAlfrescoUploader.exe`

4. **Estrutura após compilação**:
```
release/
├── dist/
│   └── H2LAlfrescoUploader.exe
├── build/                    # Arquivos temporários (pode deletar)
└── H2LAlfrescoUploader.spec  # Especificação do build
```

5. **Prepare para distribuição**:
```
pasta_distribuicao/
├── H2LAlfrescoUploader.exe
├── config/
│   └── config.json
└── logs/                    # Será criado automaticamente
```

> **Dica**: Distribua a pasta completa com o executável e a pasta `config/` configurada

> **Importante**: O arquivo `config.json` deve estar na pasta `config/` relativa ao executável

---

## Execução

### Interface do Sistema

Ao executar o programa, você verá duas janelas principais:

#### 1. **Janela de Logs** (Azul)
Exibe em tempo real:
- Criação de pastas
- Upload de arquivos
- Avisos e erros
- Operações de retry

#### 2. **Janela de Progresso** (Verde)
Mostra:
- Barra de progresso visual
- Arquivos processados / total
- Tamanho processado / total
- Tempo estimado restante

### Exemplo de Saída

```
[10:30:15]   📂 Conectado ao Alfresco. Iniciando upload da pasta: C:\Users\...
[10:30:16]   📁 Criada pasta: Documentos
[10:30:17]     📁 Criada pasta: Contratos
[10:30:18]       📄 Enviado: contrato_2024.pdf (2.45 MB)
[10:30:20]       ℹ️ Arquivo já existe, pulando: backup.zip (156.78 MB)
[10:30:21]   ✅ Upload completo!
```

---

## Sistema de Logs

### Localização dos Logs

Os logs são salvos automaticamente em:
```
logs/upload_log_YYYYMMDD_HHMMSS.txt
```

Exemplo: `logs/upload_log_20241008_103015.txt`

### Conteúdo dos Logs

Cada entrada contém:
- **Timestamp**: Hora da operação
- **Indentação**: Nível de profundidade na estrutura de pastas
- **Ícone**: Tipo de operação (📂 📁 📄 ⚠️ ✅)
- **Mensagem**: Detalhes da operação

---

## Sistema de Retry e Recuperação

### Estratégia de Polling

O sistema implementa um mecanismo robusto de retry:

- **Timeout total por tentativa**: 1600 segundos (26 minutos)
- **Intervalo de polling**: 5 segundos
- **Número máximo de tentativas**: 9
- **Reconexão automática**: Nova sessão HTTP a cada tentativa

### Operações com Retry

1. **Conexão inicial** ao Alfresco
2. **Criação de pastas**
3. **Verificação de arquivos existentes**
4. **Upload de arquivos**

### Tratamento de Erros

| Erro | Comportamento |
|------|---------------|
| HTTP 409 (Conflito) | Considera item já existente e continua |
| Erro de rede | Retry automático com polling |
| Timeout | Nova tentativa completa |
| Arquivo inacessível | Pula arquivo e continua |

---

## Relatório Final

Ao concluir, o sistema exibe um relatório completo:

```
📊 RELATÓRIO FINAL:

• 📂 Total de arquivos encontrados: 150
• 📄 Arquivos processados: 150
• ✅ Arquivos enviados: 120 (1.25 GB)
• ⭐ Arquivos pulados (já existiam): 30 (450.50 MB)
• 📁 Pastas criadas: 25
• ⭐ Pastas puladas (já existiam): 5
• 💾 Tamanho total: 1.70 GB
• 💾 Tamanho processado: 1.70 GB
• 💾 Tamanho enviado: 1.25 GB
• 💾 Tamanho pulado: 450.50 MB
• 📈 Taxa de sucesso: 80.0%
• ⏱️ Tempo total: 0:45:23

Log salvo em: logs/upload_log_20241008_103015.txt
```

---
