// Eskuta — entry point do core Tauri (Rust).
//
// Responsabilidades:
//   - Inicializa plugins (opener, shell, updater)
//   - Spawna o sidecar Python (FastAPI) no startup do app, via std::process::Command
//   - Captura stdout/stderr do sidecar via thread + escreve nos logs do app
//   - Encerra o sidecar quando o app fecha (kill())
//
// O sidecar é empacotado pelo PyInstaller em modo --onedir e copiado pra
// `binaries/eskuta-sidecar/` na raiz do Tauri project. Em release, vai pra
// `<install>/resources/sidecar/eskuta-sidecar.exe` (via bundle.resources do
// tauri.conf.json).

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;

use tauri::{Manager, RunEvent};

const SIDECAR_PORT: &str = "8765";
const SIDECAR_HOST: &str = "127.0.0.1";

/// Handle do processo do sidecar, guardado no State global do Tauri pra
/// poder ser killado no encerramento.
struct SidecarHandle(Mutex<Option<Child>>);

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// Resolve o caminho do eskuta-sidecar.exe.
///
/// Em **release**, busca em `resource_dir/sidecar/eskuta-sidecar.exe`
/// (configurado em tauri.conf.json `bundle.resources`).
///
/// Em **debug** (npm run tauri dev), busca em `binaries/eskuta-sidecar/`
/// relativo ao cwd, ao exe atual, ou ao parent de cada.
fn resolve_sidecar_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    #[cfg(not(debug_assertions))]
    {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|e| format!("resource_dir falhou: {e}"))?;
        // Com bundle.resources do tauri.conf.json apontando pra
        // "binaries/eskuta-sidecar/**", a hierarquia é preservada dentro
        // do resource_dir do app instalado.
        let candidates = [
            resource_dir.join("binaries/eskuta-sidecar/eskuta-sidecar.exe"),
            resource_dir.join("sidecar/eskuta-sidecar.exe"),
            resource_dir.join("eskuta-sidecar/eskuta-sidecar.exe"),
        ];
        for c in candidates.iter() {
            if c.exists() {
                return Ok(c.clone());
            }
        }
        return Err(format!(
            "Sidecar não encontrado. Tentativas: {candidates:?}"
        ));
    }

    #[cfg(debug_assertions)]
    {
        let _ = app;
        let rel = "binaries/eskuta-sidecar/eskuta-sidecar.exe";
        let candidates = vec![
            PathBuf::from(rel),
            PathBuf::from("../").join(rel),
            std::env::current_exe()
                .ok()
                .and_then(|p| p.parent().map(|p| p.to_path_buf()))
                .unwrap_or_default()
                .join(rel),
        ];
        for c in candidates.iter() {
            if c.exists() {
                return Ok(c.clone());
            }
        }
        Err(format!(
            "Sidecar não encontrado em dev. Tentativas: {candidates:?}"
        ))
    }
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<Child, String> {
    let sidecar_path = resolve_sidecar_path(app)?;
    println!("[eskuta] spawning sidecar: {}", sidecar_path.display());

    let mut cmd = Command::new(&sidecar_path);
    cmd.args(["--host", SIDECAR_HOST, "--port", SIDECAR_PORT])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // No Windows: força CREATE_NO_WINDOW (0x08000000) pra garantir que
    // NENHUMA janela de console apareça, mesmo que o exe seja console
    // subsystem por algum motivo. Defesa em profundidade — o sidecar
    // já é built com --windowed no PyInstaller.
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Falha ao spawnar sidecar: {e}"))?;

    // Thread pra ler stdout (logs do sidecar) sem bloquear.
    if let Some(stdout) = child.stdout.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines().map_while(Result::ok) {
                println!("[sidecar] {line}");
            }
        });
    }
    // Thread pra ler stderr — mesma coisa.
    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().map_while(Result::ok) {
                eprintln!("[sidecar] {line}");
            }
        });
    }

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
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                    }
                }
            }
        });
}
