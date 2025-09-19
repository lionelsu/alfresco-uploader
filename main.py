import sys
import os
import requests
import json
from datetime import datetime
import traceback

# --- Base do projeto ---
if getattr(sys, 'frozen', False):
    # Executável PyInstaller
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Rodando como script normal
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

# valida se a pasta existe
if not os.path.isdir(LOCAL_DIR):
    print(f"❌ Caminho inválido: {LOCAL_DIR}")
    input("Pressione ENTER para sair...")
    exit(1)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOGS_DIR, f"upload_log_{timestamp}.txt")

session = requests.Session()
session.auth = (USERNAME, PASSWORD)

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def get_document_library_node():
    url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/sites/{SITE}/containers/documentLibrary"
    resp = session.get(url)
    resp.raise_for_status()
    return resp.json()["entry"]["id"]

def ensure_folder(parent_id, folder_name):
    url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children?where=(isFolder=true)"
    resp = session.get(url)
    resp.raise_for_status()
    for entry in resp.json()["list"]["entries"]:
        if entry["entry"]["name"] == folder_name:
            log(f"📁 Pasta já existe: {folder_name}")
            return entry["entry"]["id"]

    url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children"
    data = {"name": folder_name, "nodeType": "cm:folder"}
    try:
        resp = session.post(url, json=data)
        resp.raise_for_status()
        folder_id = resp.json()["entry"]["id"]
        log(f"📁 Criada pasta: {folder_name}")
        return folder_id
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            # Se a pasta já existe (409), buscar o ID da pasta existente
            log(f"ℹ Pasta já existe (409), buscando ID: {folder_name}")
            url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children?where=(isFolder=true)"
            resp = session.get(url)
            resp.raise_for_status()
            entries = resp.json()["list"]["entries"]

            if entries:
                return entries[0]["entry"]["id"]
            else:
                # Se ainda não encontrar, tentar uma busca alternativa
                url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children"
                resp = session.get(url)
                resp.raise_for_status()

                for entry in resp.json()["list"]["entries"]:
                    if entry["entry"]["name"] == folder_name and entry["entry"]["isFolder"]:
                        return entry["entry"]["id"]

                # Se não encontrar mesmo após busca, levantar erro
                raise Exception(f"Pasta '{folder_name}' não encontrada após erro 409")
        else:
            raise

def file_exists(parent_id, file_name):
    url = f"{ALFRESCO_URL}/api/-default-/public/alfresco/versions/1/nodes/{parent_id}/children?where=(isFile=true)"
    resp = session.get(url)
    resp.raise_for_status()
    for entry in resp.json()["list"]["entries"]:
        if entry["entry"]["name"] == file_name:
            return True
    return False

def upload_file(parent_id, file_path, depth=0):
    file_name = os.path.basename(file_path)
    if file_exists(parent_id, file_name):
        log("  " * depth + f"ℹ Arquivo já existe, pulando: {file_name}")
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
        log("  " * depth + f"📄 Enviado: {file_name}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            log("  " * depth + f"ℹ Arquivo já existe (409), pulando: {file_name}")
        else:
            raise

def upload_directory(local_dir, parent_id, depth=0):
    for root, dirs, files in os.walk(local_dir):
        relative_path = os.path.relpath(root, local_dir)
        current_parent = parent_id

        if relative_path != ".":
            for part in relative_path.split(os.sep):
                current_parent = ensure_folder(current_parent, part)

        for file in files:
            upload_file(current_parent, os.path.join(root, file), depth=relative_path.count(os.sep)+1)

if __name__ == "__main__":
    try:
        doclib_id = get_document_library_node()
        log(f"📂 Iniciando upload da pasta: {LOCAL_DIR}")
        upload_directory(LOCAL_DIR, doclib_id)
        log("✅ Upload completo!")
    except Exception as e:
        err_msg = f"❌ Exceção não tratada: {e}\n{traceback.format_exc()}"
        log(err_msg)
        print(err_msg)
    finally:
        input("\nUpload finalizado. Pressione ENTER para fechar...")
