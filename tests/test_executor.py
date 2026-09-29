import pytest
from unittest.mock import patch, MagicMock
import subprocess
from src.executor import run_command, deploy

@patch("src.executor.subprocess.run")
def test_run_command_success(mock_run):
    """Testa che un comando completato con successo (exit code 0) ritorni True."""
    # Mocca un'esecuzione andata a buon fine
    mock_run.return_value = MagicMock(stdout="Success", returncode=0)
    
    result = run_command(["git", "status"], cwd="/fake/path")
    
    assert result is True
    mock_run.assert_called_once_with(
        ["git", "status"],
        cwd="/fake/path",
        check=True,
        capture_output=True,
        text=True
    )

@patch("src.executor.subprocess.run")
def test_run_command_failure(mock_run):
    """Testa che un comando fallito (exit code != 0) ritorni False."""
    # Mocca un fallimento di subprocess (es. comando non trovato o errore)
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["git", "status"], stderr="Errore git"
    )
    
    result = run_command(["git", "status"], cwd="/fake/path")
    
    assert result is False

@patch("src.executor.run_command")
def test_deploy_success(mock_run_command):
    """Testa che il deploy chiami git e docker nell'ordine corretto se tutto va bene."""
    mock_run_command.return_value = True
    
    result = deploy("/fake/path")
    
    assert result is True
    assert mock_run_command.call_count == 3
    
    # Verifica che la costruzione degli array di comandi (sicuri) sia corretta
    mock_run_command.assert_any_call(["git", "pull", "origin", "main"], cwd="/fake/path")
    mock_run_command.assert_any_call(["docker", "compose", "pull"], cwd="/fake/path")
    mock_run_command.assert_any_call(["docker", "compose", "up", "-d"], cwd="/fake/path")

@patch("src.executor.run_command")
def test_deploy_fails_on_git_pull(mock_run_command):
    """Testa che il deploy si interrompa e ritorni False se git pull fallisce."""
    mock_run_command.return_value = False
    
    result = deploy("/fake/path")
    
    assert result is False
    # Docker compose non dovrebbe essere chiamato se git pull fallisce
    mock_run_command.assert_called_once_with(["git", "pull", "origin", "main"], cwd="/fake/path")
