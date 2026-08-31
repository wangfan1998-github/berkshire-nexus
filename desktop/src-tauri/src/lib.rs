use serde_json::{json, Value};
use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::collections::HashMap;
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent};

const KEYRING_SERVICE: &str = "com.berkshire.nexus";
const BINANCE_KEYRING_ACCOUNT: &str = "binance-api-key";
const BINANCE_SECRET_KEYRING_ACCOUNT: &str = "binance-api-secret";
const AI_KEYRING_ACCOUNT: &str = "ai-provider-api-key";
// Mirrors LIVE_ACKNOWLEDGEMENT in src/trading/binance_stocks.py. The UI must
// send this verbatim before any real order is submitted.
const LIVE_ACKNOWLEDGEMENT: &str = "我确认使用真实资金";

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
    run_json_command_full(app, arguments, binance_api_key, None, ai_api_key, false)
}

/// Full variant which can also pass the Binance secret and the live-trading
/// acknowledgement. Credentials travel as environment variables of the child
/// process so they never appear in argv (visible to any local `ps`).
fn run_json_command_full(
    app: &AppHandle,
    arguments: &[String],
    binance_api_key: Option<&str>,
    binance_api_secret: Option<&str>,
    ai_api_key: Option<&str>,
    acknowledge_live: bool,
) -> Result<Value, String> {
    let (mut command, _) = command_base(app)?;
    command.args(arguments);
    if let Some(value) = binance_api_key {
        command.env("BINANCE_API_KEY", value);
    }
    if let Some(value) = binance_api_secret {
        command.env("BINANCE_API_SECRET", value);
    }
    if let Some(value) = ai_api_key {
        command.env("BERKSHIRE_NEXUS_AI_API_KEY", value);
    }
    if acknowledge_live {
        // Second of the two independent live gates; the first is the explicit
        // confirmation string checked in Python.
        command.env("BERKSHIRE_NEXUS_LIVE_TRADING", LIVE_ACKNOWLEDGEMENT);
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
async fn app_snapshot(app: AppHandle) -> Result<Value, String> {
    run_json_command(&app, &["snapshot".to_string()], None, None)
}

#[tauri::command]
async fn analyze_tickers(
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
async fn run_paper_cycle(
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
async fn promote_model(app: AppHandle) -> Result<Value, String> {
    run_json_command(&app, &["model-promote".to_string()], None, None)
}

/// Process-lifetime cache of secrets already read from the keychain.
///
/// macOS prompts per *unlock*, and a self-signed app cannot avoid that: the
/// partition list only accepts `apple:`, `apple-tool:`, a 10-character Apple
/// Team ID, or a cdhash. This certificate has no Team ID (`TeamIdentifier=not
/// set`) and a cdhash changes on every build, so no partition entry can ever
/// match — the earlier attempt wrote the certificate SHA-1, which is simply not
/// a Team ID and was therefore inert.
///
/// What is fixable is how *often* we unlock. Reading each secret once per launch
/// and reusing it turns "a prompt on every operation" into at most one per
/// secret per launch. Values live only in memory and are dropped on exit.
static SECRET_CACHE: Mutex<Option<HashMap<String, String>>> = Mutex::new(None);

fn cached_secret(account: &str) -> Option<String> {
    let guard = SECRET_CACHE.lock().ok()?;
    guard.as_ref()?.get(account).cloned()
}

fn remember_secret(account: &str, value: &str) {
    if let Ok(mut guard) = SECRET_CACHE.lock() {
        guard
            .get_or_insert_with(HashMap::new)
            .insert(account.to_string(), value.to_string());
    }
}

fn forget_secret(account: &str) {
    if let Ok(mut guard) = SECRET_CACHE.lock() {
        if let Some(map) = guard.as_mut() {
            map.remove(account);
        }
    }
}

fn keyring_entry(account: &str) -> Result<keyring::Entry, String> {
    keyring::Entry::new(KEYRING_SERVICE, account)
        .map_err(|error| format!("Could not access the operating system credential store: {error}"))
}

fn optional_key(account: &str) -> Result<Option<String>, String> {
    if let Some(value) = cached_secret(account) {
        return Ok(Some(value));
    }
    match keyring_entry(account)?.get_password() {
        Ok(value) if !value.trim().is_empty() => {
            remember_secret(account, &value);
            Ok(Some(value))
        }
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
    remember_secret(BINANCE_KEYRING_ACCOUNT, normalized);
    keyring_entry(BINANCE_KEYRING_ACCOUNT)?
        .set_password(normalized)
        .map_err(|error| format!("Could not save the Binance API Key: {error}"))?;
    Ok(json!({"configured": true}))
}

#[tauri::command]
fn delete_binance_key() -> Result<Value, String> {
    forget_secret(BINANCE_KEYRING_ACCOUNT);
    match keyring_entry(BINANCE_KEYRING_ACCOUNT)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(json!({"configured": false})),
        Err(error) => Err(format!("Could not remove the Binance API Key: {error}")),
    }
}

#[tauri::command]
fn binance_key_status() -> Result<Value, String> {
    Ok(json!({"configured": optional_key(BINANCE_KEYRING_ACCOUNT)?.is_some()}))
}

#[tauri::command]
async fn binance_preflight(app: AppHandle, tickers: Vec<String>) -> Result<Value, String> {
    let api_key = optional_key(BINANCE_KEYRING_ACCOUNT)?
        .ok_or_else(|| "Configure a Binance API Key before running preflight".to_string())?;
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
    remember_secret(AI_KEYRING_ACCOUNT, normalized);
    keyring_entry(AI_KEYRING_ACCOUNT)?
        .set_password(normalized)
        .map_err(|error| format!("Could not save the AI provider API Key: {error}"))?;
    Ok(json!({"configured": true}))
}

#[tauri::command]
fn delete_ai_key() -> Result<Value, String> {
    forget_secret(AI_KEYRING_ACCOUNT);
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
fn save_binance_secret(api_secret: String) -> Result<Value, String> {
    let normalized = api_secret.trim();
    if normalized.len() < 16 {
        return Err("The Binance API Secret appears incomplete".to_string());
    }
    // The Secret is only displayed once, at key-creation time. Revisiting the
    // API management page shows the Key but not the Secret, so pasting the Key
    // into this field is an easy mistake that surfaces later as an opaque
    // -1022 signature error. Reject it up front.
    if let Some(existing_key) = optional_key(BINANCE_KEYRING_ACCOUNT)? {
        if existing_key.trim() == normalized {
            return Err(
                "This value is identical to your API Key, so it cannot be the Secret. \
                 Binance shows the Secret only once, when the key is created — if it \
                 was not saved then, create a new API key pair and copy the Secret \
                 from the creation screen."
                    .to_string(),
            );
        }
    }
    remember_secret(BINANCE_SECRET_KEYRING_ACCOUNT, normalized);
    keyring_entry(BINANCE_SECRET_KEYRING_ACCOUNT)?
        .set_password(normalized)
        .map_err(|error| format!("Could not save the Binance API Secret: {error}"))?;
    Ok(json!({"configured": true}))
}

/// Signed round-trip against Binance to prove the credential pair works.
/// Reports the failure cause in plain language instead of a bare error code.
#[tauri::command]
async fn verify_binance_credentials(app: AppHandle) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    if key.trim() == secret.trim() {
        return Err(
            "API Key and Secret are the same value. The Secret is shown only at \
             key-creation time; create a new key pair and copy it from that screen."
                .to_string(),
        );
    }
    run_json_command_full(
        &app,
        &["verify-credentials".to_string()],
        Some(&key),
        Some(&secret),
        None,
        false,
    )
}

#[tauri::command]
fn delete_binance_secret() -> Result<Value, String> {
    forget_secret(BINANCE_SECRET_KEYRING_ACCOUNT);
    match keyring_entry(BINANCE_SECRET_KEYRING_ACCOUNT)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(json!({"configured": false})),
        Err(error) => Err(format!("Could not remove the Binance API Secret: {error}")),
    }
}

#[tauri::command]
fn binance_secret_status() -> Result<Value, String> {
    Ok(json!({
        "configured": optional_key(BINANCE_SECRET_KEYRING_ACCOUNT)?.is_some()
    }))
}

/// Read both Binance credentials, failing with actionable guidance when either
/// is absent. Signed endpoints are unusable without the secret.
fn binance_credentials() -> Result<(String, String), String> {
    let key = optional_key(BINANCE_KEYRING_ACCOUNT)?
        .ok_or_else(|| "Configure a Binance API Key first".to_string())?;
    let secret = optional_key(BINANCE_SECRET_KEYRING_ACCOUNT)?.ok_or_else(|| {
        "Configure a Binance API Secret first — signed account and order endpoints require it"
            .to_string()
    })?;
    Ok((key, secret))
}

/// AI supply-chain daily briefing. Read-only: it never places an order.
#[tauri::command]
async fn daily_briefing(
    app: AppHandle,
    research_config: Value,
    per_segment: u32,
    segments: Option<Vec<String>>,
    minimum_score: f64,
) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    let mut arguments = vec![
        "briefing".to_string(),
        "--per-segment".to_string(),
        per_segment.max(1).to_string(),
        "--minimum-score".to_string(),
        minimum_score.to_string(),
        "--research-config-json".to_string(),
        serde_json::to_string(&research_config).map_err(|error| error.to_string())?,
    ];
    if let Some(values) = segments.filter(|items| !items.is_empty()) {
        arguments.push("--segments".to_string());
        arguments.extend(values);
    }
    let ai_key = ai_key_for_config(&research_config, false)?;
    run_json_command_full(&app, &arguments, Some(&key), Some(&secret), ai_key.as_deref(), false)
}

#[tauri::command]
async fn screen_market(app: AppHandle, per_segment: u32) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    run_json_command_full(
        &app,
        &[
            "screen".to_string(),
            "--per-segment".to_string(),
            per_segment.max(1).to_string(),
        ],
        Some(&key),
        Some(&secret),
        None,
        false,
    )
}

#[tauri::command]
async fn live_account(app: AppHandle) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    run_json_command_full(
        &app,
        &["live-account".to_string()],
        Some(&key),
        Some(&secret),
        None,
        false,
    )
}

#[tauri::command]
async fn live_reconcile(app: AppHandle) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    run_json_command_full(
        &app,
        &["live-reconcile".to_string()],
        Some(&key),
        Some(&secret),
        None,
        false,
    )
}

#[tauri::command]
async fn live_accept_disclaimer(app: AppHandle) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    run_json_command_full(
        &app,
        &["live-accept-disclaimer".to_string()],
        Some(&key),
        Some(&secret),
        None,
        false,
    )
}

#[tauri::command]
async fn live_cancel_all(app: AppHandle, symbol: Option<String>) -> Result<Value, String> {
    let (key, secret) = binance_credentials()?;
    let mut arguments = vec!["live-cancel-all".to_string()];
    if let Some(value) = symbol.filter(|item| !item.trim().is_empty()) {
        arguments.push("--symbol".to_string());
        arguments.push(value);
    }
    // Cancelling reduces exposure, so it only needs the environment gate.
    run_json_command_full(&app, &arguments, Some(&key), Some(&secret), None, true)
}

/// Preview or submit a live cycle.
///
/// `submit` alone is not enough: `confirmation` must equal the acknowledgement
/// string, and only then is the environment gate set for the child process.
#[tauri::command]
async fn run_live_cycle(
    app: AppHandle,
    tickers: Vec<String>,
    risk_config: Value,
    research_config: Value,
    confirmation: String,
    submit: bool,
) -> Result<Value, String> {
    if tickers.is_empty() {
        return Err("Add at least one ticker before running a live cycle".to_string());
    }
    let acknowledged = confirmation.trim() == LIVE_ACKNOWLEDGEMENT;
    if submit && !acknowledged {
        return Err(format!(
            "Live submission requires the confirmation phrase {LIVE_ACKNOWLEDGEMENT}"
        ));
    }
    let (key, secret) = binance_credentials()?;
    let mut arguments = vec!["live-cycle".to_string()];
    arguments.extend(tickers);
    arguments.push("--risk-config-json".to_string());
    arguments.push(serde_json::to_string(&risk_config).map_err(|error| error.to_string())?);
    arguments.push("--research-config-json".to_string());
    arguments.push(serde_json::to_string(&research_config).map_err(|error| error.to_string())?);
    if acknowledged {
        arguments.push("--confirmation".to_string());
        arguments.push(confirmation.trim().to_string());
    }
    if submit && acknowledged {
        arguments.push("--submit".to_string());
    }
    let ai_key = ai_key_for_config(&research_config, false)?;
    run_json_command_full(
        &app,
        &arguments,
        Some(&key),
        Some(&secret),
        ai_key.as_deref(),
        submit && acknowledged,
    )
}

/// Redeem Simple Earn savings into the CARD wallet so a BUY can be funded.
///
/// Binance does not auto-redeem, so an Earn balance cannot pay for an order.
/// This moves real money, so it takes the same confirmation phrase as a live
/// cycle rather than the lighter gate used by cancel-all.
#[tauri::command]
async fn live_redeem_earn(
    app: AppHandle,
    product_id: String,
    amount: Option<f64>,
    redeem_all: bool,
    confirmation: String,
) -> Result<Value, String> {
    if confirmation.trim() != LIVE_ACKNOWLEDGEMENT {
        return Err(format!(
            "Redeeming savings requires the confirmation phrase {LIVE_ACKNOWLEDGEMENT}"
        ));
    }
    if product_id.trim().is_empty() {
        return Err("A Simple Earn product id is required to redeem".to_string());
    }
    if !redeem_all && !amount.is_some_and(|value| value > 0.0) {
        return Err("Specify an amount to redeem, or redeem the whole position".to_string());
    }
    let (key, secret) = binance_credentials()?;
    let mut arguments = vec![
        "live-redeem-earn".to_string(),
        "--product-id".to_string(),
        product_id.trim().to_string(),
        "--confirmation".to_string(),
        confirmation.trim().to_string(),
    ];
    if redeem_all {
        arguments.push("--all".to_string());
    } else if let Some(value) = amount {
        arguments.push("--amount".to_string());
        arguments.push(value.to_string());
    }
    run_json_command_full(&app, &arguments, Some(&key), Some(&secret), None, true)
}

#[tauri::command]
async fn test_ai_provider(app: AppHandle, research_config: Value) -> Result<Value, String> {
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
            save_binance_secret,
            delete_binance_secret,
            binance_secret_status,
            verify_binance_credentials,
            live_account,
            daily_briefing,
            screen_market,
            live_reconcile,
            live_accept_disclaimer,
            live_cancel_all,
            live_redeem_earn,
            run_live_cycle,
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
