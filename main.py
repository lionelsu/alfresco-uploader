import sys
import os
import requests
import json
from datetime import datetime, timedelta
import traceback
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.layout import Layout
from rich.live import Live
from rich.text import Text

# --- Base do projeto ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

ALFRESCO_URL = config.get("ALFRESCO_URL")
USERNAME = config.get("USERNAME")
PASSWORD = config.get("PASSWORD")
SITE = config.get("SITE")
LOCAL_DIR = config.get("LOCAL_DIR")

if not os.path.isdir(LOCAL_DIR):
    print(f"❌ Caminho inválido: {LOCAL_DIR}")
    input("Pressione ENTER para sair...")
    exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOGS_DIR, f"upload_log_{timestamp}.txt")

session = requests.Session()
session.auth = (USERNAME, PASSWORD)


class UploadManager:
    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self.layout.split(
            Layout(name="main", ratio=4),
            Layout(name="footer", size=3)
        )

        self.progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("[progress.completed]{task.completed}/{task.total} arquivos"),
            TextColumn("•"),
            TextColumn("{task.fields[processed_size]}"),
            TextColumn("•"),
            TimeRemainingColumn()
        )

        self.log_content = []
        self.stats = {
            'total_files': 0,
            'uploaded_files': 0,
            'skipped_files': 0,
            'created_folders': 0,
            'skipped_folders': 0,
            'total_size_bytes': 0,
            'uploaded_size_bytes': 0,
            'skipped_size_bytes': 0
        }
        self.task_id = None
        self.start_time = None
        self.live = None
        self.current_depth = 0

    def format_size(self, bytes_size):
        """Formata bytes para formato legível (KB, MB, GB)"""
        if bytes_size == 0:
            return "0B"

        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while bytes_size >= 1024 and i < len(size_names) - 1:
            bytes_size /= 1024.0
            i += 1

        return f"{bytes_size:.2f} {size_names[i]}"

    def log(self, msg, depth=0):
        """Adiciona mensagem ao log e ao arquivo"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Adiciona indentação baseada na profundidade
        indent = "  " * depth
        log_msg = f"[{timestamp}] {indent}{msg}"

        self.log_content.append(log_msg)

        # Mantém apenas as últimas 100 linhas no log para display
        if len(self.log_content) > 100:
            self.log_content = self.log_content[-100:]

        # Escreve no arquivo de log
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_msg + "\n")

        # Atualiza o layout se estiver em execução
        if self.live:
            self.live.update(self.render_layout())

    def update_progress(self):
        """Atualiza a barra de progresso"""
        if self.task_id is not None:
            processed_files = self.stats['uploaded_files'] + self.stats['skipped_files']
            processed_size = self.stats['uploaded_size_bytes'] + self.stats['skipped_size_bytes']
            total_size = self.stats['total_size_bytes']

            self.progress.update(
                self.task_id,
                completed=processed_files,
                processed_size=f"{self.format_size(processed_size)}/{self.format_size(total_size)}"
            )

    def render_layout(self):
        """Renderiza o layout com as duas janelas"""
        # Janela principal com logs
        if self.log_content:
            # Pega as últimas 40 linhas para display
            display_logs = self.log_content[-40:]
            log_text = "\n".join(display_logs)
        else:
            log_text = "Aguardando início do upload..."

        main_panel = Panel(
            log_text,
            title="Logs de Upload",
            border_style="blue",
            padding=(0, 1)
        )

        # Footer com progresso
        footer_panel = Panel(
            self.progress,
            title="Progresso",
            border_style="green"
        )

        # Atualiza os layouts
        self.layout["main"].update(main_panel)
        self.layout["footer"].update(footer_panel)

        return self.layout

    def get_document_library_node(self):
        url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/sites/{SITE}/containers/documentLibrary"
        resp = session.get(url)
        resp.raise_for_status()
        return resp.json()["entry"]["id"]

    def ensure_folder(self, parent_id, folder_name, depth=0):
        # Primeiro, verifica se a pasta já existe
        url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children?where=(isFolder=true)"
        resp = session.get(url)
        resp.raise_for_status()

        for entry in resp.json()["list"]["entries"]:
            if entry["entry"]["name"] == folder_name:
                self.log(f"📁 Pasta já existe: {folder_name}", depth)
                self.stats['skipped_folders'] += 1
                return entry["entry"]["id"]

        # Se não existe, tenta criar
        url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children"
        data = {"name": folder_name, "nodeType": "cm:folder"}
        try:
            resp = session.post(url, json=data)
            resp.raise_for_status()
            folder_id = resp.json()["entry"]["id"]
            self.log(f"📁 Criada pasta: {folder_name}", depth)
            self.stats['created_folders'] += 1
            return folder_id
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:
                # Se a pasta já existe (409), fazer uma nova busca
                self.log(f"ℹ Pasta já existe (409): {folder_name}", depth)
                self.stats['skipped_folders'] += 1

                # Buscar a pasta novamente (forma simples que funciona)
                url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children?where=(isFolder=true)"
                resp = session.get(url)
                resp.raise_for_status()

                for entry in resp.json()["list"]["entries"]:
                    if entry["entry"]["name"] == folder_name and entry["entry"]["isFolder"]:
                        return entry["entry"]["id"]

                # Se não encontrar mesmo após busca, levantar erro
                raise Exception(f"Pasta '{folder_name}' não encontrada após erro 409")
            else:
                raise

    def file_exists(self, parent_id, file_name):
        # Forma simples sem parâmetros complexos
        url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children?where=(isFile=true)"
        resp = session.get(url)
        resp.raise_for_status()
        for entry in resp.json()["list"]["entries"]:
            if entry["entry"]["name"] == file_name:
                return True
        return False

    def upload_file(self, parent_id, file_path, depth=0):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)

        if self.file_exists(parent_id, file_name):
            self.log(f"ℹ Arquivo já existe, pulando: {file_name} ({self.format_size(file_size)})", depth)
            self.stats['skipped_files'] += 1
            self.stats['skipped_size_bytes'] += file_size
            self.update_progress()
            return

        url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children"
        try:
            with open(file_path, "rb") as f:
                files = {
                    "filedata": (file_name, f),
                    "name": (None, file_name)
                }
                resp = session.post(url, files=files)
                resp.raise_for_status()
            self.log(f"📄 Enviado: {file_name} ({self.format_size(file_size)})", depth)
            self.stats['uploaded_files'] += 1
            self.stats['uploaded_size_bytes'] += file_size
            self.update_progress()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 409:
                self.log(f"ℹ Arquivo já existe (409), pulando: {file_name} ({self.format_size(file_size)})", depth)
                self.stats['skipped_files'] += 1
                self.stats['skipped_size_bytes'] += file_size
                self.update_progress()
            else:
                raise

    def calculate_total_files_and_size(self, local_dir):
        """Calcula o total de arquivos e tamanho total"""
        total_files = 0
        total_size = 0

        for root, dirs, files in os.walk(local_dir):
            total_files += len(files)
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    total_size += os.path.getsize(file_path)
                except OSError:
                    # Se não conseguir obter o tamanho, ignora
                    pass

        return total_files, total_size

    def upload_directory(self, local_dir, parent_id):
        """Processa o upload recursivamente"""
        total_files, total_size = self.calculate_total_files_and_size(local_dir)
        self.stats['total_files'] = total_files
        self.stats['total_size_bytes'] = total_size

        # Inicia a barra de progresso
        self.task_id = self.progress.add_task(
            "[green]Uploading...",
            total=total_files,
            processed_size=f"0B/{self.format_size(total_size)}"
        )

        self.start_time = datetime.now()
        self.log(f"📊 Iniciando upload: {total_files} arquivos, {self.format_size(total_size)}")

        # Processa recursivamente
        for root, dirs, files in os.walk(local_dir):
            relative_path = os.path.relpath(root, local_dir)
            current_parent = parent_id
            depth = 0

            if relative_path != ".":
                parts = relative_path.split(os.sep)
                depth = len(parts)  # Profundidade baseada no número de pastas

                for part in parts:
                    current_parent = self.ensure_folder(current_parent, part, depth)
                    depth += 1  # Aumenta a profundidade para arquivos dentro desta pasta

            # Processa arquivos com profundidade +1
            for file in files:
                self.upload_file(current_parent, os.path.join(root, file), depth + 1)

    def show_final_report(self):
        """Exibe relatório final"""
        processed_files = self.stats['uploaded_files'] + self.stats['skipped_files']
        processed_size = self.stats['uploaded_size_bytes'] + self.stats['skipped_size_bytes']
        success_rate = (self.stats['uploaded_files'] / processed_files * 100) if processed_files > 0 else 0

        if self.start_time:
            end_time = datetime.now()
            duration = end_time - self.start_time
            duration_str = str(duration).split('.')[0]  # Remove microsegundos
        else:
            duration_str = "N/A"

        report = f"""
📊 RELATÓRIO FINAL:

• 📂 Total de arquivos encontrados: {self.stats['total_files']}
• 📄 Arquivos processados: {processed_files}
• ✅ Arquivos enviados: {self.stats['uploaded_files']} ({self.format_size(self.stats['uploaded_size_bytes'])})
• ⏭️ Arquivos pulados (já existiam): {self.stats['skipped_files']} ({self.format_size(self.stats['skipped_size_bytes'])})
• 📁 Pastas criadas: {self.stats['created_folders']}
• ⏭️ Pastas puladas (já existiam): {self.stats['skipped_folders']}
• 💾 Tamanho total: {self.format_size(self.stats['total_size_bytes'])}
• 💾 Tamanho processado: {self.format_size(processed_size)}
• 💾 Tamanho enviado: {self.format_size(self.stats['uploaded_size_bytes'])}
• 💾 Tamanho pulado: {self.format_size(self.stats['skipped_size_bytes'])}
• 📈 Taxa de sucesso: {success_rate:.1f}%
• ⏱️  Tempo total: {duration_str}

Log salvo em: {LOG_FILE}
        """

        self.console.print(Panel(report, title="Relatório de Execução", border_style="yellow"))

    def run(self):
        """Executa o processo completo"""
        try:
            # Primeiro, inicializa o layout
            initial_layout = self.render_layout()

            with Live(initial_layout, refresh_per_second=4, screen=True) as live:
                self.live = live  # Guarda referência para atualizações

                doclib_id = self.get_document_library_node()
                self.log(f"📂 Conectado ao Alfresco. Iniciando upload da pasta: {LOCAL_DIR}")
                self.upload_directory(LOCAL_DIR, doclib_id)
                self.log("✅ Upload completo!")

                # Atualiza o layout final
                live.update(self.render_layout())

        except Exception as e:
            err_msg = f"❌ Exceção não tratada: {e}\n{traceback.format_exc()}"
            self.log(err_msg)
            self.console.print(Panel(err_msg, title="Erro", border_style="red"))
        finally:
            self.live = None  # Limpa referência
            self.show_final_report()
            input("\nPressione ENTER para fechar...")


if __name__ == "__main__":
    manager = UploadManager()
    manager.run()