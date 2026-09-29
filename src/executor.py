import subprocess
import logging

# Configurazione base del logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_command(command: list[str], cwd: str) -> bool:
    """
    Esegue un comando shell in modo sicuro passando una lista di argomenti,
    prevenendo la command injection.
    """
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True
        )
        output = result.stdout.strip() if result.stdout else ""
        logging.info(f"Comando completato con successo: {' '.join(command)}\nOutput: {output}")
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.strip() if e.stderr else str(e)
        logging.error(f"Errore nell'esecuzione del comando: {' '.join(command)}\nErrore: {err}")
        return False
    except FileNotFoundError as e:
        logging.error(f"Eseguibile non trovato: {' '.join(command)}\nErrore: {str(e)}")
        return False
    except OSError as e:
        logging.error(f"Errore di sistema operativo per il comando {' '.join(command)}: {str(e)}")
        return False

def deploy(repo_path: str) -> bool:
    """
    Esegue i passi necessari per aggiornare il repository ed avviare i container.
    Se uno dei comandi fallisce, il deploy viene interrotto.
    """
    if not repo_path or not isinstance(repo_path, str):
        logging.error(f"Percorso del repository non valido: {repo_path}")
        return False

    logging.info(f"Iniziando il deploy nella directory: {repo_path}")
    
    try:
        # 1. Scarica gli aggiornamenti dal repository git
        if not run_command(["git", "pull", "origin", "main"], cwd=repo_path):
            logging.error("Deploy fallito al passaggio: git pull")
            return False
            
        # 2. Scarica le nuove immagini dei container
        if not run_command(["docker", "compose", "pull"], cwd=repo_path):
            logging.error("Deploy fallito al passaggio: docker compose pull")
            return False

        # 3. Riavvia o ricrea i container in background
        if not run_command(["docker", "compose", "up", "-d"], cwd=repo_path):
            logging.error("Deploy fallito al passaggio: docker compose up -d")
            return False
            
        logging.info("Deploy completato con successo!")
        return True
    except Exception as e:
        logging.error(f"Errore imprevisto durante la procedura di deploy: {e}")
        return False
