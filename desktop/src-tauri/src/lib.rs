use serde_json::{json, Value};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent};

const KEYRING_SERVICE: &str = "com.berkshire.nexus";
const BINANCE_KEYRING_ACCOUNT: &str = "binance-api-key";
const AI_KEYRING_ACCOUNT: &str = "ai-provider-api-key";

#[derive(Default)]
struct AgentProcess(Mutex<Option<Child>>);

#[derive(serde::Deserialize)]
struct AgentStartOptions {
    interval_minutes: f64,
    initial_cash: f64,
    auto_promote_paper: bool,
    risk_config: Value,
    research_config: Value,
}

struct PythonContext {
    executable: String,
    root: PathBuf,
}

fn state_directory(app: &AppHandle) -> Result<PathBuf, String> {
    let path = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Could not resolve application data directory: {error}"))?
        .join("state");
    fs::create_dir_all(&path)
        .map_err(|error| format!("Could not create application state directory: {error}"))?;
    Ok(path)
}

fn python_context(app: &AppHandle) -> Result<PythonContext, String> {
    let executable = env::var("BERKSHIRE_NEXUS_PYTHON").unwrap_or_else(|_| "python3".to_string());
    if let Ok(project_root) = env::var("BERKSHIRE_NEXUS_PROJECT_ROOT") {
        let root = PathBuf::from(project_root);
        if root.join("src").is_dir() {
            return Ok(PythonContext { executable, root });
        }
    }

    let manifest_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    if let Some(repo_root) = manifest_root.parent().and_then(|desktop| desktop.parent()) {
        if repo_root.join("src").is_dir() {
            return Ok(PythonContext {
                executable,
                root: repo_root.to_path_buf(),
            });
        }
    }

    let resource_root = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Could not resolve bundled resources: {error}"))?
        .join("python");
    if resource_root.join("src").is_dir() {
        return Ok(PythonContext {
            executable,
            root: resource_root,
        });
    }
    Err("The bundled BerkshireNexus Python engine could not be found".to_string())
}

fn command_base(app: &AppHandle) -> Result<(Command, PathBuf), String> {
    let context = python_context(app)?;
    let state_dir = state_directory(app)?;
    let mut command = Command::new(&context.executable);
    command
        .current_dir(&context.root)
        .env("PYTHONPATH", &context.root)
        .arg("-m")
        .arg("src.desktop.cli")
        .arg("--state-dir")
        .arg(&state_dir);
    Ok((command, state_dir))
}

fn run_json_command(
    app: &AppHandle,
    arguments: &[String],
    binance_api_key: Option<&str>,
    ai_api_key: Option<&str>,
) -> Result<Value, String> {
    let (mut command, _) = command_base(app)?;
    command.args(arguments);
    if let Some(value) = binance_api_key {
        command.env("BINANCE_API_KEY", value);
    }
    if let Some(value) = ai_api_key {
        command.env("BERKSHIRE_NEXUS_AI_API_KEY", value);
    }
    let output = command
        .output()
        .map_err(|error| format!("Could not start the Python engine: {error}"))?;
    if !output.status.success() {
        let message = String::from_utf8_lossy(&output.stderr);
        let sanitized = message.trim().replace('\n', " ");
        return Err(if sanitized.is_empty() {
            "The Python engine returned an error without details".to_string()
        } else {
            sanitized
        });
    }
    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("The Python engine returned invalid JSON: {error}"))
}

#[tauri::command]
fn app_snapshot(app: AppHandle) -> Result<Value, String> {
    run_json_command(&app, &["snapshot".to_string()], None, None)
}

#[tauri::command]
fn analyze_tickers(
    app: AppHandle,
    tickers: Vec<String>,
    research_config: Value,
) -> Result<Value, String> {
    let mut arguments = vec!["analyze".to_string()];
    arguments.extend(tickers);
    arguments.push("--research-config-json".to_string());
    arguments.push(serde_json::to_string(&research_config).map_err(|error| error.to_string())?);
    let ai_key = ai_key_for_config(&research_config, false)?;
    run_json_command(&app, &arguments, None, ai_key.as_deref())
}

#[tauri::command]
fn run_paper_cycle(
    app: AppHandle,
    tickers: Vec<String>,
    initial_cash: f64,
    auto_promote_paper: bool,
    risk_config: Value,
    research_config: Value,
) -> Result<Value, String> {
    let mut arguments = vec!["cycle".to_string()];
    arguments.extend(tickers);
    arguments.push("--cash".to_string());
    arguments.push(initial_cash.to_string());
    if auto_promote_paper {
        arguments.push("--auto-promote-paper".to_string());
    }
    arguments.push("--risk-config-json".to_string());
    arguments.push(serde_json::to_string(&risk_config).map_err(|error| error.to_string())?);
    arguments.push("--research-config-json".to_string());
    arguments.push(serde_json::to_string(&research_config).map_err(|error| error.to_string())?);
    let ai_key = ai_key_for_config(&research_config, false)?;
    run_json_command(&app, &arguments, None, ai_key.as_deref())
}

#[tauri::command]
fn load_desktop_settings(app: AppHandle) -> Result<Value, String> {
    let path = state_directory(&app)?.join("desktop_settings.json");
    if !path.exists() {
        return Ok(json!({}));
    }
    let bytes =
        fs::read(path).map_err(|error| format!("Could not read desktop settings: {error}"))?;
    serde_json::from_slice(&bytes).map_err(|error| format!("Desktop settings are invalid: {error}"))
}

#[tauri::command]
fn save_desktop_settings(app: AppHandle, settings: Value) -> Result<Value, String> {
    if !settings.is_object() {
        return Err("Desktop settings must be a JSON object".to_string());
    }
    let directory = state_directory(&app)?;
    let path = directory.join("desktop_settings.json");
    let temporary = directory.join("desktop_settings.json.tmp");
    fs::write(
        &temporary,
        serde_json::to_vec_pretty(&settings).map_err(|error| error.to_string())?,
    )
    .map_err(|error| format!("Could not write desktop settings: {error}"))?;
    fs::rename(&temporary, &path)
        .map_err(|error| format!("Could not replace desktop settings: {error}"))?;
    Ok(settings)
}

#[tauri::command]
fn promote_model(app: AppHandle) -> Result<Value, String> {
    run_json_command(&app, &["model-promote".to_string()], None, None)
}

fn keyring_entry(account: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, account)
        .map_err(|error| format!("Could not access the operating system credential store: {error}"))
}

fn optional_key(account: &str) -> Result<Option<String>, String> {
    match keyring_entry(account)?.get_password() {
        Ok(value) if !value.trim().is_empty() => Ok(Some(value)),
        Ok(_) | Err(keyring::Error::NoEntry) => Ok(None),
        Err(error) => Err(format!("Could not read credential status: {error}")),
    }
}

fn ai_key_for_config(config: &Value, force_enabled: bool) -> Result<Option<String>, String> {
    let enabled = force_enabled
        || config
            .get("ai_enabled")
            .and_then(Value::as_bool)
            .unwrap_or(false);
    let provider = config
        .get("ai_provider")
        .and_then(Value::as_str)
        .unwrap_or("openai-compatible");
    if enabled && provider == "openai-compatible" {
        optional_key(AI_KEYRING_ACCOUNT)
    } else {
        Ok(None)
    }
}

#[tauri::command]
fn save_binance_key(api_key: String) -> Result<Value, String> {
    let normalized = api_key.trim();
    if normalized.len() < 16 {
        return Err("The Binance API Key appears incomplete".to_string());
    }
    keyring_entry(BINANCE_KEYRING_ACCOUNT)?
        .set_password(normalized)
        .map_err(|error| format!("Could not save the Binance API Key: {error}"))?;
    Ok(json!({"configured": true}))
}

#[tauri::command]
fn delete_binance_key() -> Result<Value, String> {
    match keyring_entry(BINANCE_KEYRING_ACCOUNT)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(json!({"configured": false})),
        Err(error) => Err(format!("Could not remove the Binance API Key: {error}")),
    }
}

#[tauri::command]
fn binance_key_status() -> Result<Value, String> {
    match keyring_entry(BINANCE_KEYRING_ACCOUNT)?.get_password() {
        Ok(value) => Ok(json!({"configured": !value.trim().is_empty()})),
        Err(keyring::Error::NoEntry) => Ok(json!({"configured": false})),
        Err(error) => Err(format!("Could not read Binance credential status: {error}")),
    }
}

#[tauri::command]
fn binance_preflight(app: AppHandle, tickers: Vec<String>) -> Result<Value, String> {
    let api_key = keyring_entry(BINANCE_KEYRING_ACCOUNT)?
        .get_password()
        .map_err(|error| match error {
            keyring::Error::NoEntry => {
                "Configure a Binance API Key before running preflight".to_string()
            }
            other => format!("Could not read the Binance API Key: {other}"),
        })?;
    let mut arguments = vec!["binance-preflight".to_string()];
    arguments.extend(tickers);
    run_json_command(&app, &arguments, Some(&api_key), None)
}

#[tauri::command]
fn save_ai_key(api_key: String) -> Result<Value, String> {
    let normalized = api_key.trim();
    if normalized.len() < 8 {
        return Err("The AI provider API Key appears incomplete".to_string());
    }
    keyring_entry(AI_KEYRING_ACCOUNT)?
        .set_password(normalized)
        .map_err(|error| format!("Could not save the AI provider API Key: {error}"))?;
    Ok(json!({"configured": true}))
}

#[tauri::command]
fn delete_ai_key() -> Result<Value, String> {
    match keyring_entry(AI_KEYRING_ACCOUNT)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(json!({"configured": false})),
        Err(error) => Err(format!("Could not remove the AI provider API Key: {error}")),
    }
}

#[tauri::command]
fn ai_key_status() -> Result<Value, String> {
    Ok(json!({"configured": optional_key(AI_KEYRING_ACCOUNT)?.is_some()}))
}

#[tauri::command]
fn test_ai_provider(app: AppHandle, research_config: Value) -> Result<Value, String> {
    let arguments = vec![
        "test-ai".to_string(),
        "--research-config-json".to_string(),
        serde_json::to_string(&research_config).map_err(|error| error.to_string())?,
    ];
    let ai_key = ai_key_for_config(&research_config, true)?;
    run_json_command(&app, &arguments, None, ai_key.as_deref())
}

fn write_stopped_status(app: &AppHandle, reason: &str) -> Result<(), String> {
    let status_path = state_directory(app)?.join("desktop_agent_status.json");
    let payload = json!({
        "running": false,
        "state": "stopped",
        "stopped_reason": reason,
    });
    fs::write(
        status_path,
        serde_json::to_vec_pretty(&payload).map_err(|error| error.to_string())?,
    )
    .map_err(|error| format!("Could not update agent status: {error}"))
}

fn stop_agent_inner(app: &AppHandle, state: &AgentProcess, reason: &str) -> Result<bool, String> {
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "Agent process lock is poisoned".to_string())?;
    let stopped = if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
        true
    } else {
        false
    };
    write_stopped_status(app, reason)?;
    Ok(stopped)
}

#[tauri::command]
fn start_agent(
    app: AppHandle,
    state: State<'_, AgentProcess>,
    tickers: Vec<String>,
    options: AgentStartOptions,
) -> Result<Value, String> {
    let AgentStartOptions {
        interval_minutes,
        initial_cash,
        auto_promote_paper,
        risk_config,
        research_config,
    } = options;
    if interval_minutes < 1.0 {
        return Err("The cycle interval must be at least one minute".to_string());
    }
    if tickers.is_empty() {
        return Err("Add at least one ticker to the agent universe".to_string());
    }
    let context = python_context(&app)?;
    let state_dir = state_directory(&app)?;
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "Agent process lock is poisoned".to_string())?;
    if let Some(child) = guard.as_mut() {
        if child
            .try_wait()
            .map_err(|error| error.to_string())?
            .is_none()
        {
            return Err("The paper agent is already running".to_string());
        }
        guard.take();
    }

    let mut command = Command::new(&context.executable);
    command
        .current_dir(&context.root)
        .env("PYTHONPATH", &context.root)
        .arg("-m")
        .arg("src.desktop.agent_daemon")
        .arg("--state-dir")
        .arg(&state_dir)
        .arg("--tickers")
        .args(&tickers)
        .arg("--interval-minutes")
        .arg(interval_minutes.to_string())
        .arg("--cash")
        .arg(initial_cash.to_string())
        .arg("--risk-config-json")
        .arg(serde_json::to_string(&risk_config).map_err(|error| error.to_string())?)
        .arg("--research-config-json")
        .arg(serde_json::to_string(&research_config).map_err(|error| error.to_string())?)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    if let Some(ai_key) = ai_key_for_config(&research_config, false)? {
        command.env("BERKSHIRE_NEXUS_AI_API_KEY", ai_key);
    }
    if auto_promote_paper {
        command.arg("--auto-promote-paper");
    }
    let child = command
        .spawn()
        .map_err(|error| format!("Could not start the paper agent: {error}"))?;
    let pid = child.id();
    *guard = Some(child);
    Ok(json!({"running": true, "pid": pid, "tickers": tickers}))
}

#[tauri::command]
fn stop_agent(app: AppHandle, state: State<'_, AgentProcess>) -> Result<Value, String> {
    let stopped = stop_agent_inner(&app, &state, "operator_request")?;
    Ok(json!({"running": false, "stopped_process": stopped}))
}

#[tauri::command]
fn agent_runtime_status(app: AppHandle, state: State<'_, AgentProcess>) -> Result<Value, String> {
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "Agent process lock is poisoned".to_string())?;
    let (running, pid) = if let Some(child) = guard.as_mut() {
        match child.try_wait().map_err(|error| error.to_string())? {
            None => (true, Some(child.id())),
            Some(_) => {
                guard.take();
                (false, None)
            }
        }
    } else {
        (false, None)
    };
    let status_path = state_directory(&app)?.join("desktop_agent_status.json");
    let persisted: Value = fs::read(&status_path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or_else(|| json!({"state": "stopped", "cycles_completed": 0}));
    Ok(json!({"running": running, "pid": pid, "status": persisted}))
}

pub fn run() {
    let app = tauri::Builder::default()
        .manage(AgentProcess::default())
        .setup(|app| {
            let show = MenuItem::with_id(app, "show", "显示 BerkshireNexus", true, None::<&str>)?;
            let stop = MenuItem::with_id(app, "stop", "停止 Paper Agent", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &stop, &quit])?;
            let icon = app.default_window_icon().cloned();
            let mut tray =
                TrayIconBuilder::new()
                    .menu(&menu)
                    .on_menu_event(|app, event| match event.id.as_ref() {
                        "show" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        "stop" => {
                            let state = app.state::<AgentProcess>();
                            let _ = stop_agent_inner(app, &state, "tray_request");
                        }
                        "quit" => app.exit(0),
                        _ => {}
                    });
            if let Some(icon) = icon {
                tray = tray.icon(icon);
            }
            tray.build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![
            app_snapshot,
            analyze_tickers,
            run_paper_cycle,
            load_desktop_settings,
            save_desktop_settings,
            promote_model,
            save_binance_key,
            delete_binance_key,
            binance_key_status,
            binance_preflight,
            save_ai_key,
            delete_ai_key,
            ai_key_status,
            test_ai_provider,
            start_agent,
            stop_agent,
            agent_runtime_status,
        ])
        .build(tauri::generate_context!())
        .expect("error while building BerkshireNexus desktop application");

    app.run(|app_handle, event| {
        if matches!(event, RunEvent::Exit) {
            let state = app_handle.state::<AgentProcess>();
            let _ = stop_agent_inner(app_handle, &state, "application_exit");
        }
    });
}
