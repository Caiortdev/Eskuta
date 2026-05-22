// Eskuta — entry point do core Tauri (Rust).
//
// Responsabilidades:
//   - Inicializa plugins (opener, shell)
//   - Spawna o sidecar Python (FastAPI) no startup do app
//   - Captura stdout/stderr do sidecar e loga
//   - Encerra o sidecar quando o app fecha
//
// O sidecar é distribuído como `binaries/eskuta-sidecar` (sem extensão no
// tauri.conf.json) e empacotado pelo Tauri para o target triple atual.

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

use std::sync::Mutex;

const SIDECAR_PORT: &str = "8765";
const SIDECAR_HOST: &str = "127.0.0.1";

/// Handle do processo do sidecar, guardado no State global do Tauri pra
/// poder ser killado no encerramento.
struct SidecarHandle(Mutex<Option<CommandChild>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<CommandChild, String> {
    let sidecar_command = app
        .shell()
        .sidecar("eskuta-sidecar")
        .map_err(|e| format!("Falha ao localizar binário do sidecar: {e}"))?
        .args(["--host", SIDECAR_HOST, "--port", SIDECAR_PORT]);

    let (mut rx, child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Falha ao iniciar sidecar: {e}"))?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[sidecar] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[sidecar] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[sidecar] processo terminou: {:?}", payload);
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(SidecarHandle(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            match spawn_sidecar(&handle) {
                Ok(child) => {
                    let state = app.state::<SidecarHandle>();
                    let mut guard = state
                        .0
                        .lock()
                        .expect("lock do SidecarHandle envenenado no setup");
                    *guard = Some(child);
                }
                Err(err) => {
                    eprintln!("[eskuta] não foi possível iniciar o sidecar: {err}");
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .build(tauri::generate_context!())
        .expect("erro ao construir a aplicação Tauri")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<SidecarHandle>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
